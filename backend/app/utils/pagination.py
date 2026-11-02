"""Cursor-based pagination utilities for scale.

Provides cursor-based pagination to replace OFFSET/LIMIT for deep pagination.
"""

from __future__ import annotations

import base64
import json
import hmac
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar, Dict
from typing import Callable, Awaitable, Tuple

from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.expression import ColumnExpressionArgument, UnaryExpression

from app.core.config import get_settings
from app.core.timeutils import utcnow


T = TypeVar("T")


@dataclass
class Cursor:
    """Opaque cursor for pagination."""
    # Cursor fields - only one of after/before should be set
    after: Optional[str] = None
    before: Optional[str] = None
    limit: int = 50
    # Version for future compatibility
    version: int = 1
    # Entity type for validation
    entity_type: Optional[str] = None
    # Ordering fields for composite cursors
    ordering_fields: List[str] = field(default_factory=list)
    
    def encode(self) -> str:
        """Encode cursor to base64 string with HMAC signature."""
        data = {
            "v": self.version,
            "after": self.after,
            "before": self.before,
            "limit": self.limit,
            "entity_type": self.entity_type,
            "ordering_fields": self.ordering_fields,
        }
        encoded = base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).decode()
        # Add HMAC signature for tamper detection
        settings = get_settings()
        signature = hmac.new(
            settings.SECRET_KEY.encode(),
            encoded.encode(),
            hashlib.sha256
        ).hexdigest()[:16]
        return f"{encoded}.{signature}"
    
    @classmethod
    def decode(cls, cursor_str: str) -> "Cursor":
        """Decode cursor from base64 string with HMAC verification."""
        try:
            # Split encoded data and signature
            if "." not in cursor_str:
                return cls()
            encoded, signature = cursor_str.rsplit(".", 1)
            
            # Verify HMAC
            settings = get_settings()
            expected_signature = hmac.new(
                settings.SECRET_KEY.encode(),
                encoded.encode(),
                hashlib.sha256
            ).hexdigest()[:16]
            
            if not hmac.compare_digest(signature, expected_signature):
                # Invalid signature - return empty cursor
                return cls()
            
            data = json.loads(base64.urlsafe_b64decode(encoded).decode())
            
            # Version check
            version = data.get("v", 1)
            if version != 1:
                return cls()
            
            return cls(
                after=data.get("after"),
                before=data.get("before"),
                limit=data.get("limit", 50),
                entity_type=data.get("entity_type"),
                ordering_fields=data.get("ordering_fields", []),
            )
        except Exception:
            return cls()


@dataclass
class Page(Generic[T]):
    """Paginated result page."""
    items: List[T]
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    has_next: bool = False
    has_prev: bool = False
    total_count: Optional[int] = None


TModel = TypeVar("TModel")


class CursorPaginator(Generic[TModel]):
    """Cursor-based paginator for SQLAlchemy models."""
    
    def __init__(
        self,
        model: type,
        order_by: ColumnExpressionArgument,
        cursor_field: InstrumentedAttribute,
        cursor_decode: Callable[[str], Any] = lambda x: x,
        # Composite ordering support
        composite_order_by: Optional[List[ColumnExpressionArgument]] = None,
        composite_cursor_fields: Optional[List[InstrumentedAttribute]] = None,
        composite_cursor_decode: Optional[Callable[[str], Dict[str, Any]]] = None,
        # Entity type for cursor validation
        entity_type: Optional[str] = None,
    ):
        self.model = model
        self.order_by = order_by
        self.cursor_field = cursor_field
        self.cursor_decode = cursor_decode
        # Composite ordering support
        self.composite_order_by = composite_order_by or [order_by]
        self.composite_cursor_fields = composite_cursor_fields or [cursor_field]
        self.composite_cursor_decode = composite_cursor_decode
        self.entity_type = entity_type
    
    def _get_field_name(self, order_expr: ColumnExpressionArgument) -> str:
        """Extract field name from order expression."""
        if isinstance(order_expr, UnaryExpression):
            return order_expr.element.key
        return order_expr.key
    
    def _get_order_direction(self, order_expr: ColumnExpressionArgument) -> str:
        """Determine if ordering is ASC or DESC."""
        if isinstance(order_expr, UnaryExpression):
            modifier = order_expr.modifier
            # In SQLAlchemy, column.desc() returns a UnaryExpression with modifier=operators.desc_op
            # The modifier is a function (operators.desc_op), so we check its name
            modifier_name = getattr(modifier, '__name__', str(modifier)).lower()
            return "DESC" if 'desc' in modifier_name else "ASC"
        return "ASC"
    
    def _decode_composite_cursor(self, cursor_value: str) -> Dict[str, Any]:
        """Decode composite cursor value."""
        if self.composite_cursor_decode:
            decoded = self.composite_cursor_decode(cursor_value)
        else:
            # Fallback: assume single field with format "field=value"
            # This is a fallback for backward compatibility
            decoded = {self.cursor_field.key: self.cursor_decode(cursor_value)}
        
        # Convert ISO format datetime strings back to datetime objects
        for key, value in decoded.items():
            if isinstance(value, str):
                try:
                    decoded[key] = datetime.fromisoformat(value)
                except ValueError:
                    pass  # Not a datetime string, keep as is
        return decoded
    
    def _encode_composite_cursor(self, item: Any) -> str:
        """Encode composite cursor from item."""
        if self.composite_cursor_fields:
            values = {}
            for field in self.composite_cursor_fields:
                value = getattr(item, field.key)
                # Convert datetime to ISO format string for JSON serialization
                if isinstance(value, datetime):
                    value = value.isoformat()
                values[field.key] = value
            return json.dumps(values, separators=(',', ':'))
        value = getattr(item, self.cursor_field.key)
        if isinstance(value, datetime):
            value = value.isoformat()
        return str(value)
    
    def _apply_cursor_condition(
        self,
        query,
        cursor_value: str,
        is_before: bool = False,
    ):
        """Apply cursor condition for composite or single-field ordering."""
        decoded = self._decode_composite_cursor(cursor_value)
        
        if self.composite_order_by and len(self.composite_order_by) > 1:
            # Composite ordering - build compound condition using SQLAlchemy expressions
            conditions = []
            directions = [self._get_order_direction(o) for o in self.composite_order_by]
            
            for i, (field, direction) in enumerate(zip(self.composite_cursor_fields, directions)):
                field_name = field.key
                if field_name not in decoded:
                    continue
                
                field_val = decoded[field_name]
                
                # Build equality prefix for previous fields
                eq_conditions = []
                for j in range(i):
                    prev_field = self.composite_cursor_fields[j].key
                    if prev_field in decoded:
                        eq_conditions.append(getattr(self.model, prev_field) == decoded[prev_field])
                
                # Build inequality condition based on direction
                if direction == "DESC":
                    op_expr = getattr(self.model, field_name) < field_val if not is_before else getattr(self.model, field_name) > field_val
                else:
                    op_expr = getattr(self.model, field_name) > field_val if not is_before else getattr(self.model, field_name) < field_val
                
                if eq_conditions:
                    from sqlalchemy import and_
                    eq_expr = and_(*eq_conditions)
                    conditions.append(and_(eq_expr, op_expr))
                else:
                    conditions.append(op_expr)
            
            if conditions:
                from sqlalchemy import or_
                query = query.where(or_(*conditions))
        else:
            # Single field ordering
            if not is_before:
                query = query.where(self.cursor_field > self.cursor_decode(cursor_value))
            else:
                query = query.where(self.cursor_field < self.cursor_decode(cursor_value))
        
        return query
    
    async def get_page(
        self,
        db: AsyncSession,
        *,
        cursor: Optional[Cursor] = None,
        filters: List = None,
        limit: int = 50,
    ) -> Page:
        """Get a page of results using cursor pagination."""
        # Use provided cursor or create new one with the requested limit
        if cursor is None:
            cursor = Cursor(limit=limit)
        effective_limit = cursor.limit or limit
        
        # Validate cursor entity type
        if cursor.entity_type and self.entity_type:
            if cursor.entity_type != self.entity_type:
                raise ValueError(f"Cursor entity type mismatch: {cursor.entity_type} != {self.entity_type}")
        
        # Build base query
        query = select(self.model)
        
        # Apply filters
        if filters:
            for f in filters:
                query = query.where(f)
        
        # Apply cursor conditions
        if cursor.after:
            query = self._apply_cursor_condition(query, cursor.after, is_before=False)
        elif cursor.before:
            query = self._apply_cursor_condition(query, cursor.before, is_before=True)
        
        # Apply ordering
        query = query.order_by(*self.composite_order_by)
        
        # Fetch one extra to detect has_next
        query = query.limit(effective_limit + 1)
        
        result = await db.execute(query)
        fetched = result.scalars().all()
        
        has_next = len(fetched) > effective_limit
        # Page items are only the requested limit (slice off the lookahead item)
        page_items = fetched[:effective_limit]
        has_next = len(fetched) > effective_limit
        
        # Generate next cursor from the LAST ITEM ACTUALLY RETURNED (not the lookahead item)
        next_cursor = None
        if has_next and fetched:
            # The last item actually returned is at index effective_limit - 1
            cursor_item = fetched[effective_limit - 1]
            cursor_value = self._encode_composite_cursor(cursor_item)
            next_cursor = Cursor(
                after=cursor_value,
                limit=effective_limit,
                entity_type=self.entity_type,
                ordering_fields=[self._get_field_name(o) for o in self.composite_order_by],
            ).encode()
        
        # Generate prev cursor
        prev_cursor = None
        if cursor.after or cursor.before:
            first_item = fetched[0] if fetched else None
            if first_item:
                cursor_value = self._encode_composite_cursor(first_item)
                prev_cursor = Cursor(
                    before=cursor_value,
                    limit=effective_limit,
                    entity_type=self.entity_type,
                    ordering_fields=[self._get_field_name(o) for o in self.composite_order_by],
                ).encode()
        
        return Page(
            items=fetched[:effective_limit],
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            has_next=has_next,
            has_prev=cursor.after is not None or cursor.before is not None,
        )
    
    async def get_total_count(
        self,
        db: AsyncSession,
        filters: List = None,
    ) -> int:
        """Get total count of matching records."""
        query = select(func.count()).select_from(self.model)
        if filters:
            for f in filters:
                query = query.where(f)
        result = await db.execute(query)
        return result.scalar() or 0


# Convenience functions for common pagination patterns

async def paginate_projects(
    db: AsyncSession,
    organization_id: str,
    *,
    cursor: Optional[Cursor] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> Page:
    """Paginate projects with cursor pagination."""
    from app.models.project import Project
    
    paginator = CursorPaginator(
        model=Project,
        order_by=Project.updated_at.desc(),
        cursor_field=Project.updated_at,
        composite_order_by=[Project.updated_at.desc(), Project.id.desc()],
        composite_cursor_fields=[Project.updated_at, Project.id],
        composite_cursor_decode=lambda x: json.loads(x),
        entity_type="project",
    )
    
    filters = [Project.organization_id == organization_id]
    if status:
        filters.append(Project.status == status)
    
    return await paginator.get_page(db, cursor=cursor, filters=filters, limit=limit)


async def paginate_tasks(
    db: AsyncSession,
    organization_id: str,
    *,
    cursor: Optional[Cursor] = None,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    assignee_id: Optional[str] = None,
    limit: int = 50,
) -> Page:
    """Paginate tasks with cursor pagination."""
    from app.models.task import Task
    
    paginator = CursorPaginator(
        model=Task,
        order_by=Task.updated_at.desc(),
        cursor_field=Task.updated_at,
        composite_order_by=[Task.updated_at.desc(), Task.id.desc()],
        composite_cursor_fields=[Task.updated_at, Task.id],
        composite_cursor_decode=lambda x: json.loads(x),
        entity_type="task",
    )
    
    filters = [Task.organization_id == organization_id]
    if project_id:
        filters.append(Task.project_id == project_id)
    if status:
        filters.append(Task.status == status)
    if assignee_id:
        filters.append(Task.assignee_id == assignee_id)
    
    return await paginator.get_page(db, cursor=cursor, filters=filters, limit=limit)


async def paginate_observations(
    db: AsyncSession,
    organization_id: str,
    *,
    cursor: Optional[Cursor] = None,
    observation_type: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
) -> Page:
    """Paginate canonical observations with cursor pagination."""
    from app.models.observability import CanonicalObservation
    
    paginator = CursorPaginator(
        model=CanonicalObservation,
        order_by=CanonicalObservation.observed_at.desc(),
        cursor_field=CanonicalObservation.observed_at,
        composite_order_by=[CanonicalObservation.observed_at.desc(), CanonicalObservation.id.desc()],
        composite_cursor_fields=[CanonicalObservation.observed_at, CanonicalObservation.id],
        composite_cursor_decode=lambda x: json.loads(x),
        entity_type="observation",
    )
    
    filters = [CanonicalObservation.organization_id == organization_id]
    if observation_type:
        filters.append(CanonicalObservation.observation_type == observation_type)
    if severity:
        filters.append(CanonicalObservation.severity == severity)
    
    return await paginator.get_page(db, cursor=cursor, filters=filters, limit=limit)


async def paginate_company_attention(
    db: AsyncSession,
    organization_id: str,
    *,
    cursor: Optional[Cursor] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
) -> Page:
    """Paginate company attention signals with cursor pagination."""
    from app.models.continuous_twin import CompanyAttention
    
    paginator = CursorPaginator(
        model=CompanyAttention,
        order_by=CompanyAttention.priority_score.desc(),
        cursor_field=CompanyAttention.priority_score,
        composite_order_by=[CompanyAttention.priority_score.desc(), CompanyAttention.created_at.desc()],
        composite_cursor_fields=[CompanyAttention.priority_score, CompanyAttention.created_at],
        composite_cursor_decode=lambda x: json.loads(x),
        entity_type="attention",
    )
    
    filters = [CompanyAttention.organization_id == organization_id]
    if status:
        filters.append(CompanyAttention.status == status)
    if priority:
        filters.append(CompanyAttention.priority == priority)
    
    return await paginator.get_page(db, cursor=cursor, filters=filters, limit=limit)


async def paginate_search_results(
    db: AsyncSession,
    organization_id: str,
    query: str,
    *,
    cursor: Optional[Cursor] = None,
    limit: int = 20,
    user: Optional[Any] = None,
) -> Page:
    """Paginate search results with cursor pagination.
    
    Note: For search, we use a composite cursor with relevance score + id.
    """
    from app.models.knowledge import Document
    from app.models.project import Project
    from app.models.task import Task
    from app.models.employee import Employee
    from sqlalchemy import or_, func
    from app.services.search_service import search_service
    
    # For search, we use the search service with pagination
    # This is a simplified version - production would use a search index
    results = await search_service.search(
        db=db,
        organization_id=organization_id,
        query=query,
        user_id="system",  # Would be actual user
        limit=limit + 1,
    )
    
    items = results.get("results", [])
    has_next = len(items) > limit
    if has_next:
        items = items[:limit]
    
    # Generate cursor based on last item's score/id
    next_cursor = None
    if has_next and items:
        last = items[-1]
        cursor_data = f"{last.get('score', 0)}:{last.get('id', '')}"
        next_cursor = Cursor(after=cursor_data, limit=limit).encode()
    
    return Page(
        items=items,
        next_cursor=next_cursor,
        has_next=has_next,
    )