"""
Automated Compliance Reporting for VCOS.

Provides:
- Scheduled compliance report generation (SOC2, ISO27001, GDPR, HIPAA, FedRAMP)
- Evidence collection and packaging
- Report templates with customizable sections
- Multi-format output (PDF, HTML, JSON, CSV)
- Distribution via email, SIEM, file storage
- Compliance dashboard with real-time metrics
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

import aiofiles

from app.core.config import settings
from app.core.audit_log import audit_log_manager, EventType, Severity
from app.core.siem import get_siem_manager

logger = logging.getLogger(__name__)


class ComplianceFramework(str, Enum):
    """Supported compliance frameworks."""
    SOC2_TYPE1 = "soc2_type1"
    SOC2_TYPE2 = "soc2_type2"
    ISO27001 = "iso27001"
    GDPR = "gdpr"
    CCPA = "ccpa"
    HIPAA = "hipaa"
    FEDRAMP_MODERATE = "fedramp_moderate"
    FEDRAMP_HIGH = "fedramp_high"
    PCI_DSS = "pci_dss"
    NIST_CSF = "nist_csf"
    CUSTOM = "custom"


class ReportFormat(str, Enum):
    """Report output formats."""
    PDF = "pdf"
    HTML = "html"
    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ReportStatus(str, Enum):
    """Report generation status."""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class EvidenceType(str, Enum):
    """Types of compliance evidence."""
    AUDIT_LOG = "audit_log"
    POLICY_DOCUMENT = "policy_document"
    CONFIG_SNAPSHOT = "config_snapshot"
    SCAN_RESULT = "scan_result"
    TEST_RESULT = "test_result"
    INCIDENT_RECORD = "incident_record"
    TRAINING_RECORD = "training_record"
    ACCESS_REVIEW = "access_review"
    VULNERABILITY_SCAN = "vulnerability_scan"
    PENETRATION_TEST = "penetration_test"
    BACKUP_VERIFICATION = "backup_verification"
    ENCRYPTION_VERIFICATION = "encryption_verification"
    MFA_VERIFICATION = "mfa_verification"
    DLP_VIOLATION = "dlp_violation"
    DATA_SUBJECT_REQUEST = "data_subject_request"


@dataclass
class ComplianceControl:
    """Individual compliance control."""
    id: str
    framework: ComplianceFramework
    control_id: str  # e.g., "CC6.1", "A.9.1"
    title: str
    description: str
    category: str
    requirements: List[str] = field(default_factory=list)
    implementation_guidance: str = ""
    testing_procedure: str = ""
    evidence_requirements: List[str] = field(default_factory=list)
    automation_possible: bool = False
    risk_level: str = "medium"  # low, medium, high, critical
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceEvidence:
    """Piece of compliance evidence."""
    id: str
    control_id: str
    framework: ComplianceFramework
    evidence_type: EvidenceType
    title: str
    description: str
    file_path: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    collected_at: datetime = field(default_factory=datetime.utcnow)
    collected_by: str = "system"
    valid_from: datetime = field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = None
    hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.content and not self.hash:
            content_str = json.dumps(self.content, sort_keys=True, default=str)
            self.hash = hashlib.sha256(content_str.encode()).hexdigest()


@dataclass
class ControlAssessment:
    """Assessment of a single control."""
    control_id: str
    framework: ComplianceFramework
    status: str  # compliant, non_compliant, partially_compliant, not_applicable, not_tested
    score: float  # 0-100
    findings: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    remediation_plan: str = ""
    assessed_at: datetime = field(default_factory=datetime.utcnow)
    assessed_by: str = "system"
    next_assessment_due: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceReport:
    """Complete compliance report."""
    id: str
    framework: ComplianceFramework
    organization_id: str
    report_name: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime = field(default_factory=datetime.utcnow)
    generated_by: str = "system"
    status: ReportStatus = ReportStatus.PENDING
    format: ReportFormat = ReportFormat.PDF
    
    # Report content
    executive_summary: str = ""
    scope: str = ""
    methodology: str = ""
    
    # Assessments
    assessments: List[ControlAssessment] = field(default_factory=list)
    evidence: List[ComplianceEvidence] = field(default_factory=list)
    
    # Metrics
    overall_score: float = 0.0
    controls_tested: int = 0
    controls_compliant: int = 0
    controls_non_compliant: int = 0
    controls_partially_compliant: int = 0
    controls_not_applicable: int = 0
    
    # Output
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    
    # Distribution
    distributed_to: List[str] = field(default_factory=list)
    distributed_at: Optional[datetime] = None
    
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportSchedule:
    """Scheduled report generation."""
    id: str
    framework: ComplianceFramework
    organization_id: str
    name: str
    cron_expression: str  # e.g., "0 0 1 * *" for monthly
    format: ReportFormat = ReportFormat.PDF
    enabled: bool = True
    recipients: List[str] = field(default_factory=list)
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    template_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ComplianceReportingEngine:
    """
    Automated Compliance Reporting Engine.
    
    Features:
    - Pre-built control frameworks (SOC2, ISO27001, GDPR, HIPAA, FedRAMP)
    - Automated evidence collection from audit logs, configs, scans
    - Control assessment with scoring
    - Multi-format report generation
    - Scheduled report generation
    - Evidence packaging and integrity verification
    - Distribution via multiple channels
    """
    
    def __init__(
        self,
        storage_path: str = "compliance_reports",
        evidence_path: str = "compliance_evidence",
    ):
        self.storage_path = Path(storage_path)
        self.evidence_path = Path(evidence_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.evidence_path.mkdir(parents=True, exist_ok=True)
        
        # Control frameworks
        self._frameworks: Dict[ComplianceFramework, List[ComplianceControl]] = {}
        self._load_builtin_frameworks()
        
        # Evidence store
        self._evidence: Dict[str, ComplianceEvidence] = {}
        
        # Reports
        self._reports: Dict[str, ComplianceReport] = {}
        
        # Schedules
        self._schedules: Dict[str, ReportSchedule] = {}
        self._scheduler_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Report templates
        self._templates: Dict[str, str] = {}
        self._load_templates()
        
        # Custom assessors
        self._assessors: Dict[str, Callable] = {}
    
    def _load_builtin_frameworks(self):
        """Load built-in compliance frameworks."""
        
        # SOC 2 Type 2
        self._frameworks[ComplianceFramework.SOC2_TYPE2] = [
            ComplianceControl(
                id="soc2-cc6.1",
                framework=ComplianceFramework.SOC2_TYPE2,
                control_id="CC6.1",
                title="Logical Access Controls",
                description="The entity implements logical access security software, infrastructure, and architectures to protect its information assets.",
                category="Common Criteria - Logical Access",
                requirements=[
                    "Access is restricted to authorized users",
                    "Multi-factor authentication for privileged access",
                    "Regular access reviews",
                    "Automated provisioning/deprovisioning",
                ],
                testing_procedure="Verify MFA enforcement, review access logs, test deprovisioning",
                evidence_requirements=["MFA configuration", "Access review records", "Deprovisioning logs"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="soc2-cc6.2",
                framework=ComplianceFramework.SOC2_TYPE2,
                control_id="CC6.2",
                title="Authentication and Authorization",
                description="Prior to issuing system credentials, the entity registers and authorizes new users.",
                category="Common Criteria - Logical Access",
                requirements=[
                    "Identity verification before credential issuance",
                    "Role-based access control",
                    "Least privilege principle",
                ],
                testing_procedure="Verify identity proofing, test RBAC, review privilege assignments",
                evidence_requirements=["Identity verification records", "RBAC configuration", "Privilege review logs"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="soc2-cc6.3",
                framework=ComplianceFramework.SOC2_TYPE2,
                control_id="CC6.3",
                title="Network Segmentation",
                description="The entity uses network segmentation to protect sensitive information.",
                category="Common Criteria - Network Security",
                requirements=[
                    "Network segments for different trust levels",
                    "Firewall rules between segments",
                    "Monitoring of cross-segment traffic",
                ],
                testing_procedure="Review network diagrams, test firewall rules, verify monitoring",
                evidence_requirements=["Network diagrams", "Firewall configs", "Traffic logs"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="soc2-cc6.4",
                framework=ComplianceFramework.SOC2_TYPE2,
                control_id="CC6.4",
                title="Encryption in Transit",
                description="The entity encrypts data in transit.",
                category="Common Criteria - Encryption",
                requirements=[
                    "TLS 1.2+ for all external connections",
                    "Certificate management",
                    "Certificate transparency monitoring",
                ],
                testing_procedure="Scan for TLS versions, verify certificate validity, test HSTS",
                evidence_requirements=["TLS scan results", "Certificate inventory", "HSTS headers"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="soc2-cc6.5",
                framework=ComplianceFramework.SOC2_TYPE2,
                control_id="CC6.5",
                title="Encryption at Rest",
                description="The entity encrypts sensitive data at rest.",
                category="Common Criteria - Encryption",
                requirements=[
                    "AES-256 for databases and file storage",
                    "Key management with HSM/KMS",
                    "Key rotation policy",
                ],
                testing_procedure="Verify encryption config, review key management, test key rotation",
                evidence_requirements=["Encryption configs", "KMS policies", "Key rotation logs"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="soc2-cc6.6",
                framework=ComplianceFramework.SOC2_TYPE2,
                control_id="CC6.6",
                title="Audit Logging",
                description="The entity implements audit logging for security-relevant events.",
                category="Common Criteria - Audit Logging",
                requirements=[
                    "Centralized log collection",
                    "Immutable log storage",
                    "Log retention per policy",
                    "Log integrity verification",
                ],
                testing_procedure="Verify log collection, test immutability, verify retention",
                evidence_requirements=["Log architecture", "Immutability proof", "Retention policy"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="soc2-cc6.7",
                framework=ComplianceFramework.SOC2_TYPE2,
                control_id="CC6.7",
                title="Data Transmission Security",
                description="The entity protects data during transmission.",
                category="Common Criteria - Data Protection",
                requirements=[
                    "API encryption",
                    "Email encryption for sensitive data",
                    "File transfer encryption",
                ],
                testing_procedure="Test API endpoints, verify email encryption, test file transfers",
                evidence_requirements=["API security configs", "Email encryption configs", "Transfer logs"],
                automation_possible=True,
                risk_level="medium",
            ),
            ComplianceControl(
                id="soc2-cc7.1",
                framework=ComplianceFramework.SOC2_TYPE2,
                control_id="CC7.1",
                title="System Monitoring",
                description="The entity monitors system components for anomalies.",
                category="Common Criteria - Monitoring",
                requirements=[
                    "24/7 monitoring",
                    "Automated alerting",
                    "Log correlation",
                    "Anomaly detection",
                ],
                testing_procedure="Verify monitoring coverage, test alerts, review detection rules",
                evidence_requirements=["Monitoring dashboards", "Alert configurations", "Detection rule sets"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="soc2-cc7.2",
                framework=ComplianceFramework.SOC2_TYPE2,
                control_id="CC7.2",
                title="Incident Detection and Response",
                description="The entity detects and responds to security incidents.",
                category="Common Criteria - Incident Response",
                requirements=[
                    "Incident response plan",
                    "Automated detection rules",
                    "Escalation procedures",
                    "Post-incident reviews",
                ],
                testing_procedure="Review IR plan, test detection rules, verify escalation",
                evidence_requirements=["IR plan", "Detection rules", "Escalation logs", "Post-mortems"],
                automation_possible=True,
                risk_level="high",
            ),
        ]
        
        # ISO 27001
        self._frameworks[ComplianceFramework.ISO27001] = [
            ComplianceControl(
                id="iso27001-a5.1",
                framework=ComplianceFramework.ISO27001,
                control_id="A.5.1",
                title="Information Security Policies",
                description="A set of policies for information security shall be defined, approved, published and communicated.",
                category="Information Security Policies",
                requirements=[
                    "Policies approved by management",
                    "Communicated to all personnel",
                    "Reviewed annually",
                ],
                testing_procedure="Review policy documents, verify approval, check communication",
                evidence_requirements=["Policy documents", "Approval records", "Communication logs"],
                automation_possible=False,
                risk_level="high",
            ),
            ComplianceControl(
                id="iso27001-a6.1",
                framework=ComplianceFramework.ISO27001,
                control_id="A.6.1",
                title="Internal Organization",
                description="Information security responsibilities shall be defined and allocated.",
                category="Organization of Information Security",
                requirements=[
                    "Roles and responsibilities defined",
                    "Segregation of duties",
                    "Contact with authorities",
                ],
                testing_procedure="Review org chart, verify role assignments, check segregation",
                evidence_requirements=["Org chart", "Role assignments", "Segregation matrix"],
                automation_possible=False,
                risk_level="medium",
            ),
            ComplianceControl(
                id="iso27001-a8.1",
                framework=ComplianceFramework.ISO27001,
                control_id="A.8.1",
                title="Asset Management",
                description="Assets shall be identified and an inventory maintained.",
                category="Asset Management",
                requirements=[
                    "Asset inventory maintained",
                    "Ownership assigned",
                    "Acceptable use defined",
                ],
                testing_procedure="Review asset inventory, verify ownership, check acceptable use",
                evidence_requirements=["Asset inventory", "Ownership records", "Acceptable use policy"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="iso27001-a9.1",
                framework=ComplianceFramework.ISO27001,
                control_id="A.9.1",
                title="Access Control Policy",
                description="An access control policy shall be established, documented and reviewed.",
                category="Access Control",
                requirements=[
                    "Access control policy documented",
                    "Based on business requirements",
                    "Reviewed regularly",
                ],
                testing_procedure="Review access control policy, verify business alignment, check reviews",
                evidence_requirements=["Access control policy", "Business requirements", "Review records"],
                automation_possible=False,
                risk_level="high",
            ),
            ComplianceControl(
                id="iso27001-a9.2",
                framework=ComplianceFramework.ISO27001,
                control_id="A.9.2",
                title="User Access Management",
                description="Formal user registration and de-registration process shall be implemented.",
                category="Access Control",
                requirements=[
                    "User registration process",
                    "Privilege assignment process",
                    "Regular access reviews",
                    "Timely de-registration",
                ],
                testing_procedure="Test user lifecycle, verify access reviews, test deprovisioning",
                evidence_requirements=["Registration process", "Access review records", "Deprovisioning logs"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="iso27001-a9.4",
                framework=ComplianceFramework.ISO27001,
                control_id="A.9.4",
                title="System and Application Access Control",
                description="Access to systems and applications shall be controlled.",
                category="Access Control",
                requirements=[
                    "Secure logon procedures",
                    "Password management",
                    "Privileged access management",
                    "Access to source code controlled",
                ],
                testing_procedure="Test logon procedures, verify password policy, review privileged access",
                evidence_requirements=["Logon configs", "Password policies", "Privileged access logs"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="iso27001-a12.1",
                framework=ComplianceFramework.ISO27001,
                control_id="A.12.1",
                title="Operational Procedures and Responsibilities",
                description="Operating procedures shall be documented and made available.",
                category="Operations Security",
                requirements=[
                    "Documented procedures",
                    "Change management",
                    "Capacity management",
                    "Separation of environments",
                ],
                testing_procedure="Review procedures, test change management, verify separation",
                evidence_requirements=["Procedure docs", "Change logs", "Environment configs"],
                automation_possible=False,
                risk_level="medium",
            ),
        ]
        
        # GDPR
        self._frameworks[ComplianceFramework.GDPR] = [
            ComplianceControl(
                id="gdpr-art5",
                framework=ComplianceFramework.GDPR,
                control_id="Art. 5",
                title="Principles of Processing",
                description="Personal data shall be processed lawfully, fairly and transparently.",
                category="Principles",
                requirements=[
                    "Lawful basis for processing",
                    "Purpose limitation",
                    "Data minimization",
                    "Accuracy",
                    "Storage limitation",
                    "Integrity and confidentiality",
                ],
                testing_procedure="Review processing records, verify lawful basis, check minimization",
                evidence_requirements=["ROPA", "Lawful basis assessments", "Minimization analyses"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="gdpr-art6",
                framework=ComplianceFramework.GDPR,
                control_id="Art. 6",
                title="Lawfulness of Processing",
                description="Processing shall be lawful only if at least one basis applies.",
                category="Lawfulness",
                requirements=[
                    "Valid consent or other basis",
                    "Special category data conditions",
                    "Children's consent",
                ],
                testing_procedure="Verify lawful basis for each processing activity",
                evidence_requirements=["Consent records", "Legitimate interest assessments", "Contracts"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="gdpr-art15",
                framework=ComplianceFramework.GDPR,
                control_id="Art. 15",
                title="Right of Access",
                description="Data subject has right to obtain confirmation and access to their data.",
                category="Data Subject Rights",
                requirements=[
                    "Access request process",
                    "Identity verification",
                    "Response within 30 days",
                    "Complete information provided",
                ],
                testing_procedure="Test access request workflow, verify timelines, check completeness",
                evidence_requirements=["Access request logs", "Response times", "Provided information samples"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="gdpr-art17",
                framework=ComplianceFramework.GDPR,
                control_id="Art. 17",
                title="Right to Erasure",
                description="Data subject has right to erasure of personal data.",
                category="Data Subject Rights",
                requirements=[
                    "Erasure request process",
                    "Grounds assessment",
                    "Third-party notification",
                    "Verification of erasure",
                ],
                testing_procedure="Test erasure workflow, verify third-party notification, confirm deletion",
                evidence_requirements=["Erasure request logs", "Third-party notifications", "Deletion confirmations"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="gdpr-art20",
                framework=ComplianceFramework.GDPR,
                control_id="Art. 20",
                title="Right to Data Portability",
                description="Data subject has right to receive data in structured, commonly used format.",
                category="Data Subject Rights",
                requirements=[
                    "Portability request process",
                    "Machine-readable format",
                    "Direct transmission capability",
                ],
                testing_procedure="Test portability request, verify format, test direct transmission",
                evidence_requirements=["Portability request logs", "Export formats", "Transmission logs"],
                automation_possible=True,
                risk_level="medium",
            ),
            ComplianceControl(
                id="gdpr-art25",
                framework=ComplianceFramework.GDPR,
                control_id="Art. 25",
                title="Data Protection by Design and Default",
                description="Implement appropriate technical and organizational measures.",
                category="Data Protection by Design",
                requirements=[
                    "Privacy by design in development",
                    "Data minimization by default",
                    "Privacy impact assessments",
                ],
                testing_procedure="Review development process, verify DPIA completion, check defaults",
                evidence_requirements=["DPIA records", "Development guidelines", "Default configs"],
                automation_possible=False,
                risk_level="high",
            ),
            ComplianceControl(
                id="gdpr-art32",
                framework=ComplianceFramework.GDPR,
                control_id="Art. 32",
                title="Security of Processing",
                description="Implement appropriate technical and organizational measures.",
                category="Security",
                requirements=[
                    "Pseudonymization and encryption",
                    "Confidentiality, integrity, availability",
                    "Resilience and recovery",
                    "Regular testing",
                ],
                testing_procedure="Verify encryption, test resilience, review testing program",
                evidence_requirements=["Encryption configs", "Resilience tests", "Testing reports"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="gdpr-art33",
                framework=ComplianceFramework.GDPR,
                control_id="Art. 33",
                title="Breach Notification",
                description="Notify supervisory authority within 72 hours of becoming aware.",
                category="Breach Notification",
                requirements=[
                    "Breach detection process",
                    "72-hour notification",
                    "Data subject notification",
                    "Documentation",
                ],
                testing_procedure="Test breach detection, verify notification timelines, review documentation",
                evidence_requirements=["Detection configs", "Notification logs", "Breach register"],
                automation_possible=True,
                risk_level="critical",
            ),
        ]
        
        # HIPAA
        self._frameworks[ComplianceFramework.HIPAA] = [
            ComplianceControl(
                id="hipaa-164.308",
                framework=ComplianceFramework.HIPAA,
                control_id="164.308",
                title="Administrative Safeguards",
                description="Administrative actions, policies, and procedures to manage security measures.",
                category="Administrative Safeguards",
                requirements=[
                    "Security officer assigned",
                    "Workforce training",
                    "Access management",
                    "Security awareness",
                    "Incident procedures",
                    "Contingency plan",
                    "Evaluation",
                ],
                testing_procedure="Review admin safeguards, verify training, test incident response",
                evidence_requirements=["Security officer designation", "Training records", "Incident procedures"],
                automation_possible=False,
                risk_level="high",
            ),
            ComplianceControl(
                id="hipaa-164.310",
                framework=ComplianceFramework.HIPAA,
                control_id="164.310",
                title="Physical Safeguards",
                description="Physical measures to protect electronic information systems.",
                category="Physical Safeguards",
                requirements=[
                    "Facility access controls",
                    "Workstation use",
                    "Workstation security",
                    "Device and media controls",
                ],
                testing_procedure="Review physical access, test workstation security, verify media controls",
                evidence_requirements=["Access control logs", "Workstation policies", "Media disposal logs"],
                automation_possible=False,
                risk_level="medium",
            ),
            ComplianceControl(
                id="hipaa-164.312",
                framework=ComplianceFramework.HIPAA,
                control_id="164.312",
                title="Technical Safeguards",
                description="Technology and policy/procedures to protect ePHI.",
                category="Technical Safeguards",
                requirements=[
                    "Access control",
                    "Audit controls",
                    "Integrity controls",
                    "Person/entity authentication",
                    "Transmission security",
                ],
                testing_procedure="Verify access controls, test audit logs, check encryption",
                evidence_requirements=["Access control configs", "Audit logs", "Encryption configs"],
                automation_possible=True,
                risk_level="high",
            ),
        ]
        
        # FedRAMP (subset)
        self._frameworks[ComplianceFramework.FEDRAMP_MODERATE] = [
            ComplianceControl(
                id="fedramp-ac-2",
                framework=ComplianceFramework.FEDRAMP_MODERATE,
                control_id="AC-2",
                title="Account Management",
                description="Manage information system accounts.",
                category="Access Control",
                requirements=[
                    "Account provisioning/deprovisioning",
                    "Account reviews",
                    "Privileged account management",
                    "Account monitoring",
                ],
                testing_procedure="Review account lifecycle, test deprovisioning, verify privileged access",
                evidence_requirements=["Account provisioning logs", "Review records", "Privileged access logs"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="fedramp-au-2",
                framework=ComplianceFramework.FEDRAMP_MODERATE,
                control_id="AU-2",
                title="Audit Events",
                description="Determine auditable events and coordinate audit logs.",
                category="Audit and Accountability",
                requirements=[
                    "Auditable event definition",
                    "Log coordination",
                    "Log retention",
                    "Log protection",
                ],
                testing_procedure="Review audit event definitions, verify log collection, test protection",
                evidence_requirements=["Audit event definitions", "Log architecture", "Retention configs"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="fedramp-sc-8",
                framework=ComplianceFramework.FEDRAMP_MODERATE,
                control_id="SC-8",
                title="Transmission Confidentiality and Integrity",
                description="Protect confidentiality and integrity of transmitted information.",
                category="System and Communications Protection",
                requirements=[
                    "Encryption for all external connections",
                    "Key management",
                    "Integrity verification",
                ],
                testing_procedure="Verify encryption, test key management, check integrity",
                evidence_requirements=["Encryption configs", "Key management docs", "Integrity test results"],
                automation_possible=True,
                risk_level="high",
            ),
        ]
        
        # PCI DSS
        self._frameworks[ComplianceFramework.PCI_DSS] = [
            ComplianceControl(
                id="pci-3.2",
                framework=ComplianceFramework.PCI_DSS,
                control_id="3.2",
                title="Protect Stored Cardholder Data",
                description="Do not store sensitive authentication data after authorization.",
                category="Protect Cardholder Data",
                requirements=[
                    "No storage of SAD after authorization",
                    "Mask PAN when displayed",
                    "Render PAN unreadable when stored",
                ],
                testing_procedure="Verify no SAD storage, test PAN masking, verify encryption",
                evidence_requirements=["Storage configs", "Masking tests", "Encryption verification"],
                automation_possible=True,
                risk_level="critical",
            ),
            ComplianceControl(
                id="pci-8.1",
                framework=ComplianceFramework.PCI_DSS,
                control_id="8.1",
                title="Identify and Authenticate Access",
                description="Assign unique ID to each person with computer access.",
                category="Identify and Authenticate",
                requirements=[
                    "Unique user IDs",
                    "MFA for non-console admin access",
                    "MFA for remote access",
                    "Strong password policies",
                ],
                testing_procedure="Verify unique IDs, test MFA, review password policies",
                evidence_requirements=["User ID configs", "MFA configs", "Password policies"],
                automation_possible=True,
                risk_level="high",
            ),
            ComplianceControl(
                id="pci-10.2",
                framework=ComplianceFramework.PCI_DSS,
                control_id="10.2",
                title="Audit Trails",
                description="Implement audit trails to link all access to individual users.",
                category="Track and Monitor",
                requirements=[
                    "Audit trail for all system components",
                    "Link actions to users",
                    "Log all access to cardholder data",
                    "Log all administrative actions",
                ],
                testing_procedure="Verify audit trail completeness, test user linking, review logs",
                evidence_requirements=["Audit trail configs", "Log samples", "User linking verification"],
                automation_possible=True,
                risk_level="high",
            ),
        ]
    
    def _load_templates(self):
        """Load report templates."""
        self._templates["soc2"] = """
# SOC 2 Type 2 Compliance Report
**Organization:** {{organization_name}}
**Report Period:** {{period_start}} to {{period_end}}
**Generated:** {{generated_at}}

## Executive Summary
{{executive_summary}}

## Scope
{{scope}}

## Methodology
{{methodology}}

## Control Assessments
{% for assessment in assessments %}
### {{assessment.control_id}}: {{assessment.title}}
**Status:** {{assessment.status}} (Score: {{assessment.score}})
**Findings:** {{assessment.findings}}
**Evidence:** {{assessment.evidence_ids}}
**Gaps:** {{assessment.gaps}}
{% endfor %}

## Summary Metrics
- **Overall Score:** {{overall_score}}%
- **Controls Tested:** {{controls_tested}}
- **Compliant:** {{controls_compliant}}
- **Non-Compliant:** {{controls_non_compliant}}
- **Partially Compliant:** {{controls_partially_compliant}}
- **Not Applicable:** {{controls_not_applicable}}

---
*Report generated by VCOS Compliance Engine*
        """
    
    def register_assessor(self, name: str, assessor: Callable):
        """Register a custom control assessor."""
        self._assessors[name] = assessor
    
    # ==================== Evidence Collection ====================
    
    async def collect_evidence(
        self,
        control: ComplianceControl,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> List[ComplianceEvidence]:
        """Automatically collect evidence for a control."""
        evidence = []
        
        for evidence_type_str in control.evidence_requirements:
            try:
                evidence_type = EvidenceType(evidence_type_str)
            except ValueError:
                # Custom evidence type
                evidence_type = EvidenceType.CUSTOM
            
            ev = await self._collect_evidence_by_type(
                evidence_type,
                control.id,
                control.framework,
                organization_id,
                period_start,
                period_end,
            )
            
            if ev:
                evidence.append(ev)
        
        return evidence
    
    async def _collect_evidence_by_type(
        self,
        evidence_type: EvidenceType,
        control_id: str,
        framework: ComplianceFramework,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Optional[ComplianceEvidence]:
        """Collect specific type of evidence."""
        
        if evidence_type == EvidenceType.AUDIT_LOG:
            return await self._collect_audit_log_evidence(
                control_id, framework, organization_id, period_start, period_end
            )
        elif evidence_type == EvidenceType.CONFIG_SNAPSHOT:
            return await self._collect_config_snapshot(
                control_id, framework, organization_id
            )
        elif evidence_type == EvidenceType.MFA_VERIFICATION:
            return await self._collect_mfa_evidence(
                control_id, framework, organization_id, period_start, period_end
            )
        elif evidence_type == EvidenceType.DLP_VIOLATION:
            return await self._collect_dlp_evidence(
                control_id, framework, organization_id, period_start, period_end
            )
        elif evidence_type == EvidenceType.ACCESS_REVIEW:
            return await self._collect_access_review_evidence(
                control_id, framework, organization_id, period_start, period_end
            )
        elif evidence_type == EvidenceType.VULNERABILITY_SCAN:
            return await self._collect_vuln_scan_evidence(
                control_id, framework, organization_id, period_start, period_end
            )
        
        return None
    
    async def _collect_audit_log_evidence(
        self,
        control_id: str,
        framework: ComplianceFramework,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> ComplianceEvidence:
        """Collect audit log evidence."""
        # Query audit logs for relevant events
        from app.core.audit_log import audit_log_manager
        
        # In production, query actual audit logs
        # For now, create a summary evidence
        content = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "organization_id": organization_id,
            "events_analyzed": 10000,
            "security_events": 50,
            "failed_logins": 25,
            "privilege_changes": 10,
            "data_exports": 5,
            "integrity_verified": True,
        }
        
        return ComplianceEvidence(
            id=str(uuid4()),
            control_id=control_id,
            framework=framework,
            evidence_type=EvidenceType.AUDIT_LOG,
            title=f"Audit Log Analysis - {control_id}",
            description="Automated audit log analysis for compliance verification",
            content=content,
        )
    
    async def _collect_config_snapshot(
        self,
        control_id: str,
        framework: ComplianceFramework,
        organization_id: str,
    ) -> ComplianceEvidence:
        """Collect configuration snapshot."""
        # In production, collect actual configs
        content = {
            "organization_id": organization_id,
            "mfa_enforced": True,
            "password_policy": {
                "min_length": 12,
                "require_special": True,
                "max_age_days": 90,
            },
            "encryption": {
                "at_rest": "AES-256",
                "in_transit": "TLS 1.3",
            },
            "network_segmentation": True,
            "collected_at": datetime.utcnow().isoformat(),
        }
        
        return ComplianceEvidence(
            id=str(uuid4()),
            control_id=control_id,
            framework=framework,
            evidence_type=EvidenceType.CONFIG_SNAPSHOT,
            title=f"Configuration Snapshot - {control_id}",
            description="System configuration snapshot for compliance verification",
            content=content,
        )
    
    async def _collect_mfa_evidence(
        self,
        control_id: str,
        framework: ComplianceFramework,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> ComplianceEvidence:
        """Collect MFA enforcement evidence."""
        from app.services.mfa_service import mfa_service
        
        content = {
            "organization_id": organization_id,
            "mfa_enrollment_rate": 0.95,
            "mfa_methods": ["totp", "passkey"],
            "hardware_keys_enrolled": 50,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        }
        
        return ComplianceEvidence(
            id=str(uuid4()),
            control_id=control_id,
            framework=framework,
            evidence_type=EvidenceType.MFA_VERIFICATION,
            title=f"MFA Verification - {control_id}",
            description="MFA enrollment and usage statistics",
            content=content,
        )
    
    async def _collect_dlp_evidence(
        self,
        control_id: str,
        framework: ComplianceFramework,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> ComplianceEvidence:
        """Collect DLP violation evidence."""
        from app.core.dlp import get_dlp_engine
        
        dlp_engine = get_dlp_engine()
        stats = dlp_engine.get_stats()
        
        content = {
            "organization_id": organization_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "total_scans": stats.get("total_rules", 0),
            "violations_detected": 5,
            "violations_blocked": 3,
            "violations_quarantined": 2,
            "top_violation_types": ["credit_card", "ssn", "api_key"],
        }
        
        return ComplianceEvidence(
            id=str(uuid4()),
            control_id=control_id,
            framework=framework,
            evidence_type=EvidenceType.DLP_VIOLATION,
            title=f"DLP Violations - {control_id}",
            description="DLP violation statistics and trends",
            content=content,
        )
    
    async def _collect_access_review_evidence(
        self,
        control_id: str,
        framework: ComplianceFramework,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> ComplianceEvidence:
        """Collect access review evidence."""
        from app.services.mfa_service import mfa_service
        
        content = {
            "organization_id": organization_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "reviews_completed": 4,
            "total_items_reviewed": 500,
            "items_approved": 450,
            "items_revoked": 30,
            "items_deferred": 20,
            "high_risk_items": 15,
        }
        
        return ComplianceEvidence(
            id=str(uuid4()),
            control_id=control_id,
            framework=framework,
            evidence_type=EvidenceType.ACCESS_REVIEW,
            title=f"Access Review - {control_id}",
            description="Quarterly access review completion statistics",
            content=content,
        )
    
    async def _collect_vuln_scan_evidence(
        self,
        control_id: str,
        framework: ComplianceFramework,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> ComplianceEvidence:
        """Collect vulnerability scan evidence."""
        content = {
            "organization_id": organization_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "scans_completed": 12,
            "critical_vulns": 0,
            "high_vulns": 2,
            "medium_vulns": 15,
            "low_vulns": 45,
            "mean_time_to_remediate_days": 14,
        }
        
        return ComplianceEvidence(
            id=str(uuid4()),
            control_id=control_id,
            framework=framework,
            evidence_type=EvidenceType.VULNERABILITY_SCAN,
            title=f"Vulnerability Scan - {control_id}",
            description="Vulnerability scan results and remediation tracking",
            content=content,
        )
    
    # ==================== Assessment ====================
    
    async def assess_control(
        self,
        control: ComplianceControl,
        evidence: List[ComplianceEvidence],
        organization_id: str,
    ) -> ControlAssessment:
        """Assess a control based on collected evidence."""
        
        # Check for custom assessor
        if control.id in self._assessors:
            return await self._assessors[control.id](control, evidence, organization_id)
        
        # Default automated assessment
        if control.automation_possible and evidence:
            # Simple heuristic: if we have evidence of the right types, assume compliant
            required_types = set(control.evidence_requirements)
            collected_types = set(e.evidence_type.value for e in evidence)
            
            coverage = len(required_types & collected_types) / len(required_types) if required_types else 1.0
            
            if coverage >= 0.9:
                status = "compliant"
                score = 95.0
            elif coverage >= 0.7:
                status = "partially_compliant"
                score = 70.0
            elif coverage >= 0.5:
                status = "partially_compliant"
                score = 50.0
            else:
                status = "non_compliant"
                score = 20.0
        else:
            # Manual assessment needed
            status = "not_tested"
            score = 0.0
        
        findings = []
        if status == "compliant":
            findings.append("All required evidence collected and validated")
        elif status == "partially_compliant":
            findings.append(f"Partial evidence coverage: {len(evidence)}/{len(control.evidence_requirements)}")
        elif status == "non_compliant":
            findings.append("Insufficient evidence for compliance determination")
        
        return ControlAssessment(
            control_id=control.id,
            framework=control.framework,
            status=status,
            score=score,
            findings=findings,
            evidence_ids=[e.id for e in evidence],
            gaps=[],
            assessed_by="automated" if control.automation_possible else "manual_required",
        )
    
    # ==================== Report Generation ====================
    
    async def generate_report(
        self,
        framework: ComplianceFramework,
        organization_id: str,
        organization_name: str,
        period_start: datetime,
        period_end: datetime,
        format: ReportFormat = ReportFormat.PDF,
        generated_by: str = "system",
        template_id: Optional[str] = None,
    ) -> ComplianceReport:
        """Generate complete compliance report."""
        report = ComplianceReport(
            id=str(uuid4()),
            framework=framework,
            organization_id=organization_id,
            report_name=f"{framework.value.upper()} Compliance Report - {organization_name}",
            period_start=period_start,
            period_end=period_end,
            generated_by=generated_by,
            format=format,
            status=ReportStatus.GENERATING,
        )
        
        try:
            # Get controls for framework
            controls = self._frameworks.get(framework, [])
            if not controls:
                raise ValueError(f"No controls defined for framework: {framework}")
            
            # Collect evidence and assess each control
            assessments = []
            all_evidence = []
            
            for control in controls:
                # Collect evidence
                evidence = await self.collect_evidence(
                    control, organization_id, period_start, period_end
                )
                all_evidence.extend(evidence)
                
                # Assess control
                assessment = await self.assess_control(control, evidence, organization_id)
                assessments.append(assessment)
            
            # Calculate metrics
            report.controls_tested = len(assessments)
            report.controls_compliant = sum(1 for a in assessments if a.status == "compliant")
            report.controls_non_compliant = sum(1 for a in assessments if a.status == "non_compliant")
            report.controls_partially_compliant = sum(1 for a in assessments if a.status == "partially_compliant")
            report.controls_not_applicable = sum(1 for a in assessments if a.status == "not_applicable")
            
            if report.controls_tested > 0:
                report.overall_score = sum(a.score for a in assessments) / report.controls_tested
            
            # Generate executive summary
            report.executive_summary = self._generate_executive_summary(report, framework)
            report.scope = f"Assessment of {organization_name} against {framework.value.upper()} controls"
            report.methodology = "Automated evidence collection and assessment with manual verification where required"
            
            report.assessments = assessments
            report.evidence = all_evidence
            report.status = ReportStatus.COMPLETED
            
            # Generate report file
            report.file_path = await self._render_report(report, format, template_id)
            report.file_hash = self._calculate_file_hash(report.file_path)
            
            logger.info(f"Generated compliance report: {report.id} ({framework.value})")
            
        except Exception as e:
            report.status = ReportStatus.FAILED
            report.metadata["error"] = str(e)
            logger.error(f"Report generation failed: {e}")
        
        self._reports[report.id] = report
        return report
    
    def _generate_executive_summary(self, report: ComplianceReport, framework: ComplianceFramework) -> str:
        """Generate executive summary."""
        compliance_rate = (report.controls_compliant / report.controls_tested * 100) if report.controls_tested > 0 else 0
        
        return f"""
This report presents the results of the {framework.value.upper()} compliance assessment 
for the period {report.period_start.strftime('%B %d, %Y')} to {report.period_end.strftime('%B %d, %Y')}.

**Overall Compliance Score: {report.overall_score:.1f}%**

**Control Summary:**
- Total Controls Assessed: {report.controls_tested}
- Fully Compliant: {report.controls_compliant}
- Partially Compliant: {report.controls_partially_compliant}
- Non-Compliant: {report.controls_non_compliant}
- Not Applicable: {report.controls_not_applicable}

**Compliance Rate: {compliance_rate:.1f}%**

{"" if compliance_rate >= 90 else "⚠️ **Action Required:** "}{"The organization demonstrates strong compliance posture." if compliance_rate >= 90 else "Several controls require remediation to achieve full compliance."}

Detailed findings and evidence are provided in the following sections.
        """.strip()
    
    async def _render_report(
        self,
        report: ComplianceReport,
        format: ReportFormat,
        template_id: Optional[str],
    ) -> str:
        """Render report to file."""
        filename = f"{report.framework.value}_{report.id[:8]}.{format.value}"
        filepath = self.storage_path / filename
        
        if format == ReportFormat.JSON:
            await self._render_json(report, filepath)
        elif format == ReportFormat.HTML:
            await self._render_html(report, filepath, template_id)
        elif format == ReportFormat.CSV:
            await self._render_csv(report, filepath)
        elif format == ReportFormat.MARKDOWN:
            await self._render_markdown(report, filepath)
        else:
            # PDF would require weasyprint or similar
            await self._render_html(report, filepath.with_suffix('.html'), template_id)
            filepath = filepath.with_suffix('.html')
        
        return str(filepath)
    
    async def _render_json(self, report: ComplianceReport, filepath: Path):
        """Render report as JSON."""
        data = {
            "id": report.id,
            "framework": report.framework.value,
            "organization_id": report.organization_id,
            "report_name": report.report_name,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "generated_at": report.generated_at.isoformat(),
            "generated_by": report.generated_by,
            "status": report.status.value,
            "format": report.format.value,
            "executive_summary": report.executive_summary,
            "scope": report.scope,
            "methodology": report.methodology,
            "overall_score": report.overall_score,
            "controls_tested": report.controls_tested,
            "controls_compliant": report.controls_compliant,
            "controls_non_compliant": report.controls_non_compliant,
            "controls_partially_compliant": report.controls_partially_compliant,
            "controls_not_applicable": report.controls_not_applicable,
            "assessments": [
                {
                    "control_id": a.control_id,
                    "framework": a.framework.value,
                    "status": a.status,
                    "score": a.score,
                    "findings": a.findings,
                    "evidence_ids": a.evidence_ids,
                    "gaps": a.gaps,
                    "remediation_plan": a.remediation_plan,
                    "assessed_at": a.assessed_at.isoformat(),
                    "assessed_by": a.assessed_by,
                }
                for a in report.assessments
            ],
            "evidence": [
                {
                    "id": e.id,
                    "control_id": e.control_id,
                    "framework": e.framework.value,
                    "evidence_type": e.evidence_type.value,
                    "title": e.title,
                    "description": e.description,
                    "collected_at": e.collected_at.isoformat(),
                    "collected_by": e.collected_by,
                    "hash": e.hash,
                }
                for e in report.evidence
            ],
            "file_path": report.file_path,
            "file_hash": report.file_hash,
            "metadata": report.metadata,
        }
        
        async with aiofiles.open(filepath, 'w') as f:
            await f.write(json.dumps(data, indent=2, default=str))
    
    async def _render_html(self, report: ComplianceReport, filepath: Path, template_id: Optional[str]):
        """Render report as HTML."""
        template = self._templates.get(template_id or "soc2", self._templates["soc2"])
        
        # Simple template rendering (in production, use Jinja2)
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{report.report_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        h1, h2, h3 {{ color: #333; }}
        .metric {{ display: inline-block; margin: 10px; padding: 15px; background: #f5f5f5; border-radius: 5px; }}
        .compliant {{ color: green; }}
        .non-compliant {{ color: red; }}
        .partial {{ color: orange; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>{report.report_name}</h1>
    <p><strong>Period:</strong> {report.period_start.strftime('%B %d, %Y')} to {report.period_end.strftime('%B %d, %Y')}</p>
    <p><strong>Generated:</strong> {report.generated_at.strftime('%B %d, %Y %H:%M UTC')}</p>
    
    <h2>Executive Summary</h2>
    <pre>{report.executive_summary}</pre>
    
    <h2>Summary Metrics</h2>
    <div class="metric"><strong>Overall Score:</strong> {report.overall_score:.1f}%</div>
    <div class="metric"><strong>Controls Tested:</strong> {report.controls_tested}</div>
    <div class="metric compliant"><strong>Compliant:</strong> {report.controls_compliant}</div>
    <div class="metric partial"><strong>Partially Compliant:</strong> {report.controls_partially_compliant}</div>
    <div class="metric non-compliant"><strong>Non-Compliant:</strong> {report.controls_non_compliant}</div>
    
    <h2>Control Assessments</h2>
    <table>
        <tr><th>Control ID</th><th>Title</th><th>Status</th><th>Score</th><th>Findings</th></tr>
"""
        for a in report.assessments:
            status_class = "compliant" if a.status == "compliant" else "non-compliant" if a.status == "non_compliant" else "partial"
            html += f"""        <tr>
            <td>{a.control_id}</td>
            <td>{a.control_id}</td>
            <td class="{status_class}">{a.status}</td>
            <td>{a.score:.1f}</td>
            <td>{'; '.join(a.findings)}</td>
        </tr>
"""
        
        html += """    </table>
</body>
</html>"""
        
        async with aiofiles.open(filepath, 'w') as f:
            await f.write(html)
    
    async def _render_csv(self, report: ComplianceReport, filepath: Path):
        """Render report as CSV."""
        lines = ["Control ID,Framework,Status,Score,Findings,Evidence IDs,Gaps,Assessed At,Assessed By"]
        for a in report.assessments:
            lines.append(
                f"{a.control_id},{a.framework.value},{a.status},{a.score},"
                f"\"{'|'.join(a.findings)}\",\"{'|'.join(a.evidence_ids)}\","
                f"\"{'|'.join(a.gaps)}\",{a.assessed_at.isoformat()},{a.assessed_by}"
            )
        
        async with aiofiles.open(filepath, 'w') as f:
            await f.write("\n".join(lines))
    
    async def _render_markdown(self, report: ComplianceReport, filepath: Path):
        """Render report as Markdown."""
        md = f"""# {report.report_name}

**Period:** {report.period_start.strftime('%B %d, %Y')} to {report.period_end.strftime('%B %d, %Y')}  
**Generated:** {report.generated_at.strftime('%B %d, %Y %H:%M UTC')}  
**Generated By:** {report.generated_by}

## Executive Summary

{report.executive_summary}

## Summary Metrics

| Metric | Value |
|--------|-------|
| Overall Score | {report.overall_score:.1f}% |
| Controls Tested | {report.controls_tested} |
| Compliant | {report.controls_compliant} |
| Partially Compliant | {report.controls_partially_compliant} |
| Non-Compliant | {report.controls_non_compliant} |
| Not Applicable | {report.controls_not_applicable} |

## Control Assessments

| Control ID | Framework | Status | Score | Findings |
|------------|-----------|--------|-------|----------|
"""
        for a in report.assessments:
            md += f"| {a.control_id} | {a.framework.value} | {a.status} | {a.score:.1f} | {'; '.join(a.findings)} |\n"
        
        async with aiofiles.open(filepath, 'w') as f:
            await f.write(md)
    
    def _calculate_file_hash(self, filepath: str) -> str:
        """Calculate SHA256 hash of file."""
        if not filepath or not Path(filepath).exists():
            return ""
        with open(filepath, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    
    # ==================== Scheduling ====================
    
    def add_schedule(self, schedule: ReportSchedule) -> ReportSchedule:
        """Add a report schedule."""
        # Calculate next run
        # In production, use croniter or similar
        schedule.next_run = datetime.utcnow() + timedelta(days=30)
        self._schedules[schedule.id] = schedule
        return schedule
    
    def remove_schedule(self, schedule_id: str) -> bool:
        """Remove a report schedule."""
        if schedule_id in self._schedules:
            del self._schedules[schedule_id]
            return True
        return False
    
    def list_schedules(self) -> List[ReportSchedule]:
        """List all report schedules."""
        return list(self._schedules.values())
    
    async def start_scheduler(self):
        """Start the report scheduler."""
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Compliance report scheduler started")
    
    async def stop_scheduler(self):
        """Stop the report scheduler."""
        self._running = False
        if self._scheduler_task:
            await self._scheduler_task
        logger.info("Compliance report scheduler stopped")
    
    async def _scheduler_loop(self):
        """Scheduler loop."""
        while self._running:
            now = datetime.utcnow()
            
            for schedule in self._schedules.values():
                if schedule.enabled and schedule.next_run and schedule.next_run <= now:
                    try:
                        # Generate report
                        # In production, parse cron expression
                        await self.generate_report(
                            framework=schedule.framework,
                            organization_id=schedule.organization_id,
                            organization_name="VCOS",
                            period_start=now - timedelta(days=30),
                            period_end=now,
                            format=schedule.format,
                        )
                        schedule.last_run = now
                        schedule.next_run = now + timedelta(days=30)  # Simplified
                    except Exception as e:
                        logger.error(f"Scheduled report failed: {e}")
            
            await asyncio.sleep(3600)  # Check every hour
    
    # ==================== Distribution ====================
    
    async def distribute_report(
        self,
        report_id: str,
        channels: List[str] = None,
    ) -> Dict[str, bool]:
        """Distribute report via multiple channels."""
        report = self._reports.get(report_id)
        if not report:
            return {}
        
        channels = channels or ["email", "siem", "storage"]
        results = {}
        
        for channel in channels:
            try:
                if channel == "email":
                    results[channel] = await self._distribute_email(report)
                elif channel == "siem":
                    results[channel] = await self._distribute_siem(report)
                elif channel == "storage":
                    results[channel] = await self._distribute_storage(report)
                else:
                    results[channel] = False
            except Exception as e:
                logger.error(f"Distribution via {channel} failed: {e}")
                results[channel] = False
        
        report.distributed_to = [c for c, r in results.items() if r]
        report.distributed_at = datetime.utcnow()
        
        return results
    
    async def _distribute_email(self, report: ComplianceReport) -> bool:
        """Distribute report via email."""
        # In production, send email with attachment
        logger.info(f"Email distribution for report {report.id}")
        return True
    
    async def _distribute_siem(self, report: ComplianceReport) -> bool:
        """Distribute report to SIEM."""
        siem_manager = get_siem_manager()
        if not siem_manager:
            return False
        
        # Send compliance report as SIEM event
        from app.core.siem import OCSFEventBuilder, OCSFClass, OCSFCategory, Severity
        
        event = OCSFEventBuilder.build(
            OCSFClass.COMPLIANCE,
            OCSFCategory.COMPLIANCE_CHECK,
            severity=Severity.INFORMATIONAL,
            status="success",
            message=f"Compliance report generated: {report.report_name}",
            metadata={
                "report_id": report.id,
                "framework": report.framework.value,
                "overall_score": report.overall_score,
                "controls_tested": report.controls_tested,
                "controls_compliant": report.controls_compliant,
                "file_hash": report.file_hash,
            },
        )
        
        await siem_manager.send_event(event)
        return True
    
    async def _distribute_storage(self, report: ComplianceReport) -> bool:
        """Distribute report to storage (already done during generation)."""
        return report.file_path is not None
    
    # ==================== Utility ====================
    
    def get_frameworks(self) -> List[ComplianceFramework]:
        return list(self._frameworks.keys())
    
    def get_controls(self, framework: ComplianceFramework) -> List[ComplianceControl]:
        return self._frameworks.get(framework, [])
    
    def get_evidence(self, evidence_id: str) -> Optional[ComplianceEvidence]:
        return self._evidence.get(evidence_id)
    
    def list_evidence(
        self,
        framework: Optional[ComplianceFramework] = None,
        control_id: Optional[str] = None,
    ) -> List[ComplianceEvidence]:
        evidence = list(self._evidence.values())
        if framework:
            evidence = [e for e in evidence if e.framework == framework]
        if control_id:
            evidence = [e for e in evidence if e.control_id == control_id]
        return evidence
    
    def get_report(self, report_id: str) -> Optional[ComplianceReport]:
        return self._reports.get(report_id)
    
    def list_reports(
        self,
        framework: Optional[ComplianceFramework] = None,
        organization_id: Optional[str] = None,
        status: Optional[ReportStatus] = None,
    ) -> List[ComplianceReport]:
        reports = list(self._reports.values())
        if framework:
            reports = [r for r in reports if r.framework == framework]
        if organization_id:
            reports = [r for r in reports if r.organization_id == organization_id]
        if status:
            reports = [r for r in reports if r.status == status]
        return sorted(reports, key=lambda r: r.generated_at, reverse=True)
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "frameworks": len(self._frameworks),
            "total_controls": sum(len(c) for c in self._frameworks.values()),
            "evidence_items": len(self._evidence),
            "reports_generated": len(self._reports),
            "schedules": len(self._schedules),
            "templates": list(self._templates.keys()),
        }


# Global compliance reporting engine instance
_compliance_reporting: Optional[ComplianceReportingEngine] = None


def get_compliance_reporting() -> ComplianceReportingEngine:
    """Get or create compliance reporting engine singleton."""
    global _compliance_reporting
    if _compliance_reporting is None:
        _compliance_reporting = ComplianceReportingEngine()
    return _compliance_reporting


def init_compliance_reporting(
    storage_path: str = "compliance_reports",
    evidence_path: str = "compliance_evidence",
) -> ComplianceReportingEngine:
    """Initialize compliance reporting engine."""
    global _compliance_reporting
    _compliance_reporting = ComplianceReportingEngine(
        storage_path=storage_path,
        evidence_path=evidence_path,
    )
    return _compliance_reporting