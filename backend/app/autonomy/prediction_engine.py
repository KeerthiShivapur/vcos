"""Predictive intelligence engine — predicts problems before they occur.

Cross-domain prediction kinds: project_failure, employee_burnout, customer_churn,
budget_overrun, knowledge_loss, missed_deadline, hiring_need,
infrastructure_growth, compliance_risk, innovation_decline, attrition,
skill_gap, capacity_bottleneck. Every generated prediction persists, is
explainable (signals), and is validated against historical outcomes through
PredictionHistory/PredictionModel.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.course import CourseEnrollment
from app.models.customer import Customer, CustomerHealth
from app.models.employee import Employee, EmployeeSkill
from app.models.finance import Budget
from app.models.knowledge import Document
from app.models.prediction import (
    PREDICTION_KINDS,
    Prediction,
    PredictionHistory,
    PredictionModel,
)
from app.models.project import Project
from app.models.task import Task


class PredictionEngine:
    async def generate(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        """Generate the full cross-domain prediction set for an organization."""
        now = utcnow()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        async def _count(model, **filters):
            stmt = select(func.count(model.id)).where(model.organization_id == organization_id)
            for key, value in filters.items():
                stmt = stmt.where(getattr(model, key) == value)
            return (await db.execute(stmt)).scalar() or 0

        projects = (
            await db.execute(
                select(Project).where(Project.organization_id == organization_id).limit(200)
            )
        ).scalars().all()
        tasks = (
            await db.execute(
                select(Task).where(Task.organization_id == organization_id).limit(500)
            )
        ).scalars().all()
        now_date = now.date()
        overdue = [t for t in tasks if t.due_date is not None and t.due_date < now_date
                   and t.status not in ("done", "completed", "cancelled")]
        in_progress = [t for t in tasks if t.status not in ("done", "completed", "cancelled")]
        blocked = [t for t in tasks if t.status == "blocked"]

        employees = await _count(Employee)
        skill_rows = (
            await db.execute(
                select(EmployeeSkill).join(Employee, Employee.id == EmployeeSkill.employee_id)
                .where(Employee.organization_id == organization_id).limit(500)
            )
        ).scalars().all()
        skills_by_emp: dict[str, int] = {}
        for s in skill_rows:
            skills_by_emp[getattr(s, "employee_id", "") or ""] = skills_by_emp.get(getattr(s, "employee_id", "") or "", 0) + 1
        low_skill_emp = sum(1 for v in skills_by_emp.values() if v <= 1) if skills_by_emp else 0

        docs = await _count(Document)
        docs_7d = (
            await db.execute(
                select(func.count(Document.id)).where(
                    Document.organization_id == organization_id, Document.created_at >= week_ago
                )
            )
        ).scalar() or 0
        courses_total = await _count(CourseEnrollment)
        enroll_30d = (
            await db.execute(
                select(func.count(CourseEnrollment.id)).where(
                    CourseEnrollment.organization_id == organization_id,
                    CourseEnrollment.created_at >= month_ago,
                )
            )
        ).scalar() or 0

        customers = (
            await db.execute(
                select(CustomerHealth).join(Customer, Customer.id == CustomerHealth.customer_id)
                .where(Customer.organization_id == organization_id).limit(200)
            )
        ).scalars().all()
        low_health = [c for c in customers if c.score is not None and c.score < 50]

        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.status == "active")
            )
        ).scalars().all()
        overrun = [
            b for b in budgets
            if (b.allocated_amount or 0) > 0 and (b.used_amount or 0) / b.allocated_amount > 0.9
        ]

        active_projects = [p for p in projects if p.status in ("active", "in_progress", "on_track")]
        capacity_ratio = len(in_progress) / max(employees * 3, 1)
        delay_ratio = len(overdue) / max(len(in_progress), 1)

        candidates: list[dict[str, Any]] = []

        # 1. capacity bottleneck (hiring need)
        if employees > 0 and capacity_ratio > 0.9:
            candidates.append({
                "kind": "capacity_bottleneck",
                "title": "Engineering capacity will become a bottleneck",
                "description": (
                    f"{len(in_progress)} active tasks against {employees} employees "
                    f"(utilization {round(capacity_ratio * 100, 0)}%)."
                ),
                "probability": round(min(0.95, 0.4 + capacity_ratio * 0.4), 2),
                "impact": "high", "level": "high" if capacity_ratio > 1.2 else "medium",
                "horizon_days": 60,
                "subject_type": "organization",
                "signals": [{"metric": "task_per_employee", "value": round(capacity_ratio, 2)}],
            })

        # 2. missed deadlines
        if overdue:
            candidates.append({
                "kind": "missed_deadline",
                "title": f"{len(overdue)} tasks are already past due",
                "description": "Delivery dates are slipping; dependent milestones may shift.",
                "probability": round(min(0.9, 0.3 + delay_ratio * 0.6), 2),
                "impact": "medium", "level": "high" if len(overdue) >= 5 else "medium",
                "horizon_days": 14,
                "subject_type": "task",
                "signals": [{"metric": "overdue_tasks", "value": len(overdue)}],
            })

        # 3. project failure risk
        failing = [
            p for p in projects
            if p.status in ("at_risk", "blocked") or (getattr(p, "health_score", 100) or 100) < 50
        ]
        if failing:
            candidates.append({
                "kind": "project_failure",
                "title": f"{len(failing)} project(s) show failure signals",
                "description": "At-risk or blocked projects need intervention.",
                "probability": 0.6, "impact": "high", "level": "medium",
                "horizon_days": 30, "subject_type": "project",
                "signals": [{"metric": "at_risk_projects", "value": len(failing)}],
            })

        # 4. employee burnout / attrition
        burnout = [
            t for t in tasks
            if t.assignee_id and t.status in ("in_progress", "todo")
        ]
        per_assignee: dict[str, int] = {}
        for t in burnout:
            per_assignee[t.assignee_id] = per_assignee.get(t.assignee_id, 0) + 1
        overloaded = [k for k, v in per_assignee.items() if v >= 8]
        if overloaded:
            candidates.append({
                "kind": "employee_burnout",
                "title": f"{len(overloaded)} employee(s) carry heavy task loads",
                "description": "Sustained overload predicts burnout and attrition.",
                "probability": round(min(0.85, 0.35 + len(overloaded) * 0.1), 2),
                "impact": "high", "level": "medium", "horizon_days": 45,
                "subject_type": "employee",
                "signals": [{"metric": "overloaded_employees", "value": len(overloaded)}],
            })

        # 5. customer churn
        if low_health:
            candidates.append({
                "kind": "customer_churn",
                "title": f"{len(low_health)} customer(s) have declining health",
                "description": "Low satisfaction/health signals precede churn.",
                "probability": 0.55, "impact": "high", "level": "medium",
                "horizon_days": 90, "subject_type": "customer",
                "signals": [{"metric": "customers_below_50", "value": len(low_health)}],
            })

        # 6. budget overrun
        if overrun:
            candidates.append({
                "kind": "budget_overrun",
                "title": f"{len(overrun)} budget(s) exceed 90% allocation",
                "description": "Active budgets are close to exhausted.",
                "probability": 0.7, "impact": "high", "level": "medium",
                "horizon_days": 30, "subject_type": "budget",
                "signals": [{"metric": "budgets_over_90", "value": len(overrun)}],
            })

        # 7. knowledge loss
        if docs and docs_7d == 0 and employees >= 3:
            candidates.append({
                "kind": "knowledge_loss",
                "title": "Knowledge growth has stalled",
                "description": "No documents added in 7 days; institutional knowledge may be lost.",
                "probability": 0.5, "impact": "medium", "level": "low",
                "horizon_days": 30, "subject_type": "knowledge",
                "signals": [{"metric": "documents_added_7d", "value": docs_7d}],
            })

        # 8. innovation decline
        if enroll_30d == 0 and courses_total >= 1 and employees >= 3:
            candidates.append({
                "kind": "innovation_decline",
                "title": "Learning and innovation activity is declining",
                "description": "No new enrollments in 30 days signals stagnation.",
                "probability": 0.45, "impact": "medium", "level": "low",
                "horizon_days": 60, "subject_type": "learning",
                "signals": [{"metric": "enrollments_30d", "value": enroll_30d}],
            })

        # 9. skill gap
        if employees >= 5 and low_skill_emp >= max(2, employees * 0.2):
            candidates.append({
                "kind": "skill_gap",
                "title": "Critical skill gaps are emerging",
                "description": "Multiple employees have minimal recorded expertise.",
                "probability": 0.5, "impact": "medium", "level": "medium",
                "horizon_days": 90, "subject_type": "employees",
                "signals": [{"metric": "low_skill_employees", "value": low_skill_emp}],
            })

        # 10. compliance risk (no policies/documents updated in 90 days)
        policies_updated = (
            await db.execute(
                select(func.count(Document.id)).where(
                    Document.organization_id == organization_id,
                    Document.updated_at >= month_ago,
                )
            )
        ).scalar() or 0
        if docs and policies_updated == 0:
            candidates.append({
                "kind": "compliance_risk",
                "title": "Documentation may be out of compliance",
                "description": "No documents updated in 30 days.",
                "probability": 0.4, "impact": "medium", "level": "low",
                "horizon_days": 60, "subject_type": "knowledge",
                "signals": [{"metric": "documents_updated_30d", "value": policies_updated}],
            })

        rows: list[Prediction] = []
        for candidate in candidates:
            row = Prediction(
                organization_id=organization_id,
                kind=candidate["kind"],
                title=candidate["title"],
                description=candidate["description"],
                probability=candidate["probability"],
                impact=candidate["impact"],
                level=candidate["level"],
                horizon_days=candidate["horizon_days"],
                subject_type=candidate["subject_type"],
                signals=candidate["signals"],
                status="open",
                source_event="prediction.generated",
                due_at=now + timedelta(days=candidate["horizon_days"]),
            )
            db.add(row)
            rows.append(row)
            await self._ensure_model(db, organization_id, candidate["kind"])
        await db.flush()
        created = [{"id": r.id, **candidate} for r, candidate in zip(rows, candidates)]
        for row in created:
            await publish_background_event(
                db, name="prediction.generated", organization_id=organization_id,
                payload={"prediction_id": row["id"], "kind": row["kind"],
                         "probability": row["probability"]},
            )
        if commit:
            await db.commit()
        return {"total": len(created), "predictions": created}

    async def _ensure_model(
        self, db: AsyncSession, organization_id: str, kind: str
    ) -> PredictionModel:
        if kind not in PREDICTION_KINDS:
            raise ValueError(f"unknown prediction kind: {kind}")
        row = (
            await db.execute(
                select(PredictionModel).where(
                    PredictionModel.organization_id == organization_id,
                    PredictionModel.kind == kind,
                )
            )
        ).scalars().first()
        if row is None:
            row = PredictionModel(
                organization_id=organization_id,
                kind=kind,
                name=f"{kind.replace('_', ' ').title()} model",
                version="1.0",
                params={"method": "heuristic", "horizon_days": 30},
                last_trained_at=utcnow(),
            )
            db.add(row)
            await db.flush()
        return row

    async def list(
        self, db: AsyncSession, organization_id: str, *, status: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        stmt = select(Prediction).where(Prediction.organization_id == organization_id)
        if status:
            stmt = stmt.where(Prediction.status == status)
        rows = (
            await db.execute(stmt.order_by(Prediction.created_at.desc()).limit(limit))
        ).scalars().all()
        return {"total": len(rows), "predictions": [self._serialize(r) for r in rows]}

    async def get(self, db: AsyncSession, organization_id: str, prediction_id: str) -> dict[str, Any] | None:
        row = (
            await db.execute(
                select(Prediction).where(
                    Prediction.organization_id == organization_id,
                    Prediction.id == prediction_id,
                )
            )
        ).scalars().first()
        return self._serialize(row) if row else None

    async def set_status(
        self, db: AsyncSession, organization_id: str, prediction_id: str, status: str
    ) -> dict[str, Any] | None:
        row = (
            await db.execute(
                select(Prediction).where(
                    Prediction.organization_id == organization_id,
                    Prediction.id == prediction_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        if status not in ("open", "acknowledged", "dismissed", "resolved"):
            raise ValueError(f"status must be one of open/acknowledged/dismissed/resolved")
        row.status = status
        await db.flush()
        return self._serialize(row)

    async def validate(
        self, db: AsyncSession, organization_id: str, prediction_id: str, *, came_true: bool
    ) -> dict[str, Any]:
        """Record a validated outcome for a prediction and update model accuracy."""
        prediction = await self.get(db, organization_id, prediction_id)
        if prediction is None:
            raise LookupError("prediction not found")
        model = (
            await db.execute(
                select(PredictionModel).where(
                    PredictionModel.organization_id == organization_id,
                    PredictionModel.kind == prediction["kind"],
                )
            )
        ).scalars().first()
        history = PredictionHistory(
            organization_id=organization_id,
            prediction_id=prediction_id,
            kind=prediction["kind"],
            outcome=came_true,
            validated_at=utcnow(),
        )
        db.add(history)
        if model is not None:
            model.predictions_count += 1
            total = model.predictions_count
            model.accuracy = round(((model.accuracy * (total - 1)) + (1.0 if came_true else 0.0)) / total, 3)
            model.last_trained_at = utcnow()
        await db.flush()
        row = (
            await db.execute(
                select(Prediction).where(Prediction.id == prediction_id)
            )
        ).scalars().first()
        if row is not None and row.status == "open":
            row.status = "validated"
            await db.flush()
        return {
            "prediction_id": prediction_id,
            "kind": prediction["kind"],
            "outcome": came_true,
            "status": "validated",
            "model_accuracy": round(model.accuracy, 3) if model else None,
            "history_id": history.id,
        }

    async def models(
        self, db: AsyncSession, organization_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(PredictionModel)
                .where(PredictionModel.organization_id == organization_id)
                .order_by(PredictionModel.kind)
            )
        ).scalars().all()
        return [
            {
                "id": r.id, "kind": r.kind, "name": r.name, "version": r.version,
                "accuracy": r.accuracy, "predictions_count": r.predictions_count,
                "last_trained_at": r.last_trained_at.isoformat() if r.last_trained_at else None,
            }
            for r in rows
        ]

    def _serialize(self, row: Prediction) -> dict[str, Any]:
        return {
            "id": row.id, "kind": row.kind, "title": row.title,
            "description": row.description, "probability": row.probability,
            "impact": row.impact, "level": row.level, "horizon_days": row.horizon_days,
            "subject_type": row.subject_type, "subject_id": row.subject_id,
            "signals": row.signals or [], "status": row.status,
            "due_at": row.due_at.isoformat() if row.due_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


prediction_engine = PredictionEngine()
