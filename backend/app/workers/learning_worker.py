"""Learning worker — distills lessons from project outcomes into memory.

Mines completed projects for measurable outcomes and stores lessons the org
can reuse. Event handlers already record inline lessons; this worker adds the
project-level retrospective layer.

Run standalone: python -m app.workers.learning_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.intelligence.learning_engine import learning_engine
from app.models.organization import Organization
from app.models.project import Project

logger = logging.getLogger("vcos.workers.learning")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            projects = (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == org_id,
                        Project.status == "completed",
                    )
                )
            ).scalars().all()
            for project in projects:
                existing = await learning_engine.lessons(
                    db, organization_id=org_id, event_type="project_completed"
                )
                if any(e["entity_id"] == project.id for e in existing):
                    continue
                await learning_engine.record(
                    db, organization_id=org_id,
                    event_type="project_completed",
                    title=f"Project completed: {project.name}",
                    detail="Retrospective insight captured automatically after project completion.",
                    lesson="Review completed projects for reusable practices before starting similar work.",
                    entity_type="project", entity_id=project.id,
                    tags=["project", "retrospective"],
                    memory=True,
                )
                total += 1
            await db.flush()
        await db.commit()
    return total


async def run_forever(interval_seconds: int = 43200) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("learning worker recorded %s lessons", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("learning worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
