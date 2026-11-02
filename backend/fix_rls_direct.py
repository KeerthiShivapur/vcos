from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def fix_rls():
    async with SessionLocal() as db:
        # Drop function with cascade
        await db.execute(text("DROP FUNCTION IF EXISTS public.current_organization_id() CASCADE"))
        await db.execute(text("DROP FUNCTION IF EXISTS public.set_current_organization_id(text) CASCADE"))
        await db.execute(text("DROP FUNCTION IF EXISTS public.clear_current_organization_id() CASCADE"))
        await db.commit()
        
        # Create function returning text (hex without hyphens)
        await db.execute(text("""
            CREATE FUNCTION public.current_organization_id()
            RETURNS text LANGUAGE sql STABLE AS $$
                SELECT replace(NULLIF(current_setting('app.current_organization_id', true), ''), '-', '')
            $$;
        """))
        
        await db.execute(text("""
            CREATE FUNCTION public.set_current_organization_id(org_id text)
            RETURNS void LANGUAGE sql AS $$
                SELECT set_config('app.current_organization_id', org_id, false);
            $$;
        """))
        
        await db.execute(text("""
            CREATE FUNCTION public.clear_current_organization_id()
            RETURNS void LANGUAGE sql AS $$
                SELECT set_config('app.current_organization_id', '', false);
            $$;
        """))
        await db.commit()
        
        # Recreate policies for core tables
        core_tables = [
            "employees", "projects", "tasks", "users", "departments", "teams",
            "roles", "organizations", "meetings", "documents", "decisions",
            "approvals", "risks", "goals", "events", "messages", "conversations",
            "notifications", "announcements", "posts", "comments", "wiki_pages",
            "calendar_events", "meeting_rooms", "meeting_sessions", "meeting_notes",
            "meeting_transcripts", "meeting_captions", "meeting_whiteboards",
            "meeting_recordings", "meeting_action_items", "meeting_agenda_items",
            "meeting_participants", "leave_requests", "leave_balances", "leave_types",
            "attendance_records", "attendance_corrections", "certifications",
            "certifications_earned", "skills", "employee_skills", "certification_attempts",
            "career_paths", "career_path_steps", "career_progress", "learning_paths",
            "learning_path_steps", "course_enrollments", "courses", "course_modules",
            "course_quizzes", "training_completions", "training_requirements",
            "performance_reviews", "performance_goals", "performance_cycles",
            "devices", "api_keys", "developer_api_keys", "developer_applications",
            "developer_certifications", "developer_subscriptions", "developer_usage",
            "developers", "marketplace_reviews", "marketplace_items", "extension_installs",
            "plugins", "plugin_versions", "feature_flags", "feature_flag_evaluations",
            "feature_flag_history", "feature_flag_audit_log", "observability_logs",
            "canonical_observations", "correlation_contexts", "degradations",
            "slo_targets", "health_metrics", "security_events", "security_audit_events",
            "alerts", "incident_responses", "incident_timeline_events"
        ]
        
        for table in core_tables:
            # Check if table has organization_id column
            has_org_id = await db.execute(text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = '{table}'
                    AND column_name = 'organization_id'
                )
            """))
            has_org_id = has_org_id.scalar()
            
            if not has_org_id:
                continue
            
            # Drop and recreate policies
            for cmd, policy_name in [
                ("SELECT", f"{table}_tenant_select"),
                ("INSERT", f"{table}_tenant_insert"),
                ("UPDATE", f"{table}_tenant_update"),
                ("DELETE", f"{table}_tenant_delete"),
            ]:
                await db.execute(text(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table}"'))
            
            # Create SELECT policy
            await db.execute(text(f"""
                CREATE POLICY "{table}_tenant_select" ON "{table}"
                FOR SELECT USING (
                    organization_id = public.current_organization_id()
                )
            """))
            
            # Create INSERT policy
            await db.execute(text(f"""
                CREATE POLICY "{table}_tenant_insert" ON "{table}"
                FOR INSERT WITH CHECK (
                    organization_id = public.current_organization_id()
                )
            """))
            
            # Create UPDATE policy
            await db.execute(text(f"""
                CREATE POLICY "{table}_tenant_update" ON "{table}"
                FOR UPDATE USING (
                    organization_id = public.current_organization_id()
                ) WITH CHECK (
                    organization_id = public.current_organization_id()
                )
            """))
            
            # Create DELETE policy
            await db.execute(text(f"""
                CREATE POLICY "{table}_tenant_delete" ON "{table}"
                FOR DELETE USING (
                    organization_id = public.current_organization_id()
                )
            """))
        
        await db.commit()
        print("RLS fix completed!")

asyncio.run(fix_rls())