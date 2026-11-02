import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.models.organization import Organization

async def test():
    engine = create_async_engine('postgresql+asyncpg://postgres:keerthi@localhost:5432/vcos_gate7_fresh')
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        # Check key tables exist
        tables = ['organizations', 'users', 'roles', 'company_intents', 'company_goals', 
                  'company_objectives', 'company_initiatives', 'company_decisions',
                  'company_authorizations', 'company_commitments', 'company_actions',
                  'organizational_responsibilities', 'company_planning_contexts',
                  'attention_signals', 'verification_contexts']
        for table in tables:
            result = await session.execute(text(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{table}'"))
            exists = result.scalar() == 1
            print(f'{table}: {"EXISTS" if exists else "MISSING"}')
        
        # Try to create an organization
        org = Organization(id='test-fresh', name='Fresh Test', slug='fresh-test', status='active')
        session.add(org)
        await session.commit()
        print('Organization created successfully!')
        
    await engine.dispose()

asyncio.run(test())