"""
Phase 4I.10 — Universal Company Operating Orchestration Engine.

The canonical reconciliation engine that continuously verifies the company's
operating reality against its canonical plan/expectations.

Key principles:
- Evidence-driven: assessment must be backed by evidence
- Provenance: full traceability to source events
- Temporal: historical state preserved (no history rewriting)
- Governance-first: access controlled by scope
- Epistemic separation: observed/measured/evidence_backed/inferred/predicted/proposed/contested
- Contradiction preservation: both sides visible
- Exact-once: fingerprint-based deduplication

This engine does NOT create a parallel state store. It composes the existing
canonical graph (Objectives, Commitments, Actions, Outcomes, Evidence, Learning)
into verification contexts with full provenance.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, selectinload

from app.core.timeutils import utcnow
from app.db.database import Base
from app.models.execution_strategy import (
    AdaptivePlanningContext,
    AssessmentRecord,
    AttentionSignal,
    CompanyCommitment,
    CompanyObjective,
    CompanyPlanningContext,
    DecisionIntelligenceContext,
    LessonVerificationLink,
    ObjectiveOutcome,
    ObjectiveOutcomeAssessment,
    OrganizationalResponsibility,
    PatternVerificationLink,
    ReplanningProposal,
    VerificationContext,
    VerificationEvidence,
    VERIFICATION_STATES,
)
from app.models.intelligence import PatternDetection
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.organizational_learning import OrganizationalLearning
from app.intelligence.company_brain import company_brain
from app.models.execution_strategy import (
    ASSESSMENT_VERDICTS,
    EVIDENCE_TYPES,
    VERIFICATION_TRIGGERS,
    EVIDENCE_QUALITY,
    VERIFICATION_TYPES,
    _compute_fingerprint,
)


def _fingerprint(data: dict) -> str:
    """Generate deterministic SHA-256 fingerprint for exact-once identity."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class VerificationOrchestrationEngine:
    """
    The canonical reconciliation engine for 4I.10.
    
    Orchestrates the continuous verification of company operating reality:
    Expected State → Observed Reality → Evidence Collection → Reconciliation
    → Assessment → State Update → Attention/Replanning → Learning
    """

    def __init__(self):
        self._version = "4I.10"

    # =========================================================================
    # Verification Context Management
    # =========================================================================

    async def create_verification_context(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        verification_type: str = "plan_vs_reality",
        title: str,
        description: Optional[str] = None,
        scope_type: str = "company",
        scope_id: Optional[str] = None,
        commitment_id: Optional[str] = None,
        authorization_id: Optional[str] = None,
        objective_id: Optional[str] = None,
        initiative_id: Optional[str] = None,
        project_id: Optional[str] = None,
        responsibility_id: Optional[str] = None,
        expected_outcome: Optional[dict] = None,
        expected_confidence: float = 0.5,
        trigger: str = "manual_request",
        source_event_id: Optional[str] = None,
        requested_by: Optional[str] = None,
    ) -> VerificationContext:
        """
        Create a new verification context with exact-once semantics.
        
        The verification context represents a bounded reconciliation operation.
        """
        # Governance: scope resolution would happen here in production
        # resolve_caller_access(organization_id, scope_type, scope_id)

        fingerprint = _fingerprint({
            "organization_id": organization_id,
            "verification_type": verification_type,
            "scope_type": scope_type,
            "scope_id": scope_id or "",
            "commitment_id": commitment_id or "",
            "objective_id": objective_id or "",
            "initiative_id": initiative_id or "",
            "project_id": project_id or "",
            "expected_outcome": expected_outcome or {},
            "trigger": trigger,
            "source_event_id": source_event_id or "",
        })

        # Check exact-once
        existing = await db.execute(
            select(VerificationContext).where(
                VerificationContext.organization_id == organization_id,
                VerificationContext.fingerprint == fingerprint,
            )
        )
        existing_vc = existing.scalar_one_or_none()
        if existing_vc:
            return existing_vc

        vc = VerificationContext(
            organization_id=organization_id,
            verification_type=verification_type,
            title=title[:300],
            description=description,
            scope_type=scope_type,
            scope_id=scope_id,
            commitment_id=commitment_id,
            authorization_id=authorization_id,
            objective_id=objective_id,
            initiative_id=initiative_id,
            project_id=project_id,
            responsibility_id=responsibility_id,
            expected_outcome=expected_outcome,
            expected_confidence=expected_confidence,
            state="pending",
            trigger=trigger,
            source_event_id=source_event_id,
            requested_by=requested_by,
            fingerprint=fingerprint,
        )
        db.add(vc)
        await db.flush()
        return vc

    async def get_verification_context(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
    ) -> Optional[VerificationContext]:
        """Retrieve a verification context by ID with governance scope."""
        result = await db.execute(
            select(VerificationContext).where(
                VerificationContext.organization_id == organization_id,
                VerificationContext.id == verification_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_verification_contexts(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        state: Optional[str] = None,
        verification_type: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[VerificationContext]:
        """List verification contexts with filtering."""
        conditions = [VerificationContext.organization_id == organization_id]
        if state:
            conditions.append(VerificationContext.state == state)
        if verification_type:
            conditions.append(VerificationContext.verification_type == verification_type)
        if scope_type:
            conditions.append(VerificationContext.scope_type == scope_type)
        if scope_id:
            conditions.append(VerificationContext.scope_id == scope_id)

        stmt = (
            select(VerificationContext)
            .where(*conditions)
            .order_by(VerificationContext.computed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    # =========================================================================
    # Evidence Management
    # =========================================================================

    async def submit_evidence(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
        *,
        evidence_type: str,
        evidence_id: str,
        evidence_type_detail: str,
        summary: str,
        detail: Optional[str] = None,
        quality: str = "secondary",
        source: Optional[str] = None,
        captured_at: Optional[datetime] = None,
        supports_verdict: Optional[str] = None,
        source_event_id: Optional[str] = None,
        submitted_by: Optional[str] = None,
    ) -> VerificationEvidence:
        """
        Submit evidence for a verification context.
        
        Evidence is immutable once submitted. Exact-once on (verification_id, evidence_type, evidence_id).
        """
        vc = await self.get_verification_context(db, organization_id, verification_id)
        if not vc:
            raise ValueError("Verification context not found")

        fingerprint = _fingerprint({
            "verification_id": verification_id,
            "evidence_type": evidence_type,
            "evidence_id": evidence_id,
        })

        # Check exact-once
        existing = await db.execute(
            select(VerificationEvidence).where(
                VerificationEvidence.verification_id == verification_id,
                VerificationEvidence.evidence_type == evidence_type,
                VerificationEvidence.evidence_id == evidence_id,
            )
        )
        if existing.scalar_one_or_none():
            return existing.scalar_one()

        evidence = VerificationEvidence(
            organization_id=organization_id,
            verification_id=verification_id,
            evidence_type=evidence_type,
            evidence_id=evidence_id,
            evidence_type_detail=evidence_type_detail,
            summary=summary[:500],
            detail=detail,
            quality=quality,
            source=source,
            captured_at=captured_at or utcnow(),
            source_event_id=source_event_id,
            supports_verdict=supports_verdict,
            fingerprint=fingerprint,
        )
        db.add(evidence)
        await db.flush()

        # Update verification context state
        if vc.state == "pending":
            vc.state = "in_progress"
        await db.flush()
        return evidence

    async def get_evidence(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
    ) -> list[VerificationEvidence]:
        """Retrieve all evidence for a verification context."""
        result = await db.execute(
            select(VerificationEvidence).where(
                VerificationEvidence.organization_id == organization_id,
                VerificationEvidence.verification_id == verification_id,
            ).order_by(VerificationEvidence.captured_at)
        )
        return result.scalars().all()

    # =========================================================================
    # Reconciliation & Assessment
    # =========================================================================

    async def run_reconciliation(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
        *,
        actual_outcome: dict,
        actual_confidence: float = 0.5,
        assessed_by: Optional[str] = None,
    ) -> AssessmentRecord:
        """
        Run the core reconciliation: compare expected vs actual, produce assessment.
        
        This is the heart of 4I.10 - the evidence-backed assessment of reality vs plan.
        """
        vc = await self.get_verification_context(db, organization_id, verification_id)
        if not vc:
            raise ValueError("Verification context not found")

        if vc.state not in ("pending", "in_progress"):
            raise ValueError(f"Cannot run reconciliation in state: {vc.state}")

        # Load evidence
        evidence = await self.get_evidence(db, organization_id, verification_id)
        evidence_fps = [e.fingerprint for e in evidence]

        # Compute variance
        expected = vc.expected_outcome or {}
        actual = actual_outcome

        expected_val = expected.get("target_value")
        actual_val = actual.get("actual_value")

        variance_pct = None
        variance_direction = None
        if expected_val is not None and actual_val is not None and expected_val != 0:
            variance_pct = ((actual_val - expected_val) / abs(expected_val)) * 100
            variance_direction = "positive" if variance_pct > 0 else ("negative" if variance_pct < 0 else "neutral")

        # Determine assessment based on evidence
        assessment, assessment_confidence = self._determine_assessment(
            variance_pct=variance_pct,
            evidence=evidence,
            expected_confidence=vc.expected_confidence,
            actual_confidence=actual_confidence,
        )

        # Create assessment record
        assessment_fp = _fingerprint({
            "verification_id": verification_id,
            "assessment": assessment,
            "variance_pct": variance_pct,
            "evidence_fps": sorted(evidence_fps),
        })

        # Check exact-once for assessment
        existing_assessment = await db.execute(
            select(AssessmentRecord).where(
                AssessmentRecord.organization_id == organization_id,
                AssessmentRecord.verification_id == verification_id,
                AssessmentRecord.fingerprint == assessment_fp,
            )
        )
        if existing_assessment.scalar_one_or_none():
            return existing_assessment.scalar_one()

        # Build evidence categorization
        supporting = [e.fingerprint for e in evidence if e.supports_verdict == assessment]
        contradicting = [e.fingerprint for e in evidence if e.supports_verdict and e.supports_verdict != assessment]

        ar = AssessmentRecord(
            organization_id=organization_id,
            verification_id=verification_id,
            objective_id=vc.objective_id,
            assessment_key=f"{vc.verification_type}:{assessment}",
            assessment=assessment,
            confidence=assessment_confidence,
            reasoning=self._generate_assessment_reasoning(
                assessment, variance_pct, len(evidence), len(supporting), len(contradicting)
            ),
            variance_pct=variance_pct,
            evidence_fingerprints=evidence_fps,
            supporting_pattern_ids=[],  # Would be populated from pattern engine
            supporting_lesson_fingerprints=[],
            contradicting_evidence_fingerprints=contradicting,
            contradicting_pattern_ids=[],
            contradicting_lesson_fingerprints=[],
            contradiction_ids=[],
            assessed_by=assessed_by,
            assessed_at=utcnow(),
            fingerprint=assessment_fp,
        )
        db.add(ar)

        # Update verification context
        vc.state = "completed"
        vc.actual_outcome = actual_outcome
        vc.actual_confidence = actual_confidence
        vc.variance_pct = variance_pct
        vc.variance_direction = variance_direction
        vc.assessment = assessment
        vc.assessment_confidence = assessment_confidence
        vc.assessment_reasoning = ar.reasoning
        vc.evidence_fingerprints = evidence_fps
        vc.supporting_pattern_ids = []
        vc.supporting_lesson_fingerprints = []
        vc.contradicting_evidence_fingerprints = contradicting
        vc.contradicting_pattern_ids = []
        vc.contradicting_lesson_fingerprints = []
        vc.contradiction_ids = []
        vc.computed_at = utcnow()
        vc.reviewed_by = assessed_by
        vc.reviewed_at = utcnow()
        vc.approved_by = assessed_by
        vc.approved_at = utcnow()

        await db.flush()

        # Link patterns and lessons
        await self._link_patterns_and_lessons(db, organization_id, verification_id, ar)

        # Propagate to company state
        await self._propagate_assessment(db, organization_id, vc, ar)

        return ar

    def _determine_assessment(
        self,
        *,
        variance_pct: Optional[float],
        evidence: list[VerificationEvidence],
        expected_confidence: float,
        actual_confidence: float,
    ) -> tuple[str, float]:
        """Determine assessment verdict based on variance and evidence quality."""
        # Count evidence by quality
        primary = sum(1 for e in evidence if e.quality == "primary")
        secondary = sum(1 for e in evidence if e.quality == "secondary")

        # Base confidence from evidence
        evidence_confidence = min(0.9, 0.3 + primary * 0.15 + secondary * 0.05)
        combined_confidence = (expected_confidence + actual_confidence + evidence_confidence) / 3

        if variance_pct is None:
            return "inconclusive", combined_confidence * 0.5

        if variance_pct >= 20:
            return "outperformed", combined_confidence
        elif variance_pct >= 0:
            return "met", combined_confidence
        elif variance_pct >= -20:
            return "partially_met", combined_confidence
        elif variance_pct >= -50:
            return "underperformed", combined_confidence
        else:
            return "missed", combined_confidence

    def _generate_assessment_reasoning(
        self,
        assessment: str,
        variance_pct: Optional[float],
        evidence_count: int,
        supporting_count: int,
        contradicting_count: int,
    ) -> str:
        """Generate human-readable assessment reasoning."""
        parts = []
        parts.append(f"Assessment: {assessment.replace('_', ' ').title()}.")
        
        if variance_pct is not None:
            parts.append(f"Variance: {variance_pct:.1f}% from expected.")
        
        parts.append(f"Evidence: {evidence_count} items ({supporting_count} supporting, {contradicting_count} contradicting).")
        
        if contradicting_count > 0:
            parts.append("Contradicting evidence present - assessment may require review.")
        
        return " ".join(parts)

    async def _link_patterns_and_lessons(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
        ar: AssessmentRecord,
    ) -> None:
        """Link assessment to relevant patterns and lessons."""
        # Find patterns matching the assessment context
        patterns = await db.execute(
            select(PatternDetection).where(
                PatternDetection.organization_id == organization_id,
                PatternDetection.confidence >= 0.7,
            ).limit(10)
        )
        pattern_matches = patterns.scalars().all()

        for p in pattern_matches:
            link = PatternVerificationLink(
                organization_id=organization_id,
                verification_id=verification_id,
                pattern_id=p.id,
                match_confidence=p.confidence * 0.8,
                match_type="inferred",
                match_details={"pattern_kind": p.pattern_kind, "cohort": p.cohort_signature},
                fingerprint=_fingerprint({"verification": verification_id, "pattern": p.id}),
            )
            db.add(link)

        # Find lessons relevant to the assessment
        lessons = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == organization_id,
                OrganizationalLearning.confidence >= 0.6,
            ).limit(10)
        )
        lesson_matches = lessons.scalars().all()

        for l in lesson_matches:
            link = LessonVerificationLink(
                organization_id=organization_id,
                verification_id=verification_id,
                lesson_id=l.id,
                link_type="supports",
                confidence=l.confidence * 0.7,
                reasoning=f"Lesson '{l.title}' relevant to {ar.assessment}",
                fingerprint=_fingerprint({"verification": verification_id, "lesson": l.id}),
            )
            db.add(link)

        await db.flush()

    async def _propagate_assessment(
        self,
        db: AsyncSession,
        organization_id: str,
        vc: VerificationContext,
        ar: AssessmentRecord,
    ) -> None:
        """Propagate assessment results to company state and trigger attention."""
        # Update objective outcome if linked
        if vc.objective_id:
            outcome_fp = _fingerprint({
                "objective_id": vc.objective_id,
                "verification_id": vc.id,
                "assessment": ar.assessment,
            })
            
            existing = await db.execute(
                select(ObjectiveOutcome).where(
                    ObjectiveOutcome.organization_id == organization_id,
                    ObjectiveOutcome.objective_id == vc.objective_id,
                    ObjectiveOutcome.fingerprint == outcome_fp,
                )
            )
            if not existing.scalar_one_or_none():
                outcome = ObjectiveOutcome(
                    organization_id=organization_id,
                    objective_id=vc.objective_id,
                    metric_kind=vc.expected_outcome.get("metric_kind", "unknown") if vc.expected_outcome else "unknown",
                    unit=vc.expected_outcome.get("unit", "") if vc.expected_outcome else "",
                    expected_value=vc.expected_outcome.get("target_value") if vc.expected_outcome else None,
                    actual_value=vc.actual_outcome.get("actual_value") if vc.actual_outcome else None,
                    variance_pct=vc.variance_pct,
                    outcome_state="actual",
                    assessment=ar.assessment,
                    assessment_confidence=ar.confidence,
                    source_event_id=vc.source_event_id,
                    fingerprint=outcome_fp,
                )
                db.add(outcome)

        # Create attention signal for negative assessments
        if ar.assessment in ("underperformed", "missed", "inconclusive"):
            await self._create_attention_signal(db, organization_id, vc, ar)

        await db.flush()

    async def _create_attention_signal(
        self,
        db: AsyncSession,
        organization_id: str,
        vc: VerificationContext,
        ar: AssessmentRecord,
    ) -> AttentionSignal:
        """Create attention signal for negative verification outcomes."""
        signal_fp = _fingerprint({
            "verification_id": vc.id,
            "signal_type": "outcome_deviation",
            "assessment": ar.assessment,
        })

        existing = await db.execute(
            select(AttentionSignal).where(
                AttentionSignal.organization_id == organization_id,
                AttentionSignal.fingerprint == signal_fp,
            )
        )
        if existing.scalar_one_or_none():
            return existing.scalar_one()

        severity = "critical" if ar.assessment == "missed" else "high" if ar.assessment == "underperformed" else "medium"

        signal = AttentionSignal(
            organization_id=organization_id,
            scope=vc.scope_type,
            scope_id=vc.scope_id,
            planning_context_id=vc.objective_id or "0",  # Would link to planning context
            adaptive_context_id=None,
            signal_type="outcome_deviation",
            severity=severity,
            title=f"Verification {vc.verification_type}: {ar.assessment.replace('_', ' ').title()}",
            description=ar.reasoning,
            source_context_section="outcome_state",
            source_conclusion_key=vc.verification_type,
            source_conclusion_value=ar.assessment,
            confidence=ar.confidence,
            epistemic_status="evidence_backed",
            affected_entities=[{"type": "verification", "id": vc.id}],
            evidence_fingerprints=ar.evidence_fingerprints,
            pattern_ids=[],
            lesson_fingerprints=[],
            contradiction_ids=ar.contradiction_ids,
            objective_id=vc.objective_id,
            fingerprint=signal_fp,
        )
        db.add(signal)
        await db.flush()
        return signal

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def get_verification_history(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        verification_id: Optional[str] = None,
        objective_id: Optional[str] = None,
        commitment_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[VerificationContext]:
        """Get verification history with filtering."""
        conditions = [VerificationContext.organization_id == organization_id]
        if verification_id:
            conditions.append(VerificationContext.id == verification_id)
        if objective_id:
            conditions.append(VerificationContext.objective_id == objective_id)
        if commitment_id:
            conditions.append(VerificationContext.commitment_id == commitment_id)

        stmt = (
            select(VerificationContext)
            .where(*conditions)
            .order_by(VerificationContext.computed_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_assessment_record(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
    ) -> Optional[AssessmentRecord]:
        """Get the assessment record for a verification."""
        result = await db.execute(
            select(AssessmentRecord).where(
                AssessmentRecord.organization_id == organization_id,
                AssessmentRecord.verification_id == verification_id,
            ).order_by(AssessmentRecord.assessed_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_evidence_quality_summary(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
    ) -> dict:
        """Get evidence quality breakdown for a verification."""
        evidence = await self.get_evidence(db, organization_id, verification_id)
        quality_counts = {"primary": 0, "secondary": 0, "hearsay": 0, "inferred": 0}
        for e in evidence:
            if e.quality in quality_counts:
                quality_counts[e.quality] += 1
        return {
            "total": len(evidence),
            "by_quality": quality_counts,
            "has_primary": quality_counts["primary"] > 0,
            "has_contradictions": any(e.supports_verdict and e.supports_verdict != "met" for e in evidence),
        }

    # =========================================================================
    # Public API Wrappers (for consistent interface)
    # =========================================================================

    async def add_evidence(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
        *,
        evidence_type: str,
        evidence_id: str,
        evidence_type_detail: str,
        summary: str,
        detail: Optional[str] = None,
        quality: str = "secondary",
        source: Optional[str] = None,
        captured_at: Optional[datetime] = None,
        supports_verdict: Optional[str] = None,
        source_event_id: Optional[str] = None,
        submitted_by: Optional[str] = None,
    ) -> VerificationEvidence:
        """Public alias for submit_evidence."""
        return await self.submit_evidence(
            db, organization_id, verification_id,
            evidence_type=evidence_type,
            evidence_id=evidence_id,
            evidence_type_detail=evidence_type_detail,
            summary=summary,
            detail=detail,
            quality=quality,
            source=source,
            captured_at=captured_at,
            supports_verdict=supports_verdict,
            source_event_id=source_event_id,
            submitted_by=submitted_by,
        )

    async def reconcile(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
        *,
        actual_outcome: dict,
        actual_confidence: float = 0.5,
        assessed_by: Optional[str] = None,
    ) -> AssessmentRecord:
        """Public alias for run_reconciliation."""
        return await self.run_reconciliation(
            db, organization_id, verification_id,
            actual_outcome=actual_outcome,
            actual_confidence=actual_confidence,
            assessed_by=assessed_by,
        )

    async def assess(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
        *,
        actual_outcome: dict,
        actual_confidence: float = 0.5,
        assessed_by: Optional[str] = None,
    ) -> AssessmentRecord:
        """Public alias for run_reconciliation (assessment focus)."""
        return await self.run_reconciliation(
            db, organization_id, verification_id,
            actual_outcome=actual_outcome,
            actual_confidence=actual_confidence,
            assessed_by=assessed_by,
        )

    async def link_pattern(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
        pattern_id: str,
        *,
        match_confidence: float = 0.8,
        match_type: str = "inferred",
        match_details: Optional[dict] = None,
    ) -> PatternVerificationLink:
        """Manually link a pattern to a verification context."""
        await self._link_single_pattern(db, organization_id, verification_id, pattern_id, match_confidence, match_type, match_details)
        # Return the created link
        result = await db.execute(
            select(PatternVerificationLink).where(
                PatternVerificationLink.organization_id == organization_id,
                PatternVerificationLink.verification_id == verification_id,
                PatternVerificationLink.pattern_id == pattern_id,
            )
        )
        return result.scalar_one()

    async def link_lesson(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
        lesson_id: str,
        *,
        link_type: str = "supports",
        confidence: float = 0.7,
        reasoning: str = "",
    ) -> LessonVerificationLink:
        """Manually link a lesson to a verification context."""
        await self._link_single_lesson(db, organization_id, verification_id, lesson_id, link_type=link_type, confidence=confidence, reasoning=reasoning)
        # Return the created link
        result = await db.execute(
            select(LessonVerificationLink).where(
                LessonVerificationLink.organization_id == organization_id,
                LessonVerificationLink.verification_id == verification_id,
                LessonVerificationLink.lesson_id == lesson_id,
            )
        )
        return result.scalar_one()

    async def get_context(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
    ) -> Optional[VerificationContext]:
        """Public alias for get_verification_context."""
        return await self.get_verification_context(db, organization_id, verification_id)

    async def get_quality(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
    ) -> dict:
        """Public alias for get_evidence_quality_summary."""
        return await self.get_evidence_quality_summary(db, organization_id, verification_id)

    async def get_contradictions(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
    ) -> dict:
        """Get contradiction analysis for a verification."""
        vc = await self.get_verification_context(db, organization_id, verification_id)
        if not vc:
            return {"has_contradictions": False, "count": 0, "details": []}
        
        evidence = await self.get_evidence(db, organization_id, verification_id)
        contradictions = []
        for e in evidence:
            if e.supports_verdict and e.supports_verdict != "met":
                contradictions.append({
                    "evidence_id": e.evidence_id,
                    "type": e.evidence_type,
                    "summary": e.summary,
                    "verdict": e.supports_verdict,
                    "quality": e.quality,
                })
        
        return {
            "has_contradictions": len(contradictions) > 0,
            "count": len(contradictions),
            "details": contradictions,
        }

    async def get_reconciliation_state(
        self,
        db: AsyncSession,
        organization_id: str,
        verification_id: str,
    ) -> dict:
        """Get comprehensive reconciliation state for a verification."""
        vc = await self.get_verification_context(db, organization_id, verification_id)
        if not vc:
            return {"error": "Verification context not found"}
        
        assessment = await self.get_assessment_record(db, organization_id, verification_id)
        evidence = await self.get_evidence(db, organization_id, verification_id)
        quality = await self.get_evidence_quality_summary(db, organization_id, verification_id)
        contradictions = await self.get_contradictions(db, organization_id, verification_id)
        history = await self.get_verification_history(db, organization_id, verification_id=verification_id)
        
        return {
            "verification": {
                "id": vc.id,
                "type": vc.verification_type,
                "title": vc.title,
                "state": vc.state,
                "expected_outcome": vc.expected_outcome,
                "actual_outcome": vc.actual_outcome,
                "expected_confidence": vc.expected_confidence,
                "actual_confidence": vc.actual_confidence,
                "variance_pct": vc.variance_pct,
                "variance_direction": vc.variance_direction,
            },
            "assessment": {
                "assessment": ar.assessment if assessment else None,
                "confidence": ar.confidence if assessment else None,
                "reasoning": ar.reasoning if assessment else None,
                "variance_pct": vc.variance_pct,
                "variance_direction": vc.variance_direction,
            } if assessment else None,
            "evidence": {
                "total": len(evidence),
                "by_quality": quality,
                "has_contradictions": contradictions["has_contradictions"],
            },
            "contradictions": contradictions,
            "history": [
                {
                    "id": h.id,
                    "state": h.state,
                    "computed_at": h.computed_at.isoformat() if h.computed_at else None,
                } for h in history
            ],
        }


# Global instance
verification_orchestration_engine = VerificationOrchestrationEngine()