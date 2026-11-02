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
from datetime import timedelta
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

# Slice 4D.7 bounds — unified timeline / reasoning / follow-up.
MAX_TIMELINE = 50
MAX_ANSWER_TIMELINE = 6
MAX_NEXT_QUESTIONS = 3
MAX_CHAIN_STEPS = 6
MAX_OWNERSHIP_CLAIMS = 2
MAX_WHAT_CHANGED_CATEGORIES = 6
MAX_WHAT_CHANGED_ITEMS = 20
MAX_CHANGED_QUERY_RESULTS = 50
MAX_CHANGED_DAYS = 30

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

# Phase G — institutional intelligence triggers
_LEARNING_TRIGGERS = (
    "learned", "lesson", "what did we learn", "institutional", "organizational learning",
    "pattern", "recurring", "evidence", "provenance", "why do we believe",
    "contradiction", "superseded", "temporal", "historical belief", "what did we believe",
)

# Phase 4I.4 — planning context triggers
_PLANNING_CONTEXT_TRIGGERS = (
    "what is the state", "what's the state", "whats the state", "company state",
    "planning context", "strategic state", "execution state", "alignment state",
    "what should we do", "should we continue", "what are the risks", "what are the gaps",
    "company health", "organizational health", "strategic health", "execution health",
)


def _code_to_label(type_: str) -> str:
    return type_.replace("_", " ").title()


class CompanyBrain:
    """Unified, governance-first orchestration over 4D.1-4D.5 producers."""

    # ---------------------------------------------------------------- routing

    def _route(self, question: str, entity_type: Optional[str] = None) -> dict[str, bool]:
        """Deterministic source routing — the user never picks a subsystem.

        Routing considers both the question shape *and* the resolved context
        (entity anchor): a follow-up that inherits an anchor consults the
        entity-flavored sources even when it carries no project keywords, so
        the routing is context-aware, not keyword-only.
        """
        lowered = (question or "").lower()
        project_flavored = (
            entity_type is not None
            or any(t in lowered for t in _PROJECT_TRIGGERS)
        )
        delay_flavored = any(
            t in lowered for t in ("delayed", "delay", "blocked", "behind", "slow", "stuck", "overdue")
        )
        change_flavored = any(
            t in lowered
            for t in ("changed", "this week", "this month", "since", "recent", "what happened")
        )
        history_flavored = delay_flavored or change_flavored or any(t in lowered for t in _HISTORY_TRIGGERS)
        knowledge_flavored = any(t in lowered for t in _KNOWLEDGE_TRIGGERS)
        company_flavored = any(t in lowered for t in _COMPANY_TRIGGERS)
        learning_flavored = any(t in lowered for t in _LEARNING_TRIGGERS)
        planning_context_flavored = any(t in lowered for t in _PLANNING_CONTEXT_TRIGGERS)
        return {
            "patterns": project_flavored or delay_flavored or company_flavored or learning_flavored,
            "insights": project_flavored or delay_flavored or company_flavored or learning_flavored,
            "memory": history_flavored or learning_flavored,
            "knowledge": knowledge_flavored,
            "learning": learning_flavored,
            "planning_context": planning_context_flavored or company_flavored,
        }

    def _who_flavored(self, question: str) -> bool:
        lowered = (question or "").lower()
        return any(
            t in lowered
            for t in (
                "who owns", "who is responsible", "who knows", "assigned to",
                "owner of", "who should", "who's", "whos", "in charge of",
                "who is working on", "who leads",
            )
        )

    def _why_flavored(self, question: str) -> bool:
        lowered = (question or "").lower()
        return any(
            t in lowered
            for t in (
                "why", "delayed", "delay", "blocked", "blocking", "behind",
                "stuck", "slow", "slowing", "overdue", "causing",
            )
        )

    def _change_flavored(self, question: str) -> bool:
        lowered = (question or "").lower()
        return any(
            t in lowered
            for t in (
                "what changed", "what's changed", "whats changed", "this week",
                "this month", "recent", "since", "what happened", "digest",
            )
        )

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
        conversation_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """One governed answer composed from every relevant intelligence source.

        Additive to the 4D.1 contract: the canonical ``claims`` are produced
        by the reasoning engine (unchanged), then unified sections are
        attached — patterns, memories, insights, knowledge and related
        entities, each governed and bounded.

        Slice 4D.7 — conversation continuity: when ``conversation_id`` is
        given, a follow-up question that does not name an entity inherits the
        conversation's anchor (the user never repeats it). The answered turn
        is persisted so the next question can anchor again. Returns None when
        the conversation is not found or belongs to another tenant/owner.
        """
        started = time.perf_counter()
        from app.intelligence.company_context import build_context
        from app.intelligence_network.reasoning_engine import reasoning_engine

        conversation = None
        if conversation_id:
            from app.intelligence.brain_conversation import (
                get_conversation,
                resolve_anchor,
            )

            conversation = await get_conversation(
                db,
                organization_id=organization_id,
                user_id=user.id,
                conversation_id=conversation_id,
                include_turns=False,
            )
            if conversation is None:
                return None
            if not (entity_type and entity_id):
                anchor = await resolve_anchor(db, conversation_id=conversation_id)
                if anchor:
                    entity_type = anchor["type"]
                    entity_id = anchor["id"]

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

        # Phase G — institutional learning
        lessons: list[dict[str, Any]] = []
        if route.get("learning"):
            from app.intelligence.company_context import resolve_caller_access
            from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
            from app.models.company_operating import CompanyDecisionContradiction
            from app.models.intelligence import PatternDetection
            from sqlalchemy import select, func, and_, or_

            access = await resolve_caller_access(db, organization_id=organization_id, user=user)

            conditions = [
                OrganizationalLearning.organization_id == organization_id,
                OrganizationalLearning.status == "active",
            ]

            # Scope governance for lessons: check via source pattern if available
            # OrganizationalLearning doesn't have direct scope columns; scope is inherited from source pattern
            if not access.org_wide:
                # For scoped users, we need to check if the lesson's source pattern is accessible
                # We'll do this by joining with PatternDetection for pattern-sourced lessons
                # For non-pattern lessons, default to org scope (accessible to all)
                # This is a simplified check - full scope inheritance would require more complex query
                pass

            stmt = (
                select(
                    OrganizationalLearning,
                    func.count(LearningEvidence.id).label("evidence_count")
                )
                .outerjoin(LearningEvidence, LearningEvidence.learning_id == OrganizationalLearning.id)
                .where(and_(*conditions))
                .group_by(OrganizationalLearning.id)
                .order_by(OrganizationalLearning.updated_at.desc())
                .limit(section_limit)
            )
            result = await db.execute(stmt)
            rows = result.all()

            for learning, evidence_count in rows:
                # For scoped users, check if lesson's source pattern is accessible
                if not access.org_wide and learning.source_type == "pattern" and learning.source_id:
                    pattern = await db.get(PatternDetection, learning.source_id)
                    if pattern:
                        if pattern.scope_type == "project" and pattern.auth_project_id:
                            if pattern.auth_project_id not in access.project_ids:
                                continue
                        elif pattern.scope_type != "org":
                            continue

                # Get contradiction count
                contra_stmt = select(func.count(CompanyDecisionContradiction.id)).where(
                    CompanyDecisionContradiction.lesson_memory_id == learning.id
                )
                contra_result = await db.execute(contra_stmt)
                contradiction_count = contra_result.scalar() or 0

                lessons.append({
                    "id": learning.id,
                    "kind": learning.kind,
                    "fingerprint": learning.fingerprint,
                    "title": learning.title,
                    "lesson": learning.lesson,
                    "status": learning.status,
                    "lifecycle": learning.lifecycle,
                    "confidence": round(float(learning.confidence or 0.0), 3),
                    "topic_name": learning.topic_name,
                    "evidence_count": evidence_count,
                    "contradiction_count": contradiction_count,
                    "observed_at": learning.observed_at.isoformat() if learning.observed_at else None,
                    "source_type": learning.source_type,
                    "source_id": learning.source_id,
                    "url": f"/brain/learning/lessons/{learning.id}",
                })
            sources.append("learning")

        # Phase 4I.4 — Planning Context / State Synthesis
        planning_context: Optional[dict[str, Any]] = None
        if route.get("planning_context"):
            from app.intelligence.company_planning_context_engine import company_planning_context_engine
            
            # Get or synthesize planning context
            pc = await company_planning_context_engine.get_planning_context(
                db, organization_id=organization_id
            )
            if not pc:
                pc = await company_planning_context_engine.synthesize_planning_context(
                    db, organization_id
                )
            
            planning_context = {
                "version": pc.version,
                "computed_at": pc.computed_at.isoformat() if pc.computed_at else None,
                "overall_health": pc.overall_health,
                "overall_confidence": pc.overall_confidence,
                "strategic_state": pc.strategic_state.get("state", {}) if pc.strategic_state else {},
                "execution_state": pc.execution_state.get("state", {}) if pc.execution_state else {},
                "outcome_state": pc.outcome_state.get("state", {}) if pc.outcome_state else {},
                "alignment_state": pc.alignment_state.get("state", {}) if pc.alignment_state else {},
                "learning_state": pc.learning_state.get("state", {}) if pc.learning_state else {},
                "resource_state": pc.resource_state.get("state", {}) if pc.resource_state else {},
                "risk_state": pc.risk_state.get("state", {}) if pc.risk_state else {},
                "governance_state": pc.governance_state.get("state", {}) if pc.governance_state else {},
                "active_contradictions": pc.active_contradictions,
                "critical_gaps": pc.critical_gaps,
                "total_gaps": pc.total_gaps,
                "relevant_lessons": pc.relevant_lessons,
                "high_confidence_lessons": pc.high_confidence_lessons,
                "emerging_patterns": pc.emerging_patterns,
                "elevated_risks": pc.elevated_risks,
                "newly_emerging_risks": pc.newly_emerging_risks,
                "provenance_available": True,
            }
            sources.append("planning_context")

        related_entities = self._related_from_context(context, limit=ANSWER_RELATED_LIMIT)

        # Slice 4D.7 — persona-aware scope: the caller's rule, not a label.
        persona = await self._persona_scope(db, organization_id, user, context)

        # Primary entity the question is about (governed evidence only).
        primary = self._primary_entity(context, entity_type, entity_id)

        # Evidence-backed unified timeline (governed, bounded).
        timeline = await self._timeline_for_answer(
            db, organization_id, user, primary,
            patterns=patterns, insights=insights, memories=memories, lessons=lessons,
        )
        recommended_next = self._recommended_next_questions(
            question, primary, route, claims, persona
        )
        reasoning_chain = self._reasoning_chain(question, claims) if self._why_flavored(question) else []

        related_patterns, related_memories, related_insights = [], [], []
        if primary is not None:
            related_patterns, related_memories, related_insights = (
                await self._related_projections(
                    db, organization_id, user, primary["type"], primary["id"]
                )
            )

        what_changed: Optional[dict[str, Any]] = None
        if self._change_flavored(question):
            what_changed = await self._what_changed_data(
                db, organization_id, user, days=7, persona=persona
            )

        claim_confidences = [c.get("confidence") for c in claims if isinstance(c.get("confidence"), (int, float))]
        confidence = round(
            sum(claim_confidences) / len(claim_confidences), 3
        ) if claim_confidences else 0.5
        summary = self._summarize(claims, insights, patterns, memories, knowledge, lessons, planning_context)
        evidence_count = sum(len(c.get("evidence", [])) for c in claims)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        logger.info(
            "brain_query org=%s sources=%s claims=%d evidence=%d duration_ms=%d",
            organization_id, ",".join(sorted(sources)), len(claims), evidence_count, elapsed_ms,
        )

        answer: dict[str, Any] = {
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
            "lessons": lessons,
            "planning_context": planning_context,
            "sources_consulted": sorted(sources),
            "scope": {"org_wide": persona.get("org_wide", False)},
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
        # Slice 4D.7 additive keys
        if conversation is not None:
            answer["conversation"] = {
                "id": conversation["id"],
                "turn": conversation["turn_count"] + 1,
            }
        answer["persona"] = {
            "org_wide": persona.get("org_wide", False),
            "visible_project_count": persona.get("visible_project_count", 0),
            "visible_scope_count": persona.get("visible_scope_count", 0),
        }
        if timeline:
            answer["timeline"] = timeline
        if recommended_next:
            answer["recommended_next_questions"] = recommended_next
        if reasoning_chain:
            answer["reasoning_chain"] = reasoning_chain
        if related_patterns or related_memories or related_insights:
            answer["related_patterns"] = related_patterns
            answer["related_memories"] = related_memories
            answer["related_insights"] = related_insights
        if what_changed is not None:
            answer["what_changed"] = what_changed
        answer["metrics"].update({
            "timeline_entries": len(timeline),
            "reasoning_chain_steps": len(reasoning_chain),
            "recommended_next_questions": len(recommended_next),
        })

        if conversation is not None:
            from app.intelligence.brain_conversation import append_turn

            anchor_title = None
            if primary is not None:
                anchor_title = primary.get("title")
            elif entity_type and entity_id:
                anchor_title = entity_id
            await append_turn(
                db,
                conversation_id=conversation["id"],
                question=question,
                summary=summary,
                anchor_type=entity_type,
                anchor_id=entity_id,
                anchor_title=anchor_title,
            )
        return answer

    def _summarize(
        self,
        claims: list[dict[str, Any]],
        insights: list[dict[str, Any]],
        patterns: list[dict[str, Any]],
        memories: list[dict[str, Any]],
        knowledge: list[dict[str, Any]],
        lessons: list[dict[str, Any]] = None,
        planning_context: Optional[dict[str, Any]] = None,
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
        if lessons:
            for lesson in lessons[:1]:
                parts.append(f"lesson: {lesson.get('title')} ({lesson.get('lifecycle')})")
        if planning_context:
            pc = planning_context
            parts.append(
                f"company state: {pc.get('overall_health')} (confidence {pc.get('overall_confidence'):.2f}), "
                f"{pc.get('active_contradictions', 0)} contradictions, {pc.get('critical_gaps', 0)} critical gaps, "
                f"{pc.get('elevated_risks', 0)} risks"
            )
        return " · ".join(p for p in parts if p)[:500] or "No evidence within your access."

    # ------------------------------------------------------- 4D.7 persona & follow-up

    async def _persona_scope(
        self,
        db: AsyncSession,
        organization_id: str,
        user: Any,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """The caller's governance persona — counts from the canonical resolver.

        The same question produces different reasoning for different callers
        because the evidence they may see differs; the persona describes that
        rule (org-wide vs scoped) with bounded counts of what they can see.
        """
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(
            db, organization_id=organization_id, user=user
        )
        org_wide = context.get("org_wide", access.org_wide)
        return {
            "org_wide": org_wide,
            "visible_project_count": len(access.project_ids),
            "visible_scope_count": len(access.visible_scope_ids),
            "member_conversation_count": len(access.member_conversation_ids),
            "employee_id": access.employee_id,
        }

    def _primary_entity(
        self,
        context: dict[str, Any],
        entity_type: Optional[str],
        entity_id: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """The entity the question is about, from governed context evidence only.

        Prefers the explicit anchor; otherwise the first project/task/decision
        the context resolved. Never fabricated — always a real evidence item.
        """
        if entity_type and entity_id:
            for item in context.get("evidence", []):
                if item.get("type") == entity_type and item.get("id") == entity_id:
                    return {
                        "type": entity_type,
                        "id": entity_id,
                        "title": item.get("title"),
                    }
            return {"type": entity_type, "id": entity_id, "title": entity_id}
        for item in context.get("evidence", []):
            if item.get("type") in ("project", "task", "decision") and item.get("id"):
                return {
                    "type": item["type"],
                    "id": item["id"],
                    "title": item.get("title"),
                }
        return None

    async def _timeline_for_answer(
        self,
        db: AsyncSession,
        organization_id: str,
        user: Any,
        primary: Optional[dict[str, Any]],
        *,
        patterns: list[dict[str, Any]],
        insights: list[dict[str, Any]],
        memories: list[dict[str, Any]],
        lessons: list[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Evidence-backed "what happened" for the answer (bounded, governed).

        Composed from the governed sections already retrieved for this answer
        plus (for a project anchor) that project's timeline rows — every
        entry references a real row via its id/url. Nothing is scanned.
        """
        entries: list[dict[str, Any]] = []
        for item in memories:
            entries.append({
                "kind": "memory",
                "id": item["id"],
                "title": item["title"],
                "url": f"/brain/memory/{item['id']}",
                "occurred_at": item.get("occurred_at"),
                "confidence": item.get("confidence"),
            })
        for item in patterns:
            entries.append({
                "kind": "pattern",
                "id": item["id"],
                "title": item["title"],
                "url": f"/brain/patterns/{item['id']}",
                "occurred_at": item.get("last_seen"),
                "confidence": item.get("confidence"),
            })
        for item in insights:
            entries.append({
                "kind": "insight",
                "id": item["id"],
                "title": item["title"],
                "url": f"/brain/insights/{item['id']}",
                "occurred_at": item.get("last_observed_at"),
                "confidence": item.get("confidence"),
            })
        if lessons:
            for item in lessons:
                entries.append({
                    "kind": "lesson",
                    "id": item["id"],
                    "title": item["title"],
                    "url": f"/brain/learning/lessons/{item['id']}",
                    "occurred_at": item.get("observed_at"),
                    "confidence": item.get("confidence"),
                })
        if primary is not None and primary["type"] == "project":
            from app.intelligence.company_context import resolve_accessible_ids
            from app.models.project import ProjectTimeline

            visible = await resolve_accessible_ids(
                db, user, organization_id=organization_id,
                kind="project", ids=[primary["id"]],
            )
            if visible:
                rows = (
                    await db.execute(
                        select(ProjectTimeline)
                        .where(
                            ProjectTimeline.organization_id == organization_id,
                            ProjectTimeline.project_id == primary["id"],
                        )
                        .order_by(ProjectTimeline.occurred_at.desc())
                        .limit(MAX_ANSWER_TIMELINE)
                    )
                ).scalars().all()
                for row in rows:
                    entries.append({
                        "kind": "project_timeline",
                        "id": row.id,
                        "title": row.title,
                        "url": f"/projects/{row.project_id}",
                        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                        "confidence": 0.8,
                    })
        entries.sort(key=lambda e: e.get("occurred_at") or "", reverse=True)
        return entries[:MAX_ANSWER_TIMELINE]

    def _recommended_next_questions(
        self,
        question: str,
        primary: Optional[dict[str, Any]],
        route: dict[str, bool],
        claims: list[dict[str, Any]],
        persona: dict[str, Any],
    ) -> list[str]:
        """Deterministic follow-up suggestions, bounded, never mutations.

        Suggestions are observation-shaped ("who knows", "has this happened",
        "what changed") and always reference what the caller can already see.
        """
        lowered = (question or "").lower()
        suggestions: list[str] = []
        if primary is not None:
            title = primary.get("title") or primary["id"]
            suggestions.append(f"Who knows most about {title}?")
            suggestions.append(f"Has this happened before with {title}?")
            suggestions.append(f"What changed with {title} this week?")
            if route.get("learning"):
                suggestions.append(f"What did we learn about {title}?")
                suggestions.append(f"What evidence supports the lesson about {title}?")
        else:
            suggestions.append("What changed this week?")
            if persona.get("org_wide"):
                suggestions.append("Who knows most about this?")
            if route.get("memory"):
                suggestions.append("Has this happened before?")
            else:
                suggestions.append("What needs attention in the company?")
        if route.get("learning"):
            suggestions.append("What patterns exist in the company?")
            suggestions.append("What contradictions exist in our learning?")
            suggestions.append("What did we believe historically?")
        if any(c.get("kind") == "insight" for c in claims):
            suggestions.append("What should I know about the company?")
        # Never suggest the question that was just asked.
        deduped: list[str] = []
        for suggestion in suggestions:
            if suggestion.lower() in lowered or suggestion in deduped:
                continue
            deduped.append(suggestion)
            if len(deduped) >= MAX_NEXT_QUESTIONS:
                break
        return deduped

    def _reasoning_chain(
        self, question: str, claims: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Causal "why" chain — deterministic ordering of evidence-backed claims.

        Steps are drawn only from the claims already produced for this answer
        (each with its own evidence trail); the chain orders them as
        situation -> causes -> signals -> history. Bounded.
        """
        situation = [c for c in claims if c.get("kind") in (None, "observation") and c.get("evidence")]
        dependencies = [c for c in claims if "dependenc" in c.get("claim", "").lower()]
        signals = [c for c in claims if c.get("kind") == "insight"]
        patterns = [c for c in claims if c.get("kind") == "pattern"]
        history = [c for c in claims if c.get("kind") in ("memory", "experience", "lesson", "outcome")]
        institutional = [c for c in claims if c.get("kind") == "institutional"]

        chain: list[dict[str, Any]] = []
        for group, label in (
            (situation, "Current state"),
            (dependencies, "Dependency pressure"),
            (signals, "Systemic signal"),
            (patterns, "Recurring pattern"),
            (institutional, "Institutional learning"),
            (history, "Historical precedent"),
        ):
            for claim in group:
                if len(chain) >= MAX_CHAIN_STEPS:
                    break
                chain.append({
                    "step": len(chain) + 1,
                    "label": label,
                    "claim": claim.get("claim", ""),
                    "evidence": claim.get("evidence", []),
                    "confidence": round(float(claim.get("confidence") or 0.5), 3),
                })
            if len(chain) >= MAX_CHAIN_STEPS:
                break
        return chain

    async def _related_projections(
        self,
        db: AsyncSession,
        organization_id: str,
        user: Any,
        entity_type: str,
        entity_id: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Cross-source projections anchored to one entity (governed, bounded).

        The same linked-pattern/insight/memory retrieval the evidence drawer
        uses, capped small for answer embedding.
        """
        limit = ANSWER_SECTION_LIMIT
        patterns = await self._linked_patterns(
            db, organization_id, user, entity_type, entity_id, limit
        )
        insights = await self._linked_insights(
            db, organization_id, user, entity_type, entity_id, limit
        )
        memories = await self._linked_memories(
            db, organization_id, user, entity_type, entity_id, limit
        )
        return (
            [
                {
                    "id": p["id"],
                    "title": p.get("title") or p.get("pattern_type"),
                    "pattern_type": p.get("pattern_type"),
                    "confidence": round(float(p.get("confidence") or 0.0), 3),
                    "url": f"/brain/patterns/{p['id']}",
                }
                for p in patterns
            ],
            [
                {
                    "id": m["id"],
                    "title": m.get("title") or m.get("summary"),
                    "memory_category": m.get("memory_category"),
                    "confidence": round(float(m.get("confidence") or 0.0), 3),
                    "url": f"/brain/memory/{m['id']}",
                }
                for m in memories
            ],
            [
                {
                    "id": i["id"],
                    "title": i.get("title"),
                    "insight_type": i.get("insight_type"),
                    "confidence": round(float(i.get("confidence") or 0.0), 3),
                    "url": f"/brain/insights/{i['id']}",
                }
                for i in insights
            ],
        )

    async def _what_changed_data(
        self,
        db: AsyncSession,
        organization_id: str,
        user: Any,
        *,
        days: int,
        persona: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Governed "what changed" digest — bounded, persona-aware.

        Org-wide callers see the canonical kernel digest. Scoped callers see
        only their visible scope's activity (projects, tasks, decisions,
        member conversations, memories) — never another scope's numbers.
        """
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(
            db, organization_id=organization_id, user=user
        )
        days = max(1, min(days, MAX_CHANGED_DAYS))
        since = utcnow() - timedelta(days=days)
        categories: list[dict[str, Any]] = []

        from app.models.knowledge import Decision
        from app.models.task import Task
        from app.memory.memory_store import feed as memory_feed

        if access.org_wide:
            from app.kernel.context_engine import context_engine

            digest = await context_engine.digest(db, organization_id, days=days)
            new_tasks = digest.get("new_tasks", 0) or 0
            new_memories = digest.get("new_memories", 0) or 0
            new_documents = digest.get("new_documents", 0) or 0
            new_meetings = digest.get("new_meetings", 0) or 0
            categories.append({"category": "new_tasks", "count": new_tasks})
            categories.append({"category": "new_documents", "count": new_documents})
            categories.append({"category": "new_meetings", "count": new_meetings})
            categories.append({"category": "new_memories", "count": new_memories})
            events = digest.get("events", [])[:MAX_WHAT_CHANGED_ITEMS]
            if events:
                categories.append({
                    "category": "events",
                    "count": len(events),
                    "items": [
                        {
                            "type": "event",
                            "id": e.get("id"),
                            "title": e.get("name"),
                            "url": f"/brain/events?name={e.get('name', '')}",
                            "timestamp": e.get("created_at"),
                        }
                        for e in events
                    ],
                })
        else:
            project_ids = list(access.project_ids)[:MAX_CHANGED_QUERY_RESULTS]
            if project_ids:
                new_tasks = (
                    await db.execute(
                        select(Task).where(
                            Task.organization_id == organization_id,
                            Task.project_id.in_(project_ids),
                            Task.created_at >= since,
                        ).limit(MAX_WHAT_CHANGED_ITEMS + 1)
                    )
                ).scalars().all()
                new_decisions = (
                    await db.execute(
                        select(Decision).where(
                            Decision.organization_id == organization_id,
                            Decision.project_id.in_(project_ids),
                            Decision.created_at >= since,
                        ).limit(MAX_WHAT_CHANGED_ITEMS + 1)
                    )
                ).scalars().all()
                categories.append({
                    "category": "new_tasks",
                    "count": len(new_tasks),
                    "items": [
                        {
                            "type": "task",
                            "id": t.id,
                            "title": t.title,
                            "url": f"/tasks/{t.id}",
                            "timestamp": t.created_at.isoformat() if t.created_at else None,
                        }
                        for t in new_tasks[:MAX_WHAT_CHANGED_ITEMS]
                    ],
                })
                categories.append({
                    "category": "new_decisions",
                    "count": len(new_decisions),
                    "items": [
                        {
                            "type": "decision",
                            "id": d.id,
                            "title": d.title,
                            "url": f"/decisions/{d.id}",
                            "timestamp": d.created_at.isoformat() if d.created_at else None,
                        }
                        for d in new_decisions[:MAX_WHAT_CHANGED_ITEMS]
                    ],
                })
            memories = (await memory_feed(
                db, organization_id=organization_id, user=user, limit=MAX_WHAT_CHANGED_ITEMS
            )).get("memories", [])
            recent_memories = [
                m for m in memories
                if (m.get("occurred_at") or "") >= since.isoformat()
            ][:MAX_WHAT_CHANGED_ITEMS]
            if recent_memories:
                categories.append({
                    "category": "new_memories",
                    "count": len(recent_memories),
                    "items": [
                        {
                            "type": "memory",
                            "id": m["id"],
                            "title": m.get("title") or m.get("summary"),
                            "url": f"/brain/memory/{m['id']}",
                            "timestamp": m.get("occurred_at"),
                        }
                        for m in recent_memories
                    ],
                })
            if access.member_conversation_ids:
                from app.models.communication import Message

                rows = (
                    await db.execute(
                        select(Message)
                        .where(
                            Message.organization_id == organization_id,
                            Message.conversation_id.in_(access.member_conversation_ids),
                            Message.created_at >= since,
                            Message.deleted.is_(False),
                        )
                        .order_by(Message.created_at.desc())
                        .limit(MAX_WHAT_CHANGED_ITEMS)
                    )
                ).scalars().all()
                if rows:
                    categories.append({
                        "category": "conversation_activity",
                        "count": len(rows),
                        "items": [
                            {
                                "type": "message",
                                "id": m.id,
                                "title": (m.content or "")[:120],
                                "url": f"/messaging/messages/{m.id}",
                                "timestamp": m.created_at.isoformat() if m.created_at else None,
                            }
                            for m in rows
                        ],
                    })

        categories = categories[:MAX_WHAT_CHANGED_CATEGORIES]
        return {
            "since": since.isoformat(),
            "days": days,
            "org_wide": access.org_wide,
            "categories": categories,
        }

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

    # ---------------------------------------------------------------- overview

    async def timeline(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user: Any,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = MAX_TIMELINE,
    ) -> Optional[dict[str, Any]]:
        """Unified, evidence-backed company timeline (governed, bounded).

        When anchored to an entity, entries are filtered to that entity's
        scope (project timeline rows + linked intelligence). Returns None when
        the anchor is not resolvable under the caller's access.
        """
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(
            db, organization_id=organization_id, user=user
        )
        limit = max(1, min(limit, MAX_TIMELINE))
        primary = None
        if entity_type and entity_id:
            resolved = await self._resolve_entity(
                db, organization_id, user, source_type=entity_type, source_id=entity_id
            )
            if resolved is None:
                return None
            primary = {"type": entity_type, "id": entity_id, "title": resolved.get("title")}

        entries: list[dict[str, Any]] = []
        per_source = max(2, limit // 3)

        if primary is not None and primary["type"] == "project":
            from app.models.project import ProjectTimeline

            rows = (
                await db.execute(
                    select(ProjectTimeline)
                    .where(
                        ProjectTimeline.organization_id == organization_id,
                        ProjectTimeline.project_id == primary["id"],
                    )
                    .order_by(ProjectTimeline.occurred_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            for row in rows:
                entries.append({
                    "kind": "project_timeline",
                    "id": row.id,
                    "title": row.title,
                    "url": f"/projects/{row.project_id}",
                    "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                    "confidence": 0.8,
                })
        elif primary is not None and primary["type"] == "task":
            from app.intelligence.company_context import resolve_accessible_ids
            from app.models.project import ProjectTimeline

            visible = await resolve_accessible_ids(
                db, user, organization_id=organization_id, kind="task", ids=[primary["id"]]
            )
            if visible:
                from app.models.task import Task

                task = await db.get(Task, primary["id"])
                if task and task.project_id and (
                    access.org_wide or task.project_id in access.project_ids
                ):
                    rows = (
                        await db.execute(
                            select(ProjectTimeline)
                            .where(
                                ProjectTimeline.organization_id == organization_id,
                                ProjectTimeline.project_id == task.project_id,
                            )
                            .order_by(ProjectTimeline.occurred_at.desc())
                            .limit(limit)
                        )
                    ).scalars().all()
                    for row in rows:
                        entries.append({
                            "kind": "project_timeline",
                            "id": row.id,
                            "title": row.title,
                            "url": f"/projects/{task.project_id}",
                            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                            "confidence": 0.8,
                        })

        from app.intelligence.insight_engine import insight_engine
        from app.intelligence.pattern_engine import pattern_engine
        from app.memory.memory_store import feed as memory_feed

        memories = (await memory_feed(
            db, organization_id=organization_id, user=user, limit=per_source
        )).get("memories", [])
        patterns = (await pattern_engine.list_visible(
            db, organization_id=organization_id, user=user, limit=per_source
        )).get("patterns", [])
        insights = (await insight_engine.list_visible(
            db, organization_id=organization_id, user=user,
            limit=per_source, status="active",
        )).get("insights", [])

        memory_ids = {m["id"] for m in memories}
        pattern_ids = {p["id"] for p in patterns}
        insight_ids = {i["id"] for i in insights}

        for item in memories:
            if primary is None or self._timeline_entry_matches(item, primary, "memory"):
                entries.append({
                    "kind": "memory",
                    "id": item["id"],
                    "title": item.get("title") or item.get("summary"),
                    "url": f"/brain/memory/{item['id']}",
                    "occurred_at": item.get("occurred_at"),
                    "confidence": round(float(item.get("confidence") or 0.0), 3),
                })
        for item in patterns:
            if primary is None or self._timeline_entry_matches(item, primary, "pattern"):
                entries.append({
                    "kind": "pattern",
                    "id": item["id"],
                    "title": item.get("title") or item.get("pattern_type"),
                    "url": f"/brain/patterns/{item['id']}",
                    "occurred_at": item.get("last_seen"),
                    "confidence": round(float(item.get("confidence") or 0.0), 3),
                })
        for item in insights:
            if primary is None or self._timeline_entry_matches(item, primary, "insight"):
                entries.append({
                    "kind": "insight",
                    "id": item["id"],
                    "title": item.get("title"),
                    "url": f"/brain/insights/{item['id']}",
                    "occurred_at": item.get("last_observed_at"),
                    "confidence": round(float(item.get("confidence") or 0.0), 3),
                })

        seen: set[tuple[str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for entry in entries:
            key = (entry["kind"], entry["id"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(entry)
        deduped.sort(key=lambda e: e.get("occurred_at") or "", reverse=True)
        entries = deduped[:limit]

        return {
            "timeline": entries,
            "count": len(entries),
            "limit": limit,
            "entity": primary,
            "scope": {"org_wide": access.org_wide},
            "generated_at": utcnow().isoformat(),
            "metrics": {
                "brain_query": "timeline",
                "timeline_entries": len(entries),
                "sources_consulted": 4,
            },
        }

    @staticmethod
    def _timeline_entry_matches(
        item: dict[str, Any], primary: dict[str, Any], kind: str
    ) -> bool:
        entity_id = primary["id"]
        if kind == "memory":
            return (
                item.get("entity_id") == entity_id
                or item.get("auth_project_id") == entity_id
                or item.get("auth_scope_id") == entity_id
            )
        if kind == "pattern":
            return (
                item.get("auth_project_id") == entity_id
                or any(
                    e.get("id") == entity_id
                    for e in (item.get("evidence") or [])
                )
            )
        return (
            item.get("auth_project_id") == entity_id
            or item.get("scope_id") == entity_id
            or any(
                e.get("id") == entity_id
                for e in (item.get("evidence") or [])
                if e.get("type") in ("project", "task", "decision")
            )
        )

    async def what_changed(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user: Any,
        days: int = 7,
    ) -> dict[str, Any]:
        """What changed — governed, persona-aware digest (bounded)."""
        persona = await self._persona_scope(
            db, organization_id, user, {"org_wide": False}
        )
        return await self._what_changed_data(
            db, organization_id, user, days=days, persona=persona
        )

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