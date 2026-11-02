"""
SIEM Integration for VCOS.

Provides:
- OCSF (Open Cybersecurity Schema Framework) event format
- Multiple SIEM backend support (Splunk, Datadog, Elastic, Sentinel, Generic)
- Real-time event streaming
- Batch export capabilities
- Custom field mapping
- Secure delivery with retries
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from collections import deque

import aiohttp
import aiofiles

from app.core.config import settings

logger = logging.getLogger(__name__)


class SIEMBackend(str, Enum):
    """Supported SIEM backends."""
    SPLUNK_HEC = "splunk_hec"
    DATADOG = "datadog"
    ELASTIC = "elastic"
    AZURE_SENTINEL = "azure_sentinel"
    GENERIC_HTTP = "generic_http"
    SYSLOG = "syslog"
    KAFKA = "kafka"


class OCSFClass(str, Enum):
    """OCSF Event Classes."""
    # Authentication
    AUTHENTICATION = "authentication"
    # Authorization
    AUTHORIZATION = "authorization"
    # Data Security
    DATA_SECURITY = "data_security"
    # System Activity
    SYSTEM_ACTIVITY = "system_activity"
    # Network Activity
    NETWORK_ACTIVITY = "network_activity"
    # Security Finding
    SECURITY_FINDING = "security_finding"
    # Alert
    ALERT = "alert"
    # Incident
    INCIDENT = "incident"
    # Vulnerability
    VULNERABILITY = "vulnerability"
    # Compliance
    COMPLIANCE = "compliance"


class OCSFCategory(str, Enum):
    """OCSF Event Categories."""
    # Authentication
    LOGON = "logon"
    LOGOFF = "logoff"
    LOGON_FAILED = "logon_failed"
    MFA_CHALLENGE = "mfa_challenge"
    PASSWORD_CHANGE = "password_change"
    
    # Authorization
    PERMISSION_CHANGE = "permission_change"
    ROLE_ASSIGNMENT = "role_assignment"
    POLICY_CHANGE = "policy_change"
    
    # Data Security
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    DATA_DELETION = "data_deletion"
    DATA_EXPORT = "data_export"
    DLP_VIOLATION = "dlp_violation"
    
    # System Activity
    PROCESS_START = "process_start"
    PROCESS_STOP = "process_stop"
    SERVICE_START = "service_start"
    SERVICE_STOP = "service_stop"
    CONFIG_CHANGE = "config_change"
    SOFTWARE_INSTALL = "software_install"
    
    # Network Activity
    NETWORK_CONNECTION = "network_connection"
    DNS_QUERY = "dns_query"
    HTTP_ACTIVITY = "http_activity"
    
    # Security Finding
    MALWARE_DETECTION = "malware_detection"
    INTRUSION_DETECTION = "intrusion_detection"
    ANOMALY_DETECTION = "anomaly_detection"
    BRUTE_FORCE = "brute_force"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    
    # Alert
    ALERT_GENERATED = "alert_generated"
    ALERT_UPDATED = "alert_updated"
    ALERT_CLOSED = "alert_closed"
    
    # Incident
    INCIDENT_CREATED = "incident_created"
    INCIDENT_UPDATED = "incident_updated"
    INCIDENT_CLOSED = "incident_closed"
    
    # Vulnerability
    VULNERABILITY_DETECTED = "vulnerability_detected"
    VULNERABILITY_PATCHED = "vulnerability_patched"
    
    # Compliance
    COMPLIANCE_CHECK = "compliance_check"
    COMPLIANCE_VIOLATION = "compliance_violation"
    AUDIT_LOG = "audit_log"


class Severity(str, Enum):
    """Event severity levels."""
    UNKNOWN = "unknown"
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class OCSFEvent:
    """OCSF Base Event Structure."""
    # Required fields
    class_name: str  # OCSFClass
    category_name: str  # OCSFCategory
    category_uid: int
    class_uid: int
    activity_id: int  # Specific activity within category
    activity_name: str
    
    # Metadata
    time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    severity: str = Severity.INFORMATIONAL
    severity_id: int = 1
    status: str = "success"
    status_id: int = 1
    message: str = ""
    
    # Actor (User/Service)
    actor: Optional[Dict[str, Any]] = None
    
    # Target (Resource)
    target: Optional[Dict[str, Any]] = None
    
    # Source/Network
    src_endpoint: Optional[Dict[str, Any]] = None
    dst_endpoint: Optional[Dict[str, Any]] = None
    network: Optional[Dict[str, Any]] = None
    
    # Cloud/Infrastructure
    cloud: Optional[Dict[str, Any]] = None
    device: Optional[Dict[str, Any]] = None
    
    # Security
    security_control: Optional[Dict[str, Any]] = None
    vulnerability: Optional[Dict[str, Any]] = None
    
    # Custom/Extensions
    metadata: Dict[str, Any] = field(default_factory=dict)
    unmapped_data: Dict[str, Any] = field(default_factory=dict)
    
    # Risk/Threat
    risk_score: int = 0
    confidence: int = 0
    threat: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {}
        for key, value in asdict(self).items():
            if value is not None:
                result[key] = value
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class OCSFEventBuilder:
    """Builder for creating OCSF events."""
    
    # OCSF Class/Category UID mappings
    CLASS_UIDS = {
        OCSFClass.AUTHENTICATION: 3001,
        OCSFClass.AUTHORIZATION: 3002,
        OCSFClass.DATA_SECURITY: 4001,
        OCSFClass.SYSTEM_ACTIVITY: 5001,
        OCSFClass.NETWORK_ACTIVITY: 4002,
        OCSFClass.SECURITY_FINDING: 2001,
        OCSFClass.ALERT: 5002,
        OCSFClass.INCIDENT: 5003,
        OCSFClass.VULNERABILITY: 2002,
        OCSFClass.COMPLIANCE: 5004,
    }
    
    CATEGORY_UIDS = {
        OCSFCategory.LOGON: 1,
        OCSFCategory.LOGOFF: 2,
        OCSFCategory.LOGON_FAILED: 3,
        OCSFCategory.MFA_CHALLENGE: 4,
        OCSFCategory.PASSWORD_CHANGE: 5,
        OCSFCategory.PERMISSION_CHANGE: 10,
        OCSFCategory.ROLE_ASSIGNMENT: 11,
        OCSFCategory.POLICY_CHANGE: 12,
        OCSFCategory.DATA_ACCESS: 1,
        OCSFCategory.DATA_MODIFICATION: 2,
        OCSFCategory.DATA_DELETION: 3,
        OCSFCategory.DATA_EXPORT: 4,
        OCSFCategory.DLP_VIOLATION: 5,
        OCSFCategory.PROCESS_START: 1,
        OCSFCategory.PROCESS_STOP: 2,
        OCSFCategory.SERVICE_START: 3,
        OCSFCategory.SERVICE_STOP: 4,
        OCSFCategory.CONFIG_CHANGE: 5,
        OCSFCategory.SOFTWARE_INSTALL: 6,
        OCSFCategory.NETWORK_CONNECTION: 1,
        OCSFCategory.DNS_QUERY: 2,
        OCSFCategory.HTTP_ACTIVITY: 3,
        OCSFCategory.MALWARE_DETECTION: 1,
        OCSFCategory.INTRUSION_DETECTION: 2,
        OCSFCategory.ANOMALY_DETECTION: 3,
        OCSFCategory.BRUTE_FORCE: 4,
        OCSFCategory.PRIVILEGE_ESCALATION: 5,
        OCSFCategory.ALERT_GENERATED: 1,
        OCSFCategory.ALERT_UPDATED: 2,
        OCSFCategory.ALERT_CLOSED: 3,
        OCSFCategory.INCIDENT_CREATED: 1,
        OCSFCategory.INCIDENT_UPDATED: 2,
        OCSFCategory.INCIDENT_CLOSED: 3,
        OCSFCategory.VULNERABILITY_DETECTED: 1,
        OCSFCategory.VULNERABILITY_PATCHED: 2,
        OCSFCategory.COMPLIANCE_CHECK: 1,
        OCSFCategory.COMPLIANCE_VIOLATION: 2,
        OCSFCategory.AUDIT_LOG: 3,
    }
    
    ACTIVITY_IDS = {
        OCSFCategory.LOGON: 1,
        OCSFCategory.LOGOFF: 2,
        OCSFCategory.LOGON_FAILED: 3,
        OCSFCategory.MFA_CHALLENGE: 4,
        OCSFCategory.PASSWORD_CHANGE: 5,
        OCSFCategory.PERMISSION_CHANGE: 1,
        OCSFCategory.ROLE_ASSIGNMENT: 2,
        OCSFCategory.POLICY_CHANGE: 3,
        OCSFCategory.DATA_ACCESS: 1,
        OCSFCategory.DATA_MODIFICATION: 2,
        OCSFCategory.DATA_DELETION: 3,
        OCSFCategory.DATA_EXPORT: 4,
        OCSFCategory.DLP_VIOLATION: 5,
        OCSFCategory.BRUTE_FORCE: 4,
        OCSFCategory.ANOMALY_DETECTION: 3,
        OCSFCategory.ALERT_GENERATED: 1,
        OCSFCategory.ALERT_UPDATED: 2,
        OCSFCategory.ALERT_CLOSED: 3,
        OCSFCategory.INCIDENT_CREATED: 1,
        OCSFCategory.INCIDENT_UPDATED: 2,
        OCSFCategory.INCIDENT_CLOSED: 3,
        OCSFCategory.VULNERABILITY_DETECTED: 1,
        OCSFCategory.VULNERABILITY_PATCHED: 2,
        OCSFCategory.COMPLIANCE_CHECK: 1,
        OCSFCategory.COMPLIANCE_VIOLATION: 2,
        OCSFCategory.AUDIT_LOG: 3,
    }
    
    @classmethod
    def build(cls, event_class: OCSFClass, category: OCSFCategory, **kwargs) -> OCSFEvent:
        """Build an OCSF event."""
        return OCSFEvent(
            class_name=event_class.value,
            category_name=category.value,
            category_uid=cls.CATEGORY_UIDS.get(category, 0),
            class_uid=cls.CLASS_UIDS.get(event_class, 0),
            activity_id=cls.ACTIVITY_IDS.get(category, 0),
            activity_name=category.value,
            **kwargs,
        )


@dataclass
class SIEMConfig:
    """SIEM backend configuration."""
    backend: SIEMBackend
    name: str
    enabled: bool = True
    
    # Connection settings
    endpoint: str = ""
    token: str = ""
    api_key: str = ""
    
    # Splunk HEC specific
    hec_token: str = ""
    index: str = "main"
    sourcetype: str = "ocsf"
    
    # Datadog specific
    datadog_api_key: str = ""
    datadog_site: str = "datadoghq.com"
    
    # Elastic specific
    elastic_username: str = ""
    elastic_password: str = ""
    elastic_index: str = "ocsf-logs"
    
    # Azure Sentinel specific
    workspace_id: str = ""
    shared_key: str = ""
    log_type: str = "VCOS_OCSF"
    
    # Generic HTTP
    headers: Dict[str, str] = field(default_factory=dict)
    auth_type: str = "bearer"  # bearer, api_key, basic, none
    
    # Delivery settings
    batch_size: int = 100
    flush_interval: float = 5.0
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 30.0
    
    # TLS/SSL
    verify_ssl: bool = True
    ca_cert: Optional[str] = None
    client_cert: Optional[str] = None
    client_key: Optional[str] = None
    
    # Field mapping
    field_mapping: Dict[str, str] = field(default_factory=dict)
    drop_fields: List[str] = field(default_factory=list)
    
    # Filtering
    min_severity: str = "informational"
    include_categories: List[str] = field(default_factory=list)
    exclude_categories: List[str] = field(default_factory=list)


class SIEMBackendBase:
    """Base class for SIEM backends."""
    
    def __init__(self, config: SIEMConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None
        self._buffer: deque = deque()
    
    async def initialize(self):
        """Initialize the backend."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout),
        )
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(f"Initialized SIEM backend: {self.config.name} ({self.config.backend.value})")
    
    async def close(self):
        """Close the backend."""
        self._running = False
        if self._flush_task:
            await self._flush_task
        await self._flush()
        if self._session:
            await self._session.close()
    
    async def send_event(self, event: OCSFEvent) -> bool:
        """Add event to buffer for async delivery."""
        # Apply field mapping and filtering
        processed_event = self._process_event(event)
        if processed_event:
            self._buffer.append(processed_event)
            if len(self._buffer) >= self.config.batch_size:
                await self._flush()
        return True
    
    def _process_event(self, event: OCSFEvent) -> Optional[Dict[str, Any]]:
        """Process event: apply field mapping, filtering, etc."""
        event_dict = event.to_dict()
        
        # Apply field mapping
        if self.config.field_mapping:
            mapped = {}
            for src_field, dst_field in self.config.field_mapping.items():
                if src_field in event_dict:
                    mapped[dst_field] = event_dict[src_field]
            # Keep unmapped fields
            for k, v in event_dict.items():
                if k not in self.config.field_mapping:
                    mapped[k] = v
            event_dict = mapped
        
        # Drop fields
        for field in self.config.drop_fields:
            event_dict.pop(field, None)
        
        # Filter by severity
        severity_order = ["unknown", "informational", "low", "medium", "high", "critical"]
        min_idx = severity_order.index(self.config.min_severity)
        event_severity = event_dict.get("severity", "informational")
        if severity_order.index(event_severity) < min_idx:
            return None
        
        # Filter categories
        if self.config.include_categories:
            if event_dict.get("category_name") not in self.config.include_categories:
                return None
        if self.config.exclude_categories:
            if event_dict.get("category_name") in self.config.exclude_categories:
                return None
        
        return event_dict
    
    async def _flush(self):
        """Flush buffer to SIEM."""
        if not self._buffer:
            return
        
        events = list(self._buffer)
        self._buffer.clear()
        
        for attempt in range(self.config.max_retries):
            try:
                await self._deliver(events)
                logger.debug(f"Delivered {len(events)} events to {self.config.name}")
                return
            except Exception as e:
                logger.warning(f"SIEM delivery attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
        
        # If all retries failed, re-queue events
        logger.error(f"Failed to deliver {len(events)} events to {self.config.name} after {self.config.max_retries} retries")
        self._buffer.extendleft(reversed(events))
    
    async def _deliver(self, events: List[Dict[str, Any]]):
        """Deliver events to SIEM backend. Override in subclasses."""
        raise NotImplementedError
    
    async def _flush_loop(self):
        """Periodic flush loop."""
        while self._running:
            await asyncio.sleep(self.config.flush_interval)
            await self._flush()


class SplunkHECBackend(SIEMBackendBase):
    """Splunk HTTP Event Collector backend."""
    
    async def _deliver(self, events: List[Dict[str, Any]]):
        headers = {
            "Authorization": f"Splunk {self.config.hec_token}",
            "Content-Type": "application/json",
        }
        
        # Splunk HEC expects events in a specific format
        payload = []
        for event in events:
            payload.append({
                "event": event,
                "index": self.config.index,
                "sourcetype": self.config.sourcetype,
                "source": "vcos",
                "host": "vcos",
            })
        
        async with self._session.post(
            f"{self.config.endpoint}/services/collector",
            headers=headers,
            json=payload,
            ssl=self.config.verify_ssl,
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"Splunk HEC error {resp.status}: {text}")


class DatadogBackend(SIEMBackendBase):
    """Datadog Logs API backend."""
    
    async def _deliver(self, events: List[Dict[str, Any]]):
        headers = {
            "Content-Type": "application/json",
            "DD-API-KEY": self.config.datadog_api_key or self.config.api_key,
        }
        
        # Datadog expects array of log objects
        payload = []
        for event in events:
            payload.append({
                "ddsource": "vcos",
                "ddtags": f"env:{settings.ENVIRONMENT},service:vcos",
                "hostname": "vcos",
                "message": json.dumps(event),
                "service": "vcos",
                "status": event.get("severity", "info"),
            })
        
        url = f"https://http-intake.logs.{self.config.datadog_site}/api/v2/logs"
        async with self._session.post(
            url,
            headers=headers,
            json=payload,
            ssl=self.config.verify_ssl,
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"Datadog error {resp.status}: {text}")


class ElasticBackend(SIEMBackendBase):
    """Elasticsearch/Elastic Cloud backend."""
    
    async def _deliver(self, events: List[Dict[str, Any]]):
        auth = aiohttp.BasicAuth(
            self.config.elastic_username,
            self.config.elastic_password,
        ) if self.config.elastic_username else None
        
        # Use bulk API for efficiency
        bulk_lines = []
        for event in events:
            # Index action
            bulk_lines.append(json.dumps({
                "index": {
                    "_index": self.config.elastic_index,
                }
            }))
            # Document
            bulk_lines.append(json.dumps(event))
        
        bulk_data = "\n".join(bulk_lines) + "\n"
        
        headers = {
            "Content-Type": "application/x-ndjson",
        }
        
        async with self._session.post(
            f"{self.config.endpoint}/_bulk",
            headers=headers,
            data=bulk_data,
            auth=auth,
            ssl=self.config.verify_ssl,
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"Elastic error {resp.status}: {text}")
            
            result = await resp.json()
            if result.get("errors"):
                raise Exception(f"Elastic bulk errors: {result}")


class GenericHTTPBackend(SIEMBackendBase):
    """Generic HTTP endpoint backend."""
    
    async def _deliver(self, events: List[Dict[str, Any]]):
        headers = {
            "Content-Type": "application/json",
        }
        
        # Apply custom headers
        headers.update(self.config.headers)
        
        # Apply authentication
        if self.config.auth_type == "bearer" and self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        elif self.config.auth_type == "api_key" and self.config.api_key:
            headers["X-API-Key"] = self.config.api_key
        elif self.config.auth_type == "basic" and self.config.elastic_username:
            auth = aiohttp.BasicAuth(
                self.config.elastic_username,
                self.config.elastic_password,
            )
        
        payload = {"events": events, "source": "vcos", "timestamp": datetime.now(timezone.utc).isoformat()}
        
        async with self._session.post(
            self.config.endpoint,
            headers=headers,
            json=payload,
            auth=auth if 'auth' in locals() else None,
            ssl=self.config.verify_ssl,
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"HTTP error {resp.status}: {text}")


class AzureSentinelBackend(SIEMBackendBase):
    """Azure Sentinel / Log Analytics backend."""
    
    async def _deliver(self, events: List[Dict[str, Any]]):
        import base64
        import hmac
        
        # Build the request body
        body = json.dumps(events)
        
        # Create signature
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        string_to_hash = f"POST\n{len(body)}\napplication/json\nx-ms-date:{date}\n/api/logs"
        hashed = hmac.new(
            base64.b64decode(self.config.shared_key),
            string_to_hash.encode(),
            hashlib.sha256
        ).digest()
        signature = base64.b64encode(hashed).decode()
        
        headers = {
            "Content-Type": "application/json",
            "Log-Type": self.config.log_type,
            "Authorization": f"SharedKey {self.config.workspace_id}:{signature}",
            "x-ms-date": date,
            "time-generated-field": "time",
        }
        
        url = f"https://{self.config.workspace_id}.ods.opinsights.azure.com/api/logs?api-version=2016-04-01"
        
        async with self._session.post(
            url,
            headers=headers,
            data=body,
            ssl=self.config.verify_ssl,
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"Azure Sentinel error {resp.status}: {text}")


class SIEMManager:
    """
    SIEM Integration Manager.
    
    Manages multiple SIEM backends, event routing, and delivery.
    """
    
    def __init__(self):
        self._backends: Dict[str, SIEMBackendBase] = {}
        self._configs: Dict[str, SIEMConfig] = {}
        self._event_handlers: List[Callable] = []
        self._initialized = False
    
    def add_backend(self, config: SIEMConfig) -> SIEMBackendBase:
        """Add a SIEM backend."""
        backend = self._create_backend(config)
        self._configs[config.name] = config
        self._backends[config.name] = backend
        logger.info(f"Added SIEM backend: {config.name} ({config.backend.value})")
        return backend
    
    def _create_backend(self, config: SIEMConfig) -> SIEMBackendBase:
        """Create backend instance based on type."""
        backends = {
            SIEMBackend.SPLUNK_HEC: SplunkHECBackend,
            SIEMBackend.DATADOG: DatadogBackend,
            SIEMBackend.ELASTIC: ElasticBackend,
            SIEMBackend.AZURE_SENTINEL: AzureSentinelBackend,
            SIEMBackend.GENERIC_HTTP: GenericHTTPBackend,
        }
        
        backend_class = backends.get(config.backend)
        if not backend_class:
            raise ValueError(f"Unsupported SIEM backend: {config.backend.value}")
        
        return backend_class(config)
    
    def remove_backend(self, name: str) -> bool:
        """Remove a SIEM backend."""
        if name in self._backends:
            del self._backends[name]
            del self._configs[name]
            return True
        return False
    
    def get_backend(self, name: str) -> Optional[SIEMBackendBase]:
        """Get backend by name."""
        return self._backends.get(name)
    
    def list_backends(self) -> List[Dict[str, Any]]:
        """List all backends."""
        return [
            {
                "name": name,
                "backend": config.backend.value,
                "enabled": config.enabled,
                "endpoint": config.endpoint,
            }
            for name, config in self._configs.items()
        ]
    
    async def initialize(self):
        """Initialize all enabled backends."""
        for name, backend in self._backends.items():
            if self._configs[name].enabled:
                await backend.initialize()
        self._initialized = True
        logger.info(f"Initialized {len(self._backends)} SIEM backends")
    
    async def close(self):
        """Close all backends."""
        for backend in self._backends.values():
            await backend.close()
        self._initialized = False
    
    async def send_event(
        self,
        event: OCSFEvent,
        backend_names: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """Send event to specified backends or all enabled backends."""
        if not self._initialized:
            await self.initialize()
        
        targets = backend_names or [
            name for name, config in self._configs.items()
            if config.enabled
        ]
        
        results = {}
        for name in targets:
            backend = self._backends.get(name)
            if backend:
                try:
                    results[name] = await backend.send_event(event)
                except Exception as e:
                    logger.error(f"Failed to send event to {name}: {e}")
                    results[name] = False
            else:
                results[name] = False
        
        return results
    
    def register_event_handler(self, handler: Callable[[OCSFEvent], Any]):
        """Register a custom event handler."""
        self._event_handlers.append(handler)
    
    # ==================== Convenience Methods for Common Events ====================
    
    async def log_authentication(
        self,
        user_id: str,
        username: str,
        organization_id: str,
        success: bool,
        ip_address: str,
        user_agent: str,
        mfa_used: bool = False,
        mfa_method: Optional[str] = None,
        error: Optional[str] = None,
        backend_names: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """Log authentication event."""
        category = OCSFCategory.LOGON if success else OCSFCategory.LOGON_FAILED
        event = OCSFEventBuilder.build(
            OCSFClass.AUTHENTICATION,
            category,
            severity=Severity.INFORMATIONAL if success else Severity.MEDIUM,
            status="success" if success else "failure",
            message=f"User {'login' if success else 'login failed'}: {username}",
            actor={
                "user_id": user_id,
                "user_name": username,
                "type": "user",
            },
            src_endpoint={
                "ip": ip_address,
                "user_agent": user_agent,
            },
            target={
                "type": "account",
                "uid": user_id,
            },
            metadata={
                "organization_id": organization_id,
                "mfa_used": mfa_used,
                "mfa_method": mfa_method,
                "error": error,
            },
        )
        return await self.send_event(event, backend_names)
    
    async def log_authorization(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        allowed: bool,
        organization_id: str,
        ip_address: str,
        policy_id: Optional[str] = None,
        backend_names: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """Log authorization decision."""
        category = OCSFCategory.PERMISSION_CHANGE if allowed else OCSFCategory.POLICY_CHANGE
        event = OCSFEventBuilder.build(
            OCSFClass.AUTHORIZATION,
            category,
            severity=Severity.INFORMATIONAL if allowed else Severity.MEDIUM,
            status="success" if allowed else "failure",
            message=f"Authorization {'granted' if allowed else 'denied'}: {action} on {resource_type}:{resource_id}",
            actor={
                "user_id": user_id,
                "type": "user",
            },
            target={
                "type": resource_type,
                "uid": resource_id,
            },
            src_endpoint={
                "ip": ip_address,
            },
            security_control={
                "policy_id": policy_id,
                "action": action,
            },
            metadata={
                "organization_id": organization_id,
            },
        )
        return await self.send_event(event, backend_names)
    
    async def log_dlp_violation(
        self,
        scan_id: str,
        user_id: str,
        organization_id: str,
        matches: List[Dict[str, Any]],
        action: str,
        source: str,
        source_id: str,
        ip_address: Optional[str] = None,
        backend_names: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """Log DLP violation."""
        event = OCSFEventBuilder.build(
            OCSFClass.DATA_SECURITY,
            OCSFCategory.DLP_VIOLATION,
            severity=Severity.HIGH,
            status="failure",
            message=f"DLP violation detected: {len(matches)} matches",
            actor={
                "user_id": user_id,
                "type": "user",
            },
            target={
                "type": "data",
                "uid": source_id,
            },
            src_endpoint={
                "ip": ip_address,
            } if ip_address else None,
            metadata={
                "organization_id": organization_id,
                "scan_id": scan_id,
                "source": source,
                "source_id": source_id,
                "action_taken": action,
                "matches": matches,
            },
        )
        return await self.send_event(event, backend_names)
    
    async def log_security_finding(
        self,
        finding_type: str,
        title: str,
        description: str,
        severity: Severity,
        user_id: Optional[str],
        organization_id: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        indicators: Optional[List[Dict[str, Any]]] = None,
        backend_names: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """Log security finding."""
        category_map = {
            "malware": OCSFCategory.MALWARE_DETECTION,
            "intrusion": OCSFCategory.INTRUSION_DETECTION,
            "anomaly": OCSFCategory.ANOMALY_DETECTION,
            "brute_force": OCSFCategory.BRUTE_FORCE,
            "privilege_escalation": OCSFCategory.PRIVILEGE_ESCALATION,
        }
        
        event = OCSFEventBuilder.build(
            OCSFClass.SECURITY_FINDING,
            category_map.get(finding_type, OCSFCategory.ANOMALY_DETECTION),
            severity=severity,
            status="open",
            message=f"{finding_type}: {title}",
            actor={
                "user_id": user_id,
                "type": "user",
            } if user_id else None,
            target={
                "type": resource_type,
                "uid": resource_id,
            } if resource_type and resource_id else None,
            src_endpoint={
                "ip": ip_address,
            } if ip_address else None,
            metadata={
                "organization_id": organization_id,
                "finding_type": finding_type,
                "description": description,
                "indicators": indicators or [],
            },
            threat={
                "type": finding_type,
                "indicators": indicators or [],
            },
        )
        return await self.send_event(event, backend_names)
    
    async def log_audit(
        self,
        event_type: str,
        user_id: str,
        organization_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        backend_names: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """Log audit event."""
        event = OCSFEventBuilder.build(
            OCSFClass.COMPLIANCE,
            OCSFCategory.AUDIT_LOG,
            severity=Severity.INFORMATIONAL,
            status=outcome,
            message=f"Audit: {event_type} - {action}",
            actor={
                "user_id": user_id,
                "type": "user",
            },
            target={
                "type": resource_type,
                "uid": resource_id,
            },
            src_endpoint={
                "ip": ip_address,
            } if ip_address else None,
            metadata={
                "organization_id": organization_id,
                "event_type": event_type,
                "action": action,
                "details": details or {},
            },
        )
        return await self.send_event(event, backend_names)


# Global SIEM manager instance
_siem_manager: Optional[SIEMManager] = None


def get_siem_manager() -> SIEMManager:
    """Get or create SIEM manager singleton."""
    global _siem_manager
    if _siem_manager is None:
        _siem_manager = SIEMManager()
    return _siem_manager


def init_siem_manager() -> SIEMManager:
    """Initialize SIEM manager."""
    global _siem_manager
    _siem_manager = SIEMManager()
    return _siem_manager