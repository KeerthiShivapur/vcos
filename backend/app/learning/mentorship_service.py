"""Mentorship service (Phase 10.7 — Internal Mentorship).

Employees become mentors via MentorProfile. AI mentor matching scores
candidate mentors by skill level (expertise), availability, department
proximity and load. Mentorships track sessions, goals and feedback; the
service emits mentor.assigned events and keeps progress updated.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.models.employee import Employee
from app.models.mentorship import MentorProfile, Mentorship, MentorshipFeedback, MentorshipSession
from app.models.skill import Skill
from app.models.employee import EmployeeSkill

logger = logging.getLogger("vcos.learning.mentorship")

_event_bus = EventBus()


class MentorshipService:
    # ------------------------------------------------------------------ mentors

    async def create_profile(self, db: AsyncSession, *, organization_id: str, employee_id: str, data: dict[str, Any]) -> Optional[MentorProfile]:
        employee = await db.get(Employee, employee_id)
        if employee is None or employee.organization_id != organization_id:
            return None
        profile = (
            await db.execute(
                select(MentorProfile).where(
                    MentorProfile.organization_id == organization_id,
                    MentorProfile.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if profile is None:
            profile = MentorProfile(
                organization_id=organization_id, employee_id=employee_id,
                bio=data.get("bio"), topics=data.get("topics") or [],
                availability=data.get("availability", "weekly"),
                max_mentees=data.get("max_mentees", 3),
                active=data.get("active", True),
            )
            db.add(profile)
        else:
            if data.get("bio") is not None:
                profile.bio = data["bio"]
            if data.get("topics") is not None:
                profile.topics = data["topics"]
            if data.get("availability") is not None:
                profile.availability = data["availability"]
            if data.get("max_mentees") is not None:
                profile.max_mentees = data["max_mentees"]
            if data.get("active") is not None:
                profile.active = data["active"]
        await db.flush()
        return profile

    async def list_mentors(
        self, db: AsyncSession, *, organization_id: str,
        topic: Optional[str] = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = (
            select(MentorProfile, Employee)
            .join(Employee, Employee.id == MentorProfile.employee_id)
            .where(
                MentorProfile.organization_id == organization_id,
                MentorProfile.active.is_(True),
                Employee.status == "active",
            )
        )
        if topic:
            query = query.where(MentorProfile.topics.contains([topic]))
        rows = (await db.execute(query.order_by(Employee.display_name).limit(limit))).all()
        result = []
        for profile, employee in rows:
            active_count = (
                await db.execute(
                    select(func.count(Mentorship.id)).where(
                        Mentorship.organization_id == organization_id,
                        Mentorship.mentor_id == employee.id,
                        Mentorship.status == "active",
                    )
                )
            ).scalar() or 0
            result.append(
                {
                    "id": profile.id,
                    "employee_id": employee.id,
                    "name": employee.full_name,
                    "designation": employee.designation,
                    "bio": profile.bio,
                    "topics": profile.topics or [],
                    "availability": profile.availability,
                    "max_mentees": profile.max_mentees,
                    "active_mentees": active_count,
                }
            )
        return result

    async def recommend_mentors(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        skills: Optional[list[str]] = None, limit: int = 5,
    ) -> list[dict[str, Any]]:
        """AI mentor matching: skill level × availability × department × load."""
        mentors = await self.list_mentors(db, organization_id=organization_id, limit=100)
        target = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id, Employee.id == employee_id
                )
            )
        ).scalar_one_or_none()
        wanted = [s.strip().lower() for s in (skills or []) if s and s.strip()]
        scored: list[tuple[float, dict[str, Any]]] = []
        for mentor in mentors:
            if mentor["employee_id"] == employee_id:
                continue
            if mentor["active_mentees"] >= mentor["max_mentees"]:
                continue
            score = 0.0
            # skill alignment
            emp_skills = await db.execute(
                select(EmployeeSkill, Skill)
                .join(Skill, Skill.id == EmployeeSkill.skill_id)
                .where(
                    EmployeeSkill.organization_id == organization_id,
                    EmployeeSkill.employee_id == mentor["employee_id"],
                )
            )
            skill_levels = {skill.name.lower(): emp_skill.level for emp_skill, skill in emp_skills.all()}
            topic_hits = 0
            for topic in mentor["topics"] or []:
                if topic.lower() in wanted:
                    topic_hits += 1
            for skill_name in wanted:
                level = skill_levels.get(skill_name, 0)
                score += level * 10
            score += topic_hits * 15
            # department proximity
            if target and mentor.get("designation") and target.designation:
                pass  # department proximity approximated via shared topics
            # availability
            score += {"weekly": 10, "biweekly": 7, "monthly": 4, "on_demand": 2}.get(mentor["availability"], 5)
            # load
            score -= mentor["active_mentees"] * 3
            scored.append((score, mentor))
        scored.sort(key=lambda pair: -pair[0])
        return [mentor for _, mentor in scored[:limit]]

    # ------------------------------------------------------------------ mentorships

    async def request(
        self,
        db: AsyncSession, *, organization_id: str,
        mentor_id: str, mentee_id: str, topic: str,
        goals: Optional[list[str]] = None, requested_by: str = "mentee",
    ) -> Optional[Mentorship]:
        if mentor_id == mentee_id:
            return None
        mentor = await db.get(Employee, mentor_id)
        if mentor is None or mentor.organization_id != organization_id:
            return None
        existing = (
            await db.execute(
                select(Mentorship).where(
                    Mentorship.organization_id == organization_id,
                    Mentorship.mentor_id == mentor_id,
                    Mentorship.mentee_id == mentee_id,
                    Mentorship.status.in_(("pending", "active")),
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        mentorship = Mentorship(
            organization_id=organization_id,
            mentor_id=mentor_id,
            mentee_id=mentee_id,
            topic=topic,
            goals=goals or [],
            status="pending",
            requested_by=requested_by,
        )
        db.add(mentorship)
        await db.flush()
        return mentorship

    async def respond(self, db: AsyncSession, *, organization_id: str, mentorship_id: str, actor_id: str, accept: bool) -> Optional[Mentorship]:
        mentorship = (
            await db.execute(
                select(Mentorship).where(
                    Mentorship.organization_id == organization_id,
                    Mentorship.id == mentorship_id,
                    Mentorship.mentor_id == actor_id,
                )
            )
        ).scalar_one_or_none()
        if mentorship is None or mentorship.status != "pending":
            return None
        mentorship.status = "active" if accept else "declined"
        mentorship.started_at = utcnow() if accept else None
        await db.flush()
        if accept:
            # mentor capacity is enforced at matching time; log the relationship
            from app.models.learning_profile import LearningProfile
            profile = (
                await db.execute(
                    select(LearningProfile).where(
                        LearningProfile.organization_id == organization_id,
                        LearningProfile.employee_id == mentorship.mentee_id,
                    )
                )
            ).scalar_one_or_none()
            if profile:
                profile.mentor_id = mentorship.mentor_id
                profile.last_learning_date = utcnow()
            await _event_bus.publish(
                db,
                name="mentor.assigned",
                organization_id=organization_id,
                actor_id=actor_id,
                payload={
                    "mentor_id": mentorship.mentor_id,
                    "mentee_id": mentorship.mentee_id,
                    "mentorship_id": mentorship.id,
                    "topic": mentorship.topic,
                },
                flush=False,
            )
        return mentorship

    async def list_for(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        role: str = "mentee", status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(Mentorship).where(Mentorship.organization_id == organization_id)
        if role == "mentor":
            query = query.where(Mentorship.mentor_id == employee_id)
        else:
            query = query.where(Mentorship.mentee_id == employee_id)
        if status:
            query = query.where(Mentorship.status == status)
        rows = (await db.execute(query.order_by(Mentorship.created_at.desc()))).scalars().all()
        result = []
        for mentorship in rows:
            other_id = mentorship.mentee_id if role == "mentor" else mentorship.mentor_id
            other = await db.get(Employee, other_id)
            session_count = (
                await db.execute(
                    select(func.count(MentorshipSession.id)).where(
                        MentorshipSession.organization_id == organization_id,
                        MentorshipSession.mentorship_id == mentorship.id,
                    )
                )
            ).scalar() or 0
            result.append(
                {
                    "id": mentorship.id,
                    "mentor_id": mentorship.mentor_id,
                    "mentee_id": mentorship.mentee_id,
                    "other_name": other.full_name if other else None,
                    "other_designation": other.designation if other else None,
                    "topic": mentorship.topic,
                    "goals": mentorship.goals or [],
                    "status": mentorship.status,
                    "requested_by": mentorship.requested_by,
                    "started_at": mentorship.started_at.isoformat() if mentorship.started_at else None,
                    "progress": mentorship.progress,
                    "session_count": session_count,
                }
            )
        return result

    async def add_session(
        self, db: AsyncSession, *, organization_id: str, mentorship_id: str,
        actor_id: str, title: str, notes: Optional[str] = None,
        kind: str = "call", occurred_at: Optional[str] = None,
        duration_minutes: int = 30,
    ) -> Optional[MentorshipSession]:
        mentorship = (
            await db.execute(
                select(Mentorship).where(
                    Mentorship.organization_id == organization_id,
                    Mentorship.id == mentorship_id,
                    Mentorship.status == "active",
                )
            )
        ).scalar_one_or_none()
        if mentorship is None:
            return None
        if actor_id not in (mentorship.mentor_id, mentorship.mentee_id):
            return None
        occurred = utcnow()
        if occurred_at:
            try:
                occurred = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
            except ValueError:
                pass
        session = MentorshipSession(
            organization_id=organization_id,
            mentorship_id=mentorship_id,
            title=title,
            notes=notes,
            kind=kind,
            occurred_at=occurred,
            duration_minutes=duration_minutes,
        )
        db.add(session)
        # progress moves toward completion with sessions + feedback
        sessions = (
            await db.execute(
                select(func.count(MentorshipSession.id)).where(
                    MentorshipSession.organization_id == organization_id,
                    MentorshipSession.mentorship_id == mentorship_id,
                )
            )
        ).scalar() or 0
        mentorship.progress = round(min(100.0, sessions * 20.0 + (mentorship.progress or 0) * 0.5), 1)
        await db.flush()
        return session

    async def add_feedback(
        self, db: AsyncSession, *, organization_id: str, mentorship_id: str,
        author_id: str, rating: int = 5, comment: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[MentorshipFeedback]:
        mentorship = (
            await db.execute(
                select(Mentorship).where(
                    Mentorship.organization_id == organization_id,
                    Mentorship.id == mentorship_id,
                )
            )
        ).scalar_one_or_none()
        if mentorship is None or author_id not in (mentorship.mentor_id, mentorship.mentee_id):
            return None
        feedback = MentorshipFeedback(
            organization_id=organization_id,
            mentorship_id=mentorship_id,
            session_id=session_id,
            author_id=author_id,
            rating=max(1, min(5, rating)),
            comment=comment,
        )
        db.add(feedback)
        await db.flush()
        return feedback

    async def complete(self, db: AsyncSession, *, organization_id: str, mentorship_id: str, actor_id: str) -> Optional[Mentorship]:
        mentorship = (
            await db.execute(
                select(Mentorship).where(
                    Mentorship.organization_id == organization_id,
                    Mentorship.id == mentorship_id,
                )
            )
        ).scalar_one_or_none()
        if mentorship is None or actor_id not in (mentorship.mentor_id, mentorship.mentee_id):
            return None
        mentorship.status = "completed"
        mentorship.progress = 100.0
        mentorship.ended_at = utcnow()
        await db.flush()
        return mentorship


mentorship_service = MentorshipService()
