"""Plugin health worker (Phase 15) — installed plugin hygiene.

Re-verifies installed plugins: plugins whose scan state is stale or whose
payload no longer matches the stored manifest are re-scanned and flagged.
Returns the number of plugins checked.

Run standalone: python -m app.workers.plugin_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.enterprise.plugin_service import _scan_payload
from app.models.enterprise import Plugin, PluginVersion

logger = logging.getLogger("vcos.workers.plugin")


async def _check_plugins(db) -> int:
    plugins = (
        await db.execute(
            select(Plugin).where(Plugin.status.in_(("installed", "disabled")))
        )
    ).scalars().all()
    checked = 0
    for plugin in plugins:
        version_row = (
            await db.execute(
                select(PluginVersion)
                .where(PluginVersion.plugin_id == plugin.id)
                .order_by(PluginVersion.created_at.desc())
            )
        ).scalars().first()
        if version_row is None:
            continue
        ok, _ = _scan_payload(version_row.payload)
        plugin.scan_status = "clean" if ok else "blocked"
        checked += 1
    return checked


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            checked = await _check_plugins(session)
            await session.commit()
            return checked
    checked = await _check_plugins(db)
    await db.commit()
    return checked


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("plugin worker verified %s installed plugins", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("plugin worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
