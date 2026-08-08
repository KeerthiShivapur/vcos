"""Generic knowledge CRUD — one implementation for all six entity kinds.

Each kind-specific service extends this with its own fields and workflows.
All creates/updates/deletes are tenanted, versioned, tagged, indexed for
semantic search, emitted on the event bus, written to the audit log, and
auto-linked into the knowledge graph.
"""

from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.knowledge import knowledge_base as kb
from app.knowledge.ai_service import ai_service
from app.models.employee import Employee
from app.schemas.knowledge import entity_url

PUBLISHABLE = ("draft", "in_review", "published", "approved", "archived", "proposed", "made", "implemented", "reviewed")


class KnowledgeCrud:
    model: Any
    kind: str

    def _slug_field(self):
        return self.model.slug

    async def _unique_slug(self, db: AsyncSession, organization_id: str, title: str) -> str:
        base = kb.slugify(title)
        slug = base
        n = 1
        while True:
            row = (
                await db.execute(
                    select(self.model).where(
                        self.model.organization_id == organization_id, self.model.slug == slug
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return slug
            n += 1
            slug = f"{base}-{n}"

    async def _finalize(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity: Any,
        tags: Optional[list[str]],
        actor: Optional[Employee],
        ip_address: Optional[str],
        event_name: str,
        version: Optional[int] = None,
        change_note: Optional[str] = None,
        notify_title: Optional[str] = None,
    ) -> Any:
        """Version row + tags + index + AI enrich + events + audit + auto-links."""
        await kb.create_version(
            db,
            organization_id=organization_id,
            entity_type=self.kind,
            entity_id=entity.id,
            version=version if version is not None else getattr(entity, "version", 1),
            title=entity.title,
            content=getattr(entity, "content", None),
            summary=getattr(entity, "summary", None),
            editor_id=actor.user_id if actor else None,
            change_note=change_note,
        )
        await kb.set_entity_tags(
            db, organization_id=organization_id, entity_type=self.kind, entity_id=entity.id, names=tags
        )
        await ai_service.enrich(db, entity_type=self.kind, entity_id=entity.id, organization_id=organization_id)
        await kb.write_index(db, organization_id=organization_id, entity_type=self.kind, entity_id=entity.id, entity=entity)
        await kb.emit_and_audit(
            db,
            organization_id=organization_id,
            name=event_name,
            actor=actor,
            actor_user_id=actor.user_id if actor else None,
            ip_address=ip_address,
            payload={"entity_type": self.kind, "entity_id": entity.id, "title": entity.title},
            resource_type=self.kind,
            resource_id=entity.id,
        )
        from app.knowledge.relation_service import relation_service

        await relation_service.auto_link(
            db, organization_id=organization_id, entity_type=self.kind, entity_id=entity.id, entity=entity
        )
        await db.flush()
        if notify_title:
            await kb.notify_watchers(
                db,
                organization_id=organization_id,
                entity_type=self.kind,
                entity_id=entity.id,
                title=notify_title,
                body=entity.title,
                actor_user_id=actor.user_id if actor else None,
            )
        return entity

    # ------------------------------------------------------------------ read

    async def list_all(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        status: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        owner_id: Optional[str] = None,
        project_id: Optional[str] = None,
        department_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        filters = [self.model.organization_id == organization_id]
        if status:
            filters.append(self.model.status == status)
        if category:
            filters.append(self.model.category == category)
        if owner_id and hasattr(self.model, "owner_id"):
            filters.append(self.model.owner_id == owner_id)
        if project_id and hasattr(self.model, "project_id"):
            filters.append(self.model.project_id == project_id)
        if department_id and hasattr(self.model, "department_id"):
            filters.append(self.model.department_id == department_id)
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                or_(
                    func.lower(self.model.title).like(pattern),
                    func.lower(self.model.description).like(pattern),
                )
            )
        rows = (
            await db.execute(
                select(self.model).where(*filters).order_by(self.model.updated_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows)

    async def get(self, db: AsyncSession, *, organization_id: str, entity_id: str) -> Any:
        entity = await db.get(self.model, entity_id)
        if entity is None or entity.organization_id != organization_id:
            return None
        return entity

    # ----------------------------------------------------------------- write

    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        payload: dict[str, Any],
        actor: Optional[Employee],
        ip_address: Optional[str],
    ) -> Any:
        tags = payload.pop("tags", None)
        data = dict(payload)
        data["organization_id"] = organization_id
        data["slug"] = await self._unique_slug(db, organization_id, payload.get("title", "untitled"))
        data.setdefault("version", 1)
        data.setdefault("status", "draft")
        if getattr(self.model, "created_at", None) is None:  # pragma: no cover
            pass
        entity = self.model(**data)
        db.add(entity)
        await db.flush()
        if actor and not getattr(entity, "author_id", None) and hasattr(self.model, "author_id"):
            entity.author_id = actor.id
        if actor and not getattr(entity, "owner_id", None) and hasattr(self.model, "owner_id"):
            entity.owner_id = actor.id
        await self._finalize(
            db,
            organization_id=organization_id,
            entity=entity,
            tags=tags,
            actor=actor,
            ip_address=ip_address,
            event_name=f"{self.kind}.created",
            notify_title=f"New {self.kind}",
        )
        await db.flush()
        return entity

    async def update(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_id: str,
        payload: dict[str, Any],
        actor: Optional[Employee],
        ip_address: Optional[str],
    ) -> Optional[Any]:
        entity = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if entity is None:
            return None
        tags = payload.pop("tags", None)
        change_note = payload.pop("change_note", None)
        if payload.get("title") and payload["title"] != entity.title:
            entity.slug = await self._unique_slug(db, organization_id, payload["title"])
        for key, value in payload.items():
            if value is not None and hasattr(entity, key):
                setattr(entity, key, value)
        entity.version = (entity.version or 1) + 1
        entity.updated_at = utcnow()
        if hasattr(self.model, "editor_id"):
            entity.editor_id = actor.user_id if actor else None
        await self._finalize(
            db,
            organization_id=organization_id,
            entity=entity,
            tags=tags,
            actor=actor,
            ip_address=ip_address,
            event_name=f"{self.kind}.updated",
            version=entity.version,
            change_note=change_note,
            notify_title=f"{self.kind.capitalize()} updated",
        )
        await db.flush()
        return entity

    async def delete(self, db: AsyncSession, *, organization_id: str, entity_id: str, actor: Optional[Employee], ip_address: Optional[str]) -> bool:
        entity = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if entity is None:
            return False
        await kb.delete_index(db, organization_id=organization_id, entity_type=self.kind, entity_id=entity_id)
        await kb.emit_and_audit(
            db,
            organization_id=organization_id,
            name=f"{self.kind}.deleted",
            actor=actor,
            actor_user_id=actor.user_id if actor else None,
            ip_address=ip_address,
            payload={"entity_type": self.kind, "entity_id": entity_id, "title": entity.title},
            resource_type=self.kind,
            resource_id=entity_id,
        )
        await db.delete(entity)
        await db.flush()
        return True

    # -------------------------------------------------------------- workflow

    async def set_status(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_id: str,
        status: str,
        actor: Optional[Employee],
        ip_address: Optional[str],
        note: Optional[str] = None,
        version_bump: bool = False,
    ) -> Optional[Any]:
        entity = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if entity is None or status not in PUBLISHABLE:
            return None
        entity.status = status
        entity.updated_at = utcnow()
        if status in ("published", "approved") and not entity.published_at:
            entity.published_at = utcnow()
        if version_bump:
            entity.version = (entity.version or 1) + 1
            await kb.create_version(
                db,
                organization_id=organization_id,
                entity_type=self.kind,
                entity_id=entity.id,
                version=entity.version,
                title=entity.title,
                content=getattr(entity, "content", None),
                summary=getattr(entity, "summary", None),
                editor_id=actor.user_id if actor else None,
                change_note=note or f"Status → {status}",
            )
        await kb.emit_and_audit(
            db,
            organization_id=organization_id,
            name=f"{self.kind}.{status}",
            actor=actor,
            actor_user_id=actor.user_id if actor else None,
            ip_address=ip_address,
            payload={"entity_type": self.kind, "entity_id": entity.id, "title": entity.title, "note": note},
            resource_type=self.kind,
            resource_id=entity.id,
        )
        await kb.notify_watchers(
            db,
            organization_id=organization_id,
            entity_type=self.kind,
            entity_id=entity.id,
            title=f"{self.kind.capitalize()} {status}",
            body=entity.title,
            actor_user_id=actor.user_id if actor else None,
        )
        await db.flush()
        return entity

    async def restore(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_id: str,
        version: int,
        actor: Optional[Employee],
        ip_address: Optional[str],
    ) -> Optional[Any]:
        """Restore a previous version's title/content into the current entity."""
        from app.models.knowledge import DocumentVersion

        entity = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if entity is None:
            return None
        old = (
            await db.execute(
                select(DocumentVersion).where(
                    DocumentVersion.organization_id == organization_id,
                    DocumentVersion.entity_type == self.kind,
                    DocumentVersion.entity_id == entity_id,
                    DocumentVersion.version == version,
                )
            )
        ).scalar_one_or_none()
        if old is None:
            return None
        entity.title = old.title
        entity.content = old.content
        entity.summary = old.summary
        entity.version = (entity.version or 1) + 1
        entity.updated_at = utcnow()
        await self._finalize(
            db,
            organization_id=organization_id,
            entity=entity,
            tags=None,
            actor=actor,
            ip_address=ip_address,
            event_name=f"{self.kind}.restored",
            version=entity.version,
            change_note=f"Restored from v{version}",
            notify_title=f"{self.kind.capitalize()} restored",
        )
        await db.flush()
        return entity
