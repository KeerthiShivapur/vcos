"""Industry API package (Phase 17.16).

Nine industry routers are generated from one factory — healthcare,
manufacturing, education, retail, government, finance, logistics, legal and
research. Every router exposes the same endpoint surface; the pack data
drives the behaviour, so there is exactly zero per-industry endpoint code.
"""

from fastapi import APIRouter

from app.industry.api.common import build_industry_router

INDUSTRY_ROUTERS: dict[str, APIRouter] = {
    "healthcare": build_industry_router("healthcare"),
    "manufacturing": build_industry_router("manufacturing"),
    "education": build_industry_router("education"),
    "retail": build_industry_router("retail"),
    "government": build_industry_router("government"),
    "finance": build_industry_router("finance"),
    "logistics": build_industry_router("logistics"),
    "legal": build_industry_router("legal"),
    "research": build_industry_router("research"),
}

__all__ = ["INDUSTRY_ROUTERS", "build_industry_router"]
