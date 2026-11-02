"""Test to verify tenant context doesn't leak across connection reuse."""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text


async def test_context_leak():
    """Test that tenant context doesn't leak across sessions using same connection pool."""
    
    engine = create_async_engine(
        'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test',
        pool_size=1,
        max_overflow=0,
        echo=False,
        future=True,
    )
    
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    org_a_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    org_b_id = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    
    print("=== Test: Connection Reuse Context Leak ===")
    
    # Request 1: Tenant A
    print("\n1. Request for Tenant A")
    async with SessionLocal() as session:
        await session.execute(text("SET ROLE vcos"))
        await session.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a_id})
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f"   After setting context: {val}")
        await session.commit()
    
    # Request 2: Tenant B (should NOT see Tenant A's context)
    print("\n2. Request for Tenant B (new session from pool)")
    async with SessionLocal() as session:
        await session.execute(text("SET ROLE vcos"))
        # Don't set context - should be empty if no leak
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f"   Before setting context: {val}")
        
        if val == org_a_id:
            print("   [LEAK] Tenant A's context leaked to Tenant B's session!")
        elif val is None or val == '':
            print("   [OK] No leak: Context properly reset")
        else:
            print(f"   ? Unexpected value: {val}")
        
        # Now set Tenant B's context
        await session.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b_id})
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f"   After setting Tenant B context: {val}")
        await session.commit()
    
    # Request 3: Tenant A again (should NOT see Tenant B's context)
    print("\n3. Request for Tenant A again (new session from pool)")
    async with SessionLocal() as session:
        await session.execute(text("SET ROLE vcos"))
        # Don't set context - should be empty if no leak
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f"   Before setting context: {val}")
        
        if val == org_b_id:
            print("   [LEAK] Tenant B's context leaked to Tenant A's session!")
        elif val is None or val == '':
            print("   [OK] No leak: Context properly reset")
        else:
            print(f"   ? Unexpected value: {val}")
        
        await session.commit()
    
    await engine.dispose()
    print("\n=== Test Complete ===")


async def test_context_clearing():
    """Test explicit context clearing."""
    
    engine = create_async_engine(
        'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test',
        pool_size=1,
        max_overflow=0,
        echo=False,
        future=True,
    )
    
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    org_a_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    org_b_id = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    
    print("\n=== Test: Explicit Context Clearing ===")
    
    # Request 1: Tenant A with explicit clearing
    print("\n1. Request for Tenant A with explicit clearing")
    async with SessionLocal() as session:
        await session.execute(text("SET ROLE vcos"))
        await session.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a_id})
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f"   After setting context: {val}")
        
        # Explicitly clear
        await session.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        await session.commit()
        print("   Explicitly cleared context")
    
    # Request 2: Tenant B
    print("\n2. Request for Tenant B (after explicit clear)")
    async with SessionLocal() as session:
        await session.execute(text("SET ROLE vcos"))
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f"   Before setting context: {val}")
        
        if val == org_a_id:
            print("   [LEAK] LEAK DETECTED even after explicit clear!")
        elif val is None or val == '':
            print("   [OK] No leak: Explicit clear worked")
        else:
            print(f"   ? Unexpected value: {val}")
        
        await session.commit()
    
    await engine.dispose()
    print("\n=== Test Complete ===")


async def main():
    await test_context_leak()
    await test_context_clearing()


if __name__ == "__main__":
    asyncio.run(main())