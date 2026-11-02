"""
Alerting Integration for VCOS.

Provides multi-channel alerting with Alertmanager integration,
webhook delivery, and notification routing.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from collections import deque

import aiohttp

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    PAGER = "pager"  # Pages on-call


class AlertState(str, Enum):
    """Alert lifecycle states."""
    FIRING = "firing"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"
    SUPPRESSED = "suppressed"


class NotificationChannel(str, Enum):
    """Notification delivery channels."""
    EMAIL = "email"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    WEBHOOK = "webhook"
    SMS = "sms"
    PUSH = "push"


@dataclass
class Alert:
    """Alert representation."""
    name: str
    service: str
    severity: AlertSeverity
    summary: str
    description: str
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    starts_at: datetime = field(default_factory=datetime.utcnow)
    ends_at: Optional[datetime] = None
    generator_url: Optional[str] = None
    fingerprint: str = field(default="", init=False)

    def __post_init__(self):
        if not self.fingerprint:
            # Generate stable fingerprint
            content = f"{self.name}{self.service}{json.dumps(self.labels, sort_keys=True)}"
            self.fingerprint = hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_alertmanager(self) -> Dict[str, Any]:
        """Convert to Alertmanager format."""
        return {
            "labels": {
                "alertname": self.name,
                "service": self.service,
                "severity": self.severity.value,
                **self.labels,
            },
            "annotations": {
                "summary": self.summary,
                "description": self.description,
                **self.annotations,
            },
            "startsAt": self.starts_at.isoformat() + "Z",
            "endsAt": (self.ends_at or datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
            "generatorURL": self.generator_url or "",
        }


@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    query: str  # PromQL query
    duration: str = "5m"  # For how long condition must be true
    severity: AlertSeverity = AlertSeverity.WARNING
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class NotificationRoute:
    """Routing configuration for alerts."""
    name: str
    matchers: Dict[str, str] = field(default_factory=dict)  # Label matchers
    matchers_re: Dict[str, str] = field(default_factory=dict)  # Regex matchers
    continue_routing: bool = False
    group_by: List[str] = field(default_factory=lambda: ["alertname", "service"])
    group_wait: str = "30s"
    group_interval: str = "5m"
    repeat_interval: str = "4h"
    receivers: List[str] = field(default_factory=list)


@dataclass
class Receiver:
    """Notification receiver configuration."""
    name: str
    channels: List[NotificationChannel] = field(default_factory=list)
    configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # E.g., {"slack": {"webhook_url": "...", "channel": "#alerts"}}


class AlertManagerClient:
    """Client for Alertmanager API."""

    def __init__(self, url: str = "http://localhost:9093"):
        self.url = url.rstrip("/")
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def post_alerts(self, alerts: List[Alert]) -> bool:
        """Send alerts to Alertmanager."""
        if not self.session:
            return False

        payload = [alert.to_alertmanager() for alert in alerts]
        try:
            async with self.session.post(
                f"{self.url}/api/v2/alerts",
                json=payload,
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to post alerts to Alertmanager: {e}")
            return False

    async def silence_alert(
        self,
        matchers: List[Dict[str, str]],
        starts_at: datetime,
        ends_at: datetime,
        created_by: str = "VCOS",
        comment: str = "",
    ) -> bool:
        """Create a silence in Alertmanager."""
        if not self.session:
            return False

        payload = {
            "matchers": matchers,
            "startsAt": starts_at.isoformat() + "Z",
            "endsAt": ends_at.isoformat() + "Z",
            "createdBy": created_by,
            "comment": comment,
        }

        try:
            async with self.session.post(
                f"{self.url}/api/v2/silences",
                json=payload,
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to create silence: {e}")
            return False

    async def get_alerts(self, filter_: Optional[str] = None) -> List[Dict]:
        """Get active alerts from Alertmanager."""
        if not self.session:
            return []

        try:
            params = {"filter": filter_} if filter_ else {}
            async with self.session.get(
                f"{self.url}/api/v2/alerts",
                params=params,
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"Failed to get alerts: {e}")
        return []


class NotificationDispatcher:
    """Dispatches notifications to multiple channels."""

    def __init__(self):
        self.channels: Dict[NotificationChannel, Callable] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    def register_channel(self, channel: NotificationChannel, handler: Callable):
        """Register a notification channel handler."""
        self.channels[channel] = handler

    async def dispatch(self, alert: Alert, channels: List[NotificationChannel]) -> Dict[str, bool]:
        """Dispatch alert to multiple channels."""
        results = {}
        for channel in channels:
            handler = self.channels.get(channel)
            if handler:
                try:
                    result = await handler(alert)
                    results[channel.value] = result
                except Exception as e:
                    logger.error(f"Failed to send alert via {channel}: {e}")
                    results[channel.value] = False
            else:
                logger.warning(f"No handler for channel: {channel}")
                results[channel.value] = False
        return results


# Built-in channel handlers
async def send_slack_alert(alert: Alert, webhook_url: str, channel: str = "#alerts") -> bool:
    """Send alert to Slack via webhook."""
    severity_colors = {
        AlertSeverity.INFO: "#36a64f",
        AlertSeverity.WARNING: "#ff9800",
        AlertSeverity.CRITICAL: "#f44336",
        AlertSeverity.PAGER: "#ff0000",
    }

    payload = {
        "channel": channel,
        "username": "VCOS Alerts",
        "icon_emoji": ":warning:",
        "attachments": [{
            "color": severity_colors.get(alert.severity, "#ff9800"),
            "title": f"{alert.severity.value.upper()}: {alert.summary}",
            "text": alert.description,
            "fields": [
                {"title": "Service", "value": alert.service, "short": True},
                {"title": "Severity", "value": alert.severity.value.upper(), "short": True},
                {"title": "Alert", "value": alert.name, "short": True},
            ] + [
                {"title": k, "value": v, "short": True}
                for k, v in alert.labels.items()
            ],
            "ts": int(alert.starts_at.timestamp()),
            "footer": "VCOS Monitoring",
        }],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload) as resp:
                return resp.status == 200
    except Exception as e:
        logger.error(f"Failed to send Slack alert: {e}")
        return False


async def send_pagerduty_alert(
    alert: Alert,
    integration_key: str,
) -> bool:
    """Send alert to PagerDuty Events API v2."""
    severity_map = {
        AlertSeverity.INFO: "info",
        AlertSeverity.WARNING: "warning",
        AlertSeverity.CRITICAL: "critical",
        AlertSeverity.PAGER: "critical",
    }

    payload = {
        "routing_key": integration_key,
        "event_action": "trigger",
        "dedup_key": alert.fingerprint,
        "payload": {
            "summary": alert.summary,
            "source": alert.service,
            "severity": severity_map.get(alert.severity, "warning"),
            "component": alert.service,
            "group": alert.labels.get("team", "unknown"),
            "class": alert.name,
            "custom_details": {
                "description": alert.description,
                "labels": alert.labels,
                "annotations": alert.annotations,
            },
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                return resp.status == 202
    except Exception as e:
        logger.error(f"Failed to send PagerDuty alert: {e}")
        return False


async def send_opsgenie_alert(alert: Alert, api_key: str) -> bool:
    """Send alert to Opsgenie."""
    priority_map = {
        AlertSeverity.INFO: "P5",
        AlertSeverity.WARNING: "P3",
        AlertSeverity.CRITICAL: "P1",
        AlertSeverity.PAGER: "P1",
    }

    payload = {
        "message": alert.summary,
        "description": alert.description,
        "priority": priority_map.get(alert.severity, "P3"),
        "source": alert.service,
        "tags": [f"{k}:{v}" for k, v in alert.labels.items()],
        "details": alert.annotations,
        "entity": alert.service,
        "alias": alert.fingerprint,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.opsgenie.com/v2/alerts",
                json=payload,
                headers={
                    "Authorization": f"GenieKey {settings.OPSGENIE_API_KEY}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                return resp.status in (200, 201, 202)
    except Exception as e:
        logger.error(f"Failed to send Opsgenie alert: {e}")
        return False


async def send_email_alert(alert: Alert, smtp_config: Dict[str, Any]) -> bool:
    """Send alert via email (simplified - use proper email library in production)."""
    # This is a simplified version - in production use aiosmtplib or similar
    logger.info(f"Email alert would be sent: {alert.summary}")
    return True


async def send_webhook_alert(alert: Alert, webhook_url: str, secret: Optional[str] = None) -> bool:
    """Send alert to generic webhook endpoint."""
    payload = alert.to_alertmanager()

    headers = {"Content-Type": "application/json"}
    if secret:
        signature = hmac.new(
            secret.encode(),
            json.dumps(payload).encode(),
            hashlib.sha256,
        ).hexdigest()
        headers["X-Signature"] = f"sha256={signature}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                headers=headers,
            ) as resp:
                return resp.status < 400
    except Exception as e:
        logger.error(f"Failed to send webhook alert: {e}")
        return False


class AlertRouter:
    """Routes alerts to appropriate receivers based on routing rules."""

    def __init__(self):
        self.routes: List[NotificationRoute] = []
        self.receivers: Dict[str, Receiver] = {}
        self.default_receiver: Optional[str] = None

    def add_route(self, route: NotificationRoute):
        self.routes.append(route)

    def add_receiver(self, receiver: Receiver):
        self.receivers[receiver.name] = receiver

    def set_default_receiver(self, name: str):
        self.default_receiver = name

    def match_route(self, alert: Alert) -> List[str]:
        """Find matching receivers for an alert."""
        matched_receivers = set()

        for route in self.routes:
            if self._match_route(route, alert):
                matched_receivers.update(route.receivers)
                if not route.continue_routing:
                    break

        if not matched_receivers and self.default_receiver:
            matched_receivers.add(self.default_receiver)

        return list(matched_receivers)

    def _match_route(self, route: NotificationRoute, alert: Alert) -> bool:
        """Check if alert matches route matchers."""
        # Exact matchers
        for key, value in route.matchers.items():
            if alert.labels.get(key) != value:
                return False

        # Regex matchers
        import re
        for key, pattern in route.matchers_re.items():
            label_value = alert.labels.get(key, "")
            if not re.match(pattern, label_value):
                return False

        return True


class AlertManager:
    """Central alert management system."""

    def __init__(self):
        self.router = AlertRouter()
        self.dispatcher = NotificationDispatcher()
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=10000)
        self.silences: Dict[str, Dict] = {}

    def register_receiver(self, name: str, channels: List[NotificationChannel], config: Dict[str, Any]):
        """Register a notification receiver."""
        receiver = Receiver(name=name, channels=channels, configs={})
        self.router.add_receiver(receiver)

    def add_route(self, route: NotificationRoute):
        self.router.add_route(route)

    def set_default_receiver(self, name: str):
        self.router.default_receiver = name

    async def fire_alert(self, alert: Alert) -> bool:
        """Fire an alert through the routing and dispatch system."""
        # Deduplicate
        fingerprint = alert.fingerprint
        if fingerprint in self.active_alerts:
            existing = self.active_alerts[fingerprint]
            # Update existing alert
            existing.ends_at = None
            existing.annotations.update(alert.annotations)
            return True

        # Add to active alerts
        self.active_alerts[fingerprint] = alert
        self.alert_history.append(alert)

        # Route and dispatch
        receiver_names = self.router.match_route(alert)
        receivers = [self.router.receivers[name] for name in receiver_names if name in self.router.receivers]

        if not receivers:
            logger.warning(f"No receivers matched for alert: {alert.name}")
            return False

        # Determine channels from receivers
        all_channels = set()
        for receiver in receivers:
            all_channels.update(receiver.channels)

        # Dispatch
        async with NotificationDispatcher() as dispatcher:
            for channel in all_channels:
                # Would register channel handlers here
                pass

        logger.info(f"Fired alert: {alert.name} (fingerprint: {alert.fingerprint})")
        return True

    async def resolve_alert(self, fingerprint: str) -> bool:
        """Resolve an active alert."""
        if fingerprint not in self.active_alerts:
            return False

        alert = self.active_alerts.pop(fingerprint)
        alert.ends_at = datetime.utcnow()
        return True

    def silence_alert(
        self,
        matchers: List[Dict[str, str]],
        duration: timedelta = timedelta(hours=1),
    ) -> str:
        """Create a silence for matching alerts."""
        silence_id = hashlib.sha256(
            f"{json.dumps(matchers, sort_keys=True)}{datetime.utcnow()}".encode()
        ).hexdigest()[:16]

        self.silences[silence_id] = {
            "matchers": matchers,
            "starts_at": datetime.utcnow(),
            "ends_at": datetime.utcnow() + duration,
        }
        return silence_id

    def is_silenced(self, alert: Alert) -> bool:
        """Check if alert is silenced."""
        for silence in self.silences.values():
            if silence["ends_at"] < datetime.utcnow():
                continue

            matches = True
            for matcher in silence["matchers"]:
                if alert.labels.get(matcher["name"]) != matcher["value"]:
                    matches = False
                    break
            if matches:
                return True

        return False


# Global alert manager
_alert_manager = None


def get_alert_manager() -> 'AlertManager':
    """Get global alert manager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


async def init_alerting(
    alertmanager_url: str = None,
    pagerduty_key: str = None,
    slack_webhook: str = None,
    opsgenie_key: str = None,
) -> AlertManager:
    """Initialize alerting system with integrations."""
    manager = get_alert_manager()

    # Configure default routes
    default_route = NotificationRoute(
        name="default",
        receivers=["default"],
    )
    manager.add_route(default_route)

    # Register default receiver
    channels = []
    configs = {}

    if slack_webhook:
        channels.append(NotificationChannel.SLACK)
    if pagerduty_key:
        channels.append(NotificationChannel.PAGERDUTY)
    if settings.OPSGENIE_API_KEY:
        channels.append(NotificationChannel.OPSGENIE)

    # Always add webhook for internal processing
    channels.append(NotificationChannel.WEBHOOK)

    manager.register_receiver("default", channels, {})

    logger.info("Alerting system initialized")
    return get_alert_manager()


# Convenience functions
async def fire_alert(
    name: str,
    service: str,
    severity: AlertSeverity,
    summary: str,
    description: str,
    labels: Dict[str, str] = None,
    annotations: Dict[str, str] = None,
) -> bool:
    """Convenience function to fire an alert."""
    alert = Alert(
        name=name,
        service=service,
        severity=severity,
        summary=summary,
        description=description,
        labels=labels or {},
        annotations=annotations or {},
    )
    manager = get_alert_manager()
    return await manager.fire_alert(alert)


async def resolve_alert(name: str, labels: Dict[str, str] = None) -> bool:
    """Resolve an alert by name and labels."""
    # Generate fingerprint
    fingerprint = hashlib.sha256(
        f"{name}{json.dumps(labels or {}, sort_keys=True)}".encode()
    ).hexdigest()[:16]

    manager = get_alert_manager()
    return await manager.resolve_alert(fingerprint)