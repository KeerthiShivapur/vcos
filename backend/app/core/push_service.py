"""
Push Notification Service for VCOS.

Supports:
- Web Push Protocol (VAPID) for browser push notifications
- Firebase Cloud Messaging (FCM) for Android
- Apple Push Notification service (APNs) for iOS
- Offline message queue with persistence
- Subscription management
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Callable
from urllib.parse import urlparse

import aiohttp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import webpush, WebPushException

from app.core.config import settings

logger = logging.getLogger(__name__)


class PushProvider(str, Enum):
    """Push notification providers."""
    WEBPUSH = "webpush"      # Web Push Protocol (VAPID)
    FCM = "fcm"              # Firebase Cloud Messaging
    APNS = "apns"            # Apple Push Notification Service


class PushPriority(str, Enum):
    """Push notification priority."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class PushSubscription:
    """Push subscription data."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    organization_id: str = ""
    provider: PushProvider = PushProvider.WEBPUSH
    endpoint: str = ""
    keys: Dict[str, str] = field(default_factory=dict)  # p256dh, auth for WebPush; token for FCM/APNS
    user_agent: str = ""
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PushMessage:
    """Push notification message."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    body: str = ""
    icon: Optional[str] = None
    badge: Optional[str] = None
    image: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    actions: List[Dict[str, str]] = field(default_factory=list)
    require_interaction: bool = False
    silent: bool = False
    priority: PushPriority = PushPriority.NORMAL
    ttl: int = 86400  # 24 hours
    topic: Optional[str] = None
    collapse_key: Optional[str] = None


@dataclass
class PushResult:
    """Push notification delivery result."""
    success: bool
    message_id: str
    provider: PushProvider
    endpoint: str
    status_code: Optional[int] = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class VAPIDKeyManager:
    """Manages VAPID keys for Web Push."""

    def __init__(self):
        self._private_key: Optional[ec.EllipticCurvePrivateKey] = None
        self._public_key: Optional[ec.EllipticCurvePublicKey] = None
        self._subject: str = "mailto:admin@vcos.io"

    def generate_keys(self) -> tuple[str, str]:
        """Generate new VAPID key pair."""
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        self._private_key = private_key
        self._public_key = public_key

        return private_pem, public_pem

    def load_keys(self, private_pem: str, public_pem: str):
        """Load existing VAPID keys."""
        self._private_key = serialization.load_pem_private_key(
            private_pem.encode(),
            password=None,
        )
        self._public_key = serialization.load_pem_public_key(
            public_pem.encode(),
        )

    def get_public_key_base64(self) -> str:
        """Get public key in base64url format for client."""
        if not self._public_key:
            raise ValueError("VAPID keys not initialized")
        public_numbers = self._public_key.public_numbers()
        x = public_numbers.x.to_bytes(32, byteorder="big")
        y = public_numbers.y.to_bytes(32, byteorder="big")
        import base64
        return base64.urlsafe_b64encode(x + y).decode().rstrip("=")

    def get_private_key_pem(self) -> str:
        """Get private key in PEM format."""
        if not self._private_key:
            raise ValueError("VAPID keys not initialized")
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()


class WebPushProvider:
    """Web Push Protocol implementation using VAPID."""

    def __init__(self, vapid_key_manager: VAPIDKeyManager, subject: str = "mailto:admin@vcos.io"):
        self.vapid_key_manager = vapid_key_manager
        self.subject = subject

    async def send(
        self,
        subscription: PushSubscription,
        message: PushMessage,
    ) -> PushResult:
        """Send push notification via Web Push Protocol."""
        try:
            # Prepare payload
            payload = {
                "title": message.title,
                "body": message.body,
                "icon": message.icon or "/icons/icon-192.png",
                "badge": message.badge or "/icons/badge-72.png",
                "image": message.image,
                "data": message.data,
                "actions": message.actions,
                "requireInteraction": message.require_interaction,
                "silent": message.silent,
                "timestamp": int(time.time() * 1000),
            }

            # Send via pywebpush
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": subscription.keys,
                },
                data=json.dumps(payload),
                vapid_private_key=self.vapid_key_manager.get_private_key_pem(),
                vapid_claims={
                    "sub": self.subject,
                    "exp": int(time.time()) + message.ttl,
                },
                ttl=message.ttl,
            )

            return PushResult(
                success=True,
                message_id=message.id,
                provider=PushProvider.WEBPUSH,
                endpoint=subscription.endpoint,
                status_code=201,
            )

        except WebPushException as e:
            logger.error(f"WebPush failed: {e}")
            return PushResult(
                success=False,
                message_id=message.id,
                provider=PushProvider.WEBPUSH,
                endpoint=subscription.endpoint,
                status_code=e.response.status_code if e.response else None,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"WebPush error: {e}")
            return PushResult(
                success=False,
                message_id=message.id,
                provider=PushProvider.WEBPUSH,
                endpoint=subscription.endpoint,
                error=str(e),
            )


class FCMProvider:
    """Firebase Cloud Messaging provider."""

    def __init__(self, server_key: str, project_id: str):
        self.server_key = server_key
        self.project_id = project_id
        self.base_url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

    async def send(
        self,
        subscription: PushSubscription,
        message: PushMessage,
    ) -> PushResult:
        """Send push notification via FCM."""
        try:
            fcm_message = {
                "message": {
                    "token": subscription.keys.get("token", ""),
                    "notification": {
                        "title": message.title,
                        "body": message.body,
                        "icon": message.icon,
                        "image": message.image,
                    },
                    "data": {k: str(v) for k, v in message.data.items()},
                    "android": {
                        "priority": message.priority.value,
                        "ttl": f"{message.ttl}s",
                        "collapse_key": message.collapse_key,
                    },
                    "apns": {
                        "headers": {
                            "apns-priority": "10" if message.priority == PushPriority.HIGH else "5",
                            "apns-expiration": str(int(time.time()) + message.ttl),
                            "apns-collapse-id": message.collapse_key or "",
                        },
                        "payload": {
                            "aps": {
                                "alert": {
                                    "title": message.title,
                                    "body": message.body,
                                },
                                "sound": "default" if not message.silent else None,
                                "content-available": 1 if message.silent else 0,
                                "mutable-content": 1,
                            },
                        },
                    },
                    "webpush": {
                        "headers": {
                            "Urgency": message.priority.value,
                            "TTL": str(message.ttl),
                        },
                        "notification": {
                            "title": message.title,
                            "body": message.body,
                            "icon": message.icon,
                            "badge": message.badge,
                            "image": message.image,
                            "data": message.data,
                            "actions": message.actions,
                            "requireInteraction": message.require_interaction,
                            "silent": message.silent,
                        },
                    },
                },
            }

            headers = {
                "Authorization": f"Bearer {await self._get_access_token()}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, headers=headers, json=fcm_message) as resp:
                    response_data = await resp.json()
                    if resp.status == 200:
                        return PushResult(
                            success=True,
                            message_id=message.id,
                            provider=PushProvider.FCM,
                            endpoint=subscription.endpoint,
                            status_code=200,
                        )
                    else:
                        error = response_data.get("error", {}).get("message", "Unknown error")
                        return PushResult(
                            success=False,
                            message_id=message.id,
                            provider=PushProvider.FCM,
                            endpoint=subscription.endpoint,
                            status_code=resp.status,
                            error=error,
                        )

        except Exception as e:
            logger.error(f"FCM error: {e}")
            return PushResult(
                success=False,
                message_id=message.id,
                provider=PushProvider.FCM,
                endpoint=subscription.endpoint,
                error=str(e),
            )

    async def _get_access_token(self) -> str:
        """Get OAuth2 access token for FCM."""
        # In production, use Google Auth library to get service account token
        # This is a simplified version
        return self.server_key


class APNsProvider:
    """Apple Push Notification Service provider."""

    def __init__(
        self,
        team_id: str,
        key_id: str,
        bundle_id: str,
        private_key_path: str,
        use_sandbox: bool = True,
    ):
        self.team_id = team_id
        self.key_id = key_id
        self.bundle_id = bundle_id
        self.private_key_path = private_key_path
        self.use_sandbox = use_sandbox
        self.base_url = "https://api.sandbox.push.apple.com" if use_sandbox else "https://api.push.apple.com"

    async def send(
        self,
        subscription: PushSubscription,
        message: PushMessage,
    ) -> PushResult:
        """Send push notification via APNs."""
        try:
            import jwt
            import jwt.algorithms

            # Generate JWT token
            token = self._generate_token()

            # Prepare APNs payload
            aps = {
                "alert": {
                    "title": message.title,
                    "body": message.body,
                },
                "sound": "default" if not message.silent else None,
                "content-available": 1 if message.silent else 0,
                "mutable-content": 1,
                "badge": message.data.get("badge", 1),
            }

            payload = {
                "aps": aps,
                **message.data,
            }

            headers = {
                "authorization": f"bearer {token}",
                "apns-topic": self.bundle_id,
                "apns-priority": "10" if message.priority in (PushPriority.HIGH, PushPriority.URGENT) else "5",
                "apns-expiration": str(int(time.time()) + message.ttl),
                "apns-collapse-id": message.collapse_key or "",
            }

            device_token = subscription.keys.get("token", "")
            url = f"{self.base_url}/3/device/{device_token}"

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    response_data = await resp.text()
                    if resp.status == 200:
                        return PushResult(
                            success=True,
                            message_id=message.id,
                            provider=PushProvider.APNS,
                            endpoint=subscription.endpoint,
                            status_code=200,
                        )
                    else:
                        return PushResult(
                            success=False,
                            message_id=message.id,
                            provider=PushProvider.APNS,
                            endpoint=subscription.endpoint,
                            status_code=resp.status,
                            error=response_data,
                        )

        except Exception as e:
            logger.error(f"APNs error: {e}")
            return PushResult(
                success=False,
                message_id=message.id,
                provider=PushProvider.APNS,
                endpoint=subscription.endpoint,
                error=str(e),
            )

    def _generate_token(self) -> str:
        """Generate JWT token for APNs authentication."""
        import jwt
        from jwt.algorithms import ECAlgorithm

        # Load private key
        with open(self.private_key_path, "r") as f:
            private_key = f.read()

        # Generate token
        payload = {
            "iss": self.team_id,
            "iat": int(time.time()),
        }

        headers = {
            "alg": "ES256",
            "kid": self.key_id,
        }

        return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


class PushService:
    """
    Unified Push Notification Service.

    Features:
    - Multi-provider support (WebPush, FCM, APNs)
    - Subscription management
    - Offline message queue
    - Delivery tracking and retry
    - Batch sending
    """

    def __init__(
        self,
        vapid_subject: str = "mailto:admin@vcos.io",
        fcm_server_key: Optional[str] = None,
        fcm_project_id: Optional[str] = None,
        apns_team_id: Optional[str] = None,
        apns_key_id: Optional[str] = None,
        apns_bundle_id: Optional[str] = None,
        apns_private_key_path: Optional[str] = None,
        apns_use_sandbox: bool = True,
        redis_url: Optional[str] = None,
    ):
        # VAPID for WebPush
        self.vapid_key_manager = VAPIDKeyManager()
        self.vapid_subject = vapid_subject

        # Initialize or load VAPID keys
        if hasattr(settings, "VAPID_PRIVATE_KEY") and settings.VAPID_PRIVATE_KEY:
            self.vapid_key_manager.load_keys(
                settings.VAPID_PRIVATE_KEY,
                settings.VAPID_PUBLIC_KEY,
            )
        else:
            self.vapid_key_manager.generate_keys()

        # Providers
        self.webpush_provider = WebPushProvider(self.vapid_key_manager, vapid_subject)
        self.fcm_provider = FCMProvider(fcm_server_key, fcm_project_id) if fcm_server_key and fcm_project_id else None
        self.apns_provider = APNsProvider(
            apns_team_id, apns_key_id, apns_bundle_id, apns_private_key_path, apns_use_sandbox
        ) if all([apns_team_id, apns_key_id, apns_bundle_id, apns_private_key_path]) else None

        # Redis for persistence
        self.redis_url = redis_url
        self._redis = None
        self._running = False
        self._use_redis = redis_url is not None

        # In-memory fallback
        self._subscriptions: Dict[str, PushSubscription] = {}
        self._user_subscriptions: Dict[str, Set[str]] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._delivery_results: Dict[str, List[PushResult]] = {}

    async def initialize(self):
        """Initialize Redis connection and start background tasks."""
        if not self._use_redis:
            logger.info("Push Service initialized without Redis (in-memory only)")
            self._running = True
            asyncio.create_task(self._process_queue())
            asyncio.create_task(self._cleanup_expired_subscriptions())
            return
            
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("Push Service initialized with Redis backend")
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory fallback: {e}")

        self._running = True
        asyncio.create_task(self._process_queue())
        asyncio.create_task(self._cleanup_expired_subscriptions())

    async def close(self):
        """Close connections and stop background tasks."""
        self._running = False
        if self._redis:
            await self._redis.close()
        logger.info("Push Service closed")

    # ==================== Subscription Management ====================

    async def subscribe(
        self,
        user_id: str,
        organization_id: str,
        provider: PushProvider,
        endpoint: str,
        keys: Dict[str, str],
        user_agent: str = "",
        metadata: Dict[str, Any] = None,
    ) -> PushSubscription:
        """Register a new push subscription."""
        subscription = PushSubscription(
            user_id=user_id,
            organization_id=organization_id,
            provider=provider,
            endpoint=endpoint,
            keys=keys,
            user_agent=user_agent,
            metadata=metadata or {},
        )

        if self._redis:
            await self._save_subscription_redis(subscription)
        else:
            self._subscriptions[subscription.id] = subscription
            if user_id not in self._user_subscriptions:
                self._user_subscriptions[user_id] = set()
            self._user_subscriptions[user_id].add(subscription.id)

        logger.info(f"New {provider.value} subscription for user {user_id}: {subscription.id}")
        return subscription

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a push subscription."""
        if self._redis:
            pass  # Implement Redis deletion
        else:
            if subscription_id in self._subscriptions:
                sub = self._subscriptions.pop(subscription_id)
                if sub.user_id in self._user_subscriptions:
                    self._user_subscriptions[sub.user_id].discard(subscription_id)
                return True
        return False

    async def get_user_subscriptions(
        self,
        user_id: str,
        active_only: bool = True,
    ) -> List[PushSubscription]:
        """Get all subscriptions for a user."""
        if self._redis:
            return []
        else:
            sub_ids = self._user_subscriptions.get(user_id, set())
            subscriptions = [self._subscriptions[sid] for sid in sub_ids if sid in self._subscriptions]
            if active_only:
                subscriptions = [s for s in subscriptions if s.is_active]
            return subscriptions

    async def update_subscription_activity(self, subscription_id: str):
        """Update last_used timestamp."""
        if self._redis:
            pass
        else:
            if subscription_id in self._subscriptions:
                self._subscriptions[subscription_id].last_used = time.time()

    # ==================== Sending Notifications ====================

    async def send_to_user(
        self,
        user_id: str,
        message: PushMessage,
        providers: Optional[List[PushProvider]] = None,
    ) -> List[PushResult]:
        """Send push notification to all user's subscriptions."""
        subscriptions = await self.get_user_subscriptions(user_id)
        if not subscriptions:
            logger.warning(f"No active subscriptions for user {user_id}")
            return []

        # Filter by provider if specified
        if providers:
            subscriptions = [s for s in subscriptions if s.provider in providers]

        # Queue for async processing
        results = []
        for subscription in subscriptions:
            await self._message_queue.put((subscription, message))
            results.append(PushResult(
                success=False,  # Will be updated when processed
                message_id=message.id,
                provider=subscription.provider,
                endpoint=subscription.endpoint,
                error="queued",
            ))

        return results

    async def send_to_organization(
        self,
        organization_id: str,
        message: PushMessage,
        providers: Optional[List[PushProvider]] = None,
    ) -> List[PushResult]:
        """Send push notification to all users in organization."""
        # In production, query database for organization users
        # For now, return empty
        return []

    async def broadcast(
        self,
        message: PushMessage,
        filter_func: Optional[Callable[[PushSubscription], bool]] = None,
    ) -> List[PushResult]:
        """Broadcast to all subscriptions matching filter."""
        if self._redis:
            return []

        results = []
        for subscription in self._subscriptions.values():
            if subscription.is_active and (filter_func is None or filter_func(subscription)):
                await self._message_queue.put((subscription, message))
                results.append(PushResult(
                    success=False,
                    message_id=message.id,
                    provider=subscription.provider,
                    endpoint=subscription.endpoint,
                    error="queued",
                ))
        return results

    # ==================== Background Processing ====================

    async def _process_queue(self):
        """Process message queue."""
        while self._running:
            try:
                subscription, message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0,
                )

                result = await self._send_single(subscription, message)

                # Store result
                if message.id not in self._delivery_results:
                    self._delivery_results[message.id] = []
                self._delivery_results[message.id].append(result)

                # Update subscription activity
                await self.update_subscription_activity(subscription.id)

                # Handle failures (expired subscriptions, etc.)
                if not result.success and result.status_code in (404, 410):
                    await self.unsubscribe(subscription.id)
                    logger.info(f"Removed expired subscription: {subscription.id}")

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
                await asyncio.sleep(1)

    async def _send_single(
        self,
        subscription: PushSubscription,
        message: PushMessage,
    ) -> PushResult:
        """Send to single subscription based on provider."""
        if subscription.provider == PushProvider.WEBPUSH:
            return await self.webpush_provider.send(subscription, message)
        elif subscription.provider == PushProvider.FCM and self.fcm_provider:
            return await self.fcm_provider.send(subscription, message)
        elif subscription.provider == PushProvider.APNS and self.apns_provider:
            return await self.apns_provider.send(subscription, message)
        else:
            return PushResult(
                success=False,
                message_id=message.id,
                provider=subscription.provider,
                endpoint=subscription.endpoint,
                error=f"Provider not configured: {subscription.provider}",
            )

    async def _cleanup_expired_subscriptions(self):
        """Periodically clean up expired/inactive subscriptions."""
        while self._running:
            await asyncio.sleep(3600)  # Every hour
            try:
                cutoff = time.time() - (30 * 24 * 3600)  # 30 days
                if not self._redis:
                    expired = [
                        sid for sid, sub in self._subscriptions.items()
                        if sub.last_used < cutoff or not sub.is_active
                    ]
                    for sid in expired:
                        await self.unsubscribe(sid)
                    if expired:
                        logger.info(f"Cleaned up {len(expired)} expired subscriptions")
            except Exception as e:
                logger.error(f"Subscription cleanup error: {e}")

    # ==================== VAPID Public Key ====================

    def get_vapid_public_key(self) -> str:
        """Get VAPID public key for client subscription."""
        return self.vapid_key_manager.get_public_key_base64()

    # ==================== Delivery Tracking ====================

    async def get_delivery_results(self, message_id: str) -> List[PushResult]:
        """Get delivery results for a message."""
        return self._delivery_results.get(message_id, [])

    async def get_stats(self, organization_id: str) -> Dict[str, Any]:
        """Get push service statistics."""
        total_subs = len(self._subscriptions)
        active_subs = sum(1 for s in self._subscriptions.values() if s.is_active)
        by_provider = {}
        for sub in self._subscriptions.values():
            if sub.is_active:
                by_provider[sub.provider.value] = by_provider.get(sub.provider.value, 0) + 1

        return {
            "total_subscriptions": total_subs,
            "active_subscriptions": active_subs,
            "by_provider": by_provider,
            "queued_messages": self._message_queue.qsize(),
        }


# Global push service instance
_push_service: Optional[PushService] = None


def get_push_service() -> PushService:
    """Get or create push service singleton."""
    global _push_service
    if _push_service is None:
        _push_service = PushService()
    return _push_service


def init_push_service(
    vapid_subject: str = "mailto:admin@vcos.io",
    fcm_server_key: Optional[str] = None,
    fcm_project_id: Optional[str] = None,
    apns_team_id: Optional[str] = None,
    apns_key_id: Optional[str] = None,
    apns_bundle_id: Optional[str] = None,
    apns_private_key_path: Optional[str] = None,
    apns_use_sandbox: bool = True,
    redis_url: str = "redis://localhost:6379/0",
) -> PushService:
    """Initialize push service."""
    global _push_service
    _push_service = PushService(
        vapid_subject=vapid_subject,
        fcm_server_key=fcm_server_key,
        fcm_project_id=fcm_project_id,
        apns_team_id=apns_team_id,
        apns_key_id=apns_key_id,
        apns_bundle_id=apns_bundle_id,
        apns_private_key_path=apns_private_key_path,
        apns_use_sandbox=apns_use_sandbox,
        redis_url=redis_url,
    )
    return _push_service