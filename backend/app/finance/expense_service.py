"""Expense service (Phase 13 — Finance & Business Operations).

Employees submit expenses; managers/finance approve; reimbursement is
tracked. AI helpers flag duplicates, policy violations and unusual spend.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.event_bus import EventBus
from app.finance.parse import to_date
from app.models.finance import Budget, Expense

logger = logging.getLogger("vcos.finance.expense")

_event_bus = EventBus()

EXPENSE_TYPES = [
    "travel", "food", "office", "software", "hardware", "training",
    "marketing", "client", "cloud", "miscellaneous",
]
EXPENSE_STATUSES = ["draft", "submitted", "pending", "approved", "rejected", "reimbursed"]


class ExpenseService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        amount = float(data.get("amount") or 0)
        if amount <= 0:
            raise ValueError("amount must be greater than zero")
        description = (data.get("description") or "").strip()
        if not description:
            raise ValueError("description is required")
        expense_type = data.get("expense_type", "miscellaneous")
        if expense_type not in EXPENSE_TYPES:
            raise ValueError(f"Invalid expense_type: {expense_type}")
        employee_id = data.get("employee_id") or actor_id
        expense = Expense(
            organization_id=organization_id,
            employee_id=employee_id,
            expense_type=expense_type,
            amount=amount,
            currency=data.get("currency") or "USD",
            incurred_at=to_date(data.get("incurred_at")),
            merchant=data.get("merchant"),
            description=description,
            project_id=data.get("project_id"),
            budget_id=data.get("budget_id"),
            status=data.get("status", "submitted") if data.get("status") in EXPENSE_STATUSES else "submitted",
            approver_id=data.get("approver_id"),
            receipt_url=data.get("receipt_url"),
            attributes=data.get("attributes") or {},
        )
        db.add(expense)
        await db.flush()
        expense.policy_flags = await self._check_policy(db, expense, organization_id=organization_id)
        await db.flush()
        if expense.status in ("submitted", "pending"):
            await _event_bus.publish(
                db, name="expense.submitted", organization_id=organization_id, actor_id=actor_id,
                payload={"expense_id": expense.id, "amount": expense.amount, "expense_type": expense.expense_type},
                flush=False,
            )
        if expense.budget_id:
            from app.finance.budget_service import budget_service
            budget = await budget_service.get(db, organization_id=organization_id, budget_id=expense.budget_id)
            if budget:
                await budget_service._refresh_usage(db, budget, organization_id=organization_id)
        return await self._dict(db, expense, organization_id=organization_id)

    async def get(self, db: AsyncSession, *, organization_id: str, expense_id: str) -> Optional[Expense]:
        row = await db.execute(
            select(Expense).where(Expense.organization_id == organization_id, Expense.id == expense_id)
        )
        return row.scalar_one_or_none()

    async def detail(self, db: AsyncSession, *, organization_id: str, expense_id: str) -> Optional[dict[str, Any]]:
        expense = await self.get(db, organization_id=organization_id, expense_id=expense_id)
        if expense is None:
            return None
        return await self._dict(db, expense, organization_id=organization_id)

    async def list_expenses(
        self, db: AsyncSession, *, organization_id: str,
        status: Optional[str] = None, expense_type: Optional[str] = None,
        employee_id: Optional[str] = None, project_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = select(Expense).where(Expense.organization_id == organization_id)
        if status:
            query = query.where(Expense.status == status)
        if expense_type:
            query = query.where(Expense.expense_type == expense_type)
        if employee_id:
            query = query.where(Expense.employee_id == employee_id)
        if project_id:
            query = query.where(Expense.project_id == project_id)
        rows = await db.execute(query.order_by(Expense.created_at.desc()).limit(limit))
        result = []
        for expense in rows.scalars().all():
            result.append(await self._dict(db, expense, organization_id=organization_id))
        return result

    async def update(
        self, db: AsyncSession, *, organization_id: str, expense: Expense, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if expense.status not in ("draft", "submitted", "pending"):
            raise ValueError("Only draft, submitted or pending expenses can be edited")
        if "amount" in data:
            amount = float(data["amount"] or 0)
            if amount <= 0:
                raise ValueError("amount must be greater than zero")
            expense.amount = amount
        if "expense_type" in data and data["expense_type"] in EXPENSE_TYPES:
            expense.expense_type = data["expense_type"]
        if "description" in data:
            expense.description = data["description"]
        if "incurred_at" in data:
            expense.incurred_at = to_date(data.get("incurred_at"))
        if "merchant" in data:
            expense.merchant = data.get("merchant")
        if "project_id" in data:
            expense.project_id = data.get("project_id")
        if "budget_id" in data:
            expense.budget_id = data.get("budget_id")
        if "receipt_url" in data:
            expense.receipt_url = data.get("receipt_url")
        expense.policy_flags = await self._check_policy(db, expense, organization_id=organization_id)
        await db.flush()
        return await self._dict(db, expense, organization_id=organization_id)

    async def decide(
        self, db: AsyncSession, *, organization_id: str, expense: Expense,
        decision: str, note: Optional[str] = None, actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if expense.status not in ("submitted", "pending", "approved"):
            raise ValueError("Expense cannot be decided in its current state")
        if decision not in ("approved", "rejected", "reimbursed"):
            raise ValueError("Invalid decision")
        now = utcnow()
        if decision == "approved":
            expense.status = "approved"
            expense.approver_id = actor_id or expense.approver_id
            expense.approved_at = now
            await _event_bus.publish(
                db, name="expense.approved", organization_id=organization_id, actor_id=actor_id,
                payload={"expense_id": expense.id, "amount": expense.amount},
                flush=False,
            )
        elif decision == "rejected":
            expense.status = "rejected"
            expense.rejection_reason = note
            await _event_bus.publish(
                db, name="expense.rejected", organization_id=organization_id, actor_id=actor_id,
                payload={"expense_id": expense.id, "reason": note},
                flush=False,
            )
        else:
            expense.status = "reimbursed"
            expense.reimbursed_at = now
            await _event_bus.publish(
                db, name="expense.reimbursed", organization_id=organization_id, actor_id=actor_id,
                payload={"expense_id": expense.id, "amount": expense.amount},
                flush=False,
            )
        await db.flush()
        if expense.budget_id:
            from app.finance.budget_service import budget_service
            budget = await budget_service.get(db, organization_id=organization_id, budget_id=expense.budget_id)
            if budget:
                await budget_service._refresh_usage(db, budget, organization_id=organization_id)
        return await self._dict(db, expense, organization_id=organization_id)

    async def mark_duplicate(self, db: AsyncSession, *, organization_id: str, expense: Expense,
                             duplicate_of: str) -> dict[str, Any]:
        expense.duplicate_of = duplicate_of
        flags = dict(expense.policy_flags or {})
        flags["duplicate"] = {"of": duplicate_of, "level": "high"}
        expense.policy_flags = flags
        await db.flush()
        return await self._dict(db, expense, organization_id=organization_id)

    async def _check_policy(self, db: AsyncSession, expense: Expense, *, organization_id: str) -> dict[str, Any]:
        flags: dict[str, Any] = {}
        if expense.amount and expense.amount >= 500:
            flags["high_amount"] = {"threshold": 500, "level": "medium"}
        if expense.expense_type == "food" and expense.amount and expense.amount >= 100:
            flags["food_limit"] = {"limit": 100, "level": "medium"}
        if expense.expense_type == "travel" and expense.amount and expense.amount >= 3000:
            flags["travel_limit"] = {"limit": 3000, "level": "high"}
        if not expense.receipt_url and expense.status in ("submitted", "pending", "approved"):
            flags["missing_receipt"] = {"level": "low"}
        dup = await self._find_duplicate(db, expense, organization_id=organization_id)
        if dup:
            flags["duplicate"] = {"of": dup.id, "level": "high"}
            expense.duplicate_of = dup.id
        # unusual: same employee spending > 5x their average
        avg = (
            await db.execute(
                select(func.avg(Expense.amount)).where(
                    Expense.organization_id == organization_id,
                    Expense.employee_id == expense.employee_id,
                    Expense.id != expense.id,
                    Expense.amount > 0,
                )
            )
        ).scalar_one_or_none()
        if avg and expense.amount and expense.amount > 5 * float(avg):
            flags["unusual_spending"] = {"average": round(float(avg), 2), "level": "medium"}
        flags["flagged"] = bool(flags)
        return flags

    async def _find_duplicate(self, db: AsyncSession, expense: Expense, *, organization_id: str) -> Optional[Expense]:
        if not expense.merchant or not expense.amount:
            return None
        rows = await db.execute(
            select(Expense).where(
                Expense.organization_id == organization_id,
                Expense.id != expense.id,
                Expense.amount == expense.amount,
                func.lower(Expense.merchant) == (expense.merchant or "").lower(),
            ).limit(1)
        )
        return rows.scalar_one_or_none()

    async def _dict(self, db: AsyncSession, expense: Expense, *, organization_id: str) -> dict[str, Any]:
        employee = None
        project = None
        budget = None
        if expense.employee_id:
            from app.models.employee import Employee
            employee = await db.get(Employee, expense.employee_id)
        if expense.project_id:
            from app.models.project import Project
            project = await db.get(Project, expense.project_id)
        if expense.budget_id:
            budget = await db.get(Budget, expense.budget_id)
        return {
            "id": expense.id,
            "employee_id": expense.employee_id,
            "employee_name": employee.full_name if employee else None,
            "expense_type": expense.expense_type,
            "amount": expense.amount,
            "currency": expense.currency,
            "incurred_at": expense.incurred_at.isoformat() if expense.incurred_at else None,
            "merchant": expense.merchant,
            "description": expense.description,
            "project_id": expense.project_id,
            "project_name": project.name if project else None,
            "budget_id": expense.budget_id,
            "budget_name": budget.name if budget else None,
            "status": expense.status,
            "approver_id": expense.approver_id,
            "approved_at": ensure_aware(expense.approved_at).isoformat() if expense.approved_at else None,
            "rejection_reason": expense.rejection_reason,
            "reimbursed_at": ensure_aware(expense.reimbursed_at).isoformat() if expense.reimbursed_at else None,
            "receipt_url": expense.receipt_url,
            "duplicate_of": expense.duplicate_of,
            "policy_flags": expense.policy_flags or {},
            "created_at": ensure_aware(expense.created_at).isoformat() if expense.created_at else None,
        }


expense_service = ExpenseService()
