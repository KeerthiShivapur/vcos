"""HR hub API (Phase 11 — Human Workforce Operating System).

The People Operations dashboard aggregates every HR subsystem (headcount,
recruitment, leave, performance, offboarding, compliance, assets, payroll,
wellbeing, succession) and hosts the HR AI companion plus employee lifecycle
transitions (promote, transfer) that feed the organization graph.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.core.timeutils import utcnow
from app.db.database import get_db
from app.events.event_bus import EventBus
from app.hr.hr_ai_service import hr_ai_service
from app.hr.asset_service import asset_service
from app.hr.compliance_service import compliance_service
from app.hr.leave_service import leave_service
from app.hr.offboarding_service import offboarding_service
from app.hr.payroll_service import payroll_service
from app.hr.performance_service import performance_service
from app.hr.recruitment_service import recruitment_service
from app.hr.wellbeing_service import wellbeing_service
from app.hr.workforce_service import workforce_service
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/hr", tags=["HR Hub"])

_event_bus = EventBus()


@router.get("/dashboard")
async def hr_dashboard(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated people operations dashboard."""
    workforce = await workforce_service.analytics(db, organization_id=org.id)
    recruitment = await recruitment_service.stats(db, organization_id=org.id)
    leave = await leave_service.summary(db, organization_id=org.id)
    performance = await performance_service.summary(db, organization_id=org.id)
    offboardings = await offboarding_service.list(db, organization_id=org.id)
    compliance = await compliance_service.overview(db, organization_id=org.id)
    assets = await asset_service.summary(db, organization_id=org.id)
    wellbeing = await wellbeing_service.overview(db, organization_id=org.id)
    payroll = await payroll_service.overview(db, organization_id=org.id)
    return {
        "workforce": workforce,
        "recruitment": recruitment,
        "leave": leave,
        "performance": performance,
        "offboarding": {
            "active": sum(1 for item in offboardings if item["status"] in ("requested", "approved", "in_progress")),
            "completed": sum(1 for item in offboardings if item["status"] == "completed"),
            "in_progress": sum(1 for item in offboardings if item["status"] == "in_progress"),
            "list": [item for item in offboardings if item["status"] != "completed"][:10],
        },
        "compliance": {
            "expired_documents": compliance["documents"]["expired"],
            "expiring_30": compliance["documents"]["expiring_30"],
            "missing_trainings": compliance["trainings"]["missing"],
            "total_documents": compliance["documents"]["total"],
        },
        "assets": assets,
        "wellbeing": wellbeing,
        "payroll": {
            "runs": payroll["runs"],
            "active_providers": payroll["active_providers"],
            "last_run": payroll["last_run"],
        },
    }


@router.post("/employees/{employee_id}/promote")
async def promote_employee(
    employee_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Promote an employee to a new designation/level (employee.promoted)."""
    employee = (
        await db.execute(
            select(Employee).where(Employee.organization_id == org.id, Employee.id == employee_id)
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    previous = employee.designation
    if "designation" in payload:
        employee.designation = payload["designation"]
    if "manager_id" in payload:
        employee.manager_id = payload["manager_id"]
    await db.flush()
    await _event_bus.publish(
        db,
        name="employee.promoted",
        organization_id=org.id,
        actor_id=user.id,
        payload={
            "employee_id": employee.id,
            "employee_name": employee.full_name,
            "previous_designation": previous,
            "new_designation": employee.designation,
            "promoted_at": utcnow().isoformat(),
        },
        flush=False,
    )
    await db.commit()
    return {
        "employee_id": employee.id,
        "previous_designation": previous,
        "new_designation": employee.designation,
    }


@router.post("/employees/{employee_id}/transfer")
async def transfer_employee(
    employee_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Move an employee across departments, teams or locations."""
    employee = (
        await db.execute(
            select(Employee).where(Employee.organization_id == org.id, Employee.id == employee_id)
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    for field in ("department_id", "team_id", "location_id", "business_unit_id", "manager_id"):
        if field in payload:
            setattr(employee, field, payload[field])
    await db.commit()
    return {
        "employee_id": employee.id,
        "department_id": employee.department_id,
        "team_id": employee.team_id,
        "manager_id": employee.manager_id,
    }


@router.get("/employees/{employee_id}/lifecycle")
async def employee_lifecycle(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    """One employee's complete HR footprint: attendance, leave, performance,
    assets, offboarding and compliance."""
    from app.hr.attendance_service import attendance_service
    employee = (
        await db.execute(
            select(Employee).where(Employee.organization_id == org.id, Employee.id == employee_id)
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    attendance = await attendance_service.summary(db, organization_id=org.id, employee_id=employee_id)
    balances = await leave_service.balances(db, organization_id=org.id, employee_id=employee_id)
    performance = await performance_service.employee_summary(db, organization_id=org.id, employee_id=employee_id)
    assets = await asset_service.list_assets(db, organization_id=org.id, employee_id=employee_id)
    compliance_docs = await compliance_service.list_documents(db, organization_id=org.id, employee_id=employee_id)
    trainings = await compliance_service.list_completions(db, organization_id=org.id, employee_id=employee_id)
    offboardings = await offboarding_service.list(db, organization_id=org.id)
    offboarding = next((item for item in offboardings if item["employee_id"] == employee_id), None)
    return {
        "employee": {
            "id": employee.id,
            "name": employee.full_name,
            "designation": employee.designation,
            "status": employee.status,
            "joining_date": employee.joining_date.isoformat() if employee.joining_date else None,
        },
        "attendance": attendance,
        "leave": {"balances": balances},
        "performance": performance,
        "assets": assets,
        "compliance": {"documents": compliance_docs, "trainings": trainings},
        "offboarding": offboarding,
    }


@router.post("/ai/ask")
async def hr_ai_companion(
    payload: dict[str, str],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    """The HR AI companion: answers employee / manager / executive HR
    questions with live organization data."""
    question = payload.get("question", "")
    if not question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    answer = await hr_ai_service.answer(db, organization_id=org.id, user=user, question=question)
    await db.commit()
    return answer
