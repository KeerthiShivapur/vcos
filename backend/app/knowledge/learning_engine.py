"""Slice 4E.7 — Universal Knowledge Operating Loop: the Organizational Learning
Engine that closes the company loop.

4E.6 established that knowledge can become governed action; this engine makes
the company LEARN from what actually happened:

    action/decision  ->  OutcomeAssessment (expected vs actual)
                      ->  OrganizationalLearning (exact-once, evidence-linked)
                      ->  canonical knowledge lifecycle (tested / confirmed / superseded)
                      ->  recommendation feedback (deterministic quality)
                      ->  company changes + operating insights + health signals

Every operation is deterministic rules + arithmetic over persisted evidence:
the LLM is never asked to decide what is true, who may see it, or what is
authorized. Learning NEVER silently rewrites company rules — it records an
audited, evidence-backed lesson and an explainable confidence adjustment.

All scans are bounded and tenant-scoped; every row is keyed by a stable
fingerprint so replays and concurrent replays are exact-once. The surface the
rest of the brain sees: knowledge/loop/* endpoints + the universal query
intents (learned / why / should / company_changes / decisions / companyhealth).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.intelligence.company_context import CallerAccess, resolve_caller_access
from app.knowledge.canonical_service import now_utc
from app.knowledge.intelligence_engine import _fingerprint
from app.knowledge.synthesis_engine import _json_loads
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeIntelInsight,
    KnowledgeRecommendation,
    KnowledgeRelation,
    KnowledgeTopic,
)
from app.models.organizational_learning import (
    CompanyChange,
    CompanyHealthSignal,
    DecisionOutcome,
    ImpactAssessment,
    KnowledgeClaimLifecycle,
    LearningEvidence,
    OperatingInsight,
    OrganizationalLearning,
    OutcomeAssessment,
    RecommendationOutcome,
)

logger = logging.getLogger("vcos.learning")

# ---------------------------------------------------------------------------
# deterministic constants
# ---------------------------------------------------------------------------

_CLAIM_STAGES: tuple[str, ...] = (
    "discovered", "candidate", "supported", "authoritative", "used",
    "tested", "confirmed", "superseded", "archived",
)
_STAGE_RANK = {stage: index for index, stage in enumerate(_CLAIM_STAGES)}
_LIFECYCLE_STAGES: tuple[str, ...] = (
    "discovered", "candidate", "supported", "authoritative", "confirmed",
    "superseded", "archived",
)

_DEPTH_MAX = 4
_NODES_MAX = 300
_ROWS_MAX = 400
_CHANGES_MAX = 80
_WINDOW_DAYS = 7
_DECISION_ALLOW = ("proposed",)  # open decisions awaiting finalization

# risk ladder (4E.7 §17): LOW -> automatic, MEDIUM -> approval, HIGH -> human
_AUTHORIZATION: dict[str, dict[str, str]] = {
    "low": {
        "level": "auto",
        "who": "system (governed policy)",
        "note": "Low risk: deterministic rules may act automatically within their governed scope.",
    },
    "medium": {
        "level": "approval",
        "who": "manager with scope access",
        "note": "Medium risk: requires explicit approval before any action executes.",
    },
    "high": {
        "level": "human",
        "who": "authorized human (leadership / designated approver)",
        "note": "High risk: requires explicit human authorization; no autonomous execution.",
    },
}

_CUSTOMER_TERMS = ("customer", "client", "account")
_FINANCIAL_TERMS = ("price", "pricing", "revenue", "forecast", "cost", "budget", "margin")


def _utcnow_iso() -> str:
    return now_utc().isoformat()


def _stage_rank(stage: Optional[str]) -> int:
    if not stage:
        return -1
    return _STAGE_RANK.get(stage, -1)


class LearningEngine:
    """One singleton — the 4E.7 organizational learning layer."""

    # ------------------------------------------------------------ access

    async def _access(self, db: AsyncSession, *, organization_id: str, user: Any) -> CallerAccess:
        if user is None:
            return CallerAccess(
                organization_id=organization_id,
                user_id="system",
                employee_id=None,
                org_wide=True,
            )
        return await resolve_caller_access(db, organization_id=organization_id, user=user)

    async def _claim_visible(
        self, db: AsyncSession, *, organization_id: str, claim: KnowledgeClaim, access: CallerAccess,
    ) -> bool:
        from app.knowledge.synthesis_engine import synthesis_engine

        if access.org_wide:
            return True
        if claim.subject_type == "project":
            return claim.subject_id == access.auth_project_id
        return True

    async def _visible_claims(
        self, db: AsyncSession, *, organization_id: str, claim_ids: list[str], access: CallerAccess,
    ) -> list[KnowledgeClaim]:
        if not claim_ids:
            return []
        rows = list(
            (
                await db.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.id.in_(claim_ids[:40]),
                    )
                )
            ).scalars().all()
        )
        return [c for c in rows if await self._claim_visible(db, organization_id=organization_id, claim=c, access=access)]

    @staticmethod
    def _action_scope_filter(access: CallerAccess):
        """Mirror of the 4E.6 action-center governance: non-org-wide callers
        only see project actions their governance grants them."""
        if access.org_wide:
            return None
        project_ids = set(access.project_ids) if access.project_ids else {"__none__"}
        return (CompanyAction.scope_type == "project", CompanyAction.scope_id.in_(project_ids))

    async def _actions_for_access(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess, limit: int = _ROWS_MAX,
    ) -> list[CompanyAction]:
        statement = select(CompanyAction).where(
            CompanyAction.organization_id == organization_id,
        )
        scope_filter = self._action_scope_filter(access)
        if scope_filter is not None:
            statement = statement.where(*scope_filter)
        return list((await db.execute(statement.limit(limit))).scalars().all())

    # ------------------------------------------------------ lifecycle ledger

    async def _stage_claim(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        claim_id: str,
        stage: str,
        reason: str,
        learning_id: Optional[str] = None,
        evidence: Optional[list[str]] = None,
        actor_id: Optional[str] = None,
    ) -> bool:
        """Append one governed stage transition to the lifecycle ledger.
        Never downgrades a claim's stage and never duplicates an identical
        (claim, stage, reason) step — replays are exact-once."""
        existing = (
            await db.execute(
                select(KnowledgeClaimLifecycle).where(
                    KnowledgeClaimLifecycle.organization_id == organization_id,
                    KnowledgeClaimLifecycle.claim_id == claim_id,
                    KnowledgeClaimLifecycle.stage == stage,
                    KnowledgeClaimLifecycle.reason == reason,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return False
        db.add(
            KnowledgeClaimLifecycle(
                organization_id=organization_id,
                claim_id=claim_id,
                stage=stage,
                reason=reason,
                evidence_json=json.dumps(evidence or []),
                learning_id=learning_id,
                actor_id=actor_id,
            )
        )
        return True

    async def _claim_stage(
        self, db: AsyncSession, *, organization_id: str, claim_id: str,
    ) -> tuple[Optional[str], Optional[datetime]]:
        row = (
            await db.execute(
                select(KnowledgeClaimLifecycle)
                .where(
                    KnowledgeClaimLifecycle.organization_id == organization_id,
                    KnowledgeClaimLifecycle.claim_id == claim_id,
                )
                .order_by(KnowledgeClaimLifecycle.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None, None
        return row.stage, ensure_aware(row.created_at)

    # ------------------------------------------------------------- outcomes

    @staticmethod
    def _variance(expected: float, actual: float) -> float:
        if expected == 0:
            return 100.0 if actual > 0 else 0.0
        return round((actual - expected) / expected * 100.0, 1)

    @staticmethod
    def _assess(variance: float) -> str:
        if variance >= 10.0:
            return "outperformed"
        if variance <= -10.0:
            return "underperformed"
        return "met"

    def _assessment_payload(self, row: OutcomeAssessment) -> dict[str, Any]:
        return {
            "id": row.id,
            "subject_type": row.subject_type,
            "subject_id": row.subject_id,
            "expected_metric": row.expected_metric,
            "expected_value": row.expected_value,
            "expected_units": row.expected_units,
            "actual_value": row.actual_value,
            "variance_pct": row.variance_pct,
            "assessment": row.assessment,
            "factors": _json_loads(row.factors_json, []),
            "summary": row.summary,
            "assessed_by": row.assessed_by,
            "assessed_at": ensure_aware(row.assessed_at).isoformat(),
        }

    async def assess_outcome(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        subject_type: str,
        subject_id: str,
        expected_metric: str,
        expected_value: float,
        actual_value: float,
        expected_units: Optional[str] = None,
        factors: Optional[list[str]] = None,
        summary: Optional[str] = None,
        user: Any = None,
    ) -> dict[str, Any]:
        """Record one expected-vs-actual assessment. Upserts per
        (subject_type, subject_id): re-recording refreshes, never duplicates."""
        if subject_type not in ("action", "decision"):
            raise ValueError(f"cannot assess subject_type '{subject_type}'")
        expected = max(0.0, float(expected_value or 0.0))
        actual = max(0.0, float(actual_value or 0.0))
        variance = self._variance(expected, actual)
        assessment = self._assess(variance)
        row = (
            await db.execute(
                select(OutcomeAssessment).where(
                    OutcomeAssessment.organization_id == organization_id,
                    OutcomeAssessment.subject_type == subject_type,
                    OutcomeAssessment.subject_id == subject_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = OutcomeAssessment(
                organization_id=organization_id,
                subject_type=subject_type,
                subject_id=subject_id,
                expected_metric=expected_metric or None,
                expected_value=expected,
                expected_units=expected_units,
                actual_value=actual,
                variance_pct=variance,
                assessment=assessment,
                factors_json=json.dumps(factors or []),
                summary=summary,
                assessed_by=getattr(user, "id", None) or "system",
            )
            db.add(row)
        else:
            row.expected_metric = expected_metric or row.expected_metric
            row.expected_value = expected
            row.expected_units = expected_units
            row.actual_value = actual
            row.variance_pct = variance
            row.assessment = assessment
            row.factors_json = json.dumps(factors or [])
            row.summary = summary
        await db.flush()
        return self._assessment_payload(row)

    # -------------------------------------------------------------- learning

    async def _learning_payload(
        self, db: AsyncSession, *, organization_id: str, row: OrganizationalLearning,
    ) -> dict[str, Any]:
        evidence_rows = list(
            (
                await db.execute(
                    select(LearningEvidence).where(
                        LearningEvidence.organization_id == organization_id,
                        LearningEvidence.learning_id == row.id,
                    ).order_by(LearningEvidence.recorded_at.asc()).limit(20)
                )
            ).scalars().all()
        )
        return {
            "id": row.id,
            "kind": row.kind,
            "fingerprint": row.fingerprint,
            "title": row.title,
            "lesson": row.lesson,
            "status": row.status,
            "lifecycle": row.lifecycle,
            "confidence": row.confidence,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "topic_id": row.topic_id,
            "topic_name": row.topic_name,
            "expectation": row.expectation,
            "observation": row.observation,
            "claims_updated": _json_loads(row.claims_updated_json, []),
            "recorded_by": row.recorded_by,
            "observed_at": ensure_aware(row.observed_at).isoformat(),
            "evidence": [
                {
                    "source_type": e.source_type,
                    "source_id": e.source_id,
                    "excerpt": e.excerpt,
                    "role": e.role,
                    "weight": e.weight,
                    "recorded_at": ensure_aware(e.recorded_at).isoformat(),
                }
                for e in evidence_rows
            ],
        }

    async def _add_evidence(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        learning_id: str,
        source_type: str,
        source_id: str,
        excerpt: Optional[str] = None,
        role: str = "primary",
        weight: float = 1.0,
    ) -> None:
        existing = (
            await db.execute(
                select(LearningEvidence).where(
                    LearningEvidence.organization_id == organization_id,
                    LearningEvidence.learning_id == learning_id,
                    LearningEvidence.source_type == source_type,
                    LearningEvidence.source_id == source_id,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        db.add(
            LearningEvidence(
                organization_id=organization_id,
                learning_id=learning_id,
                source_type=source_type,
                source_id=source_id,
                excerpt=excerpt,
                role=role,
                weight=weight,
            )
        )

    async def _learn(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        kind: str,
        source_type: Optional[str],
        source_id: Optional[str],
        title: str,
        lesson: Optional[str],
        expectation: Optional[str],
        observation: Optional[str],
        topic_id: Optional[str],
        topic_name: Optional[str],
        evidence: list[dict[str, Any]],
        confidence: float,
        claims_updated: Optional[list[str]] = None,
        actor_id: Optional[str] = None,
        observed_at: Optional[datetime] = None,
    ) -> OrganizationalLearning:
        """Create one exact-once lesson with its evidence rows."""
        fingerprint = _fingerprint(kind, source_type or "-", source_id or "-", title)
        existing = (
            await db.execute(
                select(OrganizationalLearning).where(
                    OrganizationalLearning.organization_id == organization_id,
                    OrganizationalLearning.kind == kind,
                    OrganizationalLearning.fingerprint == fingerprint,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = OrganizationalLearning(
            organization_id=organization_id,
            kind=kind,
            fingerprint=fingerprint,
            title=title[:240],
            lesson=lesson,
            status="active",
            lifecycle="discovered",
            confidence=max(0.0, min(1.0, confidence)),
            source_type=source_type,
            source_id=source_id,
            topic_id=topic_id,
            topic_name=topic_name,
            evidence_json=json.dumps([e.get("source_type") for e in evidence]),
            claims_updated_json=json.dumps(claims_updated or []),
            expectation=expectation,
            observation=observation,
            recorded_by=actor_id or "system",
            observed_at=observed_at or now_utc(),
        )
        db.add(row)
        await db.flush()
        for evidence_row in evidence:
            await self._add_evidence(
                db,
                organization_id=organization_id,
                learning_id=row.id,
                source_type=evidence_row.get("source_type") or "unknown",
                source_id=evidence_row.get("source_id") or "-",
                excerpt=evidence_row.get("excerpt"),
                role=evidence_row.get("role", "primary"),
                weight=float(evidence_row.get("weight", 1.0)),
            )
        return row

    async def _update_claims_from_lesson(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        learning_id: str,
        claim_ids: list[str],
        stage: str,
        reason: str,
        actor_id: Optional[str] = None,
    ) -> list[str]:
        """Advance linked canonical claims to a lifecycle stage (governed,
        never downgrading). Returns the claim ids actually advanced."""
        advanced: list[str] = []
        if not claim_ids:
            return advanced
        claims = list(
            (
                await db.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.id.in_(claim_ids[:40]),
                    )
                )
            ).scalars().all()
        )
        for claim in claims:
            if claim.status == "superseded":
                continue
            current, _ = await self._claim_stage(
                db, organization_id=organization_id, claim_id=claim.id,
            )
            if _stage_rank(current) >= _stage_rank(stage):
                continue
            if await self._stage_claim(
                db,
                organization_id=organization_id,
                claim_id=claim.id,
                stage=stage,
                reason=reason,
                learning_id=learning_id,
                evidence=[learning_id],
                actor_id=actor_id,
            ):
                advanced.append(claim.id)
        return advanced

    # ------------------------------------------- outcome -> lesson -> knowledge

    async def learn_from_outcome(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        action_id: str,
        user: Any = None,
    ) -> dict[str, Any]:
        """The heart of the loop: a verified action's outcome becomes a
        lesson, evidence-backed and idempotent.

        Chain: assessment -> OrganizationalLearning (+LearningEvidence) ->
        canonical knowledge lifecycle (tested / confirmed) -> recommendation
        outcome feedback -> learning-opportunity / company-change signals.
        """
        action = (
            await db.execute(
                select(CompanyAction).where(
                    CompanyAction.organization_id == organization_id,
                    CompanyAction.id == action_id,
                )
            )
        ).scalar_one_or_none()
        if action is None:
            raise ValueError(f"action '{action_id}' does not exist")
        if action.state not in ("completed", "verified"):
            raise ValueError(
                f"cannot learn from an action in state '{action.state}' — outcomes "
                "are only learned after verification"
            )
        assessment = (
            await db.execute(
                select(OutcomeAssessment).where(
                    OutcomeAssessment.organization_id == organization_id,
                    OutcomeAssessment.subject_type == "action",
                    OutcomeAssessment.subject_id == action_id,
                )
            )
        ).scalar_one_or_none()
        if assessment is None:
            raise ValueError(
                f"action '{action.title}' has no OutcomeAssessment — record "
                "expected vs actual before learning"
            )
        outcome = (
            await db.execute(
                select(CompanyActionOutcome).where(
                    CompanyActionOutcome.organization_id == organization_id,
                    CompanyActionOutcome.action_id == action_id,
                )
            )
        ).scalar_one_or_none()

        source_claim_ids = _json_loads(action.source_claim_ids_json, []) or []
        source_claims = list(
            (
                await db.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.id.in_(source_claim_ids[:40]),
                    )
                )
            ).scalars().all()
        ) if source_claim_ids else []
        topic_name = None
        topic_id = None
        for claim in source_claims:
            if claim.topic_id:
                topic_id = claim.topic_id
            if claim.topic_id:
                topic_row = (
                    await db.execute(
                        select(KnowledgeTopic).where(
                            KnowledgeTopic.organization_id == organization_id,
                            KnowledgeTopic.id == claim.topic_id,
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if topic_row is not None:
                    topic_name = topic_row.name
                    break
        if topic_name is None and source_claims:
            topic_name = source_claims[0].subject_id or None

        expectation = (assessment.expected_metric or "the intended result")
        outcome_text = (
            f"action '{action.title}' "
            f"{assessment.assessment} ({assessment.actual_value:.4g} vs expected "
            f"{assessment.expected_value:.4g} {assessment.expected_units or ''}). "
        ).strip()
        factors = _json_loads(assessment.factors_json, []) or []
        lesson_parts = [
            f"{outcome_text}",
            "Detected factors: " + ("; ".join(factors) if factors else "none recorded") + ". ",
        ]
        if action.why:
            lesson_parts.append(f"The action existed because: {action.why}. ")
        violated = None
        for factor in factors:
            if "technical" in factor.lower():
                violated = factor
                break
        if violated is None and assessment.assessment == "underperformed":
            violated = factors[0] if factors else None
        if violated:
            lesson_parts.append(
                f"Repeatable risk: '{violated}' recurs — the company should "
                "reconsider policies or processes touching it before the next "
                "similar action."
            )
        lesson = " ".join(p for p in lesson_parts if p)

        learning = await self._learn(
            db,
            organization_id=organization_id,
            kind="outcome_learning",
            source_type="action",
            source_id=action_id,
            title=f"Lesson: {action.title}",
            lesson=lesson,
            expectation=expectation,
            observation=f"{assessment.actual_value:.4g} {assessment.expected_units or ''} after verification",
            topic_id=topic_id,
            topic_name=topic_name,
            evidence=[
                {
                    "source_type": "assessment",
                    "source_id": assessment.id,
                    "excerpt": outcome_text,
                    "role": "primary",
                    "weight": 1.0,
                },
                {
                    "source_type": "action",
                    "source_id": action_id,
                    "excerpt": f"{action.action_type} '{action.title}' (state {action.state})",
                    "role": "primary",
                    "weight": 1.0,
                },
            ]
            + [
                {
                    "source_type": "claim",
                    "source_id": claim.id,
                    "excerpt": f"{claim.subject_id}: {claim.object_text}",
                    "role": "supporting",
                    "weight": 0.8,
                }
                for claim in source_claims[:10]
            ],
            confidence=0.7 if assessment.assessment in ("met", "outperformed") else 0.85,
            claims_updated=[c.id for c in source_claims],
            actor_id=getattr(user, "id", None) or "system",
            observed_at=now_utc(),
        )
        await db.flush()

        # canonical knowledge lifecycle: linked claims were TESTED against
        # reality; confirmed when the expectation was met or exceeded.
        advanced = await self._update_claims_from_lesson(
            db,
            organization_id=organization_id,
            learning_id=learning.id,
            claim_ids=[c.id for c in source_claims],
            stage="tested",
            reason="outcome learning — the claim was tested against reality",
            actor_id=getattr(user, "id", None) or "system",
        )
        if assessment.assessment in ("met", "outperformed") and source_claim_ids:
            confirmed_ids = await self._update_claims_from_lesson(
                db,
                organization_id=organization_id,
                learning_id=learning.id,
                claim_ids=[c.id for c in source_claims],
                stage="confirmed",
                reason="outcome learning — reality matched expectation",
                actor_id=getattr(user, "id", None) or "system",
            )
            advanced.extend(confirmed_ids)

        # recommendation feedback: the action's recommendation is measured.
        recommendation_feedback: Optional[dict[str, Any]] = None
        if action.source_recommendation_id:
            rec = (
                await db.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == organization_id,
                        KnowledgeRecommendation.id == action.source_recommendation_id,
                    )
                )
            ).scalar_one_or_none()
            if rec is not None:
                success = assessment.assessment in ("met", "outperformed")
                rec_outcome = (
                    await db.execute(
                        select(RecommendationOutcome).where(
                            RecommendationOutcome.organization_id == organization_id,
                            RecommendationOutcome.recommendation_id == rec.id,
                        )
                    )
                ).scalar_one_or_none()
                if rec_outcome is None:
                    rec_outcome = RecommendationOutcome(
                        organization_id=organization_id,
                        recommendation_id=rec.id,
                        kind=rec.kind,
                        action_id=action_id,
                        outcome_type="success" if success else "failure",
                        success=success,
                        effectiveness=float(outcome.effectiveness if outcome else (0.8 if success else 0.2)),
                        measured_by=getattr(user, "id", None) or "system",
                    )
                    db.add(rec_outcome)
                    await db.flush()
                recommendation_feedback = {
                    "recommendation_id": rec.id,
                    "kind": rec.kind,
                    "success": rec_outcome.success,
                    "effectiveness": rec_outcome.effectiveness,
                }

        # learning-opportunity signal when the outcome underperformed.
        if assessment.assessment == "underperformed":
            await self._record_learning_opportunity_insight(
                db, organization_id=organization_id, assessment=assessment,
                action=action, learning_id=learning.id, user=user,
            )

        # a normal company change: the company learned something.
        await self._record_change(
            db,
            organization_id=organization_id,
            change_type="normal",
            kind="learning",
            fingerprint_key=learning.id,
            title=f"Learned: {action.title}",
            detail=(lesson or "")[:400],
            what_changed="The company learned a lesson from a verified action",
            why_changed=outcome_text,
            evidence=[{"type": "learning", "id": learning.id}],
            impact=[{"type": "knowledge", "detail": f"{len(advanced)} claim(s) lifecycle advanced"}],
            source_type="learning",
            source_id=learning.id,
            domain="knowledge",
            actor_id=getattr(user, "id", None) or "system",
            occurred_at=ensure_aware(learning.observed_at),
        )

        payload = await self._learning_payload(db, organization_id=organization_id, row=learning)
        return {
            "learning": payload,
            "assessment": self._assessment_payload(assessment),
            "claims_advanced": advanced,
            "recommendation_feedback": recommendation_feedback,
        }

    async def _record_learning_opportunity_insight(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        assessment: OutcomeAssessment,
        action: Optional[CompanyAction],
        learning_id: Optional[str],
        user: Any,
    ) -> Optional[OperatingInsight]:
        fingerprint = _fingerprint("learn", assessment.id)
        existing = (
            await db.execute(
                select(OperatingInsight).where(
                    OperatingInsight.organization_id == organization_id,
                    OperatingInsight.category == "learning_opportunity",
                    OperatingInsight.fingerprint == fingerprint,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        title = f"Learn from {action.title if action else 'the underperformed outcome'}"
        detail = (
            f"The outcome underperformed its expectation ({assessment.actual_value:.4g} vs "
            f"{assessment.expected_value:.4g} {assessment.expected_units or ''}). "
            "Review the detected factors before the next similar action."
        )
        factors = _json_loads(assessment.factors_json, []) or []
        row = OperatingInsight(
            organization_id=organization_id,
            category="learning_opportunity",
            fingerprint=fingerprint,
            title=title[:240],
            detail=detail,
            why="An outcome underperformed its expectation — a lesson is available",
            impact="Future similar actions should account for the detected factors",
            evidence_json=json.dumps(
                [{"type": "assessment", "id": assessment.id}, {"type": "learning", "id": learning_id or ""}]
            ),
            severity="medium",
            risk="medium",
            authorization_level="auto",
            owner_id=action.assignee_id if action else None,
            status="active",
            source_type="assessment",
            source_id=assessment.id,
            reference_status="underperformed",
            reference_outcome="underperformed",
        )
        db.add(row)
        await db.flush()
        return row

    async def learn_from_decision(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision_id: str,
        expected_metric: str,
        expected_value: float,
        actual_value: float,
        expected_units: Optional[str] = None,
        factors: Optional[list[str]] = None,
        summary: Optional[str] = None,
        user: Any = None,
    ) -> dict[str, Any]:
        """Decision feedback loop: expected vs actual -> DecisionOutcome ->
        lesson -> decision-quality signal. Idempotent per decision."""
        from app.models.knowledge import Decision

        decision = (
            await db.execute(
                select(Decision).where(
                    Decision.organization_id == organization_id,
                    Decision.id == decision_id,
                )
            )
        ).scalar_one_or_none()
        if decision is None:
            raise ValueError(f"decision '{decision_id}' does not exist")

        expected = max(0.0, float(expected_value or 0.0))
        actual = max(0.0, float(actual_value or 0.0))
        variance = self._variance(expected, actual)
        assessment = self._assess(variance)
        row = (
            await db.execute(
                select(DecisionOutcome).where(
                    DecisionOutcome.organization_id == organization_id,
                    DecisionOutcome.decision_id == decision_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = DecisionOutcome(
                organization_id=organization_id,
                decision_id=decision_id,
                expected_metric=expected_metric or None,
                expected_value=expected,
                expected_units=expected_units,
                actual_value=actual,
                variance_pct=variance,
                assessment=assessment,
                outcome_type="success" if assessment in ("met", "outperformed") else "failure",
                factors_json=json.dumps(factors or []),
                summary=summary,
                measured_by=getattr(user, "id", None) or "system",
            )
            db.add(row)
        else:
            row.expected_metric = expected_metric or row.expected_metric
            row.expected_value = expected
            row.expected_units = expected_units
            row.actual_value = actual
            row.variance_pct = variance
            row.assessment = assessment
            row.outcome_type = "success" if assessment in ("met", "outperformed") else "failure"
            row.factors_json = json.dumps(factors or [])
            row.summary = summary
        await db.flush()

        lesson = (
            f"Decision '{decision.title}' {assessment} its expectation "
            f"({actual:.4g} vs expected {expected:.4g} {expected_units or ''}). "
            + ("Detected factors: " + "; ".join(factors or []) + ". ")
        )
        learning = await self._learn(
            db,
            organization_id=organization_id,
            kind="decision_learning",
            source_type="decision",
            source_id=decision_id,
            title=f"Decision lesson: {decision.title}",
            lesson=lesson,
            expectation=expected_metric or "the intended result",
            observation=f"{actual:.4g} {expected_units or ''}",
            topic_id=None,
            topic_name=decision.title,
            evidence=[
                {
                    "source_type": "decision",
                    "source_id": decision_id,
                    "excerpt": f"decision '{decision.title}' (status {decision.status})",
                    "role": "primary",
                    "weight": 1.0,
                },
                {
                    "source_type": "decision_outcome",
                    "source_id": row.id,
                    "excerpt": lesson,
                    "role": "primary",
                    "weight": 1.0,
                },
            ],
            confidence=0.7 if assessment in ("met", "outperformed") else 0.85,
            actor_id=getattr(user, "id", None) or "system",
        )
        await db.flush()
        await self._record_change(
            db,
            organization_id=organization_id,
            change_type="normal",
            kind="decision_outcome",
            fingerprint_key=learning.id,
            title=f"Decision measured: {decision.title}",
            detail=(lesson or "")[:400],
            what_changed=f"Decision '{decision.title}' was measured against reality",
            why_changed=f"{assessment} (variance {variance:+.1f}%)",
            evidence=[{"type": "learning", "id": learning.id}, {"type": "decision_outcome", "id": row.id}],
            impact=[],
            source_type="decision",
            source_id=decision_id,
            domain="governance",
            actor_id=getattr(user, "id", None) or "system",
            occurred_at=now_utc(),
        )
        return {
            "decision_outcome": {
                "id": row.id,
                "decision_id": decision_id,
                "expected_metric": row.expected_metric,
                "expected_value": row.expected_value,
                "expected_units": row.expected_units,
                "actual_value": row.actual_value,
                "variance_pct": row.variance_pct,
                "assessment": row.assessment,
                "outcome_type": row.outcome_type,
                "factors": factors or [],
                "summary": row.summary,
                "measured_at": ensure_aware(row.measured_at).isoformat(),
            },
            "learning": await self._learning_payload(db, organization_id=organization_id, row=learning),
        }

    async def recommendation_quality(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """Deterministic, explainable per-kind recommendation quality built
        from the outcome ledger — never a silent model rewrite."""
        rows = list(
            (
                await db.execute(
                    select(RecommendationOutcome).where(
                        RecommendationOutcome.organization_id == organization_id,
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        )
        by_kind: dict[str, list[RecommendationOutcome]] = {}
        for row in rows:
            by_kind.setdefault(row.kind, []).append(row)
        kinds = []
        for kind in sorted(by_kind):
            group = by_kind[kind]
            successes = sum(1 for r in group if r.success)
            rate = successes / len(group)
            kinds.append(
                {
                    "kind": kind,
                    "measured": len(group),
                    "success_rate": round(rate, 3),
                    "successes": successes,
                    "failures": len(group) - successes,
                    # explainable confidence adjustment, clamped — the company
                    # rules themselves are never rewritten autonomously.
                    "adjusted_confidence": round(min(0.95, max(0.2, 0.5 + (rate - 0.5) * 0.6)), 3),
                }
            )
        return {
            "kinds": kinds,
            "total_measured": len(rows),
            "generated_at": _utcnow_iso(),
        }

    async def record_contradiction_resolution(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        authoritative_claim_id: str,
        user: Any,
        reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """A contradiction was resolved by authority: the authoritative claim
        is retained and advanced; losing evidence is RETAINED as historical
        truth (never deleted); a lesson is recorded; the contradiction insight
        resolves and a correction insight is proposed."""
        topic = (
            await db.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == organization_id,
                    KnowledgeTopic.name == topic_name,
                )
            )
        ).scalar_one_or_none()
        if topic is None:
            raise ValueError(f"topic '{topic_name}' does not exist")
        claim = (
            await db.execute(
                select(KnowledgeClaim).where(
                    KnowledgeClaim.organization_id == organization_id,
                    KnowledgeClaim.id == authoritative_claim_id,
                )
            )
        ).scalar_one_or_none()
        if claim is None:
            raise ValueError("authoritative claim does not exist")

        # current understandng of the topic for the lesson
        active_claims = list(
            (
                await db.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.topic_id == topic.id,
                        KnowledgeClaim.status != "superseded",
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        )
        retained = [c for c in active_claims if c.id != claim.id]

        learning = await self._learn(
            db,
            organization_id=organization_id,
            kind="contradiction_resolution",
            source_type="topic",
            source_id=topic.id,
            title=f"Truth settled: {topic_name}",
            lesson=(
                f"'{claim.subject_id}: {claim.object_text}' is the authoritative "
                f"understanding of '{topic_name}' (authority level {claim.authority_level}). "
                "Conflicting claims are retained as historical evidence. "
                + (f"Reason: {reason}. " if reason else "")
            ),
            expectation="the authoritative claim resolves the conflict",
            observation=f"{len(retained)} conflicting claim(s) retained as history",
            topic_id=topic.id,
            topic_name=topic.name,
            evidence=[{"source_type": "claim", "source_id": claim.id, "role": "primary", "weight": 1.0}]
            + [{"source_type": "claim", "source_id": c.id, "role": "supporting", "weight": 0.8} for c in retained[:10]],
            confidence=0.8,
            claims_updated=[claim.id],
            actor_id=getattr(user, "id", None) or "system",
        )
        await db.flush()
        advanced = await self._update_claims_from_lesson(
            db,
            organization_id=organization_id,
            learning_id=learning.id,
            claim_ids=[claim.id],
            stage="authoritative",
            reason="contradiction resolved by authority ranking",
            actor_id=getattr(user, "id", None) or "system",
        )
        # the contradiction insight resolves (users steer the surface).
        fingerprint = _fingerprint("contra", topic.id)
        insight = (
            await db.execute(
                select(OperatingInsight).where(
                    OperatingInsight.organization_id == organization_id,
                    OperatingInsight.category == "contradiction",
                    OperatingInsight.fingerprint == fingerprint,
                    OperatingInsight.status == "active",
                )
            )
        ).scalar_one_or_none()
        if insight is not None:
            insight.status = "resolved"
            insight.resolved_at = now_utc()
            insight.resolved_by = getattr(user, "id", None) or "system"
        await self._record_change(
            db,
            organization_id=organization_id,
            change_type="important",
            kind="contradiction_resolved",
            fingerprint_key=learning.id,
            title=f"Contradiction resolved: {topic_name}",
            detail=f"The authoritative claim was retained; {len(retained)} conflicting claim(s) remain as historical evidence.",
            what_changed=f"The canonical understanding of '{topic_name}' was settled by authority",
            why_changed=reason or "authority ranking selected the authoritative claim",
            evidence=[{"type": "learning", "id": learning.id}, {"type": "claim", "id": claim.id}],
            impact=[{"type": "knowledge", "detail": "outdated claims remain visible as historical evidence"}],
            source_type="topic",
            source_id=topic.id,
            domain="knowledge",
            actor_id=getattr(user, "id", None) or "system",
            occurred_at=now_utc(),
        )
        return {
            "learning": await self._learning_payload(db, organization_id=organization_id, row=learning),
            "authoritative_claim_id": claim.id,
            "retained_conflicting": [c.id for c in retained],
            "claims_advanced": advanced,
        }

    async def learning_feed(
        self, db: AsyncSession, *, organization_id: str, user: Any,
        kind: Optional[str] = None, limit: int = 40,
    ) -> dict[str, Any]:
        """The company's learning feed (governed by visibility)."""
        access = await self._access(db, organization_id=organization_id, user=user)
        statement = (
            select(OrganizationalLearning)
            .where(OrganizationalLearning.organization_id == organization_id)
            .order_by(OrganizationalLearning.observed_at.desc())
            .limit(min(limit, 100))
        )
        if kind:
            statement = statement.where(OrganizationalLearning.kind == kind)
        rows = list((await db.execute(statement)).scalars().all())
        items = []
        allowed_action_ids: set[str] = set()
        if not access.org_wide:
            allowed_action_ids = {
                a.id for a in await self._actions_for_access(
                    db, organization_id=organization_id, access=access,
                )
            }
        for row in rows:
            claim_ids = _json_loads(row.claims_updated_json, []) or []
            visible_claims = await self._visible_claims(
                db, organization_id=organization_id, claim_ids=claim_ids, access=access,
            )
            if access.org_wide or visible_claims or claim_ids == []:
                # a scoped caller only inherits a lesson when its source entity
                # (the action it came from) is inside their granted project.
                if not access.org_wide:
                    if row.source_type == "action":
                        if row.source_id not in allowed_action_ids:
                            continue
                    elif row.source_type in ("claim", "topic"):
                        if not visible_claims:
                            continue
                    else:
                        continue
                items.append(await self._learning_payload(db, organization_id=organization_id, row=row))
        return {
            "intent": "learned",
            "items": items,
            "total": len(items),
            "scope": "org" if access.org_wide else "project",
            "generated_at": _utcnow_iso(),
        }

    # ------------------------------------------------------- company changes

    async def _record_change(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        change_type: str,
        kind: str,
        fingerprint_key: str,
        title: str,
        detail: Optional[str],
        what_changed: Optional[str],
        why_changed: Optional[str],
        evidence: list[dict[str, Any]],
        impact: list[dict[str, Any]],
        source_type: Optional[str],
        source_id: Optional[str],
        domain: Optional[str],
        actor_id: Optional[str],
        occurred_at: datetime,
        owner_id: Optional[str] = None,
        recommended_action: Optional[str] = None,
    ) -> Optional[CompanyChange]:
        fingerprint = _fingerprint(kind, fingerprint_key)
        existing = (
            await db.execute(
                select(CompanyChange).where(
                    CompanyChange.organization_id == organization_id,
                    CompanyChange.kind == kind,
                    CompanyChange.fingerprint == fingerprint,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = CompanyChange(
            organization_id=organization_id,
            change_type=change_type,
            kind=kind,
            fingerprint=fingerprint,
            title=title[:240],
            detail=detail,
            what_changed=what_changed,
            why_changed=why_changed,
            evidence_json=json.dumps(evidence),
            impact_json=json.dumps(impact),
            owner_id=owner_id,
            recommended_action=recommended_action,
            source_type=source_type,
            source_id=source_id,
            domain=domain,
            actor_id=actor_id,
            occurred_at=occurred_at,
        )
        db.add(row)
        await db.flush()
        return row

    async def company_changes(
        self, db: AsyncSession, *, organization_id: str, since_hours: int = 24, user: Any,
    ) -> dict[str, Any]:
        """Materialize + return the company "what changed?" feed. Deterministic,
        exact-once, bounded, and grouped critical / important / normal."""
        since = now_utc() - timedelta(hours=max(1, min(since_hours, 24 * 30)))
        access = await self._access(db, organization_id=organization_id, user=user)

        # 1) governed actions (bounded, ordered by recency) — scoped callers
        #    only see the actions their governance grants them.
        actions = list(
            (
                await db.execute(
                    select(CompanyAction)
                    .where(
                        CompanyAction.organization_id == organization_id,
                        CompanyAction.updated_at >= since,
                    )
                    .order_by(CompanyAction.updated_at.desc())
                    .limit(_ROWS_MAX)
                )
            ).scalars().all()
        )
        scope_filter = self._action_scope_filter(access)
        if scope_filter is not None:
            actions = [
                a for a in actions
                if a.scope_type == "project" and a.scope_id in (set(access.project_ids) if access.project_ids else {"__none__"})
            ]
        for action in actions:
            overdue = bool(
                action.due_at
                and action.state in ("ready", "in_progress", "awaiting_approval", "approved")
                and now_utc() > ensure_aware(action.due_at)
            )
            if action.escalation_level >= 1 or (action.state == "failed" and action.risk == "high"):
                await self._record_change(
                    db, organization_id=organization_id,
                    change_type="critical",
                    kind="action_critical",
                    fingerprint_key=f"critical:{action.id}",
                    title=f"{action.title}",
                    detail="An escalated or failed high-risk action needs leadership attention.",
                    what_changed=f"Action '{action.title}' is at escalation level {action.escalation_level}"
                    if action.escalation_level >= 2 else f"High-risk action '{action.title}' failed",
                    why_changed=action.fail_reason or action.blocked_reason or "escalated by policy",
                    evidence=[{"type": "action", "id": action.id}],
                    impact=[{"type": action.scope_type, "detail": action.scope_id or "org"}],
                    source_type="action",
                    source_id=action.id,
                    domain="execution",
                    actor_id=None,
                    occurred_at=ensure_aware(action.updated_at),
                    owner_id=action.assignee_id,
                    recommended_action="Leadership review of the escalated/failed action in the Action Center",
                )
            elif overdue or (action.state == "blocked" and action.risk != "low"):
                await self._record_change(
                    db, organization_id=organization_id,
                    change_type="important",
                    kind="action_delayed",
                    fingerprint_key=("overdue" if overdue else "blocked") + ":" + action.id,
                    title=f"{action.title}",
                    detail="An action is overdue or blocked — execution is at risk.",
                    what_changed=f"Action '{action.title}' is {'overdue' if overdue else 'blocked'}",
                    why_changed=action.blocked_reason or "missed its due date",
                    evidence=[{"type": "action", "id": action.id}],
                    impact=[{"type": action.scope_type, "detail": action.scope_id or "org"}],
                    source_type="action",
                    source_id=action.id,
                    domain="execution",
                    actor_id=None,
                    occurred_at=ensure_aware(action.updated_at),
                    owner_id=action.assignee_id,
                    recommended_action="Unblock or replan this action in the Action Center",
                )
            elif action.state == "verified" and action.verified_at and ensure_aware(action.verified_at) >= since:
                await self._record_change(
                    db, organization_id=organization_id,
                    change_type="normal",
                    kind="action_verified",
                    fingerprint_key=f"verified:{action.id}",
                    title=f"{action.title}",
                    detail="A governed action was completed and verified.",
                    what_changed=f"Action '{action.title}' was verified",
                    why_changed="execution completed and verified by a human",
                    evidence=[{"type": "action", "id": action.id}],
                    impact=[{"type": action.scope_type, "detail": action.scope_id or "org"}],
                    source_type="action",
                    source_id=action.id,
                    domain="execution",
                    actor_id=action.verified_by,
                    occurred_at=ensure_aware(action.verified_at),
                    owner_id=action.assignee_id,
                )

        # 2) knowledge supersessions (temporal truth movements)
        superseded = list(
            (
                await db.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.valid_to.isnot(None),
                        KnowledgeClaim.valid_to >= since,
                    )
                    .order_by(KnowledgeClaim.valid_to.desc())
                    .limit(_ROWS_MAX)
                )
            ).scalars().all()
        )
        for claim in superseded:
            if not access.org_wide:
                if not await self._claim_visible(db, organization_id=organization_id, claim=claim, access=access):
                    continue
            await self._record_change(
                db, organization_id=organization_id,
                change_type="important",
                kind="knowledge_superseded",
                fingerprint_key=f"superseded:{claim.id}",
                title=f"{claim.subject_id}: {claim.object_text}",
                detail="The company's understanding was superseded — the old truth remains in history.",
                what_changed=f"Claim '{claim.subject_id}: {claim.object_text}' was superseded",
                why_changed="newer evidence replaced the old understanding",
                evidence=[{"type": "claim", "id": claim.id}],
                impact=[{"type": "knowledge", "detail": claim.topic_id or claim.subject_id}],
                source_type="claim",
                source_id=claim.id,
                domain="knowledge",
                actor_id=None,
                occurred_at=ensure_aware(claim.valid_to),
                recommended_action="Review sources dependent on the superseded claim for impact",
            )

        # 3) active risk / contradiction perceptions become insights (already
        #    materialized) — surface them within the window.
        insights = list(
            (
                await db.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.organization_id == organization_id,
                        KnowledgeIntelInsight.status == "active",
                        KnowledgeIntelInsight.created_at >= since,
                    )
                    .order_by(KnowledgeIntelInsight.priority_score.desc())
                    .limit(_ROWS_MAX)
                )
            ).scalars().all()
        )
        for insight in insights:
            if insight.kind == "risk" and insight.severity in ("high", "critical"):
                await self._record_change(
                    db, organization_id=organization_id,
                    change_type="critical",
                    kind="emerging_risk",
                    fingerprint_key=f"risk:{insight.id}",
                    title=insight.title,
                    detail=insight.summary,
                    what_changed=f"An emerging risk was detected: {insight.title}",
                    why_changed="deterministic insight materialization",
                    evidence=[{"type": "insight", "id": insight.id}],
                    impact=[{"type": "knowledge", "detail": insight.topic_name or "org"}],
                    source_type="insight",
                    source_id=insight.id,
                    domain="risk",
                    actor_id=None,
                    occurred_at=ensure_aware(insight.created_at),
                    recommended_action="Review the risk insight and decide a governed response",
                )

        # 4) finalized decisions within the window (from decision_outcomes +
        #    lessons recorded above under kind decision_learning).
        rows = list(
            (
                await db.execute(
                    select(CompanyChange).where(
                        CompanyChange.organization_id == organization_id,
                        CompanyChange.occurred_at >= since,
                    )
                    .order_by(CompanyChange.occurred_at.desc())
                    .limit(_CHANGES_MAX)
                )
            ).scalars().all()
        )
        # Governance applies on the READ side too: change rows are materialized
        # once, and a scoped caller only inherits changes whose evidence they
        # may see (their project's actions / visible claims); org-wide signals
        # with no visible reference are indistinguishable from absent.
        if not access.org_wide:
            allowed_action_ids = {
                a.id for a in await self._actions_for_access(
                    db, organization_id=organization_id, access=access,
                )
            }
            learning_rows = {
                r.id: r for r in (
                    await db.execute(
                        select(OrganizationalLearning).where(
                            OrganizationalLearning.organization_id == organization_id,
                        ).limit(_ROWS_MAX)
                    )
                ).scalars().all()
            }
            visible_rows: list[CompanyChange] = []
            for row in rows:
                refs = [
                    e for e in _json_loads(row.evidence_json, [])
                    if isinstance(e, dict) and e.get("type") in ("action", "claim", "learning")
                ]
                if not refs:
                    continue  # org-level signal, no visible entity reference
                ok = True
                for e in refs:
                    if e["type"] == "action":
                        if e.get("id") not in allowed_action_ids:
                            ok = False
                            break
                    elif e["type"] == "learning":
                        learning = learning_rows.get(e.get("id") or "")
                        if learning is None:
                            ok = False
                            break
                        if learning.source_type == "action":
                            if learning.source_id not in allowed_action_ids:
                                ok = False
                                break
                        elif learning.source_type in ("claim", "topic"):
                            source_claim = (
                                await db.execute(
                                    select(KnowledgeClaim).where(
                                        KnowledgeClaim.organization_id == organization_id,
                                        KnowledgeClaim.id == learning.source_id,
                                    ).limit(1)
                                )
                            ).scalar_one_or_none()
                            if source_claim is None or not await self._claim_visible(
                                db, organization_id=organization_id,
                                claim=source_claim, access=access,
                            ):
                                ok = False
                                break
                        else:
                            ok = False
                            break
                    elif e["type"] == "claim":
                        claim = (
                            await db.execute(
                                select(KnowledgeClaim).where(
                                    KnowledgeClaim.organization_id == organization_id,
                                    KnowledgeClaim.id == e.get("id"),
                                ).limit(1)
                            )
                        ).scalar_one_or_none()
                        if claim is None or not await self._claim_visible(
                            db, organization_id=organization_id, claim=claim, access=access,
                        ):
                            ok = False
                            break
                if ok:
                    visible_rows.append(row)
            rows = visible_rows
        changes = [
            {
                "id": row.id,
                "change_type": row.change_type,
                "kind": row.kind,
                "title": row.title,
                "detail": row.detail,
                "what_changed": row.what_changed,
                "why_changed": row.why_changed,
                "evidence": _json_loads(row.evidence_json, []),
                "impact": _json_loads(row.impact_json, []),
                "owner_id": row.owner_id,
                "recommended_action": row.recommended_action,
                "domain": row.domain,
                "occurred_at": ensure_aware(row.occurred_at).isoformat(),
            }
            for row in rows
        ]
        groups = {"critical": [], "important": [], "normal": []}
        for change in changes:
            groups.setdefault(change["change_type"], []).append(change)
        return {
            "intent": "company_changes",
            "changes": changes,
            "groups": groups,
            "total": len(changes),
            "since_hours": since_hours,
            "scope": "org" if access.org_wide else "project",
            "generated_at": _utcnow_iso(),
        }

    # -------------------------------------------------------- company health

    @staticmethod
    def _score(ok: int, total: int) -> float:
        if total <= 0:
            return 100.0
        return round(max(0.0, min(100.0, ok / total * 100.0)), 1)

    async def _upsert_health_signal(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        dimension: str,
        metric: str,
        value: float,
        evidence: list[dict[str, Any]],
        window_hours: int,
        confidence: float,
        explanation: str,
        previous: Optional[CompanyHealthSignal],
    ) -> dict[str, Any]:
        row = (
            await db.execute(
                select(CompanyHealthSignal).where(
                    CompanyHealthSignal.organization_id == organization_id,
                    CompanyHealthSignal.dimension == dimension,
                    CompanyHealthSignal.metric == metric,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = CompanyHealthSignal(
                organization_id=organization_id,
                dimension=dimension,
                metric=metric,
                value=value,
                evidence_json=json.dumps(evidence),
                time_window_hours=window_hours,
                confidence=confidence,
                explanation=explanation,
            )
            db.add(row)
        else:
            row.value = value
            row.evidence_json = json.dumps(evidence)
            row.time_window_hours = window_hours
            row.confidence = confidence
            row.explanation = explanation
        if previous is not None and value > previous.value + 2:
            row.trend = "up"
        elif previous is not None and value < previous.value - 2:
            row.trend = "down"
        else:
            row.trend = "flat"
        await db.flush()
        return {
            "metric": metric,
            "value": value,
            "trend": row.trend,
            "evidence": evidence,
            "time_window_hours": window_hours,
            "confidence": confidence,
            "explanation": explanation,
        }

    async def company_health(
        self, db: AsyncSession, *, organization_id: str, user: Any, window_hours: int = 24,
    ) -> dict[str, Any]:
        """Consolidated company health: ten explainable dimensions. Every
        signal carries metric + evidence + time window + confidence +
        explanation — never a black-box score. Signals are refreshed
        idempotently into company_health_signals."""
        access = await self._access(db, organization_id=organization_id, user=user)
        now = now_utc()
        since = now - timedelta(hours=window_hours)

        previous_rows = {
            (r.dimension, r.metric): r
            for r in (
                await db.execute(
                    select(CompanyHealthSignal).where(
                        CompanyHealthSignal.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        }

        def previous(dimension: str, metric: str) -> Optional[CompanyHealthSignal]:
            return previous_rows.get((dimension, metric))

        # ---- bounded counts over the governed substrate --------------------
        actions = list(
            (
                await db.execute(
                    select(CompanyAction).where(
                        CompanyAction.organization_id == organization_id,
                        CompanyAction.created_at >= since,
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        ) if access.org_wide else []
        all_actions = await self._actions_for_access(
            db, organization_id=organization_id, access=access,
        )
        active_actions = [a for a in all_actions if a.state in ("awaiting_approval", "approved", "ready", "in_progress", "blocked")]
        overdue_actions = [
            a for a in active_actions
            if a.due_at and now > ensure_aware(a.due_at) and a.state in ("ready", "in_progress", "approved", "awaiting_approval")
        ]
        blocked_actions = [a for a in active_actions if a.state == "blocked"]
        escalated_actions = [a for a in all_actions if a.escalation_level >= 2 and a.state not in ("verified", "cancelled", "failed", "rejected")]
        completed_window = [a for a in actions if a.state in ("completed", "verified")]

        assesses = (
            list(
                (
                    await db.execute(
                        select(OutcomeAssessment).where(
                            OutcomeAssessment.organization_id == organization_id,
                            OutcomeAssessment.assessed_at >= since,
                        ).limit(_ROWS_MAX)
                    )
                ).scalars().all()
            )
            if access.org_wide
            else []
        )
        underperformed = [a for a in assesses if a.assessment == "underperformed"]

        decision_outcomes = (
            list(
                (
                    await db.execute(
                        select(DecisionOutcome).where(
                            DecisionOutcome.organization_id == organization_id,
                            DecisionOutcome.measured_at >= since,
                        ).limit(_ROWS_MAX)
                    )
                ).scalars().all()
            )
            if access.org_wide
            else []
        )

        insights = list(
            (
                await db.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.organization_id == organization_id,
                        KnowledgeIntelInsight.status == "active",
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        ) if access.org_wide else []
        risk_insights = [i for i in insights if i.kind == "risk"]
        contradiction_insights = [i for i in insights if i.kind == "contradiction"]
        gap_insights = [i for i in insights if i.kind == "gap"]

        pending_approvals = [a for a in all_actions if a.state == "awaiting_approval"]
        learning_rows = list(
            (
                await db.execute(
                    select(OrganizationalLearning).where(
                        OrganizationalLearning.organization_id == organization_id,
                        OrganizationalLearning.observed_at >= since,
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        ) if access.org_wide else []

        from app.models.knowledge import Decision

        open_decisions = list(
            (
                await db.execute(
                    select(Decision).where(
                        Decision.organization_id == organization_id,
                        Decision.status.in_(_DECISION_ALLOW),
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        ) if access.org_wide else []
        aging_decisions = [
            d for d in open_decisions
            if d.created_at and now - ensure_aware(d.created_at) > timedelta(days=3)
        ]

        # ---- explainable signals per dimension -----------------------------

        execution_ok = len(all_actions) - len(overdue_actions) - len(blocked_actions) - len(escalated_actions)
        execution_value = self._score(execution_ok, len(all_actions)) if all_actions else 100.0
        execution_score = await self._upsert_health_signal(
            db, organization_id=organization_id, dimension="execution", metric="execution_flow",
            value=execution_value,
            evidence=[
                {"label": "active actions", "count": len(active_actions)},
                {"label": "overdue", "count": len(overdue_actions)},
                {"label": "blocked", "count": len(blocked_actions)},
                {"label": "escalated", "count": len(escalated_actions)},
                {"label": "verified in window", "count": len(completed_window)},
            ],
            window_hours=window_hours,
            confidence=0.85 if len(all_actions) >= 5 else 0.6,
            explanation=(
                f"{len(overdue_actions)} overdue, {len(blocked_actions)} blocked, "
                f"{len(escalated_actions)} escalated out of {len(all_actions)} actions."
            ),
            previous=previous("execution", "execution_flow"),
        )

        decision_ok = max(0, len(open_decisions) - len(aging_decisions) - len(decision_outcomes))
        decision_value = self._score(decision_ok, len(open_decisions)) if open_decisions else 100.0
        decision_score = await self._upsert_health_signal(
            db, organization_id=organization_id, dimension="decision", metric="decision_flow",
            value=decision_value,
            evidence=[
                {"label": "open decisions", "count": len(open_decisions)},
                {"label": "aging > 3 days", "count": len(aging_decisions)},
                {"label": "decisions measured in window", "count": len(decision_outcomes)},
                {"label": "underperformed outcomes", "count": len(underperformed)},
            ],
            window_hours=window_hours,
            confidence=0.8 if open_decisions else 0.5,
            explanation=(
                f"{len(aging_decisions)} of {len(open_decisions)} open decisions are aging "
                "beyond 3 days."
            ),
            previous=previous("decision", "decision_flow"),
        )

        knowledge_ok = len(insights) - len(contradiction_insights) - len(gap_insights) - len(risk_insights)
        knowledge_value = self._score(knowledge_ok, len(insights)) if insights else 100.0
        knowledge_score = await self._upsert_health_signal(
            db, organization_id=organization_id, dimension="knowledge", metric="knowledge_soundness",
            value=knowledge_value,
            evidence=[
                {"label": "contradictions", "count": len(contradiction_insights)},
                {"label": "gaps (high/critical)", "count": len([g for g in gap_insights if g.severity in ("high", "critical")])},
                {"label": "emerging risks", "count": len(risk_insights)},
                {"label": "lessons recorded in window", "count": len(learning_rows)},
            ],
            window_hours=window_hours,
            confidence=0.8 if insights else 0.5,
            explanation=(
                f"{len(contradiction_insights)} unresolved contradictions, "
                f"{len(risk_insights)} emerging risks, "
                f"{len([g for g in gap_insights if g.severity in ('high', 'critical')])} critical gaps."
            ),
            previous=previous("knowledge", "knowledge_soundness"),
        )

        communication_actions = [a for a in all_actions if a.action_type == "communication"]
        comm_overdue = [a for a in communication_actions if a.due_at and now > ensure_aware(a.due_at) and a.state in ("ready", "in_progress", "awaiting_approval", "approved")]
        communication_ok = len(communication_actions) - len(comm_overdue)
        communication_score = await self._upsert_health_signal(
            db, organization_id=organization_id, dimension="communication", metric="communication_delivery",
            value=self._score(communication_ok, communication_actions) if communication_actions else 100.0,
            evidence=[
                {"label": "communication actions", "count": len(communication_actions)},
                {"label": "overdue communications", "count": len(comm_overdue)},
            ],
            window_hours=window_hours,
            confidence=0.7 if communication_actions else 0.5,
            explanation=(
                f"{len(comm_overdue)} of {len(communication_actions)} communication actions are overdue."
                if communication_actions
                else "No governed communication actions in this company yet."
            ),
            previous=previous("communication", "communication_delivery"),
        )

        project_actions = [a for a in all_actions if a.action_type == "project"]
        project_blocked = [a for a in project_actions if a.state == "blocked"]
        project_ok = len(project_actions) - len(project_blocked)
        projects_score = await self._upsert_health_signal(
            db, organization_id=organization_id, dimension="projects", metric="project_delivery",
            value=self._score(project_ok, project_actions) if project_actions else 100.0,
            evidence=[
                {"label": "project actions", "count": len(project_actions)},
                {"label": "blocked projects", "count": len(project_blocked)},
            ],
            window_hours=window_hours,
            confidence=0.7 if project_actions else 0.5,
            explanation=(
                f"{len(project_blocked)} of {len(project_actions)} project actions are blocked."
                if project_actions
                else "No project actions in this company yet."
            ),
            previous=previous("projects", "project_delivery"),
        )

        customer_changes = list(
            (
                await db.execute(
                    select(CompanyChange).where(
                        CompanyChange.organization_id == organization_id,
                        CompanyChange.domain == "customer",
                        CompanyChange.occurred_at >= since,
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        ) if access.org_wide else []
        customer_critical = [c for c in customer_changes if c.change_type == "critical"]
        customer_score = await self._upsert_health_signal(
            db, organization_id=organization_id, dimension="customer", metric="customer_stability",
            value=100.0 if not customer_critical else max(0.0, 100.0 - 25.0 * len(customer_critical)),
            evidence=[
                {"label": "customer-impacting changes", "count": len(customer_changes)},
                {"label": "critical customer changes", "count": len(customer_critical)},
            ],
            window_hours=window_hours,
            confidence=0.7 if customer_changes else 0.4,
            explanation=(
                f"{len(customer_critical)} critical customer-impacting change(s) in the window."
                if customer_critical
                else "No critical customer-impacting changes in the window."
            ),
            previous=previous("customer", "customer_stability"),
        )

        revenue_score_value = 100.0 if not underperformed else max(0.0, 100.0 - 20.0 * len(underperformed))
        revenue_score = await self._upsert_health_signal(
            db, organization_id=organization_id, dimension="revenue", metric="expectation_health",
            value=revenue_score_value,
            evidence=[
                {"label": "underperformed outcomes", "count": len(underperformed)},
                {"label": "assessed outcomes", "count": len(assesses)},
            ],
            window_hours=window_hours,
            confidence=0.7 if assesses else 0.4,
            explanation=(
                f"{len(underperformed)} of {len(assesses)} measured outcomes underperformed "
                "their expectations."
            ),
            previous=previous("revenue", "expectation_health"),
        )

        risk_value = 100.0 if not (risk_insights or escalated_actions or pending_approvals) else max(
            0.0,
            100.0 - 15.0 * len(risk_insights) - 20.0 * len(escalated_actions) - 5.0 * len(pending_approvals),
        )
        risk_score = await self._upsert_health_signal(
            db, organization_id=organization_id, dimension="risk", metric="risk_exposure",
            value=risk_value,
            evidence=[
                {"label": "emerging risk insights", "count": len(risk_insights)},
                {"label": "escalated actions", "count": len(escalated_actions)},
                {"label": "pending approvals", "count": len(pending_approvals)},
            ],
            window_hours=window_hours,
            confidence=0.8 if (risk_insights or escalated_actions) else 0.6,
            explanation=(
                f"{len(escalated_actions)} escalated actions and {len(risk_insights)} emerging "
                "risk signals are open."
            ),
            previous=previous("risk", "risk_exposure"),
        )

        governance_value = 100.0 if not pending_approvals else max(0.0, 100.0 - 10.0 * len(pending_approvals))
        governance_score = await self._upsert_health_signal(
            db, organization_id=organization_id, dimension="governance", metric="approval_flow",
            value=governance_value,
            evidence=[
                {"label": "pending approvals", "count": len(pending_approvals)},
                {"label": "high-risk pending", "count": len([a for a in pending_approvals if a.risk == "high"])},
            ],
            window_hours=window_hours,
            confidence=0.8 if pending_approvals else 0.6,
            explanation=(
                f"{len(pending_approvals)} governed actions await approval."
                if pending_approvals
                else "No governed actions await approval."
            ),
            previous=previous("governance", "approval_flow"),
        )

        people_overdue = [a for a in overdue_actions if a.assignee_id]
        unassigned = [a for a in active_actions if not a.assignee_id and a.state in ("ready", "in_progress")]
        people_value = 100.0 if not (people_overdue or unassigned) else max(
            0.0, 100.0 - 15.0 * len(people_overdue) - 5.0 * len(unassigned),
        )
        people_score = await self._upsert_health_signal(
            db, organization_id=organization_id, dimension="people", metric="ownership_flow",
            value=people_value,
            evidence=[
                {"label": "overdue with owner", "count": len(people_overdue)},
                {"label": "ownerless actions", "count": len(unassigned)},
            ],
            window_hours=window_hours,
            confidence=0.8 if (people_overdue or unassigned) else 0.5,
            explanation=(
                f"{len(people_overdue)} overdue actions have owners; "
                f"{len(unassigned)} active actions have no owner."
            ),
            previous=previous("people", "ownership_flow"),
        )

        dimensions = [
            (dimension, score, signals)
            for dimension, score, signals in [
                ("execution", execution_score, []),
                ("decision", decision_score, []),
                ("knowledge", knowledge_score, []),
                ("communication", communication_score, []),
                ("projects", projects_score, []),
                ("customer", customer_score, []),
                ("revenue", revenue_score, []),
                ("risk", risk_score, []),
                ("governance", governance_score, []),
                ("people", people_score, []),
            ]
        ]
        # group the last comment: each published block carries one signal now;
        # the shape leaves room for more metrics per dimension later.
        published = []
        for dimension, signal, _signals in dimensions:
            preview = list(
                (
                    await db.execute(
                        select(CompanyHealthSignal).where(
                            CompanyHealthSignal.organization_id == organization_id,
                            CompanyHealthSignal.dimension == dimension,
                        ).order_by(CompanyHealthSignal.snapshot_at.desc()).limit(10)
                    )
                ).scalars().all()
            )
            published.append(
                {
                    "dimension": dimension,
                    "score": round(sum(s.value for s in preview) / len(preview), 1) if preview else signal["value"],
                    "trend": signal["trend"],
                    "signals": [signal],
                }
            )
        return {
            "intent": "companyhealth",
            "dimensions": published,
            "total_dimensions": len(published),
            "scope": "org" if access.org_wide else "project",
            "generated_at": _utcnow_iso(),
        }

    # -------------------------------------------------------- impact analysis

    async def _entity_label(
        self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str,
    ) -> Optional[str]:
        if entity_type == "action":
            row = (
                await db.execute(
                    select(CompanyAction).where(
                        CompanyAction.organization_id == organization_id,
                        CompanyAction.id == entity_id,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            return row.title if row else None
        if entity_type == "topic":
            row = (
                await db.execute(
                    select(KnowledgeTopic).where(
                        KnowledgeTopic.organization_id == organization_id,
                        KnowledgeTopic.id == entity_id,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            return row.name if row else None
        if entity_type == "claim":
            row = (
                await db.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.id == entity_id,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            return f"{row.subject_id}: {row.object_text}"[:240] if row else None
        return None

    async def impact_analysis(
        self, db: AsyncSession, *, organization_id: str,
        subject_type: str, subject_id: str, user: Any,
    ) -> dict[str, Any]:
        """Company-wide impact analysis: bounded BFS from a subject over the
        knowledge graph, claims and governed actions. Direct and indirect
        reach, risks, owners, customers, deadlines, financial assumptions and
        recommended mitigations — governance-filtered and persisted."""
        if subject_type not in ("topic", "action", "claim", "entity"):
            raise ValueError(f"cannot analyze subject_type '{subject_type}'")
        access = await self._access(db, organization_id=organization_id, user=user)
        title = await self._entity_label(
            db, organization_id=organization_id, entity_type=subject_type, entity_id=subject_id,
        )
        if title is None:
            raise ValueError(f"subject '{subject_type}:{subject_id}' does not exist")

        # relation edges (topic graph) — both directions
        relation_rows = list(
            (
                await db.execute(
                    select(KnowledgeRelation).where(
                        KnowledgeRelation.organization_id == organization_id,
                        KnowledgeRelation.source_type == "topic",
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        )
        edges: dict[str, set[tuple[str, str, str]]] = {}
        for rel in relation_rows:
            edges.setdefault((rel.source_type, rel.source_id), set()).add((rel.target_type, rel.target_id, rel.relation_type))
            edges.setdefault((rel.target_type, rel.target_id), set()).add((rel.source_type, rel.source_id, rel.relation_type))

        claim_rows = list(
            (
                await db.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == organization_id,
                    ).limit(_ROWS_MAX * 2)
                )
            ).scalars().all()
        )
        claims_by_subject: dict[tuple[str, str], list[KnowledgeClaim]] = {}
        for claim in claim_rows:
            claims_by_subject.setdefault((claim.subject_type, claim.subject_id), []).append(claim)

        action_rows = await self._actions_for_access(
            db, organization_id=organization_id, access=access,
        )
        actions_by_claim: dict[str, list[CompanyAction]] = {}
        for action in action_rows:
            for claim_id in _json_loads(action.source_claim_ids_json, []) or []:
                actions_by_claim.setdefault(claim_id, []).append(action)
        actions_by_target: dict[tuple[str, str], CompanyAction] = {}
        for action in action_rows:
            if action.target_type and action.target_id:
                actions_by_target[(action.target_type, action.target_id)] = action

        # BFS
        start = (subject_type, subject_id)
        visited: set[tuple[str, str]] = {start}
        frontier: list[tuple[tuple[str, str], int]] = [(start, 0)]
        nodes: list[dict[str, Any]] = []
        while frontier:
            (node_type, node_id), depth = frontier.pop(0)
            if depth >= _DEPTH_MAX or len(nodes) >= _NODES_MAX:
                break
            children: list[tuple[tuple[str, str], str]] = []
            for edge_type, edge_id, relation in edges.get((node_type, node_id), set()):
                children.append(((edge_type, edge_id), relation))
            for claim in claims_by_subject.get((node_type, node_id), []):
                if claim.topic_id:
                    children.append((("topic", claim.topic_id), "knowledge_claim"))
                if claim.superseded_by:
                    children.append((("claim", claim.superseded_by), "supersedes"))
                for related in _json_loads(claim.related_entities_json, []) or []:
                    if isinstance(related, dict) and related.get("id"):
                        children.append(((str(related.get("type") or "entity"), str(related["id"])), "related"))
            for action in actions_by_claim.get(node_id, []):
                children.append((("action", action.id), "action_from_claim"))
            if (node_type, node_id) in actions_by_target:
                action = actions_by_target[(node_type, node_id)]
                children.append((("action", action.id), "action_target"))
            for dep_id in edges.get(("action", node_id), set()):
                children.append((("action", dep_id[0] if dep_id[0] == "action" else node_id), "dependency"))

            seen_child: set[tuple[str, str]] = set()
            for (child_type, child_id), relation in children:
                if (child_type, child_id) in visited:
                    continue
                if (child_type, child_id) in seen_child:
                    continue
                seen_child.add((child_type, child_id))
                label = await self._entity_label(
                    db, organization_id=organization_id,
                    entity_type=child_type, entity_id=child_id,
                )
                if label is None:
                    continue
                if not access.org_wide and child_type == "claim":
                    claim = next((c for c in claim_rows if c.id == child_id), None)
                    if claim is not None and not await self._claim_visible(
                        db, organization_id=organization_id, claim=claim, access=access,
                    ):
                        continue
                nodes.append(
                    {
                        "entity_type": child_type,
                        "entity_id": child_id,
                        "title": label,
                        "depth": depth + 1,
                        "via": relation,
                    }
                )
                visited.add((child_type, child_id))
                frontier.append(((child_type, child_id), depth + 1))

        direct = [n for n in nodes if n["depth"] == 1]
        indirect = [n for n in nodes if n["depth"] >= 2]
        action_nodes = [n for n in nodes if n["entity_type"] == "action"]
        action_map = {a.id: a for a in action_rows}

        risks: list[dict[str, Any]] = []
        for node in action_nodes:
            action = action_map.get(node["entity_id"])
            if action is None:
                continue
            if action.state == "blocked":
                risks.append({"kind": "blocked", "target": action.title, "detail": action.blocked_reason or "dependency unresolved"})
            if action.due_at and action.state in ("ready", "in_progress", "awaiting_approval", "approved") and now_utc() > ensure_aware(action.due_at):
                risks.append({"kind": "overdue", "target": action.title, "detail": "missed its due date"})
            if action.escalation_level >= 2:
                risks.append({"kind": "escalated", "target": action.title, "detail": f"escalation level {action.escalation_level}"})
        for insight in list(
            (
                await db.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.organization_id == organization_id,
                        KnowledgeIntelInsight.status == "active",
                        KnowledgeIntelInsight.kind == "risk",
                    ).limit(20)
                )
            ).scalars().all()
        ):
            risks.append({"kind": "emerging_risk", "target": insight.title, "detail": insight.summary})

        owners = sorted({str(a.assignee_id) for a in action_map.values() if a.assignee_id and a.state not in ("cancelled", "rejected", "superseded", "failed")})
        customers = [
            {"type": node["entity_type"], "id": node["entity_id"], "title": node["title"]}
            for node in nodes
            if node["entity_type"] == "customer" or (node["entity_type"] == "entity" and any(
                term in str(node["title"]).lower() for term in _CUSTOMER_TERMS
            ))
        ]
        deadlines = [
            {"target": action.title, "due_at": ensure_aware(action.due_at).isoformat()}
            for action in action_map.values()
            if action.due_at and action.state not in ("verified", "cancelled", "rejected", "failed", "superseded")
        ]
        financial: list[dict[str, Any]] = []
        for claim in claim_rows:
            if any(term in claim.predicate.lower() for term in _FINANCIAL_TERMS) or any(
                term in str(claim.object_text).lower() for term in _FINANCIAL_TERMS
            ):
                financial.append(
                    {
                        "subject": f"{claim.subject_id}: {claim.predicate}",
                        "value": claim.object_text[:120],
                        "status": claim.status,
                    }
                )
        mitigations = [
            {"risk": r["kind"], "action": {
                "blocked": "Resolve the blocking dependency or transfer the blocker",
                "overdue": "Replan the deadline or reprioritize the action",
                "escalated": "Schedule leadership review of the escalation",
                "emerging_risk": "Open a governed action to investigate the risk signal",
            }.get(r["kind"], "Governed review of the affected area"),
            "target": r["target"]}
            for r in risks[:12]
        ]

        persist = (
            await db.execute(
                select(ImpactAssessment).where(
                    ImpactAssessment.organization_id == organization_id,
                    ImpactAssessment.subject_type == subject_type,
                    ImpactAssessment.subject_id == subject_id,
                )
            )
        ).scalar_one_or_none()
        if persist is None:
            persist = ImpactAssessment(
                organization_id=organization_id,
                subject_type=subject_type,
                subject_id=subject_id,
                subject_title=title,
                direct_json=json.dumps([{k: n[k] for k in ("entity_type", "entity_id", "title", "via")} for n in direct]),
                indirect_json=json.dumps([{k: n[k] for k in ("entity_type", "entity_id", "title", "via", "depth")} for n in indirect]),
                risks_json=json.dumps(risks),
                owners_json=json.dumps(owners),
                customers_json=json.dumps([{k: c[k] for k in ("type", "id", "title")} for c in customers]),
                deadlines_json=json.dumps([{k: d[k] for k in ("target", "due_at")} for d in deadlines]),
                financial_json=json.dumps(financial),
                mitigations_json=json.dumps([{k: m[k] for k in ("risk", "action", "target")} for m in mitigations]),
                total_direct=len(direct),
                total_indirect=len(indirect),
                generated_by=getattr(user, "id", None) or "system",
            )
            db.add(persist)
        else:
            persist.subject_title = title
            persist.direct_json = json.dumps([{k: n[k] for k in ("entity_type", "entity_id", "title", "via")} for n in direct])
            persist.indirect_json = json.dumps([{k: n[k] for k in ("entity_type", "entity_id", "title", "via", "depth")} for n in indirect])
            persist.risks_json = json.dumps(risks)
            persist.owners_json = json.dumps(owners)
            persist.customers_json = json.dumps([{k: c[k] for k in ("type", "id", "title")} for c in customers])
            persist.deadlines_json = json.dumps([{k: d[k] for k in ("target", "due_at")} for d in deadlines])
            persist.financial_json = json.dumps(financial)
            persist.mitigations_json = json.dumps([{k: m[k] for k in ("risk", "action", "target")} for m in mitigations])
            persist.total_direct = len(direct)
            persist.total_indirect = len(indirect)
        await db.flush()

        return {
            "intent": "impact",
            "subject_type": subject_type,
            "subject_id": subject_id,
            "subject_title": title,
            "total": len(nodes),
            "direct": direct,
            "indirect": indirect,
            "risks": risks,
            "owners": owners[:40],
            "customers": customers,
            "deadlines": deadlines[:40],
            "financial": financial[:40],
            "mitigations": mitigations,
            "scope": "org" if access.org_wide else "project",
            "generated_at": _utcnow_iso(),
        }

    # --------------------------------------------------- universal action center

    async def _upsert_insight(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        category: str,
        fingerprint_key: str,
        title: str,
        detail: Optional[str],
        why: Optional[str],
        impact: Optional[str],
        evidence: list[dict[str, Any]],
        severity: str,
        risk: str,
        authorization_level: str,
        owner_id: Optional[str],
        source_type: str,
        source_id: str,
        reference_status: Optional[str],
        reference_outcome: Optional[str],
    ) -> Optional[OperatingInsight]:
        fingerprint = _fingerprint(category, fingerprint_key)
        row = (await db.execute(
            select(OperatingInsight).where(
                OperatingInsight.organization_id == organization_id,
                OperatingInsight.category == category,
                OperatingInsight.fingerprint == fingerprint,
                OperatingInsight.status == "active",
            )
        )).scalar_one_or_none()
        if row is None:
            row = OperatingInsight(
                organization_id=organization_id,
                category=category,
                fingerprint=fingerprint,
                title=title[:240],
                detail=detail,
                why=why,
                impact=impact,
                evidence_json=json.dumps(evidence),
                severity=severity,
                risk=risk,
                authorization_level=authorization_level,
                owner_id=owner_id,
                status="active",
                source_type=source_type,
                source_id=source_id,
                reference_status=reference_status,
                reference_outcome=reference_outcome,
            )
            db.add(row)
            await db.flush()
        return row

    async def _resolve_insight_ref(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        category: str,
        fingerprint_key: str,
    ) -> None:
        fingerprint = _fingerprint(category, fingerprint_key)
        row = (await db.execute(
            select(OperatingInsight).where(
                OperatingInsight.organization_id == organization_id,
                OperatingInsight.category == category,
                OperatingInsight.fingerprint == fingerprint,
                OperatingInsight.status == "active",
            )
        )).scalar_one_or_none()
        if row is not None:
            row.status = "resolved"
            row.resolved_at = now_utc()
            row.resolved_by = "system"

    async def operating_insights(
        self, db: AsyncSession, *, organization_id: str, user: Any,
    ) -> dict[str, Any]:
        """The Universal Action Center: one consolidated governed board —
        critical issues, recommended actions, pending approvals, knowledge
        gaps, contradictions, emerging risks, overdue actions, decisions
        awaiting attention, customer-impacting changes and learning
        opportunities. Insights are keyed exact-once; cleared references are
        resolved (never deleted); every item carries
        why/what/impact/evidence/owner/authority/risk/approval/status/outcome."""
        access = await self._access(db, organization_id=organization_id, user=user)
        now = now_utc()

        # -- pending approvals (medium/high risk awaiting explicit approval)
        approvals = await self._actions_for_access(
            db, organization_id=organization_id, access=access,
        )
        approvals = [a for a in approvals if a.state == "awaiting_approval"]
        active_approval_ids: set[str] = set()
        for action in approvals:
            active_approval_ids.add(action.id)
            auth = _AUTHORIZATION.get(action.risk, _AUTHORIZATION["medium"])["level"]
            await self._upsert_insight(
                db, organization_id=organization_id,
                category="pending_approval",
                fingerprint_key=action.id,
                title=action.title or "Approval needed",
                detail=action.description,
                why="The action's risk policy requires explicit approval before execution",
                impact=action.why or f"{action.action_type} change in {action.scope_type}:{action.scope_id or 'org'}",
                evidence=[{"type": "action", "id": action.id}],
                severity="high" if action.risk == "high" else "medium",
                risk=action.risk,
                authorization_level=auth,
                owner_id=action.assignee_id,
                source_type="action",
                source_id=action.id,
                reference_status=action.state,
                reference_outcome=None,
            )
        for existing in list(
            (
                await db.execute(
                    select(OperatingInsight).where(
                        OperatingInsight.organization_id == organization_id,
                        OperatingInsight.category == "pending_approval",
                        OperatingInsight.status == "active",
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        ):
            if existing.source_id not in active_approval_ids:
                await self._resolve_insight_ref(
                    db, organization_id=organization_id,
                    category="pending_approval", fingerprint_key=existing.source_id,
                )

        # -- overdue actions
        scoped_active = await self._actions_for_access(
            db, organization_id=organization_id, access=access,
        )
        overdue = [
            a for a in scoped_active
            if a.state in ("ready", "in_progress", "approved", "awaiting_approval")
            and a.due_at and now > ensure_aware(a.due_at)
        ]
        for action in overdue:
            await self._upsert_insight(
                db, organization_id=organization_id,
                category="overdue_action",
                fingerprint_key=action.id,
                title=f"Overdue: {action.title}",
                detail=action.description,
                why=f"Missed its due date ({ensure_aware(action.due_at).date().isoformat()})",
                impact=action.why or "Execution risk",
                evidence=[{"type": "action", "id": action.id}],
                severity="medium",
                risk=action.risk,
                authorization_level=_AUTHORIZATION.get(action.risk, _AUTHORIZATION["medium"])["level"],
                owner_id=action.assignee_id,
                source_type="action",
                source_id=action.id,
                reference_status=action.state,
                reference_outcome="overdue",
            )

        # -- critical issues: blocked / escalated / high-risk in progress
        critical = [
            a for a in scoped_active
            if a.state in ("in_progress", "blocked")
            and (a.risk == "high" or a.escalation_level >= 2 or a.state == "blocked")
        ]
        for action in critical:
            await self._upsert_insight(
                db, organization_id=organization_id,
                category="critical_issue",
                fingerprint_key=action.id,
                title=f"Critical: {action.title}",
                detail=action.blocked_reason or action.fail_reason or action.description,
                why=(
                    f"{'Blocked' if action.state == 'blocked' else 'High-risk execution'} "
                    f"{'(escalation ' + str(action.escalation_level) + ')' if action.escalation_level >= 2 else ''}"
                ),
                impact=action.why or "Blocked execution",
                evidence=[{"type": "action", "id": action.id}],
                severity="critical" if (action.escalation_level >= 2 or action.risk == "high") else "high",
                risk=action.risk,
                authorization_level=_AUTHORIZATION.get(action.risk, _AUTHORIZATION["medium"])["level"],
                owner_id=action.assignee_id,
                source_type="action",
                source_id=action.id,
                reference_status=action.state,
                reference_outcome="blocked" if action.state == "blocked" else "in_progress",
            )

        # -- recommended actions (active knowledge recommendations)
        recommendations = list(
            (
                await db.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == organization_id,
                        KnowledgeRecommendation.status == "active",
                        KnowledgeRecommendation.lifecycle.in_(("detected", "candidate", "reviewed")),
                    ).order_by(KnowledgeRecommendation.confidence.desc()).limit(20)
                )
            ).scalars().all()
        )
        for rec in recommendations:
            await self._upsert_insight(
                db, organization_id=organization_id,
                category="recommended_action",
                fingerprint_key=rec.id,
                title=f"Recommended: {rec.reason[:200]}",
                detail=rec.reason,
                why=f"Materialized by the intelligence engine (kind {rec.kind}, confidence {rec.confidence:.0%})",
                impact="Addressing this recommendation improves the company's knowledge operations",
                evidence=[{"type": "recommendation", "id": rec.id}],
                severity="medium",
                risk=rec.risk,
                authorization_level=_AUTHORIZATION.get(rec.risk, _AUTHORIZATION["medium"])["level"],
                owner_id=None,
                source_type="recommendation",
                source_id=rec.id,
                reference_status=rec.lifecycle,
                reference_outcome=None,
            )

        # -- knowledge gaps / contradictions / emerging risks from insights
        from app.knowledge.action_engine import action_engine

        await action_engine.materialize(db, organization_id=organization_id)
        active_insights = list(
            (
                await db.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.organization_id == organization_id,
                        KnowledgeIntelInsight.status == "active",
                        KnowledgeIntelInsight.kind.in_(("gap", "contradiction", "risk")),
                    ).order_by(KnowledgeIntelInsight.priority_score.desc()).limit(_ROWS_MAX)
                )
            ).scalars().all()
        )
        for insight in active_insights:
            category = {
                "gap": "knowledge_gap",
                "contradiction": "contradiction",
                "risk": "emerging_risk",
            }[insight.kind]
            severity = insight.severity
            auth_level = "auto"
            await self._upsert_insight(
                db, organization_id=organization_id,
                category=category,
                fingerprint_key=f"insight:{insight.id}",
                title=insight.title,
                detail=insight.summary,
                why="Deterministic insight materialization",
                impact=f"{insight.topic_name or 'org-wide'} knowledge",
                evidence=[{"type": "insight", "id": insight.id}],
                severity=severity,
                risk="medium" if severity in ("high", "critical") else "low",
                authorization_level=auth_level,
                owner_id=None,
                source_type="insight",
                source_id=insight.id,
                reference_status="active",
                reference_outcome=insight.kind,
            )

        # -- customer-impacting changes within 7 days
        customer_changes = list(
            (
                await db.execute(
                    select(CompanyChange).where(
                        CompanyChange.organization_id == organization_id,
                        CompanyChange.domain == "customer",
                        CompanyChange.occurred_at >= now - timedelta(days=_WINDOW_DAYS),
                    ).limit(20)
                )
            ).scalars().all()
        )
        for change in customer_changes:
            await self._upsert_insight(
                db, organization_id=organization_id,
                category="customer_impact",
                fingerprint_key=change.id,
                title=f"Customer impact: {change.title}",
                detail=change.detail,
                why=change.what_changed or "customer-impacting change",
                impact=change.impact_json or "customer-facing",
                evidence=[{"type": "change", "id": change.id}],
                severity=change.change_type,
                risk="high" if change.change_type == "critical" else "medium",
                authorization_level="human" if change.change_type == "critical" else "approval",
                owner_id=change.owner_id,
                source_type="change",
                source_id=change.id,
                reference_status="occurred",
                reference_outcome=change.change_type,
            )

        # -- decisions awaiting attention (open > 72h)
        from app.models.knowledge import Decision

        open_decisions = list(
            (
                await db.execute(
                    select(Decision).where(
                        Decision.organization_id == organization_id,
                        Decision.status.in_(_DECISION_ALLOW),
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        )
        for decision in open_decisions:
            age_hours = (now - ensure_aware(decision.created_at)).total_seconds() / 3600
            if age_hours > 72:
                await self._upsert_insight(
                    db, organization_id=organization_id,
                    category="decision_attention",
                    fingerprint_key=decision.id,
                    title=f"Decision open: {decision.title}",
                    detail=f"Open for {int(age_hours / 24)} days without finalization",
                    why="Finalizing this decision unblocks the people and actions depending on it",
                    impact=decision.business_impact or decision.impact or "organizational",
                    evidence=[{"type": "decision", "id": decision.id}],
                    severity="medium",
                    risk="medium",
                    authorization_level="approval",
                    owner_id=decision.decision_maker_id,
                    source_type="decision",
                    source_id=decision.id,
                    reference_status=decision.status,
                    reference_outcome=None,
                )

        # -- learning opportunities (underperformed, not yet learned)
        assessments = list(
            (
                await db.execute(
                    select(OutcomeAssessment).where(
                        OutcomeAssessment.organization_id == organization_id,
                        OutcomeAssessment.assessment == "underperformed",
                    ).limit(_ROWS_MAX)
                )
            ).scalars().all()
        )
        for assessment in assessments:
            lesson_exists = (
                await db.execute(
                    select(OrganizationalLearning).where(
                        OrganizationalLearning.organization_id == organization_id,
                        OrganizationalLearning.kind == "outcome_learning",
                        OrganizationalLearning.source_type == "action",
                        OrganizationalLearning.source_id == assessment.subject_id,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if lesson_exists is not None:
                continue
            action = (
                await db.execute(
                    select(CompanyAction).where(
                        CompanyAction.organization_id == organization_id,
                        CompanyAction.id == assessment.subject_id,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            await self._upsert_insight(
                db, organization_id=organization_id,
                category="learning_opportunity",
                fingerprint_key=f"assessment:{assessment.id}",
                title=f"Learn from {action.title if action else 'the underperformed outcome'}",
                detail=(
                    f"The outcome underperformed its expectation "
                    f"({assessment.actual_value:.4g} vs {assessment.expected_value:.4g} "
                    f"{assessment.expected_units or ''})"
                ),
                why="An underperformed outcome holds a lesson not yet recorded",
                impact="Future similar actions should account for the detected factors",
                evidence=[{"type": "assessment", "id": assessment.id}],
                severity="medium",
                risk="medium",
                authorization_level="auto",
                owner_id=action.assignee_id if action else None,
                source_type="assessment",
                source_id=assessment.id,
                reference_status="underperformed",
                reference_outcome="underperformed",
            )

        rows = list(
            (
                await db.execute(
                    select(OperatingInsight).where(
                        OperatingInsight.organization_id == organization_id,
                        OperatingInsight.status == "active",
                    ).order_by(OperatingInsight.created_at.asc()).limit(_ROWS_MAX * 2)
                )
            ).scalars().all()
        )
        # Read-side governance: a scoped caller only inherits board items whose
        # source entity (action / its assessment) is inside their granted
        # project; org knowledge signals are indistinguishable from absent.
        if not access.org_wide:
            allowed_actions = {
                a.id for a in await self._actions_for_access(
                    db, organization_id=organization_id, access=access,
                )
            }
            kept_rows: list[OperatingInsight] = []
            for row in rows:
                if row.source_type == "action":
                    if row.source_id in allowed_actions:
                        kept_rows.append(row)
                    continue
                if row.source_type == "assessment":
                    assessment_row = (
                        await db.execute(
                            select(OutcomeAssessment).where(
                                OutcomeAssessment.organization_id == organization_id,
                                OutcomeAssessment.id == row.source_id,
                            ).limit(1)
                        )
                    ).scalar_one_or_none()
                    if (
                        assessment_row is not None
                        and assessment_row.subject_type == "action"
                        and assessment_row.subject_id in allowed_actions
                    ):
                        kept_rows.append(row)
                    continue
                # org knowledge signals (recommendations / insights / changes)
            rows = kept_rows
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row.category, []).append(
                {
                    "id": row.id,
                    "category": row.category,
                    "title": row.title,
                    "detail": row.detail,
                    "why": row.why,
                    "impact": row.impact,
                    "evidence": _json_loads(row.evidence_json, []),
                    "severity": row.severity,
                    "risk": row.risk,
                    "authorization_level": row.authorization_level,
                    "owner_id": row.owner_id,
                    "status": row.status,
                    "source_type": row.source_type,
                    "source_id": row.source_id,
                    "reference_status": row.reference_status,
                    "reference_outcome": row.reference_outcome,
                    "created_at": ensure_aware(row.created_at).isoformat(),
                }
            )
        counts = {category: len(items) for category, items in grouped.items()}
        return {
            "intent": "actions",
            "categories": counts,
            "items": [item for items in grouped.values() for item in items],
            "total": len(rows),
            "scope": "org" if access.org_wide else "project",
            "generated_at": _utcnow_iso(),
        }

    async def resolve_insight(
        self, db: AsyncSession, *, organization_id: str, insight_id: str, user: Any,
    ) -> dict[str, Any]:
        """Governed human resolution of an operating insight: the row is
        marked resolved with the acting user — never deleted."""
        insight = (
            await db.execute(
                select(OperatingInsight).where(
                    OperatingInsight.organization_id == organization_id,
                    OperatingInsight.id == insight_id,
                )
            )
        ).scalar_one_or_none()
        if insight is None:
            return {"resolved": False, "id": insight_id, "reason": "not found"}
        insight.status = "resolved"
        insight.resolved_at = now_utc()
        insight.resolved_by = getattr(user, "id", None) or "system"
        await db.flush()
        return {"resolved": True, "id": insight_id, "category": insight.category}

    async def insight_detail(
        self, db: AsyncSession, *, organization_id: str, insight_id: str,
    ) -> Optional[dict[str, Any]]:
        insight = (
            await db.execute(
                select(OperatingInsight).where(
                    OperatingInsight.organization_id == organization_id,
                    OperatingInsight.id == insight_id,
                )
            )
        ).scalar_one_or_none()
        if insight is None:
            return None
        return {
            "id": insight.id,
            "category": insight.category,
            "title": insight.title,
            "detail": insight.detail,
            "why": insight.why,
            "impact": insight.impact,
            "evidence": _json_loads(insight.evidence_json, []),
            "severity": insight.severity,
            "risk": insight.risk,
            "authorization_level": insight.authorization_level,
            "owner_id": insight.owner_id,
            "status": insight.status,
            "source_type": insight.source_type,
            "source_id": insight.source_id,
            "reference_status": insight.reference_status,
            "reference_outcome": insight.reference_outcome,
            "created_at": ensure_aware(insight.created_at).isoformat(),
            "resolved_at": ensure_aware(insight.resolved_at).isoformat() if insight.resolved_at else None,
            "resolved_by": insight.resolved_by,
        }

    # --------------------------------------------------------------- explain

    async def explain(
        self, db: AsyncSession, *, organization_id: str,
        subject_type: str, subject_id: str, user: Any,
    ) -> dict[str, Any]:
        """'Why?' everywhere: a subject's state decomposed into explicit
        reasons, each backed by evidence the caller may see — no black-box
        claims."""
        access = await self._access(db, organization_id=organization_id, user=user)
        reasons: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        title: Optional[str] = None

        if subject_type == "action":
            action = (
                await db.execute(
                    select(CompanyAction).where(
                        CompanyAction.organization_id == organization_id,
                        CompanyAction.id == subject_id,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if action is None:
                return {"found": False, "reason": "subject not found"}
            title = action.title
            if action.why:
                reasons.append({"kind": "intent", "reason": action.why})
                evidence.append({"type": "action", "id": action.id, "title": action.title, "detail": action.why})
            if action.state == "blocked":
                reasons.append({"kind": "blocked", "reason": action.blocked_reason or "a dependency is unresolved"})
            if action.due_at and now_utc() > ensure_aware(action.due_at):
                reasons.append({"kind": "overdue", "reason": f"missed due date {ensure_aware(action.due_at).date().isoformat()}"})
            if action.escalation_level >= 2:
                reasons.append({"kind": "escalated", "reason": f"escalation level {action.escalation_level}"})
            for claim in await self._visible_claims(
                db,
                organization_id=organization_id,
                claim_ids=_json_loads(action.source_claim_ids_json, []) or [],
                access=access,
            ):
                evidence.append(
                    {"type": "claim", "id": claim.id, "title": claim.subject_id, "detail": claim.object_text}
                )
        elif subject_type == "topic":
            topic = (
                await db.execute(
                    select(KnowledgeTopic).where(
                        KnowledgeTopic.organization_id == organization_id,
                        KnowledgeTopic.id == subject_id,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if topic is None:
                return {"found": False, "reason": "subject not found"}
            title = topic.name
            insights = list(
                (
                    await db.execute(
                        select(KnowledgeIntelInsight).where(
                            KnowledgeIntelInsight.organization_id == organization_id,
                            KnowledgeIntelInsight.status == "active",
                            KnowledgeIntelInsight.topic_id == topic.id,
                        ).limit(20)
                    )
                ).scalars().all()
            )
            for insight in insights:
                reasons.append({"kind": insight.kind, "reason": insight.summary})
                evidence.append({"type": "insight", "id": insight.id, "title": insight.title, "detail": insight.summary})
            claims = list(
                (
                    await db.execute(
                        select(KnowledgeClaim).where(
                            KnowledgeClaim.organization_id == organization_id,
                            KnowledgeClaim.topic_id == topic.id,
                            KnowledgeClaim.status != "superseded",
                        ).limit(40)
                    )
                ).scalars().all()
            )
            for claim in claims:
                if not access.org_wide and not await self._claim_visible(
                    db, organization_id=organization_id, claim=claim, access=access,
                ):
                    continue
                evidence.append(
                    {"type": "claim", "id": claim.id, "title": f"{claim.subject_id}: {claim.predicate}", "detail": claim.object_text}
                )
        else:
            claim_rows = list(
                (
                    await db.execute(
                        select(KnowledgeClaim).where(
                            KnowledgeClaim.organization_id == organization_id,
                            KnowledgeClaim.subject_type == subject_type,
                            KnowledgeClaim.subject_id == subject_id,
                        ).limit(40)
                    )
                ).scalars().all()
            )
            if not claim_rows:
                return {"found": False, "reason": "subject not found"}
            for claim in claim_rows:
                if not access.org_wide and not await self._claim_visible(
                    db, organization_id=organization_id, claim=claim, access=access,
                ):
                    continue
                reasons.append(
                    {"kind": "claim", "reason": f"{claim.predicate} = {claim.object_text} (status {claim.status})"}
                )
                evidence.append(
                    {"type": "claim", "id": claim.id, "title": claim.subject_id, "detail": claim.object_text}
                )
        return {
            "found": True,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "title": title,
            "reasons": reasons[:20],
            "evidence": evidence[:40],
            "scope": "org" if access.org_wide else "project",
            "generated_at": _utcnow_iso(),
        }

    # ------------------------------------------------------------ governance

    async def authorization_for(
        self, db: AsyncSession, *, organization_id: str, risk: str,
    ) -> dict[str, Any]:
        """The risk ladder: LOW automatic, MEDIUM approval, HIGH explicit
        human authorization (4E.7 §17)."""
        if risk not in _AUTHORIZATION:
            raise ValueError(f"unknown risk level '{risk}'")
        entry = _AUTHORIZATION[risk]
        return {
            "risk": risk,
            "level": entry["level"],
            "who": entry["who"],
            "note": entry["note"],
            "generated_at": _utcnow_iso(),
        }


learning_engine = LearningEngine()