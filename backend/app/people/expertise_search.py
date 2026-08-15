"""Slice 4F.2 — governed expertise discovery.

Expertise search ranks by evidence-derived state (score, confidence, recency,
evidence count) — never by name/keyword matching alone — inside the caller's
governance scope. The pipeline is always:

    caller -> organization -> permissions -> visible people -> expertise
    calculation/retrieval -> answer

Never: calculate across the company and hide names afterward — the aggregate
itself may leak (so aggregates are gated per scope in capability_engine).

Every request here is bounded: extraction <= MAX_EXTRACT skills, results
<= limit (<= 50), lineage <= 200 rows, and the visibility filter is applied
in SQL against indexed person/skill keys.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.company_context import CallerAccess
from app.models.employee import Employee
from app.models.skills_intelligence import (
    CanonicalSkill,
    PersonSkill,
    Expertise as ExpertiseState,
)
from app.people.skill_engine import skill_engine, MAX_EXTRACT

logger = logging.getLogger("vcos.people.expertise_search")

MAX_RESULTS = 50


class ExpertiseSearch:
    async def resolve_for_query(
        self, db: AsyncSession, *, organization_id: str, query: str,
    ) -> list[CanonicalSkill]:
        """Deterministic: exact single term first, container-probing for
        multi-term phrases, bounded by MAX_EXTRACT."""
        query = (query or "").strip()
        if not query:
            return []
        await skill_engine.ensure_taxonomy(db, organization_id=organization_id)
        single = await skill_engine.resolve_term(
            db, organization_id=organization_id, term=query
        )
        if single is not None:
            return [single]
        import re as _re

        terms = [
            t for t in _re.split(r"[^a-z0-9+#.]+", query.lower()) if len(t) > 2
        ]
        return await skill_engine.resolve_candidates(
            db, organization_id=organization_id, terms=terms or [query.lower()]
        )

    async def search(
        self,
        db: AsyncSession, *, organization_id: str, access: CallerAccess,
        query: str, scope_type: Optional[str] = None,
        scope_id: Optional[str] = None, limit: int = MAX_RESULTS,
    ) -> dict[str, Any]:
        """Governed ranked expert discovery for a skill query."""
        from app.people.people_engine import people_engine

        limit = max(1, min(limit, MAX_RESULTS))
        skills = await self.resolve_for_query(
            db, organization_id=organization_id, query=query
        )
        if not skills:
            return {
                "query": query,
                "resolved_skill_ids": [],
                "skills": [],
                "experts": [],
                "total": 0,
                "scope": "org" if access.org_wide else "project",
            }
        skill_ids = [s.id for s in skills]
        skill_names = {s.id: (s.canonical_name, s.category) for s in skills}

        visible = await people_engine.visible_person_ids(
            db, organization_id=organization_id, access=access
        )
        filters = [
            ExpertiseState.organization_id == organization_id,
            ExpertiseState.skill_id.in_(skill_ids),
            ExpertiseState.score > 0,
        ]
        if visible is not None:
            filters.append(ExpertiseState.person_id.in_(set(visible)))
        scope_filters = []
        if scope_type == "team" and scope_id:
            scope_filters.append(Employee.team_id == scope_id)
        elif scope_type == "department" and scope_id:
            scope_filters.append(Employee.department_id == scope_id)
        elif scope_type == "business_unit" and scope_id:
            scope_filters.append(Employee.business_unit_id == scope_id)

        query_obj = (
            select(
                ExpertiseState.person_id, ExpertiseState.skill_id,
                ExpertiseState.score, ExpertiseState.confidence,
                ExpertiseState.lifecycle, ExpertiseState.evidence_count,
                ExpertiseState.last_observed, ExpertiseState.frequency_90d,
                Employee.display_name, Employee.first_name, Employee.last_name,
                Employee.designation, Employee.team_id, Employee.department_id,
                Employee.status,
            )
            .join(Employee, Employee.id == ExpertiseState.person_id)
            .where(*filters)
        )
        if scope_filters:
            query_obj = query_obj.where(*scope_filters)
        rows = (
            await db.execute(
                query_obj.order_by(
                    ExpertiseState.score.desc(),
                    ExpertiseState.confidence.desc(),
                    ExpertiseState.last_observed.desc(),
                ).limit(limit)
            )
        ).all()

        team_ids = {r.team_id for r in rows if r.team_id}
        dept_ids = {r.department_id for r in rows if r.department_id}
        names: dict[str, str] = {}
        if team_ids:
            from app.models.team import Team

            names.update(
                (tid, name)
                for tid, name in (
                    await db.execute(
                        select(Team.id, Team.name).where(
                            Team.organization_id == organization_id, Team.id.in_(team_ids)
                        )
                    )
                ).all()
            )
        if dept_ids:
            from app.models.department import Department

            names.update(
                (did, name)
                for did, name in (
                    await db.execute(
                        select(Department.id, Department.name).where(
                            Department.organization_id == organization_id,
                            Department.id.in_(dept_ids),
                        )
                    )
                ).all()
            )

        experts = [
            {
                "person_id": r.person_id,
                "name": r.display_name
                or f"{r.first_name} {r.last_name or ''}".strip(),
                "designation": r.designation,
                "team": names.get(r.team_id),
                "department": names.get(r.department_id),
                "status": r.status,
                "skill_id": r.skill_id,
                "skill_name": skill_names.get(r.skill_id, (r.skill_id, None))[0],
                "category": skill_names.get(r.skill_id, (r.skill_id, None))[1],
                "score": r.score,
                "confidence": r.confidence,
                "lifecycle": r.lifecycle,
                "evidence_count": r.evidence_count,
                "last_observed": r.last_observed.isoformat() if r.last_observed else None,
                "recent_activity_90d": r.frequency_90d,
            }
            for r in rows
        ]
        return {
            "query": query,
            "resolved_skill_ids": skill_ids,
            "skills": [
                {"skill_id": sid, "skill_name": skill_names.get(sid, (sid, None))[0],
                 "category": skill_names.get(sid, (sid, None))[1]}
                for sid in skill_ids
            ],
            "experts": experts,
            "total": len(experts),
            "scope": "org" if access.org_wide else "project",
        }

    # ------------------------------------------------------------------ person surfaces

    async def person_skills(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
    ) -> dict[str, Any]:
        """The person's skill associations (declared + observed) with the
        current evidence-derived overlay. Associations are never expertise."""
        rows = (
            await db.execute(
                select(PersonSkill).where(
                    PersonSkill.organization_id == organization_id,
                    PersonSkill.person_id == person_id,
                    PersonSkill.status == "active",
                ).order_by(PersonSkill.last_seen.desc())
                .limit(200)
            )
        ).scalars().all()
        skills: list[CanonicalSkill] = list(
            (
                await db.execute(
                    select(CanonicalSkill).where(
                        CanonicalSkill.id.in_([r.skill_id for r in rows]),
                    )
                )
            ).scalars().all()
        )
        by_id = {s.id: s for s in skills}
        states = {
            s.skill_id: s
            for s in (
                await db.execute(
                    select(ExpertiseState).where(
                        ExpertiseState.organization_id == organization_id,
                        ExpertiseState.person_id == person_id,
                    )
                )
            ).scalars().all()
        }
        return {
            "person_id": person_id,
            "total": len(rows),
            "skills": [
                {
                    "skill_id": r.skill_id,
                    "skill_name": by_id[r.skill_id].canonical_name if r.skill_id in by_id else r.skill_id,
                    "category": by_id[r.skill_id].category if r.skill_id in by_id else None,
                    "declared_level": r.declared_level,
                    "source": r.source,
                    "status": r.status,
                    "first_seen": r.first_seen.isoformat(),
                    "last_seen": r.last_seen.isoformat(),
                    "expertise": {
                        "score": states[r.skill_id].score,
                        "lifecycle": states[r.skill_id].lifecycle,
                        "evidence_count": states[r.skill_id].evidence_count,
                    } if r.skill_id in states else None,
                }
                for r in rows
            ],
        }

    async def person_expertise(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
    ) -> dict[str, Any]:
        """Evidence-derived expertise states of one person, strongest first."""
        rows = (
            await db.execute(
                select(ExpertiseState).where(
                    ExpertiseState.organization_id == organization_id,
                    ExpertiseState.person_id == person_id,
                    ExpertiseState.score > 0,
                ).order_by(ExpertiseState.score.desc()).limit(200)
            )
        ).scalars().all()
        skills: list[CanonicalSkill] = list(
            (
                await db.execute(
                    select(CanonicalSkill).where(
                        CanonicalSkill.id.in_([r.skill_id for r in rows]),
                    )
                )
            ).scalars().all()
        )
        by_id = {s.id: s for s in skills}
        from app.intelligence.expertise_engine import expertise_engine

        return {
            "person_id": person_id,
            "total": len(rows),
            "expertise": [
                {
                    "skill_id": r.skill_id,
                    "skill_name": by_id[r.skill_id].canonical_name if r.skill_id in by_id else r.skill_id,
                    "category": by_id[r.skill_id].category if r.skill_id in by_id else None,
                    "score": r.score,
                    "confidence": r.confidence,
                    "lifecycle": r.lifecycle,
                    "historical_peak": r.historical_peak,
                    "evidence_count": r.evidence_count,
                    "strong_count": r.strong_count,
                    "medium_count": r.medium_count,
                    "weak_count": r.weak_count,
                    "breadth": r.breadth,
                    "recency_days": r.recency_days,
                    "frequency_90d": r.frequency_90d,
                    "span_months": r.span_months,
                    "first_observed": r.first_observed.isoformat() if r.first_observed else None,
                    "last_observed": r.last_observed.isoformat() if r.last_observed else None,
                }
                for r in rows
            ],
        }


expertise_search = ExpertiseSearch()