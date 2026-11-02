"""4H.6 post-step schema probe - READ-ONLY audit companion.

Replicates the Phase-E snapshot keys but NEVER overwrites
SLICE4H6_SCHEMA_BASELINE.json. Writes its snapshot to a separate file
(default: SLICE4H6_SCHEMA_POST_STEP2.json) so the Phase-E baseline stays
immutable for the whole slice.

Usage:
    python scripts/schema_probe_4h6.py [output_path]
"""

import asyncio
import json
import sys

import asyncpg

SCHEMA_KEYS = (
    "public_table_count",
    "company_actions_columns",
    "candidate_4h6_event_rows",
)


async def main() -> int:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "../SLICE4H6_SCHEMA_POST_STEP2.json"
    url = ""
    for line in open(".env"):
        if line.strip().startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")
    conn = await asyncpg.connect(dsn=url.replace("+asyncpg", ""))
    try:
        tables = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
        )
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='company_actions' ORDER BY column_name"
        )
        new_events = await conn.fetchval(
            "SELECT count(*) FROM events WHERE name = ANY($1)",
            [
                "performance.created", "performance.assessed", "performance.computed",
                "decision.scored", "company.performance.assessed",
            ],
        )
        quality_rows = await conn.fetchval("SELECT count(*) FROM company_decision_quality")
        track_rows = await conn.fetchval("SELECT count(*) FROM company_decision_tracks")
        outcome_rows = await conn.fetchval("SELECT count(*) FROM company_action_outcomes")
        observation_rows = await conn.fetchval("SELECT count(*) FROM business_metric_observations")
        lineage_rows = await conn.fetchval(
            "SELECT count(*) FROM company_actions WHERE source_company_decision_id IS NOT NULL"
        )
        snapshot = {
            "public_table_count": int(tables),
            "company_actions_columns": [r["column_name"] for r in cols],
            "candidate_4h6_event_rows": int(new_events),
            "company_decision_quality_rows": int(quality_rows),
            "company_decision_track_rows": int(track_rows),
            "company_action_outcome_rows": int(outcome_rows),
            "business_metric_observation_rows": int(observation_rows),
            "lineage_action_rows": int(lineage_rows),
        }
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2)
        print(json.dumps(snapshot, indent=2))
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
