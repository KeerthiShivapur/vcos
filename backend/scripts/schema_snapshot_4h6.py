"""Phase E reference snapshot - the pre-4H.6 schema state 4H.6 must preserve.

Records: table count, company_actions column set, event rows for candidate
4H.6 event names (must stay 0), decision quality/track row counts.
Run again after implementation; any delta beyond the ratified diff is a gate
failure.
"""

import asyncio
import json
import sys

import asyncpg


async def main() -> int:
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
        col_names = [r["column_name"] for r in cols]
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
            "company_actions_columns": col_names,
            "candidate_4h6_event_rows": int(new_events),
            "company_decision_quality_rows": int(quality_rows),
            "company_decision_track_rows": int(track_rows),
            "company_action_outcome_rows": int(outcome_rows),
            "business_metric_observation_rows": int(observation_rows),
            "lineage_action_rows": int(lineage_rows),
        }
        print(json.dumps(snapshot, indent=2))
        with open("../SLICE4H6_SCHEMA_BASELINE.json", "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2)
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
