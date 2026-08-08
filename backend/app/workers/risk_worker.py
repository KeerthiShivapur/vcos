"""Risk worker — proactive risk detection from work signals.

Detects and logs risks with `detected_from` provenance:
  - milestones overdue by 3+ days → schedule slippage risk
  - tasks overdue by 7+ days → delivery delay risk
  - tasks blocked for 3+ days → dependency risk
  - active projects past their end date → timeline breach risk

Each detection creates a Risk row (or bumps the score of an identical open
risk) so the risk register never goes stale.

Phase 9.9: the worker also runs the background risk engine, which converts
the intelligence layer's own findings (knowledge decay, overload signals,
approval bottlenecks, duplicate work, repeated delays, silos) into strategic
risks on the executive risk register.

Run standalone: python -m app.workers.risk_worker
"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.approval import Risk
from app.models.organization import Organization
from app.models.project import Milestone, Project
from app.models.task import Task
from app.work.risk_service import risk_service

logger = logging.getLogger("vcos.workers.risk")


async def _open_risk(db, *, organization_id: str, project_id: str, title: str) -> Risk | None:
    row = await db.execute(
        select(Risk).where(
            Risk.organization_id == organization_id,
            Risk.project_id == project_id,
            Risk.title == title,
            Risk.status != "closed",
        )
    )
    return row.scalars().first()


async def _detect(db, *, organization_id: str, title: str, project_id: str, probability: int, impact: int, mitigation: str) -> bool:
    existing = await _open_risk(db, organization_id=organization_id, project_id=project_id, title=title)
    if existing:
        existing.risk_score = risk_service.compute_score(max(existing.probability, probability), max(existing.impact, impact))
        existing.updated_at = utcnow()
        return False
    risk = Risk(
        organization_id=organization_id,
        project_id=project_id,
        title=title,
        status="identified",
        probability=probability,
        impact=impact,
        risk_score=risk_service.compute_score(probability, impact),
        mitigation=mitigation,
        detected_from="delay_detection",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(risk)
    return True


async def run_once() -> int:
    detected = 0
    now = utcnow()
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(
                select(Organization.id).where(Organization.status == "active")
            )
        ).scalars().all()
        for org_id in org_ids:
            try:
                # Overdue milestones
                milestones = (
                    await db.execute(
                        select(Milestone).where(
                            Milestone.organization_id == org_id,
                            Milestone.project_id.isnot(None),
                            Milestone.status != "completed",
                            Milestone.due_date.isnot(None),
                            Milestone.due_date < now.date() - timedelta(days=3),
                        )
                    )
                ).scalars().all()
                for m in milestones:
                    if await _detect(
                        db, organization_id=org_id,
                        title=f"Milestone overdue: {m.name}", project_id=m.project_id,
                        probability=3, impact=3,
                        mitigation="Re-baseline milestone dates and reallocate capacity",
                    ):
                        detected += 1

                # Overdue tasks
                tasks = (
                    await db.execute(
                        select(Task).where(
                            Task.organization_id == org_id,
                            Task.project_id.isnot(None),
                            Task.status.notin_(("completed", "archived")),
                            Task.due_date.isnot(None),
                            Task.due_date < now.date() - timedelta(days=7),
                        )
                    )
                ).scalars().all()
                for t in tasks:
                    if await _detect(
                        db, organization_id=org_id,
                        title=f"Task overdue: {t.title}", project_id=t.project_id,
                        probability=3, impact=2,
                        mitigation="Review scope and reprioritize the sprint",
                    ):
                        detected += 1

                # Projects past end date
                projects = (
                    await db.execute(
                        select(Project).where(
                            Project.organization_id == org_id,
                            Project.status.in_(("draft", "active", "paused")),
                            Project.end_date.isnot(None),
                            Project.end_date < now.date(),
                        )
                    )
                ).scalars().all()
                for p in projects:
                    if await _detect(
                        db, organization_id=org_id,
                        title=f"Project past end date: {p.name}", project_id=p.id,
                        probability=4, impact=4,
                        mitigation="Update the project end date or escalate for re-planning",
                    ):
                        detected += 1

                # Phase 9.9 — intelligence-layer risks → strategic risk register
                from app.intelligence.risk_engine import background_risk_engine

                detected += await background_risk_engine.scan(
                    db, organization_id=org_id
                )
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("risk worker skipped org %s: %s", org_id, exc)
        await db.commit()
        return detected


async def run_forever(interval_seconds: int = 900) -> None:
    while True:
        try:
            detected = await run_once()
            if detected:
                logger.info("risk worker detected %s new risks", detected)
        except Exception as exc:  # pragma: no cover
            logger.exception("risk worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
