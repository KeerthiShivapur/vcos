"""
Intelligence API v1 - Vector Search, ML Pipeline, Semantic Search.
"""

from fastapi import APIRouter
from app.api.v1.intelligence.vector_search import router as vector_search_router
from app.api.v1.intelligence.ml_pipeline_api import router as ml_pipeline_router

router = APIRouter()
router.include_router(vector_search_router)
router.include_router(ml_pipeline_router)

__all__ = ["router", "vector_search_router", "ml_pipeline_router"]