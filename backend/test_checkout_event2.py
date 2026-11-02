import asyncio
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

async def test():
    engine = create_async_engine(
        'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test',
        pool_size=1,
        max_overflow=0,
        echo=False,
        future=True,
    )
    
    # Add checkout event using set_config
    @event.listens_for(engine.sync_engine, 'checkout')
    def clear_context(dbapi_connection, connection_record, connection_proxy):
        print('CHECKOUT EVENT FIRED!')
        if hasattr(dbapi_connection, 'execute'):
            try:
                dbapi_connection.execute("SELECT set_config('app.current_organization_id', '', false)")
                print('Context cleared via set_config!')
            except Exception as e:
                print(f'Error clearing: {e}')
    
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    org_a_id = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    
    print('1. Request for Tenant A')
    async with SessionLocal() as session:
        await session.execute(text("SET ROLE vcos"))
        await session.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {'org_id': org_a_id})
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f'   After setting context: {val}')
        await session.commit()
    
    print('2. Request for Tenant B (new session)')
    async with SessionLocal() as session:
        await session.execute(text("SET ROLE vcos"))
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f'   Before setting context: {val}')
        await session.commit()
    
    await engine.dispose()

asyncio.run(test())