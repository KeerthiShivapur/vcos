"""Slice 4D.5 — governed read surface for universal company insights.

Mirrors ``pattern_engine``: every read resolves the caller's access
(``resolve_caller_access``) and applies downward-only visibility — a
project-scoped insight is visible only inside the caller's visible scope
subtree; org-wide insights (governance / cross-project) are visible only to
organization-wide callers. Hidden insights are indistinguishable from missing
ones (None), so a restricted insight can never be leaked.

Reads only: the pipeline writes insights; this engine never mutates anything.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from app.db.database import AsyncSession
from app.intelligence import insight_pipeline
from app.models.intelligence import InsightEvent, UniversalInsight

logger = logging.getLogger("vcos.intelligence.insights")


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _present(row: UniversalInsight) -> dict[str, Any]:
    return {
        "id": row.id,
        "insight_type": row.insight_type,
        "key": row.key,
        "domain": row.domain,
        "severity": row.severity,
        "title": row.title,
        "claim": row.claim,
        "summary": row.summary,
        "confidence": round(row.confidence or 0.0, 3),
        "confidence_components": row.confidence_components or {},
        "evidence": (row.evidence_json or [])[:20],
        "relationships": (row.relationships_json or [])[:20],
        "supporting_pattern_ids": (row.supporting_pattern_ids or [])[:20],
        "supporting_memory_ids": (row.supporting_memory_ids or [])[:20],
        "scope_type": row.scope_type,
        "scope_id": row.scope_id,
        "auth_project_id": row.auth_project_id,
        "status": row.status,
        "affected_entities": row.affected_entities or [],
        "first_observed_at": _iso(row.first_observed_at),
        "last_observed_at": _iso(row.last_observed_at),
    }


def _visible_to(access: Any, insight: UniversalInsight) -> bool:
    if access.org_wide:
        return True
    if insight.scope_type == "project" and insight.scope_id:
        return insight.scope_id in access.visible_scope_ids
    return False


def _status_filter(status: Optional[str]) -> Any:
    if status is None:
        return UniversalInsight.status.in_(("active", "faded"))
    if status == "all":
        return UniversalInsight.status.is_not(None)
    return UniversalInsight.status == status


class InsightEngine:
    """Canonical /brain/insights read surface (governance-scoped)."""

    async def list_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        limit: int = 50,
        status: Optional[str] = None,
        insight_type: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> dict[str, Any]:
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        filters = [
            UniversalInsight.organization_id == organization_id,
            _status_filter(status),
        ]
        if insight_type:
            filters.append(UniversalInsight.insight_type == insight_type)
        if severity:
            filters.append(UniversalInsight.severity == severity)
        rows = (
            await db.execute(
                select(UniversalInsight)
                .where(*filters)
                .order_by(
                    UniversalInsight.severity.desc(),
                    UniversalInsight.confidence.desc(),
                    UniversalInsight.last_observed_at.desc(),
                )
                .limit(min(limit, 200))
            )
        ).scalars().all()
        visible: list[dict[str, Any]] = []
        truncated = False
        for row in rows:
            if not _visible_to(access, row):
                continue
            visible.append(_present(row))
            if len(visible) >= limit:
                truncated = True
                break
        return {
            "insights": visible,
            "limit": limit,
            "truncated": truncated,
            "org_wide": access.org_wide,
        }

    async def get_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        insight_id: str,
    ) -> Optional[dict[str, Any]]:
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        row = await db.get(UniversalInsight, insight_id)
        if row is None or row.organization_id != organization_id:
            return None
        if not _visible_to(access, row):
            return None
        return _present(row)

    async def evidence_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        insight_id: str,
    ) -> Optional[dict[str, Any]]:
        """Why VCOS believes this insight — resolved evidence refs.

        Event refs resolve to the durable event rows (name + occurred_at);
        restricted items are dropped, never leaked. If the insight itself is
        not visible it returns None (indistinguishable from missing).
        """
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        row = await db.get(UniversalInsight, insight_id)
        if row is None or row.organization_id != organization_id:
            return None
        if not _visible_to(access, row):
            return None

        evidence = [item for item in (row.evidence_json or []) if item.get("type") != "event"]
        event_ids = [
            item["id"] for item in (row.evidence_json or []) if item.get("type") == "event"
        ]
        events = (
            (
                await db.execute(
                    select(insight_pipeline.EventRow).where(
                        insight_pipeline.EventRow.organization_id == organization_id,
                        insight_pipeline.EventRow.id.in_(event_ids[-40:]),
                    )
                )
            ).scalars().all()
            if event_ids
            else []
        )
        event_map = {e.id: e for e in events}
        for item in (row.evidence_json or []):
            if item.get("type") != "event":
                continue
            event = event_map.get(item["id"])
            if event is not None:
                evidence.append(
                    {
                        "type": "event",
                        "id": event.id,
                        "title": event.name,
                        "relationship": item.get("relationship", "supports"),
                        "occurred_at": _iso(event.occurred_at),
                    }
                )
        return {
            "insight_id": row.id,
            "insight_type": row.insight_type,
            "evidence": evidence[:40],
            "supporting_pattern_ids": (row.supporting_pattern_ids or [])[:20],
            "supporting_memory_ids": (row.supporting_memory_ids or [])[:20],
        }

    async def history_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        insight_id: str,
        limit: int = 50,
    ) -> Optional[dict[str, Any]]:
        """Recomposition timeline: every event that fed this insight."""
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        row = await db.get(UniversalInsight, insight_id)
        if row is None or row.organization_id != organization_id:
            return None
        if not _visible_to(access, row):
            return None
        links = (
            await db.execute(
                select(InsightEvent)
                .where(
                    InsightEvent.organization_id == organization_id,
                    InsightEvent.insight_id == row.id,
                )
                .order_by(InsightEvent.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        event_ids = [link.event_id for link in links]
        events = (
            (
                await db.execute(
                    select(insight_pipeline.EventRow).where(
                        insight_pipeline.EventRow.organization_id == organization_id,
                        insight_pipeline.EventRow.id.in_(event_ids),
                    )
                )
            ).scalars().all()
            if event_ids
            else []
        )
        event_map = {e.id: e for e in events}
        history = []
        for link in links:
            event = event_map.get(link.event_id)
            history.append(
                {
                    "event_id": link.event_id,
                    "event_name": event.name if event is not None else "unknown",
                    "relationship": link.relationship,
                    "occurred_at": _iso(event.occurred_at) if event is not None else _iso(link.created_at),
                }
            )
        return {
            "insight_id": row.id,
            "history": history[:limit],
            "first_observed_at": _iso(row.first_observed_at),
            "last_observed_at": _iso(row.last_observed_at),
            "status": row.status,
        }

    async def related_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        insight_id: str,
        limit: int = 10,
    ) -> Optional[dict[str, Any]]:
        """Related insights: same project anchor or sharing evidence entities."""
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        row = await db.get(UniversalInsight, insight_id)
        if row is None or row.organization_id != organization_id:
            return None
        if not _visible_to(access, row):
            return None
        anchor_ids = {e.get("id") for e in (row.affected_entities or []) if e.get("id")}
        rows = (
            await db.execute(
                select(UniversalInsight).where(
                    UniversalInsight.organization_id == organization_id,
                    UniversalInsight.id != row.id,
                    UniversalInsight.status.in_(("active", "faded")),
                )
                .order_by(UniversalInsight.confidence.desc())
                .limit(100)
            )
        ).scalars().all()
        related: list[dict[str, Any]] = []
        for candidate in rows:
            if not _visible_to(access, candidate):
                continue
            candidate_ids = {
                e.get("id") for e in (candidate.affected_entities or []) if e.get("id")
            }
            shares_anchor = bool(anchor_ids & candidate_ids)
            if shares_anchor or candidate.scope_id == row.scope_id:
                presented = _present(candidate)
                presented["relation"] = "shares_anchor" if shares_anchor else "same_scope"
                related.append(presented)
                if len(related) >= limit:
                    break
        return {"insight_id": row.id, "related": related}


insight_engine = InsightEngine()
