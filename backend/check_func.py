from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def test():
    async with SessionLocal() as db:
        await db.execute(text("SELECT set_config('app.current_organization_id', '12345678-1234-1234-1234-123456789012', false)"))
        result = await db.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f'Function returns: {val} (type: {type(val).__name__})')
        print(f'As text: {str(val)}')
        print(f'Hex without hyphens: {val.hex if val else None}')

asyncio.run(test())