"""Universal search foundation (Phase 1).

Indexes users, organizations, roles, and workspace items within the tenant.
Later phases extend this service to projects, documents, knowledge, meetings,
messages, customers — everything.
"""

import json
import time
from typing import Any, Optional

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.models.workspace import WorkspaceItem


class SearchService:
    def _like(self, value: str) -> str:
        return f"%{value}%"

    async def search(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        user_id: str,
        limit: int = 20,
        user: Optional[Any] = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        q = query.strip()
        results: list[dict[str, Any]] = []
        if not q:
            return {"query": query, "results": [], "total": 0, "took_ms": 0}

        pattern = self._like(q.lower())

        users = await db.execute(
            select(User)
            .where(
                User.organization_id == organization_id,
                User.status.in_(("active", "pending")),
                or_(
                    func_lower(User.email).like(pattern),
                    func_lower(User.full_name).like(pattern),
                    func_lower(User.job_title).like(pattern),
                    func_lower(User.username).like(pattern),
                ),
            )
            .limit(limit)
        )
        for u in users.scalars().all():
            results.append(
                {
                    "type": "user",
                    "id": u.id,
                    "title": u.full_name,
                    "subtitle": f"{u.job_title or u.role} · {u.email}",
                    "url": f"/profile/{u.id}",
                    "snippet": u.email,
                    "score": 0.9,
                    "metadata": {"email": u.email, "role": u.role, "status": u.status},
                }
            )

        organizations = await db.execute(
            select(Organization).where(
                Organization.id == organization_id,
                or_(
                    func_lower(Organization.name).like(pattern),
                    func_lower(Organization.slug).like(pattern),
                    func_lower(Organization.industry).like(pattern),
                ),
            )
        )
        for o in organizations.scalars().all():
            results.append(
                {
                    "type": "organization",
                    "id": o.id,
                    "title": o.name,
                    "subtitle": o.industry or "Organization",
                    "url": "/settings/organization",
                    "snippet": o.slug,
                    "score": 0.8,
                    "metadata": {"industry": o.industry},
                }
            )

        roles = await db.execute(
            select(Role).where(
                Role.organization_id == organization_id,
                or_(func_lower(Role.name).like(pattern), func_lower(Role.code).like(pattern)),
            )
        )

        customers = await db.execute(
            select(Customer).where(
                Customer.organization_id == organization_id,
                or_(
                    func_lower(Customer.company_name).like(pattern),
                    func_lower(Customer.industry).like(pattern),
                    func_lower(Customer.country).like(pattern),
                ),
            ).limit(limit)
        )
        for c in customers.scalars().all():
            results.append(
                {
                    "type": "customer",
                    "id": c.id,
                    "title": c.company_name,
                    "subtitle": f"{c.industry or 'Customer'} · {c.status}",
                    "url": f"/customers/{c.id}",
                    "snippet": c.description or c.country or "Customer account",
                    "score": 0.75,
                    "metadata": {"status": c.status, "health": c.health_status},
                }
            )

        for r in roles.scalars().all():
            results.append(
                {
                    "type": "role",
                    "id": r.id,
                    "title": r.name,
                    "subtitle": r.description or "Role",
                    "url": "/settings/roles",
                    "snippet": r.code,
                    "score": 0.7,
                    "metadata": {"code": r.code},
                }
            )

        items = await db.execute(
            select(WorkspaceItem).where(
                WorkspaceItem.organization_id == organization_id,
                WorkspaceItem.user_id == user_id,
                or_(
                    func_lower(WorkspaceItem.title).like(pattern),
                    func_lower(WorkspaceItem.content).like(pattern),
                ),
            )
        )
        for item in items.scalars().all():
            results.append(
                {
                    "type": "workspace_item",
                    "id": item.id,
                    "title": item.title,
                    "subtitle": item.kind,
                    "url": "/workspace",
                    "snippet": (item.content or "")[:120],
                    "score": 0.6,
                    "metadata": {"kind": item.kind},
                }
            )

        results.extend(
            await self._search_people(db, organization_id=organization_id, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_work(db, organization_id=organization_id, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_knowledge(db, organization_id=organization_id, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_finance(db, organization_id=organization_id, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_automation(db, organization_id=organization_id, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_enterprise(db, organization_id=organization_id, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_infrastructure(db, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_industry(db, organization_id=organization_id, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_digital_twin(db, organization_id=organization_id, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_developers(db, organization_id=organization_id, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_memory(db, organization_id=organization_id, pattern=pattern, limit=limit)
        )

        results.extend(
            await self._search_messaging(db, organization_id=organization_id, user_id=user_id, pattern=pattern, limit=limit)
        )

        if user is not None:
            results = await self._filter_accessible(
                db, results, organization_id=organization_id, user=user
            )

        return {
            "query": query,
            "results": results,
            "total": len(results),
            "took_ms": int((time.perf_counter() - started) * 1000),
        }

    # ------------------------------------------------------ Slice 4D.1 scoping

    _SEARCH_FILTER_KINDS = {
        "project": "project", "task": "task", "goal": "goal", "budget": "budget",
        "decision": "decision", "message": "message", "conversation": "conversation",
        "scope": "scope", "approval_policy": "approval_policy", "policy": "approval_policy",
        "person": "employee", "employee": "employee",
    }

    async def _filter_accessible(
        self, db: AsyncSession, results: list[dict[str, Any]], *, organization_id: str, user: Any,
    ) -> list[dict[str, Any]]:
        """Keep only results the caller may access (bounded, indexed).

        Org-wide callers are untouched (resolve_accessible_ids returns the
        full candidate set); scope-anchored callers only see evidence from
        their visible scope subtree.
        """
        from app.intelligence.company_context import resolve_accessible_ids

        by_kind: dict[str, list[str]] = {}
        for r in results:
            kind = self._SEARCH_FILTER_KINDS.get(r.get("type"))
            if kind:
                by_kind.setdefault(kind, []).append(r["id"])
        accessible: dict[str, set[str]] = {}
        for kind, ids in by_kind.items():
            ids = list(dict.fromkeys(ids))
            acc = await resolve_accessible_ids(
                db, user, organization_id=organization_id, kind=kind, ids=ids
            )
            accessible[kind] = set(acc)
        return [
            r for r in results
            if self._SEARCH_FILTER_KINDS.get(r.get("type")) not in accessible
            or r["id"] in accessible.get(self._SEARCH_FILTER_KINDS[r.get("type")], set())
        ]

    async def _search_messaging(
        self, db: AsyncSession, *, organization_id: str, user_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Slice 4B — index conversations and messages the viewer belongs to
        (membership-scoped: results are limited to the viewer's conversations)."""
        from app.models.communication import Conversation, ConversationMember, Message
        from app.models.employee import Employee

        out: list[dict[str, Any]] = []

        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if employee is None:
            return out
        member_conversation_ids = select(ConversationMember.conversation_id).where(
            ConversationMember.organization_id == organization_id,
            ConversationMember.employee_id == employee.id,
        )

        remaining = limit
        conversations = await db.execute(
            select(Conversation)
            .where(
                Conversation.organization_id == organization_id,
                Conversation.is_archived.is_(False),
                Conversation.id.in_(member_conversation_ids),
                or_(
                    func_lower(Conversation.title).like(pattern),
                    func_lower(Conversation.channel_key).like(pattern),
                ),
            )
            .limit(remaining)
        )
        for c in conversations.scalars().all():
            out.append(
                {
                    "type": "conversation",
                    "id": c.id,
                    "title": c.title or ("Direct message" if c.type == "dm" else "Conversation"),
                    "subtitle": f"Conversation · {c.type}",
                    "url": f"/messages/{c.id}",
                    "snippet": c.channel_key or c.type,
                    "score": 0.8,
                    "metadata": {"type": c.type},
                }
            )
        remaining = limit - len(out)

        if remaining > 0:
            messages = await db.execute(
                select(Message)
                .where(
                    Message.organization_id == organization_id,
                    Message.deleted.is_(False),
                    Message.content.isnot(None),
                    Message.conversation_id.in_(member_conversation_ids),
                    func_lower(Message.content).like(pattern),
                )
                .order_by(Message.created_at.desc())
                .limit(remaining)
            )
            for m in messages.scalars().all():
                out.append(
                    {
                        "type": "message",
                        "id": m.id,
                        "title": (m.content or "")[:80],
                        "subtitle": "Message",
                        "url": f"/messages/{m.conversation_id}",
                        "snippet": (m.content or "")[:120],
                        "score": 0.7,
                        "metadata": {"conversation_id": m.conversation_id},
                    }
                )
        return out

    async def _search_people(
        self, db: AsyncSession, *, organization_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 2 — index employees, departments, teams, and skills."""
        from app.models.department import Department
        from app.models.employee import Employee, EmployeePresence, EmployeeSkill
        from app.models.skill import Skill
        from app.models.team import Team

        out: list[dict[str, Any]] = []
        remaining = limit

        skill_ids = list(
            (
                await db.execute(
                    select(Skill.id).where(
                        Skill.organization_id == organization_id,
                        func_lower(Skill.name).like(pattern),
                    )
                )
            ).scalars().all()
        )
        has_skill_match = False
        if skill_ids:
            has_skill_match = exists(
                select(1).where(
                    EmployeeSkill.organization_id == organization_id,
                    EmployeeSkill.employee_id == Employee.id,
                    EmployeeSkill.skill_id.in_(skill_ids),
                )
            )

        employees = await db.execute(
            select(Employee)
            .where(
                Employee.organization_id == organization_id,
                Employee.status.in_(("active", "probation", "notice")),
                or_(
                    func_lower(Employee.first_name).like(pattern),
                    func_lower(Employee.last_name).like(pattern),
                    func_lower(Employee.display_name).like(pattern),
                    func_lower(Employee.email).like(pattern),
                    func_lower(Employee.designation).like(pattern),
                    func_lower(Employee.employee_number).like(pattern),
                    has_skill_match,
                ),
            )
            .limit(remaining)
        )
        emp_rows = employees.scalars().all()
        emp_ids = [e.id for e in emp_rows]
        skills_by_emp: dict[str, list[str]] = {}
        if emp_ids:
            rows = await db.execute(
                select(EmployeeSkill.employee_id, Skill.name)
                .join(Skill, Skill.id == EmployeeSkill.skill_id)
                .where(
                    EmployeeSkill.organization_id == organization_id,
                    EmployeeSkill.employee_id.in_(emp_ids),
                )
            )
            for employee_id, skill_name in rows.all():
                skills_by_emp.setdefault(employee_id, []).append(skill_name)
            online_ids = set(
                (
                    await db.execute(
                        select(EmployeePresence.employee_id).where(
                            EmployeePresence.organization_id == organization_id,
                            EmployeePresence.is_online.is_(True),
                            EmployeePresence.employee_id.in_(emp_ids),
                        )
                    )
                ).scalars().all()
            )
        else:
            online_ids = set()
        for e in emp_rows:
            out.append(
                {
                    "type": "employee",
                    "id": e.id,
                    "title": e.full_name,
                    "subtitle": f"{e.designation or 'Team member'} · {e.employee_number}",
                    "url": f"/people/{e.id}",
                    "snippet": ", ".join(skills_by_emp.get(e.id, [])[:4]) or e.email,
                    "score": 0.95,
                    "metadata": {
                        "email": e.email,
                        "designation": e.designation,
                        "is_online": e.id in online_ids,
                    },
                }
            )

        if len(out) < limit:
            departments = await db.execute(
                select(Department).where(
                    Department.organization_id == organization_id,
                    or_(func_lower(Department.name).like(pattern), func_lower(Department.code).like(pattern)),
                )
            )
            for d in departments.scalars().all():
                out.append(
                    {
                        "type": "department",
                        "id": d.id,
                        "title": d.name,
                        "subtitle": "Department",
                        "url": "/organization",
                        "snippet": d.code,
                        "score": 0.85,
                        "metadata": {"code": d.code},
                    }
                )

        if len(out) < limit:
            teams = await db.execute(
                select(Team).where(
                    Team.organization_id == organization_id,
                    or_(func_lower(Team.name).like(pattern), func_lower(Team.code).like(pattern)),
                )
            )
            for t in teams.scalars().all():
                out.append(
                    {
                        "type": "team",
                        "id": t.id,
                        "title": t.name,
                        "subtitle": "Team",
                        "url": "/organization",
                        "snippet": t.code,
                        "score": 0.85,
                        "metadata": {"code": t.code},
                    }
                )

        if len(out) < limit:
            skills = await db.execute(
                select(Skill).where(
                    Skill.organization_id == organization_id,
                    func_lower(Skill.name).like(pattern),
                )
            )
            for s in skills.scalars().all():
                out.append(
                    {
                        "type": "skill",
                        "id": s.id,
                        "title": s.name,
                        "subtitle": s.category or "Skill",
                        "url": "/people",
                        "snippet": s.description or "",
                        "score": 0.8,
                        "metadata": {"category": s.category},
                    }
                )

        return out[:limit]

    async def _search_work(
        self, db: AsyncSession, *, organization_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 3 — index projects, tasks, goals, meetings, milestones, roadmaps."""
        from app.models.goal import Goal
        from app.models.meeting import Meeting
        from app.models.project import Milestone, Project, Roadmap
        from app.models.task import Task

        out: list[dict[str, Any]] = []

        def cap_remaining() -> int:
            return max(0, limit - len(out))

        if len(out) < limit:
            projects = await db.execute(
                select(Project)
                .where(
                    Project.organization_id == organization_id,
                    or_(
                        func_lower(Project.name).like(pattern),
                        func_lower(Project.code).like(pattern),
                        func_lower(Project.description).like(pattern),
                    ),
                )
                .limit(cap_remaining())
            )
            for p in projects.scalars().all():
                out.append(
                    {
                        "type": "project",
                        "id": p.id,
                        "title": p.name,
                        "subtitle": f"{p.code} · {p.status}",
                        "url": f"/projects/{p.id}",
                        "snippet": (p.description or "")[:120],
                        "score": 0.9,
                        "metadata": {"code": p.code, "status": p.status},
                    }
                )

        if len(out) < limit:
            tasks = await db.execute(
                select(Task)
                .where(
                    Task.organization_id == organization_id,
                    or_(
                        func_lower(Task.title).like(pattern),
                        func_lower(Task.description).like(pattern),
                    ),
                )
                .limit(cap_remaining())
            )
            for t in tasks.scalars().all():
                out.append(
                    {
                        "type": "task",
                        "id": t.id,
                        "title": t.title,
                        "subtitle": f"Task · {t.status}",
                        "url": f"/tasks/{t.id}",
                        "snippet": (t.description or "")[:120],
                        "score": 0.85,
                        "metadata": {"status": t.status, "project_id": t.project_id},
                    }
                )

        if len(out) < limit:
            goals = await db.execute(
                select(Goal)
                .where(
                    Goal.organization_id == organization_id,
                    or_(func_lower(Goal.name).like(pattern), func_lower(Goal.description).like(pattern)),
                )
                .limit(cap_remaining())
            )
            for g in goals.scalars().all():
                out.append(
                    {
                        "type": "goal",
                        "id": g.id,
                        "title": g.name,
                        "subtitle": f"Goal · {g.scope} · {g.status}",
                        "url": f"/goals/{g.id}",
                        "snippet": (g.description or "")[:120],
                        "score": 0.85,
                        "metadata": {"scope": g.scope, "status": g.status},
                    }
                )

        if len(out) < limit:
            meetings = await db.execute(
                select(Meeting)
                .where(
                    Meeting.organization_id == organization_id,
                    or_(func_lower(Meeting.title).like(pattern), func_lower(Meeting.description).like(pattern)),
                )
                .limit(cap_remaining())
            )
            for m in meetings.scalars().all():
                out.append(
                    {
                        "type": "meeting",
                        "id": m.id,
                        "title": m.title,
                        "subtitle": f"Meeting · {m.meeting_type} · {m.status}",
                        "url": f"/meetings/{m.id}",
                        "snippet": (m.description or "")[:120],
                        "score": 0.85,
                        "metadata": {"meeting_type": m.meeting_type, "status": m.status},
                    }
                )

        if len(out) < limit:
            milestones = await db.execute(
                select(Milestone)
                .where(
                    Milestone.organization_id == organization_id,
                    func_lower(Milestone.name).like(pattern),
                )
                .limit(cap_remaining())
            )
            for ms in milestones.scalars().all():
                out.append(
                    {
                        "type": "milestone",
                        "id": ms.id,
                        "title": ms.name,
                        "subtitle": f"Milestone · {ms.status}",
                        "url": f"/projects/{ms.project_id}" if ms.project_id else "/projects",
                        "snippet": (ms.description or "")[:120],
                        "score": 0.8,
                        "metadata": {"status": ms.status, "project_id": ms.project_id},
                    }
                )

        if len(out) < limit:
            roadmaps = await db.execute(
                select(Roadmap)
                .where(
                    Roadmap.organization_id == organization_id,
                    func_lower(Roadmap.name).like(pattern),
                )
                .limit(cap_remaining())
            )
            for r in roadmaps.scalars().all():
                out.append(
                    {
                        "type": "roadmap",
                        "id": r.id,
                        "title": r.name,
                        "subtitle": f"Roadmap · {r.status}",
                        "url": "/projects",
                        "snippet": (r.description or "")[:120],
                        "score": 0.8,
                        "metadata": {"status": r.status},
                    }
                )

        return out

    async def _search_knowledge(
        self, db: AsyncSession, *, organization_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 4 — index documents, wiki, policies, SOPs, templates, decisions."""
        from app.knowledge import knowledge_base as kb

        out: list[dict[str, Any]] = []

        def cap_remaining() -> int:
            return max(0, limit - len(out))

        for kind, model in kb.KIND_MODELS.items():
            if len(out) >= limit:
                break
            rows = await db.execute(
                select(model)
                .where(
                    model.organization_id == organization_id,
                    or_(
                        func_lower(model.title).like(pattern),
                        func_lower(model.description).like(pattern),
                    ),
                )
                .limit(cap_remaining())
            )
            for row in rows.scalars().all():
                out.append(
                    {
                        "type": kind,
                        "id": row.id,
                        "title": row.title,
                        "subtitle": f"{kb.kind_label(kind)} · {row.status}",
                        "url": kb.entity_url(kind, row.id),
                        "snippet": (row.description or "")[:120],
                        "score": 0.85,
                        "metadata": {"status": row.status, "kind": kind},
                    }
                )
        return out

    async def _search_finance(
        self, db: AsyncSession, *, organization_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 13 — index vendors, budgets, invoices, purchase orders,
        purchase requests and expenses in universal search."""
        from app.models.finance import (
            Budget,
            Expense,
            Invoice,
            PurchaseOrder,
            PurchaseRequest,
            Vendor,
        )

        out: list[dict[str, Any]] = []
        remaining = limit

        vendors = await db.execute(
            select(Vendor).where(
                Vendor.organization_id == organization_id,
                or_(
                    func_lower(Vendor.name).like(pattern),
                    func_lower(Vendor.email).like(pattern),
                ),
            ).limit(remaining)
        )
        for v in vendors.scalars().all():
            out.append({
                "type": "vendor",
                "id": v.id,
                "title": v.name,
                "subtitle": f"Vendor · {v.kind} · {v.status}",
                "url": "/finance?tab=vendors",
                "snippet": v.contact_name or v.country or "Supplier",
                "score": 0.7,
                "metadata": {"kind": v.kind, "status": v.status},
            })
        remaining = limit - len(out)

        budgets = await db.execute(
            select(Budget).where(
                Budget.organization_id == organization_id,
                func_lower(Budget.name).like(pattern),
            ).limit(remaining)
        )
        for b in budgets.scalars().all():
            out.append({
                "type": "budget",
                "id": b.id,
                "title": b.name,
                "subtitle": f"Budget · {b.budget_type} · {b.status}",
                "url": "/finance?tab=budgets",
                "snippet": f"Allocated {b.allocated_amount or 0:,.2f} {b.currency or 'USD'}",
                "score": 0.7,
                "metadata": {"budget_type": b.budget_type, "status": b.status},
            })
        remaining = limit - len(out)

        invoices = await db.execute(
            select(Invoice).where(
                Invoice.organization_id == organization_id,
                or_(
                    func_lower(Invoice.title).like(pattern),
                    func_lower(Invoice.invoice_number).like(pattern),
                ),
            ).limit(remaining)
        )
        for inv in invoices.scalars().all():
            out.append({
                "type": "invoice",
                "id": inv.id,
                "title": inv.title,
                "subtitle": f"Invoice · {inv.direction} · {inv.status}",
                "url": "/finance?tab=invoices",
                "snippet": f"{inv.amount or 0:,.2f} {inv.currency or 'USD'}",
                "score": 0.7,
                "metadata": {"direction": inv.direction, "status": inv.status},
            })
        remaining = limit - len(out)

        orders = await db.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.organization_id == organization_id,
                or_(
                    func_lower(PurchaseOrder.title).like(pattern),
                    func_lower(PurchaseOrder.po_number).like(pattern),
                ),
            ).limit(remaining)
        )
        for order in orders.scalars().all():
            out.append({
                "type": "purchase_order",
                "id": order.id,
                "title": order.title,
                "subtitle": f"Purchase order · {order.po_number or ''} · {order.status}",
                "url": "/finance?tab=procurement",
                "snippet": f"{order.total_amount or 0:,.2f} {order.currency or 'USD'}",
                "score": 0.7,
                "metadata": {"po_number": order.po_number, "status": order.status},
            })
        remaining = limit - len(out)

        requests = await db.execute(
            select(PurchaseRequest).where(
                PurchaseRequest.organization_id == organization_id,
                func_lower(PurchaseRequest.title).like(pattern),
            ).limit(remaining)
        )
        for req in requests.scalars().all():
            out.append({
                "type": "purchase_request",
                "id": req.id,
                "title": req.title,
                "subtitle": f"Purchase request · {req.status}",
                "url": "/finance?tab=procurement",
                "snippet": f"{req.estimated_cost or 0:,.2f} {req.currency or 'USD'}",
                "score": 0.7,
                "metadata": {"status": req.status},
            })
        remaining = limit - len(out)

        if remaining > 0:
            expenses = await db.execute(
                select(Expense).where(
                    Expense.organization_id == organization_id,
                    func_lower(Expense.description).like(pattern),
                ).limit(remaining)
            )
            for exp in expenses.scalars().all():
                out.append({
                    "type": "expense",
                    "id": exp.id,
                    "title": exp.description or "Expense",
                    "subtitle": f"Expense · {exp.expense_type} · {exp.status}",
                    "url": "/finance?tab=expenses",
                    "snippet": f"{exp.amount or 0:,.2f} {exp.currency or 'USD'}",
                    "score": 0.7,
                    "metadata": {"expense_type": exp.expense_type, "status": exp.status},
                })
        return out

    async def _search_automation(
        self, db: AsyncSession, *, organization_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 14 — index workflows, rules, templates and executions in
        universal search."""
        from app.models.workflow import BusinessRule, Workflow, WorkflowExecution, WorkflowTemplate

        out: list[dict[str, Any]] = []
        remaining = limit

        workflows = await db.execute(
            select(Workflow).where(
                Workflow.organization_id == organization_id,
                or_(
                    func_lower(Workflow.name).like(pattern),
                    func_lower(Workflow.description).like(pattern),
                ),
            ).limit(remaining)
        )
        for w in workflows.scalars().all():
            out.append({
                "type": "workflow",
                "id": w.id,
                "title": w.name,
                "subtitle": f"Workflow · {w.category} · {w.status}",
                "url": f"/automation?tab=workflows&workflow={w.id}",
                "snippet": (w.description or "")[:120],
                "score": 0.85,
                "metadata": {"category": w.category, "status": w.status},
            })
        remaining = limit - len(out)

        if remaining > 0:
            rules = await db.execute(
                select(BusinessRule).where(
                    BusinessRule.organization_id == organization_id,
                    func_lower(BusinessRule.name).like(pattern),
                ).limit(remaining)
            )
            for rule in rules.scalars().all():
                out.append({
                    "type": "business_rule",
                    "id": rule.id,
                    "title": rule.name,
                    "subtitle": f"Rule · {rule.event_name} · {'enabled' if rule.enabled else 'disabled'}",
                    "url": "/automation?tab=rules",
                    "snippet": (rule.description or "")[:120],
                    "score": 0.7,
                    "metadata": {"event_name": rule.event_name, "enabled": rule.enabled},
                })
        remaining = limit - len(out)

        if remaining > 0:
            templates = await db.execute(
                select(WorkflowTemplate).where(
                    func_lower(WorkflowTemplate.name).like(pattern),
                ).limit(remaining)
            )
            for template in templates.scalars().all():
                out.append({
                    "type": "workflow_template",
                    "id": template.id,
                    "title": template.name,
                    "subtitle": f"Template · {template.category}",
                    "url": "/automation?tab=templates",
                    "snippet": (template.description or "")[:120],
                    "score": 0.6,
                    "metadata": {"category": template.category, "is_system": template.is_system},
                })
        remaining = limit - len(out)

        if remaining > 0:
            executions = await db.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.organization_id == organization_id,
                    func_lower(WorkflowExecution.workflow_name).like(pattern),
                ).limit(remaining)
            )
            for execution in executions.scalars().all():
                out.append({
                    "type": "workflow_execution",
                    "id": execution.id,
                    "title": execution.workflow_name or "Execution",
                    "subtitle": f"Execution · {execution.status} · {execution.trigger_source}",
                    "url": f"/automation?tab=executions&execution={execution.id}",
                    "snippet": execution.error or "Workflow run",
                    "score": 0.5,
                    "metadata": {"status": execution.status},
                })
        return out

    async def _search_enterprise(
        self, db: AsyncSession, *, organization_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 15 — index plugins, integrations, marketplace items, feature
        flags, security events, compliance controls and identity providers in
        universal search."""
        from app.models.enterprise import (
            ComplianceControl,
            FeatureFlag,
            IdentityProvider,
            IntegrationConnection,
            MarketplaceItem,
            Plugin,
            SecurityEvent,
        )

        out: list[dict[str, Any]] = []
        remaining = limit

        def _hit(type_name: str, url: str, title: str, subtitle: str,
                 snippet: str, score: float, metadata: dict[str, Any]) -> None:
            nonlocal remaining
            if remaining <= 0:
                return
            out.append({
                "type": type_name,
                "id": title,
                "title": title,
                "subtitle": subtitle,
                "url": url,
                "snippet": snippet[:120],
                "score": score,
                "metadata": metadata,
            })
            remaining -= 1

        plugins = await db.execute(
            select(Plugin).where(
                Plugin.organization_id == organization_id,
                or_(
                    func_lower(Plugin.name).like(pattern),
                    func_lower(Plugin.plugin_key).like(pattern),
                ),
            ).limit(remaining)
        )
        for plugin in plugins.scalars().all():
            _hit("plugin", f"/enterprise?tab=plugins&plugin={plugin.id}", plugin.name,
                 f"Plugin · {plugin.category} · {plugin.status} · v{plugin.version}",
                 plugin.description or "", 0.8,
                 {"category": plugin.category, "status": plugin.status, "version": plugin.version})

        if remaining > 0:
            integrations = await db.execute(
                select(IntegrationConnection).where(
                    IntegrationConnection.organization_id == organization_id,
                    func_lower(IntegrationConnection.name).like(pattern),
                ).limit(remaining)
            )
            for connection in integrations.scalars().all():
                _hit("integration", f"/enterprise?tab=integrations&integration={connection.id}",
                     connection.name,
                     f"Integration · {connection.provider} · {connection.status}",
                     connection.error or "Integration connection", 0.7,
                     {"provider": connection.provider, "status": connection.status})

        if remaining > 0:
            items = await db.execute(
                select(MarketplaceItem).where(
                    MarketplaceItem.published.is_(True),
                    or_(
                        func_lower(MarketplaceItem.name).like(pattern),
                        func_lower(MarketplaceItem.plugin_key).like(pattern),
                    ),
                ).limit(remaining)
            )
            for item in items.scalars().all():
                _hit("marketplace_item", f"/enterprise?tab=marketplace&item={item.id}",
                     item.name,
                     f"Marketplace · {item.category} · ★{item.rating} · {item.downloads} downloads",
                     item.description or "", 0.6,
                     {"category": item.category, "price": item.price})

        if remaining > 0:
            flags = await db.execute(
                select(FeatureFlag).where(
                    FeatureFlag.organization_id == organization_id,
                    or_(
                        func_lower(FeatureFlag.name).like(pattern),
                        func_lower(FeatureFlag.key).like(pattern),
                    ),
                ).limit(remaining)
            )
            for flag in flags.scalars().all():
                _hit("feature_flag", f"/enterprise?tab=flags&flag={flag.id}",
                     f"{flag.name} ({flag.key})",
                     f"Feature flag · {'enabled' if flag.enabled else 'disabled'}",
                     flag.description or "", 0.5,
                     {"key": flag.key, "enabled": flag.enabled})

        if remaining > 0:
            events = await db.execute(
                select(SecurityEvent).where(
                    SecurityEvent.organization_id == organization_id,
                    func_lower(SecurityEvent.title).like(pattern),
                ).limit(remaining)
            )
            for event in events.scalars().all():
                _hit("security_event", f"/enterprise?tab=security&event={event.id}",
                     event.title,
                     f"Security · {event.severity} · {event.status}",
                     f"{event.event_type} · {event.source_ip or 'no source'}", 0.5,
                     {"severity": event.severity, "status": event.status})

        if remaining > 0:
            controls = await db.execute(
                select(ComplianceControl).where(
                    ComplianceControl.organization_id == organization_id,
                    or_(
                        func_lower(ComplianceControl.title).like(pattern),
                        func_lower(ComplianceControl.control).like(pattern),
                    ),
                ).limit(remaining)
            )
            for control in controls.scalars().all():
                _hit("compliance_control", f"/enterprise?tab=compliance&control={control.id}",
                     f"{control.framework.upper()} · {control.control}",
                     f"Compliance · {control.status}",
                     control.title, 0.4,
                     {"framework": control.framework, "status": control.status})

        if remaining > 0:
            providers = await db.execute(
                select(IdentityProvider).where(
                    IdentityProvider.organization_id == organization_id,
                    func_lower(IdentityProvider.name).like(pattern),
                ).limit(remaining)
            )
            for provider in providers.scalars().all():
                _hit("identity_provider", f"/enterprise?tab=identity&provider={provider.id}",
                     provider.name,
                     f"Identity · {provider.provider_type} · {'enabled' if provider.enabled else 'disabled'}",
                     provider.description or "", 0.4,
                     {"provider_type": provider.provider_type, "enabled": provider.enabled})
        return out

    async def _search_infrastructure(
        self, db: AsyncSession, *, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 16 — index cloud regions, deployments, backups, cluster nodes,
        DR runs, autoscaling events and chaos runs in universal search."""
        from app.models.infrastructure import (
            AutoscalingEvent,
            BackupRecord,
            ChaosRun,
            CloudRegion,
            ClusterStatus,
            DeploymentRecord,
            DisasterRecoveryLog,
        )

        out: list[dict[str, Any]] = []
        remaining = limit

        def _hit(type_name: str, url: str, title: str, subtitle: str,
                 snippet: str, score: float, metadata: dict[str, Any]) -> None:
            nonlocal remaining
            if remaining <= 0:
                return
            out.append({
                "type": type_name,
                "id": title,
                "title": title,
                "subtitle": subtitle,
                "url": url,
                "snippet": snippet[:120],
                "score": score,
                "metadata": metadata,
            })
            remaining -= 1

        regions = await db.execute(
            select(CloudRegion).where(func_lower(CloudRegion.name).like(pattern)).limit(remaining)
        )
        for region in regions.scalars().all():
            _hit("cloud_region", f"/infrastructure?tab=regions&region={region.id}",
                 region.name,
                 f"Region · {region.provider} · {region.location or 'unknown'} · {region.status}",
                 f"{region.continent} · {region.latency_ms}ms · {region.load_percent}% load", 0.6,
                 {"provider": region.provider, "status": region.status, "latency_ms": region.latency_ms})

        if remaining > 0:
            deployments = await db.execute(
                select(DeploymentRecord).where(func_lower(DeploymentRecord.service).like(pattern)).limit(remaining)
            )
            for deployment in deployments.scalars().all():
                _hit("deployment", f"/infrastructure?tab=deployments&deployment={deployment.id}",
                     f"{deployment.service} · v{deployment.version}",
                     f"Deployment · {deployment.strategy} · {deployment.status}",
                     f"{deployment.region or 'all regions'} · {deployment.canary_percentage}% canary", 0.5,
                     {"strategy": deployment.strategy, "status": deployment.status, "version": deployment.version})

        if remaining > 0:
            backups = await db.execute(
                select(BackupRecord).where(func_lower(BackupRecord.target).like(pattern)).limit(remaining)
            )
            for backup in backups.scalars().all():
                _hit("backup", f"/infrastructure?tab=backups&backup={backup.id}",
                     f"Backup · {backup.target} · {backup.kind}",
                     f"Backup · {backup.status} · {backup.region or 'all regions'}",
                     f"{backup.size_bytes} bytes · {'verified' if backup.verified else 'not verified'}", 0.5,
                     {"kind": backup.kind, "status": backup.status, "target": backup.target})

        if remaining > 0:
            clusters = await db.execute(
                select(ClusterStatus).where(
                    or_(
                        func_lower(ClusterStatus.name).like(pattern),
                        func_lower(ClusterStatus.region).like(pattern),
                        func_lower(ClusterStatus.cluster_type).like(pattern),
                    )
                ).limit(remaining)
            )
            for cluster in clusters.scalars().all():
                _hit("cluster", f"/infrastructure?tab=clusters&cluster={cluster.id}",
                     cluster.name,
                     f"Cluster · {cluster.cluster_type} · {cluster.role} · {cluster.status}",
                     f"{cluster.region or 'no region'} · {cluster.healthy_nodes}/{cluster.total_nodes} nodes", 0.5,
                     {"cluster_type": cluster.cluster_type, "role": cluster.role, "status": cluster.status})

        if remaining > 0:
            runs = await db.execute(
                select(DisasterRecoveryLog).where(func_lower(DisasterRecoveryLog.scenario).like(pattern)).limit(remaining)
            )
            for run in runs.scalars().all():
                _hit("dr_run", f"/infrastructure?tab=dr&run={run.id}",
                     f"DR · {run.scenario}",
                     f"Disaster recovery · {run.status} · {run.region or 'all regions'}",
                     f"RPO {run.rpo_minutes}m · RTO {run.rto_minutes}m · {run.outcome or 'in progress'}", 0.4,
                     {"scenario": run.scenario, "status": run.status})

        if remaining > 0:
            events = await db.execute(
                select(AutoscalingEvent).where(func_lower(AutoscalingEvent.resource).like(pattern)).limit(remaining)
            )
            for event in events.scalars().all():
                _hit("autoscaling", f"/infrastructure?tab=autoscaling&event={event.id}",
                     f"Autoscale · {event.resource} · {event.direction}",
                     f"Autoscaling · {event.status} · {event.region or 'all regions'}",
                     f"{event.from_capacity} -> {event.to_capacity} · {event.metric} {event.observed}", 0.4,
                     {"resource": event.resource, "direction": event.direction, "status": event.status})

        if remaining > 0:
            chaos = await db.execute(
                select(ChaosRun).where(func_lower(ChaosRun.scenario).like(pattern)).limit(remaining)
            )
            for run in chaos.scalars().all():
                _hit("chaos_run", f"/infrastructure?tab=chaos&run={run.id}",
                     f"Chaos · {run.scenario}",
                     f"Reliability · {run.status} · {run.target_service or 'no target'}",
                     f"{run.target_region or 'all regions'} · {run.summary or run.expected_impact or ''}", 0.4,
                     {"scenario": run.scenario, "status": run.status})
        return out


    async def _search_industry(
        self, db: AsyncSession, *, organization_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 17 — index installed industry packs, selected industries,
        activated industry workflows and compliance checks in universal search."""
        from app.models.industry import Industry, IndustrySelection
        from app.models.industry_configuration import IndustryConfiguration, IndustryWorkflow

        out: list[dict[str, Any]] = []
        remaining = limit

        def _hit(type_name: str, url: str, title: str, subtitle: str,
                 snippet: str, score: float, metadata: dict[str, Any]) -> None:
            nonlocal remaining
            if remaining <= 0:
                return
            out.append({
                "type": type_name,
                "id": title,
                "title": title,
                "subtitle": subtitle,
                "url": url,
                "snippet": snippet[:120],
                "score": score,
                "metadata": metadata,
            })
            remaining -= 1

        if remaining > 0:
            selections = await db.execute(
                select(IndustrySelection)
                .where(
                    IndustrySelection.organization_id == organization_id,
                    IndustrySelection.status == "active",
                )
                .limit(remaining)
            )
            for selection in selections.scalars().all():
                _hit("industry", f"/industry?tab=installed&key={selection.industry_key}",
                     selection.industry_key.title(),
                     f"Industry · {selection.business_type or 'any business type'} · {selection.country or 'any country'}",
                     f"Selected vertical · {selection.role} · {', '.join(selection.regulations or []) or 'no regulations'}", 0.7,
                     {"industry_key": selection.industry_key, "role": selection.role})

        if remaining > 0:
            industries = await db.execute(
                select(Industry).where(func_lower(Industry.name).like(pattern)).limit(remaining)
            )
            for industry in industries.scalars().all():
                _hit("industry_pack", f"/industry?tab=catalog&key={industry.industry_key}",
                     industry.name,
                     f"Industry pack · {industry.industry_key} · {len(industry.modules or [])} modules",
                     industry.description or "", 0.5,
                     {"industry_key": industry.industry_key, "kpis": len(industry.kpis or [])})

        if remaining > 0:
            workflows = await db.execute(
                select(IndustryWorkflow).where(
                    IndustryWorkflow.organization_id == organization_id,
                    or_(
                        func_lower(IndustryWorkflow.name).like(pattern),
                        func_lower(IndustryWorkflow.industry_key).like(pattern),
                    ),
                ).limit(remaining)
            )
            for workflow in workflows.scalars().all():
                _hit("industry_workflow", f"/industry?tab=workflows&workflow={workflow.id}",
                     workflow.name,
                     f"Industry workflow · {workflow.industry_key} · {workflow.status}",
                     f"{workflow.current_step or 'no step'} · {workflow.progress}% · {workflow.template_key}", 0.5,
                     {"industry_key": workflow.industry_key, "status": workflow.status, "template_key": workflow.template_key})

        if remaining > 0:
            configs = await db.execute(
                select(IndustryConfiguration).where(
                    IndustryConfiguration.organization_id == organization_id,
                    IndustryConfiguration.status != "uninstalled",
                    or_(
                        func_lower(IndustryConfiguration.industry_key).like(pattern),
                        func_lower(IndustryConfiguration.pack_version).like(pattern),
                    ),
                ).limit(remaining)
            )
            for config in configs.scalars().all():
                _hit("industry_pack_config", f"/industry?tab=installed&key={config.industry_key}",
                     f"{config.industry_key.title()} pack",
                     f"Installed · {config.status} · v{config.pack_version}",
                     f"{len(config.modules_enabled or [])} modules enabled", 0.4,
                     {"industry_key": config.industry_key, "status": config.status})
        return out

    async def _search_digital_twin(
        self, db: AsyncSession, *, organization_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 18 — index twin state, predictions, recommendations, simulations,
        forecasts, optimizations and decisions in universal search."""
        from app.digital_twin.decision_service import decision_service
        from app.digital_twin.forecasting_service import forecasting_service
        from app.digital_twin.optimization_service import optimization_service
        from app.digital_twin.prediction_service import prediction_service
        from app.digital_twin.recommendation_service import recommendation_service
        from app.digital_twin.simulation_service import simulation_service
        from app.digital_twin.twin_service import digital_twin_service

        out: list[dict[str, Any]] = []
        remaining = limit

        def _hit(type_name: str, url: str, title: str, subtitle: str,
                 snippet: str, score: float, metadata: dict[str, Any]) -> None:
            nonlocal remaining
            if remaining <= 0:
                return
            out.append({
                "type": type_name,
                "id": title,
                "title": title,
                "subtitle": subtitle,
                "url": url,
                "snippet": snippet[:120],
                "score": score,
                "metadata": metadata,
            })
            remaining -= 1

        if remaining > 0:
            twin = await digital_twin_service.get_twin(db, organization_id)
            if twin is not None:
                try:
                    counts = json.loads(twin.entity_counts_json or "{}")
                except (json.JSONDecodeError, TypeError):
                    counts = {}
                _hit("digital_twin", "/intelligence?tab=twin",
                     f"Digital twin of {twin.organization_id[:8]}",
                     f"Last refreshed {twin.last_refreshed_at or twin.updated_at} · {twin.refresh_count} refreshes",
                     f"{counts.get('employees', 0)} employees · {counts.get('projects', 0)} projects · "
                     f"{counts.get('open_tasks', 0)} open tasks · health {twin.health_score or 0}/100", 0.6,
                     {"health": twin.health_score, "health_status": twin.health_status})

        if remaining > 0:
            predictions = await prediction_service.list(db, organization_id, status="active", limit=remaining)
            for p in predictions:
                _hit("prediction", "/intelligence?tab=predictions",
                     p["title"], f"Prediction · {p['level']} · {p['probability']}%",
                     p.get("recommended_action") or p.get("description") or "Explainable prediction", 0.55,
                     {"kind": p["kind"], "level": p["level"], "probability": p["probability"]})

        if remaining > 0:
            recommendations = await recommendation_service.list(db, organization_id, status="active", limit=remaining)
            for r in recommendations:
                _hit("recommendation", "/intelligence?tab=recommendations",
                     r["title"], f"Recommendation · {r.get('priority') or r.get('impact') or 'medium'} priority",
                     r.get("rationale") or "Executive recommendation", 0.5,
                     {"priority": r.get("priority") or r.get("impact") or "medium", "status": r["status"]})

        if remaining > 0:
            simulations = await simulation_service.list(db, organization_id, limit=remaining)
            for s in simulations:
                _hit("simulation", "/intelligence?tab=simulations",
                     s["title"], f"Simulation · {s['scenario']} · risk {s['results'].get('risk', 0)}/100",
                     s.get("summary") or "What-if simulation result", 0.45,
                     {"scenario": s["scenario"], "status": s["status"]})

        if remaining > 0:
            forecasts = await forecasting_service.list(db, organization_id, limit=remaining)
            for f in forecasts:
                _hit("forecast", "/intelligence?tab=strategy",
                     f"{f['dimension'].replace('_', ' ').title()} forecast",
                     f"Forecast · {f['trend']} · {f['horizon_days']} days",
                     f"Series of {len(f['series'])} points · latest ~{f['series'][-1]['value'] if f['series'] else 0}", 0.45,
                     {"dimension": f["dimension"], "trend": f["trend"]})

        if remaining > 0:
            optimizations = await optimization_service.list(db, organization_id, status="suggested", limit=remaining)
            for o in optimizations:
                _hit("optimization", "/intelligence?tab=optimize",
                     o["title"], f"Optimization · impact {o['impact']} · effort {o['effort']}",
                     o.get("rationale") or "Optimization suggestion", 0.4,
                     {"kind": o["kind"], "status": o["status"]})

        if remaining > 0:
            decisions = await decision_service.list(db, organization_id, limit=remaining)
            for d in decisions:
                _hit("decision", "/intelligence?tab=decisions",
                     d["decision"][:80], f"Decision · {d['category']} · {d['status']}",
                     d.get("reason") or "Stored executive decision", 0.4,
                     {"category": d["category"], "status": d["status"]})
        return out

    async def _search_developers(
        self, db: AsyncSession, *, organization_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 18 — index developer applications, apps, agents, webhooks,
        marketplace listings and certifications in universal search."""
        from app.models.developer import (
            AIAgent,
            DeveloperApplication,
            WebhookEndpoint,
        )

        out: list[dict[str, Any]] = []
        remaining = limit

        def _hit(type_name: str, url: str, title: str, subtitle: str,
                 snippet: str, score: float, metadata: dict[str, Any]) -> None:
            nonlocal remaining
            if remaining <= 0:
                return
            out.append({
                "type": type_name,
                "id": title,
                "title": title,
                "subtitle": subtitle,
                "url": url,
                "snippet": snippet[:120],
                "score": score,
                "metadata": metadata,
            })
            remaining -= 1

        if remaining > 0:
            from app.models.developer import Developer
            from app.models.user import User as SearchUser

            dev_ids = (
                select(Developer.id)
                .join(SearchUser, SearchUser.id == Developer.user_id)
                .where(SearchUser.organization_id == organization_id)
            )
            apps = await db.execute(
                select(DeveloperApplication).where(
                    DeveloperApplication.developer_id.in_(dev_ids),
                    func_lower(DeveloperApplication.name).like(pattern),
                ).limit(remaining)
            )
            for app in apps.scalars().all():
                _hit("developer_app", "/developers?tab=apps",
                     app.name,
                     f"Developer app · {app.app_type} · {app.status}",
                     f"{app.description or 'Developer application'}", 0.55,
                     {"status": app.status, "app_type": app.app_type})

        if remaining > 0:
            agents = await db.execute(
                select(AIAgent).where(
                    AIAgent.organization_id == organization_id,
                    or_(
                        func_lower(AIAgent.name).like(pattern),
                        func_lower(AIAgent.description).like(pattern),
                    ),
                ).limit(remaining)
            )
            for agent in agents.scalars().all():
                _hit("agent", "/developers?tab=agents",
                     agent.name,
                     f"AI agent · {agent.status} · {agent.role}",
                     agent.description or "AI agent", 0.5,
                     {"status": agent.status, "role": agent.role})

        if remaining > 0:
            webhooks = await db.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.organization_id == organization_id,
                    func_lower(WebhookEndpoint.url).like(pattern),
                ).limit(remaining)
            )
            for hook in webhooks.scalars().all():
                _hit("webhook", "/developers?tab=webhooks",
                     hook.url[:60], f"Webhook · {hook.status}",
                     f"Events: {', '.join((hook.events or [])[:4])}", 0.4,
                     {"status": hook.status, "secret_configured": bool(hook.secret)})
        return out

    async def _search_memory(
        self, db: AsyncSession, *, organization_id: str, pattern: str, limit: int
    ) -> list[dict[str, Any]]:
        """Phase 19 — index company memory, timeline entries and context bundles."""
        from app.memory.memory_service import memory_service
        from app.memory.timeline_service import timeline_service

        out: list[dict[str, Any]] = []
        remaining = limit

        def _hit(type_name: str, url: str, title: str, subtitle: str,
                 snippet: str, score: float, metadata: dict[str, Any]) -> None:
            nonlocal remaining
            if remaining <= 0:
                return
            out.append({
                "type": type_name,
                "id": title,
                "title": title,
                "subtitle": subtitle,
                "url": url,
                "snippet": snippet[:120],
                "score": score,
                "metadata": metadata,
            })
            remaining -= 1

        if remaining > 0:
            memories = await memory_service.list(
                db, organization_id, search=pattern.lstrip("%").rstrip("%"), limit=remaining
            )
            for m in memories:
                _hit("memory", "/memory",
                     m["title"], f"Company memory · {m['memory_type']} · {m['importance']}",
                     m.get("content") or "Permanent organizational memory", 0.6,
                     {"memory_type": m["memory_type"], "importance": m["importance"], "pinned": m["pinned"]})

        if remaining > 0:
            entries = await timeline_service.list(
                db, organization_id, search=pattern.lstrip("%").rstrip("%"), limit=remaining
            )
            for e in entries:
                _hit("timeline", "/memory?tab=timeline",
                     e["title"], f"Timeline · {e['category']}",
                     e.get("detail") or "Organization timeline entry", 0.5,
                     {"category": e["category"], "event_type": e["event_type"]})
        return out


def func_lower(column):
    from sqlalchemy import func

    return func.lower(column)


def _cap(remaining: int, want: int) -> int:
    return max(1, min(remaining, want))


search_service = SearchService()
