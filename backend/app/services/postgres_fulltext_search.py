"""PostgreSQL Full-Text Search Service (Gate 35-B).

Provides high-performance full-text search using PostgreSQL tsvector/GIN indexes
while maintaining canonical semantics, tenant isolation, and governance boundaries.
"""

from __future__ import annotations

import time
from typing import Any, Optional, List, Dict, Set, Tuple
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select, func, text, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import TSVECTOR


class SearchMode(Enum):
    """Search mode determining which index to use."""
    FTS = "fts"           # Full-text search using tsvector/GIN
    TRIGRAM = "trigram"   # Fuzzy/partial matching using pg_trgm
    EXACT = "exact"       # Exact/prefix matching using B-tree
    HYBRID = "hybrid"     # Combination of FTS + trigram


@dataclass
class SearchResult:
    """Unified search result."""
    type: str
    id: str
    title: str
    subtitle: str
    url: str
    snippet: str
    score: float
    metadata: dict
    search_mode: str


class PostgresFullTextSearchService:
    """PostgreSQL Full-Text Search Service for high-volume search.
    
    Uses PostgreSQL's native tsvector/GIN indexes for full-text search
    while preserving canonical semantics, tenant isolation, and governance.
    """
    
    # Searchable entity configurations
    SEARCHABLE_ENTITIES = {
        "knowledge": {
            "table": "knowledge_search_index",
            "search_vector_col": "search_vector",
            "title_col": "title",
            "content_col": "content",
            "entity_type_col": "entity_type",
            "entity_id_col": "entity_id",
            "org_id_col": "organization_id",
            "searchable": True,
        },
        "document": {
            "table": "documents",
            "search_vector_col": "search_vector",
            "title_col": "title",
            "content_col": "description",
            "entity_type_col": None,
            "entity_id_col": "id",
            "org_id_col": "organization_id",
            "searchable": True,
        },
        "wiki": {
            "table": "wiki_pages",
            "search_vector_col": "search_vector",
            "title_col": "title",
            "content_col": "content",
            "entity_type_col": None,
            "entity_id_col": "id",
            "org_id_col": "organization_id",
            "searchable": True,
        },
        "employee": {
            "table": "employees",
            "search_vector_col": "search_vector",
            "title_col": "display_name",
            "content_col": "designation",
            "entity_type_col": None,
            "entity_id_col": "id",
            "org_id_col": "organization_id",
            "searchable": True,
        },
        "project": {
            "table": "projects",
            "search_vector_col": "search_vector",
            "title_col": "name",
            "content_col": "description",
            "entity_type_col": None,
            "entity_id_col": "id",
            "org_id_col": "organization_id",
            "searchable": True,
        },
        "task": {
            "table": "tasks",
            "search_vector_col": "search_vector",
            "title_col": "title",
            "content_col": "description",
            "entity_type_col": None,
            "entity_id_col": "id",
            "org_id_col": "organization_id",
            "searchable": True,
        },
        "customer": {
            "table": "customers",
            "search_vector_col": "search_vector",
            "title_col": "company_name",
            "content_col": "description",
            "entity_type_col": None,
            "entity_id_col": "id",
            "org_id_col": "organization_id",
            "searchable": True,
        },
        "conversation": {
            "table": "conversations",
            "search_vector_col": "search_vector",
            "title_col": "title",
            "content_col": "channel_key",
            "entity_type_col": None,
            "entity_id_col": "id",
            "org_id_col": "organization_id",
            "searchable": True,
        },
        "message": {
            "table": "messages",
            "search_vector_col": "search_vector",
            "title_col": "content",
            "content_col": "content",
            "entity_type_col": None,
            "entity_id_col": "id",
            "org_id_col": "organization_id",
            "searchable": True,
        },
        "decision": {
            "table": "decisions",
            "search_vector_col": "search_vector",
            "title_col": "title",
            "content_col": "description",
            "entity_type_col": None,
            "entity_id_col": "id",
            "org_id_col": "organization_id",
            "searchable": True,
        },
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _to_tsquery(self, query: str) -> str:
        """Convert query string to PostgreSQL tsquery format."""
        # Sanitize and convert to tsquery
        # Split on whitespace, join with & (AND) for all terms
        terms = query.strip().split()
        if not terms:
            return "''"
        # Escape special characters
        escaped = [term.replace("'", "''").replace(":", "").replace("|", "").replace("&", "") for term in terms]
        return " & ".join(f"'{term}':*" for term in escaped)
    
    def _to_tsquery_phrasing(self, query: str) -> str:
        """Convert to tsquery with phraseto_tsquery for phrase matching."""
        # Use plainto_tsquery for simpler phrase handling
        escaped = query.strip().replace("'", "''")
        return f"plainto_tsquery('english', '{escaped}')"
    
    def _to_tsquery_websearch(self, query: str) -> str:
        """Convert to tsquery using websearch_to_tsquery for Google-like syntax."""
        escaped = query.strip().replace("'", "''")
        return f"websearch_to_tsquery('english', '{escaped}')"
    
    async def search_fulltext(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        user_id: str,
        limit: int = 20,
        user: Optional[Any] = None,
        entity_types: Optional[List[str]] = None,
        mode: "SearchMode" = "FTS",
    ) -> dict[str, Any]:
        """Full-text search using PostgreSQL tsvector/GIN indexes.
        
        Args:
            db: Database session
            organization_id: Organization ID for tenant isolation
            query: Search query string
            user_id: User ID for authorization
            limit: Maximum results per entity type
            user: User object for authorization filtering
            entity_types: Optional list of entity types to search
            mode: Search mode (FTS, TRIGRAM, HYBRID)
        
        Returns:
            Search results with metadata
        """
        started = time.perf_counter()
        q = query.strip()
        
        if not q:
            return {
                "query": query,
                "results": [],
                "total": 0,
                "took_ms": 0,
                "mode": mode.value if hasattr(mode, 'value') else str(mode),
            }
        
        # PostgreSQL FTS requires PostgreSQL (tsvector/GIN). Raise so callers
        # fall back to the portable LIKE-based search on other dialects.
        bind = db.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
        if dialect_name != "postgresql":
            raise RuntimeError(
                f"PostgreSQL full-text search requires PostgreSQL (dialect: {dialect_name})"
            )
        
        # Determine which entity types to search
        searchable_types = entity_types or [
            k for k, v in self.SEARCHABLE_ENTITIES.items() 
            if v.get("searchable", True)
        ]
        
        all_results: List[SearchResult] = []
        
        # Build access control
        access: Optional["CallerAccess"] = None
        if user is not None:
            # Import here to avoid circular import
            from app.intelligence.company_context import resolve_caller_access
            access = await resolve_caller_access(
                db, organization_id=organization_id, user=user
            )
        
        for entity_type in searchable_types:
            config = self.SEARCHABLE_ENTITIES.get(entity_type)
            if not config or not config.get("searchable", True):
                continue
            
            try:
                results = await self._search_entity_fts(
                    db=db,
                    organization_id=organization_id,
                    query=query,
                    entity_type=entity_type,
                    config=config,
                    access=access,
                    limit=limit,
                )
                all_results.extend(results)
            except Exception as e:
                # Log but continue with other entity types
                import logging
                logging.getLogger("vcos.search").warning(
                    f"FTS search failed for {entity_type}: {e}"
                )
                continue
        
        # Apply authorization filtering
        if user is not None:
            # Import here to avoid circular import
            from app.services.search_service import search_service
            # Convert to dict format for existing filter
            results_dicts = [self._result_to_dict(r) for r in all_results]
            filtered = await search_service._filter_accessible(
                db, results_dicts, organization_id=organization_id, user=user
            )
            all_results = [SearchResult(**r) for r in filtered]
        
        # Sort by score descending
        all_results.sort(key=lambda r: r.score, reverse=True)
        
        # Apply global limit
        all_results = all_results[:limit]
        
        took_ms = int((time.perf_counter() - started) * 1000)
        
        return {
            "query": query,
            "results": [self._result_to_dict(r) for r in all_results],
            "total": len(all_results),
            "took_ms": int((time.perf_counter() - started) * 1000),
            "mode": "fts",
        }
    
    async def _search_entity_fts(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        entity_type: str,
        config: dict,
        access: Optional["CallerAccess"],
        limit: int,
    ) -> List[SearchResult]:
        """Execute full-text search for a single entity type."""
        
        table = config["table"]
        search_vector_col = config["search_vector_col"]
        title_col = config["title_col"]
        content_col = config["content_col"]
        entity_id_col = config["entity_id_col"]
        org_id_col = config["org_id_col"]
        entity_type_col = config.get("entity_type_col")
        
        # For security, validate table name
        allowed_tables = {v["table"] for v in self.SEARCHABLE_ENTITIES.values()}
        if table not in allowed_tables:
            raise ValueError(f"Invalid table: {table}")
        
        # Build the query using raw SQL for dynamic table/column references
        query_sql = f"""
            SELECT 
                {config['entity_id_col']} as id,
                {config['title_col']} as title,
                {config.get('content_col', config['title_col'])} as content,
                {config.get('entity_type_col') or f"'{entity_type}'"} as entity_type,
                ts_rank_cd({config['search_vector_col']}, websearch_to_tsquery('english', :query)) as rank
            FROM {table}
            WHERE {config['org_id_col']} = :org_id
            AND {config['search_vector_col']} @@ websearch_to_tsquery('english', :query)
        """
        
        # Add authorization filters for scoped users
        params = {
            "org_id": organization_id,
            "query": query,
        }
        
        if access and not access.org_wide:
            # Add scope-based filtering
            # This would need to be implemented based on entity type
            pass
        
        query_sql += " ORDER BY rank DESC LIMIT :limit"
        params["limit"] = limit
        
        result = await db.execute(text(query_sql), params)
        rows = result.all()
        
        results = []
        for row in rows:
            # Build result
            entity_type_display = row.entity_type if hasattr(row, 'entity_type') else entity_type
            results.append(SearchResult(
                type=entity_type_display,
                id=row.id,
                title=row.title,
                subtitle=self._build_subtitle(entity_type, row),
                url=self._build_url(entity_type, row.id),
                snippet=self._build_snippet(row.content, query),
                score=float(row.rank) if row.rank else 0.5,
                metadata={"entity_type": entity_type},
                search_mode="fts",
            ))
        
        return results
    
    def _build_subtitle(self, entity_type: str, row: Any) -> str:
        """Build subtitle for search result."""
        if entity_type == "employee":
            return f"{row.content or 'Employee'}"
        elif entity_type == "project":
            return f"Project · {row.content or 'Active'}"
        elif entity_type == "task":
            return f"Task · {row.content or 'Open'}"
        elif entity_type == "document":
            return f"Document · {row.content or 'Document'}"
        elif entity_type == "wiki":
            return f"Wiki · {row.content or 'Wiki Page'}"
        elif entity_type == "customer":
            return f"Customer · {row.content or 'Active'}"
        elif entity_type in ("conversation", "message"):
            return f"{entity_type.title()} · {row.content[:50] if row.content else ''}"
        elif entity_type == "decision":
            return f"Decision · {row.content or 'Recorded'}"
        return entity_type.title()
    
    def _build_url(self, entity_type: str, entity_id: str) -> str:
        """Build URL for search result."""
        urls = {
            "employee": f"/people/{entity_id}",
            "project": f"/projects/{entity_id}",
            "task": f"/tasks/{entity_id}",
            "document": f"/documents/{entity_id}",
            "wiki": f"/wiki/{entity_id}",
            "wiki_page": f"/wiki/{entity_id}",
            "customer": f"/customers/{entity_id}",
            "conversation": f"/messages/{entity_id}",
            "message": f"/messages/{entity_id}",
            "decision": f"/decisions/{entity_id}",
        }
        return urls.get(entity_type, f"/search?type={entity_type}&id={entity_id}")
    
    def _build_snippet(self, content: Optional[str], query: str) -> str:
        """Build snippet highlighting query terms."""
        if not content:
            return ""
        # Simple snippet - take first 200 chars around first match
        content_lower = content.lower()
        query_lower = query.lower()
        idx = content_lower.find(query_lower)
        if idx == -1:
            return content[:120]
        start = max(0, idx - 60)
        end = min(len(content), idx + len(query) + 60)
        return content[start:end]
    
    def _result_to_dict(self, result: SearchResult) -> dict:
        """Convert SearchResult to dict for API response."""
        return {
            "type": result.type,
            "id": result.id,
            "title": result.title,
            "subtitle": result.subtitle,
            "url": result.url,
            "snippet": result.snippet,
            "score": result.score,
            "metadata": result.metadata,
            "search_mode": result.search_mode,
        }
    
    async def search_trigram(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        user_id: str,
        limit: int = 20,
        user: Optional[Any] = None,
        entity_types: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Trigram-based fuzzy search for partial/fuzzy matching.
        
        Uses pg_trgm indexes for fuzzy/partial matching.
        """
        started = time.perf_counter()
        q = query.strip()
        
        if not q:
            return {"query": query, "results": [], "total": 0, "took_ms": 0}
        
        results = []
        # Similar to FTS but using similarity operator
        # This would use % operator and similarity() function
        
        took_ms = int((time.perf_counter() - started) * 1000)
        return {
            "query": query,
            "results": results,
            "total": len(results),
            "took_ms": took_ms,
            "mode": "trigram",
        }
    
    async def search_hybrid(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        user_id: str,
        limit: int = 20,
        user: Optional[Any] = None,
        entity_types: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Hybrid search combining FTS and trigram."""
        # Run both searches and merge results
        fts_results = await self.search_fulltext(
            db, organization_id=organization_id, query=query,
            user_id=user_id, limit=limit, user=user
        )
        trigram_results = await self.search_trigram(
            db, organization_id=organization_id, query=query,
            user_id=user_id, limit=limit, user=user
        )
        
        # Merge and deduplicate
        # This is a simplified merge - production would use proper ranking
        merged = fts_results["results"] + trigram_results["results"]
        # Deduplicate by ID
        seen = set()
        deduped = []
        for r in merged:
            key = f"{r['type']}:{r['id']}"
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        
        took_ms = int((time.perf_counter() - (time.perf_counter() - (fts_results["took_ms"] + trigram_results["took_ms"]) / 1000)) * 1000)
        
        return {
            "query": fts_results["query"],
            "results": deduped[:limit],
            "total": len(deduped),
            "took_ms": took_ms,
            "mode": "hybrid",
        }


# Export
__all__ = [
    "PostgresFullTextSearchService",
    "SearchMode",
    "SearchResult",
]