"""Database bootstrap: creates the schema and the global permission catalog.

Run: python -m app.seed
"""

import asyncio

from app.db.database import SessionLocal, init_db
from app.services.permission_service import permission_service


async def main() -> None:
    await init_db()
    async with SessionLocal() as db:
        await permission_service.sync_catalog(db)
        await db.commit()
        count = len(await permission_service.catalog(db))
    print(f"VCOS database ready. {count} permissions in catalog.")
    print("Note: organizations are created through the registration API.")


if __name__ == "__main__":
    asyncio.run(main())
