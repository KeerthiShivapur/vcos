"""Slice 4H.7 Phase D -- Cohort Builder.

Governance-first, deterministic cohort formation from canonical 4H decisions.
A cohort is a governed, bounded set of comparable decisions that share
contract-defined dimensions.

Pipeline:
    caller -> organization -> roles -> governance scopes -> accessible IDs
         -> bounded decision retrieval -> cohort formation -> cohort signature

Governance happens BEFORE retrieval. Every decision lookup is gated through
resolve_accessible_ids so hidden decisions are never even retrieved.
Nothing is filtered after generation.

Determinism: same inputs (org, caller, as_of, scope) always produce
byte-identical cohort signatures and membership.

Observation only: no operating-layer mutation anywhere in this module.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import (
    CallerAccess,
    resolve_accessible_ids,
    resolve_caller_access,
)
from app.models.company_operating import (
    CompanyDecision,
    COMPANY_HEALTH_DOMAINS,
    DECISION_KINDS,
    COMPANY_SCOPE_TYPES,
)

logger = logging.getLogger("vcos.intelligence.cohort_builder")

# Contract constants (from SLICE4H7_MASTER_IMPLEMENTATION_CONTRACT.md)
MIN_COHORT_SIZE = 3
MAX_COHORT_SIZE = 50
COHORT_WINDOW_DAYS = 90
COHORT_WINDOW_DAYS_MAX = 365

# Cohort signature dimensions (from contract Section 5.2)
COHORT_DIMENSIONS = (
    "decision_kind",
    "scope_type",
    "scope_id",
    "business_context_hash",
    "temporal_window_start",
    "temporal_window_end",
)

FINGERPRINT_DELIMITER = "|"


@dataclass(frozen=True)
class CohortMember:
    """Single decision member of a cohort."""
    decision_id: str
    kind: str
    title: str
    state: str
    outcome_kind: Optional[str]
    effectiveness: Optional[float]
    project_id: Optional[str]
    goal_id: Optional[str]
    department_id: Optional[str]
    team_id: Optional[str]
    occurred_at: Optional[str]
    source_event_id: str


@dataclass(frozen=True)
class Cohort:
    """Governed, deterministic cohort of comparable decisions."""
    organization_id: str
    caller_access: dict[str, Any]
    as_of: str
    # Cohort signature dimensions (contract Section 5.3)
    decision_kind: str
    scope_type: str
    scope_id: Optional[str]
    business_context_hash: str
    temporal_window_start: str
    temporal_window_end: str
    # Members
    members: list[dict[str, Any]] = field(default_factory=list)
    # Cohort signature (deterministic)
    signature: str = ""
    # Governance metadata
    org_wide: bool = False
    visible_project_count: int = 0
    visible_scope_count: int = 0
    # Cohort quality metrics
    member_count: int = 0
    outcome_quality: float = 0.0
    evidence_coverage: float = 0.0
    temporal_spread_days: int = 0
    # Fingerprint for exact-once identity
    fingerprint: str = ""
    generated_at: str = ""


class CohortBuilder:
    """Governance-first deterministic cohort builder."""

    def __init__(self):
        pass

    # -------------------------------------------------------------------- public API

    async def build_cohort(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        anchor_decision_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[dict[str, Any]]:
        """Build a governed cohort around an anchor decision.

        This is the main entry point. All retrieval is governance-gated and
        bounded. The resulting cohort is deterministic and contains only
        decisions accessible to the caller.

        Returns None if anchor decision not found or not accessible.
        """
        started = time.perf_counter()
        as_of = as_of or utcnow()

        # 1. Governance-first: resolve caller access
        access = await resolve_caller_access(
            db, organization_id=organization_id, user=user
        )

        # 2. Fetch anchor decision (governance-gated)
        anchor = await self._fetch_anchor_decision(
            db, organization_id, access, anchor_decision_id, user
        )
        if anchor is None:
            return None

        # 3. Build cohort signature dimensions from anchor
        cohort_signature_dims = self._build_cohort_signature(anchor, as_of)

        # 4. Fetch candidate decisions (governance-gated, bounded)
        candidates = await self._fetch_candidate_decisions(
            db, organization_id, access, cohort_signature_dims, user
        )

        # 5. Form cohort from candidates
        cohort = self._form_cohort(
            db=db,
            organization_id=organization_id,
            access=access,
            as_of=utcnow(),
            anchor=anchor,
            candidates=candidates,
            signature_dims=cohort_signature_dims,
        )

        elapsed_ms = round((time.perf_counter() - started) * 1000)
        logger.info(
            "cohort_built org=%s anchor=%s members=%d quality=%.2f duration_ms=%d",
            organization_id, anchor_decision_id, cohort["member_count"],
            cohort["outcome_quality"], round((time.perf_counter() - started) * 1000),
        )
        return cohort

    async def build_cohort_for_decision(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        decision_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[dict[str, Any]]:
        """Build cohort anchored on a specific decision (used by PatternQualifier)."""
        return await self.build_cohort(
            db=db,
            organization_id=organization_id,
            user=user,
            anchor_decision_id=decision_id,
            as_of=as_of,
        )

    async def list_cohorts(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        limit: int = 20,
        as_of: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """List recent cohorts (governed, bounded)."""
        as_of = as_of or utcnow()
        access = await resolve_caller_access(
            db, organization_id=organization_id, user=user
        )

        # Fetch recent decisions as potential anchors
        stmt = (
            select(CompanyDecision)
            .where(CompanyDecision.organization_id == organization_id)
            .order_by(CompanyDecision.updated_at.desc())
            .limit(50)
        )
        rows = (await db.execute(stmt)).scalars().all()

        accessible_ids = await resolve_accessible_ids(
            db, user=None, organization_id=organization_id, kind="decision",
            ids=[r.decision_id for r in rows]
        )
        accessible_set = set(accessible_ids)

        cohorts = []
        for row in rows:
            if row.decision_id not in accessible_set:
                continue
            cohort = await self.build_cohort(
                db, organization_id=organization_id, user=user,
                anchor_decision_id=row.decision_id
            )
            if cohort and cohort["member_count"] >= MIN_COHORT_SIZE:
                cohorts.append({
                    "anchor_decision_id": row.decision_id,
                    "member_count": cohort["member_count"],
                    "signature": cohort["signature"],
                    "outcome_quality": cohort["outcome_quality"],
                    "temporal_span_days": cohort["temporal_spread_days"],
                })
            if len(cohorts) >= min(limit, 50):
                break
        return cohorts

    # -------------------------------------------------------------------- anchor & signature

    async def _fetch_anchor_decision(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        decision_id: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """Fetch anchor decision with governance check."""
        accessible_ids = await resolve_accessible_ids(
            db, user=user, organization_id=organization_id, kind="decision",
            ids=[decision_id]
        )
        if decision_id not in accessible_ids:
            return None

        # Query by decision_id, not primary key
        from sqlalchemy import select
        row = (
            await db.execute(
                select(CompanyDecision).where(
                    CompanyDecision.organization_id == organization_id,
                    CompanyDecision.decision_id == decision_id,
                )
            )
        ).scalars().first()
        if row is None or row.organization_id != organization_id:
            return None

        return {
            "decision_id": row.decision_id,
            "kind": row.kind,
            "title": row.title,
            "state": row.state,
            "rationale": row.rationale,
            "recommendation_key": row.recommendation_key,
            "scope_type": row.scope_type,
            "scope_id": row.scope_id,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "source_event_id": row.source_event_id,
        }

    def _build_cohort_signature(
        self,
        anchor: dict[str, Any],
        as_of: datetime,
    ) -> dict[str, Any]:
        """Build cohort signature dimensions from anchor (contract Section 5.3)."""
        # anchor["updated_at"] is already an ISO format string
        updated_at_str = anchor.get("updated_at")
        if updated_at_str:
            try:
                window_end = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                window_end = as_of
        else:
            window_end = as_of
        window_start = as_of - timedelta(days=COHORT_WINDOW_DAYS)

        # Business context hash from relevant entities
        # Note: anchor decision only has limited fields; extended context
        # would require joining with related entities (projects, goals, etc.)
        context_entities = []
        # TODO: extend with project/goal/department/team context when available

        context_hash = hashlib.sha256(
            "|".join(sorted(context_entities)).encode()
        ).hexdigest()[:16] if context_entities else "none"

        return {
            "decision_kind": anchor["kind"],
            "scope_type": anchor.get("scope_type", "org"),
            "scope_id": anchor.get("scope_id"),
            "business_context_hash": context_hash,
            "temporal_window_start": window_start.isoformat(),
            "temporal_window_end": window_end.isoformat(),
        }

    # -------------------------------------------------------------------- candidate retrieval

    async def _fetch_candidate_decisions(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        signature_dims: dict[str, Any],
        user: Any,
    ) -> list[dict[str, Any]]:
        """Fetch candidate decisions matching cohort signature (governed, bounded)."""
        kind = signature_dims["decision_kind"]
        scope_type = signature_dims["scope_type"]
        scope_id = signature_dims["scope_id"]
        window_start = signature_dims["temporal_window_start"]
        window_end = signature_dims["temporal_window_end"]

        # Build query with filters matching cohort signature
        filters = [
            CompanyDecision.organization_id == organization_id,
            CompanyDecision.kind == signature_dims["decision_kind"],
        ]

        # Scope filtering
        if scope_type == "project" and signature_dims["scope_id"]:
            filters.append(CompanyDecision.project_id == scope_id)
        elif scope_type == "goal" and signature_dims["scope_id"]:
            filters.append(CompanyDecision.goal_id == scope_id)
        elif scope_type == "department" and signature_dims["scope_id"]:
            filters.append(CompanyDecision.department_id == scope_id)
        elif scope_type == "team" and signature_dims["scope_id"]:
            filters.append(CompanyDecision.team_id == scope_id)
        elif scope_type == "org":
            # No additional scope filter for org-wide
            pass

        # Temporal window
        window_start_dt = datetime.fromisoformat(signature_dims["temporal_window_start"].replace("Z", "+00:00"))
        window_end_dt = datetime.fromisoformat(signature_dims["temporal_window_end"].replace("Z", "+00:00"))
        filters.append(CompanyDecision.updated_at >= window_start_dt)
        filters.append(CompanyDecision.updated_at <= window_end_dt)

        stmt = (
            select(CompanyDecision)
            .where(*filters)
            .order_by(CompanyDecision.updated_at.desc())
            .limit(MAX_COHORT_SIZE * 2)  # Fetch extra for filtering
        )
        rows = (await db.execute(stmt)).scalars().all()

        # Governance filter
        candidate_ids = [r.decision_id for r in rows]
        accessible_ids = await resolve_accessible_ids(
            db, user=user, organization_id=organization_id, kind="decision",
            ids=candidate_ids
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
                "outcome_kind": row.outcome_kind,
                "effectiveness": row.effectiveness,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "source_event_id": row.source_event_id,
                "rationale": row.rationale,
                "scope_type": row.scope_type,
                "scope_id": row.scope_id,
            })
        return results[:MAX_COHORT_SIZE]

    # -------------------------------------------------------------------- cohort formation

    def _form_cohort(
        self,
        db: AsyncSession,
        organization_id: str,
        access: CallerAccess,
        as_of: datetime,
        anchor: dict[str, Any],
        candidates: list[dict[str, Any]],
        signature_dims: dict[str, Any],
    ) -> dict[str, Any]:
        """Form cohort from anchor and candidates."""
        # Filter to comparable decisions
        members = []
        for c in candidates:
            if c["decision_id"] == anchor["decision_id"]:
                continue
            # Check comparability (kind, scope, temporal window)
            if c["kind"] != signature_dims["decision_kind"]:
                continue
            # Temporal window check
            if c["updated_at"]:
                updated = datetime.fromisoformat(c["updated_at"].replace("Z", "+00:00"))
                window_start = datetime.fromisoformat(signature_dims["temporal_window_start"].replace("Z", "+00:00"))
                window_end = datetime.fromisoformat(signature_dims["temporal_window_end"].replace("Z", "+00:00"))
                if not (window_start <= updated <= window_end):
                    continue
            members.append(CohortMember(
                decision_id=c["decision_id"],
                kind=c["kind"],
                title=c["title"],
                state=c["state"],
                outcome_kind=c["outcome_kind"],
                effectiveness=c["effectiveness"],
                project_id=c["project_id"],
                goal_id=c["goal_id"],
                department_id=c["department_id"],
                team_id=c["team_id"],
                occurred_at=c["updated_at"],
                source_event_id=c["source_event_id"],
            ))

        # Add anchor as first member
        anchor_member = CohortMember(
            decision_id=anchor["decision_id"],
            kind=anchor["kind"],
            title=anchor["title"],
            state=anchor["state"],
            outcome_kind=anchor.get("outcome_kind"),
            effectiveness=anchor.get("effectiveness"),
            project_id=anchor.get("project_id"),
            goal_id=anchor.get("goal_id"),
            department_id=anchor.get("department_id"),
            team_id=anchor.get("team_id"),
            occurred_at=anchor.get("updated_at"),
            source_event_id=anchor.get("source_event_id"),
        )

        all_members = [anchor_member] + members

        # Quality metrics
        member_count = len(all_members)
        outcome_quality = self._calculate_outcome_quality(all_members)
        evidence_coverage = self._calculate_evidence_coverage(all_members)
        temporal_spread = self._calculate_temporal_spread(all_members)

        # Build cohort signature
        signature = self._compute_cohort_signature(
            signature_dims=signature_dims,
        )
        # Store signature in signature_dims for later use
        signature_dims["cohort_signature"] = signature

        # Fingerprint for exact-once
        fingerprint = self._fingerprint_cohort(
            organization_id=access.organization_id,
            signature_dims=signature_dims,
            members=all_members,
        )

        return {
            "organization_id": organization_id,
            "caller_access": {
                "org_wide": access.org_wide,
                "visible_project_count": len(access.project_ids),
                "visible_scope_count": len(access.visible_scope_ids),
            },
            "as_of": utcnow().isoformat(),
            "decision_kind": signature_dims["decision_kind"],
            "scope_type": signature_dims["scope_type"],
            "scope_id": signature_dims["scope_id"],
            "business_context_hash": signature_dims["business_context_hash"],
            "temporal_window_start": signature_dims["temporal_window_start"],
            "temporal_window_end": signature_dims["temporal_window_end"],
            "members": [self._serialize_member(m) for m in all_members],
            "signature": signature,
            "fingerprint": fingerprint,
            "org_wide": access.org_wide,
            "visible_project_count": len(access.project_ids),
            "visible_scope_count": len(access.visible_scope_ids),
            "member_count": len(all_members),
            "outcome_quality": round(self._calculate_outcome_quality(all_members), 3),
            "evidence_coverage": round(self._calculate_evidence_coverage(all_members), 3),
            "temporal_spread_days": self._calculate_temporal_spread(all_members),
            "fingerprint": fingerprint,
            "generated_at": utcnow().isoformat(),
        }

    def _serialize_member(self, member: CohortMember) -> dict[str, Any]:
        return {
            "decision_id": member.decision_id,
            "kind": member.kind,
            "title": member.title,
            "state": member.state,
            "outcome_kind": member.outcome_kind,
            "effectiveness": member.effectiveness,
            "project_id": member.project_id,
            "goal_id": member.goal_id,
            "department_id": member.department_id,
            "team_id": member.team_id,
            "occurred_at": member.occurred_at,
            "source_event_id": member.source_event_id,
        }

    def _calculate_outcome_quality(self, members: list[CohortMember]) -> float:
        """Calculate outcome quality ratio (contract Section 7)."""
        if not members:
            return 0.0
        met = sum(1 for m in members if m.outcome_kind == "met")
        return met / len(members)

    def _calculate_evidence_coverage(self, members: list[CohortMember]) -> float:
        """Calculate evidence coverage ratio (contract Section 7)."""
        if not members:
            return 0.0
        with_evidence = sum(1 for m in members if m.source_event_id)
        return with_evidence / len(members)

    def _calculate_temporal_spread(self, members: list[CohortMember]) -> int:
        """Calculate temporal spread in days."""
        dates = []
        for m in members:
            if m.occurred_at:
                try:
                    dates.append(datetime.fromisoformat(m.occurred_at.replace("Z", "+00:00")))
                except (ValueError, AttributeError):
                    pass
        if len(dates) < 2:
            return 0
        dates.sort()
        return (max(dates) - min(dates)).days

    def _compute_cohort_signature(self, signature_dims: dict[str, Any]) -> str:
        """Generate deterministic cohort signature string."""
        parts = [
            signature_dims.get("decision_kind", ""),
            signature_dims.get("scope_type", "org"),
            signature_dims.get("scope_id") or "",
            signature_dims.get("business_context_hash", "none"),
            signature_dims.get("temporal_window_start", ""),
            signature_dims.get("temporal_window_end", ""),
        ]
        return FINGERPRINT_DELIMITER.join(str(p) for p in parts)

    def _fingerprint_cohort(
        self,
        organization_id: str,
        signature_dims: dict[str, Any],
        members: list,
    ) -> str:
        """Generate deterministic fingerprint for exact-once identity."""
        import json
        parts = [
            organization_id,
            self._compute_cohort_signature({
                "decision_kind": signature_dims["decision_kind"],
                "scope_type": signature_dims["scope_type"],
                "scope_id": signature_dims["scope_id"],
                "business_context_hash": signature_dims["business_context_hash"],
                "temporal_window_start": signature_dims["temporal_window_start"],
                "temporal_window_end": signature_dims["temporal_window_end"],
            }),
            json.dumps([m.decision_id for m in members], sort_keys=True),
        ]
        combined = FINGERPRINT_DELIMITER.join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:64]


# Global instance
cohort_builder = CohortBuilder()

# Contract constants (duplicated for local access)
MIN_COHORT_SIZE = 3
MAX_COHORT_SIZE = 50
COHORT_WINDOW_DAYS = 90
COHORT_WINDOW_DAYS_MAX = 365