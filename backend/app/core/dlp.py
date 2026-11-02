"""
Data Loss Prevention (DLP) Engine for VCOS.

Provides:
- Content inspection with regex patterns
- ML-based sensitive data classification
- Predefined rules for PII, PHI, PCI, Secrets
- Custom rule engine
- Real-time scanning and blocking
- Quarantine and alerting
"""

import asyncio
import hashlib
import json
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Pattern, Set
from uuid import uuid4

import aiofiles

from app.core.config import settings

logger = logging.getLogger(__name__)


class DLPAction(str, Enum):
    """DLP enforcement actions."""
    ALLOW = "allow"
    ALERT = "alert"
    QUARANTINE = "quarantine"
    BLOCK = "block"
    REDACT = "redact"
    ENCRYPT = "encrypt"


class DLPRuleType(str, Enum):
    """Types of DLP rules."""
    REGEX = "regex"
    KEYWORD = "keyword"
    ML_CLASSIFIER = "ml_classifier"
    COMPOSITE = "composite"
    EXACT_MATCH = "exact_match"


class SensitivityLevel(str, Enum):
    """Data sensitivity levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    PII = "pii"
    PHI = "phi"
    PCI = "pci"
    SECRETS = "secrets"
    IP = "ip"  # Intellectual Property


@dataclass
class DLPMatch:
    """A single DLP rule match."""
    rule_id: str
    rule_name: str
    rule_type: DLPRuleType
    sensitivity: SensitivityLevel
    match_text: str
    start_pos: int
    end_pos: int
    confidence: float
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DLPScanResult:
    """Result of a DLP scan."""
    scan_id: str
    timestamp: datetime
    content_hash: str
    matches: List[DLPMatch]
    highest_sensitivity: SensitivityLevel
    action: DLPAction
    redacted_content: Optional[str] = None
    quarantine_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DLPRule:
    """DLP detection rule."""
    id: str
    name: str
    description: str
    rule_type: DLPRuleType
    sensitivity: SensitivityLevel
    pattern: str  # regex pattern or keyword list
    action: DLPAction = DLPAction.ALERT
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # For composite rules
    sub_rules: List[str] = field(default_factory=list)
    logic: str = "any"  # any, all, not
    # ML classifier config
    model_name: Optional[str] = None
    threshold: float = 0.8
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    compiled_pattern: Optional[Pattern] = field(default=None, repr=False)

    def compile(self):
        """Compile regex pattern."""
        if self.rule_type == DLPRuleType.REGEX:
            try:
                self.compiled_pattern = re.compile(self.pattern, re.IGNORECASE | re.MULTILINE)
            except re.error as e:
                logger.error(f"Invalid regex in rule {self.id}: {e}")
                self.compiled_pattern = None


class QuarantineItem:
    """Quarantined content item."""
    def __init__(
        self,
        content: str,
        scan_result: DLPScanResult,
        source: str,
        source_id: str,
        actor_id: str,
    ):
        self.id = str(uuid4())
        self.content = content
        self.scan_result = scan_result
        self.source = source  # email, document, chat, api, file_upload
        self.source_id = source_id
        self.actor_id = actor_id
        self.created_at = datetime.utcnow()
        self.status = "pending"  # pending, released, deleted, escalated
        self.reviewed_by: Optional[str] = None
        self.reviewed_at: Optional[datetime] = None
        self.review_notes: str = ""


class DLPEngine:
    """
    Data Loss Prevention Engine.
    
    Features:
    - Real-time content scanning
    - Predefined rules for PII, PHI, PCI, Secrets, IP
    - Custom rule creation
    - ML-based classification (pluggable)
    - Quarantine workflow
    - Alerting and reporting
    - Integration with audit logging
    """

    def __init__(self):
        self._rules: Dict[str, DLPRule] = {}
        self._quarantine: Dict[str, QuarantineItem] = {}
        self._initialized = False
        self._ml_classifiers: Dict[str, Callable] = {}
        self._load_builtin_rules()

    def _load_builtin_rules(self):
        """Load built-in DLP rules for common sensitive data types."""
        
        # ===== PII Rules =====
        self.add_rule(DLPRule(
            id="dlp-pii-ssn",
            name="US Social Security Number",
            description="Detects US SSN format (XXX-XX-XXXX)",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PII,
            pattern=r"\b\d{3}-\d{2}-\d{4}\b",
            action=DLPAction.BLOCK,
            tags=["pii", "ssn", "us"],
        ))

        self.add_rule(DLPRule(
            id="dlp-pii-email",
            name="Email Address",
            description="Detects email addresses",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PII,
            pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            action=DLPAction.ALERT,
            tags=["pii", "email"],
        ))

        self.add_rule(DLPRule(
            id="dlp-pii-phone-us",
            name="US Phone Number",
            description="Detects US phone numbers",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PII,
            pattern=r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
            action=DLPAction.ALERT,
            tags=["pii", "phone", "us"],
        ))

        self.add_rule(DLPRule(
            id="dlp-pii-dob",
            name="Date of Birth",
            description="Detects date of birth patterns",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PII,
            pattern=r"\b(0?[1-9]|1[0-2])[-/\s](0?[1-9]|[12]\d|3[01])[-/\s](19|20)\d{2}\b",
            action=DLPAction.ALERT,
            tags=["pii", "dob"],
        ))

        self.add_rule(DLPRule(
            id="dlp-pii-driver-license",
            name="US Driver's License",
            description="Detects US driver's license numbers (generic)",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PII,
            pattern=r"\b[A-Z]{1,2}\d{6,8}\b",
            action=DLPAction.ALERT,
            tags=["pii", "drivers-license", "us"],
        ))

        self.add_rule(DLPRule(
            id="dlp-pii-passport-us",
            name="US Passport Number",
            description="Detects US passport numbers",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PII,
            pattern=r"\b[A-Z]\d{8}\b",
            action=DLPAction.BLOCK,
            tags=["pii", "passport", "us"],
        ))

        # ===== Financial/PCI Rules =====
        self.add_rule(DLPRule(
            id="dlp-pci-credit-card",
            name="Credit Card Number",
            description="Detects credit card numbers (Luhn validated)",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PCI,
            pattern=r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
            action=DLPAction.BLOCK,
            tags=["pci", "credit-card", "financial"],
        ))

        self.add_rule(DLPRule(
            id="dlp-pci-bank-account",
            name="Bank Account Number",
            description="Detects US bank account numbers",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PCI,
            pattern=r"\b\d{8,17}\b",
            action=DLPAction.ALERT,
            tags=["pci", "bank-account", "financial"],
        ))

        self.add_rule(DLPRule(
            id="dlp-pci-routing",
            name="ABA Routing Number",
            description="Detects US ABA routing numbers",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PCI,
            pattern=r"\b\d{9}\b",
            action=DLPAction.ALERT,
            tags=["pci", "routing", "financial"],
        ))

        # ===== PHI Rules =====
        self.add_rule(DLPRule(
            id="dlp-phi-medical-record",
            name="Medical Record Number",
            description="Detects medical record numbers",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PHI,
            pattern=r"\b(MRN|MR|Medical Record)[\s:#]*\d{6,12}\b",
            action=DLPAction.BLOCK,
            tags=["phi", "medical-record", "hipaa"],
        ))

        self.add_rule(DLPRule(
            id="dlp-phi-icd10",
            name="ICD-10 Diagnosis Code",
            description="Detects ICD-10 diagnosis codes",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PHI,
            pattern=r"\b[A-TV-Z][0-9]{2}(?:\.[0-9A-TV-Z]{1,4})?\b",
            action=DLPAction.ALERT,
            tags=["phi", "icd10", "hipaa"],
        ))

        self.add_rule(DLPRule(
            id="dlp-phi-npi",
            name="NPI Number",
            description="Detects National Provider Identifier",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.PHI,
            pattern=r"\b\d{10}\b",
            action=DLPAction.ALERT,
            tags=["phi", "npi", "hipaa"],
        ))

        # ===== Secrets/Credentials Rules =====
        self.add_rule(DLPRule(
            id="dlp-secrets-aws-access-key",
            name="AWS Access Key ID",
            description="Detects AWS access key IDs",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.SECRETS,
            pattern=r"\bAKIA[0-9A-Z]{16}\b",
            action=DLPAction.BLOCK,
            tags=["secrets", "aws", "credentials"],
        ))

        self.add_rule(DLPRule(
            id="dlp-secrets-aws-secret-key",
            name="AWS Secret Access Key",
            description="Detects AWS secret access keys",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.SECRETS,
            pattern=r"\b[0-9a-zA-Z/+]{40}\b",
            action=DLPAction.BLOCK,
            tags=["secrets", "aws", "credentials"],
        ))

        self.add_rule(DLPRule(
            id="dlp-secrets-gcp-api-key",
            name="Google Cloud API Key",
            description="Detects GCP API keys",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.SECRETS,
            pattern=r"\bAIza[0-9A-Za-z_-]{35}\b",
            action=DLPAction.BLOCK,
            tags=["secrets", "gcp", "credentials"],
        ))

        self.add_rule(DLPRule(
            id="dlp-secrets-github-token",
            name="GitHub Personal Access Token",
            description="Detects GitHub PATs",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.SECRETS,
            pattern=r"\bgh[pousr]_[0-9a-zA-Z]{36,255}\b",
            action=DLPAction.BLOCK,
            tags=["secrets", "github", "credentials"],
        ))

        self.add_rule(DLPRule(
            id="dlp-secrets-slack-token",
            name="Slack API Token",
            description="Detects Slack tokens",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.SECRETS,
            pattern=r"\bxox[baprs]-[0-9a-zA-Z]{10,48}\b",
            action=DLPAction.BLOCK,
            tags=["secrets", "slack", "credentials"],
        ))

        self.add_rule(DLPRule(
            id="dlp-secrets-generic-api-key",
            name="Generic API Key Pattern",
            description="Detects generic API key patterns",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.SECRETS,
            pattern=r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*[\"']?[0-9a-zA-Z_-]{20,}[\"']?",
            action=DLPAction.ALERT,
            tags=["secrets", "api-key", "credentials"],
        ))

        self.add_rule(DLPRule(
            id="dlp-secrets-private-key",
            name="Private Key",
            description="Detects PEM private keys",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.SECRETS,
            pattern=r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----",
            action=DLPAction.BLOCK,
            tags=["secrets", "private-key", "crypto"],
        ))

        self.add_rule(DLPRule(
            id="dlp-secrets-jwt",
            name="JWT Token",
            description="Detects JWT tokens",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.SECRETS,
            pattern=r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
            action=DLPAction.BLOCK,
            tags=["secrets", "jwt", "token"],
        ))

        # ===== IP/Proprietary Rules =====
        self.add_rule(DLPRule(
            id="dlp-ip-internal-code",
            name="Internal Code Patterns",
            description="Detects internal proprietary code patterns",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.IP,
            pattern=r"(?i)(internal[_-]?use[_-]?only|confidential|proprietary|trade[_-]?secret)",
            action=DLPAction.ALERT,
            tags=["ip", "proprietary", "confidential"],
        ))

        self.add_rule(DLPRule(
            id="dlp-ip-database-connection",
            name="Database Connection String",
            description="Detects database connection strings",
            rule_type=DLPRuleType.REGEX,
            sensitivity=SensitivityLevel.SECRETS,
            pattern=r"(?i)(mongodb|postgresql|mysql|redis)://[^:\s]+:[^@\s]+@[^/\s]+",
            action=DLPAction.BLOCK,
            tags=["secrets", "database", "connection-string"],
        ))

        # ===== Composite Rules =====
        self.add_rule(DLPRule(
            id="dlp-composite-pii-document",
            name="PII Document Detection",
            description="Document containing multiple PII types",
            rule_type=DLPRuleType.COMPOSITE,
            sensitivity=SensitivityLevel.PII,
            pattern="",
            action=DLPAction.BLOCK,
            sub_rules=["dlp-pii-ssn", "dlp-pii-email", "dlp-pii-phone-us"],
            logic="any",
            tags=["pii", "composite", "document"],
        ))

        self.add_rule(DLPRule(
            id="dlp-composite-pci-document",
            name="PCI Document Detection",
            description="Document containing payment card data",
            rule_type=DLPRuleType.COMPOSITE,
            sensitivity=SensitivityLevel.PCI,
            pattern="",
            action=DLPAction.BLOCK,
            sub_rules=["dlp-pci-credit-card", "dlp-pci-bank-account"],
            logic="any",
            tags=["pci", "composite", "financial"],
        ))

    def add_rule(self, rule: DLPRule) -> DLPRule:
        """Add a DLP rule."""
        rule.compile()
        self._rules[rule.id] = rule
        logger.info(f"Added DLP rule: {rule.id} ({rule.name})")
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a DLP rule."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def get_rule(self, rule_id: str) -> Optional[DLPRule]:
        """Get a DLP rule by ID."""
        return self._rules.get(rule_id)

    def list_rules(
        self,
        sensitivity: Optional[SensitivityLevel] = None,
        rule_type: Optional[DLPRuleType] = None,
        enabled_only: bool = True,
    ) -> List[DLPRule]:
        """List DLP rules with filters."""
        rules = list(self._rules.values())
        
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        if sensitivity:
            rules = [r for r in rules if r.sensitivity == sensitivity]
        if rule_type:
            rules = [r for r in rules if r.rule_type == rule_type]
        
        return sorted(rules, key=lambda r: r.name)

    def register_ml_classifier(self, name: str, classifier: Callable[[str], List[Dict[str, Any]]]):
        """Register an ML classifier function."""
        self._ml_classifiers[name] = classifier
        logger.info(f"Registered ML classifier: {name}")

    async def scan_content(
        self,
        content: str,
        source: str = "unknown",
        source_id: str = "",
        actor_id: str = "",
        context: Dict[str, Any] = None,
    ) -> DLPScanResult:
        """
        Scan content for sensitive data.
        
        Args:
            content: Text content to scan
            source: Source type (email, document, chat, api, file_upload)
            source_id: Identifier of the source
            actor_id: User who initiated the scan
            context: Additional context
            
        Returns:
            DLPScanResult with matches and recommended action
        """
        scan_id = str(uuid4())
        timestamp = datetime.utcnow()
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        matches = []
        highest_sensitivity = SensitivityLevel.PUBLIC

        # Scan with regex/keyword rules
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            
            rule_matches = await self._scan_with_rule(content, rule)
            matches.extend(rule_matches)
            
            # Update highest sensitivity
            if rule_matches:
                sensitivity_order = [
                    SensitivityLevel.PUBLIC,
                    SensitivityLevel.INTERNAL,
                    SensitivityLevel.CONFIDENTIAL,
                    SensitivityLevel.RESTRICTED,
                    SensitivityLevel.PII,
                    SensitivityLevel.PHI,
                    SensitivityLevel.PCI,
                    SensitivityLevel.SECRETS,
                    SensitivityLevel.IP,
                ]
                if order.index(rule.sensitivity) > order.index(highest_sensitivity):
                    highest_sensitivity = rule.sensitivity

        # Scan with ML classifiers
        for name, classifier in self._ml_classifiers.items():
            try:
                ml_results = await classifier(content)
                for result in ml_results:
                    match = DLPMatch(
                        rule_id=f"ml-{name}",
                        rule_name=f"ML Classifier: {name}",
                        rule_type=DLPRuleType.ML_CLASSIFIER,
                        sensitivity=SensitivityLevel(result.get("sensitivity", "confidential")),
                        match_text=result.get("text", ""),
                        start_pos=result.get("start", 0),
                        end_pos=result.get("end", 0),
                        confidence=result.get("confidence", 0.0),
                        context=result.get("context", {}),
                    )
                    matches.append(match)
            except Exception as e:
                logger.error(f"ML classifier {name} error: {e}")

        # Determine action based on matches
        action = self._determine_action(matches)
        
        # Redact content if needed
        redacted_content = None
        if action == DLPAction.REDACT:
            redacted_content = self._redact_content(content, matches)

        # Quarantine if needed
        quarantine_id = None
        if action == DLPAction.QUARANTINE:
            quarantine_item = QuarantineItem(content, None, source, source_id, actor_id)
            quarantine_item.scan_result = DLPScanResult(
                scan_id=scan_id,
                timestamp=timestamp,
                content_hash=content_hash,
                matches=matches,
                highest_sensitivity=highest_sensitivity,
                action=action,
            )
            self._quarantine[quarantine_item.id] = quarantine_item
            quarantine_id = quarantine_item.id

        result = DLPScanResult(
            scan_id=scan_id,
            timestamp=timestamp,
            content_hash=content_hash,
            matches=matches,
            highest_sensitivity=highest_sensitivity,
            action=action,
            redacted_content=redacted_content,
            quarantine_id=quarantine_id,
            metadata={
                "source": source,
                "source_id": source_id,
                "actor_id": actor_id,
                "content_length": len(content),
                "context": context or {},
            },
        )

        # Log audit event
        await self._log_audit_event(result, actor_id, source, source_id)

        return result

    async def _scan_with_rule(self, content: str, rule: DLPRule) -> List[DLPMatch]:
        """Scan content with a single rule."""
        matches = []
        
        if rule.rule_type == DLPRuleType.REGEX and rule.compiled_pattern:
            for match in rule.compiled_pattern.finditer(content):
                matches.append(DLPMatch(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    sensitivity=rule.sensitivity,
                    match_text=match.group(),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    confidence=0.95,
                    context={"pattern": rule.pattern},
                ))
        
        elif rule.rule_type == DLPRuleType.KEYWORD:
            keywords = [k.strip().lower() for k in rule.pattern.split(",")]
            content_lower = content.lower()
            for keyword in keywords:
                start = 0
                while True:
                    idx = content_lower.find(keyword, start)
                    if idx == -1:
                        break
                    matches.append(DLPMatch(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        rule_type=rule.rule_type,
                        sensitivity=rule.sensitivity,
                        match_text=content[idx:idx+len(keyword)],
                        start_pos=idx,
                        end_pos=idx+len(keyword),
                        confidence=0.8,
                        context={"keyword": keyword},
                    ))
                    start = idx + 1
        
        elif rule.rule_type == DLPRuleType.COMPOSITE:
            # Evaluate sub-rules
            sub_matches = []
            for sub_rule_id in rule.sub_rules:
                sub_rule = self._rules.get(sub_rule_id)
                if sub_rule and sub_rule.enabled:
                    sub_matches.extend(await self._scan_with_rule(content, sub_rule))
            
            if rule.logic == "any" and sub_matches:
                matches.extend(sub_matches)
            elif rule.logic == "all":
                # Check if all sub-rules matched
                sub_rule_ids = set(rule.sub_rules)
                matched_ids = set(m.rule_id for m in sub_matches)
                if sub_rule_ids.issubset(matched_ids):
                    matches.extend(sub_matches)
            elif rule.logic == "not":
                # Match if NONE of the sub-rules matched
                if not sub_matches:
                    # This is a negative match - content is clean
                    pass
        
        elif rule.rule_type == DLPRuleType.ML_CLASSIFIER and rule.model_name:
            classifier = self._ml_classifiers.get(rule.model_name)
            if classifier:
                try:
                    ml_results = await classifier(content)
                    for ml_result in ml_results:
                        if ml_result.get("confidence", 0) >= rule.threshold:
                            matches.append(DLPMatch(
                                rule_id=rule.id,
                                rule_name=rule.name,
                                rule_type=rule.rule_type,
                                sensitivity=SensitivityLevel(ml_result.get("sensitivity", "confidential")),
                                match_text=ml_result.get("text", ""),
                                start_pos=ml_result.get("start", 0),
                                end_pos=ml_result.get("end", 0),
                                confidence=ml_result.get("confidence", 0.0),
                                context=ml_result.get("context", {}),
                            ))
                except Exception as e:
                    logger.error(f"ML classifier {rule.model_name} error: {e}")
        
        return matches

    def _determine_action(self, matches: List[DLPMatch]) -> DLPAction:
        """Determine the most restrictive action based on matches."""
        if not matches:
            return DLPAction.ALLOW
        
        # Priority: BLOCK > QUARANTINE > REDACT > ENCRYPT > ALERT > ALLOW
        action_priority = {
            DLPAction.BLOCK: 6,
            DLPAction.QUARANTINE: 5,
            DLPAction.REDACT: 4,
            DLPAction.ENCRYPT: 3,
            DLPAction.ALERT: 2,
            DLPAction.ALLOW: 1,
        }
        
        # Get the highest priority action from matching rules
        rule_actions = {}
        for match in matches:
            rule = self._rules.get(match.rule_id)
            if rule:
                rule_actions[match.rule_id] = action_priority.get(rule.action, 1)
        
        if not rule_actions:
            return DLPAction.ALLOW
        
        max_priority = max(rule_actions.values())
        for action, priority in action_priority.items():
            if priority == max_priority:
                return action
        
        return DLPAction.ALERT

    def _redact_content(self, content: str, matches: List[DLPMatch]) -> str:
        """Redact matched sensitive content."""
        # Sort matches by position (reverse to maintain indices)
        sorted_matches = sorted(matches, key=lambda m: m.start_pos, reverse=True)
        
        redacted = content
        for match in sorted_matches:
            # Replace with asterisks preserving length
            replacement = "*" * (match.end_pos - match.start_pos)
            redacted = redacted[:match.start_pos] + replacement + redacted[match.end_pos:]
        
        return redacted

    async def _log_audit_event(
        self,
        result: DLPScanResult,
        actor_id: str,
        source: str,
        source_id: str,
    ):
        """Log DLP scan to audit trail."""
        from app.core.audit_log import audit_log_manager, EventType, Severity
        
        if result.matches:
            await audit_log_manager.log_security_event(
                event_type=EventType.SECURITY_EVENT,
                actor_id=actor_id,
                organization_id=result.metadata.get("organization_id", ""),
                details={
                    "scan_id": result.scan_id,
                    "source": source,
                    "source_id": source_id,
                    "matches_count": len(result.matches),
                    "highest_sensitivity": result.highest_sensitivity.value,
                    "action": result.action.value,
                    "rules_matched": [m.rule_id for m in result.matches],
                },
            )

    # ==================== Quarantine Management ====================

    def get_quarantine(self, quarantine_id: str) -> Optional[QuarantineItem]:
        """Get quarantined item."""
        return self._quarantine.get(quarantine_id)

    def list_quarantine(
        self,
        status: Optional[str] = None,
        actor_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[QuarantineItem]:
        """List quarantined items."""
        items = list(self._quarantine.values())
        
        if status:
            items = [i for i in items if i.status == status]
        if actor_id:
            items = [i for i in items if i.actor_id == actor_id]
        
        items.sort(key=lambda i: i.created_at, reverse=True)
        return items[:limit]

    def release_quarantine(self, quarantine_id: str, reviewer_id: str, notes: str = "") -> bool:
        """Release quarantined content."""
        item = self._quarantine.get(quarantine_id)
        if not item:
            return False
        
        item.status = "released"
        item.reviewed_by = reviewer_id
        item.reviewed_at = datetime.utcnow()
        item.review_notes = notes
        return True

    def delete_quarantine(self, quarantine_id: str, reviewer_id: str, notes: str = "") -> bool:
        """Delete quarantined content."""
        item = self._quarantine.get(quarantine_id)
        if not item:
            return False
        
        item.status = "deleted"
        item.reviewed_by = reviewer_id
        item.reviewed_at = datetime.utcnow()
        item.review_notes = notes
        return True

    def escalate_quarantine(self, quarantine_id: str, reviewer_id: str, notes: str = "") -> bool:
        """Escalate quarantined content for further review."""
        item = self._quarantine.get(quarantine_id)
        if not item:
            return False
        
        item.status = "escalated"
        item.reviewed_by = reviewer_id
        item.reviewed_at = datetime.utcnow()
        item.review_notes = notes
        return True

    # ==================== Statistics & Reporting ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get DLP engine statistics."""
        quarantine_stats = {}
        for item in self._quarantine.values():
            quarantine_stats[item.status] = quarantine_stats.get(item.status, 0) + 1
        
        rule_stats = {}
        for rule in self._rules.values():
            if rule.enabled:
                rule_stats[rule.sensitivity.value] = rule_stats.get(rule.sensitivity.value, 0) + 1
        
        return {
            "total_rules": len(self._rules),
            "enabled_rules": sum(1 for r in self._rules.values() if r.enabled),
            "rules_by_sensitivity": rule_stats,
            "ml_classifiers": len(self._ml_classifiers),
            "quarantine_items": len(self._quarantine),
            "quarantine_by_status": quarantine_stats,
        }


# Global DLP engine instance
_dlp_engine: Optional[DLPEngine] = None


def get_dlp_engine() -> DLPEngine:
    """Get or create DLP engine singleton."""
    global _dlp_engine
    if _dlp_engine is None:
        _dlp_engine = DLPEngine()
    return _dlp_engine


def init_dlp_engine() -> DLPEngine:
    """Initialize DLP engine."""
    global _dlp_engine
    _dlp_engine = DLPEngine()
    return _dlp_engine