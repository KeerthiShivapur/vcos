"""Career path engine (Phase 10.6 — Career Path Engine).

Employees see their career roadmap (Junior → Engineer → Senior → Lead →
Architect → Principal → Director → CTO). Readiness is computed from skill
coverage of the next step's required skills, tenure, completed courses,
certifications, mentorship and performance signals. When readiness crosses
the threshold a PromotionSignal is created for the manager, and the career
engine emits career.updated events.
"""

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.models.career import CareerPath, CareerPathStep, CareerProgress, PromotionSignal
from app.models.employee import Employee
from app.models.learning_profile import LearningProfile
from app.models.skill import Skill

logger = logging.getLogger("vcos.learning.career")

_event_bus = EventBus()

READINESS_THRESHOLD = 75.0


class CareerService:
    # ------------------------------------------------------------------ paths

    async def create_path(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> CareerPath:
        path = CareerPath(
            organization_id=organization_id,
            title=data["title"],
            description=data.get("description"),
            department=data.get("department"),
            levels=data.get("levels") or [],
            status=data.get("status", "published"),
        )
        db.add(path)
        await db.flush()
        for index, step in enumerate(data.get("steps") or [], start=1):
            db.add(
                CareerPathStep(
                    organization_id=organization_id,
                    career_path_id=path.id,
                    title=step["title"],
                    position=index,
                    level=step.get("level", index),
                    required_skills=step.get("required_skills") or [],
                    required_years=step.get("required_years", 2),
                    responsibilities=step.get("responsibilities"),
                    criteria=step.get("criteria") or [],
                )
            )
        await db.flush()
        return path

    async def get_path(self, db: AsyncSession, *, organization_id: str, path_id: str) -> Optional[CareerPath]:
        return (
            await db.execute(
                select(CareerPath)
                .options(selectinload(CareerPath.steps))
                .where(
                    CareerPath.organization_id == organization_id, CareerPath.id == path_id
                )
            )
        ).scalar_one_or_none()

    async def list_paths(self, db: AsyncSession, *, organization_id: str, status: str = "published") -> list[CareerPath]:
        query = select(CareerPath).where(CareerPath.organization_id == organization_id)
        if status:
            query = query.where(CareerPath.status == status)
        query = query.options(selectinload(CareerPath.steps))
        return (await db.execute(query.order_by(CareerPath.title))).scalars().all()

    # ------------------------------------------------------------------ progress

    async def progress_for(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> dict[str, Any]:
        """Current step, next step and readiness for an employee."""
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id, Employee.id == employee_id
                )
            )
        ).scalar_one_or_none()
        if employee is None:
            return {}
        progress = (
            await db.execute(
                select(CareerProgress).where(
                    CareerProgress.organization_id == organization_id,
                    CareerProgress.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()

        paths = await self.list_paths(db, organization_id=organization_id)
        chosen_path = None
        if progress and progress.career_path_id:
            chosen_path = await self.get_path(db, organization_id=organization_id, path_id=progress.career_path_id)
        if chosen_path is None:
            chosen_path = self._infer_path(db, employee=employee, paths=paths) or (paths[0] if paths else None)
        if chosen_path is None:
            return {"employee_id": employee_id, "current": None, "next": None, "readiness": 0.0, "evidence": []}

        steps = (
            await db.execute(
                select(CareerPathStep)
                .where(
                    CareerPathStep.organization_id == organization_id,
                    CareerPathStep.career_path_id == chosen_path.id,
                )
                .order_by(CareerPathStep.position)
            )
        ).scalars().all()
        if not steps:
            return {"employee_id": employee_id, "current": None, "next": None, "readiness": 0.0, "evidence": []}

        current_index = 0
        if progress and progress.current_step_id:
            for index, step in enumerate(steps):
                if step.id == progress.current_step_id:
                    current_index = index
                    break
        current = steps[current_index]
        next_step = steps[current_index + 1] if current_index + 1 < len(steps) else None

        evidence, readiness = await self._compute_readiness(
            db, organization_id=organization_id, employee=employee,
            next_step=next_step, current_level=current.level,
        )
        if progress is None:
            progress = CareerProgress(
                organization_id=organization_id,
                employee_id=employee_id,
                career_path_id=chosen_path.id,
                current_step_id=current.id,
                target_step_id=next_step.id if next_step else None,
                readiness_score=0.0,
                evidence=[],
            )
            db.add(progress)
        else:
            progress.career_path_id = chosen_path.id
            progress.current_step_id = current.id
            progress.target_step_id = next_step.id if next_step else None
        progress.readiness_score = readiness
        progress.evidence = evidence
        await db.flush()

        current_out = self._step_out(current)
        next_out = self._step_out(next_step) if next_step else None

        return {
            "employee_id": employee_id,
            "path_id": chosen_path.id,
            "path_title": chosen_path.title,
            "current": current_out,
            "next": next_out,
            "current_role": current_out["title"],
            "next_role": next_out["title"] if next_out else None,
            "readiness": round(readiness, 1),
            "evidence": evidence,
            "promotion_ready": readiness >= READINESS_THRESHOLD,
        }

    def _infer_path(self, db: AsyncSession, *, employee: Employee, paths: list[CareerPath]) -> Optional[CareerPath]:
        designation = (employee.designation or "").lower()
        for path in paths:
            title = path.title.lower()
            if "engineering" in title and any(word in designation for word in ("engineer", "developer", "architect", "cto")):
                return path
            if "management" in title and any(word in designation for word in ("manager", "lead", "director")):
                return path
            if "sales" in title and "sales" in designation:
                return path
        return None

    def _step_out(self, step: CareerPathStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "title": step.title,
            "position": step.position,
            "level": step.level,
            "required_skills": step.required_skills or [],
            "required_years": step.required_years,
            "criteria": step.criteria or [],
            "responsibilities": step.responsibilities,
        }

    async def required_skills_for_employee(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> list[dict[str, Any]]:
        """The next step's required skills (used by the gap analyzer)."""
        data = await self.progress_for(db, organization_id=organization_id, employee_id=employee_id)
        if not data.get("next"):
            # at the top of the ladder — no further requirements
            if data.get("current"):
                required = data["current"]["required_skills"]
            else:
                return []
        else:
            required = data["next"]["required_skills"]
        return [
            {
                "skill": item.get("name") or item.get("skill") or "",
                "level": item.get("level", 3),
            }
            for item in required
        ]

    async def _compute_readiness(
        self, db: AsyncSession, *, organization_id: str,
        employee: Employee, next_step: Optional[CareerPathStep], current_level: int,
    ) -> tuple[list[dict[str, Any]], float]:
        """Score readiness against the next step's requirements (0..100)."""
        evidence: list[dict[str, Any]] = []
        if next_step is None:
            return [{"category": "career", "label": "Top of career path", "value": "achieved", "met": True}], 100.0

        required = next_step.required_skills or []
        graph = {row["name"].lower(): row["level"] for row in await self._graph(db, organization_id=organization_id, employee_id=employee.id)}
        total_weight = 0.0
        earned_weight = 0.0
        for requirement in required:
            name = (requirement.get("skill") or requirement.get("name") or "").strip()
            level = int(requirement.get("level", 3))
            current = graph.get(name.lower(), 0)
            weight = 5.0
            total_weight += weight
            met = current >= level
            if met:
                earned_weight += weight
            evidence.append(
                {
                    "category": "skill",
                    "label": name,
                    "value": f"{current}/5 (need {level})",
                    "met": met,
                }
            )
        # tenure
        joining = employee.joining_date
        years = 0.0
        if joining:
            years = max(0.0, (date.today() - joining).days / 365.25)
        years_met = years >= next_step.required_years
        total_weight += 2.0
        if years_met:
            earned_weight += 2.0
        evidence.append(
            {
                "category": "experience",
                "label": f"Tenure ({next_step.required_years} years required)",
                "value": f"{years:.1f} years",
                "met": years_met,
            }
        )
        # learning profile contributions
        profile = (
            await db.execute(
                select(LearningProfile).where(
                    LearningProfile.organization_id == organization_id,
                    LearningProfile.employee_id == employee.id,
                )
            )
        ).scalar_one_or_none()
        for key, label, weight in (
            ("completed_courses", "Courses completed", 1.0),
            ("certifications", "Certifications earned", 1.0),
        ):
            if profile:
                total_weight += weight
                if getattr(profile, key, 0) > 0:
                    earned_weight += weight
                    evidence.append({"category": "learning", "label": label, "value": str(getattr(profile, key, 0)), "met": True})
        score = (earned_weight / total_weight * 100.0) if total_weight else 50.0
        return evidence, score

    async def _graph(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> list[dict[str, Any]]:
        from app.learning.skill_service import skill_service
        return await skill_service.graph(db, organization_id=organization_id, employee_id=employee_id)

    # ------------------------------------------------------------------ promotion signals

    async def detect_promotion_signals(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> Optional[PromotionSignal]:
        """Create a promotion signal when readiness crosses the threshold."""
        data = await self.progress_for(db, organization_id=organization_id, employee_id=employee_id)
        if not data.get("promotion_ready") or not data.get("next"):
            return None
        existing = (
            await db.execute(
                select(PromotionSignal).where(
                    PromotionSignal.organization_id == organization_id,
                    PromotionSignal.employee_id == employee_id,
                    PromotionSignal.status == "open",
                    PromotionSignal.career_step_id == data["next"]["id"],
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.score = data["readiness"]
            existing.evidence = data["evidence"]
            await db.flush()
            return existing
        signal = PromotionSignal(
            organization_id=organization_id,
            employee_id=employee_id,
            career_step_id=data["next"]["id"],
            target_title=data["next"]["title"],
            score=data["readiness"],
            status="open",
            evidence=data["evidence"],
        )
        db.add(signal)
        await db.flush()
        await _event_bus.publish(
            db,
            name="career.updated",
            organization_id=organization_id,
            actor_id=employee_id,
            payload={
                "employee_id": employee_id,
                "signal_id": signal.id,
                "target_title": signal.target_title,
                "score": signal.score,
            },
            flush=False,
        )
        return signal

    async def signals(self, db: AsyncSession, *, organization_id: str, employee_id: Optional[str] = None, status: str = "open") -> list[dict[str, Any]]:
        query = select(PromotionSignal).where(
            PromotionSignal.organization_id == organization_id, PromotionSignal.status == status
        )
        if employee_id:
            query = query.where(PromotionSignal.employee_id == employee_id)
        rows = await db.execute(query.order_by(PromotionSignal.score.desc()))
        result = []
        for signal in rows.scalars().all():
            employee = await db.get(Employee, signal.employee_id)
            result.append(
                {
                    "id": signal.id,
                    "employee_id": signal.employee_id,
                    "employee_name": employee.full_name if employee else None,
                    "designation": employee.designation if employee else None,
                    "target_title": signal.target_title,
                    "score": signal.score,
                    "status": signal.status,
                    "evidence": signal.evidence or [],
                }
            )
        return result

    async def review_signal(self, db: AsyncSession, *, organization_id: str, signal_id: str, status: str) -> Optional[PromotionSignal]:
        signal = (
            await db.execute(
                select(PromotionSignal).where(
                    PromotionSignal.organization_id == organization_id, PromotionSignal.id == signal_id
                )
            )
        ).scalar_one_or_none()
        if signal is None:
            return None
        signal.status = status
        await db.flush()
        return signal


career_service = CareerService()
