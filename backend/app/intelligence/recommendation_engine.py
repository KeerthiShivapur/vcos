"""Phase 9.7/9.12 — Personalized recommendation engine.

Without being asked, the engine generates a feed of recommendations for every
employee: experts to consult, documents to read, mentors, training topics,
communities, projects, and career-growth suggestions.

Signals used per recipient:
    - their skills and expertise gaps
    - who they collaborate with (graph edges)
    - popular knowledge in their areas
    - mentors (higher expertise in matching skills)
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeeSkill
from app.models.intelligence import RecommendationItem
from app.models.knowledge import Document, WikiPage
from app.models.skill import ExpertiseScore, Skill
from app.models.user import User

logger = logging.getLogger("vcos.intelligence.recommendation")

MAX_FEED = 25


class RecommendationEngine:
    async def generate_for_user(
        self, db: AsyncSession, *, organization_id: str, user_id: str,
    ) -> list[dict[str, Any]]:
        """Regenerate the personal feed for one user (idempotent per kind+entity)."""
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if employee is None:
            return []
        await self._clear_active(db, organization_id, employee.id)
        items: list[RecommendationItem] = []

        # --- skill profile
        emp_skills = list(
            (
                await db.execute(
                    select(EmployeeSkill).where(
                        EmployeeSkill.organization_id == organization_id,
                        EmployeeSkill.employee_id == employee.id,
                    )
                )
            ).scalars().all()
        )
        skill_ids = [s.skill_id for s in emp_skills]
        skills = {
            s.id: s
            for s in (
                await db.execute(
                    select(Skill).where(
                        Skill.organization_id == organization_id,
                        Skill.id.in_(skill_ids) if skill_ids else Skill.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        } if skill_ids else {}

        # --- 1. experts in the user's skills (higher scores)
        if skill_ids:
            rows = (
                await db.execute(
                    select(ExpertiseScore.employee_id, func.max(ExpertiseScore.score))
                    .where(
                        ExpertiseScore.organization_id == organization_id,
                        ExpertiseScore.skill_id.in_(skill_ids),
                        ExpertiseScore.employee_id != employee.id,
                    )
                    .group_by(ExpertiseScore.employee_id)
                    .order_by(func.max(ExpertiseScore.score).desc())
                    .limit(5)
                )
            ).all()
            for expert_id, top_score in rows:
                if top_score < 40:
                    continue
                expert = await db.get(Employee, expert_id)
                if expert is None:
                    continue
                items.append(
                    self._item(
                        organization_id, employee.id, "expert",
                        title=f"Connect with {expert.display_name or expert.first_name}",
                        body=f"{expert.designation or 'Colleague'} with strong expertise ({top_score:.0f}) in your skill areas.",
                        entity_type="employee", entity_id=expert.id,
                        score=min(1.0, top_score / 100),
                        reasons=[f"Expertise {top_score:.0f} in your skill areas"],
                    )
                )

        # --- 2. documents matching their skills (popular knowledge)
        if skill_ids:
            doc_rows = (
                await db.execute(
                    select(Document)
                    .where(
                        Document.organization_id == organization_id,
                        Document.status == "published",
                        Document.author_id != employee.id,
                    )
                    .order_by(Document.view_count.desc())
                    .limit(8)
                )
            ).scalars().all()
            for doc in doc_rows:
                haystack = f"{doc.title} {doc.category or ''} {doc.keywords or ''}".lower()
                if not any(skills[s].name.lower() in haystack for s in skills if skills[s].name):
                    continue
                items.append(
                    self._item(
                        organization_id, employee.id, "document",
                        title=f"Read: {doc.title}",
                        body=f"Popular document related to your skills ({doc.view_count} views).",
                        entity_type="document", entity_id=doc.id,
                        score=min(1.0, 0.3 + doc.view_count / 200),
                        reasons=[f"{doc.view_count} views", "Matches your skill profile"],
                    )
                )

        # --- 3. mentors: highest expertise in user's weakest skills
        if skill_ids:
            my_scores = {
                s.skill_id: s.score
                for s in (
                    await db.execute(
                        select(ExpertiseScore).where(
                            ExpertiseScore.organization_id == organization_id,
                            ExpertiseScore.employee_id == employee.id,
                        )
                    )
                ).scalars().all()
            }
            weakest = sorted(skill_ids, key=lambda sid: my_scores.get(sid, 0))[:2]
            for skill_id in weakest:
                best = (
                    await db.execute(
                        select(ExpertiseScore).where(
                            ExpertiseScore.organization_id == organization_id,
                            ExpertiseScore.skill_id == skill_id,
                            ExpertiseScore.employee_id != employee.id,
                        )
                        .order_by(ExpertiseScore.score.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if best is None or best.score < 50:
                    continue
                mentor = await db.get(Employee, best.employee_id)
                if mentor is None:
                    continue
                skill_name = skills.get(skill_id).name if skills.get(skill_id) else skill_id
                items.append(
                    self._item(
                        organization_id, employee.id, "mentor",
                        title=f"Mentor suggestion: {mentor.display_name or mentor.first_name}",
                        body=f"Top scorer ({best.score:.0f}) in '{skill_name}', which is a growth area for you.",
                        entity_type="employee", entity_id=mentor.id,
                        score=0.8,
                        reasons=[f"Growth area: {skill_name}"],
                    )
                )

        # --- 4. communities they are not in yet
        from app.models.communication import Community, CommunityMember

        memberships = set(
            (
                await db.execute(
                    select(CommunityMember.community_id).where(
                        CommunityMember.organization_id == organization_id,
                        CommunityMember.employee_id == employee.id,
                    )
                )
            ).scalars().all()
        )
        communities = list(
            (
                await db.execute(
                    select(Community).where(Community.organization_id == organization_id)
                )
            ).scalars().all()
        )
        for community in communities:
            if community.id in memberships:
                continue
            items.append(
                self._item(
                    organization_id, employee.id, "community",
                    title=f"Join community: {community.name}",
                    body=community.description or "A community at your organization.",
                    entity_type="community", entity_id=community.id,
                    score=0.5,
                    reasons=["Community you have not joined"],
                )
            )

        # --- 5. wiki knowledge matching skills
        if skill_ids:
            wiki_rows = (
                await db.execute(
                    select(WikiPage)
                    .where(
                        WikiPage.organization_id == organization_id,
                        WikiPage.status == "published",
                    )
                    .order_by(WikiPage.view_count.desc())
                    .limit(6)
                )
            ).scalars().all()
            for page in wiki_rows:
                haystack = f"{page.title} {page.category or ''} {page.keywords or ''}".lower()
                if not any(skills[s].name.lower() in haystack for s in skills if skills[s].name):
                    continue
                items.append(
                    self._item(
                        organization_id, employee.id, "knowledge",
                        title=f"Learn: {page.title}",
                        body="Wiki knowledge matching your skill profile.",
                        entity_type="wiki", entity_id=page.id,
                        score=0.5,
                        reasons=["Matches your skill profile"],
                    )
                )

        db.add_all(items)
        await db.flush()
        if items:
            from app.events.publisher import publish_background_event

            await publish_background_event(
                db,
                name="recommendation.generated",
                organization_id=organization_id,
                payload={"recipient_id": employee.id, "items": len(items)},
            )
        return [self._payload(i) for i in items[:MAX_FEED]]

    def _item(
        self, organization_id: str, employee_id: str, kind: str,
        title: str, body: Optional[str], entity_type: Optional[str],
        entity_id: Optional[str], score: float, reasons: list[str],
    ) -> RecommendationItem:
        return RecommendationItem(
            organization_id=organization_id,
            recipient_id=employee_id,
            kind=kind,
            title=title[:300],
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            score=round(score, 3),
            reasons_json=json.dumps(reasons[:3]),
            status="active",
        )

    async def _clear_active(self, db: AsyncSession, organization_id: str, employee_id: str) -> None:
        rows = (
            await db.execute(
                select(RecommendationItem).where(
                    RecommendationItem.organization_id == organization_id,
                    RecommendationItem.recipient_id == employee_id,
                    RecommendationItem.status == "active",
                )
            )
        ).scalars().all()
        for row in rows:
            row.status = "dismissed"

    async def feed(
        self, db: AsyncSession, *, organization_id: str, user_id: str, limit: int = 25,
    ) -> list[dict[str, Any]]:
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if employee is None:
            return []
        rows = (
            await db.execute(
                select(RecommendationItem)
                .where(
                    RecommendationItem.organization_id == organization_id,
                    RecommendationItem.recipient_id == employee.id,
                    RecommendationItem.status == "active",
                )
                .order_by(RecommendationItem.score.desc(), RecommendationItem.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        if not rows:
            return await self.generate_for_user(db, organization_id=organization_id, user_id=user_id)
        return [self._payload(r) for r in rows]

    def _payload(self, item: RecommendationItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "kind": item.kind,
            "title": item.title,
            "body": item.body,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "score": item.score,
            "reasons": item.reasons,
            "status": item.status,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    async def set_status(self, db: AsyncSession, *, organization_id: str, item_id: str, status: str, user_id: str) -> Optional[dict[str, Any]]:
        row = await db.get(RecommendationItem, item_id)
        if row is None or row.organization_id != organization_id:
            return None
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if employee is None or row.recipient_id != employee.id:
            return None
        row.status = status
        return {"id": row.id, "status": row.status}


recommendation_engine = RecommendationEngine()
