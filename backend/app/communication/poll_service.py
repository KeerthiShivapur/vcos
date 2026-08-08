"""Poll service (Phase 5.10)."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.events import emit_and_audit, notify_mentions
from app.models.communication import Poll, PollOption, PollVote
from app.models.employee import Employee


class PollService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Poll:
        poll = Poll(
            organization_id=organization_id,
            title=payload["title"],
            question=payload.get("question"),
            description=payload.get("description"),
            community_id=payload.get("community_id"),
            anonymous=payload.get("anonymous", False),
            multiple_choice=payload.get("multiple_choice", False),
            status=payload.get("status", "open"),
            ends_at=payload.get("ends_at"),
            created_by=actor.id,
        )
        db.add(poll)
        await db.flush()
        for index, option in enumerate(payload.get("options") or []):
            text = option.get("text") if isinstance(option, dict) else option
            sort_order = option.get("sort_order", index) if isinstance(option, dict) else index
            db.add(
                PollOption(
                    organization_id=organization_id,
                    poll_id=poll.id,
                    text=text,
                    sort_order=sort_order,
                )
            )
        await db.flush()
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="poll.created",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"poll_id": poll.id, "title": poll.title, "option_count": len(payload.get("options") or [])},
            resource_type="poll",
            resource_id=poll.id,
        )
        await notify_mentions(
            db,
            organization_id=organization_id,
            text=f"{poll.title} {poll.description or ''}",
            type="mention",
            title="You were mentioned in a poll",
            body=poll.title,
            actor_id=actor.id,
            link=f"/polls/{poll.id}",
            entity_type="poll",
            entity_id=poll.id,
        )
        return poll

    async def get(self, db: AsyncSession, *, organization_id: str, poll_id: str) -> Optional[Poll]:
        return (
            await db.execute(
                select(Poll).where(
                    Poll.organization_id == organization_id,
                    Poll.id == poll_id,
                )
            )
        ).scalar_one_or_none()

    async def list_all(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        status: Optional[str] = None,
        community_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Poll]:
        filters = [Poll.organization_id == organization_id]
        if status:
            filters.append(Poll.status == status)
        if community_id:
            filters.append(Poll.community_id == community_id)
        return list(
            (
                await db.execute(
                    select(Poll)
                    .where(*filters)
                    .order_by(Poll.created_at.desc())
                    .limit(min(limit, 500))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def update(
        self, db: AsyncSession, *, organization_id: str, poll_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Optional[Poll]:
        poll = await self.get(db, organization_id=organization_id, poll_id=poll_id)
        if poll is None:
            return None
        for key in ("title", "question", "description", "status", "ends_at"):
            if key in payload and payload[key] is not None:
                setattr(poll, key, payload[key])
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="poll.updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"poll_id": poll_id},
            resource_type="poll",
            resource_id=poll_id,
        )
        return poll

    async def delete(
        self, db: AsyncSession, *, organization_id: str, poll_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        poll = await self.get(db, organization_id=organization_id, poll_id=poll_id)
        if poll is None:
            return False
        await db.delete(poll)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="poll.deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"poll_id": poll_id},
            resource_type="poll",
            resource_id=poll_id,
        )
        return True

    async def vote(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        poll_id: str,
        option_ids: list[str],
        actor: Employee,
    ) -> dict[str, Any]:
        poll = await self.get(db, organization_id=organization_id, poll_id=poll_id)
        if poll is None:
            raise ValueError("Poll not found")
        if poll.status != "open":
            raise ValueError("Poll is not open")
        if not poll.multiple_choice and len(option_ids) != 1:
            raise ValueError("Select exactly one option")
        existing = (
            await db.execute(
                select(PollVote).where(
                    PollVote.organization_id == organization_id,
                    PollVote.poll_id == poll_id,
                    PollVote.voter_id == actor.id,
                )
            )
        ).scalars().all()
        for vote in existing:
            await db.delete(vote)
            option = (
                await db.execute(
                    select(PollOption).where(
                        PollOption.organization_id == organization_id,
                        PollOption.id == vote.option_id,
                    )
                )
            ).scalar_one_or_none()
            if option is not None:
                option.vote_count = max(0, (option.vote_count or 1) - 1)
        for option_id in option_ids:
            option = (
                await db.execute(
                    select(PollOption).where(
                        PollOption.organization_id == organization_id,
                        PollOption.id == option_id,
                        PollOption.poll_id == poll_id,
                    )
                )
            ).scalar_one_or_none()
            if option is None:
                raise ValueError("Unknown option")
            option.vote_count = (option.vote_count or 0) + 1
            db.add(
                PollVote(
                    organization_id=organization_id,
                    poll_id=poll_id,
                    option_id=option_id,
                    voter_id=actor.id,
                )
            )
        poll.vote_count = (
            await db.execute(
                select(func.count(func.distinct(PollVote.voter_id))).where(
                    PollVote.organization_id == organization_id,
                    PollVote.poll_id == poll_id,
                )
            )
        ).scalar_one()
        poll.participant_count = poll.vote_count
        return {"voted": True, "vote_count": poll.vote_count}

    async def my_vote_ids(
        self, db: AsyncSession, *, organization_id: str, poll_id: str, employee_id: str
    ) -> list[str]:
        rows = (
            await db.execute(
                select(PollVote.option_id).where(
                    PollVote.organization_id == organization_id,
                    PollVote.poll_id == poll_id,
                    PollVote.voter_id == employee_id,
                )
            )
        ).scalars().all()
        return list(rows)

    async def options(
        self, db: AsyncSession, *, organization_id: str, poll_id: str
    ) -> list[PollOption]:
        return list(
            (
                await db.execute(
                    select(PollOption)
                    .where(PollOption.organization_id == organization_id, PollOption.poll_id == poll_id)
                    .order_by(PollOption.sort_order.asc(), PollOption.created_at.asc())
                )
            ).scalars().all()
        )

    async def results(self, db: AsyncSession, *, organization_id: str, poll_id: str) -> dict[str, Any]:
        poll = await self.get(db, organization_id=organization_id, poll_id=poll_id)
        if poll is None:
            raise ValueError("Poll not found")
        options = await self.options(db, organization_id=organization_id, poll_id=poll_id)
        return {
            "poll_id": poll_id,
            "vote_count": poll.vote_count or 0,
            "options": [
                {
                    "option_id": o.id,
                    "text": o.text,
                    "vote_count": o.vote_count or 0,
                    "percentage": round((o.vote_count or 0) / max(1, poll.vote_count or 0) * 100, 1),
                }
                for o in options
            ],
        }


poll_service = PollService()
