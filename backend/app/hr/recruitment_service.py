"""Recruitment service (Phase 11.5 — Recruitment).

Jobs → candidates → interviews (with panels) → offers → hire pipeline.
Candidate matching is deterministic (skill overlap + experience) so it works
without an external AI provider, and the hire step bridges the candidate into
an Employee record — the start of the employee lifecycle.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.hr.parse import to_date, to_dt
from app.models.employee import Employee
from app.models.hr import Candidate, Interview, Job, Offer

logger = logging.getLogger("vcos.hr.recruitment")

_event_bus = EventBus()

STAGES = ["applied", "screening", "interview", "offer", "hired", "rejected", "withdrawn"]
OFFER_STATUSES = ["draft", "sent", "accepted", "declined", "withdrawn"]


class RecruitmentService:
    # ------------------------------------------------------------------ jobs

    async def create_job(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any], created_by: Optional[str] = None) -> Job:
        job = Job(
            organization_id=organization_id,
            title=data["title"],
            department=data.get("department"),
            location=data.get("location"),
            employment_type=data.get("employment_type", "full_time"),
            description=data.get("description"),
            requirements=data.get("requirements") or [],
            skills=data.get("skills") or [],
            salary_range=data.get("salary_range"),
            openings=int(data.get("openings", 1)),
            status=data.get("status", "draft"),
            created_by=created_by,
        )
        db.add(job)
        await db.flush()
        return job

    async def update_job(self, db: AsyncSession, *, organization_id: str, job_id: str, data: dict[str, Any]) -> Optional[Job]:
        job = (
            await db.execute(select(Job).where(Job.organization_id == organization_id, Job.id == job_id))
        ).scalar_one_or_none()
        if job is None:
            return None
        for field in ("title", "department", "location", "employment_type", "description",
                      "requirements", "skills", "salary_range", "openings", "status"):
            if field in data:
                setattr(job, field, data[field])
        await db.flush()
        return job

    async def get_job(self, db: AsyncSession, *, organization_id: str, job_id: str) -> Optional[Job]:
        return (
            await db.execute(select(Job).where(Job.organization_id == organization_id, Job.id == job_id))
        ).scalar_one_or_none()

    async def list_jobs(self, db: AsyncSession, *, organization_id: str, status: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(Job).where(Job.organization_id == organization_id)
        if status:
            query = query.where(Job.status == status)
        rows = await db.execute(query.order_by(Job.created_at.desc()))
        return [self._job_out(job) for job in rows.scalars().all()]

    async def close_job(self, db: AsyncSession, *, organization_id: str, job_id: str) -> Optional[Job]:
        job = await self.get_job(db, organization_id=organization_id, job_id=job_id)
        if job is None:
            return None
        job.status = "closed"
        await db.flush()
        return job

    def _job_out(self, job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "title": job.title,
            "department": job.department,
            "location": job.location,
            "employment_type": job.employment_type,
            "description": job.description,
            "requirements": job.requirements or [],
            "skills": job.skills or [],
            "salary_range": job.salary_range,
            "openings": job.openings,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }

    # ------------------------------------------------------------------ candidates

    async def add_candidate(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> Candidate:
        job = await self.get_job(db, organization_id=organization_id, job_id=data["job_id"])
        if job is None:
            raise ValueError("unknown job")
        candidate = Candidate(
            organization_id=organization_id,
            job_id=job.id,
            name=data["name"],
            email=data.get("email"),
            phone=data.get("phone"),
            resume_url=data.get("resume_url"),
            source=data.get("source", "website"),
            stage=data.get("stage", "applied"),
            skills=data.get("skills") or [],
            experience_years=float(data.get("experience_years", 0.0)),
            current_company=data.get("current_company"),
            current_title=data.get("current_title"),
            notes=data.get("notes"),
            applied_at=to_dt(data.get("applied_at")) or utcnow(),
        )
        db.add(candidate)
        await db.flush()
        if job.status == "draft":
            job.status = "open"
        if candidate.skills or candidate.experience_years:
            candidate.match_score = await self._match_score(db, job, candidate)
        await db.flush()
        return candidate

    async def update_candidate(self, db: AsyncSession, *, organization_id: str, candidate_id: str, data: dict[str, Any]) -> Optional[Candidate]:
        candidate = (
            await db.execute(
                select(Candidate).where(Candidate.organization_id == organization_id, Candidate.id == candidate_id)
            )
        ).scalar_one_or_none()
        if candidate is None:
            return None
        for field in ("name", "email", "phone", "resume_url", "source", "stage", "skills",
                      "experience_years", "current_company", "current_title", "notes", "rating"):
            if field in data:
                setattr(candidate, field, data[field])
        job = await db.get(Job, candidate.job_id)
        if job and (candidate.skills or candidate.experience_years):
            candidate.match_score = await self._match_score(db, job, candidate)
        await db.flush()
        return candidate

    async def list_candidates(
        self, db: AsyncSession, *, organization_id: str, job_id: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(Candidate).where(Candidate.organization_id == organization_id)
        if job_id:
            query = query.where(Candidate.job_id == job_id)
        if stage:
            query = query.where(Candidate.stage == stage)
        rows = await db.execute(query.order_by(Candidate.applied_at.desc()))
        result = []
        for candidate in rows.scalars().all():
            job = await db.get(Job, candidate.job_id)
            result.append(
                {
                    "id": candidate.id,
                    "job_id": candidate.job_id,
                    "job_title": job.title if job else None,
                    "name": candidate.name,
                    "email": candidate.email,
                    "phone": candidate.phone,
                    "resume_url": candidate.resume_url,
                    "source": candidate.source,
                    "stage": candidate.stage,
                    "skills": candidate.skills or [],
                    "experience_years": candidate.experience_years,
                    "current_company": candidate.current_company,
                    "current_title": candidate.current_title,
                    "match_score": round(candidate.match_score, 1),
                    "rating": candidate.rating,
                    "notes": candidate.notes,
                    "applied_at": candidate.applied_at.isoformat() if candidate.applied_at else None,
                }
            )
        return result

    async def _match_score(self, db: AsyncSession, job: Job, candidate: Candidate) -> float:
        """Deterministic AI-lite match: skill overlap weighted + experience."""
        required = [str(s).lower() for s in (job.skills or [])]
        candidate_skills = [str(s).lower() for s in (candidate.skills or [])]
        if not required:
            return 0.0
        matched = len(set(required) & set(candidate_skills))
        skill_score = 60.0 * matched / len(required)
        exp = min(candidate.experience_years or 0.0, 12.0)
        exp_score = 25.0 * exp / 12.0
        # higher seniority jobs want more experience
        experience_needed = len(required) * 0.5
        seniority = 15.0 if (candidate.experience_years or 0.0) >= experience_needed else max(0.0, 15.0 - (experience_needed - (candidate.experience_years or 0.0)) * 4.0)
        return round(min(100.0, skill_score + exp_score + seniority), 1)

    # ------------------------------------------------------------------ interviews

    async def schedule_interview(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> Interview:
        candidate = (
            await db.execute(
                select(Candidate).where(Candidate.organization_id == organization_id, Candidate.id == data["candidate_id"])
            )
        ).scalar_one_or_none()
        if candidate is None:
            raise ValueError("unknown candidate")
        interview = Interview(
            organization_id=organization_id,
            job_id=data["job_id"],
            candidate_id=candidate.id,
            scheduled_at=to_dt(data.get("scheduled_at")),
            duration_minutes=int(data.get("duration_minutes", 45)),
            panel=data.get("panel") or [],
            mode=data.get("mode", "video"),
        )
        db.add(interview)
        await db.flush()
        if candidate.stage == "screening":
            candidate.stage = "interview"
        await db.flush()
        return interview

    async def complete_interview(
        self, db: AsyncSession, *, organization_id: str, interview_id: str,
        rating: float, feedback: Optional[str] = None, recommendation: Optional[str] = None, summary: Optional[str] = None,
    ) -> Optional[Interview]:
        interview = (
            await db.execute(
                select(Interview).where(Interview.organization_id == organization_id, Interview.id == interview_id)
            )
        ).scalar_one_or_none()
        if interview is None:
            return None
        interview.status = "completed"
        interview.rating = rating
        entries = list(interview.feedback or [])
        entries.append(
            {
                "rating": rating,
                "feedback": feedback,
                "recommendation": recommendation,
                "summary": summary,
                "submitted_at": utcnow().isoformat(),
            }
        )
        interview.feedback = entries
        interview.summary = summary or interview.summary
        candidate = await db.get(Candidate, interview.candidate_id)
        if candidate:
            candidate.rating = round((candidate.rating + rating) / 2, 1) if candidate.rating else rating
            if candidate.stage == "interview":
                candidate.stage = "offer" if recommendation == "hire" else candidate.stage
        await db.flush()
        return interview

    async def list_interviews(
        self, db: AsyncSession, *, organization_id: str, job_id: Optional[str] = None, candidate_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(Interview).where(Interview.organization_id == organization_id)
        if job_id:
            query = query.where(Interview.job_id == job_id)
        if candidate_id:
            query = query.where(Interview.candidate_id == candidate_id)
        rows = await db.execute(query.order_by(Interview.scheduled_at.desc()))
        result = []
        for interview in rows.scalars().all():
            candidate = await db.get(Candidate, interview.candidate_id)
            job = await db.get(Job, interview.job_id)
            result.append(
                {
                    "id": interview.id,
                    "job_id": interview.job_id,
                    "job_title": job.title if job else None,
                    "candidate_id": interview.candidate_id,
                    "candidate_name": candidate.name if candidate else None,
                    "scheduled_at": interview.scheduled_at.isoformat() if interview.scheduled_at else None,
                    "duration_minutes": interview.duration_minutes,
                    "panel": interview.panel or [],
                    "mode": interview.mode,
                    "status": interview.status,
                    "rating": interview.rating,
                    "summary": interview.summary,
                    "feedback": interview.feedback or [],
                }
            )
        return result

    # ------------------------------------------------------------------ offers & hire

    async def create_offer(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> Offer:
        candidate = (
            await db.execute(
                select(Candidate).where(Candidate.organization_id == organization_id, Candidate.id == data["candidate_id"])
            )
        ).scalar_one_or_none()
        if candidate is None:
            raise ValueError("unknown candidate")
        offer = Offer(
            organization_id=organization_id,
            job_id=data["job_id"],
            candidate_id=candidate.id,
            salary=data.get("salary"),
            equity=data.get("equity"),
            start_date=to_date(data.get("start_date")),
            expires_at=to_date(data.get("expires_at")),
            status=data.get("status", "draft"),
            notes=data.get("notes"),
        )
        db.add(offer)
        await db.flush()
        if candidate.stage == "interview":
            candidate.stage = "offer"
        await db.flush()
        return offer

    async def update_offer(
        self, db: AsyncSession, *, organization_id: str, offer_id: str, status: str, notes: Optional[str] = None,
    ) -> tuple[Optional[Offer], Optional[Employee]]:
        """Transition an offer. Accepted offers with a start date create the Employee."""
        offer = (
            await db.execute(select(Offer).where(Offer.organization_id == organization_id, Offer.id == offer_id))
        ).scalar_one_or_none()
        if offer is None:
            return None, None
        if status not in OFFER_STATUSES:
            raise ValueError(f"invalid offer status: {status}")
        offer.status = status
        if notes is not None:
            offer.notes = notes
        created_employee = None
        if status == "accepted":
            offer.signed_at = utcnow()
            candidate = await db.get(Candidate, offer.candidate_id)
            if candidate:
                candidate.stage = "hired"
            created_employee = await self._hire(db, organization_id=organization_id, offer=offer)
        elif status in ("declined", "withdrawn"):
            candidate = await db.get(Candidate, offer.candidate_id)
            if candidate and candidate.stage in ("offer", "hired"):
                candidate.stage = "rejected" if status == "declined" else "withdrawn"
        await db.flush()
        return offer, created_employee

    async def _hire(self, db: AsyncSession, *, organization_id: str, offer: Offer) -> Optional[Employee]:
        """Bridge the accepted candidate into an Employee (employee.joined)."""
        candidate = await db.get(Candidate, offer.candidate_id)
        job = await db.get(Job, offer.job_id)
        if candidate is None or job is None:
            return None
        existing = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id, Employee.email == (candidate.email or "")
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        parts = candidate.name.split(" ", 1)
        count = (
            await db.execute(
                select(func.count()).select_from(Employee).where(Employee.organization_id == organization_id)
            )
        ).scalar_one()
        employee = Employee(
            organization_id=organization_id,
            first_name=parts[0],
            last_name=parts[1] if len(parts) > 1 else None,
            display_name=candidate.name,
            email=candidate.email or f"{candidate.name.lower().replace(' ', '.')}@hire.vcos",
            employee_number=f"EMP-{count + 1:04d}",
            designation=job.title,
            employment_type=job.employment_type or "full_time",
            joining_date=offer.start_date,
            status="active",
        )
        db.add(employee)
        await db.flush()
        if job.openings > 0:
            job.openings = max(0, job.openings - 1)
        if job.openings == 0:
            job.status = "closed"
        await _event_bus.publish(
            db,
            name="employee.joined",
            organization_id=organization_id,
            actor_id=employee.id,
            payload={
                "employee_id": employee.id,
                "name": employee.full_name,
                "designation": employee.designation,
                "source": "recruitment",
                "offer_id": offer.id,
            },
            flush=False,
        )
        return employee

    async def list_offers(
        self, db: AsyncSession, *, organization_id: str, candidate_id: Optional[str] = None, status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(Offer).where(Offer.organization_id == organization_id)
        if candidate_id:
            query = query.where(Offer.candidate_id == candidate_id)
        if status:
            query = query.where(Offer.status == status)
        rows = await db.execute(query.order_by(Offer.created_at.desc()))
        result = []
        for offer in rows.scalars().all():
            candidate = await db.get(Candidate, offer.candidate_id)
            job = await db.get(Job, offer.job_id)
            result.append(
                {
                    "id": offer.id,
                    "job_id": offer.job_id,
                    "job_title": job.title if job else None,
                    "candidate_id": offer.candidate_id,
                    "candidate_name": candidate.name if candidate else None,
                    "salary": offer.salary,
                    "equity": offer.equity,
                    "start_date": offer.start_date.isoformat() if offer.start_date else None,
                    "expires_at": offer.expires_at.isoformat() if offer.expires_at else None,
                    "status": offer.status,
                    "notes": offer.notes,
                    "signed_at": offer.signed_at.isoformat() if offer.signed_at else None,
                }
            )
        return result

    # ------------------------------------------------------------------ stats

    async def stats(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        jobs = (await db.execute(select(Job).where(Job.organization_id == organization_id))).scalars().all()
        candidates = (await db.execute(select(Candidate).where(Candidate.organization_id == organization_id))).scalars().all()
        offers = (await db.execute(select(Offer).where(Offer.organization_id == organization_id))).scalars().all()
        stage_counts: dict[str, int] = {}
        for candidate in candidates:
            stage_counts[candidate.stage] = stage_counts.get(candidate.stage, 0) + 1
        interviews = (await db.execute(select(Interview).where(Interview.organization_id == organization_id))).scalars().all()
        open_positions = sum(job.openings for job in jobs if job.status == "open")
        return {
            "open_jobs": sum(1 for job in jobs if job.status == "open"),
            "open_positions": open_positions,
            "total_jobs": len(jobs),
            "total_candidates": len(candidates),
            "candidates_by_stage": stage_counts,
            "interviews_scheduled": sum(1 for interview in interviews if interview.status == "scheduled"),
            "offers": {
                "total": len(offers),
                "sent": sum(1 for offer in offers if offer.status == "sent"),
                "accepted": sum(1 for offer in offers if offer.status == "accepted"),
                "declined": sum(1 for offer in offers if offer.status == "declined"),
            },
            "hires": sum(1 for candidate in candidates if candidate.stage == "hired"),
        }


recruitment_service = RecruitmentService()
