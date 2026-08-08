"""Company memory worker (Phase 19) — keeps organizational history permanent.

Every pass, for every active organization:
  - records a daily company-history memory entry summarizing recent timeline
    activity (company.history event),
  - auto-captures decisions that were analyzed as permanent memory,
  - rebuilds context bundles for the organization's active projects and
    upcoming meetings so context flows automatically.

Everything is idempotent: history digests are stored once per organization per
day, and context bundles are rebuilt in place.

Run standalone: python -m app.workers.memory_worker
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.events.publisher import publish_background_event
from app.memory.context_service import context_service
from app.memory.memory_service import memory_service
from app.memory.timeline_service import timeline_service
from app.models.company_memory import CompanyMemory
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.memory")


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        org_ids = (
            await session.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            try:
                await _daily_history(session, org_id)
                await _capture_decisions(session, org_id)
                await _warm_context(session, org_id)
                await session.flush()
                count += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("memory worker skipped org %s: %s", org_id, exc)
        return count

    if owns_session:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def _daily_history(session: AsyncSession, organization_id: str) -> None:
    """Record one 'company history' memory per organization per day."""
    now = utcnow()
    date_label = now.strftime("%Y-%m-%d")
    existing = (
        await session.execute(
            select(CompanyMemory.id).where(
                CompanyMemory.organization_id == organization_id,
                CompanyMemory.source_event == "company.history",
                CompanyMemory.title.ilike(f"%{date_label}%"),
            )
        )
    ).scalars().first()
    if existing is not None:
        return
    entries = await timeline_service.list(session, organization_id, limit=25)
    if not entries:
        return
    by_category: dict[str, int] = {}
    for entry in entries:
        by_category[entry["category"]] = by_category.get(entry["category"], 0) + 1
    headline = ", ".join(f"{n} {c}" for c, n in list(by_category.items())[:6])
    body = "Company history for {date}: {headline}. Recent events:\n".format(
        date=date_label, headline=headline
    )
    body += "\n".join(f"- [{e['category']}] {e['title']}" for e in entries[:15])
    await memory_service.record(
        session,
        organization_id=organization_id,
        memory_type="institutional",
        title=f"Company history — {date_label}",
        content=body,
        tags=["history", "company"],
        importance="medium",
        source_event="company.history",
        occurred_at=now,
    )
    await publish_background_event(
        session,
        name="company.history",
        organization_id=organization_id,
        payload={"date": date_label, "entries": len(entries)},
    )


async def _capture_decisions(session: AsyncSession, organization_id: str) -> None:
    """Auto-capture analyzed decisions that are not yet in company memory."""
    from app.digital_twin.decision_service import decision_service

    decisions = await decision_service.list(session, organization_id, limit=50)
    for decision in decisions:
        if decision.get("status") not in ("resolved", "implemented"):
            continue
        remembered = (
            await session.execute(
                select(CompanyMemory.id).where(
                    CompanyMemory.organization_id == organization_id,
                    CompanyMemory.entity_type == "decision",
                    CompanyMemory.entity_id == decision["id"],
                )
            )
        ).scalars().first()
        if remembered is not None:
            continue
        await memory_service.capture_from_decision(
            session,
            organization_id=organization_id,
            decision=decision,
            lessons=decision.get("lessons") or [],
        )


async def _warm_context(session: AsyncSession, organization_id: str) -> None:
    """Pre-build context bundles for active projects and recent meetings."""
    from app.models.meeting import Meeting
    from app.models.project import Project

    project_ids = (
        await session.execute(
            select(Project.id)
            .where(
                Project.organization_id == organization_id,
                Project.status.in_(["active", "in_progress", "on_track"]),
            )
            .limit(10)
        )
    ).scalars().all()
    for pid in project_ids:
        await context_service.get(session, organization_id, "project", pid)

    meeting_ids = (
        await session.execute(
            select(Meeting.id)
            .where(Meeting.organization_id == organization_id)
            .order_by(Meeting.start_at.desc())
            .limit(5)
        )
    ).scalars().all()
    for mid in meeting_ids:
        await context_service.get(session, organization_id, "meeting", mid)


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("memory worker processed %s organizations", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("memory worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
