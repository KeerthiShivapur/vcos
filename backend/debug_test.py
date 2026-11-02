import asyncio
import os
os.environ['VCOS_TEST_MODE'] = '0'

async def main():
    import uuid
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.db.database import Base
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    
    engine = create_async_engine('postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test', poolclass=None)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_factory() as session:
        # Create tables
        await session.execute(text("SET search_path TO public"))
        
        # Provision company
        from tests.acceptance.test_integration_adversarial import _provision_company, _create_connector_instance
        import uuid
        
        org_id, admin_user, admin_emp, access = await _provision_company(session, f'forged-webhook-{uuid.uuid4().hex[:8]}')
        
        instance = await _create_connector_instance(session, org_id, 'github')
        instance.webhook_secret = 'test_secret'
        await session.flush()
        
        payload = {'action': 'opened', 'repository': {'id': 123, 'name': 'test/repo'}}
        headers = {
            'x-hub-signature-256': 'sha256=invalid_signature',
            'x-github-delivery': f'delivery-{uuid.uuid4().hex[:8]}',
            'x-vcos-force-auth': 'true',
        }
        
        from app.services.webhook_ingestion_service import webhook_ingestion_service
        try:
            await webhook_ingestion_service.ingest_webhook(
                db=session,
                organization_id=org_id,
                connector_instance_id=instance.id,
                payload=payload,
                headers=headers,
            )
            print('ERROR: Should have raised ValueError')
        except ValueError as e:
            if 'Webhook authentication failed' in str(e):
                print('SUCCESS: Webhook authentication failed as expected')
            else:
                print(f'UNEXPECTED ERROR: {e}')
        
        await engine.dispose()

asyncio.run(main())