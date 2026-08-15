"""Slice 4F.2 — bounded capability aggregates.

Team/department/business-unit/organization capability maps are computed
from bounded indexed SQL rollups — the engine never "for organization in
organizations: for employee in organization.employees: recompute_every_skill".

Change-driven: when one expertise cell changes, exactly the scopes that
contain that person are refreshed (team -> department -> business unit ->
organization). Reads return stored rows, gated by governance.

Leak rule: an aggregate (counts, averages, rankings) is only served to a
caller whose governance scope includes the whole aggregate scope. A hidden
person can never leak through a count that includes them.
"""

import logging
from typing import Any, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.skills_intelligence import (
    AGGREGATE_SCOPE_TYPES,
    CapabilityAggregate,
    Expertise as ExpertiseState,
)
from app.people.skill_engine import MAX_EXTRACT

logger = logging.getLogger("vcos.people.capability")

MAX_CELLS_PER_PERSON = 500   # bounded cells refreshed per person


class CapabilityEngine:
    # ------------------------------------------------------------------ refresh

    async def refresh_person(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
    ) -> int:
        """Change-driven refresh of the scopes containing one person."""
        employee = (
            await db.execute(
                select(
                    Employee.id, Employee.team_id, Employee.department_id,
                    Employee.business_unit_id,
                ).where(
                    Employee.organization_id == organization_id,
                    Employee.id == person_id,
                )
            )
        ).first()
        if employee is None:
            return 0
        skills = list(
            (
                await db.execute(
                    select(ExpertiseState.skill_id).where(
                        ExpertiseState.organization_id == organization_id,
                        ExpertiseState.person_id == person_id,
                        ExpertiseState.score > 0,
                    ).limit(MAX_CELLS_PER_PERSON)
                )
            ).scalars().all()
        )
        refreshed = 0
        for skill_id in skills:
            if employee.team_id:
                await self.refresh_scope(
                    db, organization_id=organization_id,
                    scope_type="team", scope_id=employee.team_id,
                    skill_id=skill_id,
                )
                refreshed += 1
            if employee.department_id:
                await self.refresh_scope(
                    db, organization_id=organization_id,
                    scope_type="department", scope_id=employee.department_id,
                    skill_id=skill_id,
                )
                refreshed += 1
            if employee.business_unit_id:
                await self.refresh_scope(
                    db, organization_id=organization_id,
                    scope_type="business_unit", scope_id=employee.business_unit_id,
                    skill_id=skill_id,
                )
                refreshed += 1
            await self.refresh_scope(
                db, organization_id=organization_id,
                scope_type="organization", scope_id=organization_id,
                skill_id=skill_id,
            )
            refreshed += 1
        return refreshed

    async def refresh_scope(
        self, db: AsyncSession, *, organization_id: str,
        scope_type: str, scope_id: str, skill_id: str,
    ) -> CapabilityAggregate:
        """Upsert ONE (scope x skill) aggregate from a single indexed SQL
        rollup (desired: complexity follows the affected scope, not company
        size)."""
        if scope_type not in AGGREGATE_SCOPE_TYPES:
            raise ValueError(f"unknown aggregate scope type: {scope_type}")
        base = [
            ExpertiseState.organization_id == organization_id,
            ExpertiseState.skill_id == skill_id,
            ExpertiseState.score > 0,
        ]
        joins: list[tuple[type, Any]] = []
        if scope_type == "team":
            joins.append((Employee, Employee.id == ExpertiseState.person_id))
            base.append(Employee.team_id == scope_id)
        elif scope_type == "department":
            joins.append((Employee, Employee.id == ExpertiseState.person_id))
            base.append(Employee.department_id == scope_id)
        elif scope_type == "business_unit":
            joins.append((Employee, Employee.id == ExpertiseState.person_id))
            base.append(Employee.business_unit_id == scope_id)
        elif scope_type == "organization":
            joins.append((Employee, Employee.id == ExpertiseState.person_id))
            base.append(Employee.organization_id == organization_id)

        query = (
            select(
                func.count(func.distinct(ExpertiseState.person_id)),
                func.coalesce(func.sum(ExpertiseState.evidence_count), 0),
                func.coalesce(func.avg(ExpertiseState.score), 0.0),
                func.coalesce(func.max(ExpertiseState.score), 0.0),
                func.count(func.distinct(case(
                    (
                        ExpertiseState.lifecycle.in_(("strong", "authoritative")),
                        ExpertiseState.person_id,
                    ),
                    else_=None,
                ))),
            )
            .select_from(ExpertiseState)
        )
        for model, predicate in joins:
            query = query.join(model, predicate)
        query = query.where(*base)
        (member_count, evidence_count, avg_score, max_score, strong_members) = (
            (await db.execute(query)).one()
        )

        row = (
            await db.execute(
                select(CapabilityAggregate).where(
                    CapabilityAggregate.organization_id == organization_id,
                    CapabilityAggregate.scope_type == scope_type,
                    CapabilityAggregate.scope_id == scope_id,
                    CapabilityAggregate.skill_id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = CapabilityAggregate(
                organization_id=organization_id,
                scope_type=scope_type,
                scope_id=scope_id,
                skill_id=skill_id,
            )
            db.add(row)
        row.member_count = int(member_count or 0)
        row.evidence_count = int(evidence_count or 0)
        row.avg_score = round(float(avg_score or 0.0), 1)
        row.max_score = round(float(max_score or 0.0), 1)
        row.strong_member_count = int(strong_members or 0)
        if row.member_count == 0:
            row.avg_score = 0.0
            row.max_score = 0.0
        db.add(row)
        await db.flush()
        return row

    # ------------------------------------------------------------------ reads

    async def _scope_capabilities(
        self, db: AsyncSession, *, organization_id: str,
        scope_type: str, scope_id: str,
    ) -> list[dict[str, Any]]:
        rows = list(
            (
                await db.execute(
                    select(CapabilityAggregate).where(
                        CapabilityAggregate.organization_id == organization_id,
                        CapabilityAggregate.scope_type == scope_type,
                        CapabilityAggregate.scope_id == scope_id,
                        CapabilityAggregate.member_count > 0,
                    ).order_by(CapabilityAggregate.max_score.desc(), CapabilityAggregate.avg_score.desc())
                    .limit(200)
                )
            ).scalars().all()
        )
        if not rows:
            return []
        from app.models.skills_intelligence import CanonicalSkill

        names = {
            s.id: (s.canonical_name, s.category)
            for s in (
                await db.execute(
                    select(CanonicalSkill).where(CanonicalSkill.id.in_([r.skill_id for r in rows]))
                )
            ).scalars().all()
        }
        return [
            {
                "skill_id": r.skill_id,
                "skill_name": names.get(r.skill_id, (r.skill_id, None))[0],
                "category": names.get(r.skill_id, (r.skill_id, None))[1],
                "member_count": r.member_count,
                "evidence_count": r.evidence_count,
                "avg_score": r.avg_score,
                "max_score": r.max_score,
                "strong_member_count": r.strong_member_count,
            }
            for r in rows
        ]

    async def team_map(
        self, db: AsyncSession, *, organization_id: str, team_id: str,
    ) -> dict[str, Any]:
        capabilities = await self._scope_capabilities(
            db, organization_id=organization_id, scope_type="team", scope_id=team_id
        )
        return {
            "scope_type": "team",
            "scope_id": team_id,
            "total": len(capabilities),
            "capabilities": capabilities,
        }

    async def department_map(
        self, db: AsyncSession, *, organization_id: str, department_id: str,
    ) -> dict[str, Any]:
        capabilities = await self._scope_capabilities(
            db, organization_id=organization_id, scope_type="department", scope_id=department_id
        )
        return {
            "scope_type": "department",
            "scope_id": department_id,
            "total": len(capabilities),
            "capabilities": capabilities,
        }

    async def org_map(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        capabilities = await self._scope_capabilities(
            db, organization_id=organization_id,
            scope_type="organization", scope_id=organization_id,
        )
        return {
            "scope_type": "organization",
            "scope_id": organization_id,
            "total": len(capabilities),
            "capabilities": capabilities,
        }


capability_engine = CapabilityEngine()