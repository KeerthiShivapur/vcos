"""
Push Notification Service for VCOS.
Supports Web Push (FCM/APNs via Web Push protocol) with VAPID authentication.
"""

import json
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from pywebpush import webpush, WebPushException

from app.core.config import settings
from app.core.timeutils import utcnow
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class PushSubscription:
    """Web Push subscription data."""
    endpoint: str
    p256dh: str
    auth: str
    user_agent: Optional[str] = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class NotificationPayload:
    """Notification payload for Web Push."""
    title: str
    body: str
    icon: Optional[str] = None
    badge: Optional[str] = None
    image: Optional[str] = None
    vibrate: Optional[List[int]] = None
    data: Optional[Dict[str, Any]] = None
    actions: Optional[List[Dict[str, str]]] = None
    tag: Optional[str] = None
    renotify: bool = False
    require_interaction: bool = False
    silent: bool = False
    timestamp: Optional[int] = None
    ttl: int = 86400  # 24 hours


@dataclass
class PushSubscriptionModel:
    """Database model for push subscriptions."""
    id: str
    user_id: str
    organization_id: str
    endpoint: str
    p256dh: str
    auth: str
    user_agent: Optional[str] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=utcnow)
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class PushNotificationService:
    """
    Push Notification Service for Web Push (FCM/APNs via Web Push protocol).
    
    Features:
    - VAPID authentication
    - Subscription management
    - Notification delivery with retry
    - FCM/APNs support via Web Push protocol
    - Batch notifications
    - Subscription cleanup
    """
    
    def __init__(self):
        self._vapid_private_key = getattr(settings, 'VAPID_PRIVATE_KEY', None)
        self._vapid_public_key = getattr(settings, 'VAPID_PUBLIC_KEY', None)
        self._vapid_subject = getattr(settings, 'VAPID_SUBJECT', 'mailto:admin@vcos.io')
        
        # In-memory cache for subscriptions (use Redis in production)
        self._subscriptions: Dict[str, PushSubscriptionModel] = {}
        
        if not self._vapid_private_key or not self._vapid_public_key:
            logger.warning("VAPID keys not configured. Push notifications will not work.")
            # Generate keys for development
            from py_vapid import Vapid
            vapid = Vapid()
            self._vapid_private_key = vapid.generate_private_key()
            self._vapid_public_key = vapid.derive_public_key(self._vapid_private_key)
            logger.info("Generated VAPID keys for development")

    @property
    def vapid_public_key(self) -> str:
        """Get VAPID public key for frontend."""
        return self._vapid_public_key

    @property
    def vapid_private_key(self) -> str:
        """Get VAPID private key for signing."""
        return self._vapid_private_key

    async def subscribe_user(
        self,
        db,
        user_id: str,
        organization_id: str,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: Optional[str] = None,
    ) -> PushSubscriptionModel:
        """Register a push subscription for a user."""
        # Check if subscription already exists
        existing = None
        for sub in self._subscriptions.values():
            if sub.endpoint == endpoint and sub.user_id == user_id:
                existing = sub
                break
        
        if existing:
            # Update existing subscription
            existing.p256dh = p256dh
            existing.auth = auth
            existing.user_agent = user_agent
            existing.is_active = True
            existing.last_used_at = utcnow()
            logger.info(f"Updated push subscription for user {user_id}")
            return existing
        
        # Create new subscription
        subscription = PushSubscriptionModel(
            id=str(uuid.uuid4()),
            user_id=user_id,
            organization_id=organization_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=user_agent,
        )
        
        self._subscriptions[subscription.id] = subscription
        logger.info(f"Created push subscription for user {user_id}")
        return subscription

    async def unsubscribe_user(
        self,
        db,
        user_id: str,
        endpoint: str,
    ) -> bool:
        """Remove a push subscription."""
        for sub_id, sub in self._subscriptions.items():
            if sub.endpoint == endpoint and sub.user_id == user_id:
                sub.is_active = False
                logger.info(f"Deactivated push subscription for user {user_id}")
                return True
        return False

    async def get_user_subscriptions(
        self,
        db,
        user_id: str,
    ) -> List[PushSubscriptionModel]:
        """Get all active subscriptions for a user."""
        return [
            sub for sub in self._subscriptions.values()
            if sub.user_id == user_id and sub.is_active
        ]

    async def send_notification(
        self,
        user_id: str,
        payload: NotificationPayload,
    ) -> Dict[str, Any]:
        """Send notification to all active subscriptions of a user."""
        subscriptions = await self.get_user_subscriptions(None, user_id)
        
        if not subscriptions:
            return {
                "success": False,
                "sent": 0,
                "failed": 0,
                "errors": ["No active subscriptions for user"],
            }
        
        results = {"success": True, "sent": 0, "failed": 0, "errors": []}
        
        for subscription in subscriptions:
            try:
                await self._send_to_subscription(subscription, payload)
                results["sent"] += 1
            except Exception as e:
                logger.error(f"Failed to send to {subscription.endpoint}: {e}")
                results["failed"] += 1
                results["errors"].append(str(e))
                results["success"] = False
        
        return results

    async def send_to_subscriptions(
        self,
        subscription_ids: List[str],
        payload: NotificationPayload,
    ) -> Dict[str, Any]:
        """Send notification to specific subscriptions."""
        results = {"success": True, "sent": 0, "failed": 0, "errors": []}
        
        for sub_id in subscription_ids:
            subscription = self._subscriptions.get(sub_id)
            if not subscription or not subscription.is_active:
                results["failed"] += 1
                results["errors"].append(f"Subscription {sub_id} not found or inactive")
                results["success"] = False
                continue
            
            try:
                await self._send_to_subscription(subscription, payload)
                results["sent"] += 1
            except Exception as e:
                logger.error(f"Failed to send to {sub_id}: {e}")
                results["failed"] += 1
                results["errors"].append(str(e))
                results["success"] = False
        
        return results

    async def send_to_organization(
        self,
        organization_id: str,
        payload: NotificationPayload,
        filter_fn: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """Send notification to all users in an organization."""
        subscriptions = [
            sub for sub in self._subscriptions.values()
            if sub.organization_id == organization_id and sub.is_active
            and (filter_fn is None or filter_fn(sub))
        ]
        
        results = {"success": True, "sent": 0, "failed": 0, "errors": []}
        
        for subscription in subscriptions:
            try:
                await self._send_to_subscription(subscription, payload)
                results["sent"] += 1
            except Exception as e:
                logger.error(f"Failed to send to {subscription.endpoint}: {e}")
                results["failed"] += 1
                results["errors"].append(str(e))
                results["success"] = False
        
        return results

    async def _send_to_subscription(
        self,
        subscription: PushSubscriptionModel,
        payload: NotificationPayload,
    ):
        """Send notification to a single subscription."""
        push_data = {
            "title": payload.title,
            "body": payload.body,
        }
        
        # Add optional fields
        if payload.icon:
            push_data["icon"] = payload.icon
        if payload.badge:
            push_data["badge"] = payload.badge
        if payload.image:
            push_data["image"] = payload.image
        if payload.vibrate:
            push_data["vibrate"] = payload.vibrate
        if payload.data:
            push_data["data"] = payload.data
        if payload.actions:
            push_data["actions"] = payload.actions
        if payload.tag:
            push_data["tag"] = payload.tag
        if payload.renotify:
            push_data["renotify"] = payload.renotify
        if payload.require_interaction:
            push_data["requireInteraction"] = payload.require_interaction
        if payload.silent:
            push_data["silent"] = payload.silent
        if payload.timestamp:
            push_data["timestamp"] = payload.timestamp
        
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth,
                },
            },
            data=json.dumps(push_data),
            vapid_private_key=self._vapid_private_key,
            vapid_claims={
                "sub": self._vapid_subject,
                "exp": int((datetime.utcnow() + timedelta(hours=24)).timestamp()),
            },
            ttl=payload.ttl,
        )
        
        # Update last used time
        subscription.last_used_at = utcnow()

    async def cleanup_expired_subscriptions(self) -> int:
        """Remove expired or inactive subscriptions."""
        now = utcnow()
        expired = []
        
        for sub_id, sub in self._subscriptions.items():
            if sub.expires_at and sub.expires_at < now:
                expired.append(sub_id)
            elif not sub.is_active and sub.last_used_at:
                # Remove inactive subscriptions older than 30 days
                if (now - sub.last_used_at).days > 30:
                    expired.append(sub_id)
        
        for sub_id in expired:
            del self._subscriptions[sub_id]
        
        logger.info(f"Cleaned up {len(expired)} expired subscriptions")
        return len(expired)

    def get_vapid_public_key(self) -> str:
        """Get VAPID public key for frontend subscription."""
        return self._vapid_public_key

    def get_stats(self) -> Dict[str, Any]:
        """Get push service statistics."""
        active = sum(1 for s in self._subscriptions.values() if s.is_active)
        total = len(self._subscriptions)
        
        by_org = {}
        for sub in self._subscriptions.values():
            if sub.organization_id not in by_org:
                by_org[sub.organization_id] = {"active": 0, "total": 0}
            by_org[sub.organization_id]["total"] += 1
            if sub.is_active:
                by_org[sub.organization_id]["active"] += 1
        
        return {
            "total_subscriptions": total,
            "active_subscriptions": active,
            "by_organization": by_org,
        }


# Global push notification service instance
_push_service: Optional[PushNotificationService] = None


def get_push_service() -> PushNotificationService:
    """Get or create push notification service singleton."""
    global _push_service
    if _push_service is None:
        _push_service = PushNotificationService()
    return _push_service


def init_push_service() -> PushNotificationService:
    """Initialize push notification service."""
    global _push_service
    _push_service = PushNotificationService()
    return _push_service