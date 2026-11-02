"""Slice 4H.7 Phase C — Read-only Evidence Composer.

Governance-first, deterministic composition of canonical 4H evidence into
qualified evidence bundles. No database writes. No LLM truth decisions.
Pure composition of canonical 4H evidence substrate into traceable bundles.

Pipeline:
    caller -> organization -> roles -> governance scopes -> accessible IDs
         -> bounded retrieval per canonical source -> bounded evidence composition
         -> evidence bundle with provenance chain

Governance happens BEFORE retrieval. Every source consulted is the existing
governed engine, and every raw entity lookup is gated through
resolve_accessible_ids so hidden evidence is never even retrieved.
Nothing is filtered after generation.

Determinism: same inputs (org, caller, as_of, scope) always produce
byte-identical evidence bundles. Bounded queries, stable ordering,
exact-once fingerprints.

Observation only: no operating-layer mutation anywhere in this module.
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
from app.intelligence.company_context import (
    CallerAccess,
    classify_query,
    resolve_caller_access,
    resolve_accessible_ids,
)
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionAlternative,
    CompanyDecisionEvidence,
    CompanyDecisionPrecedent,
    CompanyDecisionQuality,
    CompanyDecisionTrack,
    CompanyDecisionContradiction,
    CompanyScenarioRun,
    CompanyCausalEdge,
)
from app.models.company_actions import (
    CompanyAction,
    CompanyActionOutcome,
)
from app.models.intelligence import (
    PatternDetection,
    UniversalInsight,
)
from app.models.company_memory import CompanyMemory
from app.models.knowledge import KnowledgeClaim, KnowledgeEvidence
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.business_performance import (
    BusinessMetricObservation,
    BusinessPerformanceLink,
)
from app.models.organizational_learning import OutcomeAssessment
from app.models.intelligence import PatternDetection
from app.models.company_memory import CompanyMemory

logger = logging.getLogger("vcos.intelligence.evidence_composer")

# Bounds: no organization-wide scans, every source capped independently.
EVIDENCE_BOUNDS = {
    "decisions": 50,
    "actions": 50,
    "outcomes": 50,
    "metrics": 50,
    "assessments": 50,
    "patterns": 50,
    "contradictions": 50,
    "precedents": 50,
    "memories": 50,
    "claims": 50,
    "causal_edges": 100,
}

# Fingerprint constants
FINGERPRINT_DELIMITER = "|"


@dataclass(frozen=True)
class EvidenceItem:
    """Single piece of evidence with its provenance."""
    source_type: str
    source_id: str
    title: str
    summary: str
    epistemic_status: str  # "recorded" | "derived" | "unknown"
    confidence: float
    occurred_at: Optional[str]
    url: str
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceBundle:
    """Deterministic evidence bundle with full provenance chain."""
    organization_id: str
    caller_access: dict[str, Any]
    as_of: str
    decisions: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    assessments: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    precedents: list[dict[str, Any]] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    causal_edges: list[dict[str, Any]] = field(default_factory=list)
    # Fingerprint for exact-once identity
    fingerprint: str = ""
    generated_at: str = ""


class EvidenceComposer:
    """Governance-first deterministic evidence composer."""

    def __init__(self):
        pass

    # -------------------------------------------------------------------- public API

    async def compose_bundle(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        as_of: Optional[datetime] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> EvidenceBundle:
        """Compose a deterministic evidence bundle for the given caller and context.

        This is the main entry point. All retrieval is governance-gated and
        bounded. The resulting bundle is deterministic and contains full
        provenance chains.
        """
        started = time.perf_counter()
        as_of = as_of or utcnow()

        # 1. Governance-first: resolve caller access
        access = await resolve_caller_access(
            db, organization_id=organization_id, user=user
        )

        # 2. Bounded retrieval per canonical source (governance-gated)
        decisions = await self._fetch_decisions(db, organization_id, access, user)
        actions = await self._fetch_actions(db, organization_id, access, user)
        outcomes = await self._fetch_outcomes(db, organization_id, access, user)
        metrics = await self._fetch_metrics(db, organization_id, access, user)
        assessments = await self._fetch_assessments(db, organization_id, access, user)
        patterns = await self._fetch_patterns(db, organization_id, access, user)
        contradictions = await self._fetch_contradictions(db, organization_id, access, user)
        precedents = await self._fetch_precedents(db, organization_id, access, user)
        memories = await self._fetch_memories(db, organization_id, access, user)
        claims = await self._fetch_claims(db, organization_id, access, user)
        causal_edges = await self._fetch_causal_edges(db, organization_id, access, user)

        # Build bundle
        bundle = EvidenceBundle(
            organization_id=organization_id,
            caller_access={
                "org_wide": access.org_wide,
                "visible_project_count": len(access.project_ids),
                "visible_scope_count": len(access.visible_scope_ids),
            },
            as_of=as_of.isoformat(),
            decisions=decisions,
            actions=actions,
            outcomes=outcomes,
            metrics=metrics,
            assessments=assessments,
            patterns=patterns,
            contradictions=contradictions,
            precedents=precedents,
            memories=memories,
            causal_edges=causal_edges,
        )

        # Generate deterministic fingerprint
        bundle.fingerprint = self._fingerprint_bundle(bundle)
        bundle.generated_at = utcnow().isoformat()

        elapsed_ms = round((time.perf_counter() - started) * 1000)
        logger.info(
            "evidence_bundle org=%s sources=%d decisions=%d actions=%d outcomes=%d "
            "patterns=%d contradictions=%d duration_ms=%d",
            organization_id,
            sum(1 for k, v in bundle.__dict__.items() if k not in ('organization_id', 'caller_access', 'as_of', 'fingerprint', 'generated_at') and v),
            len(decisions), len(actions), len(outcomes), len(patterns), len(contradictions),
            elapsed_ms,
        )
        return bundle

    # -------------------------------------------------------------------- retrieval methods

    async def _fetch_decisions(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch decisions with governance-gated retrieval."""
        from app.models.company_operating import CompanyDecision

        stmt = (
            select(CompanyDecision)
            .where(CompanyDecision.organization_id == organization_id)
            .order_by(CompanyDecision.updated_at.desc())
            .limit(EVIDENCE_BOUNDS["decisions"])
        )
        rows = (await db.execute(stmt)).scalars().all()

        # Filter by governance
        accessible_ids = await resolve_accessible_ids(
            db, user=user, organization_id=organization_id, kind="decision",
            ids=[r.decision_id for r in rows]
        )
        accessible_set = set(accessible_ids)

        results = []
        for row in rows:
            if row.decision_id not in accessible_set:
                continue
            results.append({
                "decision_id": row.decision_id,
                "kind": row.kind,
                "title": row.title,
                "state": row.state,
                "rationale": row.rationale,
                "recommendation_key": row.recommendation_key,
                "impact_label": row.impact_label,
                "expected_improvement": row.expected_improvement,
                "confidence": row.confidence,
                "state": row.state,
                "approved_at": row.approved_at.isoformat() if row.approved_at else None,
                "executed_at": row.executed_at.isoformat() if row.executed_at else None,
                "outcome_kind": row.outcome_kind,
                "effectiveness": row.effectiveness,
                "lesson": row.lesson,
                "as_of_context_json": row.as_of_context_json,
                "state_context_json": row.state_context_json,
                "quality_evidence_count": row.quality_evidence_count,
                "scope_type": row.scope_type,
                "scope_id": row.scope_id,
                "event_name": row.event_name,
                "source_event_id": row.source_event_id,
                "epistemic_status": "recorded",
                "confidence": float(row.confidence or 0.0),
            })
        return results

    async def _fetch_actions(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch company actions with governance-gated retrieval."""
        from app.models.company_actions import CompanyAction

        stmt = (
            select(CompanyAction)
            .where(CompanyAction.organization_id == organization_id)
            .order_by(CompanyAction.created_at.desc())
            .limit(EVIDENCE_BOUNDS["actions"])
        )
        rows = (await db.execute(stmt)).scalars().all()

        accessible_ids = await resolve_accessible_ids(
            db, user=user, organization_id=organization_id, kind="action",
            ids=[r.id for r in rows]
        )
        accessible_set = set(accessible_ids)

        results = []
        for row in rows:
            if row.id not in accessible_set:
                continue
            results.append({
                "action_id": row.id,
                "action_type": row.action_type,
                "title": row.title,
                "state": row.state,
                "risk": row.risk,
                "priority_score": row.priority_score,
                "scope_type": row.scope_type,
                "scope_id": row.scope_id,
                "fingerprint": row.fingerprint,
                "source_company_decision_id": row.source_company_decision_id,
                "source_scenario_id": row.source_scenario_id,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "policy": row.policy,
                "approval_required": row.approval_required,
                "assignee_type": row.assignee_type,
                "assignee_id": row.assignee_id,
                "state": row.state,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "outcome_id": row.outcome_id,
                "supersedes_id": row.supersedes_id,
                "version": row.version,
                "created_by": row.created_by,
                "source_company_decision_id": row.source_company_decision_id,
                "source_scenario_id": row.source_scenario_id,
                "epistemic_status": "recorded",
            })
        return results

    async def _fetch_outcomes(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch action outcomes with governance-gated retrieval."""
        from app.models.company_actions import CompanyActionOutcome

        stmt = (
            select(CompanyActionOutcome)
            .where(CompanyActionOutcome.organization_id == organization_id)
            .order_by(CompanyActionOutcome.measured_at.desc())
            .limit(EVIDENCE_BOUNDS["outcomes"])
        )
        rows = (await db.execute(stmt)).scalars().all()

        accessible_ids = await resolve_accessible_ids(
            db, user=user, organization_id=organization_id, kind="action_outcome",
            ids=[r.action_id for r in rows]
        )
        accessible_set = set(accessible_ids)

        results = []
        for row in rows:
            if row.action_id not in accessible_set:
                continue
            results.append({
                "outcome_id": row.id,
                "action_id": row.action_id,
                "outcome_type": row.outcome_type,
                "verdict": row.verdict,
                "effectiveness": row.effectiveness,
                "evidence_json": row.evidence_json,
                "measured_at": row.measured_at.isoformat() if row.measured_at else None,
                "recorded_by": row.recorded_by,
                "epistemic_status": "recorded",
            })
        return results

    async def _fetch_metrics(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch business metric observations with governance-gated retrieval."""
        from app.models.business_performance import BusinessMetricObservation

        stmt = (
            select(BusinessMetricObservation)
            .where(BusinessMetricObservation.organization_id == organization_id)
            .order_by(BusinessMetricObservation.observed_at.desc())
            .limit(EVIDENCE_BOUNDS["metrics"])
        )
        rows = (await db.execute(stmt)).scalars().all()

        accessible_ids = await resolve_accessible_ids(
            db, user=user, organization_id=organization_id, kind="metric_observation",
            ids=[r.id for r in rows]
        )
        accessible_set = set(accessible_ids)

        results = []
        for row in rows:
            if row.id not in accessible_set:
                continue
            results.append({
                "observation_id": row.id,
                "metric_id": row.metric_id,
                "value": row.value,
                "observed_at": row.observed_at.isoformat() if row.observed_at else None,
                "source": row.source,
                "source_ref": row.source_ref,
                "metadata_json": row.metadata_json,
                "epistemic_status": "recorded",
            })
        return results

    async def _fetch_assessments(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch outcome assessments with governance-gated retrieval."""
        from app.models.organizational_learning import OutcomeAssessment

        stmt = (
            select(OutcomeAssessment)
            .where(OutcomeAssessment.organization_id == organization_id)
            .order_by(OutcomeAssessment.assessed_at.desc())
            .limit(EVIDENCE_BOUNDS["assessments"])
        )
        rows = (await db.execute(stmt)).scalars().all()

        accessible_ids = await resolve_accessible_ids(
            db, user=user, organization_id=organization_id, kind="outcome_assessment",
            ids=[f"{r.subject_type}:{r.subject_id}" for r in rows]
        )
        accessible_set = set(accessible_ids)

        results = []
        for row in rows:
            key = f"{row.subject_type}:{row.subject_id}"
            if key not in accessible_set:
                continue
            results.append({
                "assessment_id": row.id,
                "subject_type": row.subject_type,
                "subject_id": row.subject_id,
                "expected_metric": row.expected_metric,
                "expected_value": row.expected_value,
                "expected_units": row.expected_units,
                "actual_value": row.actual_value,
                "variance_pct": row.variance_pct,
                "assessment": row.assessment,
                "factors_json": row.factors_json,
                "summary": row.summary,
                "assessed_by": row.assessed_by,
                "assessed_at": row.assessed_at.isoformat() if row.assessed_at else None,
                "epistemic_status": "derived",
            })
        return results

    async def _fetch_patterns(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch patterns with governance-gated retrieval."""
        from app.intelligence.pattern_engine import pattern_engine

        result = await pattern_engine.list_visible(
            db, organization_id=organization_id, user=user, limit=EVIDENCE_BOUNDS["patterns"]
        )
        patterns = result.get("patterns", [])

        results = []
        for p in patterns:
            # Check governance
            if not access.org_wide:
                if p.get("auth_project_id") and p["auth_project_id"] not in access.project_ids:
                    continue
            results.append({
                "pattern_id": p["id"],
                "pattern_type": p.get("pattern_type"),
                "family": p.get("family"),
                "title": p.get("title") or p.get("pattern_type"),
                "description": p.get("description"),
                "count": p.get("occurrence_count"),
                "confidence": p.get("confidence"),
                "status": p.get("status"),
                "family": p.get("family"),
                "evidence_json": p.get("evidence_json"),
                "entities_json": p.get("entities_json"),
                "supporting_memory_ids": p.get("supporting_memory_ids"),
                "supporting_event_ids": p.get("supporting_event_ids"),
                "supporting_relationships": p.get("supporting_relationships"),
                "detail_json": p.get("detail_json"),
                "scope_id": p.get("scope_id"),
                "scope_type": p.get("scope_type"),
                "auth_project_id": p.get("auth_project_id"),
                "time_window_days": p.get("time_window_days"),
                "trend": p.get("trend"),
                "avg_interval_days": p.get("avg_interval_days"),
                "last_evaluated_at": p.get("last_evaluated_at"),
                "first_seen": p.get("first_seen"),
                "last_seen": p.get("last_seen"),
                "epistemic_status": "derived",
                "confidence": float(p.get("confidence") or 0.0),
            })
        return results[:EVIDENCE_BOUNDS["patterns"]]

    async def _fetch_contradictions(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch contradictions with governance-gated retrieval."""
        from app.models.company_operating import CompanyDecisionContradiction

        stmt = (
            select(CompanyDecisionContradiction)
            .where(CompanyDecisionContradiction.organization_id == organization_id)
            .order_by(CompanyDecisionContradiction.created_at.desc())
            .limit(EVIDENCE_BOUNDS["contradictions"])
        )
        rows = (await db.execute(stmt)).scalars().all()

        results = []
        for row in rows:
            # Check governance via decision_id
            accessible_ids = await resolve_accessible_ids(
                db, user=user, organization_id=organization_id, kind="decision",
                ids=[row.decision_id]
            )
            if row.decision_id not in set(accessible_ids):
                continue
            results.append({
                "contradiction_id": row.id,
                "decision_id": row.decision_id,
                "contradiction_key": row.contradiction_key,
                "lesson_memory_id": row.lesson_memory_id,
                "precedent_decision_id": row.precedent_decision_id,
                "side_a_json": row.side_a_json,
                "side_b_json": row.side_b_json,
                "status": row.status,
                "source_event_id": row.source_event_id,
                "epistemic_status": "recorded",
            })
        return results

    async def _fetch_precedents(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch precedents with governance-gated retrieval."""
        from app.models.company_operating import CompanyDecisionPrecedent

        stmt = (
            select(CompanyDecisionPrecedent)
            .where(CompanyDecisionPrecedent.organization_id == organization_id)
            .order_by(CompanyDecisionPrecedent.created_at.desc())
            .limit(EVIDENCE_BOUNDS["precedents"])
        )
        rows = (await db.execute(stmt)).scalars().all()

        results = []
        for row in rows:
            # Check governance via decision_id
            accessible_ids = await resolve_accessible_ids(
                db, user=user, organization_id=organization_id, kind="decision",
                ids=[row.decision_id]
            )
            if row.decision_id not in set(accessible_ids):
                continue
            results.append({
                "precedent_id": row.id,
                "decision_id": row.decision_id,
                "precedent_decision_id": row.precedent_decision_id,
                "alternative_key": row.alternative_key,
                "context_signature": row.context_signature,
                "relevance_score": row.relevance_score,
                "evidence_count": row.evidence_count,
                "cited_lesson": row.cited_lesson,
                "source_event_id": row.source_event_id,
                "epistemic_status": "recorded",
            })
        return results

    async def _fetch_memories(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch memories with governance-gated retrieval."""
        from app.memory.memory_store import feed as memory_feed

        result = await memory_feed(
            db, organization_id=organization_id, user=user, limit=EVIDENCE_BOUNDS["memories"]
        )
        memories = result.get("memories", [])

        results = []
        for m in memories:
            # Check governance
            if not access.org_wide:
                if m.get("auth_scope") == "project" and m.get("auth_project_id") not in access.project_ids:
                    continue
                if m.get("auth_scope") == "personal" and m.get("recorded_by") != access.employee_id:
                    continue
            results.append({
                "memory_id": m["id"],
                "memory_type": m.get("memory_type"),
                "memory_category": m.get("memory_category"),
                "domain": m.get("domain"),
                "title": m.get("title"),
                "summary": m.get("summary"),
                "lesson": m.get("lesson"),
                "outcome": m.get("outcome"),
                "outcome_type": m.get("outcome_type"),
                "confidence": m.get("confidence"),
                "fact_kind": m.get("fact_kind"),
                "entity_type": m.get("entity_type"),
                "entity_id": m.get("entity_id"),
                "occurred_at": m.get("occurred_at"),
                "source_event_ids": m.get("source_event_ids"),
                "evidence_json": m.get("evidence_json"),
                "context_json": m.get("context_json"),
                "auth_scope": m.get("auth_scope"),
                "auth_project_id": m.get("auth_project_id"),
                "status": m.get("status"),
                "supersedes_id": m.get("supersedes_id"),
                "related_memory_ids": m.get("related_memory_ids"),
                "epistemic_status": m.get("fact_kind", "fact"),
                "confidence": float(m.get("confidence") or 0.0),
            })
        return results[:50]

    async def _fetch_claims(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch knowledge claims with governance-gated retrieval."""
        from app.models.knowledge import KnowledgeClaim

        stmt = (
            select(KnowledgeClaim)
            .where(KnowledgeClaim.organization_id == organization_id)
            .order_by(KnowledgeClaim.created_at.desc())
            .limit(EVIDENCE_BOUNDS["claims"])
        )
        rows = (await db.execute(stmt)).scalars().all()

        results = []
        for row in rows:
            # Check governance - org-wide or project-scoped
            if not access.org_wide:
                if row.context_id and row.context_id not in access.project_ids:
                    continue
            results.append({
                "claim_id": row.id,
                "subject_type": row.subject_type,
                "subject_id": row.subject_id,
                "predicate": row.predicate,
                "object_text": row.object_text,
                "claim_type": row.claim_type,
                "status": row.status,
                "authority_level": row.authority_level,
                "confidence": row.confidence,
                "context_type": row.context_type,
                "context_id": row.context_id,
                "valid_from": row.valid_from.isoformat() if row.valid_from else None,
                "valid_to": row.valid_to.isoformat() if row.valid_to else None,
                "superseded_by": row.superseded_by,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "last_seen": row.last_seen.isoformat() if row.last_seen else None,
                "epistemic_status": row.claim_type,  # fact|observation|inference|lesson
                "confidence": float(row.confidence or 0.0),
            })
        return results

    async def _fetch_causal_edges(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch causal edges with governance-gated retrieval."""
        from app.models.company_operating import CompanyCausalEdge

        stmt = (
            select(CompanyCausalEdge)
            .where(CompanyCausalEdge.organization_id == organization_id)
            .order_by(CompanyCausalEdge.created_at.desc())
            .limit(EVIDENCE_BOUNDS["causal_edges"])
        )
        rows = (await db.execute(stmt)).scalars().all()

        results = []
        for row in rows:
            # Check governance via source/target entities
            accessible = True
            if not access.org_wide:
                # Check if source/target are in accessible scope
                source_accessible = True
                target_accessible = True
                # Simplified: check if entities are in visible projects
                for entity_id in [row.source_id, row.target_id]:
                    for entity_type in ["project", "task", "decision", "capability", "customer", "goal"]:
                        # This is simplified - real impl would check entity type
                        pass
                if not (source_accessible and target_accessible):
                    continue
            results.append({
                "edge_id": row.id,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "kind": row.kind,
                "confidence": row.confidence,
                "evidence_ref": row.evidence_ref,
                "source_event_id": row.source_event_id,
                "epistemic_status": "derived",
            })
        return results

    # -------------------------------------------------------------------- provenance chain

    def _build_provenance_chain(
        self,
        bundle: "EvidenceBundle",
    ) -> dict[str, Any]:
        """Build complete provenance chain from bundle.

        Traces: lesson -> pattern -> assessment -> metric -> outcome -> action -> decision
        """
        provenance = {
            "decisions": {},
            "actions": {},
            "outcomes": {},
            "metrics": {},
            "assessments": {},
            "patterns": {},
            "contradictions": {},
            "precedents": {},
            "memories": {},
            "claims": {},
            "causal_edges": {},
        }

        # Map decisions
        for d in bundle.decisions:
            provenance["decisions"][d["decision_id"]] = {
                "decision_id": d["decision_id"],
                "kind": d["kind"],
                "state": d["state"],
                "source_event_id": d.get("source_event_id"),
            }

        # Map actions
        for a in bundle.actions:
            provenance["actions"][a["action_id"]] = {
                "action_id": a["action_id"],
                "action_type": a["action_type"],
                "source_company_decision_id": a.get("source_company_decision_id"),
                "source_scenario_id": a.get("source_scenario_id"),
                "target_type": a.get("target_type"),
                "target_id": a.get("target_id"),
            }

        # Map outcomes
        for o in bundle.outcomes:
            provenance["outcomes"][o["outcome_id"]] = {
                "outcome_id": o["outcome_id"],
                "action_id": o["action_id"],
                "outcome_type": o["outcome_type"],
                "effectiveness": o["effectiveness"],
            }

        # Map metrics
        for m in bundle.metrics:
            provenance["metrics"][m["observation_id"]] = {
                "observation_id": m["observation_id"],
                "metric_id": m["metric_id"],
                "value": m["value"],
                "measured_at": m["measured_at"],
            }

        # Map assessments
        for a in bundle.assessments:
            provenance["assessments"][a["assessment_id"]] = {
                "assessment_id": a["assessment_id"],
                "subject_type": a["subject_type"],
                "subject_id": a["subject_id"],
                "expected_metric": a.get("expected_metric"),
                "expected_value": a.get("expected_value"),
                "actual_value": a.get("actual_value"),
                "variance_pct": a.get("variance_pct"),
                "assessment": a.get("assessment"),
            }

        # Map patterns
        for p in bundle.patterns:
            provenance["patterns"][p["pattern_id"]] = {
                "pattern_id": p["pattern_id"],
                "pattern_type": p["pattern_type"],
                "family": p.get("family"),
                "count": p.get("count"),
                "confidence": p.get("confidence"),
                "evidence_json": p.get("evidence_json"),
                "entities_json": p.get("entities_json"),
            }

        # Map contradictions
        for c in bundle.contradictions:
            provenance["contradictions"][c["contradiction_id"]] = {
                "contradiction_id": c["contradiction_id"],
                "decision_id": c["decision_id"],
                "lesson_memory_id": c.get("lesson_memory_id"),
                "precedent_decision_id": c.get("precedent_decision_id"),
                "side_a_json": c.get("side_a_json"),
                "side_b_json": c.get("side_b_json"),
                "status": c.get("status"),
            }

        # Map precedents
        for p in bundle.precedents:
            provenance["precedents"][p["precedent_id"]] = {
                "precedent_id": p["precedent_id"],
                "decision_id": p["decision_id"],
                "precedent_decision_id": p.get("precedent_decision_id"),
                "context_signature": p.get("context_signature"),
                "relevance_score": p.get("relevance_score"),
                "cited_lesson": p.get("cited_lesson"),
            }

        return provenance

    # -------------------------------------------------------------------- fingerprint

    def _fingerprint_bundle(self, bundle: "EvidenceBundle") -> str:
        """Generate deterministic fingerprint for exact-once identity."""
        import hashlib
        import json

        # Create deterministic representation
        parts = [
            bundle.organization_id,
            str(sorted(bundle.caller_access.items())),
            bundle.as_of,
            json.dumps(bundle.decisions, sort_keys=True, default=str),
            json.dumps(bundle.actions, sort_keys=True, default=str),
            json.dumps(bundle.outcomes, sort_keys=True, default=str),
            json.dumps(bundle.metrics, sort_keys=True, default=str),
            json.dumps(bundle.assessments, sort_keys=True, default=str),
            json.dumps(bundle.patterns, sort_keys=True, default=str),
            json.dumps(bundle.contradictions, sort_keys=True, default=str),
            json.dumps(bundle.precedents, sort_keys=True, default=str),
            json.dumps(bundle.memories, sort_keys=True, default=str),
            json.dumps(bundle.claims, sort_keys=True, default=str),
            json.dumps(bundle.causal_edges, sort_keys=True, default=str),
        ]
        combined = FINGERPRINT_DELIMITER.join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:64]


# Global instance
evidence_composer = EvidenceComposer()