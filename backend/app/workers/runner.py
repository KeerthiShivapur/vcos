"""Standalone background worker runner (go-live entrypoint).

The default deployment runs workers inside the API process (scheduler).
This module ships the split topology already referenced by the shipped
docker-compose (`python -m app.workers.runner`): the same scheduler loop,
same worker registry, no duplicated worker code.

Behavior:
  - development: bootstraps the schema (init_db) then runs the scheduler
  - production: assumes the schema is managed by Alembic and only runs the
    scheduler (no create_all against a production database)

Run:  python -m app.workers.runner
"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import get_settings
from app.workers.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger("vcos.workers.runner")


async def run_forever(stop_event: "asyncio.Event | None" = None) -> None:
    """Start every registered worker and block until asked to stop."""
    if stop_event is None:
        stop_event = asyncio.Event()
    tasks = start_scheduler()
    logger.info("worker runner started (%d workers)", len(tasks))
    try:
        await stop_event.wait()
    finally:
        stop_scheduler(tasks)
        logger.info("worker runner stopped")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()
    if settings.APP_ENV == "production":
        logger.info("production mode: schema is managed by Alembic; skipping bootstrap")
    else:
        from app.db.database import init_db

        await init_db()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)  # not available on Windows
        except (NotImplementedError, RuntimeError):
            pass
    try:
        await run_forever(stop)
    except KeyboardInterrupt:  # Windows consoles deliver Ctrl+C here
        logger.info("worker runner interrupted")


if __name__ == "__main__":
    asyncio.run(main())
