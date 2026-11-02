"""RLS tenant inventory - structural classification of tables for row-level security design.

Ownership is derived only from:
- organization/tenant identifier columns present on the table, and
- foreign-key reachability from such tables (path recorded, bounded depth).

Table names alone never decide ownership. Tables that cannot be structurally
resolved default to SPECIAL_CASE_REVIEW_REQUIRED - never GLOBAL_REFERENCE.
GLOBAL_REFERENCE and DERIVED_OR_REBUILDABLE require explicit allowlists.

This module performs no writes and no enforcement. It is an inventory.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

DIRECT_ORG_COLUMNS = ("organization_id", "org_id", "tenant_id")
MAX_INDIRECT_DEPTH = 4
SYSTEM_SCHEMAS = ("pg_catalog", "information_schema")
SYSTEM_TABLE_NAMES = frozenset({"alembic_version", "spatial_ref_sys"})

CATEGORY_DIRECT = "TENANT_SCOPED_DIRECT"
CATEGORY_INDIRECT = "TENANT_SCOPED_INDIRECT"
CATEGORY_GLOBAL = "GLOBAL_REFERENCE"
CATEGORY_SYSTEM = "SYSTEM_INTERNAL"
CATEGORY_DERIVED = "DERIVED_OR_REBUILDABLE"
CATEGORY_SPECIAL = "SPECIAL_CASE_REVIEW_REQUIRED"

ALL_CATEGORIES = (
    CATEGORY_DIRECT,
    CATEGORY_INDIRECT,
    CATEGORY_GLOBAL,
    CATEGORY_SYSTEM,
    CATEGORY_DERIVED,
    CATEGORY_SPECIAL,
)


@dataclass
class ColumnMeta:
    name: str
    data_type: str = ""
    nullable: bool = True


@dataclass
class ForeignKeyMeta:
    column: str
    ref_table: str
    ref_column: str = "id"


@dataclass
class TableMeta:
    schema: str
    name: str
    columns: list[ColumnMeta] = field(default_factory=list)
    foreign_keys: list[ForeignKeyMeta] = field(default_factory=list)
    rls_enabled: bool = False
    rls_forced: bool = False
    policies: list[str] = field(default_factory=list)
    estimated_rows: int = -1
    relkind: str = "r"
    model: Optional[str] = None


@dataclass
class TableClassification:
    schema: str
    name: str
    category: str
    ownership_columns: list[str] = field(default_factory=list)
    ownership_path: Optional[str] = None
    depth: Optional[int] = None
    policy_design_requirement: str = ""
    unresolved_questions: list[str] = field(default_factory=list)
    model: Optional[str] = None
    column_count: int = 0
    rls_enabled: bool = False
    rls_forced: bool = False
    policies: list[str] = field(default_factory=list)
    estimated_rows: int = -1


def classify_tables(
    tables: dict[str, TableMeta],
    global_allowlist: frozenset[str] = frozenset(),
    derived_allowlist: frozenset[str] = frozenset(),
    system_allowlist: frozenset[str] = SYSTEM_TABLE_NAMES,
) -> dict[str, TableClassification]:
    direct: dict[str, list[str]] = {}
    for name, meta in tables.items():
        org_cols = [c.name for c in meta.columns if c.name in DIRECT_ORG_COLUMNS]
        if org_cols:
            direct[name] = org_cols

    children: dict[str, list[tuple[str, str]]] = {}
    for name, meta in tables.items():
        for fk in meta.foreign_keys:
            if fk.ref_table in tables:
                children.setdefault(fk.ref_table, []).append((name, fk.column))

    reached: dict[str, tuple[int, str]] = {}
    queue: deque[str] = deque()
    for name, cols in direct.items():
        reached[name] = (0, f"{cols[0]} column")
        queue.append(name)
    while queue:
        parent = queue.popleft()
        depth, path = reached[parent]
        if depth >= MAX_INDIRECT_DEPTH:
            continue
        for child, col in children.get(parent, []):
            if child == parent or child in reached:
                continue
            reached[child] = (depth + 1, f"{col} -> {parent} ({path})")
            queue.append(child)

    results: dict[str, TableClassification] = {}
    for name, meta in tables.items():
        base = TableClassification(
            schema=meta.schema,
            name=name,
            category=CATEGORY_SPECIAL,
            model=meta.model,
            column_count=len(meta.columns),
            rls_enabled=meta.rls_enabled,
            rls_forced=meta.rls_forced,
            policies=list(meta.policies),
            estimated_rows=meta.estimated_rows,
        )

        if (
            name in system_allowlist
            or meta.schema in SYSTEM_SCHEMAS
            or name.startswith("pg_")
        ):
            base.category = CATEGORY_SYSTEM
            base.policy_design_requirement = (
                "system-managed table; no tenant policy required"
            )
        elif name in global_allowlist:
            base.category = CATEGORY_GLOBAL
            base.policy_design_requirement = (
                "no tenant scoping intended; keep RLS disabled and document why the "
                "data is safe to share across organizations"
            )
        elif name in derived_allowlist:
            base.category = CATEGORY_DERIVED
            base.policy_design_requirement = (
                "rebuildable derived data; verify it cannot leak cross-tenant rows and "
                "document the rebuild procedure"
            )
        elif name in direct:
            org_cols = direct[name]
            base.category = CATEGORY_DIRECT
            base.ownership_columns = org_cols
            base.depth = 0
            base.policy_design_requirement = (
                f"FORCE ROW LEVEL SECURITY on this table; policy predicate derives tenant "
                f"from {org_cols[0]} (e.g. current_setting('app.current_organization_id', "
                f"true)); review NULL {org_cols[0]} rows before enforcement"
            )
            base.unresolved_questions = [f"verify rows where {org_cols[0]} IS NULL"]
        elif name in reached:
            depth, path = reached[name]
            base.category = CATEGORY_INDIRECT
            base.ownership_path = path
            base.depth = depth
            base.policy_design_requirement = (
                f"policy must derive tenant via join: {path}; consider denormalizing "
                f"organization_id onto this table for policy performance and FORCE RLS; "
                f"ensure the join column is indexed"
            )
            base.unresolved_questions = [
                "confirm join column is NOT NULL for all rows",
                "decide denormalized organization_id vs subquery policy",
            ]
        else:
            base.category = CATEGORY_SPECIAL
            base.policy_design_requirement = (
                "manual ownership review required - no organization/org/tenant column and "
                "no foreign-key path to a tenant-scoped table"
            )
            base.unresolved_questions = [
                "assign ownership (tenant-scoped vs global reference vs derived) and "
                "record the rationale"
            ]

        results[name] = base

    return results


def summarize(classifications: dict[str, TableClassification]) -> dict:
    counts = {cat: 0 for cat in ALL_CATEGORIES}
    missing: list[str] = []
    depths: list[int] = []
    rls_enabled = 0
    for name in sorted(classifications):
        c = classifications[name]
        counts[c.category] = counts.get(c.category, 0) + 1
        if c.rls_enabled:
            rls_enabled += 1
        if c.category in (CATEGORY_DIRECT, CATEGORY_INDIRECT):
            if not c.rls_enabled:
                missing.append(name)
            if c.depth is not None:
                depths.append(c.depth)
    return {
        "category_counts": counts,
        "rls_enabled_count": rls_enabled,
        "rls_missing_on_scoped": missing,
        "special_case_count": counts.get(CATEGORY_SPECIAL, 0),
        "max_indirect_depth": max(depths) if depths else None,
    }


def render_summary_markdown(payload: dict) -> str:
    s = payload["summary"]
    lines = [
        "# RLS Tenant Inventory - Summary",
        "",
        f"Generated: {payload['generated_at']}",
        f"Database: {payload['database']} (schema: {payload['scope']['schema']})",
        f"Tables scanned: {payload['table_count']}",
        "",
        "## Category counts",
        "",
        "| Category | Tables |",
        "|---|---|",
    ]
    for cat in ALL_CATEGORIES:
        lines.append(f"| {cat} | {s['category_counts'].get(cat, 0)} |")
    lines += [
        "",
        f"- Row-level security currently enabled on **{s['rls_enabled_count']}** tables.",
        f"- Tenant-scoped tables (direct or indirect) missing RLS: "
        f"**{len(s['rls_missing_on_scoped'])}**.",
        f"- Review queue (SPECIAL_CASE_REVIEW_REQUIRED): **{s['special_case_count']}** tables.",
        f"- Deepest indirect ownership path: "
        f"{s['max_indirect_depth'] if s['max_indirect_depth'] is not None else 'n/a'}.",
        "",
        "## Classification rules",
        "",
        "- DIRECT: has an `organization_id` / `org_id` / `tenant_id` column (structural fact).",
        "- INDIRECT: reachable from a direct table via foreign keys (path recorded; max depth "
        f"{MAX_INDIRECT_DEPTH}).",
        "- GLOBAL_REFERENCE / DERIVED_OR_REBUILDABLE: only via explicit allowlist arguments - "
        "never inferred from names.",
        "- SYSTEM_INTERNAL: alembic/system tables and non-public schemas.",
        "- SPECIAL_CASE_REVIEW_REQUIRED: no structural ownership evidence; manual review "
        "required. No guessing.",
        "",
    ]
    if s["rls_missing_on_scoped"]:
        lines += ["## Scoped tables missing RLS (first 20)", ""]
        for name in s["rls_missing_on_scoped"][:20]:
            lines.append(f"- {name}")
        lines.append("")
    specials = [
        t["name"] for t in payload["tables"] if t["category"] == CATEGORY_SPECIAL
    ]
    if specials:
        lines += ["## Review queue sample (first 20 of SPECIAL_CASE)", ""]
        for name in specials[:20]:
            lines.append(f"- {name}")
        lines.append("")
    return "\n".join(lines)


async def collect_table_metadata(dsn: str, schema: str = "public") -> dict[str, TableMeta]:
    import asyncpg

    conn = await asyncpg.connect(dsn=dsn.replace("+asyncpg", ""))
    try:
        tables: dict[str, TableMeta] = {}
        table_rows = await conn.fetch(
            """
            SELECT c.relname AS table_name, n.nspname AS schema_name,
                   c.relrowsecurity AS rls_enabled,
                   c.relforcerowsecurity AS rls_forced,
                   c.reltuples::bigint AS estimated_rows,
                   c.relkind AS relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = $1 AND c.relkind IN ('r', 'p')
            ORDER BY c.relname
            """,
            schema,
        )
        for row in table_rows:
            tables[row["table_name"]] = TableMeta(
                schema=row["schema_name"],
                name=row["table_name"],
                rls_enabled=row["rls_enabled"],
                rls_forced=row["rls_forced"],
                estimated_rows=int(row["estimated_rows"] or -1),
                relkind=row["relkind"],
            )
        column_rows = await conn.fetch(
            """
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = $1
            ORDER BY table_name, ordinal_position
            """,
            schema,
        )
        for row in column_rows:
            meta = tables.get(row["table_name"])
            if meta is not None:
                meta.columns.append(
                    ColumnMeta(
                        name=row["column_name"],
                        data_type=row["data_type"],
                        nullable=(row["is_nullable"] == "YES"),
                    )
                )
        fk_rows = await conn.fetch(
            """
            SELECT tc.table_name AS table_name,
                   kcu.column_name AS column_name,
                   ccu.table_name AS ref_table,
                   ccu.column_name AS ref_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = $1
            """,
            schema,
        )
        for row in fk_rows:
            meta = tables.get(row["table_name"])
            if meta is not None:
                meta.foreign_keys.append(
                    ForeignKeyMeta(
                        column=row["column_name"],
                        ref_table=row["ref_table"],
                        ref_column=row["ref_column"],
                    )
                )
        policy_rows = await conn.fetch(
            "SELECT tablename, policyname FROM pg_policies WHERE schemaname = $1",
            schema,
        )
        for row in policy_rows:
            meta = tables.get(row["tablename"])
            if meta is not None:
                meta.policies.append(row["policyname"])
        return tables
    finally:
        await conn.close()


def map_models() -> dict[str, str]:
    try:
        import app.models  # noqa: F401
        from app.db.database import Base
    except Exception:
        return {}
    mapping: dict[str, str] = {}
    try:
        for mapper in Base.registry.mappers:
            cls = mapper.class_
            table = getattr(cls, "__table__", None)
            if table is not None and table.name not in mapping:
                mapping[table.name] = f"{cls.__module__}.{cls.__name__}"
    except Exception:
        return mapping
    return mapping


def mask_database_url(url: str) -> str:
    return re.sub(r"://([^:/@]+):[^@]+@", r"://\1:***@", url)


def build_payload(
    classifications: dict[str, TableClassification],
    database: str,
    schema: str,
) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"schema": schema, "relkinds": ["r", "p"]},
        "database": mask_database_url(database),
        "table_count": len(classifications),
        "summary": summarize(classifications),
        "tables": [
            asdict(classifications[name]) for name in sorted(classifications)
        ],
    }
