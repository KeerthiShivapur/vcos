"""RLS tenant inventory CLI.

Produces durable artifacts (read-only against the database):
    RLS_TENANT_INVENTORY.json
    RLS_TENANT_INVENTORY_SUMMARY.md

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts\\rls_tenant_inventory.py
    .venv\\Scripts\\python.exe scripts\\rls_tenant_inventory.py --output-dir ..\\docs
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.rls_tenant_inventory import (  # noqa: E402
    build_payload,
    classify_tables,
    collect_table_metadata,
    map_models,
    render_summary_markdown,
)


def _database_url() -> str:
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _split_names(value: str) -> frozenset[str]:
    return frozenset(part.strip() for part in value.split(",") if part.strip())


async def main() -> int:
    parser = argparse.ArgumentParser(description="RLS tenant inventory (read-only)")
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--global-allowlist", default="", help="comma-separated table names")
    parser.add_argument("--derived-allowlist", default="", help="comma-separated table names")
    args = parser.parse_args()

    url = _database_url()
    if not url:
        print("BLOCKED: DATABASE_URL not found in backend/.env")
        return 2

    tables = await collect_table_metadata(url, schema=args.schema)
    if not tables:
        print(f"BLOCKED: no tables found in schema {args.schema}")
        return 3

    models = map_models()
    for name, meta in tables.items():
        meta.model = models.get(name)

    classifications = classify_tables(
        tables,
        global_allowlist=_split_names(args.global_allowlist),
        derived_allowlist=_split_names(args.derived_allowlist),
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(classifications, database=url, schema=args.schema)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()

    json_path = out_dir / "RLS_TENANT_INVENTORY.json"
    md_path = out_dir / "RLS_TENANT_INVENTORY_SUMMARY.md"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_summary_markdown(payload), encoding="utf-8")

    summary = payload["summary"]
    print(f"Tables scanned: {payload['table_count']}")
    for category, count in summary["category_counts"].items():
        print(f"  {category}: {count}")
    print(f"RLS enabled on: {summary['rls_enabled_count']} tables")
    print(f"Scoped tables missing RLS: {len(summary['rls_missing_on_scoped'])}")
    print(f"Wrote {json_path.name} and {md_path.name} to {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
