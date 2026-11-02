#!/usr/bin/env python3
"""
RLS Deployment Verification Script

This script verifies that RLS policies are correctly installed after migration.
It should be run as part of the deployment pipeline to ensure tenant isolation
is enforced before activating a new deployment.

Usage:
    python verify_rls_deployment.py [--db-url URL] [--fail-on-error]
"""

import argparse
import sys
import os
from typing import List, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor


def connect_db(db_url: str):
    """Connect to PostgreSQL database."""
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


def check_rls_enabled(conn, table: str) -> Tuple[bool, bool]:
    """Check if RLS and FORCE RLS are enabled on a table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT relrowsecurity, relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = %s AND c.relkind = 'r'
        """, (table,))
        result = cur.fetchone()
        if result:
            return result['relrowsecurity'], result['relforcerowsecurity']
        return False, False


def check_policies(conn, table: str) -> List[dict]:
    """Get all RLS policies for a table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT policyname, cmd, permissive, roles, qual, with_check
            FROM pg_policies
            WHERE schemaname = 'public' AND tablename = %s
            ORDER BY policyname
        """, (table,))
        return cur.fetchall()


def verify_table_rls(conn, table: str, expected_direct: bool = True) -> List[str]:
    """Verify RLS configuration for a single table. Returns list of errors."""
    errors = []
    
    rls_enabled, force_rls = check_rls_enabled(conn, table)
    policies = check_policies(conn, table)
    
    if not rls_enabled:
        errors.append(f"Table {table}: RLS not enabled")
    
    if not force_rls:
        errors.append(f"Table {table}: FORCE ROW LEVEL SECURITY not enabled")
    
    if expected_direct:
        # Direct tables should have 4 policies (SELECT, INSERT, UPDATE, DELETE)
        expected_cmds = {'SELECT', 'INSERT', 'UPDATE', 'DELETE'}
        actual_cmds = {p['cmd'] for p in policies}
        missing = expected_cmds - actual_cmds
        if missing:
            errors.append(f"Table {table}: Missing policies for {missing}")
        
        # Verify policy quality
        for policy in policies:
            if policy['cmd'] in ('SELECT', 'UPDATE', 'DELETE'):
                if not policy['qual'] or 'current_organization_id' not in policy['qual']:
                    errors.append(f"Table {table} policy {policy['policyname']}: Missing current_organization_id in USING clause")
            if policy['cmd'] in ('INSERT', 'UPDATE'):
                if not policy['with_check'] or 'current_organization_id' not in policy['with_check']:
                    errors.append(f"Table {table} policy {policy['policyname']}: Missing current_organization_id in WITH CHECK clause")
    
    return errors


def verify_helper_functions(conn) -> List[str]:
    """Verify that helper functions exist and are correct."""
    errors = []
    
    with conn.cursor() as cur:
        # Check current_organization_id function
        cur.execute("""
            SELECT prosrc FROM pg_proc 
            WHERE proname = 'current_organization_id' AND pronamespace = 'public'::regnamespace
        """)
        func = cur.fetchone()
        if not func:
            errors.append("Function current_organization_id() does not exist")
        else:
            source = func['prosrc']
            if 'current_setting' not in source or 'app.current_organization_id' not in source:
                errors.append("Function current_organization_id() does not use app.current_organization_id setting")
        
        # Check set_current_organization_id function
        cur.execute("""
            SELECT prosrc FROM pg_proc 
            WHERE proname = 'set_current_organization_id' AND pronamespace = 'public'::regnamespace
        """)
        func = cur.fetchone()
        if not func:
            errors.append("Function set_current_organization_id() does not exist")
        
        # Check clear_current_organization_id function
        cur.execute("""
            SELECT prosrc FROM pg_proc 
            WHERE proname = 'clear_current_organization_id' AND pronamespace = 'public'::regnamespace
        """)
        func = cur.fetchone()
        if not func:
            errors.append("Function clear_current_organization_id() does not exist")
    
    return errors


def verify_role_security(conn) -> List[str]:
    """Verify that application role cannot bypass RLS."""
    errors = []
    
    with conn.cursor() as cur:
        # Check vcos role
        cur.execute("""
            SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
            FROM pg_roles WHERE rolname = 'vcos'
        """)
        role = cur.fetchone()
        if not role:
            errors.append("Role 'vcos' does not exist")
        else:
            if role['rolsuper']:
                errors.append("Role 'vcos' is superuser (should not be)")
            if role['rolbypassrls']:
                errors.append("Role 'vcos' has BYPASSRLS (should not)")
            if role['rolcreaterole']:
                errors.append("Role 'vcos' can create roles (should not)")
            if role['rolcreatedb']:
                errors.append("Role 'vcos' can create databases (should not)")
    
    return errors


def main():
    parser = argparse.ArgumentParser(description="Verify RLS deployment")
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL", "postgresql://vcos:vcos@localhost:5432/vcos_test"),
                        help="Database connection URL")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit with error code if any issues found")
    args = parser.parse_args()
    
    print("=" * 80)
    print("RLS DEPLOYMENT VERIFICATION")
    print("=" * 80)
    print(f"Database: {args.db_url}")
    print()
    
    conn = connect_db(args.db_url)
    conn.autocommit = True
    
    all_errors = []
    
    try:
        # 1. Verify helper functions
        print("[1/4] Verifying helper functions...")
        errors = verify_helper_functions(conn)
        all_errors.extend(errors)
        if errors:
            print(f"  FAIL: {len(errors)} errors")
            for e in errors:
                print(f"  - {e}")
        else:
            print("  PASS")
        
        # 2. Verify role security
        print("[2/4] Verifying role security...")
        errors = verify_role_security(conn)
        all_errors.extend(errors)
        if errors:
            print(f"  FAIL: {len(errors)} errors")
            for e in errors:
                print(f"  - {e}")
        else:
            print("  PASS")
        
        # 3. Verify RLS on all tenant-scoped tables
        print("[3/4] Verifying RLS on tenant-scoped tables...")
        with conn.cursor() as cur:
            # Get all tables with organization_id column
            cur.execute("""
                SELECT table_name FROM information_schema.columns
                WHERE table_schema = 'public' AND column_name = 'organization_id'
                AND table_name NOT IN ('alembic_version', 'organizations')
                ORDER BY table_name
            """)
            tenant_tables = [row['table_name'] for row in cur.fetchall()]
        
        print(f"  Found {len(tenant_tables)} tables with organization_id column")
        
        table_errors = 0
        for table in tenant_tables:
            errors = verify_table_rls(conn, table, expected_direct=True)
            if errors:
                table_errors += 1
                all_errors.extend(errors)
                for e in errors:
                    print(f"  - {e}")
        
        if table_errors == 0:
            print(f"  PASS: All {len(tenant_tables)} tables verified")
        else:
            print(f"  FAIL: {table_errors} tables have issues")
        
        # 4. Verify indirect tables
        print("[4/4] Verifying indirect tenant tables...")
        indirect_tables = {
            'devices': 'user_id -> users.organization_id',
            'developers': 'user_id -> users.organization_id',
            'developer_api_keys': 'developer_id -> developers.user_id -> users.organization_id',
            'developer_applications': 'developer_id -> developers.user_id -> users.organization_id',
            'developer_certifications': 'developer_id -> developers.user_id -> users.organization_id',
            'developer_subscriptions': 'developer_id -> developers.user_id -> users.organization_id',
            'developer_usage': 'developer_id -> developers.user_id -> users.organization_id',
            'backup_corruption_tests': 'backup_id -> backup_manifests.organization_id',
            'backup_verification_results': 'backup_id -> backup_manifests.organization_id',
            'deployment_completeness_dimensions': 'matrix_id -> deployment_completeness_matrices.organization_id',
            'industry_templates': 'created_by -> users.organization_id',
            'marketplace_reviews': 'user_id -> users.organization_id',
            'optimization_alternatives': 'context_id -> optimization_contexts.organization_id',
            'plugin_versions': 'plugin_id -> plugins.organization_id',
            'provisioning_steps': 'provisioning_id -> provisionings.organization_id',
            'role_permissions': 'role_id -> roles.organization_id',
            'subscription_invoices': 'invoice_id -> invoices.organization_id',
            'subscription_payments': 'payment_id -> payments.organization_id',
            'workflow_edges': 'workflow_id -> workflows.organization_id',
            'workflow_nodes': 'workflow_id -> workflows.organization_id',
            'workflow_versions': 'workflow_id -> workflows.organization_id',
            'workflow_execution_steps': 'execution_id -> workflow_executions.organization_id',
        }
        
        indirect_errors = 0
        for table, path in indirect_tables.items():
            errors = verify_table_rls(conn, table, expected_direct=False)
            if errors:
                indirect_errors += 1
                all_errors.extend(errors)
                for e in errors:
                    print(f"  - {table}: {e}")
        
        if indirect_errors == 0:
            print(f"  PASS: All {len(indirect_tables)} indirect tables verified")
        else:
            print(f"  FAIL: {indirect_errors} indirect tables have issues")
        
    finally:
        conn.close()
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total errors: {len(all_errors)}")
    
    if all_errors:
        print("DEPLOYMENT VERIFICATION FAILED")
        if args.fail_on_error:
            sys.exit(1)
    else:
        print("DEPLOYMENT VERIFICATION PASSED")
    
    return len(all_errors) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)