"""Backup worker (Phase 15) — enterprise configuration snapshot.

Takes a lightweight snapshot of the enterprise configuration surface
(providers, policies, integrations, feature flags, license) into an
observability log line so administrators can verify restore points and
retention behavior. Returns the number of organizations backed up.

Run standalone: python -m app.workers.backup_worker
"""

import asyncio
import logging

from sqlalchemy import column, func, select, table as sa_table

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.enterprise import ObservabilityLog
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.backup")

_SNAPSHOT_TABLES = (
    "identity_providers",
    "integration_connections",
    "feature_flags",
    "organization_licenses",
)


async def _run_backup(db) -> int:
    organizations = (await db.execute(select(Organization))).scalars().all()
    backed_up = 0
    for org in organizations:
        counts: dict[str, int] = {}
        for table_name in _SNAPSHOT_TABLES:
            row = await db.execute(
                select(func.count()).select_from(sa_table(table_name)).where(
                    column("organization_id") == org.id
                )
            )
            counts[table_name] = int(row.scalar_one())
        db.add(
            ObservabilityLog(
                organization_id=org.id,
                level="info",
                source="backup",
                message=f"Configuration snapshot for {org.name}",
                details={"counts": counts, "backup_at": utcnow().isoformat()},
                recorded_at=utcnow(),
            )
        )
        backed_up += 1
    return backed_up


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            backed_up = await _run_backup(session)
            await session.commit()
            return backed_up
    backed_up = await _run_backup(db)
    await db.commit()
    return backed_up


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("backup worker snapshotted %s organizations", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("backup worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
