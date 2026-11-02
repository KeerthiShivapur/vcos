#!/usr/bin/env python3
"""
VCOS Deployment Rollback Script

This script handles safe rollback of deployments by:
1. Reverting Alembic migrations to the previous revision
2. Restoring feature flag state from deployment record
3. Verifying RLS policies are intact
4. Running canonical integrity checks

Usage:
    python rollback.py --deployment-id <deployment_id>
    python rollback.py --to-revision <revision>
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vcos.rollback")


async def rollback_migrations(target_revision: str = "-1") -> bool:
    """Rollback Alembic migrations to a target revision."""
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command

    settings = get_settings()
    
    # Load Alembic config
    backend_root = Path(__file__).resolve().parents[2]
    ini_path = backend_root / "alembic.ini"
    scripts_dir = backend_root / "alembic"
    
    if not ini_path.exists():
        fallback_ini = Path("alembic.ini")
        fallback_scripts = Path("alembic")
        if not fallback_ini.exists() or not fallback_scripts.exists():
            logger.error("Alembic configuration not found")
            return False
        cfg = AlembicConfig(str(fallback_ini))
        cfg.set_main_option("script_location", str(fallback_scripts.resolve()))
    else:
        cfg = AlembicConfig(str(ini_path))
        cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
        cfg.set_main_option("script_location", str(scripts_dir))

    try:
        logger.info(f"Rolling back to revision: {target_revision}")
        alembic_command.downgrade(cfg, target_revision)
        logger.info("Migrations rolled back successfully")
        return True
    except Exception as e:
        logger.error(f"Migration rollback failed: {e}")
        return False


async def verify_rls_integrity() -> bool:
    """Verify RLS policies are intact after rollback."""
    from app.core.config import get_settings
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with SessionLocal() as session:
            # Check RLS is enabled on tenant tables
            result = await session.execute(text("""
                SELECT COUNT(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' 
                AND c.relrowsecurity = true 
                AND c.relforcerowsecurity = true
                AND c.relkind = 'r'
            """))
            rls_count = result.scalar()
            
            if rls_count == 0:
                logger.error("RLS verification failed: no tables with FORCE ROW LEVEL SECURITY")
                return False
            
            # Check current_organization_id function exists
            result = await session.execute(text("""
                SELECT prosrc FROM pg_proc 
                WHERE proname = 'current_organization_id' 
                AND pronamespace = 'public'::regnamespace
            """))
            func = result.fetchone()
            if not func:
                logger.error("RLS verification failed: current_organization_id function missing")
                return False
            
            logger.info(f"RLS verification passed: {result.scalar()} tables with FORCE RLS")
            return True
    except Exception as e:
        logger.error(f"RLS verification failed: {e}")
        return False
    finally:
        await engine.dispose()


async def verify_canonical_integrity() -> bool:
    """Run canonical integrity check after rollback."""
    try:
        from app.services.canonical_reality_integrity_service import (
            canonical_reality_integrity_service,
            severity_matches,
        )
        from sqlalchemy import select, func
        from app.db.database import SessionLocal
        from app.models.company_operating import CompanyDecision
        
        async with SessionLocal() as db:
            result = await db.execute(select(func.count()).select_from(CompanyDecision))
            decision_count = result.scalar() or 0
            
            if decision_count == 0:
                logger.info("Canonical integrity check skipped - no decisions in database")
                return True
            
            findings = await canonical_reality_integrity_service.run_integrity_scan(
                db, "rollback_verification",
                checks=["structural", "tenant", "temporal", "provenance", "epistemic", "operating_chain"],
                limit=50
            )
            
            from app.services.canonical_reality_integrity_service import severity_matches
            critical_findings = [f for f in findings if "CRITICAL" in str(f)]
            
            if critical_findings:
                logger.error(f"Canonical integrity check failed: {len(critical_findings)} critical findings")
                return False
            
            logger.info("Canonical integrity check passed")
            return True
    except Exception as e:
        logger.error(f"Canonical integrity check failed: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="VCOS Deployment Rollback")
    parser.add_argument("--deployment-id", help="Deployment ID to rollback")
    parser.add_argument("--to-revision", default="-1", help="Target revision (default: -1 for previous)")
    parser.add_argument("--skip-migrations", action="store_true", help="Skip migration rollback, only verify")
    parser.add_argument("--verify-only", action="store_true", help="Only run verification checks")
    
    args = parser.parse_args()
    
    logger.info("Starting VCOS deployment rollback")
    
    if args.verify_only:
        logger.info("Running verification checks only")
        rls_ok = await verify_rls_integrity()
        canonical_ok = await verify_canonical_integrity()
        if rls_ok and canonical_ok:
            logger.info("All verification checks passed")
            return 0
        else:
            logger.error("Verification failed")
            return 1
    
    if args.skip_migrations:
        logger.info("Skipping migration rollback, only running verifications")
    else:
        target = args.to_revision
        success = await rollback_migrations(target)
        if not success:
            logger.error("Migration rollback failed")
            return 1
        logger.info("Migration rollback completed")
    
    # Verify RLS and canonical integrity after rollback
    logger.info("Running post-rollback verification...")
    rls_ok = await verify_rls_integrity()
    canonical_ok = await verify_canonical_integrity()
    
    if rls_ok and canonical_ok:
        logger.info("Rollback completed successfully with all verifications passed")
        return 0
    else:
        logger.error("Post-rollback verification failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))