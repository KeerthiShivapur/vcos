from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def grant_permissions():
    async with SessionLocal() as db:
        tables = [
            "organizations", "users", "employees", "projects", "tasks",
            "departments", "teams", "roles", "meetings", "documents",
            "decisions", "approvals", "risks", "goals", "events",
            "messages", "conversations", "notifications", "announcements",
            "posts", "comments", "wiki_pages", "calendar_events",
            "meeting_rooms", "meeting_sessions", "meeting_notes",
            "meeting_transcripts", "meeting_captions", "meeting_whiteboards",
            "meeting_recordings", "meeting_action_items", "meeting_agenda_items",
            "meeting_participants", "leave_requests", "leave_balances",
            "leave_types", "attendance_records", "attendance_corrections",
            "certifications", "certifications_earned", "skills",
            "employee_skills", "certification_attempts", "career_paths",
            "career_path_steps", "career_progress", "learning_paths",
            "learning_path_steps", "course_enrollments", "courses",
            "course_modules", "course_quizzes", "training_completions",
            "training_requirements", "performance_reviews", "performance_goals",
            "performance_cycles", "devices", "api_keys", "developer_api_keys",
            "developer_applications", "developer_certifications",
            "developer_subscriptions", "developer_usage", "developers",
            "marketplace_reviews", "marketplace_items", "extension_installs",
            "plugins", "plugin_versions", "feature_flags",
            "feature_flag_evaluations", "feature_flag_history",
            "feature_flag_audit_log", "observability_logs",
            "canonical_observations", "correlation_contexts", "degradations",
            "slo_targets", "health_metrics", "security_events",
            "security_audit_events", "alerts", "incident_responses",
            "incident_timeline_events"
        ]
        
        for table in tables:
            try:
                async with SessionLocal() as db2:
                    await db2.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO vcos"))
                    await db2.commit()
                print(f"Granted permissions on {table}")
            except Exception as e:
                print(f"Failed to grant on {table}: {e}")
        
        # Grant usage on sequences
        try:
            async with SessionLocal() as db2:
                await db2.execute(text("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO vcos"))
                await db2.commit()
            print("Granted sequence usage")
        except Exception as e:
            print(f"Failed to grant sequence usage: {e}")
        
        print("Permissions granted!")

asyncio.run(grant_permissions())