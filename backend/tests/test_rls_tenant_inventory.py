"""Unit tests for RLS tenant inventory classification (no database required)."""

from app.services.rls_tenant_inventory import (
    CATEGORY_DERIVED,
    CATEGORY_DIRECT,
    CATEGORY_GLOBAL,
    CATEGORY_INDIRECT,
    CATEGORY_SPECIAL,
    CATEGORY_SYSTEM,
    MAX_INDIRECT_DEPTH,
    ColumnMeta,
    ForeignKeyMeta,
    TableMeta,
    classify_tables,
    mask_database_url,
    render_summary_markdown,
    summarize,
)


def tbl(name, columns=(), fks=(), rls=False, schema="public"):
    return TableMeta(
        schema=schema,
        name=name,
        columns=[ColumnMeta(name=c) for c in columns],
        foreign_keys=[
            ForeignKeyMeta(
                column=fk[0], ref_table=fk[1], ref_column=fk[2] if len(fk) > 2 else "id"
            )
            for fk in fks
        ],
        rls_enabled=rls,
    )


class TestClassification:
    def test_direct_detection_across_column_names(self):
        tables = {
            "users": tbl("users", columns=("id", "organization_id")),
            "tenant_notes": tbl("tenant_notes", columns=("id", "tenant_id")),
            "org_settings": tbl("org_settings", columns=("id", "org_id")),
        }
        results = classify_tables(tables)
        for name in ("users", "tenant_notes", "org_settings"):
            assert results[name].category == CATEGORY_DIRECT
            assert results[name].depth == 0
            assert results[name].ownership_columns

    def test_indirect_via_single_hop(self):
        tables = {
            "users": tbl("users", columns=("id", "organization_id")),
            "api_keys": tbl("api_keys", columns=("id", "user_id"), fks=(("user_id", "users"),)),
        }
        results = classify_tables(tables)
        assert results["api_keys"].category == CATEGORY_INDIRECT
        assert results["api_keys"].depth == 1
        assert "user_id -> users" in results["api_keys"].ownership_path

    def test_indirect_two_hops_with_path(self):
        tables = {
            "users": tbl("users", columns=("id", "organization_id")),
            "api_keys": tbl("api_keys", columns=("id", "user_id"), fks=(("user_id", "users"),)),
            "api_key_events": tbl(
                "api_key_events", columns=("id", "key_id"), fks=(("key_id", "api_keys"),)
            ),
        }
        results = classify_tables(tables)
        assert results["api_key_events"].category == CATEGORY_INDIRECT
        assert results["api_key_events"].depth == 2
        assert "key_id -> api_keys" in results["api_key_events"].ownership_path

    def test_system_tables(self):
        tables = {"alembic_version": tbl("alembic_version", columns=("version_num",))}
        results = classify_tables(tables)
        assert results["alembic_version"].category == CATEGORY_SYSTEM

    def test_unknown_table_defaults_to_special_not_global(self):
        tables = {"widgets": tbl("widgets", columns=("id", "label"))}
        results = classify_tables(tables)
        assert results["widgets"].category == CATEGORY_SPECIAL
        assert results["widgets"].unresolved_questions

    def test_allowlists_promote_global_and_derived(self):
        tables = {
            "countries": tbl("countries", columns=("code",)),
            "daily_rollups": tbl("daily_rollups", columns=("id", "total")),
        }
        results = classify_tables(
            tables,
            global_allowlist=frozenset({"countries"}),
            derived_allowlist=frozenset({"daily_rollups"}),
        )
        assert results["countries"].category == CATEGORY_GLOBAL
        assert results["daily_rollups"].category == CATEGORY_DERIVED

    def test_cycles_are_safe_and_unresolved(self):
        tables = {
            "a": tbl("a", columns=("id", "b_id"), fks=(("b_id", "b"),)),
            "b": tbl("b", columns=("id", "a_id"), fks=(("a_id", "a"),)),
        }
        results = classify_tables(tables)
        assert results["a"].category == CATEGORY_SPECIAL
        assert results["b"].category == CATEGORY_SPECIAL

    def test_self_reference_does_not_create_indirect(self):
        tables = {"nodes": tbl("nodes", columns=("id", "parent_id"), fks=(("parent_id", "nodes"),))}
        results = classify_tables(tables)
        assert results["nodes"].category == CATEGORY_SPECIAL

    def test_depth_limit_beyond_max_becomes_special(self):
        tables = {"root": tbl("root", columns=("id", "organization_id"))}
        prev = "root"
        for i in range(1, MAX_INDIRECT_DEPTH + 2):
            name = f"c{i}"
            tables[name] = tbl(name, columns=("id", "parent_id"), fks=(("parent_id", prev),))
            prev = name
        results = classify_tables(tables)
        assert results[f"c{MAX_INDIRECT_DEPTH}"].category == CATEGORY_INDIRECT
        assert results[f"c{MAX_INDIRECT_DEPTH + 1}"].category == CATEGORY_SPECIAL


class TestSummarizeAndRender:
    def _payload(self):
        tables = {
            "users": tbl("users", columns=("id", "organization_id")),
            "api_keys": tbl(
                "api_keys", columns=("id", "user_id"), fks=(("user_id", "users"),), rls=True
            ),
            "widgets": tbl("widgets", columns=("id",)),
        }
        classifications = classify_tables(tables)
        payload = {
            "generated_at": "2026-10-17T00:00:00+00:00",
            "scope": {"schema": "public", "relkinds": ["r", "p"]},
            "database": mask_database_url("postgresql+asyncpg://user:secret@host/db"),
            "table_count": len(classifications),
            "summary": summarize(classifications),
            "tables": [
                {
                    "name": c.name,
                    "category": c.category,
                    "rls_enabled": c.rls_enabled,
                    "depth": c.depth,
                    "ownership_path": c.ownership_path,
                    "ownership_columns": c.ownership_columns,
                    "policy_design_requirement": c.policy_design_requirement,
                    "unresolved_questions": c.unresolved_questions,
                    "model": c.model,
                }
                for c in classifications.values()
            ],
        }
        return payload

    def test_summary_counts_and_missing_rls(self):
        payload = self._payload()
        s = payload["summary"]
        assert s["category_counts"][CATEGORY_DIRECT] == 1
        assert s["category_counts"][CATEGORY_INDIRECT] == 1
        assert s["category_counts"][CATEGORY_SPECIAL] == 1
        assert s["rls_enabled_count"] == 1
        assert s["rls_missing_on_scoped"] == ["users"]
        assert s["max_indirect_depth"] == 1

    def test_markdown_contains_categories_and_counts(self):
        payload = self._payload()
        md = render_summary_markdown(payload)
        assert CATEGORY_DIRECT in md
        assert CATEGORY_SPECIAL in md
        assert "users" in md
        assert "widgets" in md

    def test_mask_database_url_hides_password(self):
        masked = mask_database_url("postgresql+asyncpg://user:secret@host/db")
        assert "secret" not in masked
        assert "user:***@host" in masked
