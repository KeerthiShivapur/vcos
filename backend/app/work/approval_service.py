"""Approval service â€” polymorphic approvals with requester/approver flows (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.approval import Approval
from app.models.employee import Employee


class ApprovalService:
    async def _validate_ref(self, db: AsyncSession, organization_id: str, key: str, value: str):
        if key == "requester_id" and value:
            emp = await db.get(Employee, value)
            if emp is None or emp.organization_id != organization_id:
                raise ValueError("Invalid requester_id reference")
        elif key == "approver_id" and value:
            emp = await db.get(Employee, value)
            if emp is None or emp.organization_id != organization_id:
                raise ValueError("Invalid approver_id reference")

    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Approval:
        if data.get("requester_id"):
            await self._validate_ref(db, organization_id, "requester_id", data["requester_id"])
        if data.get("approver_id"):
            await self._validate_ref(db, organization_id, "approver_id", data["approver_id"])
        approval = Approval(
            organization_id=organization_id,
            approval_type=data.get("approval_type", "project"),
            title=data["title"],
            description=data.get("description"),
            requester_id=data.get("requester_id") or (actor.id if actor else None),
            approver_id=data.get("approver_id"),
            status="pending",
            priority=data.get("priority", "medium"),
            due_at=data.get("due_at"),
            entity_type=data.get("entity_type"),
            entity_id=data.get("entity_id"),
            policy_id=data.get("policy_id"),
        )
        db.add(approval)
        await db.flush()
        await self._emit(db, "approval.requested", organization_id, actor, ip_address, approval)
        if approval.approver_id:
            from app.services.work_alerts import notify_employee

            await notify_employee(
                db,
                organization_id=organization_id,
                employee_id=approval.approver_id,
                type="approval.requested",
                title=f"Approval requested: {approval.title}",
                body=f"{approval.approval_type} · {approval.priority} priority",
                actor_id=actor.user_id if actor else None,
                priority="high" if approval.priority in ("high", "critical") else "normal",
                entity_type="approval",
                entity_id=approval.id,
                link="/approvals",
            )
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="approval.requested",
            actor=actor, ip_address=ip_address,
            resource_type="approval", resource_id=approval.id,
            details={"title": approval.title, "approval_type": approval.approval_type},
        )
        return approval

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str], approval: Approval):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={
                "approval_id": approval.id, "title": approval.title,
                "approval_type": approval.approval_type, "status": approval.status,
                "requester_id": approval.requester_id, "approver_id": approval.approver_id,
            },
        )

    async def get(self, db: AsyncSession, *, organization_id: str, approval_id: str) -> Optional[Approval]:
        row = await db.execute(
            select(Approval).where(Approval.organization_id == organization_id, Approval.id == approval_id)
        )
        approval = row.scalar_one_or_none()
        if approval:
            approval.requester_name = None
            approval.approver_name = None
            if approval.requester_id:
                requester = await db.get(Employee, approval.requester_id)
                approval.requester_name = requester.full_name if requester else None
            if approval.approver_id:
                approver = await db.get(Employee, approval.approver_id)
                approval.approver_name = approver.full_name if approver else None
        return approval

    async def list_all(
        self, db: AsyncSession, *, organization_id: str,
        status: Optional[str] = None, approval_type: Optional[str] = None,
        employee_id: Optional[str] = None, limit: int = 100,
    ) -> list[Approval]:
        stmt = select(Approval).where(Approval.organization_id == organization_id)
        if status:
            stmt = stmt.where(Approval.status == status)
        if approval_type:
            stmt = stmt.where(Approval.approval_type == approval_type)
        if employee_id:
            stmt = stmt.where(or_(Approval.requester_id == employee_id, Approval.approver_id == employee_id))
        rows = await db.execute(stmt.order_by(desc(Approval.created_at)).limit(limit))
        approvals = list(rows.scalars().all())
        emp_ids = {a.requester_id for a in approvals if a.requester_id} | {a.approver_id for a in approvals if a.approver_id}
        emps = {}
        if emp_ids:
            emps = {e.id: e for e in (await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))).scalars().all()}
        for a in approvals:
            a.requester_name = emps[a.requester_id].full_name if a.requester_id and emps.get(a.requester_id) else None
            a.approver_name = emps[a.approver_id].full_name if a.approver_id and emps.get(a.approver_id) else None
        return approvals

    async def decide(
        self, db: AsyncSession, *, organization_id: str, approval: Approval,
        decision: str, note: Optional[str] = None,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Approval:
        if approval.status != "pending":
            raise ValueError("Approval has already been decided")
        if decision not in ("approved", "rejected"):
            raise ValueError("Invalid decision")
        await self._enforce_policy(db, organization_id, approval, actor)
        approval.status = decision
        approval.decision_note = note
        approval.decided_at = utcnow()
        approval.updated_at = utcnow()
        await db.flush()
        await self._emit(db, f"approval.{decision}", organization_id, actor, ip_address, approval)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action=f"approval.{decision}",
            actor=actor, ip_address=ip_address,
            resource_type="approval", resource_id=approval.id,
            details={"title": approval.title, "note": note, "policy_id": approval.policy_id},
        )
        return approval

    async def _enforce_policy(
        self, db: AsyncSession, organization_id: str, approval: Approval,
        actor: Optional[Employee],
    ) -> None:
        """Slice 4C governance: approval policies gate who may decide what.

        Without a policy the historical rule applies (approvals:manage holder
        may decide). With an active policy the decider must hold the policy's
        required permission at the policy's scope, and self-approval is denied
        unless the policy explicitly allows it.
        """
        if not approval.policy_id:
            return
        from app.models.governance import ApprovalPolicy
        from app.services.governance_service import governance_service

        policy = await db.get(ApprovalPolicy, approval.policy_id)
        if policy is None or not policy.is_active:
            return
        if actor is None:
            raise ValueError("You are not authorized to decide this approval")
        if not policy.self_approval_allowed and approval.requester_id and actor.id == approval.requester_id:
            raise ValueError("Self-approval is not allowed for this policy")
        allowed = await governance_service.has_permission(
            db,
            organization_id=organization_id,
            user_id=actor.user_id,
            permission_code=policy.required_permission,
            scope_id=policy.scope_id,
        )
        if not allowed:
            raise ValueError("You are not authorized to decide this approval")

    async def cancel(
        self, db: AsyncSession, *, organization_id: str, approval: Approval,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Approval:
        if approval.status != "pending":
            raise ValueError("Only pending approvals can be cancelled")
        approval.status = "cancelled"
        approval.updated_at = utcnow()
        await db.flush()
        await self._emit(db, "approval.cancelled", organization_id, actor, ip_address, approval)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="approval.cancelled",
            actor=actor, ip_address=ip_address,
            resource_type="approval", resource_id=approval.id,
            details={"title": approval.title},
        )
        return approval

    async def stats(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        rows = (await db.execute(
            select(Approval.status, Approval.approval_type, func.count(Approval.id))
            .where(Approval.organization_id == organization_id)
            .group_by(Approval.status, Approval.approval_type)
        )).all()
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for status, approval_type, count in rows:
            by_status[status] = by_status.get(status, 0) + count
            by_type[approval_type] = by_type.get(approval_type, 0) + count
        pending = by_status.get("pending", 0)
        return {
            "total": sum(by_status.values()),
            "pending": pending,
            "approved": by_status.get("approved", 0),
            "rejected": by_status.get("rejected", 0),
            "cancelled": by_status.get("cancelled", 0),
            "by_type": by_type,
            "approval_rate": round((by_status.get("approved", 0) / (pending + by_status.get("approved", 0) + by_status.get("rejected", 0))) * 100, 1)
            if (pending + by_status.get("approved", 0) + by_status.get("rejected", 0)) else 0.0,
        }


async def count_pending_for_approver(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
    ) -> int:
        """Count pending approvals where the user is the approver."""
        from sqlalchemy import select, func
        result = await db.execute(
            select(func.count(Approval.id)).where(
                Approval.organization_id == organization_id,
                Approval.approver_id == employee_id,
                Approval.status == "pending",
            )
        )
        return result.scalar() or 0


approval_service = ApprovalService()

