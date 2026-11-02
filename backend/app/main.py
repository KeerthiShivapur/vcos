import sys
import importlib.util
from pathlib import Path

# Load all models first to ensure they're registered with SQLAlchemy metadata
# This must happen before any service/api imports that might reference models
def _load_all_models():
    """Load all model modules to register them with SQLAlchemy metadata.
    
    This imports model modules directly from their file paths to avoid
    circular import issues with app.models.__init__.
    """
    print("DEBUG: _load_all_models called", file=sys.stderr)
    _models_dir = Path(__file__).parent / "models"
    print(f"DEBUG: models dir = {_models_dir}", file=sys.stderr)
    print(f"DEBUG: models dir exists = {_models_dir.exists()}", file=sys.stderr)
    
    _model_submodules = [
        "organization",
        "user",
        "role",
        "notification",
        "workspace",
        "ai",
        "invitation",
        "employee",
        "department",
        "team",
        "skill",
        "project",
        "task",
        "goal",
        "meeting",
        "calendar",
        "collaboration",
        "approval",
        "governance",
        "workload",
        "knowledge",
        "communication",
        "executive",
        "autonomy",
        "continuous_twin",
        "canonical_reliability",
        "observability",
        "workflow",
        "enterprise",
        "feature_flags",
        "infrastructure",
        "deployment_completeness",
        "backup_manifest",
        "release",
        "industry",
        "industry_module",
        "industry_template",
        "industry_policy",
        "industry_configuration",
        "digital_twin",
        "developer",
        "company_state",
        "autonomous_plan",
        "briefing",
        "company_memory",
        "decision_history",
        "innovation",
        "learning_cycle",
        "optimization",
        "organization_edge",
        "organization_health",
        "organization_node",
        "prediction",
        "recommendation",
        "simulation",
        "strategy_report",
        "executive_intelligence",
        "ai_governance",
        "resilience_plan",
        "brain",
        "company_actions",
        "organizational_learning",
        "people_intelligence",
        "skills_intelligence",
        "ownership_intelligence",
        "collaboration_intelligence",
        "org_capability_intelligence",
        "people_decision",
        "execution_intelligence",
        "execution_coordination",
        "execution_strategy",
        "resource_allocation_intelligence",
        "customer_intelligence",
        "business_commercial",
        "business_performance",
        "financial_resource_procurement",
        "canonical_resource_asset",
        "canonical_procurement_vendor",
        "canonical_economic_intelligence",
        "canonical_business_process",
        "canonical_knowledge",
        "canonical_communication_collaboration",
        "canonical_business_intelligence",
        "canonical_workforce",
        "canonical_integration",
        "company_operating",
        "company_intent",
        "canonical_company_continuity",
        "longitudinal",
        "learning_profile",
        "course",
        "learning_path",
        "skill_gap",
        "certification",
        "assessment",
        "academy",
        "mentorship",
        "career",
        "onboarding",
        "learning_recommendation",
        "hr",
        "customer",
        "lead",
        "contract",
        "ticket",
        "partner",
        "portal",
        "finance",
        "adaptive_operating_profile",
        "company_experience",
    ]
    
    for submodule in _model_submodules:
        module_name = f"app.models.{submodule}"
        if module_name not in sys.modules:
            module_path = Path(__file__).parent / "models" / f"{submodule}.py"
            if module_path.exists():
                print(f"DEBUG: Loading {module_name} from {module_path}", file=sys.stderr)
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    print(f"DEBUG: Loaded {module_name} successfully", file=sys.stderr)
            else:
                print(f"DEBUG: Module path not found: {module_path}", file=sys.stderr)
        else:
            print(f"DEBUG: {module_name} already in sys.modules", file=sys.stderr)


# Load all models first to register them with SQLAlchemy metadata
# This must happen before any service/api imports that might reference models
# _load_all_models()  # Disabled - causes double-loading, normal imports handle it

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from prometheus_client import generate_latest
import logging

from app.api.v1 import router as api_router
from app.core.config import settings
from app.core.observability import init_observability
from app.core.realtime import add_realtime_to_app
from app.db.database import init_db
from app.services.realtime_init import (
    initialize_realtime_services,
    shutdown_realtime_services,
    get_realtime_health,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_observability(app)
    await init_db()
    
    # Initialize real-time collaboration services
    try:
        realtime_results = await initialize_realtime_services(
            redis_url=settings.REDIS_URL if hasattr(settings, "REDIS_URL") else None,
            livekit_url=settings.LIVEKIT_URL if hasattr(settings, "LIVEKIT_URL") else None,
            livekit_api_key=settings.LIVEKIT_API_KEY if hasattr(settings, "LIVEKIT_API_KEY") else None,
            livekit_api_secret=settings.LIVEKIT_API_SECRET if hasattr(settings, "LIVEKIT_API_SECRET") else None,
            vapid_subject=settings.VAPID_SUBJECT if hasattr(settings, "VAPID_SUBJECT") else "mailto:admin@vcos.io",
            fcm_server_key=settings.FCM_SERVER_KEY if hasattr(settings, "FCM_SERVER_KEY") else None,
            fcm_project_id=settings.FCM_PROJECT_ID if hasattr(settings, "FCM_PROJECT_ID") else None,
            apns_team_id=settings.APNS_TEAM_ID if hasattr(settings, "APNS_TEAM_ID") else None,
            apns_key_id=settings.APNS_KEY_ID if hasattr(settings, "APNS_KEY_ID") else None,
            apns_bundle_id=settings.APNS_BUNDLE_ID if hasattr(settings, "APNS_BUNDLE_ID") else None,
            apns_private_key_path=settings.APNS_PRIVATE_KEY_PATH if hasattr(settings, "APNS_PRIVATE_KEY_PATH") else None,
            apns_use_sandbox=settings.APNS_USE_SANDBOX if hasattr(settings, "APNS_USE_SANDBOX") else True,
        )
        logger.info("Real-time services initialized", extra={"results": realtime_results})
    except Exception as e:
        logger.error(f"Failed to initialize real-time services: {e}")
    
    yield
    
    # Shutdown
    try:
        await shutdown_realtime_services()
    except Exception as e:
        logger.error(f"Error during real-time services shutdown: {e}")


app = FastAPI(
    title="VCOS API",
    description="Virtual Company Operating System API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add real-time WebSocket gateway
add_realtime_to_app(app)

# API routes
app.include_router(api_router, prefix="/api/v1")

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "vcos-api"}

# Real-time services health check
@app.get("/health/realtime")
async def realtime_health():
    return await get_realtime_health()

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8999)