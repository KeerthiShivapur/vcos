"""Budget service (Phase 13 — Finance & Business Operations).

Budgets cover organizations, departments, projects, teams, initiatives,
training, marketing, R&D, travel and IT. Every spend (expense, purchase
order) draws against a budget; usage and remaining amounts stay current.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.event_bus import EventBus
from app.finance.parse import to_date
from app.models.finance import (
    Budget,
    BudgetAllocation,
    BudgetRevision,
    Expense,
    PurchaseOrder,
    PurchaseRequest,
)

logger = logging.getLogger("vcos.finance.budget")

_event_bus = EventBus()

BUDGET_TYPES = [
    "annual", "quarterly", "department", "project", "team", "initiative",
    "training", "marketing", "rnd", "travel", "it", "other",
]
BUDGET_STATUSES = ["draft", "active", "frozen", "closed"]


class BudgetService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> Budget:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        allocated = float(data.get("allocated_amount") or 0)
        if allocated < 0:
            raise ValueError("allocated_amount cannot be negative")
        budget_type = data.get("budget_type", "annual")
        if budget_type not in BUDGET_TYPES:
            raise ValueError(f"Invalid budget_type: {budget_type}")
        budget = Budget(
            organization_id=organization_id,
            name=name,
            budget_type=budget_type,
            department_id=data.get("department_id"),
            project_id=data.get("project_id"),
            team_id=data.get("team_id"),
            fiscal_year=int(data["fiscal_year"]) if data.get("fiscal_year") else None,
            period_start=to_date(data.get("period_start")),
            period_end=to_date(data.get("period_end")),
            allocated_amount=allocated,
            used_amount=0.0,
            remaining_amount=allocated,
            currency=data.get("currency") or "USD",
            status=data.get("status", "active") if data.get("status") in BUDGET_STATUSES else "active",
            owner_id=data.get("owner_id") or actor_id,
            description=data.get("description"),
            attributes=data.get("attributes") or {},
        )
        db.add(budget)
        await db.flush()
        for item in data.get("allocations") or []:
            db.add(BudgetAllocation(
                organization_id=organization_id,
                budget_id=budget.id,
                name=(item.get("name") or "").strip() or "Allocation",
                amount=float(item.get("amount") or 0),
                period=item.get("period"),
                department_id=item.get("department_id"),
                project_id=item.get("project_id"),
            ))
        await self._refresh_usage(db, budget, organization_id=organization_id)
        await _event_bus.publish(
            db, name="budget.created", organization_id=organization_id, actor_id=actor_id,
            payload={"budget_id": budget.id, "name": budget.name, "allocated_amount": budget.allocated_amount},
            flush=False,
        )
        return budget

    async def get(self, db: AsyncSession, *, organization_id: str, budget_id: str) -> Optional[Budget]:
        row = await db.execute(
            select(Budget).where(Budget.organization_id == organization_id, Budget.id == budget_id)
        )
        return row.scalar_one_or_none()

    async def detail(self, db: AsyncSession, *, organization_id: str, budget_id: str) -> Optional[dict[str, Any]]:
        budget = await self.get(db, organization_id=organization_id, budget_id=budget_id)
        if budget is None:
            return None
        base = await self._dict(db, budget, organization_id=organization_id)
        allocations = (
            await db.execute(
                select(BudgetAllocation).where(
                    BudgetAllocation.organization_id == organization_id,
                    BudgetAllocation.budget_id == budget_id,
                )
            )
        ).scalars().all()
        revisions = (
            await db.execute(
                select(BudgetRevision).where(
                    BudgetRevision.organization_id == organization_id,
                    BudgetRevision.budget_id == budget_id,
                ).order_by(BudgetRevision.created_at.desc())
            )
        ).scalars().all()
        base["allocations"] = [{
            "id": a.id, "name": a.name, "amount": a.amount, "period": a.period,
            "department_id": a.department_id, "project_id": a.project_id,
        } for a in allocations]
        base["revisions"] = [{
            "id": r.id, "delta": r.delta, "previous_amount": r.previous_amount,
            "new_amount": r.new_amount, "reason": r.reason, "actor_id": r.actor_id,
            "created_at": ensure_aware(r.created_at).isoformat() if r.created_at else None,
        } for r in revisions]
        return base

    async def list_budgets(
        self, db: AsyncSession, *, organization_id: str,
        budget_type: Optional[str] = None, status: Optional[str] = None,
        department_id: Optional[str] = None, project_id: Optional[str] = None,
        owner_id: Optional[str] = None, search: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(Budget).where(Budget.organization_id == organization_id)
        if budget_type:
            query = query.where(Budget.budget_type == budget_type)
        if status:
            query = query.where(Budget.status == status)
        if department_id:
            query = query.where(Budget.department_id == department_id)
        if project_id:
            query = query.where(Budget.project_id == project_id)
        if owner_id:
            query = query.where(Budget.owner_id == owner_id)
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(func.lower(Budget.name).like(pattern))
        rows = await db.execute(query.order_by(Budget.created_at.desc()))
        result = []
        for budget in rows.scalars().all():
            item = await self._dict(db, budget, organization_id=organization_id)
            item["risk_level"] = self._risk_level(budget)
            result.append(item)
        return result

    async def update(
        self, db: AsyncSession, *, organization_id: str, budget: Budget, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> Budget:
        if budget.status == "closed":
            raise ValueError("Closed budgets cannot be updated")
        if "name" in data and data["name"]:
            budget.name = data["name"]
        if "description" in data:
            budget.description = data.get("description")
        if "status" in data and data["status"] in BUDGET_STATUSES:
            budget.status = data["status"]
        if "budget_type" in data and data["budget_type"] in BUDGET_TYPES:
            budget.budget_type = data["budget_type"]
        if "department_id" in data:
            budget.department_id = data.get("department_id")
        if "project_id" in data:
            budget.project_id = data.get("project_id")
        if "team_id" in data:
            budget.team_id = data.get("team_id")
        if "owner_id" in data:
            budget.owner_id = data.get("owner_id")
        if "period_start" in data:
            budget.period_start = to_date(data.get("period_start"))
        if "period_end" in data:
            budget.period_end = to_date(data.get("period_end"))
        if "currency" in data and data.get("currency"):
            budget.currency = data["currency"]
        if data.get("revision_delta") is not None:
            delta = float(data["revision_delta"])
            previous = budget.allocated_amount
            new_amount = max(0.0, previous + delta)
            budget.allocated_amount = new_amount
            db.add(BudgetRevision(
                organization_id=organization_id,
                budget_id=budget.id,
                delta=delta,
                previous_amount=previous,
                new_amount=new_amount,
                reason=data.get("revision_reason"),
                actor_id=actor_id,
            ))
        if "allocated_amount" in data:
            previous = budget.allocated_amount
            new_amount = float(data["allocated_amount"] or 0)
            delta = round(new_amount - previous, 2)
            if delta != 0:
                budget.allocated_amount = new_amount
                db.add(BudgetRevision(
                    organization_id=organization_id,
                    budget_id=budget.id,
                    delta=delta,
                    previous_amount=previous,
                    new_amount=new_amount,
                    reason=data.get("revision_reason") or "Amount updated",
                    actor_id=actor_id,
                ))
        await self._refresh_usage(db, budget, organization_id=organization_id)
        await _event_bus.publish(
            db, name="budget.updated", organization_id=organization_id, actor_id=actor_id,
            payload={"budget_id": budget.id, "name": budget.name, "allocated_amount": budget.allocated_amount},
            flush=False,
        )
        return budget

    async def delete(self, db: AsyncSession, *, organization_id: str, budget: Budget) -> None:
        await db.delete(budget)

    async def _refresh_usage(self, db: AsyncSession, budget: Budget, *, organization_id: str) -> None:
        expense_total = (
            await db.execute(
                select(func.coalesce(func.sum(Expense.amount), 0.0)).where(
                    Expense.organization_id == organization_id,
                    Expense.budget_id == budget.id,
                    Expense.status.in_(("submitted", "pending", "approved", "reimbursed")),
                )
            )
        ).scalar_one()
        po_total = (
            await db.execute(
                select(func.coalesce(func.sum(PurchaseOrder.total_amount), 0.0)).where(
                    PurchaseOrder.organization_id == organization_id,
                    PurchaseOrder.status.in_(("issued", "accepted", "partially_delivered", "delivered")),
                    PurchaseOrder.purchase_request_id.in_(
                        select(PurchaseRequest.id).where(
                            PurchaseRequest.organization_id == organization_id,
                            PurchaseRequest.budget_id == budget.id,
                        )
                    ),
                )
            )
        ).scalar_one()
        used = round(float(expense_total) + float(po_total), 2)
        budget.used_amount = used
        budget.remaining_amount = round(max(0.0, (budget.allocated_amount or 0) - used), 2)
        budget.risk_level = self._risk_level(budget)
        await db.flush()

    def _risk_level(self, budget: Budget) -> str:
        allocated = budget.allocated_amount or 0
        if allocated <= 0:
            return "low"
        usage = (budget.used_amount or 0) / allocated
        if usage >= 0.9:
            return "critical"
        if usage >= 0.75:
            return "high"
        if usage >= 0.5:
            return "medium"
        return "low"

    async def _dict(self, db: AsyncSession, budget: Budget, *, organization_id: str) -> dict[str, Any]:
        dept = None
        project = None
        owner = None
        if budget.department_id:
            from app.models.department import Department
            dept = await db.get(Department, budget.department_id)
        if budget.project_id:
            from app.models.project import Project
            project = await db.get(Project, budget.project_id)
        if budget.owner_id:
            from app.models.employee import Employee
            owner = await db.get(Employee, budget.owner_id)
        usage_pct = round(100 * (budget.used_amount or 0) / budget.allocated_amount, 1) if (budget.allocated_amount or 0) > 0 else 0.0
        return {
            "id": budget.id,
            "name": budget.name,
            "budget_type": budget.budget_type,
            "department_id": budget.department_id,
            "department_name": dept.name if dept else None,
            "project_id": budget.project_id,
            "project_name": project.name if project else None,
            "team_id": budget.team_id,
            "fiscal_year": budget.fiscal_year,
            "period_start": budget.period_start.isoformat() if budget.period_start else None,
            "period_end": budget.period_end.isoformat() if budget.period_end else None,
            "allocated_amount": budget.allocated_amount,
            "used_amount": budget.used_amount,
            "remaining_amount": budget.remaining_amount,
            "usage_pct": usage_pct,
            "currency": budget.currency,
            "status": budget.status,
            "owner_id": budget.owner_id,
            "owner_name": owner.full_name if owner else None,
            "forecast_amount": budget.forecast_amount,
            "risk_level": budget.risk_level,
            "description": budget.description,
            "created_at": ensure_aware(budget.created_at).isoformat() if budget.created_at else None,
            "updated_at": ensure_aware(budget.updated_at).isoformat() if budget.updated_at else None,
        }

    async def summary(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        budgets = (
            await db.execute(select(Budget).where(Budget.organization_id == organization_id))
        ).scalars().all()
        allocated = sum(b.allocated_amount or 0 for b in budgets)
        used = sum(b.used_amount or 0 for b in budgets)
        by_type: dict[str, dict[str, float]] = {}
        risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for budget in budgets:
            risk_counts[self._risk_level(budget)] = risk_counts.get(self._risk_level(budget), 0) + 1
            bucket = by_type.setdefault(budget.budget_type, {"allocated": 0.0, "used": 0.0})
            bucket["allocated"] += budget.allocated_amount or 0
            bucket["used"] += budget.used_amount or 0
        return {
            "total_budgets": len(budgets),
            "allocated": round(allocated, 2),
            "used": round(used, 2),
            "remaining": round(max(0.0, allocated - used), 2),
            "usage_pct": round(100 * used / allocated, 1) if allocated > 0 else 0.0,
            "by_type": by_type,
            "risk_counts": risk_counts,
        }


budget_service = BudgetService()
