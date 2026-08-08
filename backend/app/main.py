"""VCOS backend entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.core.config import get_settings
from app.core.middleware import RequestContextMiddleware
from app.db.database import dispose_engine, init_db

logger = logging.getLogger("vcos")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("VCOS backend starting (env=%s)", settings.APP_ENV)
    await init_db()
    from app.services.permission_service import permission_service
    from app.db.database import SessionLocal

    async with SessionLocal() as db:
        await permission_service.sync_catalog(db)
        await permission_service.sync_role_permissions(db)
        await db.commit()
    if settings.APP_ENV != "test":
        from app.workers.scheduler import start_scheduler, stop_scheduler

        scheduler_tasks = start_scheduler()
        logger.info("VCOS background workers running")
    else:
        scheduler_tasks = []
    logger.info("VCOS backend ready")
    try:
        yield
    finally:
        if scheduler_tasks:
            from app.workers.scheduler import stop_scheduler

            stop_scheduler(scheduler_tasks)
    await dispose_engine()
    logger.info("VCOS backend stopped")


app = FastAPI(
    title="VCOS API — Virtual Company Operating System",
    description=(
        "The operating system for virtual companies. One identity, one organization graph, "
        "one permission model, one event stream. Phase 3: Work Execution Engine — projects, "
        "tasks, goals, meetings, calendar, approvals, risks, workload, AI Companion and "
        "background intelligence workers."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.v1 import (  # noqa: E402
    academy,
    accounts,
    agents,
    ai,
    ai_actions,
    ai_memory,
    ai_predictions,
    ai_planning,
    ai_recommendations,
    ai_search,
    ai_voice,
    analytics,
    announcements,
    approvals,
    assessments,
    assets,
    attendance,
    audit,
    auth,
    autonomy,
    automation,
    calendar,
    career,
    certifications,
    communities,
    community_events,
    collaboration_intel,
    collaboration_live,
    compliance,
    contracts,
    contacts,
    courses,
    customers,
    dashboard,
    decisions,
    departments,
    developers,
    digital_twin,
    documents,
    employees,
    enterprise,
    events,
    exec_health,
    exec_predictions,
    exec_recommendations,
    exec_reports,
    exec_risks,
    exec_simulations,
    exec_strategy,
    executive,
    expertise,
    extensions,
    finance,
    forums,
    goals,
    health,
    hr,
    infrastructure,
    innovation,
    industry,
    insights,
    intelligence,
    intelligence_briefs,
    knowledge,
    leads,
    learning,
    learning_paths,
    leave,
    live,
    meeting_intel,
    meeting_rooms,
    meetings,
    memory,
    mentorship,
    messaging,
    notifications,
    offboarding,
    onboarding,
    opportunities,
    organization,
    organizations,
    partners,
    payroll,
    performance,
    policies,
    polls,
    portal,
    posts,
    prediction,
    presence,
    projects,
    recognition,
    recording_library,
    recordings,
    recommendations,
    recruitment,
    risks,
    roles,
    search,
    skills,
    sops,
    support,
    tasks,
    teams,
    templates,
    users,
    wellbeing,
    webhooks,
    wiki,
    workforce,
    workload,
    workspace,
    network,
    brain,
)

API_PREFIX = settings.API_V1_PREFIX
app.include_router(health.router)
app.include_router(health.platform_router, prefix=API_PREFIX)
app.include_router(ai.router, prefix=API_PREFIX)
app.include_router(ai_actions.router, prefix=API_PREFIX)
app.include_router(ai_memory.router, prefix=API_PREFIX)
app.include_router(ai_predictions.router, prefix=API_PREFIX)
app.include_router(ai_planning.router, prefix=API_PREFIX)
app.include_router(ai_recommendations.router, prefix=API_PREFIX)
app.include_router(ai_search.router, prefix=API_PREFIX)
app.include_router(ai_voice.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(organizations.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(roles.router, prefix=API_PREFIX)
app.include_router(notifications.router, prefix=API_PREFIX)
app.include_router(workspace.router, prefix=API_PREFIX)
app.include_router(audit.router, prefix=API_PREFIX)
app.include_router(events.router, prefix=API_PREFIX)
app.include_router(search.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(employees.router, prefix=API_PREFIX)
app.include_router(departments.router, prefix=API_PREFIX)
app.include_router(teams.router, prefix=API_PREFIX)
app.include_router(organization.router, prefix=API_PREFIX)
app.include_router(expertise.router, prefix=API_PREFIX)
app.include_router(presence.router, prefix=API_PREFIX)
app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(tasks.router, prefix=API_PREFIX)
app.include_router(goals.router, prefix=API_PREFIX)
app.include_router(calendar.router, prefix=API_PREFIX)
app.include_router(meeting_rooms.router, prefix=API_PREFIX)
app.include_router(approvals.router, prefix=API_PREFIX)
app.include_router(risks.router, prefix=API_PREFIX)
app.include_router(workload.router, prefix=API_PREFIX)
app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(wiki.router, prefix=API_PREFIX)
app.include_router(policies.router, prefix=API_PREFIX)
app.include_router(sops.router, prefix=API_PREFIX)
app.include_router(templates.router, prefix=API_PREFIX)
app.include_router(decisions.router, prefix=API_PREFIX)
app.include_router(knowledge.router, prefix=API_PREFIX)
app.include_router(communities.router, prefix=API_PREFIX)
app.include_router(posts.router, prefix=API_PREFIX)
app.include_router(announcements.router, prefix=API_PREFIX)
app.include_router(forums.router, prefix=API_PREFIX)
app.include_router(recognition.router, prefix=API_PREFIX)
app.include_router(innovation.router, prefix=API_PREFIX)
app.include_router(polls.router, prefix=API_PREFIX)
app.include_router(community_events.router, prefix=API_PREFIX)
app.include_router(messaging.router, prefix=API_PREFIX)
app.include_router(collaboration_live.router, prefix=API_PREFIX)
app.include_router(live.router)
app.include_router(meeting_intel.router, prefix=API_PREFIX)
app.include_router(recording_library.router, prefix=API_PREFIX)
app.include_router(meetings.router, prefix=API_PREFIX)
app.include_router(recordings.router, prefix=API_PREFIX)
app.include_router(executive.router, prefix=API_PREFIX)
app.include_router(exec_health.router, prefix=API_PREFIX)
app.include_router(exec_risks.router, prefix=API_PREFIX)
app.include_router(exec_recommendations.router, prefix=API_PREFIX)
app.include_router(exec_predictions.router, prefix=API_PREFIX)
app.include_router(exec_simulations.router, prefix=API_PREFIX)
app.include_router(exec_reports.router, prefix=API_PREFIX)
app.include_router(exec_strategy.router, prefix=API_PREFIX)
app.include_router(intelligence.router, prefix=API_PREFIX)
app.include_router(collaboration_intel.router, prefix=API_PREFIX)
app.include_router(intelligence_briefs.router, prefix=API_PREFIX)
app.include_router(recommendations.router, prefix=API_PREFIX)
app.include_router(insights.router, prefix=API_PREFIX)
app.include_router(learning.router, prefix=API_PREFIX)
app.include_router(courses.router, prefix=API_PREFIX)
app.include_router(learning_paths.router, prefix=API_PREFIX)
app.include_router(skills.router, prefix=API_PREFIX)
app.include_router(assessments.router, prefix=API_PREFIX)
app.include_router(mentorship.router, prefix=API_PREFIX)
app.include_router(certifications.router, prefix=API_PREFIX)
app.include_router(career.router, prefix=API_PREFIX)
app.include_router(academy.router, prefix=API_PREFIX)
app.include_router(onboarding.router, prefix=API_PREFIX)
app.include_router(attendance.router, prefix=API_PREFIX)
app.include_router(leave.router, prefix=API_PREFIX)
app.include_router(hr.router, prefix=API_PREFIX)
app.include_router(recruitment.router, prefix=API_PREFIX)
app.include_router(performance.router, prefix=API_PREFIX)
app.include_router(assets.router, prefix=API_PREFIX)
app.include_router(offboarding.router, prefix=API_PREFIX)
app.include_router(compliance.router, prefix=API_PREFIX)
app.include_router(workforce.router, prefix=API_PREFIX)
app.include_router(wellbeing.router, prefix=API_PREFIX)
app.include_router(payroll.router, prefix=API_PREFIX)
app.include_router(customers.router, prefix=API_PREFIX)
app.include_router(contacts.router, prefix=API_PREFIX)
app.include_router(leads.router, prefix=API_PREFIX)
app.include_router(opportunities.router, prefix=API_PREFIX)
app.include_router(contracts.router, prefix=API_PREFIX)
app.include_router(support.router, prefix=API_PREFIX)
app.include_router(partners.router, prefix=API_PREFIX)
app.include_router(accounts.router, prefix=API_PREFIX)
app.include_router(portal.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(finance.router, prefix=API_PREFIX)
app.include_router(automation.router, prefix=API_PREFIX)
app.include_router(enterprise.router, prefix=API_PREFIX)
app.include_router(infrastructure.router, prefix=API_PREFIX)
app.include_router(industry.router, prefix=API_PREFIX)
app.include_router(digital_twin.router, prefix=API_PREFIX)
app.include_router(developers.router, prefix=API_PREFIX)
app.include_router(agents.router, prefix=API_PREFIX)
app.include_router(webhooks.router, prefix=API_PREFIX)
app.include_router(extensions.router, prefix=API_PREFIX)
app.include_router(extensions.theme_router, prefix=API_PREFIX)
app.include_router(memory.memory_router, prefix=API_PREFIX)
app.include_router(memory.timeline_router, prefix=API_PREFIX)
app.include_router(memory.context_router, prefix=API_PREFIX)

# Phase 19 — Autonomous Enterprise & Intelligence Network
app.include_router(autonomy.autonomy_router, prefix=API_PREFIX)
app.include_router(autonomy.briefing_router, prefix=API_PREFIX)
app.include_router(autonomy.decision_router, prefix=API_PREFIX)
app.include_router(prediction.router, prefix=API_PREFIX)
app.include_router(network.router, prefix=API_PREFIX)

# Phase 20 — Universal Organizational Intelligence Network (Company Brain)
app.include_router(brain.router, prefix=API_PREFIX)

# Phase 17 — industry pack routers (one generated surface per vertical).
from app.industry.api import INDUSTRY_ROUTERS  # noqa: E402

for _industry_router in INDUSTRY_ROUTERS.values():
    app.include_router(_industry_router, prefix=API_PREFIX)


@app.get("/")
async def root():
    return {
        "service": "VCOS API",
        "version": "1.0.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
    }


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema["x-vcos"] = {
        "phase": 20,
        "name": "Universal Organizational Intelligence Network — The Living Company Operating System",
        "capabilities": [
            "authentication",
            "organizations",
            "multi-tenancy",
            "rbac",
            "sessions",
            "notifications",
            "audit",
            "events",
            "workspace",
            "search",
            "ai-gateway",
            "employees",
            "departments",
            "teams",
            "org-chart",
            "expertise",
            "presence",
            "intelligence",
            "projects",
            "tasks",
            "goals",
            "meetings",
            "calendar",
            "meeting-rooms",
            "meeting-sessions",
            "meeting-notes",
            "live-presence",
            "live-websocket",
            "meeting-chat",
            "meeting-whiteboard",
            "screen-share",
            "rtc-signaling",
            "reactions",
            "meeting-recordings",
            "meeting-transcript",
            "meeting-captions",
            "live-translation",
            "ai-meeting-intelligence",
            "attendance-intelligence",
            "meeting-analytics",
            "calendar-intelligence",
            "action-items-to-tasks",
            "approvals",
            "risks",
            "workload",
            "ai-companion",
            "background-workers",
            "industry-solutions",
            "industry-packs",
            "company-brain",
            "universal-search",
            "living-graph",
            "company-memory",
            "company-timeline",
            "universal-context",
            "company-health",
            "event-bus",
            "continuous-evolution",
        ],
    }
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
