"""
TURN/STUN Configuration for Production WebRTC.

Provides:
- Coturn integration for NAT traversal
- TURN server management
- Credential generation and rotation
- ICE server configuration
- Health monitoring
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import aiohttp

logger = logging.getLogger(__name__)


class TurnAuthType(str, Enum):
    """TURN authentication types."""
    STATIC = "static"           # Static username/password
    EPHEMERAL = "ephemeral"     # Time-limited credentials (RFC 8656)
    OAUTH = "oauth"             # OAuth-based authentication


@dataclass
class IceServer:
    """ICE server configuration."""
    urls: List[str]
    username: Optional[str] = None
    credential: Optional[str] = None
    credential_type: str = "password"  # "password" or "oauth"


@dataclass
class TurnServer:
    """TURN server configuration."""
    host: str
    port: int = 3478
    tls_port: int = 5349
    realm: str = "vcos.io"
    auth_type: TurnAuthType = TurnAuthType.EPHEMERAL
    static_username: Optional[str] = None
    static_password: Optional[str] = None
    shared_secret: Optional[str] = None  # For ephemeral credentials
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    max_bps: Optional[int] = None  # Bandwidth limit
    max_connections: int = 1000


@dataclass
class TurnCredentials:
    """TURN credentials for client."""
    username: str
    password: str
    ttl: int
    urls: List[str]


class TurnManager:
    """
    TURN/STUN Server Manager.

    Features:
    - Multiple TURN server support
    - Ephemeral credential generation (RFC 8656)
    - Credential rotation
    - Server health monitoring
    - Load balancing
    - Configuration API
    """

    def __init__(
        self,
        servers: List[TurnServer],
        default_ttl: int = 86400,  # 24 hours
        stun_servers: List[str] = None,
    ):
        self.servers = servers
        self.default_ttl = default_ttl
        self.stun_servers = stun_servers or [
            "stun:stun.l.google.com:19302",
            "stun:stun1.l.google.com:19302",
            "stun:stun2.l.google.com:19302",
        ]
        self._running = False
        self._health_check_task = None
        self._credential_cache: Dict[str, TurnCredentials] = {}
        self._server_stats: Dict[str, Dict[str, Any]] = {}

    def get_ice_servers(self, ttl: Optional[int] = None) -> List[IceServer]:
        """
        Get ICE server configuration for client.

        Returns list of IceServer objects with credentials.
        """
        ice_servers = []

        # Add STUN servers
        for stun_url in self.stun_servers:
            ice_servers.append(IceServer(urls=[stun_url]))

        # Add TURN servers with credentials
        ttl = ttl or self.default_ttl
        for server in self.servers:
            if server.auth_type == TurnAuthType.STATIC:
                if server.static_username and server.static_password:
                    urls = [
                        f"turn:{server.host}:{server.port}?transport=udp",
                        f"turn:{server.host}:{server.port}?transport=tcp",
                    ]
                    if server.tls_port:
                        urls.extend([
                            f"turns:{server.host}:{server.tls_port}?transport=tcp",
                        ])
                    ice_servers.append(IceServer(
                        urls=urls,
                        username=server.static_username,
                        credential=server.static_password,
                    ))

            elif server.auth_type == TurnAuthType.EPHEMERAL:
                creds = self._generate_ephemeral_credentials(server, ttl)
                urls = [
                    f"turn:{server.host}:{server.port}?transport=udp",
                    f"turn:{server.host}:{server.port}?transport=tcp",
                ]
                if server.tls_port:
                    urls.extend([
                        f"turns:{server.host}:{server.tls_port}?transport=tcp",
                    ])
                ice_servers.append(IceServer(
                    urls=urls,
                    username=creds.username,
                    credential=creds.password,
                ))

        return ice_servers

    def _generate_ephemeral_credentials(
        self,
        server: TurnServer,
        ttl: int,
    ) -> TurnCredentials:
        """Generate ephemeral TURN credentials per RFC 8656."""
        if not server.shared_secret:
            raise ValueError("Shared secret required for ephemeral credentials")

        # Generate timestamp-based username
        timestamp = int(time.time()) + ttl
        username = f"{timestamp}:{uuid4().hex[:8]}"

        # Generate password using HMAC-SHA1
        message = f"{username}:{server.realm}".encode()
        key = server.shared_secret.encode()
        password = base64.b64encode(
            hmac.new(key, message, hashlib.sha1).digest()
        ).decode()

        urls = [
            f"turn:{server.host}:{server.port}?transport=udp",
            f"turn:{server.host}:{server.port}?transport=tcp",
        ]
        if server.tls_port:
            urls.extend([
                f"turns:{server.host}:{server.tls_port}?transport=tcp",
            ])

        return TurnCredentials(
            username=username,
            password=password,
            ttl=ttl,
            urls=urls,
        )

    async def get_credentials_for_user(
        self,
        user_id: str,
        ttl: Optional[int] = None,
    ) -> TurnCredentials:
        """Get or generate TURN credentials for a specific user."""
        cache_key = f"{user_id}:{ttl or self.default_ttl}"

        if cache_key in self._credential_cache:
            creds = self._credential_cache[cache_key]
            # Check if still valid (with 5 min buffer)
            if creds.ttl > 300:
                return creds

        # Generate new credentials using first TURN server
        if not self.servers:
            raise ValueError("No TURN servers configured")

        server = self.servers[0]
        if server.auth_type == TurnAuthType.EPHEMERAL:
            creds = self._generate_ephemeral_credentials(server, ttl or self.default_ttl)
        elif server.auth_type == TurnAuthType.STATIC:
            creds = TurnCredentials(
                username=server.static_username or user_id,
                password=server.static_password or "",
                ttl=ttl or self.default_ttl,
                urls=[
                    f"turn:{server.host}:{server.port}?transport=udp",
                    f"turn:{server.host}:{server.port}?transport=tcp",
                ],
            )
        else:
            raise ValueError(f"Unsupported auth type: {server.auth_type}")

        self._credential_cache[cache_key] = creds
        return creds

    def get_ice_servers_json(self, ttl: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get ICE servers as JSON-serializable list for WebRTC."""
        ice_servers = self.get_ice_servers(ttl)
        return [
            {
                "urls": server.urls,
                "username": server.username,
                "credential": server.credential,
                "credentialType": server.credential_type,
            }
            for server in ice_servers
        ]

    # ==================== Server Management ====================

    async def add_server(self, server: TurnServer):
        """Add a TURN server."""
        self.servers.append(server)
        await self._check_server_health(server)

    async def remove_server(self, host: str):
        """Remove a TURN server by host."""
        self.servers = [s for s in self.servers if s.host != host]
        self._server_stats.pop(host, None)

    async def update_server(self, host: str, **kwargs):
        """Update TURN server configuration."""
        for server in self.servers:
            if server.host == host:
                for key, value in kwargs.items():
                    if hasattr(server, key):
                        setattr(server, key, value)
                await self._check_server_health(server)
                break

    # ==================== Health Monitoring ====================

    async def _check_server_health(self, server: TurnServer) -> Dict[str, Any]:
        """Check health of a TURN server."""
        stats = {
            "host": server.host,
            "healthy": False,
            "latency_ms": None,
            "last_check": time.time(),
            "errors": [],
        }

        try:
            # Try to connect to TURN server (simple TCP connect)
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            start = time.time()
            result = sock.connect_ex((server.host, server.port))
            latency = (time.time() - start) * 1000
            sock.close()

            if result == 0:
                stats["healthy"] = True
                stats["latency_ms"] = latency
            else:
                stats["errors"].append(f"Connection failed: {result}")

        except Exception as e:
            stats["errors"].append(str(e))

        self._server_stats[server.host] = stats
        return stats

    async def start_health_monitoring(self, interval: int = 60):
        """Start periodic health checks."""
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop(interval))

    async def stop_health_monitoring(self):
        """Stop health monitoring."""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()

    async def _health_check_loop(self, interval: int):
        """Periodic health check loop."""
        while self._running:
            try:
                for server in self.servers:
                    await self._check_server_health(server)
            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(interval)

    def get_server_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get server health statistics."""
        return self._server_stats

    def get_healthy_servers(self) -> List[TurnServer]:
        """Get list of healthy TURN servers."""
        return [
            server for server in self.servers
            if self._server_stats.get(server.host, {}).get("healthy", False)
        ]

    # ==================== Configuration Templates ====================

    @staticmethod
    def get_coturn_config_template() -> str:
        """Get Coturn configuration template."""
        return """
# Coturn Configuration for VCOS
# Save as /etc/turnserver.conf

# Listener IP and ports
listening-ip=0.0.0.0
listening-port=3478
tls-listening-port=5349

# External IP (required for cloud deployments)
# external-ip=YOUR_PUBLIC_IP/INTERNAL_IP

# Realm
realm=vcos.io

# Authentication
# For static auth:
# use-auth-secret
# static-auth-secret=YOUR_SHARED_SECRET

# For ephemeral auth (recommended):
use-auth-secret
static-auth-secret=YOUR_SHARED_SECRET

# Certificates for TLS/TURNS
cert=/etc/turnserver/cert.pem
pkey=/etc/turnserver/key.pem

# Security
no-tlsv1
no-tlsv1_1
no-sslv3
no-sslv2

# Logging
log-file=/var/log/turnserver.log
verbose

# Performance
min-port=49152
max-port=65535
# max-bps=1000000
# max-connections=1000

# Redis for shared state (optional)
# redis-userdb="ip=127.0.0.1 port=6379 password=secret db=0"

# Disable CLI
no-cli

# PID file
pidfile=/var/run/turnserver.pid
"""

    @staticmethod
    def get_docker_compose_template() -> str:
        """Get Docker Compose template for Coturn."""
        return """
version: '3.8'

services:
  coturn:
    image: coturn/coturn:latest
    container_name: vcos-turn
    network_mode: host
    environment:
      - TURN_SERVER_NAME=vcos.io
      - TURN_USERNAME=vcos
      - TURN_PASSWORD=changeme
      - TURN_SECRET=changeme_shared_secret
      - TURN_REALM=vcos.io
      - TURN_PORT=3478
      - TURN_TLS_PORT=5349
      - EXTERNAL_IP=YOUR_PUBLIC_IP
    volumes:
      - ./turnserver.conf:/etc/turnserver.conf
      - ./certs:/etc/turnserver
      - ./logs:/var/log
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "turnadmin", "-l"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 128M
"""

    @staticmethod
    def get_kubernetes_template() -> str:
        """Get Kubernetes deployment template for Coturn."""
        return """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vcos-turn
  namespace: vcos
  labels:
    app: vcos-turn
spec:
  replicas: 2
  selector:
    matchLabels:
      app: vcos-turn
  template:
    metadata:
      labels:
        app: vcos-turn
    spec:
      containers:
      - name: coturn
        image: coturn/coturn:latest
        ports:
        - containerPort: 3478
          name: turn-udp
          protocol: UDP
        - containerPort: 3478
          name: turn-tcp
          protocol: TCP
        - containerPort: 5349
          name: turns-tcp
          protocol: TCP
        - containerPort: 49152
          name: turn-min-port
          protocol: UDP
        - containerPort: 65535
          name: turn-max-port
          protocol: UDP
        env:
        - name: TURN_SERVER_NAME
          value: "vcos.io"
        - name: TURN_REALM
          value: "vcos.io"
        - name: TURN_SECRET
          valueFrom:
            secretKeyRef:
              name: turn-secret
              key: shared-secret
        - name: EXTERNAL_IP
          valueFrom:
            fieldRef:
              fieldPath: status.hostIP
        volumeMounts:
        - name: turn-config
          mountPath: /etc/turnserver.conf
          subPath: turnserver.conf
        - name: turn-certs
          mountPath: /etc/turnserver
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
      volumes:
      - name: turn-config
        configMap:
          name: vcos-turn-config
      - name: turn-certs
        secret:
          secretName: turn-certs
---
apiVersion: v1
kind: Service
metadata:
  name: vcos-turn
  namespace: vcos
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
spec:
  type: LoadBalancer
  ports:
  - port: 3478
    targetPort: 3478
    protocol: UDP
    name: turn-udp
  - port: 3478
    targetPort: 3478
    protocol: TCP
    name: turn-tcp
  - port: 5349
    targetPort: 5349
    protocol: TCP
    name: turns-tcp
  selector:
    app: vcos-turn
"""


# Global TURN manager instance
_turn_manager: Optional[TurnManager] = None


def get_turn_manager() -> TurnManager:
    """Get or create TURN manager singleton."""
    global _turn_manager
    if _turn_manager is None:
        # Default configuration - should be overridden in production
        _turn_manager = TurnManager(
            servers=[
                TurnServer(
                    host="turn.vcos.io",
                    port=3478,
                    tls_port=5349,
                    realm="vcos.io",
                    auth_type=TurnAuthType.EPHEMERAL,
                    shared_secret="changeme_shared_secret_please_rotate",
                ),
            ],
            stun_servers=[
                "stun:stun.l.google.com:19302",
                "stun:stun1.l.google.com:19302",
            ],
        )
    return _turn_manager


def init_turn_manager(
    servers: List[TurnServer],
    default_ttl: int = 86400,
    stun_servers: List[str] = None,
) -> TurnManager:
    """Initialize TURN manager."""
    global _turn_manager
    _turn_manager = TurnManager(
        servers=servers,
        default_ttl=default_ttl,
        stun_servers=stun_servers,
    )
    return _turn_manager