"""Certification engine (Phase 10.9 — Certification Engine).

Internal certifications across cloud, security, AI, leadership, HR,
finance, engineering, compliance and more. Attempts are recorded, passing
attempts earn CertificationEarned rows that also flow into the employee's
certification profile, learning profile, skill graph, AI memory, search
index and the Organization Graph via events. The certification worker
manages expiry and renewal reminders.
"""

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.models.certification import Certification, CertificationAttempt, CertificationEarned
from app.models.employee import EmployeeCertification
from app.models.learning_profile import LearningHistoryEntry, LearningProfile

logger = logging.getLogger("vcos.learning.certifications")

_event_bus = EventBus()


class CertificationService:
    # ------------------------------------------------------------------ catalog

    async def create(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> Certification:
        certification = Certification(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            category=data.get("category"),
            level=data.get("level", "associate"),
            issuer=data.get("issuer", "VCOS Academy"),
            validity_years=data.get("validity_years", 2),
            skills=data.get("skills") or [],
            status=data.get("status", "published"),
            assessment_id=data.get("assessment_id"),
        )
        db.add(certification)
        await db.flush()
        return certification

    async def update(self, db: AsyncSession, *, organization_id: str, certification_id: str, data: dict[str, Any]) -> Optional[Certification]:
        certification = await self.get(db, organization_id=organization_id, certification_id=certification_id)
        if certification is None:
            return None
        for key, value in data.items():
            if value is not None and hasattr(certification, key):
                setattr(certification, key, value)
        await db.flush()
        return certification

    async def get(self, db: AsyncSession, *, organization_id: str, certification_id: str) -> Optional[Certification]:
        return (
            await db.execute(
                select(Certification).where(
                    Certification.organization_id == organization_id,
                    Certification.id == certification_id,
                )
            )
        ).scalar_one_or_none()

    async def list_certifications(
        self, db: AsyncSession, *, organization_id: str, category: Optional[str] = None, status: str = "published",
        limit: Optional[int] = None,
    ) -> list[Certification]:
        query = select(Certification).where(Certification.organization_id == organization_id)
        if status:
            query = query.where(Certification.status == status)
        if category:
            query = query.where(Certification.category == category)
        if limit is not None:
            query = query.limit(limit)
        return (await db.execute(query.order_by(Certification.category, Certification.name))).scalars().all()

    async def categories(self, db: AsyncSession, *, organization_id: str) -> list[str]:
        rows = await db.execute(
            select(Certification.category)
            .where(Certification.organization_id == organization_id, Certification.category.isnot(None))
            .distinct()
        )
        return sorted(c for c in rows.scalars().all() if c)

    # ------------------------------------------------------------------ attempts

    async def start_attempt(self, db: AsyncSession, *, organization_id: str, certification_id: str, employee_id: str) -> Optional[CertificationAttempt]:
        certification = await self.get(db, organization_id=organization_id, certification_id=certification_id)
        if certification is None or certification.status != "published":
            return None
        attempt = CertificationAttempt(
            organization_id=organization_id,
            certification_id=certification_id,
            employee_id=employee_id,
            status="in_progress",
            attempted_at=utcnow(),
        )
        db.add(attempt)
        await db.flush()
        return attempt

    async def complete_attempt(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        attempt_id: str,
        employee_id: str,
        score: Optional[float] = None,
        passed: Optional[bool] = None,
        evidence: Optional[str] = None,
    ) -> Optional[CertificationAttempt]:
        attempt = (
            await db.execute(
                select(CertificationAttempt).where(
                    CertificationAttempt.organization_id == organization_id,
                    CertificationAttempt.id == attempt_id,
                    CertificationAttempt.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if attempt is None:
            return None
        certification = await self.get(db, organization_id=organization_id, certification_id=attempt.certification_id)
        if passed is None and score is not None:
            passed = score >= 70.0
        attempt.score = score
        attempt.evidence = evidence
        attempt.completed_at = utcnow()
        attempt.status = "passed" if passed else "failed"
        await db.flush()
        if passed:
            await self.issue_certificate(
                db,
                organization_id=organization_id,
                certification=certification,
                employee_id=employee_id,
                attempt_id=attempt.id,
                score=score,
            )
        return attempt

    async def issue_certificate(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        certification: Optional[Certification],
        employee_id: str,
        attempt_id: Optional[str] = None,
        score: Optional[float] = None,
        title: Optional[str] = None,
        course_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[CertificationEarned]:
        """Issue (or refresh) an earned certificate for an employee."""
        name = title or (certification.name if certification else "VCOS Certificate")
        validity_years = certification.validity_years if certification else 2
        cert_skills = certification.skills if certification else None
        cert_id = certification.id if certification else None
        today = utcnow().date()
        existing = None
        if certification:
            existing = (
                await db.execute(
                    select(CertificationEarned).where(
                        CertificationEarned.organization_id == organization_id,
                        CertificationEarned.certification_id == certification.id,
                        CertificationEarned.employee_id == employee_id,
                    )
                )
            ).scalar_one_or_none()
        if existing:
            existing.earned_at = utcnow()
            existing.expiry_date = today.replace(year=today.year + validity_years)
            existing.status = "valid"
            existing.attempt_id = attempt_id
            await db.flush()
            earned = existing
        else:
            earned = CertificationEarned(
                organization_id=organization_id,
                certification_id=cert_id,
                employee_id=employee_id,
                attempt_id=attempt_id,
                earned_at=utcnow(),
                expiry_date=today.replace(year=today.year + validity_years),
                credential_id=f"VCOS-{name[:3].upper()}-{employee_id[:6].upper()}",
                status="valid",
                meta={"title": name, "course_id": course_id, "category": category}
                if course_id
                else None,
            )
            db.add(earned)
            await db.flush()

        # mirror into the HR profile + learning profile
        emp_cert = (
            await db.execute(
                select(EmployeeCertification).where(
                    EmployeeCertification.organization_id == organization_id,
                    EmployeeCertification.employee_id == employee_id,
                    EmployeeCertification.name == name,
                )
            )
        ).scalar_one_or_none()
        if emp_cert is None:
            db.add(
                EmployeeCertification(
                    organization_id=organization_id,
                    employee_id=employee_id,
                    name=name,
                    issuer=certification.issuer if certification else "VCOS Academy",
                    credential_id=earned.credential_id,
                    issue_date=today,
                    expiry_date=earned.expiry_date,
                    verified=True,
                )
            )
        else:
            emp_cert.issue_date = today
            emp_cert.expiry_date = earned.expiry_date
            emp_cert.verified = True

        profile = (
            await db.execute(
                select(LearningProfile).where(
                    LearningProfile.organization_id == organization_id,
                    LearningProfile.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if profile:
            profile.certifications = (profile.certifications or 0) + (0 if existing else 1)
            profile.learning_score = min(100.0, (profile.learning_score or 0) + 7.0)
            profile.last_learning_date = utcnow()

        db.add(
            LearningHistoryEntry(
                organization_id=organization_id,
                employee_id=employee_id,
                kind="certification",
                title=f"Certified: {name}",
                entity_id=cert_id or course_id,
                score=score,
                certificate_id=earned.id,
                meta={"category": category or (certification.category if certification else None)},
                occurred_at=utcnow(),
            )
        )

        # skills from the certification feed the skill graph
        if cert_skills:
            from app.learning.skill_service import skill_service
            for skill_name in cert_skills:
                await skill_service.boost_skill(
                    db, organization_id=organization_id, employee_id=employee_id,
                    skill_name=skill_name, points=0.5, source="certification",
                    reason=f"Earned {name}",
                )

        await _event_bus.publish(
            db,
            name="certificate.earned",
            organization_id=organization_id,
            actor_id=employee_id,
            payload={
                "employee_id": employee_id,
                "certification_id": cert_id,
                "certification_name": name,
                "earned_id": earned.id,
            },
            flush=False,
        )
        return earned

    async def issue_course_certificate(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        title: str, course_id: str, category: Optional[str] = None,
    ) -> Optional[CertificationEarned]:
        return await self.issue_certificate(
            db, organization_id=organization_id, certification=None,
            employee_id=employee_id, title=title, course_id=course_id, category=category,
        )

    async def my_certifications(self, db: AsyncSession, *, organization_id: str, employee_id: str, status: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(CertificationEarned).where(
            CertificationEarned.organization_id == organization_id,
            CertificationEarned.employee_id == employee_id,
        )
        if status:
            query = query.where(CertificationEarned.status == status)
        rows = (await db.execute(query.order_by(CertificationEarned.earned_at.desc()))).scalars().all()
        result = []
        for earned in rows:
            certification = None
            if earned.certification_id:
                certification = await self.get(db, organization_id=organization_id, certification_id=earned.certification_id)
            meta = earned.meta or {}
            result.append(
                {
                    "id": earned.id,
                    "certification_id": earned.certification_id,
                    "name": certification.name if certification else meta.get("title") or "VCOS Certificate",
                    "category": certification.category if certification else meta.get("category"),
                    "level": certification.level if certification else None,
                    "issuer": certification.issuer if certification else "VCOS Academy",
                    "earned_at": earned.earned_at.isoformat() if earned.earned_at else None,
                    "expiry_date": earned.expiry_date.isoformat() if earned.expiry_date else None,
                    "credential_id": earned.credential_id,
                    "status": earned.status,
                    "course_id": meta.get("course_id"),
                }
            )
        return result

    async def expiring(self, db: AsyncSession, *, organization_id: str, days: int = 30) -> list[CertificationEarned]:
        """Certifications expiring within N days (worker + notifications)."""
        today = utcnow().date()
        horizon = today + timedelta(days=days)
        rows = await db.execute(
            select(CertificationEarned).where(
                CertificationEarned.organization_id == organization_id,
                CertificationEarned.status == "valid",
                CertificationEarned.expiry_date.isnot(None),
                CertificationEarned.expiry_date <= horizon,
            )
        )
        return rows.scalars().all()

    async def mark_expired(self, db: AsyncSession, *, organization_id: str) -> int:
        """Mark certifications past expiry (worker pass)."""
        today = utcnow().date()
        rows = (
            await db.execute(
                select(CertificationEarned).where(
                    CertificationEarned.organization_id == organization_id,
                    CertificationEarned.status.in_(("valid", "expiring_soon")),
                    CertificationEarned.expiry_date.isnot(None),
                    CertificationEarned.expiry_date < today,
                )
            )
        ).scalars().all()
        for row in rows:
            row.status = "expired"
        await db.flush()
        return len(rows)

    async def recommended_for(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        skill_names: Optional[list[str]] = None, limit: int = 5,
    ) -> list[Certification]:
        """Certifications that cover the employee's gap skills."""
        query = select(Certification).where(
            Certification.organization_id == organization_id,
            Certification.status == "published",
        )
        certifications = (await db.execute(query.limit(100))).scalars().all()
        earned = await self.my_certifications(db, organization_id=organization_id, employee_id=employee_id)
        earned_ids = {row["certification_id"] for row in earned if row["certification_id"]}
        if skill_names:
            wanted = {s.strip().lower() for s in skill_names if s and s.strip()}
            scored = []
            for cert in certifications:
                if cert.id in earned_ids:
                    continue
                tags = {str(t).lower() for t in (cert.skills or [])}
                tags.add(cert.name.lower())
                score = len(wanted & tags)
                if score:
                    scored.append((score, cert))
            scored.sort(key=lambda pair: -pair[0])
            return [c for _, c in scored[:limit]]
        return [c for c in certifications if c.id not in earned_ids][:limit]


certification_service = CertificationService()
