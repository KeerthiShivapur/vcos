"""Response presenters — enrich ORM entities into API payloads (names, tags, counts)."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge import knowledge_base as kb
from app.models.employee import Employee
from app.models.project import Project
from app.models.user import User


def _entity_url(kind: str, entity_id: str) -> str:
    return kb.entity_url(kind, entity_id)


async def _names(db: AsyncSession, employee_ids: list[str]) -> dict[str, str]:
    return await kb.employee_names(db, employee_ids=[e for e in employee_ids if e])


async def _user_names(db: AsyncSession, user_ids: list[str]) -> dict[str, str]:
    ids = [u for u in user_ids if u]
    if not ids:
        return {}
    rows = (await db.execute(select(User.id, User.full_name).where(User.id.in_(set(ids))))).all()
    return {row[0]: row[1] for row in rows}


async def _project_names(db: AsyncSession, project_ids: list[str]) -> dict[str, str]:
    ids = [p for p in project_ids if p]
    if not ids:
        return {}
    rows = (await db.execute(select(Project.id, Project.name).where(Project.id.in_(set(ids))))).all()
    return {row[0]: row[1] for row in rows}


async def present(
    db: AsyncSession, *, organization_id: str, entity: Any, kind: str,
) -> dict[str, Any]:
    """Build the full Out payload for a knowledge entity."""
    tags = await kb.entity_tags(db, organization_id=organization_id, entity_type=kind, entity_id=entity.id)
    payload: dict[str, Any] = {
        "id": entity.id,
        "kind": kind,
        "url": _entity_url(kind, entity.id),
        "title": entity.title,
        "slug": entity.slug,
        "description": getattr(entity, "description", None),
        "content": getattr(entity, "content", None),
        "summary": getattr(entity, "summary", None),
        "ai_summary": getattr(entity, "ai_summary", None),
        "keywords": getattr(entity, "keywords", None),
        "category": getattr(entity, "category", None),
        "tags": tags,
        "status": getattr(entity, "status", ""),
        "version": getattr(entity, "version", 1),
        "view_count": getattr(entity, "view_count", 0),
        "published_at": getattr(entity, "published_at", None),
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }
    for field in ("author_id", "owner_id", "editor_id", "approver_id", "decision_maker_id", "employee_id"):
        if hasattr(entity, field):
            payload[field] = getattr(entity, field)
    for field in ("project_id", "department_id", "team_id", "meeting_id", "parent_id"):
        if hasattr(entity, field):
            payload[field] = getattr(entity, field)

    name_ids: list[str] = []
    for field in ("author_id", "owner_id", "editor_id", "approver_id", "decision_maker_id"):
        if hasattr(entity, field):
            value = getattr(entity, field)
            if value:
                name_ids.append(value)
    names = await _names(db, name_ids)
    for field, out_field in (
        ("author_id", "author_name"),
        ("owner_id", "owner_name"),
        ("editor_id", "editor_name"),
        ("approver_id", "approver_name"),
        ("decision_maker_id", "decision_maker_name"),
    ):
        if hasattr(entity, field):
            value = getattr(entity, field)
            payload[out_field] = names.get(value) if value else None

    project_ids = [getattr(entity, "project_id")] if hasattr(entity, "project_id") and getattr(entity, "project_id") else []
    project_names = await _project_names(db, project_ids)
    if hasattr(entity, "project_id"):
        payload["project_name"] = project_names.get(entity.project_id) if entity.project_id else None

    if kind == "document":
        payload["visibility"] = getattr(entity, "visibility", "organization")
    if kind == "wiki":
        payload["space"] = getattr(entity, "space", "organization")
        payload["child_count"] = await _wiki_child_count(db, organization_id=organization_id, parent_id=entity.id)
    if kind == "policy":
        payload["effective_date"] = getattr(entity, "effective_date", None)
        payload["review_date"] = getattr(entity, "review_date", None)
        payload["review_overdue"] = _overdue(getattr(entity, "review_date", None))
        payload["approval_note"] = getattr(entity, "approval_note", None)
    if kind == "sop":
        from app.knowledge.sop_service import sop_service

        steps = await sop_service.steps(db, organization_id=organization_id, sop_id=entity.id)
        payload["steps"] = [
            {
                "id": step.id,
                "sop_id": step.sop_id,
                "title": step.title,
                "instruction": step.instruction,
                "is_checklist": step.is_checklist,
                "sort_order": step.sort_order,
            }
            for step in steps
        ]
    if kind == "template":
        payload["kind_name"] = getattr(entity, "kind", "other")
        payload["usage_count"] = getattr(entity, "usage_count", 0)
    if kind == "decision":
        from app.knowledge.decision_service import decision_service

        payload["context"] = getattr(entity, "context", None)
        payload["impact"] = getattr(entity, "impact", None)
        payload["business_impact"] = getattr(entity, "business_impact", None)
        payload["follow_up_actions"] = getattr(entity, "follow_up_actions", None)
        payload["future_review_date"] = getattr(entity, "future_review_date", None)
        payload["lessons_learned"] = getattr(entity, "lessons_learned", None)
        payload["decision_date"] = getattr(entity, "decision_date", None)
        payload["decided_at"] = getattr(entity, "decided_at", None)
        options = await decision_service.options(db, organization_id=organization_id, decision_id=entity.id)
        payload["options"] = [
            {
                "id": opt.id,
                "decision_id": opt.decision_id,
                "title": opt.title,
                "description": opt.description,
                "pros": opt.pros,
                "cons": opt.cons,
                "chosen": opt.chosen,
                "chosen_reason": opt.chosen_reason,
                "sort_order": opt.sort_order,
            }
            for opt in options
        ]
        participants = await decision_service.participants(db, organization_id=organization_id, decision_id=entity.id)
        p_names = await _names(db, [p.employee_id for p in participants])
        payload["participants"] = [
            {
                "id": p.id,
                "decision_id": p.decision_id,
                "employee_id": p.employee_id,
                "employee_name": p_names.get(p.employee_id),
                "role": p.role,
            }
            for p in participants
        ]
    return payload


def _overdue(review_date: Optional[Any]) -> bool:
    from datetime import date

    return bool(review_date and review_date < date.today())


async def _wiki_child_count(db: AsyncSession, *, organization_id: str, parent_id: str) -> int:
    from app.models.knowledge import WikiPage

    return int(
        (
            await db.execute(
                select(WikiPage.id).where(WikiPage.organization_id == organization_id, WikiPage.parent_id == parent_id)
            )
        ).scalars().all().__len__()
    )


async def present_comments(
    db: AsyncSession, *, organization_id: str, comments: list[Any],
) -> list[dict[str, Any]]:
    user_ids = [c.author_id for c in comments if c.author_id]
    names = await _user_names(db, user_ids)
    return [
        {
            "id": c.id,
            "entity_type": c.entity_type,
            "entity_id": c.entity_id,
            "author_id": c.author_id,
            "author_name": names.get(c.author_id),
            "content": c.content,
            "parent_id": c.parent_id,
            "resolved": c.resolved,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in comments
    ]


async def present_watchers(
    db: AsyncSession, *, organization_id: str, watchers: list[Any],
) -> list[dict[str, Any]]:
    user_ids = [w.user_id for w in watchers]
    names = await _user_names(db, user_ids)
    return [
        {
            "id": w.id,
            "entity_type": w.entity_type,
            "entity_id": w.entity_id,
            "user_id": w.user_id,
            "user_name": names.get(w.user_id),
            "created_at": w.created_at,
        }
        for w in watchers
    ]


async def present_presence(
    db: AsyncSession, *, organization_id: str, presence: list[Any],
) -> list[dict[str, Any]]:
    user_ids = [p.user_id for p in presence]
    names = await _user_names(db, user_ids)
    return [
        {
            "entity_type": p.entity_type,
            "entity_id": p.entity_id,
            "user_id": p.user_id,
            "user_name": names.get(p.user_id),
            "last_active_at": p.last_active_at,
        }
        for p in presence
    ]


async def present_relations(
    db: AsyncSession, *, organization_id: str, relations: list[Any],
) -> list[dict[str, Any]]:
    from app.knowledge.relation_service import relation_service

    out = []
    for rel in relations:
        info = await relation_service.resolve_target(
            db, organization_id=organization_id, target_type=rel.target_type, target_id=rel.target_id
        )
        out.append(
            {
                "id": rel.id,
                "source_type": rel.source_type,
                "source_id": rel.source_id,
                "target_type": rel.target_type,
                "target_id": rel.target_id,
                "relation_type": rel.relation_type,
                "target_title": info.get("title"),
                "target_url": info.get("url"),
                "created_at": rel.created_at,
            }
        )
    return out
