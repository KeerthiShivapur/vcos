"""Alter current_organization_id() function to return text (hex without hyphens).

The function was previously returning UUID with hyphens, but the organization_id
column stores hex without hyphens (32 chars). This migration alters the function
to return text (hex without hyphens) to match the column format.

Revision ID: 9f3c1a7d52e7
Revises: 9f3c1a7d52e6
Create Date: 2026-10-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9f3c1a7d52e7'
down_revision: Union[str, None] = 'f5cd24c9e5bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Drop the function with CASCADE to remove dependent policies
    conn.execute(sa.text("DROP FUNCTION IF EXISTS public.current_organization_id() CASCADE"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS public.set_current_organization_id(text) CASCADE"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS public.clear_current_organization_id() CASCADE"))
    
    # Create the function to return text (hex without hyphens)
    conn.execute(sa.text("""
        CREATE FUNCTION public.current_organization_id()
        RETURNS text LANGUAGE sql STABLE AS $$
            SELECT replace(NULLIF(current_setting('app.current_organization_id', true), ''), '-', '')
        $$;
    """))
    
    # Also update set_current_organization_id to accept text
    conn.execute(sa.text("""
        CREATE FUNCTION public.set_current_organization_id(org_id text)
        RETURNS void LANGUAGE sql AS $$
            SELECT set_config('app.current_organization_id', org_id, false);
        $$;
    """))
    
    # Recreate clear function
    conn.execute(sa.text("""
        CREATE FUNCTION public.clear_current_organization_id()
        RETURNS void LANGUAGE sql AS $$
            SELECT set_config('app.current_organization_id', '', false);
        $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    
    # Drop the functions
    conn.execute(sa.text("DROP FUNCTION IF EXISTS public.current_organization_id()"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS public.set_current_organization_id(text)"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS public.clear_current_organization_id()"))
    
    # Recreate with UUID return type
    conn.execute(sa.text("""
        CREATE FUNCTION public.current_organization_id()
        RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('app.current_organization_id', true), '')::uuid
        $$;
    """))
    
    conn.execute(sa.text("""
        CREATE FUNCTION public.set_current_organization_id(org_id uuid)
        RETURNS void LANGUAGE sql AS $$
            SELECT set_config('app.current_organization_id', org_id::text, false);
        $$;
    """))
    
    conn.execute(sa.text("""
        CREATE FUNCTION public.clear_current_organization_id()
        RETURNS void LANGUAGE sql AS $$
            SELECT set_config('app.current_organization_id', '', false);
        $$;
    """))