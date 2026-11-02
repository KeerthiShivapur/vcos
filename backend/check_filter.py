import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', poolclass=None)
    async with engine.begin() as conn:
        result = await conn.execute(text('SELECT COUNT(*) FROM decisions WHERE organization_id = \'test-org\''))
        print(f'decisions for test-org: {result.scalar()}')
        
        result = await conn.execute(text('SELECT COUNT(*) FROM decisions'))
        print(f'decisions total: {result.scalar()}')
        
        result = await conn.execute(text('SELECT COUNT(*) FROM messages WHERE organization_id = \'test-org\''))
        print(f'messages for test-org: {result.scalar()}')
        
        result = await conn.execute(text('SELECT COUNT(*) FROM messages'))
        print(f'messages total: {result.scalar()}')
    await engine.dispose()

asyncio.run(check())