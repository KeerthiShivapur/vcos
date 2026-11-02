import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

async def cleanup_database():
    engine = create_async_engine('postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test', poolclass=None)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        # Delete in reverse dependency order
        tables_to_clean = [
            "user_roles",
            "workspace_items",
            "workspaces",
            "invitations",
            "connector_instances",
            "company_timeline_events",
            "release_fingerprint_evidence",
            "release_recovery_records",
            "release_failure_injections",
            "release_records",
            "restore_operations",
            "backup_verification_results",
            "backup_manifests",
            "provisionings",
            "subscriptions",
            "commercial_accounts",
            "plans",
            "company_actions",
            "company_authorizations",
            "company_commitments",
            "company_decisions",
            "external_unknown_states",
            "worker_leases",
            "operation_checkpoints",
            "recoveries",
            "reconciliations",
            "canonical_operations",
            "operation_attempts",
            "employees",
            "users",
            "teams",
            "departments",
            "roles",
            "organizations",
        ]
        
        for table in tables_to_clean:
            try:
                await session.execute(text(f"DELETE FROM {table}"))
                print(f"Cleaned {table}")
            except Exception as e:
                print(f"Error cleaning {table}: {e}")
        
        await session.commit()
    
    await engine.dispose()
    print("Database cleanup complete")

asyncio.run(cleanup_database())