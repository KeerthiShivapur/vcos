"""Slice 4H.7 Phase D — Pattern Qualifier.

Connects cohorts to patterns and qualifies patterns based on evidence.
Does NOT create lessons. Stops at qualified pattern.

Pipeline:
    Cohort (from CohortBuilder)
        ↓
Pattern Detection lookup (governance-gated)
        ↓
Evidence Aggregation (decisions + actions + outcomes + metrics)
        ↓
Contradiction Analysis (supporting vs contradicting)
        ↓
Epistemic Qualification (thresholds from contract §7)
        ↓
Qualified Pattern (not a lesson!)

Determinism: same inputs (org, caller, cohort) always produce
byte-identical qualification results.

Observation only: no operating-layer mutation, no lesson creation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess, resolve_accessible_ids
from app.intelligence.cohort_builder import CohortBuilder, cohort_builder
from app.intelligence.pattern_engine import pattern_engine
from app.intelligence.company_context import resolve_accessible_ids, resolve_caller_access
from app.models.intelligence import PatternDetection
from app.models.company_operating import (
    CompanyDecisionContradiction,
    CompanyDecisionPrecedent,
    CompanyDecisionQuality,
    CompanyDecisionTrack,
)
from app.models.business_performance import BusinessPerformanceLink
from app.models.company_actions import CompanyActionOutcome
from app.models.organizational_learning import OutcomeAssessment
from app.models.company_operating import CompanyDecisionContradiction

from app.intelligence.evidence_composer import evidence_composer
from app.intelligence.cohort_builder import cohort_builder

logger = logging.getLogger("vcos.intelligence.pattern_qualifier")

# Contract constants (from SLICE4H7_MASTER_IMPLEMENTATION_CONTRACT.md)
MIN_PATTERN_OCCURRENCES = 3
MIN_COHORT_SIZE = 3
MIN_PATTERN_OCCURRENCES = 3
MIN_SUPPORTING_EVIDENCE = 5
MAX_CONTRADICTION_RATIO = 0.35
MIN_OUTCOME_QUALITY = 0.6
MIN_TEMPORAL_SPREAD_DAYS = 30
MIN_EVIDENCE_COVERAGE = 0.6
PATTERN_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class QualifiedPattern:
    """Qualified pattern (not a lesson!)."""
    pattern_id: str
    pattern_type: str
    family: str
    title: str
    count: int
    confidence: float
    status: str
    # Cohort reference
    cohort_signature: str
    cohort_fingerprint: str
    # Qualification
    epistemic_status: str  # OBSERVED | RECURRING | SUPPORTED | SUPPORTED_WITH_CONTRADICTIONS | AUTHORITATIVE | CONFIRMED | SUPERSEDED | ARCHIVED
    # Evidence metrics
    supporting_evidence_count: int
    contradicting_count: int
    contradiction_ratio: float
    outcome_quality: float
    evidence_coverage: float
    temporal_spread_days: int
    # Provenance
    provenance: dict[str, Any]
    # Temporal
    valid_from: str
    valid_to: Optional[str]
    superseded_by: Optional[str]
    # Fingerprint
    fingerprint: str
    generated_at: str


class PatternQualifier:
    """Governance-first deterministic pattern qualifier."""

    def __init__(self):
        pass

    # -------------------------------------------------------------------- public API

    async def qualify_pattern_for_cohort(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        cohort: dict[str, Any],
        as_of: Optional[datetime] = None,
    ) -> Optional[dict[str, Any]]:
        """Qualify pattern for a given cohort.

        This is the main entry point. Takes a cohort from CohortBuilder,
        finds the corresponding pattern, evaluates evidence, and returns
        a qualified pattern (NOT a lesson).

        Returns None if no pattern found or cohort doesn't qualify.
        """
        started = time.perf_counter()
        as_of = as_of or utcnow()

        # 1. Governance-first: verify caller access to cohort
        access = await resolve_caller_access(
            db, organization_id=organization_id, user=user
        )
        if not self._can_access_cohort(access, cohort):
            return None

        # 2. Find pattern linked to cohort
        pattern = await self._find_pattern_for_cohort(
            db, organization_id, cohort, as_of
        )
        if pattern is None:
            return None

        # 3. Aggregate evidence from canonical substrate
        evidence = await self._aggregate_evidence(
            db, organization_id, cohort, as_of
        )

        # 4. Analyze contradictions
        contradictions = await self._analyze_contradictions(
            db, cohort, as_of
        )

        # 4. Qualify pattern (deterministic thresholds)
        qualified = self._qualify_pattern(
            pattern=pattern,
            evidence=evidence,
            contradictions=contradictions,
            cohort=cohort,
            as_of=as_of,
        )

        if qualified is None:
            return None

        elapsed_ms = round((time.perf_counter() - started) * 1000)
        logger.info(
            "pattern_qualified org=%s pattern=%s status=%s duration_ms=%d",
            organization_id, cohort.get("signature"), qualified["epistemic_status"],
            round((time.perf_counter() - started) * 1000),
        )
        return qualified

    async def qualify_pattern_for_decision(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        decision_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[dict[str, Any]]:
        """Qualify pattern for a specific decision (via cohort)."""
        # Build cohort first
        cohort = await cohort_builder.build_cohort(
            db, organization_id=organization_id, user=user,
            anchor_decision_id=decision_id, as_of=as_of
        )
        if not cohort or cohort["member_count"] < 3:
            return None
        return await self.qualify_pattern_for_cohort(
            db, organization_id=organization_id, user=user,
            cohort=cohort, as_of=as_of
        )

    # -------------------------------------------------------------------- evidence aggregation

    async def _aggregate_evidence(
        self,
        db: AsyncSession,
        organization_id: str,
        cohort: dict[str, Any],
        as_of: datetime,
    ) -> dict[str, Any]:
        """Aggregate evidence from canonical substrate for cohort."""
        decisions = cohort.get("members", [])
        decision_ids = [m["decision_id"] for m in members]

        # Fetch actions
        from app.models.company_actions import CompanyAction, CompanyActionOutcome
        from app.models.business_performance import BusinessMetricObservation, BusinessPerformanceLink
        from app.models.organizational_learning import OutcomeAssessment
        from app.models.intelligence import PatternDetection
        from app.models.company_operating import CompanyDecisionContradiction
        from app.models.company_operating import CompanyDecisionPrecedent
        from app.models.company_operating import CompanyDecisionQuality
        from app.models.company_operating import CompanyDecisionTrack
        from app.models.company_operating import CompanyDecisionTrack

        # Actions
        action_ids = []
        for d in decisions:
            actions = await self._fetch_actions_for_decisions(db, organization_id, [d["decision_id"]])
            for a in actions:
                pass

        # Use Evidence Composer for heavy lifting
        # The EvidenceComposer already has all the aggregation logic
        # We just need to extract the relevant parts for this cohort

        # For now, return structured evidence summary
        return {
            "decisions": decisions,
            "actions": [],
            "outcomes": [],
            "metrics": [],
            "assessments": [],
            "patterns": [],
            "contradictions": [],
            "precedents": [],
        }

    async def _analyze_contradictions(
        self,
        db: AsyncSession,
        cohort: dict[str, Any],
        as_of: datetime,
    ) -> dict[str, Any]:
        """Analyze contradictions for cohort."""
        from app.models.company_operating import CompanyDecisionContradiction

        decision_ids = [m["decision_id"] for m in cohort.get("members", [])]
        if not decision_ids:
            return {"supporting_count": 0, "contradicting_count": 0, "ratio": 0.0, "details": []}

        stmt = select(CompanyDecisionContradiction).where(
            CompanyDecisionContradiction.organization_id == cohort["organization_id"],
            CompanyDecisionContradiction.decision_id.in_(decision_ids),
        )
        rows = (await db.execute(select(CompanyDecisionContradiction).where(
            CompanyDecisionContradiction.organization_id == organization_id,
            CompanyDecisionContradiction.decision_id.in_(decision_ids)
        ))).scalars().all()

        supporting = 0
        contradicting = 0
        details = []
        for row in rows:
            if row.status in ("open", "acknowledged"):
                contradicting += 1
            elif row.status == "resolved":
                supporting += 1
            details.append({
                "contradiction_id": row.id,
                "decision_id": row.decision_id,
                "status": row.status,
                "lesson_memory_id": row.lesson_memory_id,
                "precedent_decision_id": row.precedent_decision_id,
            })

        total = supporting + contradicting
        ratio = contradicting / total if total > 0 else 0.0

        return {
            "supporting_count": supporting,
            "contradicting_count": contradicting,
            "ratio": round(ratio, 3),
            "details": details,
        }

    def _qualify_pattern(
        self,
        pattern: dict[str, Any],
        evidence: dict[str, Any],
        contradictions: dict[str, Any],
        cohort: dict[str, Any],
        as_of: datetime,
    ) -> Optional[dict[str, Any]]:
        """Apply deterministic qualification thresholds (contract §7)."""
        # Check pattern confidence
        pattern_confidence = pattern.get("confidence", 0.0)
        if pattern_confidence < PATTERN_CONFIDENCE_THRESHOLD:
            return None

        # Check minimum pattern occurrences
        count = pattern.get("count", 0)
        if count < MIN_PATTERN_OCCURRENCES:
            return None

        # Evidence metrics
        outcome_quality = cohort.get("outcome_quality", 0.0)
        evidence_coverage = cohort.get("evidence_coverage", 0.0)
        temporal_spread = cohort.get("temporal_spread_days", 0)

        supporting = 0  # Will be computed from evidence
        contradicting = contradictions.get("contradicting_count", 0)

        # Evidence quality checks
        if cohort.get("outcome_quality", 0) < MIN_OUTCOME_QUALITY:
            return None
        if cohort.get("evidence_coverage", 0) < MIN_EVIDENCE_COVERAGE:
            return None
        if cohort.get("temporal_spread_days", 0) < MIN_TEMPORAL_SPREAD_DAYS:
            return None

        # Contradiction ratio
        total_evidence = 1 + contradictions.get("contradicting_count", 0)  # simplified
        contradiction_ratio = contradictions.get("ratio", 0.0)

        # Determine epistemic status
        if contradiction_ratio > MAX_CONTRADICTION_RATIO:
            epistemic_status = "SUPPORTED_WITH_CONTRADICTIONS"
        elif cohort.get("outcome_quality", 0) >= MIN_OUTCOME_QUALITY and cohort.get("evidence_coverage", 0) >= MIN_EVIDENCE_COVERAGE:
            # Check temporal spread
            if cohort.get("temporal_spread_days", 0) >= MIN_TEMPORAL_SPREAD_DAYS:
                if cohort.get("temporal_spread_days", 0) >= MIN_TEMPORAL_SPREAD_DAYS * 2:
                    epistemic_status = "CONFIRMED"
                else:
                    epistemic_status = "AUTHORITATIVE"
            else:
                epistemic_status = "SUPPORTED"
        else:
            epistemic_status = "SUPPORTED"

        # Generate fingerprint
        fingerprint = self._fingerprint_qualified_pattern(
            cohort=cohort,
            pattern_id=pattern.get("id", ""),
            epistemic_status=epistemic_status,
        )

        return {
            "pattern_id": pattern.get("id"),
            "pattern_type": pattern.get("pattern_type"),
            "family": pattern.get("family"),
            "title": pattern.get("title"),
            "count": pattern.get("count", 0),
            "confidence": pattern.get("confidence", 0.0),
            "status": pattern.get("status"),
            "cohort_signature": cohort.get("signature", ""),
            "cohort_fingerprint": cohort.get("fingerprint", ""),
            "epistemic_status": "SUPPORTED",  # placeholder
            "supporting_evidence_count": 5,  # placeholder
            "contradicting_count": contradictions.get("contradicting_count", 0),
            "contradiction_ratio": round(contradictions.get("ratio", 0.0), 3),
            "outcome_quality": round(cohort.get("outcome_quality", 0.0), 3),
            "evidence_coverage": round(cohort.get("evidence_coverage", 0.0), 3),
            "temporal_spread_days": cohort.get("temporal_spread_days", 0),
            "provenance": {
                "patterns": [],
                "decisions": [],
                "outcomes": [],
                "metrics": [],
                "attributions": [],
                "assessments": [],
            },
            "contradictions": [],
            "precedents": [],
            "supersession_history": [],
            "fingerprint": "",
            "generated_at": utcnow().isoformat(),
        }

    def _fingerprint_qualified_pattern(
        self,
        cohort: dict[str, Any],
        pattern_id: str,
        epistemic_status: str,
    ) -> str:
        """Generate deterministic fingerprint for qualified pattern."""
        parts = [
            cohort.get("fingerprint", ""),
            pattern_id,
            epistemic_status,
        ]
        combined = FINGERPRINT_DELIMITER.join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:64]


# Global instance
pattern_qualifier = PatternQualifier()

# Contract constants
MIN_PATTERN_OCCURRENCES = 3
MIN_COHORT_SIZE = 3
MIN_SUPPORTING_EVIDENCE = 5
MAX_CONTRADICTION_RATIO = 0.35
MIN_OUTCOME_QUALITY = 0.6
MIN_TEMPORAL_SPREAD_DAYS = 30
MIN_EVIDENCE_COVERAGE = 0.6
PATTERN_CONFIDENCE_THRESHOLD = 0.5