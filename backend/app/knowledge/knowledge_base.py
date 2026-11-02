"""Knowledge core — shared plumbing for every knowledge entity type.

Entity kinds: document | wiki | policy | sop | template | decision.

This module gives the domain services one place for:
  - the kind → model registry and tenanted entity loading
  - slug generation
  - default categories/tags seeding
  - version history creation
  - the semantic search index (keywords + embedding rows)
  - events + audit logging
  - watcher notifications
  - view counting / presence
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.knowledge import (
    Decision,
    Document,
    DocumentFavorite,
    DocumentPresence,
    DocumentVersion,
    DocumentWatcher,
    KnowledgeCategory,
    KnowledgeIndex,
    KnowledgeItemTag,
    KnowledgeTag,
    Policy,
    SOP,
    Template,
    WikiPage,
)
from app.schemas.knowledge import entity_url

KINDS = ("document", "wiki", "policy", "sop", "template", "decision")

KIND_MODELS = {
    "document": Document,
    "wiki": WikiPage,
    "policy": Policy,
    "sop": SOP,
    "template": Template,
    "decision": Decision,
}

# Linkable external entity types (org graph integration + relations)
EXTERNAL_TYPES = (
    "project", "task", "goal", "meeting", "employee", "department", "team", "location",
    "client", "policy", "sop", "document", "wiki", "template", "decision",
)

DEFAULT_CATEGORIES = [
    ("General", "general", "Everything else."),
    ("Engineering", "engineering", "Architecture, code, infrastructure."),
    ("HR", "hr", "People, hiring, onboarding, benefits."),
    ("Finance", "finance", "Budget, expense, payroll, procurement."),
    ("Marketing", "marketing", "Brand, campaigns, content."),
    ("Sales", "sales", "Deals, proposals, customer success."),
    ("Operations", "operations", "Processes and daily operations."),
    ("Legal", "legal", "Contracts, compliance, governance."),
    ("Security", "security", "Security policies and practices."),
    ("Research", "research", "Research and experiments."),
    ("Product", "product", "Product docs and decisions."),
    ("Training", "training", "Learning and onboarding material."),
    ("Architecture", "architecture", "System and solution architecture."),
    ("Customer", "customer", "Customer knowledge and requirements."),
]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


def entity_kind_ok(kind: str) -> bool:
    return kind in KIND_MODELS


async def resolve_entity(db: AsyncSession, *, organization_id: str, kind: str, entity_id: str) -> Any:
    """Load a knowledge entity scoped to the tenant, or None."""
    model = KIND_MODELS.get(kind)
    if model is None:
        return None
    entity = await db.get(model, entity_id)
    if entity is None or entity.organization_id != organization_id:
        return None
    return entity


async def load_many(
    db: AsyncSession, *, organization_id: str, kinds: list[str], limit: int = 100
) -> list[Any]:
    """Load entities across kinds (published only for drafts-aware callers)."""
    out: list[Any] = []
    for kind in kinds:
        model = KIND_MODELS.get(kind)
        if model is None:
            continue
        rows = (
            await db.execute(
                select(model).where(model.organization_id == organization_id).order_by(model.updated_at.desc()).limit(limit)
            )
        ).scalars().all()
        out.extend(rows)
    return out


def kind_label(kind: str) -> str:
    return {
        "document": "Document",
        "wiki": "Wiki",
        "policy": "Policy",
        "sop": "SOP",
        "template": "Template",
        "decision": "Decision",
    }.get(kind, kind.title())


async def ensure_default_categories(db: AsyncSession, organization_id: str) -> None:
    """Seed the standard category set once per organization."""
    existing = set(
        (
            await db.execute(
                select(KnowledgeCategory.slug).where(KnowledgeCategory.organization_id == organization_id)
            )
        ).scalars().all()
    )
    for name, slug, description in DEFAULT_CATEGORIES:
        if slug not in existing:
            db.add(
                KnowledgeCategory(
                    organization_id=organization_id, name=name, slug=slug, description=description,
                )
            )
    await db.flush()


async def get_or_create_tag(db: AsyncSession, organization_id: str, name: str) -> KnowledgeTag:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Tag name cannot be empty")
    tag = (
        await db.execute(
            select(KnowledgeTag).where(
                KnowledgeTag.organization_id == organization_id,
                func.lower(KnowledgeTag.name) == cleaned.lower(),
            )
        )
    ).scalar_one_or_none()
    if tag is None:
        tag = KnowledgeTag(organization_id=organization_id, name=cleaned, slug=slugify(cleaned))
        db.add(tag)
        await db.flush()
    return tag


async def set_entity_tags(
    db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str, names: Optional[list[str]]
) -> list[str]:
    """Replace the tag set of an entity; returns the tag names."""
    await db.execute(
        delete(KnowledgeItemTag).where(
            KnowledgeItemTag.organization_id == organization_id,
            KnowledgeItemTag.entity_type == entity_type,
            KnowledgeItemTag.entity_id == entity_id,
        )
    )
    resolved: list[str] = []
    for name in names or []:
        tag = await get_or_create_tag(db, organization_id, name)
        db.add(
            KnowledgeItemTag(
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
                tag_id=tag.id,
            )
        )
        resolved.append(tag.name)
    await db.flush()
    return resolved


async def entity_tags(db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str) -> list[str]:
    rows = (
        await db.execute(
            select(KnowledgeTag.name)
            .join(KnowledgeItemTag, KnowledgeItemTag.tag_id == KnowledgeTag.id)
            .where(
                KnowledgeItemTag.organization_id == organization_id,
                KnowledgeItemTag.entity_type == entity_type,
                KnowledgeItemTag.entity_id == entity_id,
            )
            .order_by(KnowledgeTag.name.asc())
        )
    ).all()
    return [row[0] for row in rows]


async def create_version(
    db: AsyncSession,
    *,
    organization_id: str,
    entity_type: str,
    entity_id: str,
    version: int,
    title: str,
    content: Optional[str],
    summary: Optional[str],
    editor_id: Optional[str],
    change_note: Optional[str],
) -> None:
    db.add(
        DocumentVersion(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            version=version,
            title=title,
            content=content,
            summary=summary,
            editor_id=editor_id,
            change_note=change_note,
        )
    )


def entity_text(entity: Any) -> str:
    """The full searchable text of an entity."""
    parts = [
        getattr(entity, "title", ""),
        getattr(entity, "description", ""),
        getattr(entity, "content", ""),
        getattr(entity, "context", ""),
        getattr(entity, "impact", ""),
        getattr(entity, "lessons_learned", ""),
        getattr(entity, "category", ""),
    ]
    actions = getattr(entity, "follow_up_actions", None)
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, str):
                parts.append(action)
            elif isinstance(action, dict):
                parts.append(action.get("text") or "")
    return " ".join(p for p in parts if p)


async def write_index(
    db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str, entity: Any
) -> KnowledgeIndex:
    """Upsert the semantic search index row for an entity."""
    from app.knowledge.embedding import embed_text, keywords

    text = entity_text(entity)
    row = (
        await db.execute(
            select(KnowledgeIndex).where(
                KnowledgeIndex.organization_id == organization_id,
                KnowledgeIndex.entity_type == entity_type,
                KnowledgeIndex.entity_id == entity_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = KnowledgeIndex(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        db.add(row)
    row.title = getattr(entity, "title", "")
    row.content = text
    row.keywords_json = json.dumps(keywords(text))
    row.embedding_json = json.dumps(embed_text(text))
    row.view_count = getattr(entity, "view_count", 0) or 0
    row.updated_at = utcnow()
    await db.flush()
    return row


async def delete_index(
    db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str
) -> None:
    await db.execute(
        delete(KnowledgeIndex).where(
            KnowledgeIndex.organization_id == organization_id,
            KnowledgeIndex.entity_type == entity_type,
            KnowledgeIndex.entity_id == entity_id,
        )
    )


async def emit_and_audit(
    db: AsyncSession,
    *,
    organization_id: str,
    name: str,
    actor: Optional[Employee],
    actor_user_id: Optional[str],
    ip_address: Optional[str],
    payload: Optional[dict[str, Any]] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
) -> None:
    from app.services.audit_service import audit_service
    from app.services.event_service import event_service

    actor_id = (actor.id if actor else None) or actor_user_id
    await event_service.emit(
        db,
        name=name,
        actor_id=actor_id,
        organization_id=organization_id,
        payload=payload,
    )
    await audit_service.log(
        db,
        organization_id=organization_id,
        action=name,
        actor_id=actor_id,
        actor_email=actor.email if actor else None,
        resource_type=resource_type or "knowledge",
        resource_id=resource_id,
        ip_address=ip_address,
        details=payload,
    )


async def notify_watchers(
    db: AsyncSession,
    *,
    organization_id: str,
    entity_type: str,
    entity_id: str,
    title: str,
    body: str,
    actor_user_id: Optional[str],
    entity_url: Optional[str] = None,
    kind: str = "knowledge.activity",
) -> None:
    """Notify everyone watching an entity (except the actor) of an update."""
    from app.services.notification_service import notification_service

    rows = (
        await db.execute(
            select(DocumentWatcher).where(
                DocumentWatcher.organization_id == organization_id,
                DocumentWatcher.entity_type == entity_type,
                DocumentWatcher.entity_id == entity_id,
            )
        )
    ).scalars().all()
    for watcher in rows:
        if watcher.user_id == actor_user_id:
            continue
        await notification_service.create(
            db,
            organization_id=organization_id,
            recipient_id=watcher.user_id,
            actor_id=actor_user_id,
            type=kind,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            link=entity_url or entity_url(entity_type, entity_id),
        )


async def register_view(
    db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str, user_id: str
) -> None:
    """Increment view_count, update the index popularity, and record presence."""
    entity = await resolve_entity(db, organization_id=organization_id, kind=entity_type, entity_id=entity_id)
    if entity is None:
        return
    entity.view_count = (entity.view_count or 0) + 1
    presence = (
        await db.execute(
            select(DocumentPresence).where(
                DocumentPresence.organization_id == organization_id,
                DocumentPresence.entity_type == entity_type,
                DocumentPresence.entity_id == entity_id,
                DocumentPresence.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if presence is None:
        db.add(
            DocumentPresence(
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
                user_id=user_id,
            )
        )
    else:
        presence.last_active_at = utcnow()
    index_row = (
        await db.execute(
            select(KnowledgeIndex).where(
                KnowledgeIndex.organization_id == organization_id,
                KnowledgeIndex.entity_type == entity_type,
                KnowledgeIndex.entity_id == entity_id,
            )
        )
    ).scalar_one_or_none()
    if index_row is not None:
        index_row.view_count = entity.view_count
    await db.flush()


async def recent_for_user(
    db: AsyncSession, *, organization_id: str, user_id: str, limit: int = 10
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(DocumentPresence)
            .where(
                DocumentPresence.organization_id == organization_id,
                DocumentPresence.user_id == user_id,
            )
            .order_by(DocumentPresence.last_active_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        entity = await resolve_entity(db, organization_id=organization_id, kind=row.entity_type, entity_id=row.entity_id)
        if entity is None:
            continue
        out.append(
            {
                "id": entity.id,
                "kind": row.entity_type,
                "title": entity.title,
                "url": entity_url(row.entity_type, entity.id),
                "status": getattr(entity, "status", ""),
                "viewed_at": row.last_active_at,
            }
        )
    return out


async def favorites_for_user(
    db: AsyncSession, *, organization_id: str, user_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(DocumentFavorite)
            .where(
                DocumentFavorite.organization_id == organization_id,
                DocumentFavorite.user_id == user_id,
            )
            .order_by(DocumentFavorite.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        entity = await resolve_entity(db, organization_id=organization_id, kind=row.entity_type, entity_id=row.entity_id)
        if entity is None:
            continue
        out.append(
            {
                "id": entity.id,
                "kind": row.entity_type,
                "title": entity.title,
                "url": entity_url(row.entity_type, entity.id),
                "status": getattr(entity, "status", ""),
                "favorited_at": row.created_at,
            }
        )
    return out


def published_statuses(kind: str) -> tuple[str, ...]:
    if kind == "decision":
        return ("made", "implemented", "reviewed")
    if kind == "policy":
        return ("approved", "published")
    return ("published",)


def employee_name_map(db: AsyncSession) -> dict:
    """Placeholder kept for symmetry; use _names helper below."""
    return {}


async def employee_names(db: AsyncSession, employee_ids: list[str]) -> dict[str, str]:
    if not employee_ids:
        return {}
    rows = (
        await db.execute(
            select(
                Employee.id,
                func.coalesce(
                    Employee.display_name,
                    func.trim(
                        func.concat(
                            func.coalesce(Employee.first_name, ""),
                            " ",
                            func.coalesce(Employee.last_name, ""),
                        )
                    ),
                ),
            ).where(Employee.id.in_(set(employee_ids)))
        )
    ).all()
    return {row[0]: row[1] for row in rows}


def parse_keywords(entity: Any) -> list[str]:
    try:
        return json.loads(entity.keywords) if entity.keywords else []
    except (TypeError, ValueError):
        return []


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Module-level instance for convenience
kb = None
