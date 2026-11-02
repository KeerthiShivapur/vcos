"""Enable PostgreSQL Row-Level Security for tenant isolation

This migration enables RLS on all tenant-scoped tables and creates policies
that enforce organization_id isolation using the session-local
`app.current_organization_id` setting.

Categories handled:
- TENANT_SCOPED_DIRECT (640 tables): Direct organization_id column
- TENANT_SCOPED_INDIRECT (22 tables): Ownership via parent table joins
- SPECIAL_CASE_REVIEW_REQUIRED (25 tables): Mostly global reference data, no RLS
- SYSTEM_INTERNAL (1 table): alembic_version, no RLS

Revision ID: 9f3c1a7d52e5
Revises: 9f3c1a7d52e4
Create Date: 2026-10-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9f3c1a7d52e5'
down_revision: Union[str, None] = '9f3c1a7d52e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# TENANT_SCOPED_DIRECT tables (618) - all have organization_id column
TENANT_SCOPED_DIRECT = [
    "academies",
    "academy_courses",
    "academy_members",
    "access_grants",
    "access_review_items",
    "access_reviews",
    "account_teams",
    "accountability_links",
    "adaptive_planning_contexts",
    "adaptive_planning_transitions",
    "ai_actions",
    "ai_agents",
    "ai_conversations",
    "ai_feedback",
    "ai_insights",
    "ai_memories",
    "ai_messages",
    "ai_plans",
    "ai_predictions",
    "ai_recommendations",
    "ai_tenant_memory",
    "alignment_gap_detections",
    "alignment_gaps",
    "allocation_demands",
    "alumni_profiles",
    "announcement_receipts",
    "announcements",
    "api_keys",
    "approval_policies",
    "approvals",
    "assessment_attempts",
    "assessment_records",
    "assessment_reviews",
    "assessments",
    "attendance_corrections",
    "attendance_records",
    "attention_signals",
    "audit_logs",
    "authentication_policies",
    "automation_integrations",
    "autonomous_plans",
    "autonomy_contexts",
    "autonomy_eligibilities",
    "autonomy_eligibility_cache",
    "autonomy_events",
    "autonomy_executions",
    "autonomy_learnings",
    "autonomy_policies",
    "autonomy_policy_evaluations",
    "autonomy_proposals",
    "autonomy_risks",
    "background_jobs",
    "backup_manifests",
    "badges",
    "brain_conversation_turns",
    "brain_conversations",
    "budget_allocations",
    "budget_commitments",
    "budget_revisions",
    "budgets",
    "burnout_signals",
    "business_drivers",
    "business_forecasts",
    "business_intelligence_contexts",
    "business_metric_observations",
    "business_metrics",
    "business_needs",
    "business_outcomes",
    "business_performance_history",
    "business_performance_links",
    "business_performance_snapshots",
    "business_rules",
    "business_targets",
    "business_units",
    "calendar_events",
    "candidates",
    "canonical_announcement_receipts",
    "canonical_announcements",
    "canonical_assets",
    "canonical_business_processes",
    "canonical_communication_thread_members",
    "canonical_communication_threads",
    "canonical_communities",
    "canonical_community_comments",
    "canonical_community_memberships",
    "canonical_community_posts",
    "canonical_company_health",
    "canonical_decision_assessments",
    "canonical_decision_cockpit_items",
    "canonical_decision_contexts",
    "canonical_decision_options",
    "canonical_executive_briefings",
    "canonical_group_memberships",
    "canonical_group_message_reactions",
    "canonical_group_messages",
    "canonical_group_relations",
    "canonical_group_versions",
    "canonical_groups",
    "canonical_intelligence_loop_events",
    "canonical_knowledge_artifacts",
    "canonical_knowledge_claims",
    "canonical_knowledge_evidence",
    "canonical_knowledge_relations",
    "canonical_knowledge_topics",
    "canonical_messages",
    "canonical_metrics",
    "canonical_natural_language_queries",
    "canonical_observations",
    "canonical_operations",
    "canonical_procurement",
    "canonical_resources",
    "canonical_skills",
    "canonical_vendors",
    "capability_aggregates",
    "capability_history",
    "capability_project_links",
    "capability_signals",
    "capacity_allocations",
    "capacity_history",
    "capacity_snapshots",
    "career_path_steps",
    "career_paths",
    "career_progress",
    "cause_candidates",
    "certification_attempts",
    "certifications",
    "certifications_earned",
    "collaboration_evidence",
    "collaboration_metrics",
    "collaboration_org_rollups",
    "collaboration_person_rollups",
    "collaboration_relationships",
    "collaboration_signals",
    "collaboration_unit_pairs",
    "commercial_accounts",
    "commercial_intents",
    "communities",
    "community_events",
    "community_members",
    "community_posts",
    "company_action_events",
    "company_action_outcomes",
    "company_actions",
    "company_attention",
    "company_authorizations",
    "company_causal_edges",
    "company_changes",
    "company_commitments",
    "company_continuity_events",
    "company_decision_alternatives",
    "company_decision_contradictions",
    "company_decision_evidence",
    "company_decision_precedents",
    "company_decision_quality",
    "company_decision_tracks",
    "company_decisions",
    "company_goals",
    "company_health",
    "company_health_history",
    "company_health_signals",
    "company_initiatives",
    "company_insights",
    "company_intents",
    "company_knowledge_snapshots",
    "company_memory",
    "company_memory_snapshots",
    "company_objectives",
    "company_operating_continuity",
    "company_operating_health",
    "company_plan_items",
    "company_planning_contexts",
    "company_plans",
    "company_scenario_runs",
    "company_state",
    "company_state_dimensions",
    "company_state_history",
    "company_state_snapshots",
    "company_state_snapshots_g30",
    "company_state_transitions",
    "company_timeline_events",
    "compliance_controls",
    "compliance_records",
    "connector_instances",
    "continuous_learning_sessions",
    "continuous_state_projections",
    "contract_renewals",
    "contract_versions",
    "contracts",
    "conversation_members",
    "conversations",
    "coordination_handoffs",
    "coordination_history",
    "coordination_incidents",
    "correlation_contexts",
    "course_enrollments",
    "course_modules",
    "course_quizzes",
    "courses",
    "cross_domain_consistency_checks",
    "customer_addresses",
    "customer_commitments",
    "customer_contacts",
    "customer_document_links",
    "customer_health",
    "customer_health_history",
    "customer_health_rows",
    "customer_impact_analyses",
    "customer_meeting_links",
    "customer_notes",
    "customer_operating_contexts",
    "customer_operating_slices",
    "customer_outcomes",
    "customer_project_links",
    "customer_relationships",
    "customer_risks",
    "customer_signals",
    "customer_tags",
    "customer_themes",
    "customer_timeline",
    "customers",
    "daily_briefs",
    "decision_alternatives",
    "decision_audit",
    "decision_candidates",
    "decision_consequences",
    "decision_contexts",
    "decision_evidence",
    "decision_evidence_items",
    "decision_history",
    "decision_intelligence_contexts",
    "decision_intelligence_transitions",
    "decision_options",
    "decision_outcomes",
    "decision_participants",
    "decision_precedent_links",
    "decision_risk_assessments",
    "decision_simulations",
    "decision_timeline_events",
    "decisions",
    "degradations",
    "departments",
    "deployment_completeness_matrices",
    "deployment_records",
    "deployment_verification_checks",
    "digital_twins",
    "document_comments",
    "document_favorites",
    "document_presence",
    "document_versions",
    "document_watchers",
    "documents",
    "duplicate_detections",
    "economic_bottlenecks",
    "economic_cost_variances",
    "economic_counterfactual_contexts",
    "economic_impact_analyses",
    "economic_operating_slices",
    "economic_prediction_contexts",
    "economic_state_transitions",
    "employee_achievements",
    "employee_assets",
    "employee_availability",
    "employee_badges",
    "employee_certifications",
    "employee_favorites",
    "employee_presence",
    "employee_skills",
    "employee_timelines",
    "employees",
    "enterprise_users",
    "entitlements",
    "epics",
    "epistemic_calibration_events",
    "event_registrations",
    "events",
    "executive_briefings",
    "executive_insights",
    "executive_intelligence",
    "executive_recommendations",
    "executive_reports",
    "expenses",
    "expertise",
    "expertise_evidence",
    "expertise_history",
    "expertise_scores",
    "extension_installs",
    "external_capacity",
    "external_conflicts",
    "external_events",
    "external_identity_mapping_history",
    "external_identity_mappings",
    "external_knowledge_sources",
    "external_operations",
    "external_unknown_states",
    "feature_flag_audit_log",
    "feature_flag_evaluations",
    "feature_flag_history",
    "feature_flags",
    "finance_integrations",
    "financial_forecasts",
    "financial_impact_analyses",
    "financial_metrics",
    "financial_operating_slices",
    "financial_outcomes",
    "forum_replies",
    "forum_threads",
    "forum_votes",
    "forums",
    "freshness_checks",
    "future_simulator_calibrations",
    "game_sessions",
    "goal_key_results",
    "goals",
    "governance_recommendations",
    "governance_scopes",
    "graph_updates",
    "health_dimensions",
    "holidays",
    "idea_votes",
    "identity_providers",
    "impact_assessments",
    "industry_compliance_checks",
    "industry_configurations",
    "industry_metrics",
    "industry_selections",
    "industry_workflows",
    "innovation_ideas",
    "innovations",
    "insight_events",
    "institutional_memory",
    "integration_connections",
    "integration_health",
    "intent_plan_states",
    "intent_predictions",
    "interviews",
    "invitations",
    "invoices",
    "jobs",
    "knowledge_artifact_versions",
    "knowledge_categories",
    "knowledge_claim_lifecycle",
    "knowledge_claims",
    "knowledge_conflicts",
    "knowledge_context_queries",
    "knowledge_evidence",
    "knowledge_insights",
    "knowledge_intel_insight_events",
    "knowledge_intel_insights",
    "knowledge_item_tags",
    "knowledge_quality",
    "knowledge_recommendations",
    "knowledge_relations",
    "knowledge_search_index",
    "knowledge_sources",
    "knowledge_tags",
    "knowledge_topics",
    "knowledge_vectors",
    "lead_activities",
    "leads",
    "learning_cycles",
    "learning_events",
    "learning_evidence",
    "learning_history",
    "learning_path_steps",
    "learning_paths",
    "learning_profiles",
    "learning_recommendations",
    "learning_signals",
    "learning_timeline_events",
    "leave_balances",
    "leave_requests",
    "leave_types",
    "lesson_progress",
    "lesson_verification_links",
    "lessons",
    "locations",
    "longitudinal_adversarial_tests",
    "longitudinal_integrity_findings",
    "longitudinal_provenance",
    "meeting_action_items",
    "meeting_agenda_items",
    "meeting_analytics",
    "meeting_attendees",
    "meeting_captions",
    "meeting_chat_messages",
    "meeting_decisions",
    "meeting_notes",
    "meeting_participants",
    "meeting_recordings",
    "meeting_rooms",
    "meeting_sessions",
    "meeting_transcripts",
    "meeting_whiteboards",
    "meetings",
    "memory_events",
    "memory_outcomes",
    "mentor_profiles",
    "mentorship_feedback",
    "mentorship_sessions",
    "mentorships",
    "merger_acquisition_lineage",
    "message_reactions",
    "message_read_receipts",
    "messages",
    "metric_lineage",
    "metric_observations",
    "mfa_methods",
    "milestones",
    "model_twin_drifts",
    "notification_center_responses",
    "notifications",
    "objective_contradictions",
    "objective_outcome_assessments",
    "objective_outcomes",
    "objective_plan_states",
    "objective_predictions",
    "objective_simulations",
    "observability_logs",
    "offboarding_tasks",
    "offboardings",
    "offers",
    "onboarding_plans",
    "onboarding_tasks",
    "operating_insights",
    "operation_attempts",
    "operation_checkpoints",
    "operational_targets",
    "opportunities",
    "opportunity_activities",
    "optimization_contexts",
    "optimization_history",
    "optimization_records",
    "org_capabilities",
    "org_decision_history",
    "org_graph_edges",
    "org_metrics",
    "organization_context",
    "organization_edges",
    "organization_health",
    "organization_health_records",
    "organization_licenses",
    "organization_metrics",
    "organization_nodes",
    "organization_security_policies",
    "organization_settings",
    "organization_snapshots",
    "organization_timeline",
    "organizational_learning",
    "organizational_responsibilities",
    "organizational_timeline_events",
    "outcome_assessments",
    "ownership_changes",
    "ownership_relationships",
    "ownership_signals",
    "partner_contacts",
    "partner_contract_links",
    "partners",
    "password_resets",
    "path_enrollments",
    "pattern_detections",
    "pattern_events",
    "pattern_verification_links",
    "payment_provider_configs",
    "payments",
    "payroll_providers",
    "payroll_runs",
    "people_decisions",
    "people_timelines",
    "performance_cycles",
    "performance_goals",
    "performance_reviews",
    "person_identities",
    "person_memberships",
    "person_role_assignments",
    "person_skills",
    "person_workforce_extensions",
    "pinned_messages",
    "plan_adaptations",
    "plan_simulations",
    "planning_context_provenances",
    "plugins",
    "policies",
    "poll_options",
    "poll_votes",
    "polls",
    "portal_users",
    "post_bookmarks",
    "post_comments",
    "post_reactions",
    "prediction_calibrations",
    "prediction_history",
    "prediction_models",
    "predictions",
    "process_approvals",
    "process_bottlenecks",
    "process_dependencies",
    "process_executions",
    "process_impact_analyses",
    "process_knowledge",
    "process_operating_slices",
    "process_performances",
    "process_scenarios",
    "process_steps",
    "procurement_impact_analyses",
    "procurement_records",
    "project_execution_snapshots",
    "project_execution_states",
    "project_members",
    "project_timelines",
    "projects",
    "promotion_signals",
    "provisionings",
    "purchase_orders",
    "purchase_requests",
    "recognitions",
    "recommendation_items",
    "recommendation_outcomes",
    "recommendations",
    "reconciliations",
    "recoveries",
    "recovery_proposals",
    "release_failure_injections",
    "release_fingerprint_evidence",
    "release_records",
    "release_recovery_records",
    "replanning_proposals",
    "reporting_relationships",
    "resilience_plans",
    "resource_allocations",
    "resource_allocations_record",
    "resource_conflicts",
    "resource_demands",
    "resource_impact_analyses",
    "resource_operating_slices",
    "resource_requirements",
    "restore_operations",
    "risks",
    "roadmaps",
    "roles",
    "root_cause_traces",
    "scim_groups",
    "search_insights",
    "search_metrics",
    "security_audit_events",
    "security_events",
    "self_compounding_loop_states",
    "sessions",
    "shifts",
    "simulation_runs",
    "simulations",
    "skill_aliases",
    "skill_gaps",
    "skill_snapshots",
    "skills",
    "slo_targets",
    "sop_steps",
    "sops",
    "source_authorities",
    "sprints",
    "stale_operation_detections",
    "strategic_alignment_states",
    "strategic_alignments",
    "strategic_conflicts",
    "strategic_dependencies",
    "strategic_forecasts",
    "strategic_goals",
    "strategic_history",
    "strategic_links",
    "strategic_outcomes",
    "strategic_risks",
    "strategic_snapshots",
    "strategy_reports",
    "subscription_events",
    "subscriptions",
    "succession_candidates",
    "support_tickets",
    "sync_cursors",
    "sync_runs",
    "system_metrics",
    "task_attachments",
    "task_comments",
    "task_dependencies",
    "tasks",
    "team_goals",
    "team_members",
    "teams",
    "templates",
    "temporal_query_log",
    "themes",
    "ticket_knowledge_links",
    "training_completions",
    "training_requirements",
    "trusted_devices",
    "twin_contexts",
    "twin_predictions",
    "twin_scopes",
    "twin_state_history",
    "twin_state_snapshots",
    "twin_synchronization_logs",
    "universal_company_contexts",
    "universal_company_timeline",
    "universal_insights",
    "usage_aggregations",
    "usage_records",
    "user_roles",
    "users",
    "variance_analyses",
    "vendor_capabilities",
    "vendor_contracts",
    "vendor_dependencies",
    "vendor_operating_slices",
    "vendor_performance",
    "vendors",
    "verification_contexts",
    "verification_evidence",
    "virtual_office_floors",
    "virtual_office_rooms",
    "webhook_deliveries",
    "webhook_endpoints",
    "wellbeing_checks",
    "wiki_pages",
    "worker_leases",
    "workflow_actions",
    "workflow_approvals",
    "workflow_executions",
    "workflow_insights",
    "workflow_logs",
    "workflow_metrics",
    "workflow_schedules",
    "workflow_triggers",
    "workflows",
    "workforce_capability_gaps",
    "workforce_continuity_events",
    "workforce_development_needs",
    "workforce_plans",
    "workforce_snapshots",
    "workload_snapshots",
    "workspace_items",
    "workspace_sessions",
    "workspace_settings",
    "workspaces",
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


def _execute_each(conn, statements: list[str]) -> None:
    """Execute each statement separately to avoid asyncpg multi-command error."""
    for stmt in statements:
        if stmt.strip():
            conn.execute(sa.text(stmt))


def upgrade() -> None:
    conn = op.get_bind()

    # ============================================================
    # 1. Create helper functions for tenant context
    # ============================================================

    # Function to get current organization_id from session setting
    # Returns hex without hyphens (32 chars) to match organization_id column format
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION public.current_organization_id()
        RETURNS text LANGUAGE sql STABLE AS $$
            SELECT replace(NULLIF(current_setting('app.current_organization_id', true), ''), '-', '')
        $$;
    """))

    # Function to set current organization_id (for middleware use)
    # Accepts UUID or hex string, stores as-is
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION public.set_current_organization_id(org_id text)
        RETURNS void LANGUAGE sql AS $$
            SELECT set_config('app.current_organization_id', org_id, false);
        $$;
    """))

    # Function to clear organization_id
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION public.clear_current_organization_id()
        RETURNS void LANGUAGE sql AS $$
            SELECT set_config('app.current_organization_id', '', false);
        $$;
    """))

    # ============================================================
    # 2. Enable RLS and create policies for TENANT_SCOPED_DIRECT tables
    # ============================================================

    for table in TENANT_SCOPED_DIRECT:
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

    # ============================================================
    # 3. Handle TENANT_SCOPED_INDIRECT tables with custom join policies
    # ============================================================

    def _enable_rls_and_policies(table: str, select_using: str, insert_check: str, update_using: str, delete_using: str):
        """Helper to enable RLS and create all 4 policies for a table."""
        conn.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        conn.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))

        conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_select" ON "{table}"'))
        conn.execute(sa.text(f'CREATE POLICY "{table}_tenant_select" ON "{table}" FOR SELECT USING ({select_using})'))

        conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_insert" ON "{table}"'))
        conn.execute(sa.text(f'CREATE POLICY "{table}_tenant_insert" ON "{table}" FOR INSERT WITH CHECK ({insert_check})'))

        conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_update" ON "{table}"'))
        conn.execute(sa.text(f'CREATE POLICY "{table}_tenant_update" ON "{table}" FOR UPDATE USING ({update_using}) WITH CHECK ({insert_check})'))

        conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_delete" ON "{table}"'))
        conn.execute(sa.text(f'CREATE POLICY "{table}_tenant_delete" ON "{table}" FOR DELETE USING ({delete_using})'))

    # backup_corruption_tests: backup_id -> backup_manifests
    for table in ["backup_corruption_tests", "backup_verification_results"]:
        if conn.execute(sa.text(_table_has_column(table, "backup_id"))).scalar():
            _enable_rls_and_policies(
                table,
                "backup_id IN (SELECT id FROM backup_manifests WHERE organization_id = public.current_organization_id())",
                "backup_id IN (SELECT id FROM backup_manifests WHERE organization_id = public.current_organization_id())",
                "backup_id IN (SELECT id FROM backup_manifests WHERE organization_id = public.current_organization_id())",
                "backup_id IN (SELECT id FROM backup_manifests WHERE organization_id = public.current_organization_id())",
            )

    # deployment_completeness_dimensions: matrix_id -> deployment_completeness_matrices
    if conn.execute(sa.text(_table_has_column("deployment_completeness_dimensions", "matrix_id"))).scalar():
        _enable_rls_and_policies(
            "deployment_completeness_dimensions",
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
                table,
                "developer_id IN (SELECT d.id FROM developers d JOIN users u ON d.user_id = u.id WHERE u.organization_id = public.current_organization_id())",
                "developer_id IN (SELECT d.id FROM developers d JOIN users u ON d.user_id = u.id WHERE u.organization_id = public.current_organization_id())",
                "developer_id IN (SELECT d.id FROM developers d JOIN users u ON d.user_id = u.id WHERE u.organization_id = public.current_organization_id())",
                "developer_id IN (SELECT d.id FROM developers d JOIN users u ON d.user_id = u.id WHERE u.organization_id = public.current_organization_id())",
            )

    # developers: user_id -> users
    if conn.execute(sa.text(_table_has_column("developers", "user_id"))).scalar():
        _enable_rls_and_policies(
            "developers",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
        )

    # devices: user_id -> users
    if conn.execute(sa.text(_table_has_column("devices", "user_id"))).scalar():
        _enable_rls_and_policies(
            "devices",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
        )

    # industry_templates: created_by -> users
    if conn.execute(sa.text(_table_has_column("industry_templates", "created_by"))).scalar():
        _enable_rls_and_policies(
            "industry_templates",
            "created_by IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "created_by IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "created_by IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "created_by IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
        )

    # marketplace_reviews: user_id -> users
    if conn.execute(sa.text(_table_has_column("marketplace_reviews", "user_id"))).scalar():
        _enable_rls_and_policies(
            "marketplace_reviews",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
            "user_id IN (SELECT id FROM users WHERE organization_id = public.current_organization_id())",
        )

    # optimization_alternatives: context_id -> optimization_contexts
    if conn.execute(sa.text(_table_has_column("optimization_alternatives", "context_id"))).scalar():
        _enable_rls_and_policies(
            "optimization_alternatives",
            "context_id IN (SELECT id FROM optimization_contexts WHERE organization_id = public.current_organization_id())",
            "context_id IN (SELECT id FROM optimization_contexts WHERE organization_id = public.current_organization_id())",
            "context_id IN (SELECT id FROM optimization_contexts WHERE organization_id = public.current_organization_id())",
            "context_id IN (SELECT id FROM optimization_contexts WHERE organization_id = public.current_organization_id())",
        )

    # plugin_versions: plugin_id -> plugins
    if conn.execute(sa.text(_table_has_column("plugin_versions", "plugin_id"))).scalar():
        _enable_rls_and_policies(
            "plugin_versions",
            "plugin_id IN (SELECT id FROM plugins WHERE organization_id = public.current_organization_id())",
            "plugin_id IN (SELECT id FROM plugins WHERE organization_id = public.current_organization_id())",
            "plugin_id IN (SELECT id FROM plugins WHERE organization_id = public.current_organization_id())",
            "plugin_id IN (SELECT id FROM plugins WHERE organization_id = public.current_organization_id())",
        )

    # provisioning_steps: provisioning_id -> provisionings
    if conn.execute(sa.text(_table_has_column("provisioning_steps", "provisioning_id"))).scalar():
        _enable_rls_and_policies(
            "provisioning_steps",
            "provisioning_id IN (SELECT id FROM provisionings WHERE organization_id = public.current_organization_id())",
            "provisioning_id IN (SELECT id FROM provisionings WHERE organization_id = public.current_organization_id())",
            "provisioning_id IN (SELECT id FROM provisionings WHERE organization_id = public.current_organization_id())",
            "provisioning_id IN (SELECT id FROM provisionings WHERE organization_id = public.current_organization_id())",
        )

    # role_permissions: role_id -> roles
    if conn.execute(sa.text(_table_has_column("role_permissions", "role_id"))).scalar():
        _enable_rls_and_policies(
            "role_permissions",
            "role_id IN (SELECT id FROM roles WHERE organization_id = public.current_organization_id())",
            "role_id IN (SELECT id FROM roles WHERE organization_id = public.current_organization_id())",
            "role_id IN (SELECT id FROM roles WHERE organization_id = public.current_organization_id())",
            "role_id IN (SELECT id FROM roles WHERE organization_id = public.current_organization_id())",
        )

    # subscription_invoices: invoice_id -> invoices
    if conn.execute(sa.text(_table_has_column("subscription_invoices", "invoice_id"))).scalar():
        _enable_rls_and_policies(
            "subscription_invoices",
            "invoice_id IN (SELECT id FROM invoices WHERE organization_id = public.current_organization_id())",
            "invoice_id IN (SELECT id FROM invoices WHERE organization_id = public.current_organization_id())",
            "invoice_id IN (SELECT id FROM invoices WHERE organization_id = public.current_organization_id())",
            "invoice_id IN (SELECT id FROM invoices WHERE organization_id = public.current_organization_id())",
        )

    # subscription_payments: payment_id -> payments
    if conn.execute(sa.text(_table_has_column("subscription_payments", "payment_id"))).scalar():
        _enable_rls_and_policies(
            "subscription_payments",
            "payment_id IN (SELECT id FROM payments WHERE organization_id = public.current_organization_id())",
            "payment_id IN (SELECT id FROM payments WHERE organization_id = public.current_organization_id())",
            "payment_id IN (SELECT id FROM payments WHERE organization_id = public.current_organization_id())",
            "payment_id IN (SELECT id FROM payments WHERE organization_id = public.current_organization_id())",
        )

    # workflow_* tables: workflow_id -> workflows
    for table in ["workflow_edges", "workflow_nodes", "workflow_versions"]:
        if conn.execute(sa.text(_table_has_column(table, "workflow_id"))).scalar():
            _enable_rls_and_policies(
                table,
                "workflow_id IN (SELECT id FROM workflows WHERE organization_id = public.current_organization_id())",
                "workflow_id IN (SELECT id FROM workflows WHERE organization_id = public.current_organization_id())",
                "workflow_id IN (SELECT id FROM workflows WHERE organization_id = public.current_organization_id())",
                "workflow_id IN (SELECT id FROM workflows WHERE organization_id = public.current_organization_id())",
            )

    # workflow_execution_steps: execution_id -> workflow_executions
    if conn.execute(sa.text(_table_has_column("workflow_execution_steps", "execution_id"))).scalar():
        _enable_rls_and_policies(
            "workflow_execution_steps",
            "execution_id IN (SELECT id FROM workflow_executions WHERE organization_id = public.current_organization_id())",
            "execution_id IN (SELECT id FROM workflow_executions WHERE organization_id = public.current_organization_id())",
            "execution_id IN (SELECT id FROM workflow_executions WHERE organization_id = public.current_organization_id())",
            "execution_id IN (SELECT id FROM workflow_executions WHERE organization_id = public.current_organization_id())",
        )

    print("RLS migration completed for all tenant-scoped tables")


def downgrade() -> None:
    conn = op.get_bind()

    # Drop all policies and disable RLS for DIRECT tables
    for table in TENANT_SCOPED_DIRECT:
        for policy_suffix in ["_tenant_select", "_tenant_insert", "_tenant_update", "_tenant_delete"]:
            conn.execute(sa.text(f'DROP POLICY IF EXISTS "{table}{policy_suffix}" ON "{table}"'))
        conn.execute(sa.text(f'ALTER TABLE IF EXISTS "{table}" DISABLE ROW LEVEL SECURITY'))

    # Drop policies for INDIRECT tables
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

    # Drop helper functions
    conn.execute(sa.text("DROP FUNCTION IF EXISTS public.current_organization_id()"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS public.set_current_organization_id(text)"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS public.clear_current_organization_id()"))