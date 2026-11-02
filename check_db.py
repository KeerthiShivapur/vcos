import asyncio
from app.db.database import init_db, SessionLocal
from app.models.company_experience import CompanyExperienceConfig, CompanyExperienceProfileHistory, CompanyExperienceProfile
from sqlalchemy import text, inspect

async def check():
    await init_db()
    async with SessionLocal() as db:
        # Check if tables exist
        result = await db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'company_experience%'"))
        tables = result.fetchall()
        print('Tables:', tables, flush=True)
        
        # Check if any configs exist
        result = await db.execute(text('SELECT count(*) FROM company_experience_configs'))
        count = result.scalar()
        print('Config count:', count, flush=True)
        
        result = await db.execute(text('SELECT count(*) FROM company_experience_profile_history'))
        count2 = result.scalar()
        print('History count:', count2, flush=True)
        
        # Test ORM query
        from app.models.organization import Organization
        result = await db.execute(text('SELECT id, name FROM organizations LIMIT 1'))
        org = result.first()
        if org:
            print(f'Org: {org}', flush=True)
            from app.services.company_experience_service import company_experience_service
            config = await company_experience_service.get_or_create_experience_config(db, org.id)
            print(f'Config created/fetched: {config.id}, profile: {config.experience_profile}', flush=True)

asyncio.run(check())