"""Phase 9.8b — Organizational pattern detection engine.

Identifies repeated delays, incidents, approval bottlenecks, knowledge gaps
and onboarding problems. A pattern becomes an insight only when it repeats
enough times (count threshold) — single events are not patterns.
"""

import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.approval import Approval
from app.models.intelligence import PatternDetection
from app.models.project import Project

logger = logging.getLogger("vcos.intelligence.pattern")

MIN_REPEATS = 3


class PatternEngine:
    async def scan(self, db: AsyncSession, *, organization_id: str) -> int:
        """Detect all pattern types; returns number of new/updated patterns."""
        created = 0
        created += await self._repeated_project_delays(db, organization_id=organization_id)
        created += await self._approval_bottlenecks(db, organization_id=organization_id)
        created += await self._knowledge_gaps(db, organization_id=organization_id)
        return created

    async def _upsert(
        self, db: AsyncSession, *, organization_id: str, pattern_type: str,
        key: str, title: str, detail: Optional[str], count: int,
        confidence: float, evidence: Optional[str] = None,
    ) -> int:
        row = (
            await db.execute(
                select(PatternDetection).where(
                    PatternDetection.organization_id == organization_id,
                    PatternDetection.pattern_type == pattern_type,
                    PatternDetection.key == key,
                )
            )
        ).scalar_one_or_none()
        now = utcnow()
        if row is None:
            db.add(
                PatternDetection(
                    organization_id=organization_id,
                    pattern_type=pattern_type, key=key,
                    title=title, detail=detail, count=count,
                    confidence=confidence, evidence=evidence,
                    status="open", first_seen=now, last_seen=now,
                )
            )
            return 1
        row.count = count
        row.title = title
        row.detail = detail
        row.confidence = confidence
        row.evidence = evidence or row.evidence
        row.last_seen = now
        return 0

    async def _repeated_project_delays(self, db: AsyncSession, *, organization_id: str) -> int:
        from app.models.task import Task

        now = utcnow()
        projects = list(
            (
                await db.execute(
                    select(Project).where(Project.organization_id == organization_id)
                )
            ).scalars().all()
        )
        created = 0
        for project in projects:
            overdue_tasks = (
                await db.execute(
                    select(func.count(Task.id)).where(
                        Task.organization_id == organization_id,
                        Task.project_id == project.id,
                        Task.status != "completed",
                        Task.due_date.isnot(None),
                        Task.due_date < now.date(),
                    )
                )
            ).scalar() or 0
            if overdue_tasks < MIN_REPEATS:
                continue
            created += await self._upsert(
                db, organization_id=organization_id,
                pattern_type="repeated_delay",
                key=f"project:{project.id}",
                title=f"Repeated delays: {project.name}",
                detail=f"{overdue_tasks} open tasks are past their due dates.",
                count=overdue_tasks,
                confidence=min(0.95, 0.5 + overdue_tasks * 0.08),
                evidence=f"project={project.id}",
            )
        return created

    async def _approval_bottlenecks(self, db: AsyncSession, *, organization_id: str) -> int:
        """Approvals left pending more than 5 days, aggregated by approver."""
        from app.core.timeutils import ensure_aware

        cutoff = utcnow() - timedelta(days=5)
        rows = (
            await db.execute(
                select(Approval.approver_id, func.count(Approval.id))
                .where(
                    Approval.organization_id == organization_id,
                    Approval.status == "pending",
                    Approval.created_at < cutoff,
                )
                .group_by(Approval.approver_id)
            )
        ).all()
        created = 0
        for approver_id, count in rows:
            if not approver_id:
                continue
            created += await self._upsert(
                db, organization_id=organization_id,
                pattern_type="approval_bottleneck",
                key=f"approver:{approver_id}",
                title="Approval bottleneck detected",
                detail=f"{count} approvals have been pending over 5 days for one approver.",
                count=count,
                confidence=min(0.95, 0.55 + count * 0.1),
                evidence=f"approver={approver_id}",
            )
        return created

    async def _knowledge_gaps(self, db: AsyncSession, *, organization_id: str) -> int:
        """Skills with employees but no knowledge documents mention them."""
        from app.models.employee import EmployeeSkill
        from app.models.knowledge import Document
        from app.models.skill import Skill

        rows = (
            await db.execute(
                select(Skill.id, Skill.name, func.count(func.distinct(EmployeeSkill.employee_id)))
                .join(EmployeeSkill, EmployeeSkill.skill_id == Skill.id)
                .where(EmployeeSkill.organization_id == organization_id)
                .group_by(Skill.id, Skill.name)
                .having(func.count(func.distinct(EmployeeSkill.employee_id)) >= MIN_REPEATS)
            )
        ).all()
        documents = list(
            (
                await db.execute(
                    select(Document.title).where(Document.organization_id == organization_id)
                )
            ).scalars().all()
        )
        doc_text = " ".join((d or "").lower() for d in documents)
        created = 0
        for skill_id, skill_name, employee_count in rows:
            if skill_name.lower() in doc_text:
                continue
            created += await self._upsert(
                db, organization_id=organization_id,
                pattern_type="knowledge_gap",
                key=f"skill:{skill_id}",
                title=f"Knowledge gap: no documentation for '{skill_name}'",
                detail=f"{employee_count} employees list this skill but no documents cover it.",
                count=employee_count,
                confidence=0.7,
                evidence=f"skill={skill_id}",
            )
        return created

    async def list_patterns(
        self, db: AsyncSession, *, organization_id: str, limit: int = 50,
        pattern_type: Optional[str] = None, status: Optional[str] = "open",
    ) -> list[dict[str, Any]]:
        filters = [PatternDetection.organization_id == organization_id]
        if pattern_type:
            filters.append(PatternDetection.pattern_type == pattern_type)
        if status:
            filters.append(PatternDetection.status == status)
        rows = (
            await db.execute(
                select(PatternDetection).where(*filters)
                .order_by(PatternDetection.count.desc(), PatternDetection.last_seen.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "pattern_type": r.pattern_type,
                "key": r.key,
                "title": r.title,
                "detail": r.detail,
                "count": r.count,
                "confidence": r.confidence,
                "evidence": r.evidence,
                "status": r.status,
                "first_seen": r.first_seen.isoformat() if r.first_seen else None,
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            }
            for r in rows
        ]

    async def set_status(self, db: AsyncSession, *, organization_id: str, pattern_id: str, status: str) -> Optional[dict[str, Any]]:
        row = await db.get(PatternDetection, pattern_id)
        if row is None or row.organization_id != organization_id:
            return None
        row.status = status
        return {"id": row.id, "status": row.status}


pattern_engine = PatternEngine()
