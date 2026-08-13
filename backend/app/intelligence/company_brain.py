"""Slice 4D.6 — Unified Company Brain experience (orchestration layer).

One canonical composition surface over the 4D.1-4D.5 intelligence estate.
It creates nothing: no memory database, no pattern/insight/search/graph
engine, no parallel brain store. The existing engines remain the canonical
producers; this module composes them at request time.

Pipeline (identical in principle to 4D.1):

    user -> organization -> roles -> governance scopes -> accessible IDs
        -> governed retrieval per source -> bounded evidence -> answer

Governance happens *before* retrieval: every source consulted here is the
existing governed engine, and every raw entity lookup is gated through
``resolve_accessible_ids`` so hidden evidence is never even retrieved.
Nothing is filtered after generation.

The unified answer is additive to the 4D.1 contract (question, claims,
scope_ids, answered_at stay byte-identical in meaning) and adds structured
sections (patterns/memories/insights/knowledge), related entities, a
deterministic summary + bounded confidence, and observability metrics.

Observation only: no operating-layer mutation anywhere in this module.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow

logger = logging.getLogger("vcos.intelligence.company_brain")

# Bounds: no organization-wide scans, every source capped independently.
ANSWER_SECTION_LIMIT = 3
ANSWER_RELATED_LIMIT = 8
OVERVIEW_ATTENTION_LIMIT = 3
OVERVIEW_RECENT_LIMIT = 3
OVERVIEW_COUNT_LIMIT = 200
EVIDENCE_LINK_LIMIT = 5
EVIDENCE_CANDIDATES = 30
RELATED_GRAPH_CANDIDATES = 30
RELATED_LIMIT = 8

# Entity kinds /brain/evidence and /brain/related can resolve directly. Every
# other kind (pattern/insight/memory) delegates to its governed engine.
_ENTITY_META: dict[str, dict[str, Any]] = {
    "project": {"model": "Project", "title": "name", "status": "status", "url": "/projects/{}"},
    "task": {"model": "Task", "title": "title", "status": "status", "url": "/tasks/{}"},
    "decision": {"model": "Decision", "title": "title", "status": "status", "url": "/decisions/{}"},
    "conversation": {"model": "Conversation", "title": "name", "status": None, "url": "/messaging/{}"},
    "message": {"model": "Message", "title": "content", "status": None, "url": "/messaging/messages/{}"},
    "scope": {"model": "GovernanceScope", "title": "name", "status": None, "url": "/governance/scopes/{}"},
    "approval_policy": {"model": "ApprovalPolicy", "title": "name", "status": None, "url": "/governance/approval-policies/{}"},
    "goal": {"model": "Goal", "title": "title", "status": "status", "url": "/goals/{}"},
    "budget": {"model": "Budget", "title": "name", "status": None, "url": "/finance/budgets/{}"},
    "employee": {"model": "Employee", "title": "display_name", "status": None, "url": "/people/{}"},
    "document": {"model": "Document", "title": "title", "status": "status", "url": "/documents/{}"},
    "wiki": {"model": "WikiPage", "title": "title", "status": "status", "url": "/wiki/{}"},
    "policy": {"model": "Policy", "title": "title", "status": "status", "url": "/policies/{}"},
    "sop": {"model": "Sop", "title": "title", "status": "status", "url": "/sops/{}"},
    "template": {"model": "Template", "title": "title", "status": "status", "url": "/templates/{}"},
}

_HISTORY_TRIGGERS = (
    "before", "again", "previously", "last time", "similar", "experience",
    "experienced", "history", "learned", "lesson", "remember", "happened",
    "prior", "past", "like this", "have we", "seen this",
)

_KNOWLEDGE_TRIGGERS = (
    "policy", "sop", "knowledge", "document", "guideline", "process for",
    "how do we", "why did we", "what is the company's", "company's policy",
    "do we have a", "procedure",
)

_PROJECT_TRIGGERS = (
    "project", "initiative", "program", "portfolio", "team is", "delivery",
    "sprint", "milestone",
)

_COMPANY_TRIGGERS = (
    "what's happening", "what is happening", "whats happening", "company",
    "overall", "systemic", "insight", "attention", "status of", "going on",
)


def _code_to_label(type_: str) -> str:
    return type_.replace("_", " ").title()


class CompanyBrain:
    """Unified, governance-first orchestration over 4D.1-4D.5 producers."""

    # ---------------------------------------------------------------- routing

    def _route(self, question: str, entity_type: Optional[str] = None) -> dict[str, bool]:
        """Deterministic source routing — the user never picks a subsystem.

        Broad company questions consult insights + patterns; entity and
        delay-shaped questions add memory; knowledge-shaped questions add
        semantic retrieval. Every consulted source stays governed + bounded.
        """
        lowered = (question or "").lower()
        project_flavored = (
            entity_type is not None
            or any(t in lowered for t in _PROJECT_TRIGGERS)
        )
        delay_flavored = any(
            t in lowered for t in ("delayed", "delay", "blocked", "behind", "slow", "stuck", "overdue")
        )
        history_flavored = delay_flavored or any(t in lowered for t in _HISTORY_TRIGGERS)
        knowledge_flavored = any(t in lowered for t in _KNOWLEDGE_TRIGGERS)
        company_flavored = any(t in lowered for t in _COMPANY_TRIGGERS)
        return {
            "patterns": project_flavored or delay_flavored or company_flavored,
            "insights": project_flavored or delay_flavored or company_flavored,
            "memory": history_flavored,
            "knowledge": knowledge_flavored,
        }

    # ----------------------------------------------------------------- answer

    async def answer(
        self,
        db: AsyncSession,
        organization_id: str,
        question: str,
        *,
        user: Any,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        section_limit: int = ANSWER_SECTION_LIMIT,
    ) -> dict[str, Any]:
        """One governed answer composed from every relevant intelligence source.

        Additive to the 4D.1 contract: the canonical ``claims`` are produced
        by the reasoning engine (unchanged), then unified sections are
        attached — patterns, memories, insights, knowledge and related
        entities, each governed and bounded.
        """
        started = time.perf_counter()
        from app.intelligence.company_context import build_context
        from app.intelligence_network.reasoning_engine import reasoning_engine

        context = await build_context(
            db, user, question,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        base = await reasoning_engine.answer(
            db, organization_id, question,
            user=user, context=context,
            entity_type=entity_type, entity_id=entity_id,
        )
        claims = list(base.get("claims", []))
        route = self._route(question, entity_type)
        sources: list[str] = ["context"]
        governance_filtered = 0
        section_limit = max(1, min(section_limit, 10))

        patterns: list[dict[str, Any]] = []
        if route["patterns"]:
            from app.intelligence.pattern_engine import pattern_engine

            result = await pattern_engine.list_visible(
                db, organization_id=organization_id, user=user, limit=section_limit
            )
            patterns = [
                {
                    "id": p["id"],
                    "title": p.get("title") or p.get("pattern_type"),
                    "pattern_type": p.get("pattern_type"),
                    "family": p.get("family"),
                    "occurrence_count": p.get("occurrence_count"),
                    "confidence": round(float(p.get("confidence") or 0.0), 3),
                    "status": p.get("status"),
                    "last_seen": p.get("last_seen"),
                    "url": f"/brain/patterns/{p['id']}",
                }
                for p in result.get("patterns", [])
            ]
            sources.append("patterns")
            governance_filtered += result.get("truncated") is True and 1 or 0

        insights: list[dict[str, Any]] = []
        if route["insights"]:
            from app.intelligence.insight_engine import insight_engine

            result = await insight_engine.list_visible(
                db, organization_id=organization_id, user=user,
                limit=section_limit, status="active",
            )
            insights = [
                {
                    "id": i["id"],
                    "title": i.get("title"),
                    "insight_type": i.get("insight_type"),
                    "severity": i.get("severity"),
                    "confidence": round(float(i.get("confidence") or 0.0), 3),
                    "status": i.get("status"),
                    "last_observed_at": i.get("last_observed_at"),
                    "url": f"/brain/insights/{i['id']}",
                }
                for i in result.get("insights", [])
            ]
            sources.append("insights")
            governance_filtered += result.get("truncated") is True and 1 or 0

        memories: list[dict[str, Any]] = []
        if route["memory"]:
            from app.memory.memory_store import search as memory_search

            result = await memory_search(
                db, organization_id=organization_id, user=user,
                query=question, limit=section_limit,
            )
            matched = result.get("memories", [])
            if not matched:
                # History-shaped questions deserve the caller's most recent
                # experiences even when scoring floors to nothing — bounded,
                # governed (feed = the visible memory stream, never a scan).
                from app.memory.memory_store import feed as memory_feed

                feed_result = await memory_feed(
                    db, organization_id=organization_id, user=user,
                    limit=section_limit,
                )
                matched = feed_result.get("memories", [])
            memories = [
                {
                    "id": m["id"],
                    "title": m.get("title") or m.get("summary"),
                    "memory_category": m.get("memory_category"),
                    "fact_kind": m.get("fact_kind"),
                    "confidence": round(float(m.get("confidence") or 0.0), 3),
                    "occurred_at": m.get("occurred_at"),
                    "url": f"/brain/memory/{m['id']}",
                }
                for m in matched
            ]
            sources.append("memory")

        knowledge: list[dict[str, Any]] = []
        if route["knowledge"]:
            from app.knowledge.semantic_search import search as semantic_search

            result = await semantic_search(
                db, organization_id=organization_id, user=user,
                query=question, limit=section_limit,
            )
            knowledge = [
                {
                    "source_type": r.get("source_type"),
                    "id": r.get("source_id"),
                    "title": r.get("title"),
                    "snippet": r.get("snippet"),
                    "score": round(float(r.get("retrieval_score") or 0.0), 3),
                    "url": r.get("url"),
                }
                for r in result.get("results", [])
            ]
            sources.append("knowledge")

        related_entities = self._related_from_context(context, limit=ANSWER_RELATED_LIMIT)

        claim_confidences = [c.get("confidence") for c in claims if isinstance(c.get("confidence"), (int, float))]
        confidence = round(
            sum(claim_confidences) / len(claim_confidences), 3
        ) if claim_confidences else 0.5
        summary = self._summarize(claims, insights, patterns, memories, knowledge)
        evidence_count = sum(len(c.get("evidence", [])) for c in claims)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        logger.info(
            "brain_query org=%s sources=%s claims=%d evidence=%d duration_ms=%d",
            organization_id, ",".join(sorted(sources)), len(claims), evidence_count, elapsed_ms,
        )
        return {
            # 4D.1 canonical keys (unchanged meaning)
            "question": question,
            "claims": claims,
            "scope_ids": base.get("scope_ids", []),
            "answered_at": base.get("answered_at") or utcnow().isoformat(),
            # 4D.6 unified additions
            "summary": summary,
            "confidence": confidence,
            "related_entities": related_entities,
            "patterns": patterns,
            "memories": memories,
            "insights": insights,
            "knowledge": knowledge,
            "sources_consulted": sorted(sources),
            "scope": {"org_wide": context.get("org_wide", False)},
            "generated_at": utcnow().isoformat(),
            "metrics": {
                "brain_query": "answer",
                "brain_query_duration_ms": elapsed_ms,
                "sources_consulted": len(sources),
                "evidence_count": evidence_count,
                "answer_claim_count": len(claims),
                "governance_filtered_count": governance_filtered,
            },
        }

    def _summarize(
        self,
        claims: list[dict[str, Any]],
        insights: list[dict[str, Any]],
        patterns: list[dict[str, Any]],
        memories: list[dict[str, Any]],
        knowledge: list[dict[str, Any]],
    ) -> str:
        """Deterministic one-line summary built only from retrieved evidence."""
        parts: list[str] = []
        for claim in claims[:1]:
            parts.append(claim.get("claim", ""))
        for insight in insights[:1]:
            parts.append(
                f"insight: {insight.get('title')} (confidence {insight.get('confidence')})"
            )
        for pattern in patterns[:1]:
            parts.append(
                f"pattern: {pattern.get('title')} seen {pattern.get('occurrence_count')}x"
            )
        for memory in memories[:1]:
            parts.append(f"memory: {memory.get('title')}")
        for item in knowledge[:1]:
            parts.append(f"knowledge: {item.get('title')}")
        return " · ".join(p for p in parts if p)[:500] or "No evidence within your access."

    def _related_from_context(self, context: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        """Related entities from the governed context evidence (bounded)."""
        related: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in context.get("evidence", []):
            key = (item.get("type"), item.get("id"))
            if key in seen or not item.get("id"):
                continue
            seen.add(key)
            related.append({
                "type": item.get("type"),
                "id": item.get("id"),
                "title": item.get("title"),
                "relation": item.get("relation"),
                "url": item.get("url"),
                "timestamp": item.get("timestamp"),
            })
            if len(related) >= limit:
                break
        return related

    # --------------------------------------------------------------- overview

    async def overview(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user: Any,
        attention_limit: int = OVERVIEW_ATTENTION_LIMIT,
        recent_limit: int = OVERVIEW_RECENT_LIMIT,
    ) -> dict[str, Any]:
        """Unified Company Brain overview — what needs attention, what changed.

        Everything is governed (only the caller's visible intelligence) and
        bounded. Insight/pattern counts come from the same org-scoped indexed
        candidate queries the governed lists use (capped), never a scan.
        """
        started = time.perf_counter()
        from app.intelligence.company_context import resolve_caller_access
        from app.intelligence.insight_engine import insight_engine
        from app.intelligence.pattern_engine import pattern_engine
        from app.memory.memory_store import feed as memory_feed

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)

        insights_res = await insight_engine.list_visible(
            db, organization_id=organization_id, user=user,
            limit=max(attention_limit, OVERVIEW_COUNT_LIMIT), status="active",
        )
        patterns_res = await pattern_engine.list_visible(
            db, organization_id=organization_id, user=user,
            limit=OVERVIEW_COUNT_LIMIT,
        )
        memory_res = await memory_feed(
            db, organization_id=organization_id, user=user, limit=OVERVIEW_COUNT_LIMIT,
        )

        insights = insights_res.get("insights", [])
        patterns = patterns_res.get("patterns", [])
        memories = memory_res.get("memories", [])

        attention: list[dict[str, Any]] = []
        for item in insights[:attention_limit]:
            attention.append({
                "source": "insight",
                "id": item["id"],
                "title": item.get("title"),
                "detail": f"{item.get('insight_type')} · severity {item.get('severity')}",
                "confidence": round(float(item.get("confidence") or 0.0), 3),
                "url": f"/brain/insights/{item['id']}",
            })
        for item in patterns[:attention_limit]:
            attention.append({
                "source": "pattern",
                "id": item["id"],
                "title": item.get("title") or item.get("pattern_type"),
                "detail": (
                    f"{item.get('family')} · {item.get('occurrence_count')} occurrences "
                    f"· lifecycle {item.get('status')}"
                ),
                "confidence": round(float(item.get("confidence") or 0.0), 3),
                "url": f"/brain/patterns/{item['id']}",
            })
        for item in memories[:attention_limit]:
            attention.append({
                "source": "memory",
                "id": item["id"],
                "title": item.get("title") or item.get("summary"),
                "detail": item.get("memory_category"),
                "confidence": round(float(item.get("confidence") or 0.0), 3),
                "url": f"/brain/memory/{item['id']}",
            })

        elapsed_ms = round((time.perf_counter() - started) * 1000)
        return {
            "attention": attention,
            "recent_intelligence": {
                "insights": {
                    "count": len(insights),
                    "latest": insights[:recent_limit],
                    "truncated": insights_res.get("truncated", False),
                },
                "patterns": {
                    "count": len(patterns),
                    "latest": patterns[:recent_limit],
                    "truncated": patterns_res.get("truncated", False),
                },
                "memories": {
                    "count": len(memories),
                    "latest": memories[:recent_limit],
                    "truncated": len(memories) >= OVERVIEW_COUNT_LIMIT,
                },
            },
            "scope": {"org_wide": access.org_wide},
            "generated_at": utcnow().isoformat(),
            "metrics": {
                "brain_query": "overview",
                "brain_query_duration_ms": elapsed_ms,
                "sources_consulted": 3,
            },
        }

    # ------------------------------------------------------------------ entity

    async def _resolve_entity(
        self,
        db: AsyncSession,
        organization_id: str,
        user: Any,
        source_type: str,
        source_id: str,
    ) -> Optional[dict[str, Any]]:
        """Resolve + govern one source object. None == hidden or missing."""
        from app.intelligence.company_context import resolve_accessible_ids

        if source_type in ("pattern", "insight", "memory"):
            # Delegate to the governed producers — identical 404 semantics.
            from app.intelligence.insight_engine import insight_engine
            from app.intelligence.pattern_engine import pattern_engine
            from app.memory.memory_store import get as memory_get

            if source_type == "pattern":
                return await pattern_engine.get_visible(
                    db, organization_id=organization_id, user=user, pattern_id=source_id
                )
            if source_type == "insight":
                return await insight_engine.get_visible(
                    db, organization_id=organization_id, user=user, insight_id=source_id
                )
            return await memory_get(
                db, organization_id=organization_id, user=user, memory_id=source_id
            )

        meta = _ENTITY_META.get(source_type)
        if meta is None:
            return None
        model = self._model_for(meta["model"])
        if model is None:
            return None
        row = await db.get(model, source_id)
        if row is None or getattr(row, "organization_id", None) != organization_id:
            return None
        visible = await resolve_accessible_ids(
            db, user, organization_id=organization_id, kind=source_type, ids=[source_id]
        )
        if not visible:
            return None
        title = getattr(row, meta["title"], None)
        if isinstance(title, str) and len(title) > 200:
            title = title[:200]
        return {
            "type": source_type,
            "id": source_id,
            "title": title or _code_to_label(source_type),
            "status": getattr(row, meta["status"], None) if meta["status"] else None,
            "url": meta["url"].format(source_id),
        }

    def _model_for(self, name: str):
        import importlib

        module_map = {
            "Project": ("app.models.project", "Project"),
            "Task": ("app.models.task", "Task"),
            "Decision": ("app.models.knowledge", "Decision"),
            "Conversation": ("app.models.communication", "Conversation"),
            "Message": ("app.models.communication", "Message"),
            "GovernanceScope": ("app.models.governance", "GovernanceScope"),
            "ApprovalPolicy": ("app.models.governance", "ApprovalPolicy"),
            "Goal": ("app.models.goal", "Goal"),
            "Budget": ("app.models.finance", "Budget"),
            "Employee": ("app.models.employee", "Employee"),
            "Document": ("app.models.knowledge", "Document"),
            "WikiPage": ("app.models.knowledge", "WikiPage"),
            "Policy": ("app.models.knowledge", "Policy"),
            "Sop": ("app.models.knowledge", "Sop"),
            "Template": ("app.models.knowledge", "Template"),
        }
        module_name, attr = module_map[name]
        return getattr(importlib.import_module(module_name), attr, None)

    # ---------------------------------------------------------------- evidence

    async def evidence(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user: Any,
        source_type: str,
        source_id: str,
        link_limit: int = EVIDENCE_LINK_LIMIT,
    ) -> Optional[dict[str, Any]]:
        """Evidence drawer for one source object — why sources are connected.

        The object is resolved under governance (404 when hidden), then
        linked intelligence is collected from the existing governed producers
        (patterns/insights/memories/knowledge/graph neighbors), each bounded
        and visibility-filtered. Never exposes evidence the caller cannot
        access.
        """
        from app.intelligence.company_context import resolve_accessible_ids

        obj = await self._resolve_entity(
            db, organization_id, user, source_type=source_type, source_id=source_id
        )
        if obj is None:
            return None
        obj = _normalize_source(obj, source_type, source_id)
        link_limit = max(1, min(link_limit, 10))

        linked_patterns: list[dict[str, Any]] = []
        for item in await self._linked_patterns(
            db, organization_id, user, source_type, source_id, link_limit
        ):
            linked_patterns.append({
                "type": "pattern",
                "id": item["id"],
                "title": item.get("title") or item.get("pattern_type"),
                "relationship": "recurring evidence",
                "url": f"/brain/patterns/{item['id']}",
                "timestamp": item.get("last_seen"),
            })

        linked_insights: list[dict[str, Any]] = []
        for item in await self._linked_insights(
            db, organization_id, user, source_type, source_id, link_limit
        ):
            linked_insights.append({
                "type": "insight",
                "id": item["id"],
                "title": item.get("title"),
                "relationship": "composition",
                "url": f"/brain/insights/{item['id']}",
                "timestamp": item.get("last_observed_at"),
            })

        linked_memories: list[dict[str, Any]] = []
        for item in await self._linked_memories(
            db, organization_id, user, source_type, source_id, link_limit
        ):
            linked_memories.append({
                "type": "memory",
                "id": item["id"],
                "title": item.get("title") or item.get("summary"),
                "relationship": "historical memory",
                "url": f"/brain/memory/{item['id']}",
                "timestamp": item.get("occurred_at"),
            })

        linked_knowledge: list[dict[str, Any]] = []
        if source_type in _ENTITY_META:
            from app.knowledge.semantic_search import search as semantic_search

            result = await semantic_search(
                db, organization_id=organization_id, user=user,
                query=obj.get("title") or source_type, limit=link_limit,
            )
            linked_knowledge = [
                {
                    "type": "knowledge",
                    "id": r.get("source_id"),
                    "source_type": r.get("source_type"),
                    "title": r.get("title"),
                    "relationship": "related knowledge",
                    "url": r.get("url"),
                    "timestamp": r.get("updated_at"),
                }
                for r in result.get("results", [])
            ]

        graph_neighbors = await self._graph_neighbors(
            db, organization_id, user, source_type, source_id, link_limit
        )
        related_intelligence = linked_patterns + linked_insights + linked_memories + linked_knowledge
        return {
            "source": obj,
            "evidence": related_intelligence,
            "related_entities": graph_neighbors,
            "links": {
                "patterns": len(linked_patterns),
                "insights": len(linked_insights),
                "memories": len(linked_memories),
                "knowledge": len(linked_knowledge),
            },
            "limit": link_limit,
            "generated_at": utcnow().isoformat(),
        }

    async def _linked_patterns(
        self, db, organization_id, user, source_type, source_id, limit
    ) -> list[dict[str, Any]]:
        from app.intelligence.pattern_engine import pattern_engine

        result = await pattern_engine.list_visible(
            db, organization_id=organization_id, user=user, limit=EVIDENCE_CANDIDATES
        )
        matched = []
        for pattern in result.get("patterns", []):
            anchored = (
                pattern.get("auth_project_id") == source_id
                or (source_type == "pattern" and pattern["id"] == source_id)
            )
            referenced = any(
                e.get("id") == source_id and (source_type in ("project", "task", "decision", "employee") or e.get("type") == source_type)
                for e in (pattern.get("evidence") or [])
            )
            if anchored or referenced:
                matched.append(pattern)
                if len(matched) >= limit:
                    break
        return matched

    async def _linked_insights(
        self, db, organization_id, user, source_type, source_id, limit
    ) -> list[dict[str, Any]]:
        from app.intelligence.insight_engine import insight_engine

        result = await insight_engine.list_visible(
            db, organization_id=organization_id, user=user,
            limit=EVIDENCE_CANDIDATES, status="active",
        )
        matched = []
        for insight in result.get("insights", []):
            anchored = (
                insight.get("auth_project_id") == source_id
                or insight.get("scope_id") == source_id
                or (source_type == "insight" and insight["id"] == source_id)
            )
            referenced = any(
                e.get("id") == source_id
                for e in (insight.get("evidence") or [])
                if e.get("type") in ("project", "task", "decision", "pattern", "memory")
            )
            if anchored or referenced:
                matched.append(insight)
                if len(matched) >= limit:
                    break
        return matched

    async def _linked_memories(
        self, db, organization_id, user, source_type, source_id, limit
    ) -> list[dict[str, Any]]:
        from app.intelligence.company_context import resolve_caller_access
        from app.models.company_memory import CompanyMemory

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        rows = (
            await db.execute(
                select(CompanyMemory)
                .where(
                    CompanyMemory.organization_id == organization_id,
                    CompanyMemory.status == "active",
                    or_(
                        CompanyMemory.entity_id == source_id,
                        CompanyMemory.auth_project_id == source_id,
                        CompanyMemory.auth_scope_id == source_id,
                        cast(CompanyMemory.source_event_ids, String).like(f'%"{source_id}"%'),
                    ),
                )
                .order_by(CompanyMemory.occurred_at.desc())
                .limit(EVIDENCE_CANDIDATES)
            )
        ).scalars().all()
        matched = []
        for row in rows:
            from app.memory.memory_store import serialize

            if access.org_wide:
                pass
            elif row.auth_scope != "project" or not row.auth_project_id:
                continue
            elif row.auth_project_id not in access.project_ids:
                continue
            matched.append(serialize(row))
            if len(matched) >= limit:
                break
        return matched

    async def _graph_neighbors(
        self, db, organization_id, user, source_type, source_id, limit
    ) -> list[dict[str, Any]]:
        from app.intelligence.company_context import resolve_accessible_ids
        from app.intelligence.graph_engine import graph_engine

        if source_type not in _ENTITY_META or source_type in (
            "document", "wiki", "policy", "sop", "template", "approval_policy",
        ):
            return []
        neighbors = await graph_engine.neighbors(
            db, organization_id=organization_id,
            entity_type=source_type, entity_id=source_id,
            limit=RELATED_GRAPH_CANDIDATES,
        )
        if not neighbors:
            return []
        grouped: dict[tuple[str, str], list[dict]] = {}
        for n in neighbors:
            grouped.setdefault((n["neighbor_type"], n["neighbor_id"]), []).append(n)
        entries = list(grouped.items())[:RELATED_GRAPH_CANDIDATES]
        verified: list[dict[str, Any]] = []
        for (ntype, nid), edges in entries:
            if ntype not in _ENTITY_META:
                continue
            visible = await resolve_accessible_ids(
                db, user, organization_id=organization_id, kind=ntype, ids=[nid]
            )
            if not visible:
                continue
            resolved = await self._resolve_entity(
                db, organization_id, user, source_type=ntype, source_id=nid
            )
            if resolved is None:
                continue
            verified.append({
                "type": ntype,
                "id": nid,
                "title": resolved.get("title"),
                "relation": edges[0].get("relation"),
                "url": resolved.get("url"),
            })
            if len(verified) >= limit:
                break
        return verified

    # ----------------------------------------------------------------- related

    async def related(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user: Any,
        source_type: str,
        source_id: str,
        limit: int = RELATED_LIMIT,
    ) -> Optional[dict[str, Any]]:
        """Concise, governed 'connected to' view for one source object.

        Graph neighbors (when the graph has edges) plus cross-source
        intelligence anchored to the same entity — bounded and
        visibility-filtered before exposure.
        """
        obj = await self._resolve_entity(
            db, organization_id, user, source_type=source_type, source_id=source_id
        )
        if obj is None:
            return None
        obj = _normalize_source(obj, source_type, source_id)
        limit = max(1, min(limit, 20))
        related: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for neighbor in await self._graph_neighbors(
            db, organization_id, user, source_type, source_id, limit
        ):
            key = (neighbor["type"], neighbor["id"])
            if key in seen:
                continue
            seen.add(key)
            related.append(neighbor)
            if len(related) >= limit:
                break

        for item in await self._linked_insights(
            db, organization_id, user, source_type, source_id, max(1, limit // 2)
        ):
            key = ("insight", item["id"])
            if key in seen or len(related) >= limit:
                break
            seen.add(key)
            related.append({
                "type": "insight",
                "id": item["id"],
                "title": item.get("title"),
                "relation": "composition",
                "url": f"/brain/insights/{item['id']}",
            })

        for item in await self._linked_memories(
            db, organization_id, user, source_type, source_id, max(1, limit // 2)
        ):
            key = ("memory", item["id"])
            if key in seen or len(related) >= limit:
                break
            seen.add(key)
            related.append({
                "type": "memory",
                "id": item["id"],
                "title": item.get("title") or item.get("summary"),
                "relation": "historical memory",
                "url": f"/brain/memory/{item['id']}",
            })

        return {
            "source": obj,
            "related": related,
            "limit": limit,
            "truncated": len(related) >= limit,
            "generated_at": utcnow().isoformat(),
        }


def _normalize_source(
    obj: dict[str, Any], source_type: str, source_id: str
) -> dict[str, Any]:
    """Guarantee the source envelope: type/id/title/url on any producer dict."""
    urls = {
        "pattern": "/brain/patterns/",
        "insight": "/brain/insights/",
        "memory": "/brain/memory/",
    }
    normalized = dict(obj)
    normalized["type"] = source_type
    normalized["id"] = source_id
    normalized.setdefault("title", None)
    if "url" not in normalized:
        normalized["url"] = urls.get(source_type, f"/brain/{source_type}s/").format(source_id)
    return normalized


company_brain = CompanyBrain()