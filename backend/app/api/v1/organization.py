"""Organization structure, org chart, graph, and intelligence API (Phase 2)."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.people.graph_service import graph_service
from app.people.intelligence_service import intelligence_service
from app.people.orgchart_service import orgchart_service
from app.schemas.people import (
    OrgChartResponse,
    OrganizationGraph,
    OrganizationStructure,
    OrgIntelligence,
)

router = APIRouter(prefix="/organization", tags=["Organization"])


@router.get("/structure", response_model=OrganizationStructure)
async def organization_structure(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("orgchart:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.department_service import department_service
    from app.people.team_service import team_service

    departments = await department_service.list_departments(db, organization_id=org.id)
    teams = await team_service.list(db, organization_id=org.id)
    locations = await department_service.list_locations(db, organization_id=org.id)
    business_units = await department_service.list_business_units(db, organization_id=org.id)
    return OrganizationStructure(
        departments=[
            {
                "id": d.id, "name": d.name, "code": d.code, "description": d.description,
                "parent_id": d.parent_id, "parent_name": getattr(d, "parent_name", None),
                "head_id": d.head_id, "head_name": getattr(d, "head_name", None),
                "location_id": d.location_id, "location_name": getattr(d, "location_name", None),
                "members_count": getattr(d, "members_count", 0),
                "teams_count": getattr(d, "teams_count", 0),
            }
            for d in departments
        ],
        teams=[
            {
                "id": t.id, "name": t.name, "code": t.code, "description": t.description,
                "department_id": t.department_id,
                "department_name": getattr(t, "department_name", None),
                "lead_id": t.lead_id, "lead_name": getattr(t, "lead_name", None),
                "members_count": getattr(t, "members_count", 0),
                "members": getattr(t, "_member_rows", []),
            }
            for t in teams
        ],
        locations=[
            {
                "id": l.id, "name": l.name, "code": l.code, "city": l.city,
                "country": l.country, "address": l.address, "is_office": l.is_office,
                "timezone": l.timezone, "employees_count": getattr(l, "employees_count", 0),
            }
            for l in locations
        ],
        business_units=[
            {
                "id": u.id, "name": u.name, "code": u.code, "description": u.description,
                "head_id": u.head_id, "head_name": getattr(u, "head_name", None),
                "parent_id": u.parent_id, "employees_count": getattr(u, "employees_count", 0),
            }
            for u in business_units
        ],
    )


@router.get("/chart", response_model=OrgChartResponse)
async def org_chart(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("orgchart:read")),
    db: AsyncSession = Depends(get_db),
    department_id: str = Query(None),
    team_id: str = Query(None),
    max_depth: int = Query(6, ge=1, le=20),
):
    return await orgchart_service.chart(
        db, organization_id=org.id, department_id=department_id,
        team_id=team_id, max_depth=max_depth,
    )


@router.get("/graph", response_model=OrganizationGraph)
async def organization_graph(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("orgchart:read")),
    db: AsyncSession = Depends(get_db),
    include_work: bool = Query(True, description="Include work entities (projects, tasks, goals, meetings)"),
):
    return await graph_service.build(db, organization_id=org.id, include_work=include_work)


@router.get("/intelligence", response_model=OrgIntelligence)
async def org_intelligence(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
):
    return await intelligence_service.compute(db, organization_id=org.id)
