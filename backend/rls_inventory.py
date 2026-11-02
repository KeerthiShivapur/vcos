#!/usr/bin/env python3
"""
RLS Inventory Tool - Discovers and classifies all tenant-scoped PostgreSQL tables.

This tool:
1. Connects to the database and inspects the actual schema
2. Cross-references with SQLAlchemy model metadata
3. Classifies tables as: direct, indirect, global, or unclassified
4. Checks RLS policy coverage
5. Generates a comprehensive report
"""

import os
import sys
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ["DATABASE_URL"] = "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test"

import asyncio
import asyncpg
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from app.db.database import Base
from app import models  # noqa: F401


# Tables that are genuinely global (not tenant-scoped)
GLOBAL_TABLES = {
    "alembic_version",
    "organizations",  # Global - organizations don't belong to an organization
    "posts",  # Global reference data
    "comments",  # Global reference data
    # Add more as discovered
}

# Tables with indirect ownership (ownership via parent table joins)
INDIRECT_OWNERSHIP = {
    "devices": ("user_id", "users", "organization_id"),
    "provisioning_steps": ("provisioning_id", "provisionings", "organization_id"),
    "optimization_alternatives": ("context_id", "optimization_contexts", "organization_id"),
    "developer_certifications": ("developer_id", "developers", "user_id", "users", "organization_id"),
    "workflow_nodes": ("workflow_id", "workflows", "organization_id"),
    "developer_subscriptions": ("developer_id", "developers", "user_id", "users", "organization_id"),
    "workflow_edges": ("workflow_id", "workflows", "organization_id"),
    "developer_usage": ("developer_id", "developers", "user_id", "users", "organization_id"),
    "industry_templates": ("created_by", "users", "organization_id"),
    "backup_corruption_tests": ("backup_id", "backup_manifests", "organization_id"),
    "backup_verification_results": ("backup_id", "backup_manifests", "organization_id"),
    "developer_applications": ("developer_id", "developers", "user_id", "users", "organization_id"),
    "subscription_payments": ("payment_id", "payments", "organization_id"),
    "subscription_invoices": ("invoice_id", "invoices", "organization_id"),
    "deployment_completeness_dimensions": ("matrix_id", "deployment_completeness_matrices", "organization_id"),
    "developers": ("user_id", "users", "organization_id"),
    "developer_api_keys": ("developer_id", "developers", "user_id", "users", "organization_id"),
    "role_permissions": ("role_id", "roles", "organization_id"),
    "workflow_versions": ("workflow_id", "workflows", "organization_id"),
    "marketplace_reviews": ("user_id", "users", "organization_id"),
    "plugin_versions": ("plugin_id", "plugins", "organization_id"),
    "workflow_execution_steps": ("execution_id", "workflow_executions", "organization_id"),
}


async def get_database_schema(conn):
    """Get all tables and their columns from the database."""
    # Get all tables in public schema
    tables_query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """
    async with conn.transaction():
        tables = [row[0] async for row in conn.cursor(tables_query)]
    
    # Get columns for each table
    schema = {}
    for table in tables:
        cols_query = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            ORDER BY ordinal_position
        """
        async with conn.transaction():
            cols = [(row[0], row[1], row[2], row[3]) async for row in conn.cursor(cols_query, table)]
        schema[table] = cols
    
    return schema


async def get_rls_status(conn):
    """Get RLS status for all tables."""
    query = """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
        AND c.relkind = 'r'
        ORDER BY c.relname
    """
    async with conn.transaction():
        return {row[0]: {"rls_enabled": row[1], "force_rls": row[2]} async for row in conn.cursor(query)}


async def get_policies(conn):
    """Get all RLS policies."""
    query = """
        SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
        FROM pg_policies
        WHERE schemaname = 'public'
        ORDER BY tablename, policyname
    """
    policies = {}
    async with conn.transaction():
        async for row in conn.cursor(query):
            table = row[1]
            if table not in policies:
                policies[table] = []
            policies[table].append({
                "name": row[2],
                "permissive": row[3],
                "roles": row[4],
                "cmd": row[5],
                "qual": row[6],
                "with_check": row[7]
            })
    return policies


async def get_model_tables():
    """Get all tables from SQLAlchemy models."""
    model_tables = {}
    for table in Base.metadata.tables.values():
        cols = {}
        for col in table.columns:
            cols[col.name] = {
                "type": str(col.type),
                "nullable": col.nullable,
                "primary_key": col.primary_key,
                "foreign_keys": [str(fk) for fk in col.foreign_keys]
            }
        model_tables[table.name] = cols
    return model_tables


def classify_table(table_name, schema, model_tables, rls_status, policies):
    """Classify a table's tenant ownership type."""
    if table_name in GLOBAL_TABLES:
        return "global"
    
    if table_name in INDIRECT_OWNERSHIP:
        return "indirect"
    
    # Check if table has organization_id column
    has_org_id = any(col[0] == "organization_id" for col in schema.get(table_name, []))
    
    if has_org_id:
        return "direct"
    
    # Check model metadata
    if table_name in model_tables:
        model_cols = model_tables[table_name]
        if "organization_id" in model_cols:
            return "direct"
    
    return "unclassified"


async def main():
    # Connect to database
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="vcos",
        password="vcos",
        database="vcos_test"
    )
    
    try:
        print("=" * 80)
        print("RLS UNIVERSAL TENANT ISOLATION INVENTORY")
        print("=" * 80)
        
        # Get schema
        print("\n[1/5] Inspecting database schema...")
        schema = await get_database_schema(conn)
        print(f"    Found {len(schema)} tables")
        
        # Get RLS status
        print("[2/5] Checking RLS status...")
        rls_status = await get_rls_status(conn)
        rls_enabled_count = sum(1 for v in rls_status.values() if v["rls_enabled"])
        force_rls_count = sum(1 for v in rls_status.values() if v["force_rls"])
        print(f"    RLS enabled: {rls_enabled_count}, FORCE RLS: {force_rls_count}")
        
        # Get policies
        print("[3/5] Checking RLS policies...")
        policies = await get_policies(conn)
        policy_count = sum(len(v) for v in policies.values())
        print(f"    Tables with policies: {len(policies)}, Total policies: {policy_count}")
        
        # Get model tables
        print("[4/5] Loading SQLAlchemy model metadata...")
        model_tables = await get_model_tables()
        print(f"    Model tables: {len(model_tables)}")
        
        # Classify all tables
        print("[5/5] Classifying tables...")
        
        classification = {
            "direct": [],
            "indirect": [],
            "global": [],
            "unclassified": []
        }
        
        for table in sorted(schema.keys()):
            cls = classify_table(table, schema, model_tables, rls_status, policies)
            classification[cls].append(table)
        
        # Print summary
        print("\n" + "=" * 80)
        print("CLASSIFICATION SUMMARY")
        print("=" * 80)
        for cls, tables in classification.items():
            print(f"\n{cls.upper()} ({len(tables)} tables):")
            for t in sorted(tables):
                rls = rls_status.get(t, {"rls_enabled": False, "force_rls": False})
                pol = policies.get(t, [])
                rls_str = "RLS+" if rls["rls_enabled"] else "RLS-"
                force_str = "FORCE+" if rls["force_rls"] else "FORCE-"
                pol_str = f"POL:{len(pol)}"
                print(f"  {t:<50} {rls_str} {force_str} {pol_str}")
        
        # Detailed analysis for tables with issues
        print("\n" + "=" * 80)
        print("ISSUES FOUND")
        print("=" * 80)
        
        issues = []
        
        # Tables with RLS but no policies
        for table in sorted(schema.keys()):
            rls = rls_status.get(table, {"rls_enabled": False, "force_rls": False})
            pol = policies.get(table, [])
            cls = classify_table(table, schema, model_tables, rls_status, policies)
            
            if rls["rls_enabled"] and len(pol) == 0:
                issues.append(f"[CRITICAL] {table} ({cls}): RLS enabled but NO policies - TABLE INACCESSIBLE")
            elif rls["rls_enabled"] and len(pol) < 4:
                issues.append(f"[WARNING] {table} ({cls}): RLS enabled but only {len(pol)}/4 policies")
            elif cls in ("direct", "indirect") and not rls["rls_enabled"]:
                issues.append(f"[CRITICAL] {table} ({cls}): Tenant-scoped but RLS NOT enabled")
            elif cls in ("direct", "indirect") and not rls["force_rls"]:
                issues.append(f"[WARNING] {table} ({cls}): RLS enabled but NOT FORCED (owner can bypass)")
        
        if issues:
            for issue in sorted(issues):
                print(issue)
        else:
            print("No issues found!")
        
        # Check current_organization_id function
        print("\n" + "=" * 80)
        print("HELPER FUNCTIONS")
        print("=" * 80)
        func_query = """
            SELECT proname, prosrc 
            FROM pg_proc 
            WHERE pronamespace = 'public'::regnamespace
            AND proname IN ('current_organization_id', 'set_current_organization_id', 'clear_current_organization_id')
        """
        async with conn.transaction():
            async for row in conn.cursor(func_query):
                print(f"  {row[0]}: {row[1][:80]}...")
        
        # Check database role
        print("\n" + "=" * 80)
        print("DATABASE ROLE PRIVILEGES")
        print("=" * 80)
        role_query = """
            SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
            FROM pg_roles
            WHERE rolname IN ('vcos', 'postgres')
        """
        async with conn.transaction():
            async for row in conn.cursor(role_query):
                print(f"  {row[0]}: super={row[1]}, bypassrls={row[2]}, createrole={row[3]}, createdb={row[4]}")
        
        # Summary stats
        print("\n" + "=" * 80)
        print("FINAL STATS")
        print("=" * 80)
        print(f"Total tables:                    {len(schema)}")
        print(f"Direct tenant-owned:             {len(classification['direct'])}")
        print(f"Indirect tenant-owned:           {len(classification['indirect'])}")
        print(f"Global:                          {len(classification['global'])}")
        print(f"Unclassified:                    {len(classification['unclassified'])}")
        print(f"Tables with RLS enabled:         {rls_enabled_count}")
        print(f"Tables with FORCE RLS:           {force_rls_count}")
        print(f"Tables with policies:            {len(policies)}")
        print(f"Total policies:                  {policy_count}")
        print(f"Tables with RLS but no policies: {sum(1 for t in schema if rls_status.get(t, {}).get('rls_enabled') and not policies.get(t))}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())