"""Course platform service (Phase 10.1-10.2 — Learning Foundation &
Course Management).

Handles the course catalog (internal/external/video/live/document/book/
interactive), modules, lessons and quizzes; enrollments and progress
tracking; and course completion which updates the learning profile, skill
graph, learning history and emits `course.completed` (and `certificate.
earned` when the course carries a certificate).
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.models.course import Course, CourseEnrollment, CourseModule, CourseQuiz, Lesson, LessonProgress
from app.models.employee import Employee
from app.models.learning_profile import LearningHistoryEntry, LearningProfile
from app.models.organization import Organization

logger = logging.getLogger("vcos.learning.courses")

_event_bus = EventBus()


class CourseService:
    """Course catalog, enrollment and progress engine."""

    # ------------------------------------------------------------------ catalog

    async def create_course(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> Course:
        course = Course(
            organization_id=organization_id,
            title=data["title"],
            description=data.get("description"),
            category=data.get("category"),
            difficulty=data.get("difficulty", "beginner"),
            duration_minutes=data.get("duration_minutes", 0),
            format=data.get("format", "internal"),
            author_id=data.get("author_id"),
            department=data.get("department"),
            language=data.get("language", "en"),
            status=data.get("status", "published"),
            external_url=data.get("external_url"),
            cover_url=data.get("cover_url"),
            certificate_title=data.get("certificate_title"),
            skills=data.get("skills") or [],
            tags=data.get("tags") or [],
        )
        db.add(course)
        await db.flush()
        return course

    async def update_course(self, db: AsyncSession, *, organization_id: str, course_id: str, data: dict[str, Any]) -> Optional[Course]:
        course = await self.get_course(db, organization_id=organization_id, course_id=course_id)
        if course is None:
            return None
        for key, value in data.items():
            if value is not None and hasattr(course, key):
                setattr(course, key, value)
        await db.flush()
        return course

    async def delete_course(self, db: AsyncSession, *, organization_id: str, course_id: str) -> bool:
        course = await self.get_course(db, organization_id=organization_id, course_id=course_id)
        if course is None:
            return False
        course.status = "archived"
        await db.flush()
        return True

    async def get_course(self, db: AsyncSession, *, organization_id: str, course_id: str) -> Optional[Course]:
        return (
            await db.execute(
                select(Course)
                .options(selectinload(Course.enrollments))
                .where(
                    Course.organization_id == organization_id, Course.id == course_id
                )
            )
        ).scalar_one_or_none()

    async def list_courses(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        search: Optional[str] = None,
        status: str = "published",
        limit: int = 50,
    ) -> list[Course]:
        query = select(Course).where(Course.organization_id == organization_id)
        if status:
            query = query.where(Course.status == status)
        if category:
            query = query.where(Course.category == category)
        if difficulty:
            query = query.where(Course.difficulty == difficulty)
        if search:
            like = f"%{search}%"
            query = query.where(
                or_(Course.title.ilike(like), Course.description.ilike(like), Course.category.ilike(like))
            )
        query = query.order_by(Course.created_at.desc()).limit(limit)
        return (await db.execute(query.options(selectinload(Course.enrollments)))).scalars().all()

    async def categories(self, db: AsyncSession, *, organization_id: str) -> list[str]:
        rows = await db.execute(
            select(Course.category)
            .where(Course.organization_id == organization_id, Course.category.isnot(None))
            .distinct()
        )
        return sorted(c for c in rows.scalars().all() if c)

    async def trending(self, db: AsyncSession, *, organization_id: str, limit: int = 8, days: int = 14) -> list[Course]:
        """Courses with the most recent enrollment activity."""
        since = utcnow() - timedelta(days=days)
        counts = (
            select(CourseEnrollment.course_id, func.count(CourseEnrollment.id).label("cnt"))
            .where(
                CourseEnrollment.organization_id == organization_id,
                CourseEnrollment.enrolled_at >= since,
            )
            .group_by(CourseEnrollment.course_id)
            .order_by(func.count(CourseEnrollment.id).desc())
            .limit(limit)
            .subquery()
        )
        rows = await db.execute(
            select(Course)
            .options(selectinload(Course.enrollments))
            .join(counts, counts.c.course_id == Course.id)
            .where(Course.organization_id == organization_id, Course.status == "published")
            .limit(limit)
        )
        return rows.scalars().all()

    # ------------------------------------------------------------------ content

    async def add_module(self, db: AsyncSession, *, organization_id: str, course_id: str, title: str, description: Optional[str] = None, position: Optional[int] = None) -> Optional[CourseModule]:
        if not await self.get_course(db, organization_id=organization_id, course_id=course_id):
            return None
        if position is None:
            position = (
                (
                    await db.execute(
                        select(func.max(CourseModule.position)).where(
                            CourseModule.organization_id == organization_id,
                            CourseModule.course_id == course_id,
                        )
                    )
                ).scalar()
                or 0
            ) + 1
        module = CourseModule(
            organization_id=organization_id, course_id=course_id,
            title=title, description=description, position=position,
        )
        db.add(module)
        await db.flush()
        return module

    async def add_lesson(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        course_id: str,
        title: str,
        module_id: Optional[str] = None,
        content: Optional[str] = None,
        content_type: str = "text",
        external_url: Optional[str] = None,
        duration_minutes: int = 0,
    ) -> Optional[Lesson]:
        if not await self.get_course(db, organization_id=organization_id, course_id=course_id):
            return None
        position = (
            (
                await db.execute(
                    select(func.max(Lesson.position)).where(
                        Lesson.organization_id == organization_id,
                        Lesson.course_id == course_id,
                    )
                )
            ).scalar()
            or 0
        ) + 1
        lesson = Lesson(
            organization_id=organization_id, course_id=course_id, module_id=module_id,
            title=title, content=content, content_type=content_type,
            external_url=external_url, position=position, duration_minutes=duration_minutes,
        )
        db.add(lesson)
        await db.flush()
        return lesson

    async def add_quiz(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        course_id: str,
        title: str,
        questions: list[dict[str, Any]],
        module_id: Optional[str] = None,
        passing_score: float = 70.0,
    ) -> Optional[CourseQuiz]:
        if not await self.get_course(db, organization_id=organization_id, course_id=course_id):
            return None
        position = (
            (
                await db.execute(
                    select(func.max(CourseQuiz.position)).where(
                        CourseQuiz.organization_id == organization_id,
                        CourseQuiz.course_id == course_id,
                    )
                )
            ).scalar()
            or 0
        ) + 1
        quiz = CourseQuiz(
            organization_id=organization_id, course_id=course_id, module_id=module_id,
            title=title, questions=questions, position=position, passing_score=passing_score,
        )
        db.add(quiz)
        await db.flush()
        return quiz

    # ------------------------------------------------------------------ enrollment & progress

    async def enroll(self, db: AsyncSession, *, organization_id: str, course_id: str, employee_id: str) -> Optional[CourseEnrollment]:
        course = await self.get_course(db, organization_id=organization_id, course_id=course_id)
        if course is None or course.status != "published":
            return None
        existing = (
            await db.execute(
                select(CourseEnrollment).where(
                    CourseEnrollment.organization_id == organization_id,
                    CourseEnrollment.course_id == course_id,
                    CourseEnrollment.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        enrollment = CourseEnrollment(
            organization_id=organization_id, course_id=course_id, employee_id=employee_id,
            status="enrolled", progress=0.0, enrolled_at=utcnow(),
        )
        db.add(enrollment)
        await db.flush()
        await self._ensure_profile(db, organization_id=organization_id, employee_id=employee_id)
        return enrollment

    async def my_enrollments(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> list[CourseEnrollment]:
        return (
            await db.execute(
                select(CourseEnrollment)
                .where(
                    CourseEnrollment.organization_id == organization_id,
                    CourseEnrollment.employee_id == employee_id,
                )
                .order_by(CourseEnrollment.enrolled_at.desc())
            )
        ).scalars().all()

    async def complete_lesson(self, db: AsyncSession, *, organization_id: str, enrollment_id: str, lesson_id: str, employee_id: str) -> Optional[CourseEnrollment]:
        enrollment = (
            await db.execute(
                select(CourseEnrollment).where(
                    CourseEnrollment.organization_id == organization_id,
                    CourseEnrollment.id == enrollment_id,
                    CourseEnrollment.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if enrollment is None:
            return None
        progress = (
            await db.execute(
                select(LessonProgress).where(
                    LessonProgress.organization_id == organization_id,
                    LessonProgress.enrollment_id == enrollment_id,
                    LessonProgress.lesson_id == lesson_id,
                )
            )
        ).scalar_one_or_none()
        if progress is None:
            progress = LessonProgress(
                organization_id=organization_id, enrollment_id=enrollment_id,
                lesson_id=lesson_id, completed=True, completed_at=utcnow(),
            )
            db.add(progress)
        elif not progress.completed:
            progress.completed = True
            progress.completed_at = utcnow()

        # recompute progress: fraction of completed lessons in the course
        lesson_total = (
            await db.execute(
                select(func.count(Lesson.id)).where(
                    Lesson.organization_id == organization_id,
                    Lesson.course_id == enrollment.course_id,
                )
            )
        ).scalar() or 0
        lesson_done = (
            await db.execute(
                select(func.count(LessonProgress.id)).where(
                    LessonProgress.organization_id == organization_id,
                    LessonProgress.enrollment_id == enrollment_id,
                    LessonProgress.completed.is_(True),
                )
            )
        ).scalar() or 0
        if lesson_total > 0:
            enrollment.progress = round((lesson_done / lesson_total) * 100, 1)
        else:
            enrollment.progress = 100.0 if lesson_done > 0 else 0.0
        if enrollment.status == "enrolled":
            enrollment.status = "in_progress"
        enrollment.last_activity_at = utcnow()
        await db.flush()

        if enrollment.progress >= 100.0 and enrollment.status != "completed":
            await self.complete_course(db, organization_id=organization_id, enrollment_id=enrollment.id)
        return enrollment

    async def complete_course(self, db: AsyncSession, *, organization_id: str, enrollment_id: str) -> Optional[CourseEnrollment]:
        enrollment = (
            await db.execute(
                select(CourseEnrollment).where(
                    CourseEnrollment.organization_id == organization_id,
                    CourseEnrollment.id == enrollment_id,
                )
            )
        ).scalar_one_or_none()
        if enrollment is None:
            return None
        if enrollment.status == "completed":
            return enrollment
        enrollment.status = "completed"
        enrollment.progress = 100.0
        enrollment.completed_at = utcnow()
        course = await self.get_course(db, organization_id=organization_id, course_id=enrollment.course_id)
        await db.flush()

        await self._record_completion(db, organization_id=organization_id, enrollment=enrollment, course=course)
        return enrollment

    async def _record_completion(
        self, db: AsyncSession, *, organization_id: str,
        enrollment: CourseEnrollment, course: Optional[Course],
    ) -> None:
        title = course.title if course else "Course"
        db.add(
            LearningHistoryEntry(
                organization_id=organization_id,
                employee_id=enrollment.employee_id,
                kind="course_completion",
                title=title,
                entity_id=enrollment.course_id,
                time_minutes=course.duration_minutes if course else 0,
                meta={"course_id": enrollment.course_id, "progress": enrollment.progress},
                occurred_at=utcnow(),
            )
        )
        await self._ensure_profile(db, organization_id=organization_id, employee_id=enrollment.employee_id)
        profile = (
            await db.execute(
                select(LearningProfile).where(
                    LearningProfile.organization_id == organization_id,
                    LearningProfile.employee_id == enrollment.employee_id,
                )
            )
        ).scalar_one_or_none()
        if profile:
            profile.completed_courses = (profile.completed_courses or 0) + 1
            profile.learning_score = min(100.0, (profile.learning_score or 0) + 5.0)
            profile.last_learning_date = utcnow()
        # skill boost: course skills feed the skill graph
        if course and course.skills:
            from app.learning.skill_service import skill_service
            for skill_name in course.skills:
                await skill_service.boost_skill(
                    db, organization_id=organization_id,
                    employee_id=enrollment.employee_id, skill_name=skill_name,
                    points=1.0, source="course",
                    reason=f"Completed {title}",
                )
        # certificate for courses configured with one
        if course and course.certificate_title:
            from app.learning.certification_service import certification_service
            await certification_service.issue_course_certificate(
                db, organization_id=organization_id,
                employee_id=enrollment.employee_id,
                title=course.certificate_title,
                course_id=course.id,
                category=course.category,
            )
        await _event_bus.publish(
            db,
            name="course.completed",
            organization_id=organization_id,
            actor_id=enrollment.employee_id,
            payload={
                "employee_id": enrollment.employee_id,
                "course_id": enrollment.course_id,
                "course_title": title,
            },
            flush=False,
        )

    # ------------------------------------------------------------------ recommendations helpers

    async def recommended_for(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: str,
        skill_names: Optional[list[str]] = None,
        limit: int = 8,
    ) -> list[Course]:
        """Courses matching the employee's skill gaps (by skill tags)."""
        query = select(Course).where(
            Course.organization_id == organization_id,
            Course.status == "published",
            Course.id.notin_(
                select(CourseEnrollment.course_id).where(
                    CourseEnrollment.organization_id == organization_id,
                    CourseEnrollment.employee_id == employee_id,
                )
            ),
        )
        courses = (await db.execute(query.limit(200))).scalars().all()
        if skill_names:
            wanted = {s.strip().lower() for s in skill_names if s and s.strip()}
            scored: list[tuple[int, Course]] = []
            for course in courses:
                tags = {str(t).lower() for t in (course.skills or [])} | {str(t).lower() for t in (course.tags or [])}
                score = len(wanted & tags)
                if score:
                    scored.append((score, course))
            scored.sort(key=lambda pair: (-pair[0], pair[1].created_at))
            return [c for _, c in scored[:limit]]
        return courses[:limit]

    async def recently_viewed(self, db: AsyncSession, *, organization_id: str, employee_id: str, limit: int = 6) -> list[Course]:
        """Courses the employee touched most recently."""
        enrollments = (
            await db.execute(
                select(CourseEnrollment)
                .where(
                    CourseEnrollment.organization_id == organization_id,
                    CourseEnrollment.employee_id == employee_id,
                )
                .order_by(CourseEnrollment.last_activity_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        courses: list[Course] = []
        for enrollment in enrollments:
            course = await self.get_course(db, organization_id=organization_id, course_id=enrollment.course_id)
            if course:
                courses.append(course)
        return courses

    async def _ensure_profile(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> LearningProfile:
        from app.learning.profile_service import profile_service
        return await profile_service.ensure_profile(db, organization_id=organization_id, employee_id=employee_id)


course_service = CourseService()
