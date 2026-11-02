"""Add RLS for missing tenant-scoped tables

These 13 tables have organization_id column but were missing RLS policies.
They were likely added after the initial RLS migration.

Revision ID: 003fb2c21887
Revises: 62daa73a2354
Create Date: 2026-10-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '003fb2c21887'
down_revision: Union[str, None] = '62daa73a2354'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables with direct organization_id that were missing RLS
MISSING_TENANT_TABLES = [
    "company_knowledge_snapshots",
    "company_memory_snapshots",
    "company_timeline_events",
    "decision_timeline_events",
    "epistemic_calibration_events",
    "future_simulator_calibrations",
    "learning_timeline_events",
    "longitudinal_adversarial_tests",
    "longitudinal_integrity_findings",
    "longitudinal_provenance",
    "merger_acquisition_lineage",
    "organizational_timeline_events",
    "temporal_query_log",
]


def _table_has_column(table_name: str, column_name: str) -> str:
    """Generate SQL to check if table has a specific column."""
    return f"""
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = '{table_name}'
        AND column_name = '{column_name}'
    )
"""


def upgrade() -> None:
    conn = op.get_bind()

    for table in MISSING_TENANT_TABLES:
        # Check if table exists and has organization_id column
        has_org_id = conn.execute(sa.text(_table_has_column(table, "organization_id"))).scalar()

        if not has_org_id:
            print(f"WARNING: Table {table} does not have organization_id column, skipping")
            continue

        # Enable RLS
        conn.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))

        # Force RLS (applies to table owners too)
        conn.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))

        # Create SELECT policy
        conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_select" ON "{table}"'))
        conn.execute(sa.text(f"""
            CREATE POLICY "{table}_tenant_select" ON "{table}"
            FOR SELECT USING (
                organization_id = public.current_organization_id()
            )
        """))

        # Create INSERT policy
        conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_insert" ON "{table}"'))
        conn.execute(sa.text(f"""
            CREATE POLICY "{table}_tenant_insert" ON "{table}"
            FOR INSERT WITH CHECK (
                organization_id = public.current_organization_id()
            )
        """))

        # Create UPDATE policy
        conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_update" ON "{table}"'))
        conn.execute(sa.text(f"""
            CREATE POLICY "{table}_tenant_update" ON "{table}"
            FOR UPDATE USING (
                organization_id = public.current_organization_id()
            ) WITH CHECK (
                organization_id = public.current_organization_id()
            )
        """))

        # Create DELETE policy
        conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_delete" ON "{table}"'))
        conn.execute(sa.text(f"""
            CREATE POLICY "{table}_tenant_delete" ON "{table}"
            FOR DELETE USING (
                organization_id = public.current_organization_id()
            )
        """))

        print(f"Added RLS policies for {table}")

    print("RLS migration completed for missing tenant-scoped tables")


def downgrade() -> None:
    conn = op.get_bind()

    for table in MISSING_TENANT_TABLES:
        for policy_suffix in ["_tenant_select", "_tenant_insert", "_tenant_update", "_tenant_delete"]:
            conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}{policy_suffix}" ON "{table}"'))
        conn.execute(sa.text(f'ALTER TABLE IF EXISTS "{table}" DISABLE ROW LEVEL SECURITY'))