"""Knowledge Hub API — search, graph, analytics, recommendations, collab (Phase 4.9-4.11)."""

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.knowledge import knowledge_base as kb
from app.knowledge.analytics_service import analytics_service
from app.knowledge.collab_service import collab_service
from app.knowledge.graph_service import knowledge_graph_service
from app.knowledge.presenters import (
    present_comments,
    present_presence,
    present_relations,
    present_watchers,
)
from app.knowledge.recommendation_service import recommendation_service
from app.knowledge.relation_service import relation_service
from app.knowledge.search_service import knowledge_search_service
from app.models.knowledge import (
    DocumentFavorite,
    DocumentVersion,
    KnowledgeCategory,
    KnowledgeTag,
)
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.knowledge import (
    CommentCreate,
    CommentUpdate,
    KnowledgeCategoryCreate,
    KnowledgeGraphOut,
    KnowledgeQualityOut,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
    RelationCreate,
    WorkflowAction,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


def _require_kind(kind: str) -> str:
    if kind not in kb.KINDS:
        raise HTTPException(404, "Unknown knowledge kind")
    return kind


async def _get_entity(db: AsyncSession, org: Organization, kind: str, entity_id: str):
    entity = await kb.resolve_entity(db, organization_id=org.id, kind=kind, entity_id=entity_id)
    if entity is None:
        raise HTTPException(404, f"{kind.capitalize()} not found")
    return entity


# ---------------------------------------------------------------------- search

@router.get("/search", response_model=KnowledgeSearchResponse)
async def knowledge_search(
    q: str,
    mode: str = "hybrid",
    kind: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    author_id: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    started = time.monotonic()
    data = await knowledge_search_service.search(
        db, organization_id=org.id, query=q, mode=mode,
        kind=kind if kind else None, status=status or None,
        project_id=project_id or None, author_id=author_id or None,
        tags=[t.strip() for t in tags.split(",")] if tags else None,
        limit=min(limit, 100), offset=offset,
    )
    results = [
        KnowledgeSearchResult(
            id=r["id"],
            kind=r["type"],
            title=r["title"],
            url=r["url"],
            subtitle=r["summary"],
            snippet=(r["summary"] or "")[:160],
            score=r["score"],
            matched_keywords=r.get("matched_keywords", []),
            metadata={"status": r.get("status"), "author_id": r.get("author_id"), "project_id": r.get("project_id")},
        )
        for r in data["results"]
    ]
    return KnowledgeSearchResponse(
        query=q,
        mode=data["mode"],
        results=results,
        total=data["total"],
        took_ms=int((time.monotonic() - started) * 1000),
    )


# --------------------------------------------------------------------- graph

@router.get("/graph", response_model=KnowledgeGraphOut)
async def knowledge_graph(
    kind: Optional[str] = None,
    focus: Optional[str] = None,
    depth: int = 3,
    limit: int = 250,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    data = await knowledge_graph_service.build(
        db, organization_id=org.id, kind=kind, focus=focus, depth=min(depth, 5), limit=min(limit, 500),
    )
    return KnowledgeGraphOut(
        nodes=[
            {
                "id": n["id"],
                "label": n["label"],
                "kind": n.get("type", "knowledge"),
                "status": n.get("status"),
                "meta": {"summary": n.get("summary"), "url": n.get("url"), "project_id": n.get("project_id")},
            }
            for n in data["nodes"]
        ],
        edges=[
            {"source": e["source"], "target": e["target"], "relation": e.get("type", e.get("relation", "related_to"))}
            for e in data["edges"]
        ],
    )


# ------------------------------------------------------------------ analytics

@router.get("/analytics", response_model=dict)
async def knowledge_analytics(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    overview = await analytics_service.overview(db, organization_id=org.id)
    growth = await analytics_service.growth(db, organization_id=org.id, days=30)
    top_viewed = await analytics_service.top_viewed(db, organization_id=org.id, limit=10)
    contributors = await analytics_service.contributors(db, organization_id=org.id, limit=10)
    coverage = await analytics_service.coverage(db, organization_id=org.id)
    quality = await analytics_service.quality(db, organization_id=org.id, limit=10)
    duplicates = await analytics_service.duplicates(db, organization_id=org.id)
    outdated = await recommendation_service.stale(db, organization_id=org.id, limit=10)
    from app.knowledge.policy_service import policy_service

    overdue = await policy_service.overdue_reviews(db, organization_id=org.id)
    return {
        "totals": overview["totals"],
        "total_items": overview["total_items"],
        "total_relations": overview["total_relations"],
        "avg_quality_score": overview["avg_quality_score"],
        "growth_30d": growth["by_kind"],
        "growth_series": [
            {"date": day, "count": count}
            for day, count in zip(growth["days"], growth["counts"])
        ],
        "top_viewed": [
            {"id": r["id"], "kind": r["type"], "title": r["title"], "url": r["url"], "views": r["views"]}
            for r in top_viewed
        ],
        "top_contributors": contributors,
        "category_coverage": [],
        "department_health": [],
        "outdated": outdated,
        "review_backlog": [
            {"id": p.id, "kind": "policy", "title": p.title, "url": kb.entity_url("policy", p.id), "status": "review_overdue"}
            for p in overdue
        ],
        "quality_distribution": {},
        "expert_distribution": [],
        "search_trends": [],
        "duplicates": duplicates.get("items", []),
        "coverage": coverage,
        "quality_lowest": quality.get("lowest", []),
    }


# ---------------------------------------------------------- recommendations

@router.get("/recommendations", response_model=list[dict])
async def knowledge_recommendations(
    limit: int = 10,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    recs = await recommendation_service.for_user(db, organization_id=org.id, employee=actor, limit=min(limit, 50))
    return [
        {
            "id": r["id"],
            "kind": r["type"],
            "title": r["title"],
            "url": r["url"],
            "reason": r["reason"],
            "score": r["score"],
            "status": r.get("status"),
        }
        for r in recs
    ]


@router.get("/experts", response_model=list[dict])
async def knowledge_experts(
    topic: Optional[str] = None,
    limit: int = 10,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    return await recommendation_service.experts(db, organization_id=org.id, topic=topic, limit=min(limit, 50))


@router.get("/stale", response_model=list[dict])
async def stale_knowledge(
    days: int = 180,
    limit: int = 20,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    return await recommendation_service.stale(db, organization_id=org.id, days=days, limit=min(limit, 100))


# -------------------------------------------------------- recent / favorites

@router.get("/recent", response_model=list[dict])
async def recent_knowledge(
    limit: int = 10,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    return await kb.recent_for_user(db, organization_id=org.id, user_id=user.id, limit=min(limit, 50))


@router.get("/favorites", response_model=list[dict])
async def my_favorites(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    return await kb.favorites_for_user(db, organization_id=org.id, user_id=user.id)


# --------------------------------------------------------- categories / tags

@router.get("/categories", response_model=list[dict])
async def list_categories(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(KnowledgeCategory)
            .where(KnowledgeCategory.organization_id == org.id)
            .order_by(KnowledgeCategory.name.asc())
        )
    ).scalars().all()
    return [{"id": c.id, "name": c.name, "slug": c.slug, "description": c.description, "color": c.color} for c in rows]


@router.post("/categories", response_model=dict, status_code=201)
async def create_category(
    payload: KnowledgeCategoryCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    slug = kb.slugify(payload.name)
    existing = (
        await db.execute(
            select(KnowledgeCategory).where(
                KnowledgeCategory.organization_id == org.id, KnowledgeCategory.slug == slug
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Category already exists")
    category = KnowledgeCategory(
        organization_id=org.id, name=payload.name, slug=slug,
        description=payload.description, color=payload.color,
    )
    db.add(category)
    await db.commit()
    return {"id": category.id, "name": category.name, "slug": category.slug, "description": category.description, "color": category.color}


@router.get("/tags", response_model=list[dict])
async def list_tags(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(KnowledgeTag)
            .where(KnowledgeTag.organization_id == org.id)
            .order_by(KnowledgeTag.name.asc())
            .limit(200)
        )
    ).scalars().all()
    return [{"id": t.id, "name": t.name, "slug": t.slug} for t in rows]


# ------------------------------------------------------------------ versions

@router.get("/{kind}/{entity_id}/versions", response_model=list[dict])
async def list_versions(
    kind: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    rows = (
        await db.execute(
            select(DocumentVersion)
            .where(
                DocumentVersion.organization_id == org.id,
                DocumentVersion.entity_type == kind,
                DocumentVersion.entity_id == entity_id,
            )
            .order_by(DocumentVersion.version.desc())
        )
    ).scalars().all()
    names = await kb.employee_names(db, employee_ids=[r.editor_id for r in rows if r.editor_id])
    return [
        {
            "id": r.id,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "version": r.version,
            "title": r.title,
            "content": r.content,
            "summary": r.summary,
            "editor_id": r.editor_id,
            "editor_name": names.get(r.editor_id) if r.editor_id else None,
            "change_note": r.change_note,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/{kind}/{entity_id}/versions/{version}", response_model=dict)
async def get_version(
    kind: str,
    entity_id: str,
    version: int,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    row = (
        await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.organization_id == org.id,
                DocumentVersion.entity_type == kind,
                DocumentVersion.entity_id == entity_id,
                DocumentVersion.version == version,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Version not found")
    names = await kb.employee_names(db, employee_ids=[row.editor_id] if row.editor_id else [])
    return {
        "id": row.id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "version": row.version,
        "title": row.title,
        "content": row.content,
        "summary": row.summary,
        "editor_id": row.editor_id,
        "editor_name": names.get(row.editor_id) if row.editor_id else None,
        "change_note": row.change_note,
        "created_at": row.created_at,
    }


@router.post("/{kind}/{entity_id}/versions/{version}/restore", response_model=dict)
async def restore_version(
    kind: str,
    entity_id: str,
    version: int,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    actor = await _actor(db, org, user)
    service = kb.KIND_MODELS[kind]
    from app.knowledge.crud_base import KnowledgeCrud

    crud = KnowledgeCrud()
    crud.model = service
    crud.kind = kind
    entity = await crud.restore(
        db, organization_id=org.id, entity_id=entity_id, version=version,
        actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Entity or version not found")
    await db.commit()
    from app.knowledge.presenters import present

    return await present(db, organization_id=org.id, entity=entity, kind=kind)


# ------------------------------------------------------------------ comments

@router.get("/{kind}/{entity_id}/comments", response_model=list[dict])
async def list_comments(
    kind: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    rows = await collab_service.list_comments(db, organization_id=org.id, entity_type=kind, entity_id=entity_id)
    return await present_comments(db, organization_id=org.id, comments=rows)


@router.post("/{kind}/{entity_id}/comments", response_model=dict, status_code=201)
async def add_comment(
    kind: str,
    entity_id: str,
    payload: CommentCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    comment = await collab_service.add_comment(
        db, organization_id=org.id, entity_type=kind, entity_id=entity_id,
        content=payload.content, actor=user, ip_address=get_client_ip(request), parent_id=payload.parent_id,
    )
    await db.commit()
    return (await present_comments(db, organization_id=org.id, comments=[comment]))[0]


@router.patch("/{kind}/{entity_id}/comments/{comment_id}", response_model=dict)
async def update_comment(
    kind: str,
    entity_id: str,
    comment_id: str,
    payload: CommentUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    comment = await collab_service.update_comment(
        db, organization_id=org.id, comment_id=comment_id, content=payload.content, user=user,
    )
    if comment is None:
        raise HTTPException(404, "Comment not found")
    await db.commit()
    return (await present_comments(db, organization_id=org.id, comments=[comment]))[0]


@router.delete("/{kind}/{entity_id}/comments/{comment_id}", response_model=Message)
async def delete_comment(
    kind: str,
    entity_id: str,
    comment_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    if not await collab_service.delete_comment(db, organization_id=org.id, comment_id=comment_id, user=user):
        raise HTTPException(404, "Comment not found")
    await db.commit()
    return Message(message="Comment deleted")


# ------------------------------------------------- watchers / favorites / presence

@router.post("/{kind}/{entity_id}/watch", response_model=dict)
async def toggle_watch(
    kind: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    result = await collab_service.toggle_watch(db, organization_id=org.id, entity_type=kind, entity_id=entity_id, user=user)
    await db.commit()
    return result


@router.get("/{kind}/{entity_id}/watchers", response_model=list[dict])
async def list_watchers(
    kind: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    rows = await collab_service.watchers(db, organization_id=org.id, entity_type=kind, entity_id=entity_id)
    return await present_watchers(db, organization_id=org.id, watchers=rows)


@router.post("/{kind}/{entity_id}/favorite", response_model=dict)
async def toggle_favorite(
    kind: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    result = await collab_service.toggle_favorite(db, organization_id=org.id, entity_type=kind, entity_id=entity_id, user=user)
    await db.commit()
    return result


@router.post("/{kind}/{entity_id}/presence", response_model=dict)
async def update_presence(
    kind: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    await collab_service.touch_presence(db, organization_id=org.id, entity_type=kind, entity_id=entity_id, user=user)
    await db.commit()
    return {"presence": "ok"}


@router.get("/{kind}/{entity_id}/presence", response_model=list[dict])
async def list_presence(
    kind: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    rows = await collab_service.present(db, organization_id=org.id, entity_type=kind, entity_id=entity_id)
    return await present_presence(db, organization_id=org.id, presence=rows)


# ------------------------------------------------------------------ relations

@router.get("/{kind}/{entity_id}/relations", response_model=list[dict])
async def list_relations(
    kind: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    rows = await relation_service.list_for(db, organization_id=org.id, entity_type=kind, entity_id=entity_id)
    return await present_relations(db, organization_id=org.id, relations=rows)


@router.post("/{kind}/{entity_id}/relations", response_model=dict, status_code=201)
async def add_relation(
    kind: str,
    entity_id: str,
    payload: RelationCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    try:
        relation = await relation_service.add(
            db, organization_id=org.id, source_type=kind, source_id=entity_id,
            target_type=payload.target_type, target_id=payload.target_id,
            relation_type=payload.relation_type or "related_to", created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return (await present_relations(db, organization_id=org.id, relations=[relation]))[0]


@router.delete("/{kind}/{entity_id}/relations/{relation_id}", response_model=Message)
async def remove_relation(
    kind: str,
    entity_id: str,
    relation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    await _get_entity(db, org, kind, entity_id)
    if not await relation_service.remove(db, organization_id=org.id, relation_id=relation_id):
        raise HTTPException(404, "Relation not found")
    await db.commit()
    return Message(message="Relation removed")


# -------------------------------------------------------------------- workflow

@router.post("/{kind}/{entity_id}/submit", response_model=dict)
async def submit_for_review(
    kind: str,
    entity_id: str,
    payload: Optional[WorkflowAction] = None,
    request: Request = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    kind = _require_kind(kind)
    actor = await _actor(db, org, user)
    from app.knowledge.crud_base import KnowledgeCrud

    crud = KnowledgeCrud()
    crud.model = kb.KIND_MODELS[kind]
    crud.kind = kind
    entity = await crud.set_status(
        db, organization_id=org.id, entity_id=entity_id, status="in_review",
        actor=actor, ip_address=get_client_ip(request), note="Submitted for review",
    )
    if entity is None:
        raise HTTPException(404, f"{kind.capitalize()} not found")
    if kind in ("document", "policy"):
        from app.knowledge.workflow_service import workflow_service

        await workflow_service.create_approval(
            db, organization_id=org.id, entity=entity, actor=actor,
            approver_id=payload.approver_id if payload else None,
        )
    await db.commit()
    return {"status": "in_review", "entity_id": entity_id, "kind": kind}
