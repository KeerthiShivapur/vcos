"""Dependency worker — keeps the task board truthful.

Finds tasks whose uncompleted dependencies block them and transitions them to
`blocked`, then unblocks tasks whose dependencies have all been completed.

Run standalone: python -m app.workers.dependency_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.organization import Organization
from app.models.task import Task
from app.work.dependency_service import dependency_service

logger = logging.getLogger("vcos.workers.dependency")


async def run_once() -> int:
    processed = 0
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(
                select(Organization.id).where(Organization.status == "active")
            )
        ).scalars().all()
        for org_id in org_ids:
            try:
                tasks = (
                    await db.execute(
                        select(Task).where(
                            Task.organization_id == org_id,
                            Task.status.in_(("todo", "in_progress", "review", "backlog")),
                        )
                    )
                ).scalars().all()
                for task in tasks:
                    blockers = await dependency_service.blockers_for(
                        db, organization_id=org_id, task_id=task.id
                    )
                    if blockers and task.status != "blocked":
                        task.status = "blocked"
                        processed += 1
                    elif not blockers and task.status == "blocked":
                        task.status = "todo"
                        processed += 1
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("dependency worker skipped org %s: %s", org_id, exc)
        await db.commit()
        return processed


async def run_forever(interval_seconds: int = 300) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("dependency worker adjusted %s tasks", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("dependency worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
