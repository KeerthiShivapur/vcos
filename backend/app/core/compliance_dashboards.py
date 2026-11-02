"""
FedRAMP/HIPAA/ISO27001/SOC2/GDPR Compliance Dashboards.

Provides:
- Automated compliance posture assessment
- Real-time compliance dashboards
- Evidence collection and management
- Control implementation tracking
- Audit readiness scoring
- Automated report generation for multiple frameworks
- Continuous compliance monitoring
- Gap analysis and remediation tracking
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

from sqlalchemy import Column, String, Text, JSON, DateTime, Index, ForeignKey, Boolean, Integer, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

logger = logging.getLogger(__name__)


# ==================== Framework Enums ====================

class ComplianceFramework(str, Enum):
    """Supported compliance frameworks."""
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    GDPR = "gdpr"
    HIPAA = "hipaa"
    FEDRAMP = "fedramp"
    PCI_DSS = "pci_dss"
    NIST_CSF = "nist_csf"
    NIST_800_53 = "nist_800_53"
    CIS_CONTROLS = "cis_controls"
    CUSTOM = "custom"


class ControlStatus(str, Enum):
    """Control implementation status."""
    NOT_APPLICABLE = "not_applicable"
    NOT_IMPLEMENTED = "not_implemented"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    IMPLEMENTED = "implemented"
    AUTOMATED = "automated"
    CONTINUOUS = "continuous"


class EvidenceType(str, Enum):
    """Types of compliance evidence."""
    DOCUMENT = "document"
    SCREENSHOT = "screenshot"
    LOG = "log"
    CONFIGURATION = "configuration"
    SCAN_RESULT = "scan_result"
    TEST_RESULT = "test_result"
    POLICY = "policy"
    PROCEDURE = "procedure"
    ATTESTATION = "attestation"
    CERTIFICATE = "certificate"
    REPORT = "report"
    METRICS = "metrics"


class AuditReadiness(str, Enum):
    """Audit readiness levels."""
    NOT_READY = "not_ready"
    PREPARING = "preparing"
    READY = "ready"
    AUDIT_COMPLETE = "audit_complete"


class RemediationStatus(str, Enum):
    """Remediation tracking status."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    CLOSED = "closed"
    ACCEPTED_RISK = "accepted_risk"


# ==================== Data Structures ====================

@dataclass
class ComplianceControl:
    """Individual compliance control."""
    id: str
    framework: ComplianceFramework
    control_id: str                      # e.g., "CC6.1", "A.9.1", "164.308(a)(1)"
    title: str
    description: str
    category: str                        # e.g., "Access Control", "Encryption", "Incident Response"
    implementation_guidance: str = ""
    testing_procedure: str = ""
    status: ControlStatus = ControlStatus.NOT_IMPLEMENTED
    evidence: List[str] = field(default_factory=list)  # Evidence IDs
    automated: bool = False
    last_tested: Optional[datetime] = None
    next_test_due: Optional[datetime] = None
    owner_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    related_controls: List[str] = field(default_factory=list)  # Control IDs
    control_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceEvidence:
    """Compliance evidence artifact."""
    id: str
    control_id: str
    framework: ComplianceFramework
    evidence_type: EvidenceType
    title: str
    description: str
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    content: Optional[str] = None
    collected_at: datetime = field(default_factory=datetime.utcnow)
    collected_by: str = ""
    expires_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    evidence_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceGap:
    """Identified compliance gap."""
    id: str
    control_id: str
    framework: ComplianceFramework
    title: str
    description: str
    severity: str  # critical, high, medium, low
    status: RemediationStatus = RemediationStatus.OPEN
    identified_at: datetime = field(default_factory=datetime.utcnow)
    identified_by: str = ""
    assigned_to: Optional[str] = None
    due_date: Optional[datetime] = None
    remediation_plan: str = ""
    remediation_notes: str = ""
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    gap_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceAssessment:
    """Compliance assessment result."""
    id: str
    framework: ComplianceFramework
    organization_id: str
    assessed_at: datetime
    assessed_by: str
    overall_score: float  # 0-100
    control_scores: Dict[str, float] = field(default_factory=dict)  # control_id -> score
    passed_controls: int = 0
    failed_controls: int = 0
    not_applicable_controls: int = 0
    gaps: List[str] = field(default_factory=list)  # Gap IDs
    evidence_collected: int = 0
    audit_readiness: AuditReadiness = AuditReadiness.NOT_READY
    next_assessment_due: Optional[datetime] = None
    assessment_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceDashboard:
    """Compliance dashboard view."""
    organization_id: str
    framework: ComplianceFramework
    last_assessment: Optional[ComplianceAssessment] = None
    overall_score: float = 0.0
    controls_by_status: Dict[str, int] = field(default_factory=dict)
    gaps_by_severity: Dict[str, int] = field(default_factory=dict)
    evidence_status: Dict[str, int] = field(default_factory=dict)
    upcoming_tests: List[Dict[str, Any]] = field(default_factory=list)
    open_gaps: List[ComplianceGap] = field(default_factory=list)
    remediation_timeline: List[Dict[str, Any]] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.utcnow)


# ==================== Framework Definitions ====================

class FrameworkRegistry:
    """Registry of compliance frameworks and their controls."""
    
    SOC2_CONTROLS = {
        "CC6.1": {
            "title": "Logical Access Controls",
            "description": "The entity implements logical access security software, infrastructure, and architectures to protect its information assets.",
            "category": "Access Control",
            "implementation": "Implement role-based access control (RBAC), multi-factor authentication (MFA), and privileged access management (PAM).",
            "testing": "Review access control lists, verify MFA enforcement, test privilege escalation prevention.",
        },
        "CC6.2": {
            "title": "Authentication and Authorization",
            "description": "The entity authenticates and authorizes users and devices before granting access to systems and data.",
            "category": "Access Control",
            "implementation": "Deploy MFA, SSO, and attribute-based access control (ABAC). Implement session management and device trust.",
            "testing": "Test authentication flows, verify authorization decisions, review session timeouts.",
        },
        "CC6.3": {
            "title": "Network Segmentation",
            "description": "The entity restricts network access to protect sensitive systems and data.",
            "category": "Network Security",
            "implementation": "Implement network segmentation, zero-trust architecture, and micro-segmentation.",
            "testing": "Verify network segmentation, test inter-segment communication controls.",
        },
        "CC6.4": {
            "title": "Encryption in Transit",
            "description": "The entity encrypts data in transit to protect confidentiality and integrity.",
            "category": "Encryption",
            "implementation": "Enforce TLS 1.2+ for all communications, implement mTLS for service-to-service communication.",
            "testing": "Scan for TLS versions, verify certificate validity, test mTLS enforcement.",
        },
        "CC6.5": {
            "title": "Encryption at Rest",
            "description": "The entity encrypts data at rest to protect confidentiality.",
            "category": "Encryption",
            "implementation": "Enable AES-256 encryption for databases, object storage, and backups. Use HSM for key management.",
            "testing": "Verify encryption configuration, test key rotation, verify HSM integration.",
        },
        "CC6.6": {
            "title": "Audit Logging",
            "description": "The entity implements audit logging for security-relevant events.",
            "category": "Monitoring",
            "implementation": "Implement centralized logging with immutable audit trails, Merkle tree verification, and SIEM integration.",
            "testing": "Verify log completeness, test log integrity, verify SIEM alerts.",
        },
        "CC6.7": {
            "title": "Data Transmission Protection",
            "description": "The entity protects data during transmission over public networks.",
            "category": "Network Security",
            "implementation": "Implement TLS everywhere, VPN for remote access, and secure file transfer protocols.",
            "testing": "Verify TLS everywhere, test VPN connections, scan for cleartext protocols.",
        },
        "CC7.1": {
            "title": "System Monitoring",
            "description": "The entity monitors system components for anomalies and security events.",
            "category": "Monitoring",
            "implementation": "Deploy continuous monitoring with real-time alerts, anomaly detection, and automated response.",
            "testing": "Verify monitoring coverage, test alert accuracy, review false positive rates.",
        },
        "CC7.2": {
            "title": "Incident Detection",
            "description": "The entity detects security incidents through monitoring and analysis.",
            "category": "Incident Response",
            "implementation": "Deploy SIEM with correlation rules, threat intelligence integration, and automated triage.",
            "testing": "Test detection rules, verify alert enrichment, measure detection time.",
        },
    }
    
    ISO27001_CONTROLS = {
        "A.5.1": {
            "title": "Information Security Policies",
            "description": "A set of policies for information security is defined, approved, published, and communicated.",
            "category": "Governance",
        },
        "A.6.1": {
            "title": "Internal Organization",
            "description": "Internal organization for information security management is established.",
            "category": "Governance",
        },
        "A.8.1": {
            "title": "Asset Management",
            "description": "Assets are identified and managed throughout their lifecycle.",
            "category": "Asset Management",
        },
        "A.9.1": {
            "title": "Access Control Policy",
            "description": "Access control policy is established, documented, and reviewed.",
            "category": "Access Control",
        },
        "A.12.1": {
            "title": "Operational Procedures",
            "description": "Operating procedures are documented and made available to all users.",
            "category": "Operations",
        },
    }
    
    GDPR_CONTROLS = {
        "Art.5": {
            "title": "Lawfulness, Fairness, Transparency",
            "description": "Personal data processed lawfully, fairly, and transparently.",
            "category": "Data Protection Principles",
        },
        "Art.6": {
            "title": "Lawful Basis for Processing",
            "description": "Processing has a valid legal basis.",
            "category": "Lawful Basis",
        },
        "Art.7": {
            "title": "Consent Conditions",
            "description": "Consent is freely given, specific, informed, and unambiguous.",
            "category": "Consent",
        },
        "Art.15": {
            "title": "Right of Access",
            "description": "Data subjects can access their personal data.",
            "category": "Data Subject Rights",
        },
        "Art.17": {
            "title": "Right to Erasure",
            "description": "Data subjects can request deletion of personal data.",
            "category": "Data Subject Rights",
        },
        "Art.20": {
            "title": "Right to Data Portability",
            "description": "Data subjects can receive their data in a structured, commonly used format.",
            "category": "Data Subject Rights",
        },
        "Art.25": {
            "title": "Data Protection by Design and Default",
            "description": "Implement appropriate technical and organizational measures.",
            "category": "Data Protection by Design",
        },
        "Art.32": {
            "title": "Security of Processing",
            "description": "Implement appropriate technical and organizational measures for security.",
            "category": "Security",
        },
        "Art.33": {
            "title": "Breach Notification",
            "description": "Notify supervisory authority of data breaches within 72 hours.",
            "category": "Breach Notification",
        },
    }
    
    HIPAA_CONTROLS = {
        "164.308(a)(1)": {
            "title": "Security Officer Assignment",
            "description": "Assign a security official responsible for developing and implementing security policies.",
            "category": "Administrative Safeguards",
        },
        "164.308(a)(3)": {
            "title": "Workforce Security",
            "description": "Implement policies for authorization, supervision, and termination procedures.",
            "category": "Administrative Safeguards",
        },
        "164.308(a)(4)": {
            "title": "Information Access Management",
            "description": "Implement policies for authorizing access to ePHI.",
            "category": "Administrative Safeguards",
        },
        "164.308(a)(5)": {
            "title": "Security Awareness Training",
            "description": "Implement security awareness and training program for all workforce members.",
            "category": "Administrative Safeguards",
        },
        "164.310(a)(1)": {
            "title": "Facility Access Controls",
            "description": "Implement policies to limit physical access to electronic information systems.",
            "category": "Physical Safeguards",
        },
        "164.312(a)(1)": {
            "title": "Access Control",
            "description": "Implement technical policies for electronic information systems to allow access only to authorized persons.",
            "category": "Technical Safeguards",
        },
        "164.312(a)(2)": {
            "title": "Unique User Identification",
            "description": "Assign a unique name/number for identifying and tracking user identity.",
            "category": "Technical Safeguards",
        },
        "164.312(b)": {
            "title": "Audit Controls",
            "description": "Implement hardware, software, and procedural mechanisms to record and examine activity.",
            "category": "Technical Safeguards",
        },
        "164.312(c)(1)": {
            "title": "Integrity Controls",
            "description": "Implement electronic mechanisms to corroborate that ePHI has not been altered or destroyed.",
            "category": "Technical Safeguards",
        },
        "164.312(e)(1)": {
            "title": "Transmission Security",
            "description": "Implement technical security measures to guard against unauthorized access to ePHI during transmission.",
            "category": "Technical Safeguards",
        },
    }
    
    FEDRAMP_CONTROLS = {
        "AC-1": {
            "title": "Access Control Policy and Procedures",
            "description": "The organization develops, documents, and disseminates an access control policy.",
            "category": "Access Control",
        },
        "AC-2": {
            "title": "Account Management",
            "description": "The organization manages information system accounts.",
            "category": "Access Control",
        },
        "AC-3": {
            "title": "Access Enforcement",
            "description": "The information system enforces approved authorizations for logical access.",
            "category": "Access Control",
        },
        "AC-4": {
            "title": "Information Flow Enforcement",
            "description": "The information system enforces approved authorizations for controlling the flow of information.",
            "category": "Access Control",
        },
        "AU-2": {
            "title": "Audit Events",
            "description": "The organization determines which events require auditing.",
            "category": "Audit and Accountability",
        },
        "AU-6": {
            "title": "Audit Review, Analysis, and Reporting",
            "description": "The organization reviews and analyzes audit records.",
            "category": "Audit and Accountability",
        },
        "SC-8": {
            "title": "Transmission Confidentiality and Integrity",
            "description": "The information system protects the confidentiality and integrity of transmitted information.",
            "category": "System and Communications Protection",
        },
        "SC-13": {
            "title": "Cryptographic Protection",
            "description": "The information system implements cryptographic mechanisms to protect information.",
            "category": "System and Communications Protection",
        },
    }
    
    @classmethod
    def get_framework_controls(cls, framework: ComplianceFramework) -> Dict[str, Dict[str, Any]]:
        """Get controls for a framework."""
        mapping = {
            ComplianceFramework.SOC2: cls.SOC2_CONTROLS,
            ComplianceFramework.ISO27001: cls.ISO27001_CONTROLS,
            ComplianceFramework.GDPR: cls.GDPR_CONTROLS,
            ComplianceFramework.HIPAA: cls.HIPAA_CONTROLS,
            ComplianceFramework.FEDRAMP: cls.FEDRAMP_CONTROLS,
        }
        return mapping.get(framework, {})
    
    @classmethod
    def get_all_frameworks(cls) -> List[ComplianceFramework]:
        """Get all supported frameworks."""
        return [
            ComplianceFramework.SOC2,
            ComplianceFramework.ISO27001,
            ComplianceFramework.GDPR,
            ComplianceFramework.HIPAA,
            ComplianceFramework.FEDRAMP,
        ]


# ==================== Compliance Engine ====================

class ComplianceEngine:
    """
    Central compliance management engine.
    
    Provides:
    - Multi-framework compliance management
    - Automated control assessment
    - Evidence collection and validation
    - Gap analysis and remediation tracking
    - Compliance dashboards and reporting
    - Continuous compliance monitoring
    """
    
    def __init__(
        self,
        session: AsyncSession = None,
        rtbf_engine: Any = None,
        encryption_engine: Any = None,
        audit_logger: Any = None,
    ):
        self.session = session
        self.rtbf = rtbf_engine
        self.encryption = encryption_engine
        self.audit = audit_logger
        
        self._controls: Dict[str, ComplianceControl] = {}
        self._evidence: Dict[str, ComplianceEvidence] = {}
        self._gaps: Dict[str, ComplianceGap] = {}
        self._assessments: Dict[str, ComplianceAssessment] = {}
        self._dashboards: Dict[str, ComplianceDashboard] = {}
        
        # Initialize controls for all frameworks
        self._initialize_controls()
    
    def _initialize_controls(self):
        """Initialize controls for all frameworks."""
        for framework in FrameworkRegistry.get_all_frameworks():
            controls = FrameworkRegistry.get_framework_controls(framework)
            for control_id, control_data in controls.items():
                control = ComplianceControl(
                    id=f"{framework.value}:{control_id}",
                    framework=framework,
                    control_id=control_id,
                    title=control_data["title"],
                    description=control_data["description"],
                    category=control_data.get("category", "General"),
                    implementation_guidance=control_data.get("implementation", ""),
                    testing_procedure=control_data.get("testing", ""),
                )
                self._controls[control.id] = control
    
    # ==================== Control Management ====================
    
    def get_control(self, control_id: str) -> Optional[ComplianceControl]:
        """Get control by ID."""
        return self._controls.get(control_id)
    
    def list_controls(
        self,
        framework: ComplianceFramework = None,
        category: str = None,
        status: ControlStatus = None,
    ) -> List[ComplianceControl]:
        """List controls with filters."""
        controls = list(self._controls.values())
        
        if framework:
            controls = [c for c in controls if c.framework == framework]
        if category:
            controls = [c for c in controls if c.category == category]
        if status:
            controls = [c for c in controls if c.status == status]
        
        return controls
    
    def update_control_status(
        self,
        control_id: str,
        status: ControlStatus,
        evidence_ids: List[str] = None,
        notes: str = "",
    ):
        """Update control implementation status."""
        control = self._controls.get(control_id)
        if not control:
            raise ValueError(f"Control not found: {control_id}")
        
        control.status = status
        if evidence_ids:
            control.evidence = evidence_ids
        control.control_metadata["last_status_update"] = datetime.utcnow().isoformat()
        control.control_metadata["status_notes"] = notes
    
    # ==================== Evidence Management ====================
    
    async def add_evidence(
        self,
        control_id: str,
        framework: ComplianceFramework,
        evidence_type: EvidenceType,
        title: str,
        description: str,
        content: str = None,
        file_path: str = None,
        collected_by: str = "",
        expires_in_days: int = 365,
    ) -> ComplianceEvidence:
        """Add evidence for a control."""
        evidence = ComplianceEvidence(
            id=str(uuid4()),
            control_id=control_id,
            framework=framework,
            evidence_type=evidence_type,
            title=title,
            description=description,
            content=content,
            file_path=file_path,
            collected_by=collected_by,
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
        )
        
        # Calculate file hash if file provided
        if file_path:
            evidence.file_hash = self._calculate_file_hash(file_path)
        
        self._evidence[evidence.id] = evidence
        
        # Link evidence to control
        control = self._controls.get(f"{framework.value}:{control_id}")
        if control and evidence.id not in control.evidence:
            control.evidence.append(evidence.id)
        
        # Log audit event
        # (would integrate with audit logger)
        
        return evidence
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def get_evidence(self, evidence_id: str) -> Optional[ComplianceEvidence]:
        """Get evidence by ID."""
        return self._evidence.get(evidence_id)
    
    def list_evidence(
        self,
        control_id: str = None,
        framework: ComplianceFramework = None,
        evidence_type: EvidenceType = None,
    ) -> List[ComplianceEvidence]:
        """List evidence with filters."""
        evidence = list(self._evidence.values())
        
        if control_id:
            evidence = [e for e in evidence if e.control_id == control_id]
        if framework:
            evidence = [e for e in evidence if e.framework == framework]
        if evidence_type:
            evidence = [e for e in evidence if e.evidence_type == evidence_type]
        
        return evidence
    
    # ==================== Gap Analysis ====================
    
    async def perform_gap_analysis(
        self,
        framework: ComplianceFramework,
        organization_id: str,
    ) -> List[ComplianceGap]:
        """Perform automated gap analysis for framework."""
        controls = self.list_controls(framework=framework)
        gaps = []
        
        for control in controls:
            # Check if control has sufficient evidence
            evidence_count = len(control.evidence)
            is_implemented = control.status in (ControlStatus.IMPLEMENTED, ControlStatus.AUTOMATED, ControlStatus.CONTINUOUS)
            
            if not is_implemented:
                # Determine severity based on control criticality
                severity = self._calculate_severity(control)
                
                gap = ComplianceGap(
                    id=str(uuid4()),
                    control_id=control.id,
                    framework=framework,
                    title=f"Gap: {control.title}",
                    description=f"Control {control.control_id} ({control.title}) is not implemented. {control.implementation_guidance}",
                    severity=severity,
                    remediation_plan=control.implementation_guidance,
                )
                gaps.append(gap)
                self._gaps[gap.id] = gap
            
            elif evidence_count == 0 and control.status != ControlStatus.NOT_APPLICABLE:
                # Implemented but no evidence
                gap = ComplianceGap(
                    id=str(uuid4()),
                    control_id=control.id,
                    framework=framework,
                    title=f"Missing Evidence: {control.title}",
                    description=f"Control {control.control_id} is marked as implemented but has no supporting evidence.",
                    severity="medium",
                    remediation_plan=f"Collect and attach evidence for control {control.control_id}.",
                )
                gaps.append(gap)
                self._gaps[gap.id] = gap
        
        return gaps
    
    def _calculate_severity(self, control: ComplianceControl) -> str:
        """Calculate gap severity based on control criticality."""
        critical_categories = ["Access Control", "Encryption", "Incident Response", "Data Protection"]
        high_categories = ["Monitoring", "Network Security", "Vulnerability Management"]
        
        if control.category in critical_categories:
            return "critical"
        elif control.category in high_categories:
            return "high"
        return "medium"
    
    def get_gap(self, gap_id: str) -> Optional[ComplianceGap]:
        """Get gap by ID."""
        return self._gaps.get(gap_id)
    
    def update_gap_status(
        self,
        gap_id: str,
        status: RemediationStatus,
        notes: str = "",
        assigned_to: str = None,
    ):
        """Update gap remediation status."""
        gap = self._gaps.get(gap_id)
        if not gap:
            raise ValueError(f"Gap not found: {gap_id}")
        
        gap.status = status
        gap.gap_metadata["remediation_notes"] = notes
        if assigned_to:
            gap.assigned_to = assigned_to
        if status == RemediationStatus.VERIFIED:
            gap.verified_at = datetime.utcnow()
            gap.verified_by = assigned_to
    
    # ==================== Assessment ====================
    
    async def perform_assessment(
        self,
        framework: ComplianceFramework,
        organization_id: str,
        assessed_by: str,
    ) -> ComplianceAssessment:
        """Perform comprehensive compliance assessment."""
        controls = self.list_controls(framework=framework)
        
        control_scores = {}
        passed = 0
        failed = 0
        not_applicable = 0
        
        for control in controls:
            score = self._calculate_control_score(control)
            control_scores[control.id] = score
            
            if control.status == ControlStatus.NOT_APPLICABLE:
                not_applicable += 1
            elif score >= 0.7:
                passed += 1
            else:
                failed += 1
        
        total_applicable = len(controls) - not_applicable
        overall_score = (passed / total_applicable * 100) if total_applicable > 0 else 100
        
        # Determine audit readiness
        if overall_score >= 90 and failed == 0:
            readiness = AuditReadiness.READY
        elif overall_score >= 70:
            readiness = AuditReadiness.PREPARING
        else:
            readiness = AuditReadiness.NOT_READY
        
        # Get gaps for this framework
        gaps = [g.id for g in self._gaps.values() if g.framework == framework]
        
        assessment = ComplianceAssessment(
            id=str(uuid4()),
            framework=framework,
            organization_id=organization_id,
            assessed_at=datetime.utcnow(),
            assessed_by=assessed_by,
            overall_score=overall_score,
            control_scores=control_scores,
            passed_controls=passed,
            failed_controls=failed,
            not_applicable_controls=not_applicable,
            gaps=gaps,
            evidence_collected=len(self._evidence),
            audit_readiness=readiness,
            next_assessment_due=datetime.utcnow() + timedelta(days=90),
        )
        
        self._assessments[assessment.id] = assessment
        self._dashboards[f"{organization_id}:{framework.value}"] = self._build_dashboard(
            organization_id, framework, assessment
        )
        
        return assessment
    
    def _calculate_control_score(self, control: ComplianceControl) -> float:
        """Calculate control implementation score (0-1)."""
        if control.status == ControlStatus.NOT_APPLICABLE:
            return 1.0
        
        if control.status in (ControlStatus.AUTOMATED, ControlStatus.CONTINUOUS):
            base = 1.0
        elif control.status == ControlStatus.IMPLEMENTED:
            base = 0.8
        elif control.status == ControlStatus.PARTIALLY_IMPLEMENTED:
            base = 0.5
        else:
            base = 0.0
        
        # Bonus for evidence
        evidence_bonus = min(len(control.evidence) * 0.05, 0.2)
        
        # Bonus for automation
        automation_bonus = 0.1 if control.automated else 0.0
        
        return min(base + evidence_bonus + automation_bonus, 1.0)
    
    def _build_dashboard(
        self,
        organization_id: str,
        framework: ComplianceFramework,
        assessment: ComplianceAssessment,
    ) -> ComplianceDashboard:
        """Build compliance dashboard."""
        controls = self.list_controls(framework=framework)
        
        status_counts = defaultdict(int)
        for control in controls:
            status_counts[control.status.value] += 1
        
        gaps = [g for g in self._gaps.values() if g.framework == framework]
        severity_counts = defaultdict(int)
        for gap in gaps:
            severity_counts[gap.severity] += 1
        
        evidence_status = defaultdict(int)
        for evidence in self._evidence.values():
            if evidence.framework == framework:
                evidence_status[evidence.evidence_type.value] += 1
        
        # Upcoming tests
        upcoming_tests = []
        for control in controls:
            if control.next_test_due:
                upcoming_tests.append({
                    "control_id": control.id,
                    "title": control.title,
                    "due_date": control.next_test_due.isoformat(),
                })
        
        return ComplianceDashboard(
            organization_id=organization_id,
            framework=framework,
            last_assessment=assessment,
            overall_score=assessment.overall_score,
            controls_by_status=dict(status_counts),
            gaps_by_severity=dict(severity_counts),
            evidence_status=dict(evidence_status),
            upcoming_tests=sorted(upcoming_tests, key=lambda x: x["due_date"])[:10],
            open_gaps=[g for g in self._gaps.values() if g.framework == framework and g.status in (RemediationStatus.OPEN, RemediationStatus.IN_PROGRESS)],
        )
    
    def get_dashboard(
        self,
        organization_id: str,
        framework: ComplianceFramework,
    ) -> Optional[ComplianceDashboard]:
        """Get compliance dashboard."""
        return self._dashboards.get(f"{organization_id}:{framework.value}")
    
    # ==================== Reporting ====================
    
    async def generate_compliance_report(
        self,
        framework: ComplianceFramework,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
        generated_by: str,
    ) -> Dict[str, Any]:
        """Generate comprehensive compliance report."""
        assessment = await self.perform_assessment(framework, organization_id, "system")
        
        report = {
            "report_id": str(uuid4()),
            "framework": framework.value,
            "organization_id": organization_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "generated_by": generated_by,
            "executive_summary": {
                "overall_score": assessment.overall_score,
                "audit_readiness": assessment.audit_readiness.value,
                "total_controls": len(self.list_controls(framework=framework)),
                "passed": assessment.passed_controls,
                "failed": assessment.failed_controls,
                "open_gaps": len(assessment.gaps),
            },
            "control_details": [
                {
                    "control_id": c.control_id,
                    "title": c.title,
                    "category": c.category,
                    "status": c.status.value,
                    "score": self._calculate_control_score(c),
                    "evidence_count": len(c.evidence),
                    "automated": c.automated,
                }
                for c in self.list_controls(framework=framework)
            ],
            "gap_analysis": [
                {
                    "gap_id": g.id,
                    "control_id": g.control_id,
                    "title": g.title,
                    "severity": g.severity,
                    "status": g.status.value,
                    "assigned_to": g.assigned_to,
                    "due_date": g.due_date.isoformat() if g.due_date else None,
                }
                for g in self._gaps.values() if g.framework == framework
            ],
            "evidence_summary": {
                "total_pieces": len([e for e in self._evidence.values() if e.framework == framework]),
                "by_type": defaultdict(int),
            },
        }
        
        # Add evidence type counts
        for evidence in self._evidence.values():
            if evidence.framework == framework:
                report["evidence_summary"]["by_type"][evidence.evidence_type.value] += 1
        
        return report
    
    # ==================== Continuous Monitoring ====================
    
    async def run_continuous_checks(self):
        """Run continuous compliance checks."""
        for framework in FrameworkRegistry.get_all_frameworks():
            await self._check_framework_controls(framework)
    
    async def _check_framework_controls(self, framework: ComplianceFramework):
        """Check controls for framework."""
        controls = self.list_controls(framework=framework)
        
        for control in controls:
            if control.automated:
                # Run automated check
                result = await self._run_automated_check(control)
                if not result["passed"]:
                    # Create or update gap
                    await self._handle_failed_check(control, result)
    
    async def _run_automated_check(self, control: ComplianceControl) -> Dict[str, Any]:
        """Run automated compliance check."""
        # In production, integrate with actual security controls
        # For now, return mock result
        return {
            "passed": True,
            "details": "Automated check passed",
        }
    
    async def _handle_failed_check(self, control: ComplianceControl, result: Dict[str, Any]):
        """Handle failed automated check."""
        # Find or create gap
        existing_gap = None
        for gap in self._gaps.values():
            if gap.control_id == control.id and gap.status != RemediationStatus.CLOSED:
                existing_gap = gap
                break
        
        if not existing_gap:
            gap = ComplianceGap(
                id=str(uuid4()),
                control_id=control.id,
                framework=control.framework,
                title=f"Automated Check Failed: {control.title}",
                description=result.get("details", "Automated compliance check failed"),
                severity="high",
            )
            self._gaps[gap.id] = gap
        else:
            # Update existing gap
            existing_gap.status = RemediationStatus.OPEN
            existing_gap.gap_metadata["remediation_notes"] = f"Automated check failed: {result.get('details')}"


# ==================== Database Models ====================

class ComplianceControlModel(Base, TimestampMixin):
    """Database model for compliance controls."""
    
    __tablename__ = "compliance_controls"
    __table_args__ = (
        Index("ix_compliance_controls_framework", "framework"),
        Index("ix_compliance_controls_status", "status"),
        UniqueConstraint("framework", "control_id", name="uq_compliance_controls_framework_id"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    framework: Mapped[str] = mapped_column(SQLEnum(ComplianceFramework), nullable=False)
    control_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(128))
    implementation_guidance: Mapped[str] = mapped_column(Text)
    testing_procedure: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(SQLEnum(ControlStatus), default=ControlStatus.NOT_IMPLEMENTED)
    evidence: Mapped[List[str]] = mapped_column(JSON, default=list)
    automated: Mapped[bool] = mapped_column(Boolean, default=False)
    last_tested: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_test_due: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    owner_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey("users.id", ondelete="SET NULL"))
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    related_controls: Mapped[List[str]] = mapped_column(JSON, default=list)
    control_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class ComplianceEvidenceModel(Base, TimestampMixin):
    """Database model for compliance evidence."""
    
    __tablename__ = "compliance_evidence"
    __table_args__ = (
        Index("ix_compliance_evidence_control", "control_id"),
        Index("ix_compliance_evidence_framework", "framework"),
        Index("ix_compliance_evidence_type", "evidence_type"),
        Index("ix_compliance_evidence_expires", "expires_at"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    control_id: Mapped[str] = mapped_column(String(128), nullable=False)
    framework: Mapped[str] = mapped_column(SQLEnum(ComplianceFramework), nullable=False)
    evidence_type: Mapped[str] = mapped_column(SQLEnum(EvidenceType), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text)
    file_path: Mapped[Optional[str]] = mapped_column(String(512))
    file_hash: Mapped[Optional[str]] = mapped_column(String(64))
    content: Mapped[Optional[str]] = mapped_column(Text)
    collected_by: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    evidence_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class ComplianceGapModel(Base, TimestampMixin):
    """Database model for compliance gaps."""
    
    __tablename__ = "compliance_gaps"
    __table_args__ = (
        Index("ix_compliance_gaps_control", "control_id"),
        Index("ix_compliance_gaps_framework", "framework"),
        Index("ix_compliance_gaps_status", "status"),
        Index("ix_compliance_gaps_severity", "severity"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    control_id: Mapped[str] = mapped_column(String(128), nullable=False)
    framework: Mapped[str] = mapped_column(SQLEnum(ComplianceFramework), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(SQLEnum(RemediationStatus), default=RemediationStatus.OPEN)
    identified_by: Mapped[str] = mapped_column(String(32))
    assigned_to: Mapped[Optional[str]] = mapped_column(String(32))
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    remediation_plan: Mapped[str] = mapped_column(Text)
    remediation_notes: Mapped[str] = mapped_column(Text)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[Optional[str]] = mapped_column(String(32))
    gap_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class ComplianceAssessmentModel(Base, TimestampMixin):
    """Database model for compliance assessments."""
    
    __tablename__ = "compliance_assessments"
    __table_args__ = (
        Index("ix_compliance_assessments_org", "organization_id"),
        Index("ix_compliance_assessments_framework", "framework"),
        Index("ix_compliance_assessments_date", "assessed_at"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    framework: Mapped[str] = mapped_column(SQLEnum(ComplianceFramework), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assessed_by: Mapped[str] = mapped_column(String(32))
    overall_score: Mapped[float] = mapped_column(default=0.0)
    control_scores: Mapped[Dict[str, float]] = mapped_column(JSON, default=dict)
    passed_controls: Mapped[int] = mapped_column(Integer, default=0)
    failed_controls: Mapped[int] = mapped_column(Integer, default=0)
    not_applicable_controls: Mapped[int] = mapped_column(Integer, default=0)
    gaps: Mapped[List[str]] = mapped_column(JSON, default=list)
    evidence_collected: Mapped[int] = mapped_column(Integer, default=0)
    audit_readiness: Mapped[str] = mapped_column(SQLEnum(AuditReadiness), default=AuditReadiness.NOT_READY)
    next_assessment_due: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    assessment_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class RemediationActionModel(Base, TimestampMixin):
    """Database model for remediation actions."""
    
    __tablename__ = "remediation_actions"
    __table_args__ = (
        Index("ix_remediation_actions_gap", "gap_id"),
        Index("ix_remediation_actions_status", "status"),
        Index("ix_remediation_actions_assignee", "assigned_to"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    gap_id: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(Text)
    assigned_to: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(SQLEnum(RemediationStatus), default=RemediationStatus.OPEN)
    evidence_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text)
    verified_by: Mapped[Optional[str]] = mapped_column(String(32))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ==================== Global Engine ====================

_compliance_engine: Optional[ComplianceEngine] = None


def get_compliance_engine(session: AsyncSession = None) -> ComplianceEngine:
    """Get global compliance engine."""
    global _compliance_engine
    if _compliance_engine is None:
        _compliance_engine = ComplianceEngine(session)
    return _compliance_engine


async def init_compliance_engine(session: AsyncSession = None) -> ComplianceEngine:
    """Initialize compliance engine."""
    global _compliance_engine
    _compliance_engine = ComplianceEngine(session)
    return _compliance_engine


# ==================== Convenience Functions ====================

async def assess_compliance(
    framework: ComplianceFramework,
    organization_id: str,
    assessed_by: str,
    session: AsyncSession = None,
) -> ComplianceAssessment:
    """Perform compliance assessment."""
    engine = get_compliance_engine(session)
    return await engine.perform_assessment(framework, organization_id, assessed_by)


async def get_compliance_dashboard(
    organization_id: str,
    framework: ComplianceFramework,
    session: AsyncSession = None,
) -> Optional[ComplianceDashboard]:
    """Get compliance dashboard."""
    engine = get_compliance_engine(session)
    return engine.get_dashboard(organization_id, framework)


async def generate_compliance_report(
    framework: ComplianceFramework,
    organization_id: str,
    period_start: datetime,
    period_end: datetime,
    generated_by: str,
    session: AsyncSession = None,
) -> Dict[str, Any]:
    """Generate compliance report."""
    engine = get_compliance_engine(session)
    return await engine.generate_compliance_report(
        framework, organization_id, period_start, period_end, generated_by
    )


async def run_gap_analysis(
    framework: ComplianceFramework,
    organization_id: str,
    session: AsyncSession = None,
) -> List[ComplianceGap]:
    """Run gap analysis for framework."""
    engine = get_compliance_engine(session)
    return await engine.perform_gap_analysis(framework, organization_id)


async def add_compliance_evidence(
    control_id: str,
    framework: ComplianceFramework,
    evidence_type: EvidenceType,
    title: str,
    description: str,
    content: str = None,
    file_path: str = None,
    collected_by: str = "",
    session: AsyncSession = None,
) -> ComplianceEvidence:
    """Add compliance evidence."""
    engine = get_compliance_engine(session)
    return await engine.add_evidence(
        control_id, framework, evidence_type, title, description,
        content, file_path, collected_by
    )


async def update_gap_remediation(
    gap_id: str,
    status: RemediationStatus,
    notes: str = "",
    assigned_to: str = None,
    session: AsyncSession = None,
):
    """Update gap remediation status."""
    engine = get_compliance_engine(session)
    engine.update_gap_status(gap_id, status, notes, assigned_to)


async def run_continuous_compliance_checks(session: AsyncSession = None):
    """Run continuous compliance checks."""
    engine = get_compliance_engine(session)
    await engine.run_continuous_checks()


# ==================== Global Engine ====================

_compliance_engine: Optional[ComplianceEngine] = None


def get_compliance_engine(session: AsyncSession = None) -> ComplianceEngine:
    """Get global compliance engine."""
    global _compliance_engine
    if _compliance_engine is None:
        _compliance_engine = ComplianceEngine(session)
    return _compliance_engine


async def init_compliance_engine(session: AsyncSession = None) -> ComplianceEngine:
    """Initialize compliance engine."""
    global _compliance_engine
    _compliance_engine = ComplianceEngine(session)
    return _compliance_engine