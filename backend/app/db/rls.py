from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import engine

async def set_tenant_context(session: AsyncSession, tenant_id: str):
    """Set the tenant context for RLS policies."""
    # Skip for SQLite as it doesn't support SET command
    if engine.dialect.name != "sqlite":
        await session.execute(text(f"SET app.current_tenant = '{tenant_id}'"))

@asynccontextmanager
async def tenant_context(session: AsyncSession, tenant_id: str):
    """Context manager for setting tenant context."""
    await set_tenant_context(session, tenant_id)
    try:
        yield
    finally:
        if engine.dialect.name != "sqlite":
            await session.execute(text("RESET app.current_tenant"))