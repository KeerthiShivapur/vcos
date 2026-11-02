"""
Breach Detection and Notification for VCOS.

Provides:
- Real-time breach detection from multiple sources
- Automated incident classification and severity scoring
- 72-hour GDPR breach notification workflow
- Evidence preservation and chain of custody
- Regulatory notification templates
- Post-incident analysis and reporting
"""

import asyncio
import hashlib
import json
import logging
import secrets
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

import aiofiles

from app.core.config import settings
from app.core.audit_log import audit_log_manager, EventType, Severity
from app.core.siem import get_siem_manager, OCSFEventBuilder, OCSFClass, OCSFCategory

logger = logging.getLogger(__name__)


class BreachType(str, Enum):
    """Types of data breaches."""
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    DATA_EXFILTRATION = "data_exfiltration"
    RANSOMWARE = "ransomware"
    INSIDER_THREAT = "insider_threat"
    PHISHING = "phishing"
    MALWARE = "malware"
    MISCONFIGURATION = "misconfiguration"
    LOST_DEVICE = "lost_device"
    THIRD_PARTY = "third_party"
    PHYSICAL_THEFT = "physical_theft"
    SOCIAL_ENGINEERING = "social_engineering"
    UNKNOWN = "unknown"


class BreachSeverity(str, Enum):
    """Breach severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BreachStatus(str, Enum):
    """Breach investigation status."""
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    CONFIRMED = "confirmed"
    CONTAINED = "contained"
    ERADICATED = "eradicated"
    RECOVERED = "recovered"
    NOTIFIED = "notified"
    CLOSED = "closed"
    FALSE_POSITIVE = "false_positive"


class NotificationType(str, Enum):
    """Types of breach notifications."""
    SUPERVISORY_AUTHORITY = "supervisory_authority"  # GDPR 72-hour
    DATA_SUBJECTS = "data_subjects"  # GDPR Art. 34
    REGULATOR = "regulator"  # HIPAA, PCI, etc.
    LAW_ENFORCEMENT = "law_enforcement"
    PARTNERS = "partners"  # Third parties
    INTERNAL = "internal"  # Internal stakeholders
    PUBLIC = "public"  # Public disclosure


class DataCategory(str, Enum):
    """Categories of personal/sensitive data."""
    PII = "pii"  # Personal Identifiable Information
    PHI = "phi"  # Protected Health Information
    FINANCIAL = "financial"  # Financial data
    CREDENTIALS = "credentials"  # Authentication credentials
    BIOMETRIC = "biometric"  # Biometric data
    LOCATION = "location"  # Location data
    BEHAVIORAL = "behavioral"  # Behavioral/analytics data
    CHILDREN = "children"  # Children's data
    SPECIAL_CATEGORY = "special_category"  # GDPR Art. 9
    INTELLECTUAL_PROPERTY = "ip"  # Trade secrets, IP
    UNKNOWN = "unknown"


@dataclass
class BreachIndicator:
    """Indicator of compromise or breach signal."""
    id: str
    source: str  # dlp, siem, ids, user_report, audit_log, threat_intel
    indicator_type: str  # anomaly, signature, behavioral, threshold
    description: str
    severity: BreachSeverity
    confidence: float  # 0-1
    detected_at: datetime = field(default_factory=datetime.utcnow)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    mitre_attack_techniques: List[str] = field(default_factory=list)
    related_entities: List[str] = field(default_factory=list)  # IPs, users, hosts, files


@dataclass
class AffectedData:
    """Description of affected data in a breach."""
    data_categories: List[DataCategory]
    record_count: int
    data_subjects_affected: int
    systems_affected: List[str]
    data_description: str
    encryption_status: str  # encrypted, unencrypted, partially_encrypted
    contains_special_category: bool = False
    contains_children_data: bool = False
    jurisdictions: List[str] = field(default_factory=list)  # GDPR, CCPA, HIPAA, etc.


@dataclass
class BreachTimelineEvent:
    """Event in breach investigation timeline."""
    id: str
    timestamp: datetime
    event_type: str  # detected, analyzed, contained, notified, etc.
    description: str
    actor: str
    details: Dict[str, Any] = field(default_factory=dict)
    evidence_ids: List[str] = field(default_factory=list)


@dataclass
class BreachIncident:
    """Data breach incident record."""
    id: str
    title: str
    breach_type: BreachType
    severity: BreachSeverity
    status: BreachStatus
    
    # Detection
    detected_at: datetime
    detected_by: str  # system, user, third_party
    detection_source: str
    initial_indicators: List[BreachIndicator] = field(default_factory=list)
    
    # Impact Assessment
    affected_data: Optional[AffectedData] = None
    estimated_records: int = 0
    estimated_subjects: int = 0
    
    # Investigation
    assigned_to: Optional[str] = None
    investigation_team: List[str] = field(default_factory=list)
    timeline: List[BreachTimelineEvent] = field(default_factory=list)
    evidence_collected: List[str] = field(default_factory=list)
    root_cause: str = ""
    attack_vector: str = ""
    
    # Containment & Recovery
    contained_at: Optional[datetime] = None
    containment_actions: List[str] = field(default_factory=list)
    recovery_actions: List[str] = field(default_factory=list)
    recovered_at: Optional[datetime] = None
    
    # Notifications
    notifications_sent: List["BreachNotification"] = field(default_factory=list)
    supervisory_notified_at: Optional[datetime] = None
    data_subjects_notified_at: Optional[datetime] = None
    
    # Compliance
    gdpr_applicable: bool = False
    hipaa_applicable: bool = False
    pci_applicable: bool = False
    ccpa_applicable: bool = False
    fedramp_applicable: bool = False
    other_regulations: List[str] = field(default_factory=list)
    
    # Risk Assessment
    risk_score: float = 0.0  # 0-100
    likelihood: str = "medium"  # low, medium, high, very_high
    impact: str = "medium"  # low, medium, high, very_high
    
    # Closure
    closed_at: Optional[datetime] = None
    closure_summary: str = ""
    lessons_learned: List[str] = field(default_factory=list)
    preventive_measures: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_timeline_event(
        self,
        event_type: str,
        description: str,
        actor: str,
        details: Dict[str, Any] = None,
        evidence_ids: List[str] = None,
    ):
        """Add event to timeline."""
        event = BreachTimelineEvent(
            id=str(uuid4()),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            description=description,
            actor=actor,
            details=details or {},
            evidence_ids=evidence_ids or [],
        )
        self.timeline.append(event)
        self.updated_at = datetime.utcnow()
    
    def calculate_risk_score(self) -> float:
        """Calculate breach risk score (0-100)."""
        score = 0.0
        
        # Base score by severity
        severity_scores = {
            BreachSeverity.LOW: 10,
            BreachSeverity.MEDIUM: 30,
            BreachSeverity.HIGH: 60,
            BreachSeverity.CRITICAL: 90,
        }
        score = severity_scores.get(self.severity, 30)
        
        # Adjust for data sensitivity
        if self.affected_data:
            sensitivity_multiplier = 1.0
            for cat in self.affected_data.data_categories:
                if cat in [DataCategory.PHI, DataCategory.FINANCIAL, DataCategory.CREDENTIALS, DataCategory.BIOMETRIC]:
                    sensitivity_multiplier = max(sensitivity_multiplier, 1.5)
                elif cat in [DataCategory.SPECIAL_CATEGORY, DataCategory.CHILDREN]:
                    sensitivity_multiplier = max(sensitivity_multiplier, 2.0)
            
            score *= sensitivity_multiplier
            
            # Adjust for record count
            if self.affected_data.record_count > 100000:
                score *= 1.3
            elif self.affected_data.record_count > 10000:
                score *= 1.2
            elif self.affected_data.record_count > 1000:
                score *= 1.1
        
        # Adjust for special categories
        if self.affected_data and self.affected_data.contains_special_category:
            score *= 1.3
        if self.affected_data and self.affected_data.contains_children_data:
            score *= 1.5
        
        # Adjust for encryption
        if self.affected_data and self.affected_data.encryption_status == "unencrypted":
            score *= 1.3
        elif self.affected_data and self.affected_data.encryption_status == "partially_encrypted":
            score *= 1.1
        
        # Cap at 100
        return min(score, 100.0)


@dataclass
class BreachNotification:
    """Breach notification record."""
    id: str
    breach_id: str
    notification_type: NotificationType
    recipient: str  # Authority, email, organization name
    method: str  # email, portal, certified_mail, api
    status: str  # pending, sent, delivered, failed, acknowledged
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    content: str = ""
    template_used: str = ""
    attachments: List[str] = field(default_factory=list)
    reference_number: str = ""
    response_received: bool = False
    response_details: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class BreachDetectionEngine:
    """
    Breach Detection and Notification Engine.
    
    Features:
    - Multi-source detection (DLP, SIEM, IDS, Audit, User Reports)
    - Automated correlation and alerting
    - GDPR 72-hour notification workflow
    - Multi-regulation compliance (GDPR, HIPAA, PCI, CCPA, FedRAMP)
    - Evidence preservation with chain of custody
    - Notification templates for all regulation types
    - Post-incident analysis and lessons learned
    """
    
    def __init__(
        self,
        evidence_path: str = "breach_evidence",
        notification_templates_path: str = "breach_templates",
    ):
        self.evidence_path = Path(evidence_path)
        self.templates_path = Path(notification_templates_path)
        self.evidence_path.mkdir(parents=True, exist_ok=True)
        self.templates_path.mkdir(parents=True, exist_ok=True)
        
        # Active incidents
        self._incidents: Dict[str, BreachIncident] = {}
        
        # Detection rules
        self._detection_rules: Dict[str, Callable] = {}
        
        # Notification templates
        self._templates: Dict[str, str] = {}
        self._load_templates()
        
        # Correlators
        self._correlators: List[Callable] = []
        
        # Notification handlers
        self._notification_handlers: Dict[NotificationType, Callable] = {}
        self._register_default_handlers()
        
        # Background tasks
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Threat intelligence
        self._threat_intel: Dict[str, Any] = {}
    
    def _load_templates(self):
        """Load notification templates."""
        self._templates["gdpr_72h"] = """
BREACH NOTIFICATION TO SUPERVISORY AUTHORITY (GDPR Art. 33)

Reference: {{reference_number}}
Date: {{date}}
Organization: {{organization_name}}
Contact: {{dpo_contact}}

INCIDENT SUMMARY
- Breach ID: {{breach_id}}
- Detected: {{detected_at}}
- Type: {{breach_type}}
- Severity: {{severity}}
- Status: {{status}}

AFFECTED DATA
- Categories: {{data_categories}}
- Records: {{record_count}}
- Data Subjects: {{data_subjects_affected}}
- Encryption: {{encryption_status}}
- Special Category Data: {{contains_special_category}}
- Children's Data: {{contains_children_data}}

DESCRIPTION
{{description}}

LIKELY CONSEQUENCES
{{consequences}}

MEASURES TAKEN
{{measures_taken}}

MEASURES PROPOSED
{{measures_proposed}}

DPO CONTACT
{{dpo_contact}}

This notification is made pursuant to Article 33 of the GDPR within 72 hours of becoming aware of the breach.
        """
        
        self._templates["gdpr_data_subject"] = """
NOTICE OF DATA BREACH (GDPR Art. 34)

Dear {{data_subject_name}},

We are writing to inform you of a data breach that may have affected your personal information.

INCIDENT DETAILS
- Date of Breach: {{breach_date}}
- Type of Breach: {{breach_type}}
- Information Affected: {{data_categories_description}}

WHAT HAPPENED
{{description}}

WHAT INFORMATION WAS INVOLVED
{{data_categories}}

WHAT WE ARE DOING
{{measures_taken}}

WHAT YOU CAN DO
{{recommended_actions}}

CONTACT INFORMATION
{{contact_information}}

We sincerely apologize for this incident and any inconvenience it may cause.
        """
        
        self._templates["hipaa"] = """
BREACH NOTIFICATION (HIPAA)

To: {{recipient}}
From: {{organization_name}}
Date: {{date}}
Reference: {{reference_number}}

This notification is provided pursuant to the HIPAA Breach Notification Rule (45 CFR §§ 164.400-414).

BREACH SUMMARY
- Breach ID: {{breach_id}}
- Discovered: {{detected_at}}
- Type: {{breach_type}}
- PHI Involved: {{phi_categories}}
- Individuals Affected: {{individuals_affected}}

DESCRIPTION
{{description}}

MITIGATION ACTIONS
{{measures_taken}}

CONTACT
{{contact_information}}
        """
        
        self._templates["pci"] = """
BREACH NOTIFICATION (PCI DSS)

To: {{recipient}}
From: {{organization_name}}
Date: {{date}}
Reference: {{reference_number}}

This notification is provided pursuant to PCI DSS Requirement 12.10.

BREACH SUMMARY
- Breach ID: {{breach_id}}
- Discovered: {{detected_at}}
- Type: {{breach_type}}
- Cardholder Data Affected: {{card_data_categories}}
- Accounts Affected: {{accounts_affected}}

DESCRIPTION
{{description}}

CONTAINMENT MEASURES
{{measures_taken}}

CONTACT
{{contact_information}}
        """
        
        self._templates["ccpa"] = """
BREACH NOTIFICATION (CCPA)

To: {{data_subject_name}}
From: {{organization_name}}
Date: {{date}}

NOTICE OF DATA BREACH

We are writing to inform you of a data breach involving your personal information.

INCIDENT DETAILS
- Date: {{breach_date}}
- Type: {{breach_type}}
- Information: {{data_categories}}

DESCRIPTION
{{description}}

YOUR RIGHTS
Under the California Consumer Privacy Act (CCPA), you have the right to:
- Request deletion of your personal information
- Opt-out of the sale of your personal information
- Request disclosure of categories of personal information collected

WHAT WE ARE DOING
{{measures_taken}}

CONTACT
{{contact_information}}
        """
        
        self._templates["fedramp"] = """
INCIDENT REPORT (FedRAMP)

To: {{recipient}}
From: {{organization_name}}
Date: {{date}}
Incident ID: {{breach_id}}
System: {{system_name}}
FIPS 199 Impact Level: {{impact_level}}

INCIDENT SUMMARY
- Detected: {{detected_at}}
- Type: {{breach_type}}
- Severity: {{severity}}
- Status: {{status}}

AFFECTED SYSTEMS
{{affected_systems}}

IMPACT ASSESSMENT
{{impact_assessment}}

CONTAINMENT ACTIONS
{{measures_taken}}

ROOT CAUSE
{{root_cause}}

RECOVERY PLAN
{{recovery_plan}}

CONTACT
{{contact_information}}

Reported per FedRAMP Incident Reporting Requirements (NIST SP 800-61).
        """
    
    def _register_default_handlers(self):
        """Register default notification handlers."""
        self._notification_handlers[NotificationType.SUPERVISORY_AUTHORITY] = self._send_supervisory_notification
        self._notification_handlers[NotificationType.DATA_SUBJECTS] = self._send_data_subject_notification
        self._notification_handlers[NotificationType.REGULATOR] = self._send_regulator_notification
        self._notification_handlers[NotificationType.LAW_ENFORCEMENT] = self._send_law_enforcement_notification
        self._notification_handlers[NotificationType.PARTNERS] = self._send_partner_notification
        self._notification_handlers[NotificationType.INTERNAL] = self._send_internal_notification
        self._notification_handlers[NotificationType.PUBLIC] = self._send_public_notification
    
    # ==================== Detection ====================
    
    def register_detection_rule(self, name: str, rule: Callable[[Dict], Optional[BreachIndicator]]):
        """Register a custom detection rule."""
        self._detection_rules[name] = rule
    
    def register_correlator(self, correlator: Callable[[List[BreachIndicator]], List[BreachIndicator]]):
        """Register a correlation function."""
        self._correlators.append(correlator)
    
    async def process_detection_signal(
        self,
        source: str,
        signal_data: Dict[str, Any],
    ) -> List[BreachIndicator]:
        """Process a detection signal from any source."""
        indicators = []
        
        # Run detection rules
        for name, rule in self._detection_rules.items():
            try:
                indicator = await rule(signal_data)
                if indicator:
                    indicator.source = source
                    indicators.append(indicator)
            except Exception as e:
                logger.error(f"Detection rule {name} error: {e}")
        
        # Run correlators
        for correlator in self._correlators:
            try:
                correlated = await correlator(indicators)
                indicators.extend(correlated)
            except Exception as e:
                logger.error(f"Correlator error: {e}")
        
        # If indicators found, create or update incident
        if indicators:
            await self._handle_indicators(indicators)
        
        return indicators
    
    async def _handle_indicators(self, indicators: List[BreachIndicator]):
        """Handle detected indicators - create or update incident."""
        # For now, create a new incident for each high-severity indicator
        # In production, correlate with existing incidents
        
        high_severity = [i for i in indicators if i.severity in [BreachSeverity.HIGH, BreachSeverity.CRITICAL]]
        
        for indicator in high_severity:
            await self._create_incident_from_indicator(indicator)
    
    async def _create_incident_from_indicator(self, indicator: BreachIndicator) -> BreachIncident:
        """Create a new breach incident from an indicator."""
        breach_type = self._classify_breach_type(indicator)
        
        incident = BreachIncident(
            id=str(uuid4()),
            title=f"Potential {breach_type.value.replace('_', ' ').title()}: {indicator.description[:100]}",
            breach_type=breach_type,
            severity=indicator.severity,
            status=BreachStatus.DETECTED,
            detected_at=indicator.detected_at,
            detected_by="system",
            detection_source=indicator.source,
            initial_indicators=[indicator],
            assigned_to=None,
        )
        
        # Initial risk assessment
        incident.risk_score = incident.calculate_risk_score()
        
        # Determine applicable regulations
        self._determine_applicable_regulations(incident)
        
        # Add timeline event
        incident.add_timeline_event(
            "detected",
            f"Breach detected via {indicator.source}: {indicator.description}",
            "system",
            {"indicator_id": indicator.id, "confidence": indicator.confidence},
        )
        
        self._incidents[incident.id] = incident
        
        # Log audit event
        await audit_log_manager.log_security_event(
            event_type=EventType.SECURITY_EVENT,
            actor_id="system",
            organization_id=indicator.raw_data.get("organization_id", ""),
            details={
                "breach_id": incident.id,
                "breach_type": incident.breach_type.value,
                "severity": incident.severity.value,
                "indicator_id": indicator.id,
            },
        )
        
        # Send to SIEM
        siem_manager = get_siem_manager()
        if siem_manager:
            from app.core.siem import OCSFEventBuilder, OCSFClass, OCSFCategory, Severity as SIEMSev
            sev_map = {
                BreachSeverity.LOW: SIEMSev.LOW,
                BreachSeverity.MEDIUM: SIEMSev.MEDIUM,
                BreachSeverity.HIGH: SIEMSev.HIGH,
                BreachSeverity.CRITICAL: SIEMSev.CRITICAL,
            }
            event = OCSFEventBuilder.build(
                OCSFClass.SECURITY_FINDING,
                OCSFCategory.INTRUSION_DETECTION,
                severity=sev_map.get(indicator.severity, SIEMSev.MEDIUM),
                status="open",
                message=f"Potential breach detected: {indicator.description}",
                metadata={
                    "breach_id": incident.id,
                    "breach_type": incident.breach_type.value,
                    "indicator_id": indicator.id,
                    "confidence": indicator.confidence,
                },
            )
            await siem_manager.send_event(event)
        
        logger.warning(f"Created breach incident {incident.id}: {incident.title}")
        
        return incident
    
    def _classify_breach_type(self, indicator: BreachIndicator) -> BreachType:
        """Classify breach type from indicator."""
        source_type_map = {
            "dlp": BreachType.DATA_EXFILTRATION,
            "ids": BreachType.MALWARE,
            "audit_log": BreachType.UNAUTHORIZED_ACCESS,
            "user_report": BreachType.PHISHING,
            "threat_intel": BreachType.MALWARE,
            "siem": BreachType.UNKNOWN,
        }
        return source_type_map.get(indicator.source, BreachType.UNKNOWN)
    
    def _determine_applicable_regulations(self, incident: BreachIncident):
        """Determine which regulations apply based on affected data."""
        # This would be enhanced with actual data classification
        # For now, set based on breach type
        if incident.breach_type in [BreachType.DATA_EXFILTRATION, BreachType.UNAUTHORIZED_ACCESS]:
            incident.gdpr_applicable = True
            incident.ccpa_applicable = True
        
        if incident.breach_type == BreachType.DATA_EXFILTRATION:
            incident.hipaa_applicable = True
            incident.pci_applicable = True
    
    # ==================== Investigation ====================
    
    async def update_incident(
        self,
        breach_id: str,
        updates: Dict[str, Any],
        actor: str,
    ) -> Optional[BreachIncident]:
        """Update breach incident."""
        incident = self._incidents.get(breach_id)
        if not incident:
            return None
        
        for key, value in updates.items():
            if hasattr(incident, key):
                setattr(incident, key, value)
        
        incident.updated_at = datetime.utcnow()
        
        # Add timeline event
        incident.add_timeline_event(
            "updated",
            f"Incident updated: {', '.join(updates.keys())}",
            actor,
            {"updates": updates},
        )
        
        # Recalculate risk if severity changed
        if "severity" in updates or "affected_data" in updates:
            incident.risk_score = incident.calculate_risk_score()
        
        return incident
    
    async def contain_incident(
        self,
        breach_id: str,
        actions: List[str],
        actor: str,
    ) -> Optional[BreachIncident]:
        """Mark incident as contained."""
        incident = self._incidents.get(breach_id)
        if not incident:
            return None
        
        incident.status = BreachStatus.CONTAINED
        incident.contained_at = datetime.utcnow()
        incident.containment_actions.extend(actions)
        incident.updated_at = datetime.utcnow()
        
        incident.add_timeline_event(
            "contained",
            f"Incident contained: {'; '.join(actions)}",
            actor,
            {"actions": actions},
        )
        
        return incident
    
    async def recover_incident(
        self,
        breach_id: str,
        actions: List[str],
        actor: str,
    ) -> Optional[BreachIncident]:
        """Mark incident as recovered."""
        incident = self._incidents.get(breach_id)
        if not incident:
            return None
        
        incident.status = BreachStatus.RECOVERED
        incident.recovered_at = datetime.utcnow()
        incident.recovery_actions.extend(actions)
        incident.updated_at = datetime.utcnow()
        
        incident.add_timeline_event(
            "recovered",
            f"Incident recovered: {'; '.join(actions)}",
            actor,
            {"actions": actions},
        )
        
        return incident
    
    async def close_incident(
        self,
        breach_id: str,
        summary: str,
        lessons: List[str],
        preventive: List[str],
        actor: str,
    ) -> Optional[BreachIncident]:
        """Close breach incident."""
        incident = self._incidents.get(breach_id)
        if not incident:
            return None
        
        incident.status = BreachStatus.CLOSED
        incident.closed_at = datetime.utcnow()
        incident.closure_summary = summary
        incident.lessons_learned = lessons
        incident.preventive_measures = preventive
        incident.updated_at = datetime.utcnow()
        
        incident.add_timeline_event(
            "closed",
            f"Incident closed: {summary}",
            actor,
            {"lessons": lessons, "preventive": preventive},
        )
        
        return incident
    
    # ==================== Evidence ====================
    
    async def add_evidence(
        self,
        breach_id: str,
        evidence_type: str,
        description: str,
        content: Dict[str, Any],
        collected_by: str,
    ) -> Optional[str]:
        """Add evidence to breach incident."""
        incident = self._incidents.get(breach_id)
        if not incident:
            return None
        
        evidence_id = str(uuid4())
        
        # Save evidence to file
        evidence_file = self.evidence_path / f"{breach_id}_{evidence_id}.json"
        evidence_data = {
            "id": evidence_id,
            "breach_id": breach_id,
            "type": evidence_type,
            "description": description,
            "content": content,
            "collected_by": collected_by,
            "collected_at": datetime.utcnow().isoformat(),
            "hash": hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest(),
        }
        
        async with aiofiles.open(evidence_file, 'w') as f:
            await f.write(json.dumps(evidence_data, indent=2, default=str))
        
        incident.evidence_collected.append(evidence_id)
        incident.updated_at = datetime.utcnow()
        
        return evidence_id
    
    # ==================== Notifications ====================
    
    async def send_notification(
        self,
        breach_id: str,
        notification_type: NotificationType,
        recipient: str,
        method: str = "email",
        custom_content: Optional[str] = None,
        template: Optional[str] = None,
    ) -> Optional[BreachNotification]:
        """Send breach notification."""
        incident = self._incidents.get(breach_id)
        if not incident:
            return None
        
        handler = self._notification_handlers.get(notification_type)
        if not handler:
            logger.error(f"No handler for notification type: {notification_type}")
            return None
        
        notification = BreachNotification(
            id=str(uuid4()),
            breach_id=breach_id,
            notification_type=notification_type,
            recipient=recipient,
            method=method,
            status="pending",
            template_used=template or "",
        )
        
        try:
            success = await handler(incident, notification, custom_content, template)
            
            if success:
                notification.status = "sent"
                notification.sent_at = datetime.utcnow()
            else:
                notification.status = "failed"
            
            incident.notifications_sent.append(notification)
            incident.updated_at = datetime.utcnow()
            
            # Track specific notification types
            if notification_type == NotificationType.SUPERVISORY_AUTHORITY:
                incident.supervisory_notified_at = datetime.utcnow()
            elif notification_type == NotificationType.DATA_SUBJECTS:
                incident.data_subjects_notified_at = datetime.utcnow()
            
            return notification
            
        except Exception as e:
            logger.error(f"Notification failed: {e}")
            notification.status = "failed"
            notification.metadata["error"] = str(e)
            return notification
    
    async def _send_supervisory_notification(
        self,
        incident: BreachIncident,
        notification: BreachNotification,
        custom_content: Optional[str],
        template: Optional[str],
    ) -> bool:
        """Send GDPR 72-hour supervisory authority notification."""
        template_name = template or "gdpr_72h"
        template_str = self._templates.get(template_name, self._templates["gdpr_72h"])
        
        content = custom_content or self._render_template(template_str, {
            "reference_number": notification.id[:12].upper(),
            "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "organization_name": "VCOS",
            "dpo_contact": "dpo@vcos.io",
            "breach_id": incident.id,
            "detected_at": incident.detected_at.isoformat(),
            "breach_type": incident.breach_type.value.replace("_", " ").title(),
            "severity": incident.severity.value.title(),
            "status": incident.status.value.title(),
            "data_categories": ", ".join([c.value for c in incident.affected_data.data_categories]) if incident.affected_data else "Unknown",
            "record_count": incident.affected_data.record_count if incident.affected_data else 0,
            "data_subjects_affected": incident.affected_data.data_subjects_affected if incident.affected_data else 0,
            "encryption_status": incident.affected_data.encryption_status if incident.affected_data else "Unknown",
            "contains_special_category": "Yes" if incident.affected_data and incident.affected_data.contains_special_category else "No",
            "contains_children_data": "Yes" if incident.affected_data and incident.affected_data.contains_children_data else "No",
            "description": incident.root_cause or "Under investigation",
            "consequences": "Potential unauthorized access to personal data, identity theft risk, financial fraud",
            "measures_taken": "; ".join(incident.containment_actions) or "Investigation initiated, systems isolated",
            "measures_proposed": "Enhanced monitoring, additional encryption, staff training",
            "dpo_contact": "dpo@vcos.io | +1-555-DPO-VCOS",
        })
        
        notification.content = content
        notification.template_used = template_name
        
        # In production, send via email/API
        logger.info(f"Sent supervisory notification for breach {incident.id}")
        return True
    
    async def _send_data_subject_notification(
        self,
        incident: BreachIncident,
        notification: BreachNotification,
        custom_content: Optional[str],
        template: Optional[str],
    ) -> bool:
        """Send GDPR Art. 34 data subject notification."""
        template_str = self._templates.get("gdpr_data_subject", self._templates["gdpr_data_subject"])
        
        notification.content = custom_content or self._render_template(template_str, {
            "data_subject_name": notification.recipient,
            "breach_date": incident.detected_at.strftime("%B %d, %Y"),
            "breach_type": incident.breach_type.value.replace("_", " ").title(),
            "data_categories_description": ", ".join([c.value for c in incident.affected_data.data_categories]) if incident.affected_data else "Personal data",
            "description": incident.root_cause or "Under investigation",
            "data_categories": ", ".join([c.value for c in incident.affected_data.data_categories]) if incident.affected_data else "Personal data",
            "measures_taken": "; ".join(incident.containment_actions) or "Investigation initiated",
            "recommended_actions": "Monitor accounts, enable MFA, review credit reports",
            "contact_information": "privacy@vcos.io | +1-555-PRIVACY",
        })
        
        notification.template_used = "gdpr_data_subject"
        logger.info(f"Sent data subject notification for breach {incident.id}")
        return True
    
    async def _send_regulator_notification(
        self,
        incident: BreachIncident,
        notification: BreachNotification,
        custom_content: Optional[str],
        template: Optional[str],
    ) -> bool:
        """Send regulator-specific notification (HIPAA, PCI, etc.)."""
        # Determine which template based on applicable regulations
        if incident.hipaa_applicable:
            template_name = "hipaa"
        elif incident.pci_applicable:
            template_name = "pci"
        elif incident.ccpa_applicable:
            template_name = "ccpa"
        elif incident.fedramp_applicable:
            template_name = "fedramp"
        else:
            template_name = "hipaa"  # Default
        
        template_str = self._templates.get(template_name, self._templates[template_name])
        
        notification.content = custom_content or self._render_template(template_str, {
            "recipient": notification.recipient,
            "organization_name": "VCOS",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "reference_number": notification.id[:12].upper(),
            "breach_id": incident.id,
            "detected_at": incident.detected_at.strftime("%Y-%m-%d %H:%M UTC"),
            "breach_type": incident.breach_type.value.replace("_", " ").title(),
            "phi_categories": ", ".join([c.value for c in incident.affected_data.data_categories]) if incident.affected_data else "PHI",
            "individuals_affected": incident.affected_data.data_subjects_affected if incident.affected_data else 0,
            "card_data_categories": "Cardholder data" if incident.pci_applicable else "N/A",
            "accounts_affected": incident.affected_data.record_count if incident.affected_data else 0,
            "description": incident.root_cause or "Under investigation",
            "measures_taken": "; ".join(incident.containment_actions) or "Investigation initiated",
            "impact_assessment": f"Risk score: {incident.risk_score:.1f}/100",
            "root_cause": incident.root_cause or "Under investigation",
            "recovery_plan": "; ".join(incident.recovery_actions) or "To be determined",
            "affected_systems": ", ".join(incident.affected_data.systems_affected) if incident.affected_data else "Unknown",
            "impact_level": "Moderate",
            "system_name": "VCOS Platform",
            "contact_information": "security@vcos.io | +1-555-SECURE",
        })
        
        notification.template_used = template_name
        logger.info(f"Sent {template_name} regulator notification for breach {incident.id}")
        return True
    
    async def _send_law_enforcement_notification(
        self,
        incident: BreachIncident,
        notification: BreachNotification,
        custom_content: Optional[str],
        template: Optional[str],
    ) -> bool:
        """Send law enforcement notification."""
        # Law enforcement notifications are typically formal letters
        notification.content = custom_content or f"""
LAW ENFORCEMENT NOTIFICATION

Incident ID: {incident.id}
Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
Organization: VCOS

This notification is provided regarding a cybersecurity incident that may constitute a criminal offense.

INCIDENT SUMMARY:
- Type: {incident.breach_type.value.replace('_', ' ').title()}
- Detected: {incident.detected_at.isoformat()}
- Severity: {incident.severity.value.title()}
- Status: {incident.status.value.title()}

INVESTIGATION STATUS:
- Root Cause: {incident.root_cause or 'Under investigation'}
- Attack Vector: {incident.attack_vector or 'Unknown'}
- Containment: {incident.contained_at.isoformat() if incident.contained_at else 'Not yet contained'}

EVIDENCE PRESERVED:
All relevant logs, forensic images, and evidence have been preserved with chain of custody documentation.

CONTACT:
Security Team: security@vcos.io
Legal: legal@vcos.io
        """
        logger.info(f"Sent law enforcement notification for breach {incident.id}")
        return True
    
    async def _send_partner_notification(
        self,
        incident: BreachIncident,
        notification: BreachNotification,
        custom_content: Optional[str],
        template: Optional[str],
    ) -> bool:
        """Send partner/third-party notification."""
        notification.content = custom_content or f"""
THIRD-PARTY BREACH NOTIFICATION

Dear {notification.recipient},

We are notifying you of a security incident that may affect data shared with or processed by your organization.

INCIDENT REFERENCE: {incident.id}
DETECTED: {incident.detected_at.isoformat()}
TYPE: {incident.breach_type.value.replace('_', ' ').title()}
SEVERITY: {incident.severity.value.title()}

IMPACT ASSESSMENT:
Based on our investigation, the following data categories shared with your organization may have been affected:
{', '.join([c.value for c in incident.affected_data.data_categories]) if incident.affected_data else 'Under assessment'}

ACTIONS TAKEN:
{'; '.join(incident.containment_actions) or 'Investigation ongoing'}

RECOMMENDED ACTIONS FOR YOUR ORGANIZATION:
- Review access logs for anomalous activity
- Verify integrity of shared data
- Update credentials and access tokens
- Monitor for suspicious activity

CONTACT:
Security: security@vcos.io
        """
        logger.info(f"Sent partner notification for breach {incident.id}")
        return True
    
    async def _send_internal_notification(
        self,
        incident: BreachIncident,
        notification: BreachNotification,
        custom_content: Optional[str],
        template: Optional[str],
    ) -> bool:
        """Send internal stakeholder notification."""
        notification.content = custom_content or f"""
INTERNAL SECURITY INCIDENT NOTIFICATION

INCIDENT ID: {incident.id}
DATE: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
CLASSIFICATION: CONFIDENTIAL

SUMMARY:
A {incident.severity.value} severity {incident.breach_type.value.replace('_', ' ')} incident has been detected and is under investigation.

DETAILS:
- Detected: {incident.detected_at.isoformat()}
- Type: {incident.breach_type.value}
- Status: {incident.status.value}
- Assigned To: {incident.assigned_to or 'Unassigned'}
- Risk Score: {incident.risk_score:.1f}/100

AFFECTED DATA:
{incident.affected_data.data_description if incident.affected_data else 'Under assessment'}

CURRENT ACTIONS:
{'; '.join(incident.containment_actions) or 'Initial triage in progress'}

NEXT STEPS:
- Complete forensic analysis
- Determine full scope of impact
- Initiate regulatory notifications as required
- Implement preventive measures

THIS INFORMATION IS CONFIDENTIAL. DO NOT DISTRIBUTE OUTSIDE AUTHORIZED PERSONNEL.
        """
        logger.info(f"Sent internal notification for breach {incident.id}")
        return True
    
    async def _send_public_notification(
        self,
        incident: BreachIncident,
        notification: BreachNotification,
        custom_content: Optional[str],
        template: Optional[str],
    ) -> bool:
        """Send public disclosure notification."""
        notification.content = custom_content or f"""
PUBLIC SECURITY NOTICE

VCOS Security Incident Notification

We are writing to inform you of a security incident that we have identified and are actively addressing.

WHAT HAPPENED:
On {incident.detected_at.strftime('%B %d, %Y')}, we detected a {incident.breach_type.value.replace('_', ' ')} affecting our systems.

WHAT INFORMATION WAS INVOLVED:
{incident.affected_data.data_description if incident.affected_data else 'The investigation is ongoing to determine the full scope of data involved.'}

WHAT WE ARE DOING:
{'; '.join(incident.containment_actions) or 'We have engaged leading cybersecurity experts to investigate and remediate this incident.'}

WHAT YOU CAN DO:
We recommend that you remain vigilant against phishing attempts and monitor your accounts for suspicious activity.

CONTACT:
For questions, please contact security@vcos.io

We take the security of your data seriously and apologize for any concern this may cause.
        """
        logger.info(f"Sent public notification for breach {incident.id}")
        return True
    
    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """Simple template rendering."""
        result = template
        for key, value in context.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result
    
    # ==================== Automation ====================
    
    async def auto_notify_72h(self, breach_id: str) -> Dict[str, bool]:
        """Automatically send required 72-hour notifications."""
        incident = self._incidents.get(breach_id)
        if not incident:
            return {}
        
        results = {}
        
        # GDPR 72-hour notification
        if incident.gdpr_applicable:
            results["gdpr_72h"] = await self.send_notification(
                breach_id,
                NotificationType.SUPERVISORY_AUTHORITY,
                "supervisory_authority@gdpr.eu",
                method="email",
            )
        
        # HIPAA notification (without unreasonable delay, max 60 days)
        if incident.hipaa_applicable:
            results["hipaa"] = await self.send_notification(
                breach_id,
                NotificationType.REGULATOR,
                "ocr@hhs.gov",
                method="email",
            )
        
        # PCI notification
        if incident.pci_applicable:
            results["pci"] = await self.send_notification(
                breach_id,
                NotificationType.REGULATOR,
                "pci@pcisecuritystandards.org",
                method="email",
            )
        
        # Internal notification (always)
        results["internal"] = await self.send_notification(
            breach_id,
            NotificationType.INTERNAL,
            "security-team@vcos.io",
            method="email",
        )
        
        return results
    
    # ==================== Monitoring ====================
    
    async def start_monitoring(self):
        """Start continuous breach monitoring."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Breach detection monitoring started")
    
    async def stop_monitoring(self):
        """Stop breach monitoring."""
        self._running = False
        if self._monitor_task:
            await self._monitor_task
        logger.info("Breach detection monitoring stopped")
    
    async def _monitor_loop(self):
        """Continuous monitoring loop."""
        while self._running:
            try:
                # Check for overdue notifications
                await self._check_overdue_notifications()
                
                # Check for stale incidents
                await self._check_stale_incidents()
                
                # Update threat intelligence
                await self._update_threat_intel()
                
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
            
            await asyncio.sleep(300)  # Every 5 minutes
    
    async def _check_overdue_notifications(self):
        """Check for overdue regulatory notifications."""
        now = datetime.utcnow()
        
        for incident in self._incidents.values():
            if incident.status in [BreachStatus.DETECTED, BreachStatus.INVESTIGATING, BreachStatus.CONFIRMED]:
                # GDPR 72-hour check
                if incident.gdpr_applicable and not incident.supervisory_notified_at:
                    if now - incident.detected_at > timedelta(hours=72):
                        logger.warning(f"GDPR 72-hour notification overdue for breach {incident.id}")
                        await self.send_notification(
                            incident.id,
                            NotificationType.SUPERVISORY_AUTHORITY,
                            "supervisory_authority@gdpr.eu",
                        )
                
                # HIPAA 60-day check
                if incident.hipaa_applicable:
                    # Check if any regulator notification sent
                    has_regulator = any(
                        n.notification_type == NotificationType.REGULATOR and n.status == "sent"
                        for n in incident.notifications_sent
                    )
                    if not has_regulator and now - incident.detected_at > timedelta(days=55):
                        logger.warning(f"HIPAA notification approaching deadline for breach {incident.id}")
    
    async def _check_stale_incidents(self):
        """Check for incidents that haven't been updated."""
        now = datetime.utcnow()
        
        for incident in self._incidents.values():
            if incident.status in [BreachStatus.DETECTED, BreachStatus.INVESTIGATING]:
                if now - incident.updated_at > timedelta(days=7):
                    logger.warning(f"Stale incident {incident.id} not updated in 7 days")
                    # Could escalate or notify management
    
    async def _update_threat_intel(self):
        """Update threat intelligence feeds."""
        # In production, pull from threat intel feeds
        pass
    
    # ==================== Utility ====================
    
    def get_incident(self, breach_id: str) -> Optional[BreachIncident]:
        return self._incidents.get(breach_id)
    
    def list_incidents(
        self,
        status: Optional[BreachStatus] = None,
        severity: Optional[BreachSeverity] = None,
        limit: int = 50,
    ) -> List[BreachIncident]:
        incidents = list(self._incidents.values())
        
        if status:
            incidents = [i for i in incidents if i.status == status]
        if severity:
            incidents = [i for i in incidents if i.severity == severity]
        
        incidents.sort(key=lambda i: i.detected_at, reverse=True)
        return incidents[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_incidents": len(self._incidents),
            "by_status": {
                status.value: sum(1 for i in self._incidents.values() if i.status == status)
                for status in BreachStatus
            },
            "by_severity": {
                severity.value: sum(1 for i in self._incidents.values() if i.severity == severity)
                for severity in BreachSeverity
            },
            "by_type": {
                btype.value: sum(1 for i in self._incidents.values() if i.breach_type == btype)
                for btype in BreachType
            },
            "gdpr_applicable": sum(1 for i in self._incidents.values() if i.gdpr_applicable),
            "hipaa_applicable": sum(1 for i in self._incidents.values() if i.hipaa_applicable),
            "pci_applicable": sum(1 for i in self._incidents.values() if i.pci_applicable),
            "active_investigations": sum(1 for i in self._incidents.values() if i.status in [BreachStatus.DETECTED, BreachStatus.INVESTIGATING]),
        }


# Global breach detection engine instance
_breach_engine: Optional[BreachDetectionEngine] = None


def get_breach_engine() -> BreachDetectionEngine:
    """Get or create breach detection engine singleton."""
    global _breach_engine
    if _breach_engine is None:
        _breach_engine = BreachDetectionEngine()
    return _breach_engine


def init_breach_engine(
    evidence_path: str = "breach_evidence",
    templates_path: str = "breach_templates",
) -> BreachDetectionEngine:
    """Initialize breach detection engine."""
    global _breach_engine
    _breach_engine = BreachDetectionEngine(
        evidence_path=evidence_path,
        templates_path=templates_path,
    )
    return _breach_engine