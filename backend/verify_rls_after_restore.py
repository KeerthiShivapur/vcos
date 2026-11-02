#!/usr/bin/env python3
"""
RLS Backup/Restore/DR Integration Verification

This script extends the DR test to verify RLS policies are preserved
after backup and restore operations.
"""

import asyncio
import os
import sys
import tempfile
import subprocess
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


async def verify_rls_after_restore(source_db_url: str, restored_db_url: str) -> dict:
    """Verify RLS policies are preserved after restore."""
    
    results = {
        "source_db_verified": False,
        "restored_db_verified": False,
        "policies_match": False,
        "helper_functions_preserved": False,
        "role_security_preserved": False,
        "errors": []
    }
    
    async def verify_database(db_url: str, label: str) -> dict:
        """Verify RLS on a single database."""
        db_results = {
            "rls_tables": 0,
            "policies_count": 0,
            "helper_functions": False,
            "role_security": False,
            "errors": []
        }
        
        engine = create_async_engine(db_url, echo=False, future=True)
        try:
            async with engine.begin() as conn:
                # Check helper functions
                result = await conn.execute(text("""
                    SELECT proname FROM pg_proc 
                    WHERE proname IN ('current_organization_id', 'set_current_organization_id', 'clear_current_organization_id')
                    AND pronamespace = 'public'::regnamespace
                """))
                funcs = [row[0] for row in result.fetchall()]
                expected_funcs = {'current_organization_id', 'set_current_organization_id', 'clear_current_organization_id'}
                if set(funcs) == expected_funcs:
                    db_results["helper_functions"] = True
                else:
                    db_results["errors"].append(f"Missing helper functions: {expected_funcs - set(funcs)}")
                
                # Check RLS tables
                result = await conn.execute(text("""
                    SELECT COUNT(*) FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relrowsecurity = true
                    AND c.relforcerowsecurity = true
                    AND c.relkind = 'r'
                """))
                rls_count = result.scalar()
                db_results["rls_tables"] = rls_count
                
                # Check policies
                result = await conn.execute(text("""
                    SELECT COUNT(*) FROM pg_policies WHERE schemaname = 'public'
                """))
                policy_count = result.scalar()
                db_results["policies_count"] = policy_count
                
                # Check role security
                result = await conn.execute(text("""
                    SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'vcos'
                """))
                role = result.fetchone()
                if role and not role[0] and not role[1]:  # not super, not bypassrls
                    db_results["role_security"] = True
                else:
                    db_results["errors"].append("vcos role has excessive privileges")
            
        except Exception as e:
            db_results["errors"].append(f"Verification error: {e}")
        finally:
            await engine.dispose()
        
        return db_results
    
    print(f"Verifying source database...")
    source_results = await verify_database(source_db_url, "source")
    results["source_db_verified"] = len(source_results["errors"]) == 0
    results["errors"].extend(source_results["errors"])
    
    print(f"Verifying restored database...")
    restored_results = await verify_database(restored_db_url, "restored")
    results["restored_db_verified"] = len(restored_results["errors"]) == 0
    results["errors"].extend(restored_results["errors"])
    
    # Compare policies
    if source_results.get("policies_count") == restored_results.get("policies_count"):
        results["policies_match"] = True
    else:
        results["errors"].append(f"Policy count mismatch: source={source_results.get('policies_count')}, restored={restored_results.get('policies_count')}")
    
    results["helper_functions_preserved"] = source_results.get("helper_functions") and restored_results.get("helper_functions")
    results["role_security_preserved"] = source_results.get("role_security") and restored_results.get("role_security")
    
    return results


async def test_rls_restoration():
    """Test RLS restoration using pg_dump/pg_restore."""
    
    # This is a template for how to test RLS preservation during backup/restore
    # In practice, you would:
    # 1. Create a test database with RLS
    # 2. Run pg_dump
    # 3. Restore to a new database
    # 4. Run verify_database on both
    
    print("RLS Backup/Restore Integration Test")
    print("=" * 60)
    print("This is a template for DR integration testing.")
    print("To run a full test:")
    print("  1. Set SOURCE_DB_URL and RESTORED_DB_URL environment variables")
    print("  2. Run: python verify_rls_after_restore.py")
    print()
    
    source_url = os.environ.get("SOURCE_DB_URL")
    restored_url = os.environ.get("RESTORED_DB_URL")
    
    if not source_url or not restored_url:
        print("Skipping full test - set SOURCE_DB_URL and RESTORED_DB_URL to run")
        return True
    
    results = await verify_rls_after_restore(source_url, restored_url)
    
    print("Results:")
    for key, value in results.items():
        if key != "errors":
            print(f"  {key}: {value}")
    
    if results["errors"]:
        print("Errors:")
        for e in results["errors"]:
            print(f"  - {e}")
        return False
    
    print("All DR verification checks passed!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_rls_restoration())
    sys.exit(0 if success else 1)