# API v1 Router
from fastapi import APIRouter

from app.api.v1 import adaptive_operating_profile, company_experience, dashboard, health, realtime, meetings
from app.api.v1 import crdt
from app.api.v1 import ml_pipeline
from app.api.v1 import knowledge_rag
from app.api.v1 import realtime_yjs
from app.api.v1 import realtime_livekit
from app.api.v1 import realtime_collab
from app.api.v1 import realtime_sync
from app.api.v1 import ml_platform
from app.api.v1 import scim
from app.api.v1 import webauthn
from app.api.v1 import integrations
from app.api.v1 import intelligence
from app.api.v1 import authorization
from app.api.v1 import compliance
from app.api.v1 import turn
from app.api.v1 import push_notifications
from app.api.v1 import e2e_encryption
from app.api.v1 import security_compliance
from app.api.v1 import embedded_analytics
from app.api.v1 import sre
from app.api.v1 import multiregion
from app.api.v1 import livekit_cluster
from app.api.v1 import auth
from app.api.v1 import organizations
from app.api.v1 import documents
from app.core.edge_functions import router as edge_router

router = APIRouter()

router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["Authentication"])
router.include_router(organizations.router, tags=["Organizations"])
router.include_router(company_experience.router, prefix="/company-experience", tags=["company-experience"])
router.include_router(adaptive_operating_profile.router, prefix="/adaptive-operating-profile", tags=["adaptive-operating-profile"])
router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
router.include_router(realtime.router, prefix="/realtime", tags=["realtime"])
router.include_router(realtime_yjs.router, prefix="/yjs", tags=["yjs"])
router.include_router(realtime_livekit.router, prefix="/livekit", tags=["livekit"])
router.include_router(realtime_collab.router, prefix="/realtime", tags=["realtime-collab"])
router.include_router(realtime_sync.router, prefix="/realtime", tags=["realtime-sync"])
router.include_router(ml_platform.router, prefix="/ml", tags=["ml-platform"])
router.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
router.include_router(scim.router, tags=["scim"])
router.include_router(webauthn.router, tags=["webauthn"])
router.include_router(crdt.router, tags=["crdt"])
router.include_router(ml_pipeline.router, tags=["ml"])
router.include_router(knowledge_rag.router, tags=["knowledge-rag"])
router.include_router(integrations.router, tags=["integrations"])
router.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"])
router.include_router(authorization.router, prefix="/authorization", tags=["authorization"])
router.include_router(compliance.router, prefix="/compliance", tags=["compliance"])
router.include_router(turn.router, prefix="/turn", tags=["turn"])
router.include_router(push_notifications.router, prefix="/push", tags=["push"])
router.include_router(e2e_encryption.router, prefix="/e2e", tags=["E2E Encryption"])
router.include_router(security_compliance.router, prefix="/security", tags=["Security & Compliance"])
router.include_router(embedded_analytics.router, prefix="/embedded-analytics", tags=["Embedded Analytics"])
router.include_router(sre.router, prefix="/sre", tags=["SRE & Operations"])
router.include_router(multiregion.router, prefix="/multiregion", tags=["Multi-Region & Global Scale"])
router.include_router(livekit_cluster.router, prefix="/livekit/cluster", tags=["LiveKit Cluster"])
router.include_router(documents.router, tags=["Documents"])
router.include_router(edge_router, prefix="/edge", tags=["Edge Functions"])