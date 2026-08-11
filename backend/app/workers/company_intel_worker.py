"""Slice 4D.1 — company intelligence worker.

Change-driven by the durable event bus: operating events
(messaging.*, governance.*) trigger a bounded refresh of the affected entity
via ``refresh_entity`` from the event handlers. This worker owns the
idempotent, retry-safe ``CompanyInsight`` upsert for one entity and exposes a
bounded scheduled sweep (``run_once``) that re-freshes insights for the most
recently changed graph entities, so the freshness signal stays current even if
a handler is unavailable.

The brain never depends on this table for authorization or retrieval: it reads
live, governance-scoped evidence from the underlying tables. This table only
marts "what changed, why, and when" so consumers can show staleness/recency.

Run standalone: python -m app.workers.company_intel_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.intelligence import CompanyInsight, OrgGraphEdge

logger = logging.getLogger("vcos.workers.company_intel")

# Bounded sweep ceilings (law: never O(N) full-org scans from here).
MAX_SWEEP_ITEMS = 200
MAX_DETAIL_CHARS = 240


async def _scope_for_entity(
    db, *, organization_id: str, entity_type: str, entity_id: str,
) -> str | None:
    """Resolve the governance scope anchoring this entity (bounded, indexed).

    project-type scopes carry the project id in ``entity_id``; work entities
    derive their scope from their project.
    """
    from app.models.governance import GovernanceScope

    project_id: str | None = None
    if entity_type in ("project", "scope"):
        project_id = entity_id
    elif entity_type in ("task", "decision", "goal", "budget"):
        model_map = {
            "task": "Task", "decision": "Decision",
            "goal": "Goal", "budget": "Budget",
        }
        module = {
            "task": "app.models.task", "decision": "app.models.knowledge",
            "goal": "app.models.goal", "budget": "app.models.finance",
        }[entity_type]
        model = getattr(__import__(module, fromlist=[model_map[entity_type]]), model_map[entity_type])
        row = await db.get(model, entity_id)
        if row is not None and row.organization_id == organization_id:
            project_id = getattr(row, "project_id", None)
    if not project_id:
        return None
    scope = (
        await db.execute(
            select(GovernanceScope.id).where(
                GovernanceScope.organization_id == organization_id,
                GovernanceScope.scope_type == "project",
                GovernanceScope.entity_id == project_id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    return scope


async def _entity_context(
    db, *, organization_id: str, entity_type: str, entity_id: str,
) -> tuple[str | None, str | None, str | None, dict]:
    """Return (title, status, scope_id, detail) for an entity; None if unknown.

    Every lookup is a primary-key get or an indexed org-scoped select.
    """
    if entity_type == "project":
        from app.models.project import Project

        row = await db.get(Project, entity_id)
        if row is None or row.organization_id != organization_id:
            return (None, None, None, {})
        return (
            row.title, row.status,
            await _scope_for_entity(db, organization_id=organization_id,
                                    entity_type="project", entity_id=entity_id),
            {"title": row.title, "status": row.status},
        )
    if entity_type == "task":
        from app.models.task import Task

        row = await db.get(Task, entity_id)
        if row is None or row.organization_id != organization_id:
            return (None, None, None, {})
        return (
            row.title, row.status,
            await _scope_for_entity(db, organization_id=organization_id,
                                    entity_type="task", entity_id=entity_id),
            {"title": row.title, "status": row.status, "project_id": row.project_id},
        )
    if entity_type == "decision":
        from app.models.knowledge import Decision

        row = await db.get(Decision, entity_id)
        if row is None or row.organization_id != organization_id:
            return (None, None, None, {})
        return (
            row.title, row.status,
            await _scope_for_entity(db, organization_id=organization_id,
                                    entity_type="decision", entity_id=entity_id),
            {"title": row.title, "status": row.status, "project_id": row.project_id},
        )
    if entity_type == "conversation":
        from app.models.communication import Conversation

        row = await db.get(Conversation, entity_id)
        if row is None or row.organization_id != organization_id:
            return (None, None, None, {})
        title = row.title or (row.name if getattr(row, "name", None) else "Conversation")
        return (
            title, "active" if not row.is_archived else "archived", None,
            {"title": title, "type": row.type, "message_count": row.message_count},
        )
    if entity_type == "message":
        from app.models.communication import Message

        row = await db.get(Message, entity_id)
        if row is None or row.organization_id != organization_id:
            return (None, None, None, {})
        content = (row.content or "") if not row.deleted else ""
        return (
            (content[:MAX_DETAIL_CHARS]) or "Message",
            "deleted" if row.deleted else "active", None,
            {"content": content[:MAX_DETAIL_CHARS], "conversation_id": row.conversation_id},
        )
    if entity_type == "scope":
        from app.models.governance import GovernanceScope

        row = await db.get(GovernanceScope, entity_id)
        if row is None or row.organization_id != organization_id:
            return (None, None, None, {})
        return (
            row.name, row.scope_type, row.id,
            {"name": row.name, "scope_type": row.scope_type, "entity_id": row.entity_id},
        )
    if entity_type == "goal":
        from app.models.goal import Goal

        row = await db.get(Goal, entity_id)
        if row is None or row.organization_id != organization_id:
            return (None, None, None, {})
        return (
            row.name, row.status,
            await _scope_for_entity(db, organization_id=organization_id,
                                    entity_type="goal", entity_id=entity_id),
            {"title": row.name, "status": row.status, "project_id": row.project_id},
        )
    if entity_type == "budget":
        from app.models.finance import Budget

        row = await db.get(Budget, entity_id)
        if row is None or row.organization_id != organization_id:
            return (None, None, None, {})
        return (
            row.name, row.status,
            await _scope_for_entity(db, organization_id=organization_id,
                                    entity_type="budget", entity_id=entity_id),
            {"title": row.name, "status": row.status, "project_id": row.project_id},
        )
    if entity_type == "employee":
        from app.models.employee import Employee

        row = await db.get(Employee, entity_id)
        if row is None or row.organization_id != organization_id:
            return (None, None, None, {})
        name = row.display_name or " ".join(
            p for p in (row.first_name, row.last_name) if p
        ) or "Employee"
        return (name, "active", None, {"name": name})
    return (None, None, None, {})


async def refresh_entity(
    db, *, organization_id: str, entity_type: str, entity_id: str,
    reason: str | None = None, actor: str | None = None,
) -> bool:
    """Idempotent, bounded CompanyInsight upsert for one affected entity.

    Never commits; safe to call from event handlers (caller owns the
    transaction) and safe to retry (unique key upsert semantics).
    """
    if not entity_id:
        return False
    title, status, scope_id, detail = await _entity_context(
        db, organization_id=organization_id, entity_type=entity_type, entity_id=entity_id
    )
    if title is None:
        return False
    existing = (
        await db.execute(
            select(CompanyInsight).where(
                CompanyInsight.organization_id == organization_id,
                CompanyInsight.entity_type == entity_type,
                CompanyInsight.entity_id == entity_id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = CompanyInsight(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        db.add(existing)
    existing.kind = "context"
    existing.title = title
    existing.status = status
    existing.scope_id = scope_id
    existing.reason = reason
    existing.detail = detail
    existing.touched_by = actor
    return True


async def run_once(max_items: int = MAX_SWEEP_ITEMS) -> int:
    """Bounded sweep: refresh insights for the most recently changed entities.

    Uses the indexed graph-edge recency (overall, not a per-org scan) so the
    work is proportional to recent change volume, not organization count.
    """
    processed = 0
    async with SessionLocal() as db:
        recent = (
            await db.execute(
                select(
                    OrgGraphEdge.organization_id,
                    OrgGraphEdge.source_type,
                    OrgGraphEdge.source_id,
                )
                .order_by(OrgGraphEdge.updated_at.desc())
                .limit(max_items)
            )
        ).all()
        seen: set[tuple[str, str, str]] = set()
        for org_id, source_type, source_id in recent:
            if source_type not in (
                "project", "task", "decision", "conversation", "message",
                "scope", "goal", "budget", "employee",
            ):
                continue
            key = (org_id, source_type, source_id)
            if key in seen:
                continue
            seen.add(key)
            try:
                if await refresh_entity(
                    db, organization_id=org_id,
                    entity_type=source_type, entity_id=source_id,
                    reason="scheduled_recent_refresh",
                ):
                    processed += 1
            except Exception:  # noqa: BLE001 - per-row isolation
                logger.exception("company-intel sweep row failed: %s", key)
        await db.commit()
    if processed:
        logger.info("company-intel sweep refreshed %s entities", processed)
    return processed


async def run_forever(interval_seconds: int = 900) -> None:
    while True:
        try:
            await run_once()
        except Exception as exc:  # pragma: no cover
            logger.exception("company-intel sweep error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
