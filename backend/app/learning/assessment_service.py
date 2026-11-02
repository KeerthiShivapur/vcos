"""Assessment service (Phase 10.8 — Assessments).

Quiz, coding, essay, case study, presentation, interview and assignment
assessments. Quiz attempts are auto-scored by the AI evaluation engine
(heuristic answer matching); other kinds wait for peer/manager review.
Finished assessments update the Skill Graph and Learning History and emit
assessment.finished events.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.models.assessment import Assessment, AssessmentAttempt, AssessmentReview
from app.models.learning_profile import LearningHistoryEntry, LearningProfile

logger = logging.getLogger("vcos.learning.assessments")

_event_bus = EventBus()


class AssessmentService:
    # ------------------------------------------------------------------ catalog

    async def create(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> Assessment:
        assessment = Assessment(
            organization_id=organization_id,
            title=data["title"],
            description=data.get("description"),
            kind=data.get("kind", "quiz"),
            course_id=data.get("course_id"),
            certification_id=data.get("certification_id"),
            difficulty=data.get("difficulty", "intermediate"),
            duration_minutes=data.get("duration_minutes", 30),
            passing_score=data.get("passing_score", 70.0),
            max_score=data.get("max_score", 100.0),
            evaluation=data.get("evaluation", "ai"),
            skills=data.get("skills") or [],
            questions=data.get("questions"),
            rubric=data.get("rubric"),
            status=data.get("status", "published"),
        )
        db.add(assessment)
        await db.flush()
        return assessment

    async def get(self, db: AsyncSession, *, organization_id: str, assessment_id: str) -> Optional[Assessment]:
        return (
            await db.execute(
                select(Assessment).where(
                    Assessment.organization_id == organization_id,
                    Assessment.id == assessment_id,
                )
            )
        ).scalar_one_or_none()

    async def list_assessments(
        self, db: AsyncSession, *, organization_id: str,
        kind: Optional[str] = None, status: str = "published", search: Optional[str] = None,
        category: Optional[str] = None, limit: Optional[int] = None,
    ) -> list[Assessment]:
        query = select(Assessment).where(Assessment.organization_id == organization_id)
        if status:
            query = query.where(Assessment.status == status)
        if kind:
            query = query.where(Assessment.kind == kind)
        if category:
            query = query.where(Assessment.kind == category)
        if search:
            query = query.where(Assessment.title.ilike(f"%{search}%"))
        if limit is not None:
            query = query.limit(limit)
        return (await db.execute(query.order_by(Assessment.created_at.desc()))).scalars().all()

    # ------------------------------------------------------------------ attempts

    async def assign(self, db: AsyncSession, *, organization_id: str, assessment_id: str, employee_id: str) -> Optional[AssessmentAttempt]:
        assessment = await self.get(db, organization_id=organization_id, assessment_id=assessment_id)
        if assessment is None or assessment.status != "published":
            return None
        attempt = AssessmentAttempt(
            organization_id=organization_id,
            assessment_id=assessment_id,
            employee_id=employee_id,
            status="assigned",
        )
        db.add(attempt)
        await db.flush()
        return attempt

    async def submit(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        attempt_id: str,
        employee_id: str,
        answers: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[AssessmentAttempt]:
        attempt = (
            await db.execute(
                select(AssessmentAttempt).where(
                    AssessmentAttempt.organization_id == organization_id,
                    AssessmentAttempt.id == attempt_id,
                    AssessmentAttempt.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if attempt is None:
            return None
        assessment = await self.get(db, organization_id=organization_id, assessment_id=attempt.assessment_id)
        attempt.answers = answers or []
        attempt.status = "submitted"
        attempt.submitted_at = utcnow()
        await db.flush()

        if assessment and assessment.evaluation == "ai":
            await self.evaluate(db, organization_id=organization_id, attempt_id=attempt.id, reviewer_kind="ai")
        return attempt

    async def evaluate(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        attempt_id: str,
        reviewer_kind: str = "ai",
        reviewer_id: Optional[str] = None,
        score: Optional[float] = None,
        feedback: Optional[str] = None,
    ) -> Optional[AssessmentAttempt]:
        attempt = (
            await db.execute(
                select(AssessmentAttempt).where(
                    AssessmentAttempt.organization_id == organization_id,
                    AssessmentAttempt.id == attempt_id,
                )
            )
        ).scalar_one_or_none()
        if attempt is None:
            return None
        assessment = await self.get(db, organization_id=organization_id, assessment_id=attempt.assessment_id)
        final_score = score
        if final_score is None and reviewer_kind == "ai" and assessment and assessment.questions:
            final_score = self._auto_score(assessment, attempt.answers or [])
        if final_score is not None:
            if score is None and reviewer_kind == "ai":
                # AI gets one shot at the auto-score; human reviewers may adjust
                attempt.score = final_score
            elif reviewer_kind != "ai":
                attempt.score = final_score
            attempt.passed = final_score >= (assessment.passing_score if assessment else 70.0)
            attempt.status = "evaluated"
            attempt.evaluator_id = reviewer_id
            attempt.evaluated_at = utcnow()
            if feedback:
                attempt.feedback = feedback
        elif attempt.answers and not assessment.questions:
            # non-quiz submissions awaiting review
            attempt.status = "submitted"

        if reviewer_kind in ("peer", "manager"):
            db.add(
                AssessmentReview(
                    organization_id=organization_id,
                    attempt_id=attempt.id,
                    reviewer_id=reviewer_id,
                    review_kind=reviewer_kind,
                    score=final_score,
                    feedback=feedback,
                )
            )
        await db.flush()

        if attempt.status == "evaluated" and attempt.passed is not None:
            await self._finish(db, organization_id=organization_id, attempt=attempt, assessment=assessment)
        return attempt

    def _auto_score(self, assessment: Assessment, answers: list[dict[str, Any]]) -> float:
        """Heuristic AI evaluation: match answers to question answer_index."""
        questions = assessment.questions or []
        if not questions:
            return 0.0
        earned = 0.0
        total = 0.0
        by_index: dict[int, Any] = {}
        for answer in answers:
            q_index = answer.get("question_index")
            if q_index is not None:
                by_index[int(q_index)] = answer.get("answer")
        for index, question in enumerate(questions):
            points = float(question.get("points", 1))
            total += points
            correct = question.get("answer_index")
            submitted = by_index.get(index)
            if correct is not None and submitted == correct:
                earned += points
            elif correct is not None and isinstance(submitted, (int, float)) and int(submitted) == int(correct):
                earned += points
        return round((earned / total) * 100.0, 1) if total else 0.0

    async def _finish(self, db: AsyncSession, *, organization_id: str, attempt: AssessmentAttempt, assessment: Optional[Assessment]) -> None:
        profile = (
            await db.execute(
                select(LearningProfile).where(
                    LearningProfile.organization_id == organization_id,
                    LearningProfile.employee_id == attempt.employee_id,
                )
            )
        ).scalar_one_or_none()
        if profile:
            profile.learning_score = min(100.0, (profile.learning_score or 0) + 4.0)
            profile.last_learning_date = utcnow()
        db.add(
            LearningHistoryEntry(
                organization_id=organization_id,
                employee_id=attempt.employee_id,
                kind="assessment",
                title=assessment.title if assessment else "Assessment",
                entity_id=attempt.assessment_id,
                score=attempt.score,
                time_minutes=assessment.duration_minutes if assessment else 0,
                feedback=attempt.feedback,
                meta={"passed": attempt.passed, "attempt_id": attempt.id},
                occurred_at=utcnow(),
            )
        )
        # passed assessments update the skill graph
        if attempt.passed and assessment and assessment.skills:
            from app.learning.skill_service import skill_service
            await skill_service.apply_assessment_result(
                db, organization_id=organization_id, employee_id=attempt.employee_id,
                skill_names=assessment.skills, score_pct=attempt.score or 0.0, source="assessment",
            )
        # pass the linked certification when applicable
        if attempt.passed and assessment and assessment.certification_id:
            from app.learning.certification_service import certification_service
            certification = await certification_service.get(
                db, organization_id=organization_id, certification_id=assessment.certification_id
            )
            if certification:
                cert_attempt = await certification_service.start_attempt(
                    db, organization_id=organization_id,
                    certification_id=certification.id, employee_id=attempt.employee_id,
                )
                if cert_attempt:
                    await certification_service.complete_attempt(
                        db, organization_id=organization_id, attempt_id=cert_attempt.id,
                        employee_id=attempt.employee_id, score=attempt.score, passed=True,
                        evidence=f"Passed assessment {assessment.title}",
                    )
        await _event_bus.publish(
            db,
            name="assessment.finished",
            organization_id=organization_id,
            actor_id=attempt.employee_id,
            payload={
                "employee_id": attempt.employee_id,
                "assessment_id": attempt.assessment_id,
                "assessment_title": assessment.title if assessment else "",
                "score": attempt.score,
                "passed": attempt.passed,
            },
            flush=False,
        )

    async def my_attempts(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(AssessmentAttempt)
                .where(
                    AssessmentAttempt.organization_id == organization_id,
                    AssessmentAttempt.employee_id == employee_id,
                )
                .order_by(AssessmentAttempt.created_at.desc())
            )
        ).scalars().all()
        result = []
        for attempt in rows:
            assessment = await self.get(db, organization_id=organization_id, assessment_id=attempt.assessment_id)
            result.append(
                {
                    "id": attempt.id,
                    "assessment_id": attempt.assessment_id,
                    "assessment_title": assessment.title if assessment else "Assessment",
                    "kind": assessment.kind if assessment else None,
                    "status": attempt.status,
                    "score": attempt.score,
                    "passed": attempt.passed,
                    "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
                    "evaluated_at": attempt.evaluated_at.isoformat() if attempt.evaluated_at else None,
                    "feedback": attempt.feedback,
                    "evaluation": assessment.evaluation if assessment else None,
                }
            )
        return result

    async def pending_reviews(self, db: AsyncSession, *, organization_id: str, limit: int = 50) -> list[AssessmentAttempt]:
        rows = await db.execute(
            select(AssessmentAttempt)
            .join(Assessment, Assessment.id == AssessmentAttempt.assessment_id)
            .where(
                AssessmentAttempt.organization_id == organization_id,
                AssessmentAttempt.status == "submitted",
                Assessment.evaluation.in_(("peer", "manager")),
            )
            .order_by(AssessmentAttempt.submitted_at.asc())
            .limit(limit)
        )
        return rows.scalars().all()


assessment_service = AssessmentService()
