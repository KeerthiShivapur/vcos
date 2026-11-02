"""
OCSF (Open Cybersecurity Schema Framework) SIEM Export + DLP (Data Loss Prevention).

Provides:
- OCSF 1.3.0 compliant event schema mapping
- Real-time SIEM integration (Splunk, Datadog, Elastic, Sentinel, Sumo Logic)
- Data Loss Prevention with content inspection
- Regex/ML-based classifiers for sensitive data detection
- Policy-based alerting and blocking
- Structured logging for compliance
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

import aiohttp

from sqlalchemy import Column, String, Text, JSON, DateTime, Index, ForeignKey, Boolean, Integer, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid
from app.core.compliance import DataClassification

logger = logging.getLogger(__name__)


# ==================== OCSF Schema Definitions ====================

class OCSFVersion(str, Enum):
    V1_3_0 = "1.3.0"
    V1_2_0 = "1.2.0"
    V1_1_0 = "1.1.0"


class OCSFClassUid(int, Enum):
    """OCSF Class UIDs (Category identifiers)."""
    # System Activity
    PROCESS_ACTIVITY = 1001
    FILE_SYSTEM_ACTIVITY = 1002
    NETWORK_ACTIVITY = 1003
    MEMORY_ACTIVITY = 1004
    SCHEDULED_JOB_ACTIVITY = 1005
    KERNEL_ACTIVITY = 1006
    MODULE_ACTIVITY = 1007
    
    # Identity & Access
    AUTHENTICATION = 3001
    AUTHORIZATION = 3002
    ENTITY_MANAGEMENT = 3003
    GROUP_MANAGEMENT = 3004
    PRIVILEGE_MANAGEMENT = 3005
    ROLE_MANAGEMENT = 3006
    ACCESS_CONTROL = 3007
    
    # Security Findings
    SECURITY_FINDING = 2001
    VULNERABILITY = 2002
    MALWARE = 2003
    THREAT_INTEL = 2004
    
    # Application Activity
    APPLICATION_LIFECYCLE = 4001
    API_ACTIVITY = 4002
    WEB_RESOURCE_ACTIVITY = 4003
    DATABASE_ACTIVITY = 4004
    
    # Network
    NETWORK_CONNECTION = 4005
    DNS_ACTIVITY = 4006
    HTTP_ACTIVITY = 4007
    EMAIL_ACTIVITY = 4008
    DHCP_ACTIVITY = 4009
    
    # Compliance
    COMPLIANCE_FINDING = 5001
    DATA_PROTECTION = 5002
    
    # Custom extensions
    CUSTOM_FINDING = 9001


class OCSFActivityId(int, Enum):
    """OCSF Activity IDs for Authentication class."""
    LOGIN = 1
    LOGOUT = 2
    LOGIN_FAILED = 3
    MFA_CHALLENGE = 4
    PASSWORD_CHANGE = 5
    ACCOUNT_LOCKOUT = 6
    ACCOUNT_UNLOCK = 7
    SESSION_CREATED = 8
    SESSION_TERMINATED = 9
    TOKEN_REFRESH = 10
    ASSUME_ROLE = 11
    OTHER = 99


class OCSFSeverityId(int, Enum):
    """OCSF Severity IDs."""
    INFORMATIONAL = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    CRITICAL = 5
    FATAL = 6
    UNKNOWN = 99


class OCSFStatusId(int, Enum):
    """OCSF Status IDs."""
    SUCCESS = 1
    FAILURE = 2
    ONGOING = 3
    UNKNOWN = 99


@dataclass
class OCSFEvent:
    """Base OCSF Event structure."""
    # Required fields
    time: datetime
    class_uid: int
    class_name: str
    activity_id: int
    activity_name: str
    type_uid: int
    type_name: str
    severity_id: int
    severity: str
    status_id: int
    status: str
    status_detail: str
    
    # Actor (who performed the action)
    actor: Dict[str, Any] = field(default_factory=dict)
    
    # Target (what was acted upon)
    target: Dict[str, Any] = field(default_factory=dict)
    
    # Source/Intermediate
    src_endpoint: Dict[str, Any] = field(default_factory=dict)
    dst_endpoint: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    cloud: Dict[str, Any] = field(default_factory=dict)
    observables: List[Dict[str, Any]] = field(default_factory=list)
    enrichments: List[Dict[str, Any]] = field(default_factory=list)
    
    # Custom fields
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    
    def to_ocsf_json(self) -> Dict[str, Any]:
        """Convert to OCSF-compliant JSON."""
        return {
            "time": self.time.isoformat() + "Z",
            "class_uid": self.class_uid,
            "class_name": self.class_name,
            "activity_id": self.activity_id,
            "activity_name": self.activity_name,
            "type_uid": self.type_uid,
            "type_name": self.type_name,
            "severity_id": self.severity_id,
            "severity": self.severity,
            "status_id": self.status_id,
            "status": self.status,
            "status_detail": self.status_detail,
            "actor": self.actor,
            "target": self.target,
            "src_endpoint": self.src_endpoint,
            "dst_endpoint": self.dst_endpoint,
            "metadata": self.metadata,
            "cloud": self.cloud,
            "observables": self.observables,
            "enrichments": self.enrichments,
            **self.custom_fields,
        }


# ==================== OCSF Event Builders ====================

class OCSFEventBuilder:
    """Build OCSF-compliant events from VCOS internal events."""
    
    @staticmethod
    def build_authentication_event(
        event_type: str,
        actor_user_id: str,
        actor_email: str,
        actor_ip: str,
        actor_user_agent: str,
        organization_id: str,
        status: str,
        metadata: Dict[str, Any] = None,
    ) -> OCSFEvent:
        """Build OCSF Authentication event."""
        
        activity_map = {
            "login": (OCSFActivityId.LOGIN, "Login"),
            "logout": (OCSFActivityId.LOGOUT, "Logout"),
            "login_failed": (OCSFActivityId.LOGIN_FAILED, "Login Failed"),
            "mfa_challenge": (OCSFActivityId.MFA_CHALLENGE, "MFA Challenge"),
            "password_change": (OCSFActivityId.PASSWORD_CHANGE, "Password Change"),
            "account_lockout": (OCSFActivityId.ACCOUNT_LOCKOUT, "Account Lockout"),
            "account_unlock": (OCSFActivityId.ACCOUNT_UNLOCK, "Account Unlock"),
        }
        
        activity_id, activity_name = activity_map.get(event_type, (OCSFActivityId.OTHER, "Other"))
        
        severity = OCSFSeverityId.LOW if status == "success" else OCSFSeverityId.MEDIUM
        if event_type == "login_failed":
            severity = OCSFSeverityId.HIGH
        
        return OCSFEvent(
            time=datetime.utcnow(),
            class_uid=OCSFClassUid.AUTHENTICATION,
            class_name="Authentication",
            activity_id=activity_id,
            activity_name=activity_name,
            type_uid=3001001 + activity_id,
            type_name=f"Authentication - {activity_name}",
            severity_id=severity,
            severity=severity.name.lower(),
            status_id=OCSFStatusId.SUCCESS if status == "success" else OCSFStatusId.FAILURE,
            status="Success" if status == "success" else "Failure",
            status_detail=metadata.get("failure_reason", "") if status != "success" else "",
            actor={
                "user": {
                    "uid": actor_user_id,
                    "name": actor_email,
                    "email_addr": actor_email,
                    "type": "User",
                },
                "process": {
                    "name": "vcos-auth",
                    "pid": 0,
                },
                "session": {
                    "uid": metadata.get("session_id", "") if metadata else "",
                },
                "user_name": actor_email,
            },
            target={
                "organization": {
                    "uid": organization_id,
                },
            },
            src_endpoint={
                "ip": actor_ip,
                "port": 0,
                "user_agent": actor_user_agent,
            },
            metadata={
                "product": {
                    "name": "VCOS",
                    "version": "1.0.0",
                    "vendor_name": "VCOS",
                },
                "version": "1.3.0",
                "event_code": event_type,
            },
            custom_fields=metadata or {},
        )
    
    @staticmethod
    def build_authorization_event(
        event_type: str,
        actor_user_id: str,
        actor_email: str,
        resource_type: str,
        resource_id: str,
        action: str,
        decision: str,
        organization_id: str,
        metadata: Dict[str, Any] = None,
    ) -> OCSFEvent:
        """Build OCSF Authorization event."""
        
        return OCSFEvent(
            time=datetime.utcnow(),
            class_uid=OCSFClassUid.AUTHORIZATION,
            class_name="Authorization",
            activity_id=1 if decision == "allow" else 2,
            activity_name="Access Granted" if decision == "allow" else "Access Denied",
            type_uid=3002001 if decision == "allow" else 3002002,
            type_name=f"Authorization - {event_type}",
            severity_id=OCSFSeverityId.LOW if decision == "allow" else OCSFSeverityId.MEDIUM,
            severity="low" if decision == "allow" else "medium",
            status_id=OCSFStatusId.SUCCESS if decision == "allow" else OCSFStatusId.FAILURE,
            status="Success" if decision == "allow" else "Failure",
            status_detail=f"Access {decision} for {action} on {resource_type}:{resource_id}",
            actor={
                "user": {
                    "uid": actor_user_id,
                    "name": actor_email,
                    "email_addr": actor_email,
                    "type": "User",
                },
            },
            target={
                "resource": {
                    "type": resource_type,
                    "uid": resource_id,
                    "name": resource_type,
                },
                "organization": {
                    "uid": organization_id,
                },
            },
            metadata={
                "product": {
                    "name": "VCOS",
                    "version": "1.0.0",
                    "vendor_name": "VCOS",
                },
                "version": "1.3.0",
                "action": action,
            },
            custom_fields=metadata or {},
        )
    
    @staticmethod
    def build_security_finding(
        finding_type: str,
        title: str,
        description: str,
        severity: OCSFSeverityId,
        organization_id: str,
        actor_user_id: Optional[str] = None,
        actor_email: Optional[str] = None,
        source_ip: Optional[str] = None,
        resources: List[Dict[str, Any]] = None,
        metadata: Dict[str, Any] = None,
    ) -> OCSFEvent:
        """Build OCSF Security Finding event."""
        
        return OCSFEvent(
            time=datetime.utcnow(),
            class_uid=OCSFClassUid.SECURITY_FINDING,
            class_name="Security Finding",
            activity_id=1,
            activity_name="Create",
            type_uid=2001001,
            type_name="Security Finding - Create",
            severity_id=severity,
            severity=severity.name.lower(),
            status_id=OCSFStatusId.ONGOING,
            status="Ongoing",
            status_detail=description,
            actor={
                "user": {
                    "uid": actor_user_id or "",
                    "name": actor_email or "",
                    "email_addr": actor_email or "",
                    "type": "User",
                } if actor_user_id else None,
            } if actor_user_id else {},
            target={
                "organization": {
                    "uid": organization_id,
                },
            },
            src_endpoint={
                "ip": source_ip or "",
            } if source_ip else {},
            observables=resources or [],
            metadata={
                "product": {
                    "name": "VCOS",
                    "version": "1.0.0",
                    "vendor_name": "VCOS",
                },
                "version": "1.3.0",
                "finding_type": finding_type,
            },
            custom_fields=metadata or {},
        )
    
    @staticmethod
    def build_data_protection_event(
        event_type: str,
        actor_user_id: str,
        actor_email: str,
        organization_id: str,
        classification: str,
        resource_type: str,
        resource_id: str,
        action: str,
        metadata: Dict[str, Any] = None,
    ) -> OCSFEvent:
        """Build OCSF Data Protection event."""
        
        return OCSFEvent(
            time=datetime.utcnow(),
            class_uid=OCSFClassUid.DATA_PROTECTION,
            class_name="Data Protection",
            activity_id=1,
            activity_name="Create",
            type_uid=5002001,
            type_name="Data Protection Event",
            severity_id=OCSFSeverityId.MEDIUM,
            severity="medium",
            status_id=OCSFStatusId.SUCCESS,
            status="Success",
            status_detail=f"Data {action} for {classification} {resource_type}",
            actor={
                "user": {
                    "uid": actor_user_id,
                    "name": actor_email,
                    "email_addr": actor_email,
                    "type": "User",
                },
            },
            target={
                "resource": {
                    "type": resource_type,
                    "uid": resource_id,
                    "name": resource_type,
                    "classification": classification,
                },
                "organization": {
                    "uid": organization_id,
                },
            },
            metadata={
                "product": {
                    "name": "VCOS",
                    "version": "1.0.0",
                    "vendor_name": "VCOS",
                },
                "version": "1.3.0",
                "data_classification": classification,
                "action": action,
            },
            custom_fields=metadata or {},
        )


# ==================== SIEM Integration ====================

class SIEMConnectorType(str, Enum):
    SPLUNK_HEC = "splunk_hec"
    DATADOG = "datadog"
    ELASTIC = "elastic"
    SENTINEL = "sentinel"
    SUMO_LOGIC = "sumo_logic"
    SYSLOG = "syslog"
    KAFKA = "kafka"
    WEBHOOK = "webhook"


@dataclass
class SIEMConnectorConfig:
    """SIEM connector configuration."""
    connector_type: SIEMConnectorType
    name: str
    endpoint: str
    auth_token: Optional[str] = None
    api_key: Optional[str] = None
    index: Optional[str] = None
    sourcetype: str = "ocsf"
    batch_size: int = 100
    flush_interval: float = 5.0
    timeout: float = 30.0
    retry_attempts: int = 3
    verify_ssl: bool = True
    custom_headers: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


class SIEMConnector:
    """Base SIEM connector."""
    
    def __init__(self, config: SIEMConnectorConfig):
        self.config = config
        self._buffer: List[OCSFEvent] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """Initialize connector."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            connector=aiohttp.TCPConnector(verify_ssl=self.config.verify_ssl),
        )
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(f"Initialized {self.config.connector_type.value} SIEM connector: {self.config.name}")
    
    async def close(self):
        """Close connector."""
        self._running = False
        if self._flush_task:
            await self._flush_task
        await self._flush()
        if self._session:
            await self._session.close()
    
    async def send_event(self, event: OCSFEvent):
        """Queue event for sending."""
        self._buffer.append(event)
        if len(self._buffer) >= self.config.batch_size:
            await self._flush()
    
    async def _flush(self):
        """Flush buffer to SIEM."""
        if not self._buffer or not self._session:
            return
        
        events = self._buffer[:]
        self._buffer.clear()
        
        try:
            await self._send_batch(events)
        except Exception as e:
            logger.error(f"Failed to send events to {self.config.name}: {e}")
            # Re-queue events
            self._buffer = events + self._buffer
    
    async def _send_batch(self, events: List[OCSFEvent]):
        """Send batch to SIEM - implemented by subclasses."""
        raise NotImplementedError
    
    async def _flush_loop(self):
        """Periodic flush loop."""
        while self._running:
            await asyncio.sleep(self.config.flush_interval)
            await self._flush()


class SplunkHECConnector(SIEMConnector):
    """Splunk HTTP Event Collector connector."""
    
    async def _send_batch(self, events: List[OCSFEvent]):
        headers = {
            "Authorization": f"Splunk {self.config.auth_token}",
            "Content-Type": "application/json",
        }
        
        payload = "\n".join(json.dumps(event.to_ocsf_json()) for event in events)
        
        async with self._session.post(
            f"{self.config.endpoint}/services/collector",
            headers=headers,
            data=payload,
        ) as resp:
            if resp.status >= 400:
                error = await resp.text()
                raise Exception(f"Splunk HEC error: {error}")


class DatadogConnector(SIEMConnector):
    """Datadog Logs API connector."""
    
    async def _send_batch(self, events: List[OCSFEvent]):
        headers = {
            "DD-API-KEY": self.config.api_key,
            "Content-Type": "application/json",
        }
        
        payload = [
            {
                "ddsource": "vcos",
                "ddtags": f"env:production,service:vcos",
                "hostname": "vcos",
                "message": json.dumps(event.to_ocsf_json()),
                "service": "vcos",
            }
            for event in events
        ]
        
        async with self._session.post(
            f"{self.config.endpoint}/api/v2/logs",
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status >= 400:
                error = await resp.text()
                raise Exception(f"Datadog error: {error}")


class ElasticConnector(SIEMConnector):
    """Elasticsearch connector."""
    
    async def _send_batch(self, events: List[OCSFEvent]):
        # Bulk API format
        bulk_lines = []
        for event in events:
            bulk_lines.append(json.dumps({"index": {"_index": self.config.index or "vcos-ocsf"}}))
            bulk_lines.append(json.dumps(event.to_ocsf_json()))
        
        payload = "\n".join(bulk_lines) + "\n"
        
        headers = {
            "Authorization": f"ApiKey {self.config.auth_token}",
            "Content-Type": "application/x-ndjson",
        }
        
        async with self._session.post(
            f"{self.config.endpoint}/_bulk",
            headers=headers,
            data=payload,
        ) as resp:
            if resp.status >= 400:
                error = await resp.text()
                raise Exception(f"Elastic error: {error}")


class SentinelConnector(SIEMConnector):
    """Microsoft Sentinel (Log Analytics) connector."""
    
    async def _send_batch(self, events: List[OCSFEvent]):
        # Sentinel uses Data Collector API
        import base64
        import hmac
        import hashlib
        
        workspace_id = self.config.custom_headers.get("workspace_id")
        shared_key = self.config.auth_token
        
        payload = [event.to_ocsf_json() for event in events]
        body = json.dumps(payload)
        
        # Build signature
        date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        string_to_hash = f"POST\n{len(body)}\napplication/json\nx-ms-date:{date}\n/api/logs"
        signature = base64.b64encode(
            hmac.new(base64.b64decode(shared_key), string_to_hash.encode(), hashlib.sha256).digest()
        ).decode()
        
        headers = {
            "Authorization": f"SharedKey {workspace_id}:{signature}",
            "Content-Type": "application/json",
            "Log-Type": "VCOS_OCSF",
            "x-ms-date": date,
        }
        
        async with self._session.post(
            f"https://{workspace_id}.ods.opinsights.azure.com/api/logs?api-version=2016-04-01",
            headers=headers,
            data=body,
        ) as resp:
            if resp.status >= 400:
                error = await resp.text()
                raise Exception(f"Sentinel error: {error}")


class KafkaConnector(SIEMConnector):
    """Apache Kafka connector."""
    
    def __init__(self, config: SIEMConnectorConfig):
        super().__init__(config)
        self._producer = None
    
    async def initialize(self):
        from aiokafka import AIOKafkaProducer
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.config.endpoint,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await self._producer.start()
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
    
    async def close(self):
        self._running = False
        if self._flush_task:
            await self._flush_task
        if self._producer:
            await self._producer.stop()
    
    async def _send_batch(self, events: List[OCSFEvent]):
        topic = self.config.custom_headers.get("topic", "vcos-ocsf")
        for event in self._buffer[:]:
            await self._producer.send_and_wait(topic, event.to_ocsf_json())
        self._buffer.clear()


class WebhookConnector(SIEMConnector):
    """Generic webhook connector."""
    
    async def _send_batch(self, events: List[OCSFEvent]):
        headers = {
            "Content-Type": "application/json",
            **self.config.custom_headers,
        }
        
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        
        payload = [event.to_ocsf_json() for event in events]
        
        async with self._session.post(
            self.config.endpoint,
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status >= 400:
                error = await resp.text()
                raise Exception(f"Webhook error: {error}")


# ==================== DLP Engine ====================

class DLPAction(str, Enum):
    """DLP actions."""
    ALLOW = "allow"
    BLOCK = "block"
    QUARANTINE = "quarantine"
    REDACT = "redact"
    ALERT = "alert"
    ENCRYPT = "encrypt"


class DLPClassifierType(str, Enum):
    """DLP classifier types."""
    REGEX = "regex"
    KEYWORD = "keyword"
    ML_MODEL = "ml_model"
    COMPOSITE = "composite"


@dataclass
class DLPRule:
    """DLP detection rule."""
    id: str
    name: str
    description: str
    classifier_type: DLPClassifierType
    patterns: List[str] = field(default_factory=list)
    ml_model_id: Optional[str] = None
    classifications: List[DataClassification] = field(default_factory=list)
    min_confidence: float = 0.8
    action: DLPAction = DLPAction.ALERT
    severity: OCSFSeverityId = OCSFSeverityId.MEDIUM
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DLPMatch:
    """DLP match result."""
    rule_id: str
    rule_name: str
    classification: DataClassification
    confidence: float
    matched_content: str
    location: Dict[str, Any]
    action: DLPAction
    severity: OCSFSeverityId


class DLPEngine:
    """
    Data Loss Prevention Engine.
    
    Features:
    - Regex-based pattern matching
    - Keyword-based detection
    - ML model integration for unstructured data
    - Composite rules (AND/OR logic)
    - Real-time scanning with configurable actions
    - Integration with OCSF for SIEM alerting
    """
    
    def __init__(
        self,
        session: AsyncSession = None,
        ocsf_builder: OCSFEventBuilder = None,
        siem_manager: Any = None,
    ):
        self.session = session
        self.ocsf_builder = ocsf_builder or OCSFEventBuilder()
        self.siem_manager = siem_manager
        
        self._rules: Dict[str, DLPRule] = {}
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}
        self._ml_models: Dict[str, Any] = {}
        
        # Default rules
        self._load_default_rules()
    
    def _load_default_rules(self):
        """Load default DLP rules."""
        default_rules = [
            DLPRule(
                id="pii_ssn",
                name="US Social Security Number",
                description="Detect US SSN format (XXX-XX-XXXX)",
                classifier_type=DLPClassifierType.REGEX,
                patterns=[r'\b\d{3}-\d{2}-\d{4}\b'],
                classifications=[DataClassification.PII],
                action=DLPAction.REDACT,
                severity=OCSFSeverityId.HIGH,
            ),
            DLPRule(
                id="pii_email",
                name="Email Address",
                description="Detect email addresses",
                classifier_type=DLPClassifierType.REGEX,
                patterns=[r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'],
                classifications=[DataClassification.PII],
                action=DLPAction.ALERT,
                severity=OCSFSeverityId.MEDIUM,
            ),
            DLPRule(
                id="pci_credit_card",
                name="Credit Card Number",
                description="Detect credit card numbers (Luhn validated)",
                classifier_type=DLPClassifierType.REGEX,
                patterns=[r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'],
                classifications=[DataClassification.PCI],
                action=DLPAction.BLOCK,
                severity=OCSFSeverityId.CRITICAL,
            ),
            DLPRule(
                id="pci_cvv",
                name="CVV/CVC Code",
                description="Detect 3-4 digit CVV codes",
                classifier_type=DLPClassifierType.REGEX,
                patterns=[r'\b\d{3,4}\b'],
                classifications=[DataClassification.PCI],
                action=DLPAction.BLOCK,
                severity=OCSFSeverityId.CRITICAL,
            ),
            DLPRule(
                id="phi_medical_record",
                name="Medical Record Number",
                description="Detect medical record numbers",
                classifier_type=DLPClassifierType.REGEX,
                patterns=[r'\b[A-Z]{2}\d{6,8}\b', r'\bMRN\d{6,10}\b'],
                classifications=[DataClassification.PHI],
                action=DLPAction.ALERT,
                severity=OCSFSeverityId.HIGH,
            ),
            DLPRule(
                id="restricted_api_key",
                name="API Key/Secret",
                description="Detect API keys and secrets",
                classifier_type=DLPClassifierType.REGEX,
                patterns=[
                    r'(?i)(api[_-]?key|secret|token)["\s:=]+[\w-]{20,}',
                    r'(?i)(aws[_-]?access[_-]?key|aws[_-]?secret)',
                    r'(?i)(private[_-]?key|ssh[_-]?key)',
                ],
                classifications=[DataClassification.RESTRICTED],
                action=DLPAction.BLOCK,
                severity=OCSFSeverityId.CRITICAL,
            ),
            DLPRule(
                id="pii_phone_us",
                name="US Phone Number",
                description="Detect US phone numbers",
                classifier_type=DLPClassifierType.REGEX,
                patterns=[r'\b\d{3}-\d{3}-\d{4}\b', r'\b\(\d{3}\)\s*\d{3}-\d{4}\b'],
                classifications=[DataClassification.PII],
                action=DLPAction.ALERT,
                severity=OCSFSeverityId.MEDIUM,
            ),
        ]
        
        for rule in default_rules:
            self.add_rule(rule)
    
    def add_rule(self, rule: DLPRule):
        """Add DLP rule."""
        self._rules[rule.id] = rule
        
        # Compile regex patterns
        if rule.classifier_type in (DLPClassifierType.REGEX, DLPClassifierType.COMPOSITE):
            self._compiled_patterns[rule.id] = [
                re.compile(pattern, re.IGNORECASE) for pattern in rule.patterns
            ]
    
    def remove_rule(self, rule_id: str):
        """Remove DLP rule."""
        self._rules.pop(rule_id, None)
        self._compiled_patterns.pop(rule_id, None)
    
    def get_rule(self, rule_id: str) -> Optional[DLPRule]:
        """Get DLP rule."""
        return self._rules.get(rule_id)
    
    def list_rules(self, enabled_only: bool = True) -> List[DLPRule]:
        """List DLP rules."""
        rules = list(self._rules.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        return rules
    
    async def scan_content(
        self,
        content: str,
        context: Dict[str, Any] = None,
    ) -> List[DLPMatch]:
        """
        Scan content for DLP violations.
        
        Args:
            content: Text content to scan
            context: Additional context (field_name, resource_type, user_id, etc.)
        
        Returns:
            List of DLP matches
        """
        matches = []
        context = context or {}
        
        for rule_id, rule in self._rules.items():
            if not rule.enabled:
                continue
            
            if rule.classifier_type in (DLPClassifierType.REGEX, DLPClassifierType.COMPOSITE):
                matches.extend(await self._scan_regex(content, rule, context))
            elif rule.classifier_type == DLPClassifierType.KEYWORD:
                matches.extend(await self._scan_keywords(content, rule, context))
            elif rule.classifier_type == DLPClassifierType.ML_MODEL:
                matches.extend(await self._scan_ml(content, rule, context))
        
        return matches
    
    async def _scan_regex(
        self,
        content: str,
        rule: DLPRule,
        context: Dict[str, Any],
    ) -> List[DLPMatch]:
        """Scan content using regex patterns."""
        matches = []
        patterns = self._compiled_patterns.get(rule.id, [])
        
        for pattern in patterns:
            for match in pattern.finditer(content):
                matched_text = match.group()
                
                # Additional validation for PCI (Luhn check)
                if rule.id == "pci_credit_card" and not self._luhn_check(matched_text.replace("-", "").replace(" ", "")):
                    continue
                
                confidence = 1.0
                if confidence >= rule.min_confidence:
                    matches.append(DLPMatch(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        classification=rule.classifications[0] if rule.classifications else DataClassification.INTERNAL,
                        confidence=confidence,
                        matched_content=matched_text[:100],
                        location={
                            "offset": match.start(),
                            "length": match.end() - match.start(),
                            "field_name": context.get("field_name", ""),
                        },
                        action=rule.action,
                        severity=rule.severity,
                    ))
        
        return matches
    
    async def _scan_keywords(
        self,
        content: str,
        rule: DLPRule,
        context: Dict[str, Any],
    ) -> List[DLPMatch]:
        """Scan content using keyword matching."""
        matches = []
        content_lower = content.lower()
        
        for keyword in rule.patterns:
            if keyword.lower() in content_lower:
                matches.append(DLPMatch(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    classification=rule.classifications[0] if rule.classifications else DataClassification.INTERNAL,
                    confidence=0.9,
                    matched_content=keyword,
                    location={
                        "offset": content_lower.index(keyword.lower()),
                        "length": len(keyword),
                        "field_name": context.get("field_name", ""),
                    },
                    action=rule.action,
                    severity=rule.severity,
                ))
        
        return matches
    
    async def _scan_ml(
        self,
        content: str,
        rule: DLPRule,
        context: Dict[str, Any],
    ) -> List[DLPMatch]:
        """Scan content using ML model."""
        # In production, integrate with ML model serving (TensorFlow Serving, Triton, etc.)
        # For now, return empty
        return []
    
    def _luhn_check(self, card_number: str) -> bool:
        """Validate credit card number using Luhn algorithm."""
        digits = [int(d) for d in card_number if d.isdigit()]
        if len(digits) < 13 or len(digits) > 19:
            return False
        
        checksum = 0
        for i, d in enumerate(reversed(digits)):
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            checksum += d
        
        return checksum % 10 == 0
    
    async def scan_record(
        self,
        record: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, List[DLPMatch]]:
        """
        Scan entire record (JSON object) for DLP violations.
        
        Returns:
            Dict mapping field names to list of matches
        """
        results = {}
        context = context or {}
        
        async def scan_value(value: Any, field_path: str):
            if isinstance(value, str):
                matches = await self.scan_content(value, {**context, "field_name": field_path})
                if matches:
                    results[field_path] = matches
            elif isinstance(value, dict):
                for k, v in value.items():
                    await scan_value(v, f"{field_path}.{k}" if field_path else k)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    await scan_value(item, f"{field_path}[{i}]")
        
        for field_name, value in record.items():
            await scan_value(value, field_name)
        
        return results
    
    async def apply_actions(
        self,
        matches: List[DLPMatch],
        content: str,
        context: Dict[str, Any] = None,
    ) -> Tuple[str, List[OCSFEvent]]:
        """
        Apply DLP actions to content based on matches.
        
        Returns:
            Tuple of (modified_content, ocsf_events)
        """
        modified_content = content
        ocsf_events = []
        
        # Sort by severity (highest first) and action priority
        action_priority = {
            DLPAction.BLOCK: 4,
            DLPAction.QUARANTINE: 3,
            DLPAction.REDACT: 2,
            DLPAction.ENCRYPT: 2,
            DLPAction.ALERT: 1,
            DLPAction.ALLOW: 0,
        }
        
        sorted_matches = sorted(matches, key=lambda m: (action_priority.get(m.action, 0), m.severity), reverse=True)
        
        for match in sorted_matches:
            if match.action == DLPAction.REDACT:
                # Redact matched content
                modified_content = modified_content.replace(
                    match.matched_content,
                    "[REDACTED]"
                )
            
            elif match.action == DLPAction.ENCRYPT:
                # Would integrate with field encryption engine
                pass
            
            elif match.action == DLPAction.BLOCK:
                # Generate blocking event
                event = self.ocsf_builder.build_security_finding(
                    finding_type="dlp.blocked",
                    title=f"DLP Blocked: {match.rule_name}",
                    description=f"Blocked content matching rule: {match.rule_name}",
                    severity=match.severity,
                    organization_id=context.get("organization_id", "") if context else "",
                    actor_user_id=context.get("actor_user_id") if context else None,
                    actor_email=context.get("actor_email") if context else None,
                    source_ip=context.get("source_ip") if context else None,
                    metadata={
                        "dlp_rule_id": match.rule_id,
                        "dlp_rule_name": match.rule_name,
                        "classification": match.classification.value,
                        "confidence": match.confidence,
                        "action": match.action.value,
                    },
                )
                ocsf_events.append(event)
            
            elif match.action == DLPAction.ALERT:
                # Generate alert event
                event = self.ocsf_builder.build_security_finding(
                    finding_type="dlp.alert",
                    title=f"DLP Alert: {match.rule_name}",
                    description=f"Content matched DLP rule: {match.rule_name}",
                    severity=match.severity,
                    organization_id=context.get("organization_id", "") if context else "",
                    actor_user_id=context.get("actor_user_id") if context else None,
                    actor_email=context.get("actor_email") if context else None,
                    source_ip=context.get("source_ip") if context else None,
                    metadata={
                        "dlp_rule_id": match.rule_id,
                        "dlp_rule_name": match.rule_name,
                        "classification": match.classification.value,
                        "confidence": match.confidence,
                        "action": match.action.value,
                    },
                )
                ocsf_events.append(event)
            
            elif match.action == DLPAction.QUARANTINE:
                # Generate quarantine event
                event = self.ocsf_builder.build_security_finding(
                    finding_type="dlp.quarantine",
                    title=f"DLP Quarantined: {match.rule_name}",
                    description=f"Content quarantined per DLP rule: {match.rule_name}",
                    severity=match.severity,
                    organization_id=context.get("organization_id", "") if context else "",
                    actor_user_id=context.get("actor_user_id") if context else None,
                    actor_email=context.get("actor_email") if context else None,
                    source_ip=context.get("source_ip") if context else None,
                    metadata={
                        "dlp_rule_id": match.rule_id,
                        "dlp_rule_name": match.rule_name,
                        "classification": match.classification.value,
                        "confidence": match.confidence,
                        "action": match.action.value,
                    },
                )
                ocsf_events.append(event)
        
        return modified_content, ocsf_events


# ==================== SIEM Manager ====================

class SIEMManager:
    """Manages multiple SIEM connectors and event routing."""
    
    def __init__(self):
        self._connectors: Dict[str, SIEMConnector] = {}
        self._event_buffer: List[OCSFEvent] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        self._routing_rules: List[Dict[str, Any]] = []
    
    async def initialize(self):
        """Initialize SIEM manager."""
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("SIEM Manager initialized")
    
    async def close(self):
        """Close SIEM manager."""
        self._running = False
        if self._flush_task:
            await self._flush_task
        for connector in self._connectors.values():
            await connector.close()
    
    def add_connector(self, connector: SIEMConnector):
        """Add SIEM connector."""
        self._connectors[connector.config.name] = connector
    
    def remove_connector(self, name: str):
        """Remove SIEM connector."""
        if name in self._connectors:
            asyncio.create_task(self._connectors[name].close())
            del self._connectors[name]
    
    def add_routing_rule(
        self,
        class_uid: Optional[int] = None,
        severity_min: Optional[OCSFSeverityId] = None,
        classifications: Optional[List[DataClassification]] = None,
        connector_names: List[str] = None,
    ):
        """Add routing rule for event forwarding."""
        self._routing_rules.append({
            "class_uid": class_uid,
            "severity_min": severity_min,
            "classifications": classifications,
            "connector_names": connector_names or list(self._connectors.keys()),
        })
    
    async def send_event(self, event: OCSFEvent):
        """Route event to appropriate connectors."""
        # Determine target connectors
        target_connectors = self._get_target_connectors(event)
        
        for connector_name in target_connectors:
            if connector_name in self._connectors:
                await self._connectors[connector_name].send_event(event)
    
    def _get_target_connectors(self, event: OCSFEvent) -> List[str]:
        """Determine which connectors should receive this event."""
        if not self._routing_rules:
            return list(self._connectors.keys())
        
        targets = set()
        for rule in self._routing_rules:
            match = True
            
            if rule.get("class_uid") and event.class_uid != rule["class_uid"]:
                match = False
            
            if rule.get("severity_min") and event.severity_id < rule["severity_min"]:
                match = False
            
            if rule.get("classifications"):
                event_class = event.custom_fields.get("data_classification") or event.custom_fields.get("classification")
                if event_class not in [c.value for c in rule["classifications"]]:
                    match = False
            
            if match:
                targets.update(rule.get("connector_names", []))
        
        return list(targets)
    
    async def _flush_loop(self):
        """Periodic flush of all connectors."""
        while self._running:
            await asyncio.sleep(5)
            for connector in self._connectors.values():
                await connector._flush()


# ==================== Database Models ====================

class SIEMConnectorModel(Base, TimestampMixin):
    """Database model for SIEM connectors."""
    
    __tablename__ = "siem_connectors"
    __table_args__ = (
        Index("ix_siem_connectors_org", "organization_id"),
        UniqueConstraint("organization_id", "name", name="uq_siem_connectors_org_name"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    auth_token: Mapped[Optional[str]] = mapped_column(Text)  # Encrypted
    api_key: Mapped[Optional[str]] = mapped_column(Text)  # Encrypted
    index: Mapped[Optional[str]] = mapped_column(String(128))
    sourcetype: Mapped[str] = mapped_column(String(64), default="ocsf")
    batch_size: Mapped[int] = mapped_column(Integer, default=100)
    flush_interval: Mapped[float] = mapped_column(default=5.0)
    timeout: Mapped[float] = mapped_column(default=30.0)
    retry_attempts: Mapped[int] = mapped_column(Integer, default=3)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    custom_headers: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_flush_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    events_sent: Mapped[int] = mapped_column(Integer, default=0)
    events_failed: Mapped[int] = mapped_column(Integer, default=0)


class DLPRuleModel(Base, TimestampMixin):
    """Database model for DLP rules."""
    
    __tablename__ = "dlp_rules"
    __table_args__ = (
        Index("ix_dlp_rules_org", "organization_id"),
        Index("ix_dlp_rules_enabled", "enabled"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    classifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    patterns: Mapped[List[str]] = mapped_column(JSON, default=list)
    ml_model_id: Mapped[Optional[str]] = mapped_column(String(128))
    classifications: Mapped[List[str]] = mapped_column(JSON, default=list)
    min_confidence: Mapped[float] = mapped_column(default=0.8)
    action: Mapped[str] = mapped_column(String(20), default="alert")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rule_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class DLPMatchLog(Base, TimestampMixin):
    """Database model for DLP match logs."""
    
    __tablename__ = "dlp_matches"
    __table_args__ = (
        Index("ix_dlp_matches_org", "organization_id"),
        Index("ix_dlp_matches_rule", "rule_id"),
        Index("ix_dlp_matches_classification", "classification"),
        Index("ix_dlp_matches_action", "action"),
        Index("ix_dlp_matches_time", "created_at"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0)
    matched_content_preview: Mapped[str] = mapped_column(Text)
    field_path: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey("users.id", ondelete="SET NULL"))
    actor_email: Mapped[Optional[str]] = mapped_column(String(255))
    source_ip: Mapped[Optional[str]] = mapped_column(String(64))
    resource_type: Mapped[Optional[str]] = mapped_column(String(64))
    resource_id: Mapped[Optional[str]] = mapped_column(String(64))
    match_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class SIEMConnectorModel(Base, TimestampMixin):
    """Database model for SIEM connectors."""
    
    __tablename__ = "siem_connectors"
    __table_args__ = (
        Index("ix_siem_connectors_org", "organization_id"),
        UniqueConstraint("organization_id", "name", name="uq_siem_connectors_org_name"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    auth_token: Mapped[Optional[str]] = mapped_column(Text)  # Encrypted
    api_key: Mapped[Optional[str]] = mapped_column(Text)  # Encrypted
    index: Mapped[Optional[str]] = mapped_column(String(128))
    sourcetype: Mapped[str] = mapped_column(String(64), default="ocsf")
    batch_size: Mapped[int] = mapped_column(Integer, default=100)
    flush_interval: Mapped[float] = mapped_column(default=5.0)
    timeout: Mapped[float] = mapped_column(default=30.0)
    retry_attempts: Mapped[int] = mapped_column(Integer, default=3)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    custom_headers: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_flush_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    events_sent: Mapped[int] = mapped_column(Integer, default=0)
    events_failed: Mapped[int] = mapped_column(Integer, default=0)


class DLPRuleModel(Base, TimestampMixin):
    """Database model for DLP rules."""
    
    __tablename__ = "dlp_rules"
    __table_args__ = (
        Index("ix_dlp_rules_org", "organization_id"),
        Index("ix_dlp_rules_enabled", "enabled"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    classifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    patterns: Mapped[List[str]] = mapped_column(JSON, default=list)
    ml_model_id: Mapped[Optional[str]] = mapped_column(String(128))
    classifications: Mapped[List[str]] = mapped_column(JSON, default=list)
    min_confidence: Mapped[float] = mapped_column(default=0.8)
    action: Mapped[str] = mapped_column(String(20), default="alert")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rule_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class DLPMatchLog(Base, TimestampMixin):
    """Database model for DLP match logs."""
    
    __tablename__ = "dlp_matches"
    __table_args__ = (
        Index("ix_dlp_matches_org", "organization_id"),
        Index("ix_dlp_matches_rule", "rule_id"),
        Index("ix_dlp_matches_classification", "classification"),
        Index("ix_dlp_matches_action", "action"),
        Index("ix_dlp_matches_time", "created_at"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0)
    matched_content_preview: Mapped[str] = mapped_column(Text)
    field_path: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey("users.id", ondelete="SET NULL"))
    actor_email: Mapped[Optional[str]] = mapped_column(String(255))
    source_ip: Mapped[Optional[str]] = mapped_column(String(64))
    resource_type: Mapped[Optional[str]] = mapped_column(String(64))
    resource_id: Mapped[Optional[str]] = mapped_column(String(64))
    match_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


# ==================== Global Managers ====================

_ocsf_builder: Optional[OCSFEventBuilder] = None
_dlp_engine: Optional[DLPEngine] = None
_siem_manager: Optional[SIEMManager] = None


def get_ocsf_builder() -> OCSFEventBuilder:
    """Get global OCSF event builder."""
    global _ocsf_builder
    if _ocsf_builder is None:
        _ocsf_builder = OCSFEventBuilder()
    return _ocsf_builder


def get_dlp_engine(
    session: AsyncSession = None,
    ocsf_builder: OCSFEventBuilder = None,
    siem_manager: Any = None,
) -> DLPEngine:
    """Get global DLP engine."""
    global _dlp_engine
    if _dlp_engine is None:
        _dlp_engine = DLPEngine(session, ocsf_builder, siem_manager)
    return _dlp_engine


def get_siem_manager() -> SIEMManager:
    """Get global SIEM manager."""
    global _siem_manager
    if _siem_manager is None:
        _siem_manager = SIEMManager()
    return _siem_manager


async def init_ocsf_siem(
    session: AsyncSession = None,
) -> Tuple[OCSFEventBuilder, DLPEngine, SIEMManager]:
    """Initialize OCSF SIEM and DLP components."""
    global _ocsf_builder, _dlp_engine, _siem_manager
    
    _ocsf_builder = OCSFEventBuilder()
    _siem_manager = SIEMManager()
    _dlp_engine = DLPEngine(session, _ocsf_builder, _siem_manager)
    
    await _siem_manager.initialize()
    
    logger.info("OCSF SIEM and DLP initialized")
    return _ocsf_builder, _dlp_engine, _siem_manager


# ==================== Convenience Functions ====================

async def log_ocsf_event(
    event: OCSFEvent,
    siem_manager: SIEMManager = None,
):
    """Log OCSF event to SIEM."""
    if siem_manager:
        await siem_manager.send_event(event)
    else:
        manager = get_siem_manager()
        await manager.send_event(event)


async def scan_for_dlp(
    content: str,
    context: Dict[str, Any] = None,
    dlp_engine: DLPEngine = None,
) -> List[DLPMatch]:
    """Scan content for DLP violations."""
    if dlp_engine:
        return await dlp_engine.scan_content(content, context)
    else:
        engine = get_dlp_engine()
        return await engine.scan_content(content, context)


async def scan_and_protect(
    content: str,
    context: Dict[str, Any] = None,
    dlp_engine: DLPEngine = None,
) -> Tuple[str, List[OCSFEvent]]:
    """Scan content and apply DLP actions."""
    if dlp_engine:
        matches = await dlp_engine.scan_content(content, context)
        return await dlp_engine.apply_actions(matches, content, context)
    else:
        engine = get_dlp_engine()
        matches = await engine.scan_content(content, context)
        return await engine.apply_actions(matches, content, context)


# ==================== ML Classifier Integration ====================

class MLClassifier:
    """
    ML-based DLP classifier for unstructured data.
    
    Integrates with:
    - TensorFlow Serving
    - Triton Inference Server
    - Custom model endpoints
    - ONNX Runtime
    """
    
    def __init__(
        self,
        model_endpoint: str,
        model_name: str,
    ):
        self.model_endpoint = model_endpoint
        self.model_name = model_name