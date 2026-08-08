"""Innovation hub service — idea pitches, votes, promotion to projects (Phase 5.9)."""

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.events import emit_and_audit, notify_mentions, notify_user
from app.models.communication import IdeaVote, InnovationIdea
from app.models.employee import Employee


class InnovationService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> InnovationIdea:
        idea = InnovationIdea(
            organization_id=organization_id,
            author_id=actor.id,
            title=payload["title"],
            description=payload.get("description"),
            problem=payload.get("problem"),
            solution=payload.get("solution"),
            impact=payload.get("impact"),
            tags=payload.get("tags"),
            status="submitted",
        )
        db.add(idea)
        await db.flush()
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="innovation.submitted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"idea_id": idea.id, "title": idea.title},
            resource_type="innovation_idea",
            resource_id=idea.id,
        )
        await notify_mentions(
            db,
            organization_id=organization_id,
            text="\n".join(filter(None, (idea.description, idea.problem, idea.solution, idea.impact))),
            type="mention",
            title="You were mentioned in an innovation idea",
            body=idea.title,
            actor_id=actor.id,
            link=f"/innovation/{idea.id}",
            entity_type="innovation_idea",
            entity_id=idea.id,
        )
        return idea

    async def get(self, db: AsyncSession, *, organization_id: str, idea_id: str) -> Optional[InnovationIdea]:
        return (
            await db.execute(
                select(InnovationIdea).where(
                    InnovationIdea.organization_id == organization_id,
                    InnovationIdea.id == idea_id,
                )
            )
        ).scalar_one_or_none()

    async def list_all(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InnovationIdea]:
        filters = [InnovationIdea.organization_id == organization_id]
        if status:
            filters.append(InnovationIdea.status == status)
        if search:
            filters.append(
                func.lower(InnovationIdea.title).like(f"%{search.lower()}%")
                | func.lower(InnovationIdea.description).like(f"%{search.lower()}%")
            )
        return list(
            (
                await db.execute(
                    select(InnovationIdea)
                    .where(*filters)
                    .order_by(InnovationIdea.vote_count.desc(), InnovationIdea.created_at.desc())
                    .limit(min(limit, 500))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def update(
        self, db: AsyncSession, *, organization_id: str, idea_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Optional[InnovationIdea]:
        idea = await self.get(db, organization_id=organization_id, idea_id=idea_id)
        if idea is None:
            return None
        editable = {
            "title", "description", "problem", "solution", "impact", "tags",
        }
        for key, value in payload.items():
            if key in editable and value is not None:
                setattr(idea, key, value)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="innovation.updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"idea_id": idea_id},
            resource_type="innovation_idea",
            resource_id=idea_id,
        )
        return idea

    async def update_status(
        self, db: AsyncSession, *, organization_id: str, idea_id: str, status: str, feedback: Optional[str], actor: Employee, ip_address: Optional[str]
    ) -> Optional[InnovationIdea]:
        idea = await self.get(db, organization_id=organization_id, idea_id=idea_id)
        if idea is None:
            return None
        idea.status = status
        if feedback is not None:
            idea.ai_insight = feedback
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="innovation.status_changed",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"idea_id": idea_id, "status": status, "feedback": feedback},
            resource_type="innovation_idea",
            resource_id=idea_id,
        )
        if idea.author_id and idea.author_id != actor.id:
            await notify_user(
                db,
                organization_id=organization_id,
                recipient_id=idea.author_id,
                type="community.activity",
                title=f"Idea status updated: {status.replace('_', ' ')}",
                body=feedback or idea.title,
                actor_id=actor.id,
                link=f"/innovation/{idea_id}",
                entity_type="innovation_idea",
                entity_id=idea_id,
            )
        return idea

    async def delete(
        self, db: AsyncSession, *, organization_id: str, idea_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        idea = await self.get(db, organization_id=organization_id, idea_id=idea_id)
        if idea is None:
            return False
        await db.delete(idea)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="innovation.deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"idea_id": idea_id},
            resource_type="innovation_idea",
            resource_id=idea_id,
        )
        return True

    async def vote(self, db: AsyncSession, *, organization_id: str, idea_id: str, actor: Employee) -> dict[str, Any]:
        idea = await self.get(db, organization_id=organization_id, idea_id=idea_id)
        if idea is None:
            raise ValueError("Idea not found")
        row = (
            await db.execute(
                select(IdeaVote).where(
                    IdeaVote.organization_id == organization_id,
                    IdeaVote.idea_id == idea_id,
                    IdeaVote.employee_id == actor.id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            await db.delete(row)
            idea.vote_count = max(0, (idea.vote_count or 1) - 1)
            voted = False
        else:
            db.add(
                IdeaVote(
                    organization_id=organization_id,
                    idea_id=idea_id,
                    employee_id=actor.id,
                )
            )
            idea.vote_count = (idea.vote_count or 0) + 1
            voted = True
            if idea.author_id and idea.author_id != actor.id:
                await notify_user(
                    db,
                    organization_id=organization_id,
                    recipient_id=idea.author_id,
                    type="community.activity",
                    title="Your idea received a vote",
                    body=idea.title,
                    actor_id=actor.id,
                    link=f"/innovation/{idea_id}",
                    entity_type="innovation_idea",
                    entity_id=idea_id,
                )
        return {"voted": voted, "vote_count": idea.vote_count}

    async def my_vote(self, db: AsyncSession, *, organization_id: str, idea_id: str, employee_id: str) -> bool:
        row = (
            await db.execute(
                select(IdeaVote.id).where(
                    IdeaVote.organization_id == organization_id,
                    IdeaVote.idea_id == idea_id,
                    IdeaVote.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        return row is not None

    async def promote_to_project(
        self, db: AsyncSession, *, organization_id: str, idea_id: str, project_id: Optional[str], actor: Employee, ip_address: Optional[str]
    ) -> Optional[InnovationIdea]:
        idea = await self.get(db, organization_id=organization_id, idea_id=idea_id)
        if idea is None:
            return None
        idea.status = "approved"
        if project_id:
            idea.project_id = project_id
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="innovation.promoted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"idea_id": idea_id, "title": idea.title, "project_id": project_id},
            resource_type="innovation_idea",
            resource_id=idea_id,
        )
        if idea.author_id and idea.author_id != actor.id:
            await notify_user(
                db,
                organization_id=organization_id,
                recipient_id=idea.author_id,
                type="community.activity",
                title="Your idea was promoted to a project",
                body=idea.title,
                actor_id=actor.id,
                link=f"/innovation/{idea_id}",
                entity_type="innovation_idea",
                entity_id=idea_id,
            )
        return idea

    async def stats(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        total = (
            await db.execute(select(func.count(InnovationIdea.id)).where(InnovationIdea.organization_id == organization_id))
        ).scalar_one()
        by_status = list(
            (
                await db.execute(
                    select(InnovationIdea.status, func.count(InnovationIdea.id))
                    .where(InnovationIdea.organization_id == organization_id)
                    .group_by(InnovationIdea.status)
                )
            ).all()
        )
        return {
            "total": total,
            "by_status": [{"status": r[0], "count": r[1]} for r in by_status],
        }


innovation_service = InnovationService()
