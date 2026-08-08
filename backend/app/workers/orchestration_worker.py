"""Orchestration worker — runs the full evolution cycle for every org.

The continuous evolution cycle: observe -> rebuild graph -> refresh health ->
generate intelligence -> record timeline/memory -> emit events.

Run standalone: python -m app.workers.orchestration_worker
"""

import asyncio
import logging

from app.db.database import SessionLocal
from app.kernel.orchestration_engine import orchestration_engine

logger = logging.getLogger("vcos.workers.orchestration")


async def run_once() -> int:
    async with SessionLocal() as db:
        result = await orchestration_engine.run_all(db)
        await db.commit()
        logger.info("orchestration worker: %s orgs evolved", result["organizations"])
        return result["organizations"]


async def run_forever(interval_seconds: int = 21600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("orchestration worker evolved %s organizations", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("orchestration worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
