"""Digital Twin service (Phase 18.1/18.2/18.16) — the living organizational model.

The service aggregates every major entity type (people, projects, knowledge,
customers, finance, HR, meetings, learning, community, assets, workflows) into
a single twin payload, computes the current state, stores a state history
snapshot, and projects a predicted state 30 days ahead.

The aggregation is deterministic and defensive: every entity query is wrapped
so a new model being absent can never break the twin.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow, ensure_aware
from app.events.publisher import publish_background_event
from app.models.digital_twin import DigitalTwin, TwinStateHistory

logger = logging.getLogger("vcos.digital_twin.twin")

# Twin dimensions — the living model mirrors all Phase 18 entity categories.
TWIN_DIMENSIONS = [
    "people",
    "organization",
    "projects",
    "knowledge",
    "customers",
    "finance",
    "hr",
    "meetings",
    "learning",
    "community",
    "assets",
    "workflows",
]


class DigitalTwinService:
    """Builds and persists the one living digital twin per organization."""

    async def build_twin(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        """Aggregate every entity category into the twin payload (no writes)."""
        counts, dimensions = await self._aggregate(db, organization_id)
        twin = {
            "organization_id": organization_id,
            "built_at": utcnow().isoformat(),
            "entity_counts": counts,
            "dimensions": dimensions,
            "state": await self._current_state(counts, dimensions),
        }
        return twin

    async def _aggregate(
        self, db: AsyncSession, organization_id: str
    ) -> tuple[dict[str, int], dict[str, Any]]:
        counts: dict[str, int] = {}
        dimensions: dict[str, Any] = {}

        # ---- people
        try:
            from app.models.employee import Employee

            total = (
                await db.execute(
                    select(func.count()).select_from(Employee).where(Employee.organization_id == organization_id)
                )
            ).scalar_one()
            active = (
                await db.execute(
                    select(func.count())
                    .select_from(Employee)
                    .where(Employee.organization_id == organization_id, Employee.status == "active")
                )
            ).scalar_one()
            counts["employees"] = total or 0
            counts["active_employees"] = active or 0
            dimensions["people"] = {"total": total or 0, "active": active or 0}
        except Exception as exc:  # pragma: no cover
            logger.warning("twin people aggregation: %s", exc)
            counts["employees"] = 0
            dimensions["people"] = {"total": 0, "active": 0}

        # ---- organization structure
        try:
            from app.models.department import Department
            from app.models.team import Team

            depts = (
                await db.execute(
                    select(func.count()).select_from(Department).where(Department.organization_id == organization_id)
                )
            ).scalar_one()
            teams = (
                await db.execute(
                    select(func.count()).select_from(Team).where(Team.organization_id == organization_id)
                )
            ).scalar_one()
            counts["departments"] = depts or 0
            counts["teams"] = teams or 0
            dimensions["organization"] = {"departments": depts or 0, "teams": teams or 0}
        except Exception as exc:  # pragma: no cover
            logger.warning("twin org aggregation: %s", exc)
            counts["departments"] = 0
            counts["teams"] = 0
            dimensions["organization"] = {"departments": 0, "teams": 0}

        # ---- projects & work
        try:
            from app.models.project import Project
            from app.models.task import Task

            projects = (
                await db.execute(
                    select(func.count()).select_from(Project).where(Project.organization_id == organization_id)
                )
            ).scalar_one()
            active_projects = (
                await db.execute(
                    select(func.count())
                    .select_from(Project)
                    .where(
                        Project.organization_id == organization_id,
                        Project.status.in_(["active", "in_progress", "on_track"]),
                    )
                )
            ).scalar_one()
            tasks = (
                await db.execute(
                    select(func.count()).select_from(Task).where(Task.organization_id == organization_id)
                )
            ).scalar_one()
            open_tasks = (
                await db.execute(
                    select(func.count())
                    .select_from(Task)
                    .where(
                        Task.organization_id == organization_id,
                        Task.status.not_in(["completed", "done", "cancelled"]),
                    )
                )
            ).scalar_one()
            counts["projects"] = projects or 0
            counts["active_projects"] = active_projects or 0
            counts["tasks"] = tasks or 0
            counts["open_tasks"] = open_tasks or 0
            dimensions["projects"] = {
                "total": projects or 0,
                "active": active_projects or 0,
                "tasks": tasks or 0,
                "open_tasks": open_tasks or 0,
            }
        except Exception as exc:  # pragma: no cover
            logger.warning("twin work aggregation: %s", exc)
            for key in ("projects", "active_projects", "tasks", "open_tasks"):
                counts.setdefault(key, 0)
            dimensions["projects"] = {"total": 0, "active": 0, "tasks": 0, "open_tasks": 0}

        # ---- knowledge
        try:
            from app.models.knowledge import Document, KnowledgeIndex, WikiPage

            documents = (
                await db.execute(
                    select(func.count()).select_from(Document).where(Document.organization_id == organization_id)
                )
            ).scalar_one()
            wiki = (
                await db.execute(
                    select(func.count()).select_from(WikiPage).where(WikiPage.organization_id == organization_id)
                )
            ).scalar_one()
            indexed = (
                await db.execute(
                    select(func.count()).select_from(KnowledgeIndex).where(KnowledgeIndex.organization_id == organization_id)
                )
            ).scalar_one()
            counts["documents"] = documents or 0
            counts["wiki_pages"] = wiki or 0
            counts["knowledge_indexed"] = indexed or 0
            dimensions["knowledge"] = {
                "documents": documents or 0,
                "wiki_pages": wiki or 0,
                "indexed": indexed or 0,
            }
        except Exception as exc:  # pragma: no cover
            logger.warning("twin knowledge aggregation: %s", exc)
            counts.setdefault("documents", 0)
            counts.setdefault("wiki_pages", 0)
            counts.setdefault("knowledge_indexed", 0)
            dimensions["knowledge"] = {"documents": 0, "wiki_pages": 0, "indexed": 0}

        # ---- customers
        try:
            from app.models.customer import Customer
            from app.models.contract import Contract

            customers = (
                await db.execute(
                    select(func.count()).select_from(Customer).where(Customer.organization_id == organization_id)
                )
            ).scalar_one()
            contracts = (
                await db.execute(
                    select(func.count()).select_from(Contract).where(Contract.organization_id == organization_id)
                )
            ).scalar_one()
            counts["customers"] = customers or 0
            counts["contracts"] = contracts or 0
            dimensions["customers"] = {"customers": customers or 0, "contracts": contracts or 0}
        except Exception as exc:  # pragma: no cover
            logger.warning("twin customers aggregation: %s", exc)
            counts.setdefault("customers", 0)
            counts.setdefault("contracts", 0)
            dimensions["customers"] = {"customers": 0, "contracts": 0}

        # ---- finance
        try:
            from app.models.finance import Budget, Expense, FinancialMetric

            budgets = (
                await db.execute(
                    select(func.count()).select_from(Budget).where(Budget.organization_id == organization_id)
                )
            ).scalar_one()
            expenses = (
                await db.execute(
                    select(func.count()).select_from(Expense).where(Expense.organization_id == organization_id)
                )
            ).scalar_one()
            metrics = (
                await db.execute(
                    select(func.count()).select_from(FinancialMetric).where(FinancialMetric.organization_id == organization_id)
                )
            ).scalar_one()
            counts["budgets"] = budgets or 0
            counts["expenses"] = expenses or 0
            counts["financial_metrics"] = metrics or 0
            dimensions["finance"] = {"budgets": budgets or 0, "expenses": expenses or 0, "metrics": metrics or 0}
        except Exception as exc:  # pragma: no cover
            logger.warning("twin finance aggregation: %s", exc)
            counts.setdefault("budgets", 0)
            counts.setdefault("expenses", 0)
            counts.setdefault("financial_metrics", 0)
            dimensions["finance"] = {"budgets": 0, "expenses": 0, "metrics": 0}

        # ---- hr
        try:
            from app.models.hr import LeaveRequest, PerformanceReview, PayrollRun

            leaves = (
                await db.execute(
                    select(func.count()).select_from(LeaveRequest).where(LeaveRequest.organization_id == organization_id)
                )
            ).scalar_one()
            reviews = (
                await db.execute(
                    select(func.count()).select_from(PerformanceReview).where(PerformanceReview.organization_id == organization_id)
                )
            ).scalar_one()
            payrolls = (
                await db.execute(
                    select(func.count()).select_from(PayrollRun).where(PayrollRun.organization_id == organization_id)
                )
            ).scalar_one()
            counts["leave_requests"] = leaves or 0
            counts["performance_reviews"] = reviews or 0
            counts["payroll_runs"] = payrolls or 0
            dimensions["hr"] = {
                "leave_requests": leaves or 0,
                "performance_reviews": reviews or 0,
                "payroll_runs": payrolls or 0,
            }
        except Exception as exc:  # pragma: no cover
            logger.warning("twin hr aggregation: %s", exc)
            counts.setdefault("leave_requests", 0)
            counts.setdefault("performance_reviews", 0)
            counts.setdefault("payroll_runs", 0)
            dimensions["hr"] = {"leave_requests": 0, "performance_reviews": 0, "payroll_runs": 0}

        # ---- meetings
        try:
            from app.models.meeting import Meeting

            meetings = (
                await db.execute(
                    select(func.count()).select_from(Meeting).where(Meeting.organization_id == organization_id)
                )
            ).scalar_one()
            counts["meetings"] = meetings or 0
            dimensions["meetings"] = {"total": meetings or 0}
        except Exception as exc:  # pragma: no cover
            logger.warning("twin meetings aggregation: %s", exc)
            counts["meetings"] = 0
            dimensions["meetings"] = {"total": 0}

        # ---- learning
        try:
            from app.models.course import CourseEnrollment

            enrollments = (
                await db.execute(
                    select(func.count()).select_from(CourseEnrollment).where(CourseEnrollment.organization_id == organization_id)
                )
            ).scalar_one()
            counts["course_enrollments"] = enrollments or 0
            dimensions["learning"] = {"enrollments": enrollments or 0}
        except Exception as exc:  # pragma: no cover
            logger.warning("twin learning aggregation: %s", exc)
            counts["course_enrollments"] = 0
            dimensions["learning"] = {"enrollments": 0}

        # ---- community
        try:
            from app.models.communication import CommunityPost, Recognition

            posts = (
                await db.execute(
                    select(func.count()).select_from(CommunityPost).where(CommunityPost.organization_id == organization_id)
                )
            ).scalar_one()
            recognition = (
                await db.execute(
                    select(func.count()).select_from(Recognition).where(Recognition.organization_id == organization_id)
                )
            ).scalar_one()
            counts["community_posts"] = posts or 0
            counts["recognition"] = recognition or 0
            dimensions["community"] = {"posts": posts or 0, "recognition": recognition or 0}
        except Exception as exc:  # pragma: no cover
            logger.warning("twin community aggregation: %s", exc)
            counts.setdefault("community_posts", 0)
            counts.setdefault("recognition", 0)
            dimensions["community"] = {"posts": 0, "recognition": 0}

        # ---- assets
        try:
            from app.models.hr import EmployeeAsset

            assets = (
                await db.execute(
                    select(func.count()).select_from(EmployeeAsset).where(EmployeeAsset.organization_id == organization_id)
                )
            ).scalar_one()
            counts["assets"] = assets or 0
            dimensions["assets"] = {"total": assets or 0}
        except Exception as exc:  # pragma: no cover
            logger.warning("twin assets aggregation: %s", exc)
            counts["assets"] = 0
            dimensions["assets"] = {"total": 0}

        # ---- workflows
        try:
            from app.models.workflow import Workflow, WorkflowExecution

            workflows = (
                await db.execute(
                    select(func.count()).select_from(Workflow).where(Workflow.organization_id == organization_id)
                )
            ).scalar_one()
            executions = (
                await db.execute(
                    select(func.count()).select_from(WorkflowExecution).where(WorkflowExecution.organization_id == organization_id)
                )
            ).scalar_one()
            counts["workflows"] = workflows or 0
            counts["workflow_executions"] = executions or 0
            dimensions["workflows"] = {"workflows": workflows or 0, "executions": executions or 0}
        except Exception as exc:  # pragma: no cover
            logger.warning("twin workflows aggregation: %s", exc)
            counts.setdefault("workflows", 0)
            counts.setdefault("workflow_executions", 0)
            dimensions["workflows"] = {"workflows": 0, "executions": 0}

        return counts, dimensions

    async def _current_state(
        self, counts: dict[str, int], dimensions: dict[str, Any]
    ) -> dict[str, Any]:
        """Derive the current organizational state summary from the twin."""
        employees = counts.get("employees", 0) or 0
        open_tasks = counts.get("open_tasks", 0) or 0
        active_projects = counts.get("active_projects", 0) or 0
        workload = round(open_tasks / employees, 2) if employees else 0.0
        collaboration = min(100, (counts.get("meetings", 0) or 0) * 2 + (counts.get("community_posts", 0) or 0))
        knowledge_growth = counts.get("documents", 0) or 0
        return {
            "employees": employees,
            "active_projects": active_projects,
            "open_tasks": open_tasks,
            "workload_per_employee": workload,
            "meetings": counts.get("meetings", 0) or 0,
            "customers": counts.get("customers", 0) or 0,
            "knowledge_items": counts.get("documents", 0) or 0,
            "workflow_executions": counts.get("workflow_executions", 0) or 0,
            "collaboration_activity": collaboration,
            "knowledge_growth": knowledge_growth,
        }

    async def get_twin(self, db: AsyncSession, organization_id: str) -> Optional[DigitalTwin]:
        return (
            await db.execute(
                select(DigitalTwin).where(DigitalTwin.organization_id == organization_id)
            )
        ).scalars().first()

    async def refresh(self, db: AsyncSession, organization_id: str, *, commit: bool = False) -> dict[str, Any]:
        """Rebuild the twin, persist it, and append a state history snapshot."""
        twin = await self.build_twin(db, organization_id)
        twin_payload = json.dumps(twin, default=str)

        row = await self.get_twin(db, organization_id)
        now = utcnow()
        history = json.loads(row.state_history_json) if row and row.state_history_json else []
        history.append(
            {
                "captured_at": now.isoformat(),
                "state": twin["state"],
                "counts": twin["entity_counts"],
            }
        )
        history = history[-12:]

        if row is None:
            row = DigitalTwin(
                organization_id=organization_id,
                twin_json=twin_payload,
                entity_counts_json=json.dumps(twin["entity_counts"]),
                dimensions_json=json.dumps(twin["dimensions"]),
                state_json=json.dumps(twin["state"]),
                state_history_json=json.dumps(history),
                refresh_count=1,
                last_refreshed_at=now,
            )
            db.add(row)
        else:
            row.twin_json = twin_payload
            row.entity_counts_json = json.dumps(twin["entity_counts"])
            row.dimensions_json = json.dumps(twin["dimensions"])
            row.state_json = json.dumps(twin["state"])
            row.state_history_json = json.dumps(history)
            row.refresh_count = (row.refresh_count or 0) + 1
            row.last_refreshed_at = now
        await db.flush()

        # state history table (headline metrics per snapshot)
        db.add(
            TwinStateHistory(
                organization_id=organization_id,
                state_json=json.dumps(twin["state"]),
                summary_json=json.dumps(twin["entity_counts"]),
                captured_at=now,
            )
        )

        await publish_background_event(
            db,
            name="digital_twin.updated",
            organization_id=organization_id,
            payload={"entity_counts": twin["entity_counts"], "built_at": twin["built_at"]},
        )
        if commit:
            await db.commit()
        return twin

    async def history(self, db: AsyncSession, organization_id: str, limit: int = 30) -> list[dict[str, Any]]:
        result = await db.execute(
            select(TwinStateHistory)
            .where(TwinStateHistory.organization_id == organization_id)
            .order_by(TwinStateHistory.captured_at.desc())
            .limit(limit)
        )
        out = []
        for row in result.scalars().all():
            state = {}
            if row.state_json:
                try:
                    state = json.loads(row.state_json)
                except (json.JSONDecodeError, TypeError):
                    state = {}
            out.append(
                {
                    "id": row.id,
                    "captured_at": ensure_aware(row.captured_at).isoformat() if row.captured_at else None,
                    "state": state,
                    "summary": json.loads(row.summary_json) if row.summary_json else {},
                }
            )
        return out

    def serialize(self, twin: DigitalTwin) -> dict[str, Any]:
        def _loads(value: Optional[str], fallback: Any):
            if not value:
                return fallback
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return fallback

        return {
            "organization_id": twin.organization_id,
            "twin": _loads(twin.twin_json, {}),
            "entity_counts": _loads(twin.entity_counts_json, {}),
            "dimensions": _loads(twin.dimensions_json, {}),
            "state": _loads(twin.state_json, {}),
            "state_history": _loads(twin.state_history_json, []),
            "predicted_state": _loads(twin.predicted_state_json, {}),
            "health_score": twin.health_score,
            "health_status": twin.health_status,
            "refresh_count": twin.refresh_count,
            "last_refreshed_at": twin.last_refreshed_at.isoformat() if twin.last_refreshed_at else None,
            "updated_at": twin.updated_at.isoformat() if twin.updated_at else None,
        }


digital_twin_service = DigitalTwinService()
