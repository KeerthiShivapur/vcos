"""Fix missing RLS policies for indirect tenant-owned tables

These 21 tables have RLS enabled (via migration 9f3c1a7d52e5) but their policies
were dropped by migration 9f3c1a7d52e6 which only recreated policies for tables
with direct organization_id column. This migration restores the missing policies.

Revision ID: 62daa73a2354
Revises: c9a1f4e7b2d8
Create Date: 2026-10-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '62daa73a2354'
down_revision: Union[str, None] = 'c9a1f4e7b2d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_has_column(table_name: str, column_name: str) -> str:
    """Generate SQL to check if table has a specific column."""
    return f"""
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = '{table_name}'
        AND column_name = '{column_name}'
    )
"""


def _enable_rls_and_policies(conn, table: str, select_using: str, insert_check: str, update_using: str, delete_using: str):
    """Helper to enable RLS and create all 4 policies for a table."""
    # Enable RLS if not already enabled
    conn.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    conn.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))

    # Drop existing policies if any
    conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_select" ON "{table}"'))
    conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_insert" ON "{table}"'))
    conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_update" ON "{table}"'))
    conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_delete" ON "{table}"'))

    # Create SELECT policy
    conn.execute(sa.text(f'CREATE POLICY "{table}_tenant_select" ON "{table}" FOR SELECT USING ({select_using})'))

    # Create INSERT policy
    conn.execute(sa.text(f'CREATE POLICY "{table}_tenant_insert" ON "{table}" FOR INSERT WITH CHECK ({insert_check})'))

    # Create UPDATE policy
    conn.execute(sa.text(f'CREATE POLICY "{table}_tenant_update" ON "{table}" FOR UPDATE USING ({update_using}) WITH CHECK ({insert_check})'))

    # Create DELETE policy
    conn.execute(sa.text(f'CREATE POLICY "{table}_tenant_delete" ON "{table}" FOR DELETE USING ({delete_using})'))


def upgrade() -> None:
    conn = op.get_bind()

    # backup_corruption_tests: backup_id -> backup_manifests
    for table in ["backup_corruption_tests", "backup_verification_results"]:
        if conn.execute(sa.text(_table_has_column(table, "backup_id"))).scalar():
            _enable_rls_and_policies(
                conn, table,
                "backup_id IN (SELECT id FROM backup_manifests WHERE organization_id = public.current_organization_id())",
                "backup_id IN (SELECT id FROM backup_manifests WHERE organization_id = public.current_organization_id())",
                "backup_id IN (SELECT id FROM backup_manifests WHERE organization_id = public.current_organization_id())",
                "backup_id IN (SELECT id FROM backup_manifests WHERE organization_id = public.current_organization_id())",
            )

    # deployment_completeness_dimensions: matrix_id -> deployment_completeness_matrices
    if conn.execute(sa.text(_table_has_column("deployment_completeness_dimensions", "matrix_id"))).scalar():
        _enable_rls_and_policies(
            conn, "deployment_completeness_dimensions",
            "matrix_id IN (SELECT id FROM deployment_completeness_matrices WHERE organization_id = public.current_organization_id())",
            "matrix_id IN (SELECT id FROM deployment_completeness_matrices WHERE organization_id = public.current_organization_id())",
            "matrix_id IN (SELECT id FROM deployment_completeness_matrices WHERE organization_id = public.current_organization_id())",
            "matrix_id IN (SELECT id FROM deployment_completeness_matrices WHERE organization_id = public.current_organization_id())",
        )

    # developer_* tables: developer_id -> developers -> users
    for table in ["developer_api_keys", "developer_applications", "developer_certifications",
                  "developer_subscriptions", "developer_usage"]:
        if conn.execute(sa.text(_table_has_column(table, "developer_id"))).scalar():
            _enable_rls_and_policies(
                conn, table,
                "developer_id IN (SELECT d.id FROM developers d JOIN users u ON d.user_id = u.id WHERE u.organization_id = public.current_organization_id())",
                "developer_id IN (SELECT d.id FROM developers d JOIN users u ON d.user_id = u.id WHERE u.organization_id = public.current_organization_id())",
                "developer_id IN (SELECT d.id FROM developers d JOIN users u ON d.user_id = u.id WHERE u.organization_id = public.current_organization_id())",
                "developer_id IN (SELECT d.id FROM developers d JOIN users u ON d.user_id = u.id WHERE u.organization_id = public.current_organization_id())",
            )

    # developers: user_id -> users
    if conn.execute(sa.text(_table_has_column("developers", "user_id"))).scalar():
        _enable_rls_and_policies(
            conn, "developers",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
        )

    # devices: user_id -> users (already has policies, but ensure they're correct)
    if conn.execute(sa.text(_table_has_column("devices", "user_id"))).scalar():
        _enable_rls_and_policies(
            conn, "devices",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
        )

    # industry_templates: created_by -> users
    if conn.execute(sa.text(_table_has_column("industry_templates", "created_by"))).scalar():
        _enable_rls_and_policies(
            conn, "industry_templates",
            "created_by IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "created_by IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "created_by IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "created_by IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
        )

    # marketplace_reviews: user_id -> users
    if conn.execute(sa.text(_table_has_column("marketplace_reviews", "user_id"))).scalar():
        _enable_rls_and_policies(
            conn, "marketplace_reviews",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
        )

    # optimization_alternatives: context_id -> optimization_contexts
    if conn.execute(sa.text(_table_has_column("optimization_alternatives", "context_id"))).scalar():
        _enable_rls_and_policies(
            conn, "optimization_alternatives",
            "context_id IN (SELECT id FROM optimization_contexts WHERE organization_id = public.current_organization_id())",
            "context_id IN (SELECT id FROM optimization_contexts WHERE organization_id = public.current_organization_id())",
            "context_id IN (SELECT id FROM optimization_contexts WHERE organization_id = public.current_organization_id())",
            "context_id IN (SELECT id FROM optimization_contexts WHERE organization_id = public.current_organization_id())",
        )

    # plugin_versions: plugin_id -> plugins
    if conn.execute(sa.text(_table_has_column("plugin_versions", "plugin_id"))).scalar():
        _enable_rls_and_policies(
            conn, "plugin_versions",
            "plugin_id IN (SELECT id FROM plugins WHERE organization_id = public.current_organization_id())",
            "plugin_id IN (SELECT id FROM plugins WHERE organization_id = public.current_organization_id())",
            "plugin_id IN (SELECT id FROM plugins WHERE organization_id = public.current_organization_id())",
            "plugin_id IN (SELECT id FROM plugins WHERE organization_id = public.current_organization_id())",
        )

    # provisioning_steps: provisioning_id -> provisionings
    if conn.execute(sa.text(_table_has_column("provisioning_steps", "provisioning_id"))).scalar():
        _enable_rls_and_policies(
            conn, "provisioning_steps",
            "provisioning_id IN (SELECT id FROM provisionings WHERE organization_id = public.current_organization_id())",
            "provisioning_id IN (SELECT id FROM provisionings WHERE organization_id = public.current_organization_id())",
            "provisioning_id IN (SELECT id FROM provisionings WHERE organization_id = public.current_organization_id())",
            "provisioning_id IN (SELECT id FROM provisionings WHERE organization_id = public.current_organization_id())",
        )

    # role_permissions: role_id -> roles
    if conn.execute(sa.text(_table_has_column("role_permissions", "role_id"))).scalar():
        _enable_rls_and_policies(
            conn, "role_permissions",
            "role_id IN (SELECT id FROM roles WHERE organization_id = public.current_organization_id())",
            "role_id IN (SELECT id FROM roles WHERE organization_id = public.current_organization_id())",
            "role_id IN (SELECT id FROM roles WHERE organization_id = public.current_organization_id())",
            "role_id IN (SELECT id FROM roles WHERE organization_id = public.current_organization_id())",
        )

    # subscription_invoices: invoice_id -> invoices
    if conn.execute(sa.text(_table_has_column("subscription_invoices", "invoice_id"))).scalar():
        _enable_rls_and_policies(
            conn, "subscription_invoices",
            "invoice_id IN (SELECT id FROM invoices WHERE organization_id = public.current_organization_id())",
            "invoice_id IN (SELECT id FROM invoices WHERE organization_id = public.current_organization_id())",
            "invoice_id IN (SELECT id FROM invoices WHERE organization_id = public.current_organization_id())",
            "invoice_id IN (SELECT id FROM invoices WHERE organization_id = public.current_organization_id())",
        )

    # subscription_payments: payment_id -> payments
    if conn.execute(sa.text(_table_has_column("subscription_payments", "payment_id"))).scalar():
        _enable_rls_and_policies(
            conn, "subscription_payments",
            "payment_id IN (SELECT id FROM payments WHERE organization_id = public.current_organization_id())",
            "payment_id IN (SELECT id FROM payments WHERE organization_id = public.current_organization_id())",
            "payment_id IN (SELECT id FROM payments WHERE organization_id = public.current_organization_id())",
            "payment_id IN (SELECT id FROM payments WHERE organization_id = public.current_organization_id())",
        )

    # workflow_* tables: workflow_id -> workflows
    for table in ["workflow_edges", "workflow_nodes", "workflow_versions"]:
        if conn.execute(sa.text(_table_has_column(table, "workflow_id"))).scalar():
            _enable_rls_and_policies(
                conn, table,
                "workflow_id IN (SELECT id FROM workflows WHERE organization_id = public.current_organization_id())",
                "workflow_id IN (SELECT id FROM workflows WHERE organization_id = public.current_organization_id())",
                "workflow_id IN (SELECT id FROM workflows WHERE organization_id = public.current_organization_id())",
                "workflow_id IN (SELECT id FROM workflows WHERE organization_id = public.current_organization_id())",
            )

    # workflow_execution_steps: execution_id -> workflow_executions
    if conn.execute(sa.text(_table_has_column("workflow_execution_steps", "execution_id"))).scalar():
        _enable_rls_and_policies(
            conn, "workflow_execution_steps",
            "execution_id IN (SELECT id FROM workflow_executions WHERE organization_id = public.current_organization_id())",
            "execution_id IN (SELECT id FROM workflow_executions WHERE organization_id = public.current_organization_id())",
            "execution_id IN (SELECT id FROM workflow_executions WHERE organization_id = public.current_organization_id())",
            "execution_id IN (SELECT id FROM workflow_executions WHERE organization_id = public.current_organization_id())",
        )

    print("Fixed missing RLS policies for all indirect tenant-owned tables")


def downgrade() -> None:
    conn = op.get_bind()

    # Drop all policies and disable RLS for the 21 indirect tables
    indirect_tables = [
        "backup_corruption_tests", "backup_verification_results",
        "deployment_completeness_dimensions",
        "developer_api_keys", "developer_applications", "developer_certifications",
        "developer_subscriptions", "developer_usage", "developers", "devices",
        "industry_templates", "marketplace_reviews",
        "optimization_alternatives", "plugin_versions", "provisioning_steps",
        "role_permissions", "subscription_invoices", "subscription_payments",
        "workflow_edges", "workflow_nodes", "workflow_versions", "workflow_execution_steps",
    ]
    for table in indirect_tables:
        for policy_suffix in ["_tenant_select", "_tenant_insert", "_tenant_update", "_tenant_delete"]:
            conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}{policy_suffix}" ON "{table}"'))
        conn.execute(sa.text(f'ALTER TABLE IF EXISTS "{table}" DISABLE ROW LEVEL SECURITY'))