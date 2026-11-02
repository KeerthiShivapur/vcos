# RLS Tenant Inventory - Summary

Generated: 2026-10-17T12:38:08.440859+00:00
Database: postgresql+asyncpg://postgres:***@localhost:5432/vcos4 (schema: public)
Tables scanned: 688

## Category counts

| Category | Tables |
|---|---|
| TENANT_SCOPED_DIRECT | 640 |
| TENANT_SCOPED_INDIRECT | 22 |
| GLOBAL_REFERENCE | 0 |
| SYSTEM_INTERNAL | 1 |
| DERIVED_OR_REBUILDABLE | 0 |
| SPECIAL_CASE_REVIEW_REQUIRED | 25 |

- Row-level security currently enabled on **0** tables.
- Tenant-scoped tables (direct or indirect) missing RLS: **662**.
- Review queue (SPECIAL_CASE_REVIEW_REQUIRED): **25** tables.
- Deepest indirect ownership path: 2.

## Classification rules

- DIRECT: has an `organization_id` / `org_id` / `tenant_id` column (structural fact).
- INDIRECT: reachable from a direct table via foreign keys (path recorded; max depth 4).
- GLOBAL_REFERENCE / DERIVED_OR_REBUILDABLE: only via explicit allowlist arguments - never inferred from names.
- SYSTEM_INTERNAL: alembic/system tables and non-public schemas.
- SPECIAL_CASE_REVIEW_REQUIRED: no structural ownership evidence; manual review required. No guessing.

## Scoped tables missing RLS (first 20)

- academies
- academy_courses
- academy_members
- access_grants
- access_review_items
- access_reviews
- account_teams
- accountability_links
- adaptive_planning_contexts
- adaptive_planning_transitions
- ai_actions
- ai_agents
- ai_conversations
- ai_feedback
- ai_insights
- ai_memories
- ai_messages
- ai_plans
- ai_predictions
- ai_recommendations

## Review queue sample (first 20 of SPECIAL_CASE)

- autoscaling_events
- backup_history
- chaos_runs
- cloud_regions
- cluster_status
- connector_capabilities
- connectors
- deployment_history
- disaster_recovery_logs
- failure_taxonomy
- health_metrics
- industries
- industry_ai_models
- industry_modules
- industry_policies
- marketplace_items
- organizations
- permissions
- plans
- pricing_rule_versions
