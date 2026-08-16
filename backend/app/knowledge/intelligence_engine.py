"""Slice 4E.4 — Knowledge Intelligence Engine.

4E.1-4E.3 build the canonical knowledge substrate: sources -> claims ->
topics -> one synthesized understanding per topic. 4E.4 turns that
substrate into intelligence — what the company's knowledge MEANS:

    4.4.1 discovery          give meaning to a question ("why are enterprise
                             customers delaying renewals?") by connecting
                             observed evidence across the organization,
    4.4.2 relationships      traverse the knowledge graph with typed edges
                             (supported_by / affected / based_on / concerns),
    4.4.3 change + impact    what changed in our understanding, and who else
                             is affected when a piece of knowledge changes,
    4.4.4 gaps               missing evidence, stale knowledge, unresolved
                             contradictions, missing ownership, undocumented
                             processes,
    4.4.5 timeline           (already surfaced by 4E.3; re-exposed here for
                             the universal query surface),
    4.4.6 confidence +       every number can be explained factor by factor;
       ownership + health    one topic's accountable owner; the 7-bar
                             organizational knowledge health,
    4.4.7 recommendations    deterministic, evidence-backed, persisted
                             exactly-once and auto-resolved when the
                             condition clears,
    4.4.8 universal query    one surface: natural questions route to the
                             right intelligence and only the evidence the
                             caller may see.

Design laws (mirroring 4E.1-4E.3, per the 4E.4 contract):
* deterministic first — no LLM invents an organizational fact anywhere here,
* governance is inherited: no intelligence may be more permissive than the
  evidence used to produce it. Every read resolves caller access BEFORE
  assembly and never fetches what the caller cannot see; a topic with no
  visible evidence is indistinguishable from a missing topic,
* one canonical brain: this engine REUSES the 4E.3 substrate (evidence
  collection, contradiction detection, synthesis claims, visibility) — there
  are no competing pipelines,
* exact-once: recommendations are keyed by stable fingerprints; replays
  never duplicate and conditions that clear are resolved, not re-created,
* change-driven, bounded: no full-org rescans — every candidate fetch is an
  indexed organization-scoped query with a hard limit.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.intelligence.company_context import CallerAccess, resolve_caller_access, tokens
from app.knowledge.canonical_service import (
    _AUTHORITY_LABELS,
    _load_provenance,
    now_utc,
)
from app.knowledge.synthesis_engine import (
    _AUTHORITY_NORM,
    _MONTHS,
    _json_loads,
    _snippet,
    extract_facets,
    synthesis_engine,
)
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEvidence,
    KnowledgeRecommendation,
    KnowledgeRelation,
    KnowledgeSource,
    KnowledgeTopic,
)

logger = logging.getLogger("vcos.knowledge.intelligence")

# ---------------------------------------------------------------------------
# bounds — every read and every write is hard-capped
# ---------------------------------------------------------------------------

_MAX_TOPICS_SCAN = 100         # topics considered by org-wide intelligence
_MAX_CLAIM_SCAN = 400          # candidate claims loaded per intelligence pass
_MAX_DISCOVERY = 10            # discovery results
_MAX_CHANGES = 20              # change-intelligence results
_MAX_IMPACT_ENTITIES = 60      # impacted entities (graph neighbors)
_MAX_IMPACT_CLAIMS = 40        # dependent knowledge claims quoted
_MAX_NEIGHBORS = 40            # relationship traversal bound
_MAX_GAPS_PER_KIND = 8         # gaps per kind
_MAX_GAPS = 30                 # total gaps surfaced
_MAX_RECOMMENDATIONS = 25      # recommendation rows evaluated / surfaced
_MAX_ANSWER_EVIDENCE = 12      # citations in an intelligence answer

_DOCUMENT_FAMILIES = frozenset({"document", "wiki", "policy", "sop", "template"})
_PROCESS_FAMILIES = frozenset({"pattern", "task", "meeting"})

# freshness buckets shared by health/gaps
_FRESH_OK = frozenset({"very_high", "high", "medium"})

# intent routing for the universal knowledge query (deterministic keywords)
_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    # Slice 4E.7 — the company-level loop surfaces route FIRST so the company
    # meaning wins over the knowledge-only meaning ("what changed in the
    # company since yesterday" is company change, not claim change).
    ("company_changes", ("changed overnight", "changed in the company", "company changes", "changed since yesterday")),
    ("learned", ("what did we learn", "what have we learned", "did we learn", "lessons learned", "what should the company remember", "what did the company learn")),
    ("why", ("why is", "why are", "why did", "why was", "is at risk", "at risk", "explain why")),
    ("affected", ("which projects are affected", "projects are affected", "who is affected", "what is affected", "whom does")),
    ("changes", ("what changed", "since", "changed in our understanding", "when did", "evolution")),
    ("impact", ("impact", "affected", "affect", "what else", "depends on", "dependent")),
    ("gaps", ("don't know", "don t know", "missing", "gaps", "stale", "outdated", "unverified", "undocumented")),
    ("contradictions", ("uncertain", "uncertainty", "conflict", "contradict", "inconsistent")),
    ("ownership", ("who owns", "owner of", "accountable for")),
    ("companyhealth", ("company health", "how healthy is the company", "is the company healthy", "how is the company doing")),
    ("health", ("health", "healthy", "how are we doing")),
    ("should", ("should we launch", "should we enter", "should we invest", "should we expand", "should we hire", "should we do this")),
    ("worry", ("should i worry", "worry", "emerging risk", "concern")),
    ("decide", ("needs a decision", "needs our decision", "decision needed", "should leadership decide")),
    ("decisions", ("which decisions", "decision quality", "decision performance", "expected vs actual", "decisions are causing", "how good are our decisions")),
    ("next", ("should i do next", "should we do next", "next action", "what should we do next")),
    ("recommendations", ("recommend", "improve", "prioritize")),
    ("missing", ("what are we missing", "are we missing", "what critical information")),
    ("confident", ("how confident", "confident are we", "confidence")),
    ("stakeholders", ("who needs to know", "who should know")),
    ("provenance", ("what is the source", "source of", "where did")),
    # Slice 4E.6 — universal action intents: the company asks about its
    # governed actions in the same natural surface as its knowledge.
    ("actions", ("action center", "my action", "action required", "open action", "what is being actioned", "acting on")),
    ("attention", ("needs my attention", "needs attention", "should i focus", "what is urgent")),
    ("blocked", ("is blocked", "blocked", "stuck", "unblock")),
    ("overdue", ("overdue", "behind schedule", "missed deadline")),
    ("escalation", ("escalat", "raised to leadership")),
    # Slice 4F.1 — universal people intelligence questions route to the
    # governed people surfaces (deterministic: unit membership, reporting
    # lines, org chart, directory). Kept last so "who owns X" stays the
    # knowledge ownership meaning.
    ("people", ("who works in", "who works at", "who is in", "who are in",
                "who belongs to", "who is part of", "who are the people in",
                "members of the", "which team members are in", "people in the",
                "who manages", "who reports to", "reporting line",
                "org chart", "organisation chart", "organization chart")),
    # Slice 4F.3 — expertise EVIDENCE & TRUST questions: "why do you think X
    # knows Y", "what evidence backs that", "can we trust X on Y", "is it
    # still current". Placed just before expertise discovery so the WHY of a
    # claim wins over the WHO of discovery, without stealing "why is/are/did"
    # (the knowledge why intent sits earlier and wins those).
    ("expertise_trust", ("why does", "why do you", "why you think", "why you say",
                         "what evidence", "evidence for", "evidence behind",
                         "evidence trail", "proven by", "recent evidence",
                         "still current", "their expertise", "should we trust",
                         "can we trust", "how much do we trust", "do you trust",
                         "rated for", "how did you rate")),
    # Slice 4F.2 — universal skills & expertise questions. Kept after people
    # so "who knows X" never steals the reporting/unit meanings, but before
    # the discovery default. "what does X know" is person expertise.
    ("expertise", ("who knows", "who is an expert", "who is the expert",
                   "who are the experts", "experts in", "expert in",
                   "expertise", "strongest in", "best at", "skilled in",
                   "skilled at", "proficient in", "knows about",
                   "knows python", "works with", "what does",
                   "does anyone know", "who can help with", "who could help",
                   "is good at", "is known for", "good at whats",
                   "recently", "who has shown", "who demonstrated")),
    # Slice 4F.4 — ownership & responsibility questions. "who owns" stays the
    # knowledge meaning (above); these surface the canonical responsibility
    # record: who holds it, who held it before, who takes over if they leave,
    # where responsibility is missing or dangerously concentrated.
    ("responsibility", ("whose responsibility", "responsible for",
                        "in charge of", "who is accountable",
                        "who is responsible")),
    ("continuity", ("who takes over", "backup owner", "would take over",
                    "takes over when", "single point of failure",
                    "single-person dependency", "too many responsibilities",
                    "overloaded with work")),
    ("responsibility_history", ("who used to own", "who owned", "who previously",
                                "was responsible for", "used to be responsible",
                                "responsibility history")),
    ("responsibility_gaps", ("missing owner", "no owner", "who should own",
                             "ownership gap", "unowned", "without an owner",
                             "owner left", "who owns nothing", "gap analysis")),
]

_CHANGE_SIGNAL = re.compile(
    r"\b(changed|moved|delayed|postponed|rescheduled|increased|decreased|"
    r"launched|released|approved|rejected|cancelled|extended|paused|resumed|"
    r"rolled out|rollout|signed|hired|frozen|unfrozen)\b",
    re.IGNORECASE,
)


def _clean_topic_name(name: Optional[str]) -> Optional[str]:
    """Keyword-derived topics can carry JSON punctuation from their source
    (e.g. '"renewal"' or '["renewal"') — surface the name as a plain word."""
    if not name:
        return name
    name = str(name).strip()
    if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
        name = name[1:-1]
    if len(name) >= 2 and name[0] == "[" and name[-1] == '"':
        name = name[1:-1]
    name = name.strip()
    return name[:120] or None


def _utcnow_iso() -> str:
    return now_utc().isoformat()


def _stem_overlap(a: set[str], b: set[str]) -> bool:
    """Deterministic inflection-aware token overlap.

    Exact token matches win; otherwise tokens sharing a 5+ character prefix
    (renewals ~ renewal, delays ~ delay, migrating ~ migration) count as the
    same concept — plural/singular/tense without any stemmer.
    """
    if not a or not b:
        return False
    if a & b:
        return True
    a_long = [t for t in a if len(t) >= 5]
    b_long = [t for t in b if len(t) >= 5]
    for left in a_long:
        for right in b_long:
            if left[:5] == right[:5]:
                return True
    return False


def _matched_query_tokens(query_tokens: set[str], claim_tokens: set[str]) -> list[str]:
    exact = sorted(query_tokens & claim_tokens, key=str.lower)
    if exact:
        return exact
    extra = []
    for left in sorted(query_tokens, key=str.lower):
        if len(left) < 5:
            continue
        if any(len(right) >= 5 and left[:5] == right[:5] for right in claim_tokens):
            extra.append(left)
    return extra


def _fingerprint(kind: str, *parts: str) -> str:
    digest = hashlib.sha256(("|".join((kind, *parts))).encode("utf-8")).hexdigest()
    return digest[:80]


# ---------------------------------------------------------------------------
# shared scan: ONE bounded pass over the org's knowledge, per caller
# ---------------------------------------------------------------------------


class IntelligenceEngine:
    async def _access(self, db: AsyncSession, *, organization_id: str, user: Any) -> CallerAccess:
        if user is None:
            return CallerAccess(
                organization_id=organization_id,
                user_id="system",
                employee_id=None,
                org_wide=True,
            )
        return await resolve_caller_access(db, organization_id=organization_id, user=user)

    async def _topic_by_name(
        self, db: AsyncSession, *, organization_id: str, topic_name: str
    ) -> Optional[KnowledgeTopic]:
        return (
            await db.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == organization_id,
                    KnowledgeTopic.name == topic_name,
                )
            )
        ).scalar_one_or_none()

    async def _topics_by_ids(
        self, db: AsyncSession, *, organization_id: str, topic_ids: list[str]
    ) -> dict[str, KnowledgeTopic]:
        if not topic_ids:
            return {}
        rows = (
            await db.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == organization_id,
                    KnowledgeTopic.id.in_(topic_ids),
                    KnowledgeTopic.status == "active",
                )
            )
        ).scalars().all()
        return {t.id: t for t in rows}

    async def _scan_topics(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        access: CallerAccess,
        include_superseded: bool = False,
        limit: int = _MAX_TOPICS_SCAN,
    ) -> dict[str, dict[str, Any]]:
        """One governed pass over the org's topics -> visible evidence claims.

        Mirrors the 4E.3 evidence law (name + aliases, provenance visibility,
        authority x freshness ranking) but in a single bounded fetch so
        org-wide intelligence never degrades into N topic queries.
        """
        topics = list(
            (
                await db.execute(
                    select(KnowledgeTopic)
                    .where(
                        KnowledgeTopic.organization_id == organization_id,
                        KnowledgeTopic.status == "active",
                    )
                    .order_by(KnowledgeTopic.updated_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
        )
        if not topics:
            return {}
        candidates = list(
            (
                await db.execute(
                    select(KnowledgeClaim)
                    .where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.claim_type != "synthesis",
                    )
                    .order_by(KnowledgeClaim.valid_from.desc())
                    .limit(_MAX_CLAIM_SCAN)
                )
            ).scalars().all()
        )
        sources = list(
            (
                await db.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.organization_id == organization_id,
                        KnowledgeSource.source_type.in_({c.subject_type for c in candidates}),
                    )
                )
            ).scalars().all()
        )
        by_source: dict[tuple[str, str], KnowledgeSource] = {
            (s.source_type, s.source_id): s for s in sources
        }
        out: dict[str, dict[str, Any]] = {}
        for topic in topics:
            aliases = [a.lower() for a in _json_loads(topic.aliases_json, []) if a]
            needles = {topic.name.lower(), *aliases}
            scored: list[tuple[float, KnowledgeClaim]] = []
            for claim in candidates:
                if not include_superseded and claim.status == "superseded":
                    continue
                source = by_source.get((claim.subject_type, claim.subject_id))
                if source is None:
                    continue
                provenance = _load_provenance(source.provenance_json)
                if not synthesis_engine._visible(access, provenance):
                    continue
                text = (
                    f"{source.title} {claim.object_text} "
                    f"{provenance.get('category') or ''} {provenance.get('keywords') or ''}"
                ).lower()
                if not any(needle in text for needle in needles):
                    continue
                mention = 1.0
                if not any(needle in claim.object_text.lower() for needle in needles) and \
                   not any(needle in (source.title or "").lower() for needle in needles):
                    mention = 0.6
                relevance = (
                    _AUTHORITY_NORM.get(claim.authority_level, 0.25)
                    * (0.4 + 0.6 * (source.freshness_score or 0) / 100.0)
                    * mention
                )
                scored.append((relevance, claim))
            scored.sort(key=lambda item: (-item[0], ensure_aware(item[1].valid_from)))
            if scored:
                out[topic.id] = {
                    "topic": topic,
                    "claims": [c for _, c in scored[:_MAX_CLAIM_SCAN]],
                    "sources": by_source,
                }
        return out

    async def _synthesis_current_claim(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_id: str,
        access: CallerAccess,
    ) -> Optional[KnowledgeClaim]:
        claims = [
            c for c in await synthesis_engine._synthesis_claims(
                db, organization_id=organization_id, topic_id=topic_id
            )
            if c.status != "superseded"
            and await synthesis_engine._claim_visible(
                db, organization_id=organization_id, claim=c, access=access
            )
        ]
        if not claims:
            return None
        if len(claims) == 1:
            return claims[0]
        return max(claims, key=lambda c: ensure_aware(c.valid_from))

    async def _synthesis_evolution(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_id: str,
        access: CallerAccess,
    ) -> list[KnowledgeClaim]:
        return [
            c for c in await synthesis_engine._synthesis_claims(
                db, organization_id=organization_id, topic_id=topic_id
            )
            if await synthesis_engine._claim_visible(
                db, organization_id=organization_id, claim=c, access=access
            )
        ]

    # ------------------------------------------------------------------
    # 4.4.1 — knowledge discovery
    # ------------------------------------------------------------------

    async def discover(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        user: Any,
        limit: int = _MAX_DISCOVERY,
        in_families: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Give meaning to a question: rank topics by evidence match, then
        return each topic's observed evidence, synthesized understanding,
        confidence and citation chain — only from visible evidence."""
        access = await self._access(db, organization_id=organization_id, user=user)
        query_tokens = tokens(query)
        families = frozenset(in_families or [])

        scanned = await self._scan_topics(
            db, organization_id=organization_id, access=access
        )
        ranked: list[tuple[float, dict[str, Any]]] = []
        for topic_id, entry in scanned.items():
            topic = entry["topic"]
            claims = entry["claims"]
            source_map = entry["sources"]
            matched: list[dict[str, Any]] = []
            for claim in claims:
                source = source_map.get((claim.subject_type, claim.subject_id))
                hay = f"{source.title if source else ''} {claim.object_text} {topic.name}"
                claim_tokens = tokens(hay)
                if not _stem_overlap(query_tokens, claim_tokens):
                    continue
                if families and claim.subject_type not in families:
                    continue
                matched.append(
                    {
                        "claim_id": claim.id,
                        "subject_type": claim.subject_type,
                        "subject_id": claim.subject_id,
                        "excerpt": _snippet(claim.object_text, 200),
                        "source_title": source.title if source else None,
                        "authority_level": claim.authority_level,
                        "valid_from": ensure_aware(claim.valid_from).isoformat(),
                        "matched_tokens": _matched_query_tokens(query_tokens, claim_tokens)[:8],
                    }
                )
            if not matched:
                continue
            current = await self._synthesis_current_claim(
                db, organization_id=organization_id, topic_id=topic_id, access=access
            )
            families_present = {m["subject_type"] for m in matched}
            authority = max((m["authority_level"] for m in matched), default=1)
            score = (
                0.5 * min(1.0, len(matched) / 5.0)
                + 0.25 * _AUTHORITY_NORM.get(authority, 0.25)
                + 0.25 * min(1.0, len(families_present) / 3.0)
            )
            ranked.append(
                (
                    score,
                    {
                        "topic": topic,
                        "matched": matched,
                        "families": sorted(families_present),
                        "current": current,
                        "authority": authority,
                    },
                )
            )
        ranked.sort(key=lambda item: -item[0])
        limit = max(1, min(limit, _MAX_DISCOVERY))
        results: list[dict[str, Any]] = []
        for score, entry in ranked[:limit]:
            current = entry["current"]
            results.append(
                {
                    "topic": {"id": entry["topic"].id, "name": _clean_topic_name(entry["topic"].name)},
                    "score": round(score, 3),
                    "statement": current.object_text if current else None,
                    "claim_id": current.id if current else None,
                    "confidence": current.confidence if current else None,
                    "authority": entry["authority"],
                    "families": entry["families"],
                    "evidence": entry["matched"][:_MAX_ANSWER_EVIDENCE],
                }
            )
        return {
            "query": query,
            "intent": "discovery",
            "total": len(results),
            "answers": results,
            "scope": "org" if access.org_wide else "project",
            "generated_at": _utcnow_iso(),
        }

    # ------------------------------------------------------------------
    # 4.4.2 — relationship (graph) intelligence
    # ------------------------------------------------------------------

    async def relationships(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: str,
        entity_id: str,
        user: Any,
        limit: int = _MAX_NEIGHBORS,
    ) -> Optional[dict[str, Any]]:
        """Typed graph view of one entity: every edge (either direction) and
        each neighbor's canonical claims + the topics they speak about."""
        access = await self._access(db, organization_id=organization_id, user=user)
        edges = list(
            (
                await db.execute(
                    select(KnowledgeRelation).where(
                        KnowledgeRelation.organization_id == organization_id,
                        (
                            (KnowledgeRelation.source_type == entity_type)
                            & (KnowledgeRelation.source_id == entity_id)
                        )
                        | (
                            (KnowledgeRelation.target_type == entity_type)
                            & (KnowledgeRelation.target_id == entity_id)
                        ),
                    ).order_by(KnowledgeRelation.created_at.desc())
                    .limit(limit * 3)
                )
            ).scalars().all()
        )
        neighbors: dict[tuple[str, str], dict[str, Any]] = {}
        for edge in edges:
            if (edge.source_type, edge.source_id) == (entity_type, entity_id):
                key = (edge.target_type, edge.target_id)
                direction, relation = "outgoing", edge.relation_type
            else:
                key = (edge.source_type, edge.source_id)
                direction, relation = "incoming", edge.relation_type
            if key == (entity_type, entity_id):
                continue
            entry = neighbors.setdefault(
                key, {"type": key[0], "id": key[1], "title": None, "relations": []}
            )
            entry["relations"].append(
                {"relation": relation, "direction": direction, "edge_id": edge.id}
            )
        topic_edges = list(
            (
                await db.execute(
                    select(KnowledgeRelation).where(
                        KnowledgeRelation.organization_id == organization_id,
                        KnowledgeRelation.source_type == entity_type,
                        KnowledgeRelation.source_id == entity_id,
                        KnowledgeRelation.target_type == "topic",
                    )
                )
            ).scalars().all()
        )
        if topic_edges:
            topic_ids_here = [e.target_id for e in topic_edges]
            peer_edges = list(
                (
                    await db.execute(
                        select(KnowledgeRelation).where(
                            KnowledgeRelation.organization_id == organization_id,
                            KnowledgeRelation.target_type == "topic",
                            KnowledgeRelation.target_id.in_(topic_ids_here),
                        )
                        .order_by(KnowledgeRelation.created_at.desc())
                        .limit(_MAX_NEIGHBORS * 3)
                    )
                ).scalars().all()
            )
            topic_names = {t.id: t.name for t in (await self._topics_by_ids(db, organization_id=organization_id, topic_ids=topic_ids_here)).values()}
            for edge in peer_edges:
                key = (edge.source_type, edge.source_id)
                if key == (entity_type, entity_id):
                    continue
                entry = neighbors.setdefault(
                    key, {"type": key[0], "id": key[1], "title": None, "relations": []}
                )
                entry["relations"].append(
                    {
                        "relation": "concerns",
                        "direction": "via_topic",
                        "edge_id": edge.id,
                        "topic": topic_names.get(edge.target_id),
                    }
                )
        if not neighbors:
            return {
                "entity": {"type": entity_type, "id": entity_id},
                "total": 0,
                "neighbors": [],
            }

        ordered_keys = sorted(neighbors, key=lambda k: (k[0], k[1]))[:limit]
        source_rows = list(
            (
                await db.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.organization_id == organization_id,
                        KnowledgeSource.source_type.in_({k[0] for k in ordered_keys}),
                        KnowledgeSource.source_id.in_({k[1] for k in ordered_keys}),
                    )
                )
            ).scalars().all()
        )
        source_map = {(s.source_type, s.source_id): s for s in source_rows}
        claim_rows = list(
            (
                await db.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.claim_type != "synthesis",
                    )
                    .order_by(KnowledgeClaim.valid_from.desc())
                    .limit(_MAX_CLAIM_SCAN)
                )
            ).scalars().all()
        )
        claims_by_source: dict[tuple[str, str], list[KnowledgeClaim]] = {}
        for claim in claim_rows:
            claims_by_source.setdefault((claim.subject_type, claim.subject_id), []).append(claim)
        neighbor_topic_edges = (
            await db.execute(
                select(KnowledgeRelation).where(
                    KnowledgeRelation.organization_id == organization_id,
                    KnowledgeRelation.target_type == "topic",
                    KnowledgeRelation.source_id.in_({k[1] for k in ordered_keys}),
                ).limit(_MAX_NEIGHBORS * 8)
            )
        ).scalars().all()
        topic_names = {
            t.id: t.name
            for t in (
                await self._topics_by_ids(
                    db,
                    organization_id=organization_id,
                    topic_ids=[e.target_id for e in neighbor_topic_edges],
                )
            ).values()
        }
        topics_by_key: dict[tuple[str, str], list[str]] = {}
        for edge in neighbor_topic_edges:
            name = topic_names.get(edge.target_id)
            if not name:
                continue
            topics_by_key.setdefault((edge.source_type, edge.source_id), []).append(name)

        neighbors_out: list[dict[str, Any]] = []
        for key in ordered_keys:
            source = source_map.get(key)
            if source is not None and not synthesis_engine._visible(
                access, _load_provenance(source.provenance_json)
            ):
                continue
            claims = claims_by_source.get(key, [])
            visible_claims = []
            for claim in claims[:8]:
                claim_source = source_map.get((claim.subject_type, claim.subject_id))
                if claim_source is not None and not synthesis_engine._visible(
                    access, _load_provenance(claim_source.provenance_json)
                ):
                    continue
                visible_claims.append(synthesis_engine._claim_shape(claim))
            neighbors_out.append(
                {
                    "type": key[0],
                    "id": key[1],
                    "title": source.title if source else neighbors[key]["title"],
                    "relations": neighbors[key]["relations"],
                    "claims": visible_claims,
                    "topics": sorted(set(topics_by_key.get(key, []))),
                }
            )
        return {
            "entity": {"type": entity_type, "id": entity_id},
            "total": len(neighbors_out),
            "neighbors": neighbors_out,
            "scope": "org" if access.org_wide else "project",
        }

    # ------------------------------------------------------------------
    # 4.4.3 — change intelligence
    # ------------------------------------------------------------------

    async def changes(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        days: int = 7,
        limit: int = _MAX_CHANGES,
    ) -> dict[str, Any]:
        """What changed in our understanding recently: for every topic whose
        current understanding (or evidence) moved inside the window, show
        old -> new, at what time, and which source families forced it."""
        access = await self._access(db, organization_id=organization_id, user=user)
        days = max(1, min(days, 365))
        cutoff = ensure_aware(now_utc()) - timedelta(days=days)
        limit = max(1, min(limit, _MAX_CHANGES))

        scanned = await self._scan_topics(
            db, organization_id=organization_id, access=access,
            include_superseded=True,
        )
        results: list[dict[str, Any]] = []
        for topic_id, entry in scanned.items():
            topic = entry["topic"]
            evolution = await self._synthesis_evolution(
                db, organization_id=organization_id, topic_id=topic_id, access=access
            )
            recent_evidence = [
                c for c in entry["claims"]
                if ensure_aware(c.valid_from) >= cutoff
            ]
            events: list[dict[str, Any]] = []
            families = sorted({c.subject_type for c in recent_evidence})
            if recent_evidence:
                source_map = entry["sources"]
                newest_claim = max(
                    recent_evidence, key=lambda c: ensure_aware(c.valid_from)
                )
                source = source_map.get(
                    (newest_claim.subject_type, newest_claim.subject_id)
                )
                events.append(
                    {
                        "kind": "new_evidence",
                        "at": ensure_aware(newest_claim.valid_from).isoformat(),
                        "family": newest_claim.subject_type,
                        "statement": _snippet(newest_claim.object_text, 220),
                        "source_title": source.title if source else None,
                        "claim_id": newest_claim.id,
                    }
                )
            for index, claim in enumerate(evolution):
                if ensure_aware(claim.valid_from) < cutoff:
                    continue
                prior = evolution[index - 1] if index > 0 else None
                change_signal = bool(_CHANGE_SIGNAL.search(claim.object_text)) or (
                    prior is not None and prior.object_text != claim.object_text
                )
                if not change_signal:
                    continue
                events.append(
                    {
                        "kind": "understanding",
                        "at": ensure_aware(claim.valid_from).isoformat(),
                        "from": _snippet(prior.object_text, 400) if prior else None,
                        "to": _snippet(claim.object_text, 400),
                        "claim_id": claim.id,
                        "supersedes_claim_id": prior.id if prior else None,
                    }
                )
            if not events:
                continue
            events.sort(key=lambda e: e["at"])
            results.append(
                {
                    "topic": {"id": topic.id, "name": _clean_topic_name(topic.name)},
                    "families": families,
                    "events": events[-6:],
                }
            )
        results.sort(
            key=lambda r: max(
                (e["at"] for e in r["events"]), key=lambda stamp: stamp
            ),
            reverse=True,
        )
        return {
            "window_days": days,
            "total": len(results),
            "topic_changes": results[:limit],
            "scope": "org" if access.org_wide else "project",
        }

    # ------------------------------------------------------------------
    # 4.4.3 — impact analysis
    # ------------------------------------------------------------------

    async def impact(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """If this knowledge changes, what else changes? Answers by walking
        the entity set behind a topic and the typed edges that anchor it, plus
        dependent knowledge claims that quote the same facts."""
        topic = await self._topic_by_name(
            db, organization_id=organization_id, topic_name=topic_name
        )
        if topic is None:
            return None
        access = await self._access(db, organization_id=organization_id, user=user)
        evidence = await synthesis_engine._collect_evidence(
            db, organization_id=organization_id, topic=topic, access=access
        )
        if not evidence:
            return None

        entity_keys = {
            (c.subject_type, c.subject_id) for c in evidence
        } | {("topic", topic.id)}
        neighbors: dict[tuple[str, str], list[str]] = {}
        batch = list(entity_keys)[:_MAX_IMPACT_ENTITIES]
        for etype, eid in batch:
            edges = list(
                (
                    await db.execute(
                        select(KnowledgeRelation).where(
                            KnowledgeRelation.organization_id == organization_id,
                            (
                                (KnowledgeRelation.source_type == etype)
                                & (KnowledgeRelation.source_id == eid)
                            )
                            | (
                                (KnowledgeRelation.target_type == etype)
                                & (KnowledgeRelation.target_id == eid)
                            ),
                        ).limit(_MAX_IMPACT_ENTITIES)
                    )
                ).scalars().all()
            )
            for edge in edges:
                if (edge.source_type, edge.source_id) == (etype, eid):
                    key = (edge.target_type, edge.target_id)
                else:
                    key = (edge.source_type, edge.source_id)
                if key in entity_keys:
                    continue
                neighbors.setdefault(key, []).append(edge.relation_type)

        source_map = await synthesis_engine._sources_for(
            db, organization_id=organization_id, claims=evidence
        )
        dependent: list[dict[str, Any]] = []
        needles = {topic.name.lower(), *(a.lower() for a in _json_loads(topic.aliases_json, []))}
        candidates = list(
            (
                await db.execute(
                    select(KnowledgeClaim)
                    .where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.claim_type != "synthesis",
                        KnowledgeClaim.status != "superseded",
                    )
                    .order_by(KnowledgeClaim.valid_from.desc())
                    .limit(_MAX_CLAIM_SCAN)
                )
            ).scalars().all()
        )
        dep_sources = list(
            (
                await db.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.organization_id == organization_id,
                        KnowledgeSource.source_type.in_({c.subject_type for c in candidates}),
                    )
                )
            ).scalars().all()
        )
        dep_source_map = {(s.source_type, s.source_id): s for s in dep_sources}
        for claim in candidates:
            source = dep_source_map.get((claim.subject_type, claim.subject_id))
            if source is None or not synthesis_engine._visible(
                access, _load_provenance(source.provenance_json)
            ):
                continue
            hay = f"{source.title} {claim.object_text}".lower()
            if not any(needle in hay for needle in needles):
                continue
            dependent.append(
                {
                    "claim_id": claim.id,
                    "subject_type": claim.subject_type,
                    "subject_id": claim.subject_id,
                    "statement": _snippet(claim.object_text, 220),
                    "source_title": source.title,
                    "authority_level": claim.authority_level,
                    "valid_from": ensure_aware(claim.valid_from).isoformat(),
                    "in_topic_evidence": (claim.subject_type, claim.subject_id) in entity_keys,
                }
            )
        dependent.sort(key=lambda d: (-d["authority_level"], d["valid_from"]))
        dependent = dependent[:_MAX_IMPACT_CLAIMS]

        family_count: dict[str, int] = {}
        impacted: list[dict[str, Any]] = []
        for key, relations in neighbors.items():
            family_count[key[0]] = family_count.get(key[0], 0) + 1
            impacted.append(
                {
                    "type": key[0],
                    "id": key[1],
                    "relations": sorted(set(relations)),
                }
            )
        impacted = impacted[:_MAX_IMPACT_ENTITIES]

        sources_evidence = [
            {
                "type": c.subject_type,
                "id": c.subject_id,
                "title": (
                    source_map.get((c.subject_type, c.subject_id)).title
                    if source_map.get((c.subject_type, c.subject_id)) else None
                ),
                "excerpt": _snippet(c.object_text, 200),
                "authority_level": c.authority_level,
            }
            for c in evidence[:_MAX_ANSWER_EVIDENCE]
        ]
        aliases = _json_loads(topic.aliases_json, [])
        return {
            "topic": {"id": topic.id, "name": _clean_topic_name(topic.name), "aliases": aliases},
            "evidence": {
                "total": len(evidence),
                "sources": sources_evidence,
            },
            "affected": {
                "total": len(impacted),
                "by_family": {
                    family: {
                        "count": family_count[family],
                        "entities": [
                            {"id": x["id"], "relations": x["relations"]}
                            for x in impacted if x["type"] == family
                        ],
                    }
                    for family in sorted(family_count)
                },
            },
            "dependent_knowledge": {
                "total": len(dependent),
                "claims": dependent,
            },
            "scope": "org" if access.org_wide else "project",
        }

    # ------------------------------------------------------------------
    # 4.4.4 — gap & uncertainty intelligence
    # ------------------------------------------------------------------

    async def gaps(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        limit: int = _MAX_GAPS,
    ) -> dict[str, Any]:
        """What the company doesn't know it doesn't know: stale authoritative
        knowledge, unresolved conflicts, undocumented processes, knowledge
        without an accountable owner."""
        access = await self._access(db, organization_id=organization_id, user=user)
        scanned = await self._scan_topics(
            db, organization_id=organization_id, access=access
        )
        gaps: list[dict[str, Any]] = []

        for topic_id, entry in scanned.items():
            topic = entry["topic"]
            claims = entry["claims"]
            source_map = entry["sources"]
            active = [c for c in claims if c.status != "superseded"]
            if not active:
                continue
            families = {c.subject_type for c in active}
            contradictions = synthesis_engine._detect_contradictions(active)
            latest_authority = max((c.authority_level for c in active), default=1)
            newest_source = max(
                (source_map.get((c.subject_type, c.subject_id)) for c in active),
                key=lambda s: ensure_aware(s.source_updated_at)
                if s and s.source_updated_at else now_utc(),
                default=None,
            )
            freshness = newest_source.freshness_label if newest_source else "stale"

            if latest_authority >= 4 and freshness not in _FRESH_OK:
                gaps.append(
                    {
                        "kind": "stale",
                        "topic": {"id": topic.id, "name": _clean_topic_name(topic.name)},
                        "reason": (
                            f"authoritative knowledge ({_AUTHORITY_LABELS.get(latest_authority)}) "
                            f"is {freshness} — last verified "
                            f"{ensure_aware(newest_source.last_verified_at).date().isoformat() if newest_source and newest_source.last_verified_at else 'never'}"
                        ),
                        "confidence": 0.85 if freshness == "stale" else 0.7,
                        "severity": "high" if freshness == "stale" else "medium",
                        "authority_level": latest_authority,
                        "evidence": len(active),
                    }
                )

            unresolved = [
                p for p in contradictions if p["resolution"] == "newer valid_from"
            ]
            if unresolved:
                pair = unresolved[0]
                gaps.append(
                    {
                        "kind": "contradiction",
                        "topic": {"id": topic.id, "name": _clean_topic_name(topic.name)},
                        "reason": (
                            f"{pair['facet_label']} {pair['value_a']} vs {pair['value_b']} — "
                            f"equal authority, resolved by recency; the loser may be stale"
                        ),
                        "confidence": 0.7,
                        "severity": "medium",
                        "pair_ids": [pair["claim_a"], pair["claim_b"]],
                        "evidence": len(active),
                    }
                )

            patterns = any(c.subject_type == "pattern" for c in active)
            documented = bool(families & _DOCUMENT_FAMILIES)
            if patterns and not documented:
                gaps.append(
                    {
                        "kind": "undocumented_process",
                        "topic": {"id": topic.id, "name": _clean_topic_name(topic.name)},
                        "reason": (
                            "repeated observations signal an operational process "
                            "that has no documented procedure (no document, wiki, "
                            "policy, sop or template evidence)"
                        ),
                        "confidence": 0.75,
                        "severity": "medium",
                        "evidence": len(active),
                    }
                )

            if latest_authority >= 3 and len(families) == 1 and not families & _DOCUMENT_FAMILIES:
                gaps.append(
                    {
                        "kind": "thin_evidence",
                        "topic": {"id": topic.id, "name": _clean_topic_name(topic.name)},
                        "reason": (
                            f"understanding rests on a single family ({sorted(families)[0]}) "
                            "with no cross-validation"
                        ),
                        "confidence": 0.6,
                        "severity": "low",
                        "evidence": len(active),
                    }
                )
        gaps.sort(key=lambda g: (g["severity"] != "high", g["severity"] != "medium", g["confidence"]))
        gaps = gaps[: min(limit, _MAX_GAPS)]
        kinds = sorted({g["kind"] for g in gaps})
        return {
            "total": len(gaps),
            "kinds": kinds,
            "gaps": gaps,
            "shortage_total": len([
                g for g in gaps if g["kind"] == "stale"
            ]),
            "scope": "org" if access.org_wide else "project",
        }

    # ------------------------------------------------------------------
    # 4.4.6 — explainable confidence
    # ------------------------------------------------------------------

    async def confidence(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        claim_id: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """Why a claim is as confident as it is: authority, evidence strength,
        corroboration, agreement, consistency minus contradiction, and the
        penalties (staleness, conflicts) — every factor explained."""
        claim = (
            await db.execute(
                select(KnowledgeClaim).where(
                    KnowledgeClaim.organization_id == organization_id,
                    KnowledgeClaim.id == claim_id,
                )
            )
        ).scalar_one_or_none()
        if claim is None:
            return None
        access = await self._access(db, organization_id=organization_id, user=user)
        if not await synthesis_engine._claim_visible(
            db, organization_id=organization_id, claim=claim, access=access
        ):
            return None
        evidence_rows = list(
            (
                await db.execute(
                    select(KnowledgeEvidence).where(
                        KnowledgeEvidence.organization_id == organization_id,
                        KnowledgeEvidence.claim_id == claim.id,
                    ).limit(_MAX_ANSWER_EVIDENCE * 2)
                )
            ).scalars().all()
        )
        keys = {(e.source_type, e.source_id) for e in evidence_rows}
        if claim.subject_type != "topic":
            keys.add((claim.subject_type, claim.subject_id))
        sources = await synthesis_engine._sources_for_map(db, organization_id, keys)
        freshness_values = [
            s.freshness_score or 0 for s in sources.values() if s.freshness_score is not None
        ]
        newest_freshness = max(freshness_values, default=0) / 100.0
        contradicted = [e for e in evidence_rows if e.role == "contradicted"]
        auth_norm = _AUTHORITY_NORM.get(claim.authority_level, 0.25)
        evidence_count = len(evidence_rows)
        corroboration = min(1.0, evidence_count / 3.0)
        n_agree = max(0, evidence_count - len(contradicted))
        agreement = n_agree / evidence_count if evidence_rows else 0.0
        consistency = max(0.0, 1.0 - len(contradicted) / max(1, evidence_count))
        source_diversity = min(1.0, len({e.source_type for e in evidence_rows}) / 3.0)
        staleness_penalty = 0.0 if newest_freshness >= 0.4 else (0.4 - newest_freshness)
        stale_label = "no" if newest_freshness >= 0.4 else "yes"

        factors = [
            {
                "name": "authority",
                "value": round(auth_norm, 3),
                "weight": 0.35,
                "sign": "+",
                "detail": f"{_AUTHORITY_LABELS.get(claim.authority_level, 'unverified')} source ({claim.authority_level})",
            },
            {
                "name": "evidence strength",
                "value": round(corroboration, 3),
                "weight": 0.25,
                "sign": "+",
                "detail": f"{len(evidence_rows)} supporting evidence rows",
            },
            {
                "name": "freshness",
                "value": round(newest_freshness, 3),
                "weight": 0.25,
                "sign": "+",
                "detail": f"newest source freshness {stale_label}",
            },
            {
                "name": "agreement",
                "value": round(agreement, 3),
                "weight": 0.15,
                "sign": "+",
                "detail": f"{n_agree}/{len(evidence_rows)} rows agree",
            },
            {
                "name": "consistency",
                "value": round(consistency, 3),
                "weight": 0.0,
                "sign": "+",
                "detail": f"{len(contradicted)} contradicting rows",
            },
            {
                "name": "source diversity",
                "value": round(source_diversity, 3),
                "weight": 0.0,
                "sign": "+",
                "detail": f"{len({e.source_type for e in evidence_rows})} distinct source families",
            },
            {
                "name": "staleness penalty",
                "value": round(staleness_penalty, 3),
                "weight": 0.0,
                "sign": "-",
                "detail": "applied when freshness < 0.4",
            },
        ]
        computed = round(
            0.35 * auth_norm
            + 0.25 * newest_freshness
            + 0.25 * min(1.0, sum(1 for _ in evidence_rows) / 3.0)
            + 0.15 * agreement,
            3,
        )
        return {
            "claim_id": claim.id,
            "confidence": computed,
            "recorded_confidence": claim.confidence,
            "factors": factors,
            "explanation": (
                f"Confidence {computed} = 0.35*authority({auth_norm:.2f}) "
                f"+ 0.25*freshness({newest_freshness:.2f}) "
                f"+ 0.25*evidence strength + 0.15*agreement — "
                f"penalized by {len(contradicted)} contradiction(s) and "
                f"{'staleness' if stale_label == 'yes' else 'no staleness'}."
            ),
        }

    # ------------------------------------------------------------------
    # 4.4.6 — ownership intelligence
    # ------------------------------------------------------------------

    async def ownership(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """Who owns this knowledge: the author of the highest-authority,
        most recent source behind the topic's current understanding."""
        topic = await self._topic_by_name(
            db, organization_id=organization_id, topic_name=topic_name
        )
        if topic is None:
            return None
        access = await self._access(db, organization_id=organization_id, user=user)
        evidence = await synthesis_engine._collect_evidence(
            db, organization_id=organization_id, topic=topic, access=access
        )
        if not evidence:
            return None
        sources = await synthesis_engine._sources_for(
            db, organization_id=organization_id, claims=evidence
        )
        candidate_sources = [
            s for c in evidence
            if (s := sources.get((c.subject_type, c.subject_id))) is not None
            and c.status != "superseded"
        ]
        if not candidate_sources:
            return None
        best = max(
            candidate_sources,
            key=lambda s: (
                s.authority_level,
                ensure_aware(s.source_updated_at).timestamp()
                if s.source_updated_at else ensure_aware(s.ingested_at).timestamp(),
            ),
        )
        author_sources = [
            s for s in candidate_sources
            if _load_provenance(s.provenance_json).get("author_id")
        ]
        owner_source = max(
            author_sources,
            key=lambda s: (
                s.authority_level,
                ensure_aware(s.source_updated_at).timestamp()
                if s.source_updated_at else ensure_aware(s.ingested_at).timestamp(),
            ),
        ) if author_sources else None
        owner_id = None
        if owner_source is not None:
            owner_id = _load_provenance(owner_source.provenance_json).get("author_id")
        return {
            "topic": {"id": topic.id, "name": _clean_topic_name(topic.name)},
            "owner": {
                "employee_id": owner_id,
                "resolved": bool(owner_id),
            },
            "source": {
                "type": best.source_type,
                "id": best.source_id,
                "title": best.title,
            },
            "authority": {
                "level": best.authority_level,
                "label": _AUTHORITY_LABELS.get(best.authority_level, "unverified"),
            },
            "last_verified_at": (
                ensure_aware(best.last_verified_at).isoformat()
                if best.last_verified_at else None
            ),
            "freshness_label": best.freshness_label,
            "evidence": len(evidence),
        }

    # ------------------------------------------------------------------
    # 4.4.6 — 4F.4 universal ownership & responsibility questions
    # ------------------------------------------------------------------

    async def _resolve_owned_object(
        self, db: AsyncSession, *, organization_id: str, question: str, access: Any,
    ) -> Optional[tuple[str, str, str]]:
        """Best-effort bounded resolution of the object in a responsibility
        question (project/customer/partner/budget/unit by name overlap)."""
        q_tokens = tokens(question)
        best: Optional[tuple[int, str, str, str]] = None
        try:
            from app.models.customer import Customer
            from app.models.finance import Budget
            from app.models.partner import Partner
            from app.models.project import Project
            from app.models.team import Team
        except Exception:
            return None
        for model, otype, name_col in (
            (Project, "project", "name"),
            (Customer, "customer", "name"),
            (Partner, "partner", "name"),
            (Budget, "budget", "name"),
            (Team, "unit", "name"),
        ):
            try:
                rows = (
                    await db.execute(
                        select(model.id, getattr(model, name_col))
                        .where(model.organization_id == organization_id)
                        .limit(50)
                    )
                ).all()
            except Exception:
                continue
            for rid, name in rows:
                label = str(name or "")[:255]
                overlap = len(q_tokens & tokens(label))
                if not overlap:
                    continue
                if (not getattr(access, "org_wide", False)
                        and otype == "project"
                        and rid not in getattr(access, "project_ids", frozenset())):
                    continue
                if best is None or overlap > best[0]:
                    best = (overlap, otype, rid, label)
        if best is None:
            return None
        return best[1], best[2], best[3]

    async def _ownership_query(
        self, db: AsyncSession, *, organization_id: str,
        question: str, user: Any, intent: str,
    ) -> dict[str, Any]:
        """Slice 4F.4 universal ownership answers: current owner, history,
        continuity and advisory findings - all bounded, all read-only."""
        from app.intelligence.ownership_engine import ownership_engine

        access = await self._access(db, organization_id=organization_id, user=user)
        scope_label = "org" if access.org_wide else "project"

        if intent == "responsibility_gaps":
            signals = await ownership_engine.signals(
                db, organization_id=organization_id, kind="gap",
                status="open", limit=10,
            )
            items = signals["signals"]
            lines = [
                f"{s['object_name']} ({s['object_type']}) - {s['detail'][:140]}"
                for s in items
            ]
            answer = (
                f"{len(items)} responsibility gap{'s' if len(items) != 1 else ''} "
                f"open (owner left or never assigned). "
                f"Responsibilities are never auto-assigned; " +
                f"leadership reviews: " + ("; ".join(lines) if lines else "none.")
                if items else "No open responsibility gaps - every recorded "
                "ownership window has an active owner."
            )
            return {
                "question": question, "intent": intent, "kind": "responsibility_gaps",
                "total": len(items), "answers": items,
                "answer": answer,
                "scope": scope_label, "generated_at": _utcnow_iso(),
            }

        concentration = False
        if intent == "continuity" and any(
            m in question.lower()
            for m in ("single point", "overloaded", "too many", "concentrat", "dependency risk")
        ):
            concentration = True
        if concentration or intent in ("single_point",):
            signals = await ownership_engine.signals(
                db, organization_id=organization_id, kind="single_point",
                status="open", limit=10,
            )
            items = signals["signals"]
            answer = (
                f"{len(items)} single-person dependency risk{'s' if len(items) != 1 else ''} "
                "flagged (an owner holding responsibilities with no backup - "
                "advisory only, never auto-changed): " +
                ("; ".join(f"{s['object_name']} - {s['detail'][:120]}" for s in items)
                 if items else "none.")
            )
            return {
                "question": question, "intent": intent, "kind": "single_point",
                "total": len(items), "answers": items,
                "answer": answer,
                "scope": scope_label, "generated_at": _utcnow_iso(),
            }

        resolved = await self._resolve_owned_object(
            db, organization_id=organization_id, question=question, access=access)
        if resolved is None and intent not in ("responsibility_history",):
            return {
                "question": question, "intent": intent, "total": 0,
                "answers": [], "scope": scope_label,
                "answer": (
                    "I could not identify which project, customer, partner, "
                    "budget or team this question is about. Ask e.g. \"who is "
                    "responsible for the Payments Platform?\""
                ),
                "generated_at": _utcnow_iso(),
            }

        if intent == "responsibility_history":
            if resolved is None:
                history: dict[str, Any] = {
                    "object_type": "?", "object_id": "?", "events": [], "total": 0,
                }
            else:
                history = await ownership_engine.history(
                    db, organization_id=organization_id,
                    object_type=resolved[0], object_id=resolved[1], access=access,
                    limit=10,
                )
            events = history.get("events", [])
            lines = []
            for ev in events:
                if ev.get("action") == "assigned":
                    lines.append(f"assigned to {ev['to_owner_label']} "
                                 f"({_clean_topic_name(ev['occurred_at'].strftime('%Y-%m-%d') if ev.get('occurred_at') else '')})")
                elif ev.get("action") == "transferred":
                    lines.append(f"transferred from {ev.get('from_owner_label')} "
                                 f"to {ev.get('to_owner_label')}")
                elif ev.get("action") == "closed":
                    lines.append(f"closed (was {ev.get('from_owner_label')})")
                else:
                    lines.append(f"{ev.get('action')} ({ev.get('to_owner_label') or ev.get('from_owner_label')})")
            answer = (
                f"Responsibility history for {resolved[2] if resolved else '? '}- "
                + ("; ".join(lines) if lines else "no recorded windows yet.")
            )
            return {
                "question": question, "intent": intent, "kind": "responsibility_history",
                "total": len(events), "answers": events,
                "answer": answer,
                "scope": scope_label, "generated_at": _utcnow_iso(),
            }

        current = await ownership_engine.current(
            db, organization_id=organization_id,
            object_type=resolved[0], object_id=resolved[1], access=access, limit=20,
        )
        primary = current.get("primary")
        if primary is None:
            answer = (
                f"No declared owner for {current.get('object_name') or resolved[2]}. "
                "Assign one explicitly - VCOS never invents owners."
            )
        else:
            since = (
                primary.get("declared_start", "").strftime("%Y-%m-%d")
                if primary.get("declared_start") else "?"
            )
            backup = (
                f", backed up by {primary['backup_owner_label']}"
                if primary.get("backup_owner_id") else ""
            )
            answer = (
                f"{primary['owner_label']} is responsible for "
                f"{current.get('object_name') or resolved[2]} "
                f"({primary['responsibility_type']}, since {since}{backup})."
            )
        if intent == "continuity":
            continuity = await ownership_engine.continuity(
                db, organization_id=organization_id,
                object_type=resolved[0], object_id=resolved[1], access=access,
            )
            if continuity.get("backup"):
                answer = (
                    f"If {continuity['primary']['owner_label']} is unavailable, "
                    f"{continuity['backup']['owner_label']} steps in as backup "
                    f"for {continuity.get('object_name')}."
                )
            elif continuity.get("delegation"):
                answer = answer + " Governed 4C delegation exists at this scope."
            else:
                answer = answer + " No backup or governed delegation is set."
        return {
            "question": question, "intent": intent, "kind": "ownership",
            "total": len(current.get("relationships", [])),
            "answers": current.get("relationships", []),
            "answer": answer,
            "scope": scope_label, "generated_at": _utcnow_iso(),
        }

    # ------------------------------------------------------------------
    # 4.4.6 — knowledge health
    # ------------------------------------------------------------------

    async def health(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
    ) -> dict[str, Any]:
        """The organization's knowledge health: seven bars, each explainable,
        plus what is dragging it down."""
        access = await self._access(db, organization_id=organization_id, user=user)
        scanned = await self._scan_topics(
            db, organization_id=organization_id, access=access
        )
        if not scanned:
            return {
                "total_topics": 0,
                "bars": [],
                "why_weak": [],
                "scope": "org" if access.org_wide else "project",
            }

        coverage_ok = 0
        freshness_ok = documented_ok = multi_family_ok = 0
        contradiction_free = 0
        owned_topics = 0
        evidence_counts: list[int] = []
        stale_claims: list[dict[str, Any]] = []
        low_confidence_topics: list[dict[str, Any]] = []
        unresolved_conflicts: list[dict[str, Any]] = []

        for topic_id, entry in scanned.items():
            topic = entry["topic"]
            claims = [c for c in entry["claims"] if c.status != "superseded"]
            source_map = entry["sources"]
            families = {c.subject_type for c in claims}
            evidence_counts.append(len(claims))
            current = await self._synthesis_current_claim(
                db, organization_id=organization_id, topic_id=topic_id, access=access
            )
            if current is not None:
                coverage_ok += 1
            freshness_ok += 1
            contradictions = synthesis_engine._detect_contradictions(claims)
            if not contradictions:
                contradiction_free += 1
            unresolved = [p for p in contradictions if p["resolution"] == "newer valid_from"]
            if unresolved:
                pair = unresolved[0]
                unresolved_conflicts.append(
                    {
                        "topic": topic.name,
                        "facet": pair["facet_label"],
                        "values": [pair["value_a"], pair["value_b"]],
                    }
                )
            if families & _DOCUMENT_FAMILIES:
                documented_ok += 1
            if len(families) >= 3:
                multi_family_ok += 1
            newest_source = max(
                (source_map.get((c.subject_type, c.subject_id)) for c in claims),
                key=lambda s: ensure_aware(s.source_updated_at)
                if s and s.source_updated_at else now_utc(),
                default=None,
            )
            if newest_source and newest_source.freshness_label not in _FRESH_OK:
                freshness_ok -= 1
                if max((c.authority_level for c in claims), default=0) >= 4:
                    stale_claims.append(
                        {
                            "topic": topic.name,
                            "freshness": newest_source.freshness_label,
                            "title": newest_source.title,
                        }
                    )
            provenance_author = None
            for c in claims:
                source = source_map.get((c.subject_type, c.subject_id))
                if source and _load_provenance(source.provenance_json).get("author_id"):
                    provenance_author = True
                    break
            if provenance_author:
                owned_topics += 1
            if current and current.confidence and current.confidence < 0.5:
                low_confidence_topics.append(
                    {"topic": topic.name, "confidence": current.confidence}
                )
        low_confidence_topics.sort(key=lambda x: x["confidence"])
        stale_claims.sort(key=lambda x: x["freshness"])
        total = len(scanned)
        avg_evidence = sum(evidence_counts) / total if total else 0.0
        bars = [
            {
                "name": "coverage",
                "value": round(coverage_ok / total * 100),
                "label": "healthy",
                "detail": f"{total} active knowledge topics synthesized",
            },
            {
                "name": "freshness",
                "value": round(freshness_ok / total * 100),
                "label": "healthy" if freshness_ok / total >= 0.8 else "attention",
                "detail": f"{freshness_ok}/{total} topics backed by recent sources",
            },
            {
                "name": "evidence_quality",
                "value": round(min(100, avg_evidence * 10)),
                "label": "healthy" if avg_evidence >= 3 else "attention",
                "detail": f"{avg_evidence:.1f} evidence claims per topic on average",
            },
            {
                "name": "contradiction_resolution",
                "value": round(contradiction_free / total * 100),
                "label": "healthy" if contradiction_free / total >= 0.9 else "attention",
                "detail": f"{contradiction_free}/{total} topics free of facet conflicts",
            },
            {
                "name": "ownership",
                "value": round(owned_topics / total * 100),
                "label": "healthy" if owned_topics / total >= 0.8 else "attention",
                "detail": f"{owned_topics}/{total} topics have an accountable author",
            },
            {
                "name": "documentation",
                "value": round(documented_ok / total * 100),
                "label": "healthy" if documented_ok / total >= 0.6 else "attention",
                "detail": f"{documented_ok}/{total} topics covered by a document, wiki, policy, sop or template",
            },
            {
                "name": "cross_team_consistency",
                "value": round(multi_family_ok / total * 100),
                "label": "healthy" if multi_family_ok / total >= 0.3 else "attention",
                "detail": f"{multi_family_ok}/{total} topics corroborated by 3+ source families",
            },
        ]
        why_weak: list[dict[str, Any]] = []
        if stale_claims:
            why_weak.append(
                {
                    "reason": "critical knowledge is stale",
                    "details": stale_claims[:_MAX_GAPS_PER_KIND],
                }
            )
        if low_confidence_topics:
            why_weak.append(
                {
                    "reason": "understanding rests on uncertain knowledge",
                    "details": low_confidence_topics[:_MAX_GAPS_PER_KIND],
                }
            )
        if unresolved_conflicts:
            why_weak.append(
                {
                    "reason": "authoritative conflicts remain unresolved",
                    "details": unresolved_conflicts[:_MAX_GAPS_PER_KIND],
                }
            )
        covered = coverage_ok
        if covered < total:
            why_weak.append(
                {
                    "reason": f"{total - covered} topics lack synthesized understanding",
                    "details": [],
                }
            )
        return {
            "total_topics": total,
            "bars": bars,
            "health_score": round(sum(b["value"] for b in bars) / len(bars)),
            "why_weak": why_weak,
            "scope": "org" if access.org_wide else "project",
        }

    # ------------------------------------------------------------------
    # 4.4.7 — recommendations (persisted, exact-once)
    # ------------------------------------------------------------------

    async def recommendations(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        limit: int = _MAX_RECOMMENDATIONS,
    ) -> dict[str, Any]:
        """Evaluated, persisted, evidence-backed recommendations.

        Materialization is exact-once: a recommendation is keyed by a stable
        fingerprint; re-running with the same conditions refreshes it,
        conditions that clear move the row to ``resolved``. Nothing is ever
        invented — every recommendation cites the claims it is based on.
        """
        access = await self._access(db, organization_id=organization_id, user=user)
        scanned = await self._scan_topics(
            db, organization_id=organization_id, access=access
        )
        materialized: list[dict[str, Any]] = []
        current_fingerprints: set[tuple[str, str]] = set()

        for topic_id, entry in scanned.items():
            topic = entry["topic"]
            claims = [c for c in entry["claims"] if c.status != "superseded"]
            source_map = entry["sources"]
            families = {c.subject_type for c in claims}
            contradictions = synthesis_engine._detect_contradictions(claims)
            unresolved = [p for p in contradictions if p["resolution"] == "newer valid_from"]
            latest_authority = max((c.authority_level for c in claims), default=1)
            newest_source = max(
                (source_map.get((c.subject_type, c.subject_id)) for c in claims),
                key=lambda s: ensure_aware(s.source_updated_at)
                if s and s.source_updated_at else now_utc(),
                default=None,
            )
            freshness = newest_source.freshness_label if newest_source else "stale"

            if latest_authority >= 4 and freshness not in _FRESH_OK:
                fingerprint = _fingerprint("stale_critical", topic.id)
                current_fingerprints.add(("stale_critical", fingerprint))
                materialized.append(
                    {
                        "kind": "stale_critical",
                        "fingerprint": fingerprint,
                        "reason": (
                            f"Critically authoritative knowledge on '{topic.name}' is {freshness}; "
                            "verify before it drives a decision."
                        ),
                        "confidence": 0.85 if freshness == "stale" else 0.7,
                        "risk": "high" if freshness == "stale" else "medium",
                        "evidence": [c.id for c in claims if c.authority_level >= 4][:12],
                        "entities": [
                            {"type": "topic", "id": topic.id, "name": _clean_topic_name(topic.name)}
                        ],
                    }
                )
            if unresolved:
                pair = unresolved[0]
                fingerprint = _fingerprint("conflict", topic.id, pair["claim_a"], pair["claim_b"])
                current_fingerprints.add(("conflict", fingerprint))
                materialized.append(
                    {
                        "kind": "conflict",
                        "fingerprint": fingerprint,
                        "reason": (
                            f"'{topic.name}': {pair['facet_label']} {pair['value_a']} vs "
                            f"{pair['value_b']} has equal-authority sources; the losing side "
                            f"('{pair['value_b']}') may be stale documentation."
                        ),
                        "confidence": 0.7,
                        "risk": "medium",
                        "evidence": [pair["claim_a"], pair["claim_b"]],
                        "entities": [
                            {"type": "topic", "id": topic.id, "name": _clean_topic_name(topic.name)}
                        ],
                    }
                )
            if any(c.subject_type == "pattern" for c in claims) and not families & _DOCUMENT_FAMILIES:
                fingerprint = _fingerprint("undocumented_process", topic.id)
                current_fingerprints.add(("undocumented_process", fingerprint))
                materialized.append(
                    {
                        "kind": "undocumented_process",
                        "fingerprint": fingerprint,
                        "reason": (
                            f"Repeated observations around '{topic.name}' signal an operational "
                            "process with no documented procedure — consider an SOP or runbook."
                        ),
                        "confidence": 0.75,
                        "risk": "medium",
                        "evidence": [
                            c.id for c in claims if c.subject_type == "pattern"
                        ][:12],
                        "entities": [
                            {"type": "topic", "id": topic.id, "name": _clean_topic_name(topic.name)}
                        ],
                    }
                )
            if len(families) >= 3 and len(claims) >= 4:
                fingerprint = _fingerprint("cross_functional", topic.id)
                current_fingerprints.add(("cross_functional", fingerprint))
                materialized.append(
                    {
                        "kind": "cross_functional",
                        "fingerprint": fingerprint,
                        "reason": (
                            f"'{topic.name}' is evidenced by {len(families)} source families "
                            f"({', '.join(sorted(families))}) — consider a cross-functional "
                            "review before it grows further."
                        ),
                        "confidence": 0.65,
                        "risk": "low",
                        "evidence": [c.id for c in claims][:12],
                        "entities": [
                            {"type": "topic", "id": topic.id, "name": _clean_topic_name(topic.name)}
                        ],
                    }
                )
        materialized = materialized[:limit]

        existing = list(
            (
                await db.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == organization_id,
                    ).order_by(KnowledgeRecommendation.created_at.desc())
                    .limit(_MAX_RECOMMENDATIONS * 2)
                )
            ).scalars().all()
        )
        by_fingerprint: dict[tuple[str, str], KnowledgeRecommendation] = {
            (r.kind, r.fingerprint): r for r in existing
        }
        now = now_utc()
        for row in existing:
            if row.status != "active":
                continue
            if row.lifecycle not in ("detected", "candidate"):
                continue  # 4E.5: a user-driven lifecycle decision is never overwritten
            if (row.kind, row.fingerprint) not in current_fingerprints:
                row.status = "resolved"
                row.resolved_at = now
        for item in materialized:
            key = (item["kind"], item["fingerprint"])
            row = by_fingerprint.get(key)
            if row is None:
                row = KnowledgeRecommendation(
                    organization_id=organization_id,
                    kind=item["kind"],
                    fingerprint=item["fingerprint"],
                    status="active",
                    lifecycle="detected",
                    reason=item["reason"],
                    confidence=item["confidence"],
                    risk=item["risk"],
                    evidence_json=json.dumps(item["evidence"]),
                    entities_json=json.dumps(item["entities"]),
                )
                db.add(row)
                await db.flush()
            else:
                if row.lifecycle not in ("detected", "candidate"):
                    continue  # user already steered this recommendation
                row.reason = item["reason"]
                row.confidence = item["confidence"]
                row.risk = item["risk"]
                row.evidence_json = json.dumps(item["evidence"])
                row.entities_json = json.dumps(item["entities"])
                row.status = "active"
                row.resolved_at = None
        await db.flush()
        active = list(
            (
                await db.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == organization_id,
                        KnowledgeRecommendation.status == "active",
                    ).order_by(KnowledgeRecommendation.updated_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
        )
        return {
            "total": len(active),
            "active_kinds": sorted({r.kind for r in active}),
            "recommendations": [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "status": r.status,
                    "fingerprint": r.fingerprint,
                    "lifecycle": r.lifecycle,
                    "reason": r.reason,
                    "confidence": r.confidence,
                    "risk": r.risk,
                    "evidence": _json_loads(r.evidence_json, []),
                    "entities": _json_loads(r.entities_json, []),
                    "created_at": ensure_aware(r.created_at).isoformat(),
                    "updated_at": ensure_aware(r.updated_at).isoformat(),
                }
                for r in active
            ],
            "scope": "org" if access.org_wide else "project",
        }

    # ------------------------------------------------------------------
    # 4.4.8 — universal knowledge query
    # ------------------------------------------------------------------

    async def _people_query(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        question: str,
        user: Any,
    ) -> dict[str, Any]:
        """Slice 4F.1 — universal people intelligence questions.

        Deterministic routing: "who works in X" -> unit members, "who
        reports to X" -> direct reports, "who manages X" -> reporting
        line, "org chart" -> the living chart, otherwise the governed
        directory. Every answer is governance-scoped and carries `scope`.
        """
        from app.people.people_engine import people_engine

        access = await self._access(db, organization_id=organization_id, user=user)
        lowered = question.lower().strip()
        scope_label = "org" if access.org_wide else "project"

        unit_phrase: Optional[str] = None
        for keyword in (
            "who works in", "who works at", "who is in", "who are in",
            "who belongs to", "who is part of", "who are the people in",
            "members of the", "which team members are in", "people in the",
        ):
            if keyword in lowered:
                unit_phrase = lowered.split(keyword, 1)[1]
                break
        if unit_phrase:
            import re as _re

            phrase = _re.sub(r"^(the|a|an|my)\s+", "", unit_phrase.strip().strip("?")).strip()
            probes = [phrase]
            for suffix in (" business unit", " department", " team", " unit"):
                if phrase.endswith(suffix):
                    probes.append(phrase[: -len(suffix)])
            for probe in probes:
                search = await people_engine.search(
                    db, organization_id=organization_id, access=access,
                    q=probe, limit=5,
                )
                units = search["teams"] + search["departments"]
                if not units:
                    continue
                unit = units[0]
                members = await people_engine.unit_members(
                    db, organization_id=organization_id, access=access,
                    unit_kind=unit["type"], unit_id=unit["id"],
                )
                names = [m["name"] for m in members["members"]]
                if names:
                    answer = (f"{members['unit_name']} has {len(names)} member(s) "
                              f"visible to you: {', '.join(names)}.")
                else:
                    answer = f"No members are visible to you in {members['unit_name']}."
                return {
                    "question": question,
                    "intent": "people",
                    "kind": "unit_members",
                    "total": len(names),
                    "answers": members["members"],
                    "answer": answer,
                    "scope": scope_label,
                    "generated_at": _utcnow_iso(),
                }

        target_phrase: Optional[str] = None
        direct_reports_question = False
        for keyword in ("who reports to", "who manages"):
            if keyword in lowered:
                target_phrase = lowered.split(keyword, 1)[1].strip().strip("?").strip()
                direct_reports_question = keyword == "who reports to"
                break
        if target_phrase:
            search = await people_engine.search(
                db, organization_id=organization_id, access=access,
                q=target_phrase, limit=10,
            )
            if search["people"]:
                person = search["people"][0]
                if direct_reports_question:
                    related = await people_engine.related_people(
                        db, organization_id=organization_id, access=access,
                        person_id=person["id"],
                    )
                    reports = [
                        r for r in related["relations"] if r["relation"] == "direct_report"
                    ]
                    names = [r["name"] for r in reports]
                    if names:
                        answer = (f"{person['name']} has {len(names)} visible direct "
                                  f"report(s): {', '.join(names)}.")
                    else:
                        answer = f"No direct reports are visible to you under {person['name']}."
                    return {
                        "question": question,
                        "intent": "people",
                        "kind": "direct_reports",
                        "total": len(names),
                        "answers": reports,
                        "answer": answer,
                        "scope": scope_label,
                        "generated_at": _utcnow_iso(),
                    }
                line = await people_engine.reporting_line(
                    db, organization_id=organization_id, access=access,
                    person_id=person["id"],
                )
                if line["manager_chain"]:
                    names = [m["name"] for m in line["manager_chain"]]
                    answer = f"{person['name']} reports to " + " reports to ".join(names) + "."
                else:
                    answer = f"{person['name']} has no visible manager."
                return {
                    "question": question,
                    "intent": "people",
                    "kind": "reporting_line",
                    "total": len(line["manager_chain"]),
                    "answers": line["manager_chain"],
                    "answer": answer,
                    "scope": scope_label,
                    "generated_at": _utcnow_iso(),
                }

        if any(k in lowered for k in ("org chart", "organisation chart", "organization chart")):
            chart = await people_engine.org_chart(
                db, organization_id=organization_id, access=access
            )
            names: list[str] = []

            def walk(roots: list[dict[str, Any]], depth: int = 0) -> None:
                for node in roots:
                    names.append(("  " * depth) + node["name"])
                    if depth < 4 and node.get("children"):
                        walk(node["children"], depth + 1)

            walk(chart["roots"])
            if not chart["roots"]:
                answer = "No org chart structure is visible to you."
            elif len(names) > 30:
                answer = (f"The visible org chart has {chart['nodes']} node(s); "
                          f"top-level teams: {', '.join(n for n in names if not n.startswith('  '))}.")
            else:
                answer = "\n".join(names)
            return {
                "question": question,
                "intent": "people",
                "kind": "org_chart",
                "total": chart["nodes"],
                "answers": chart["roots"],
                "answer": answer,
                "scope": scope_label,
                "generated_at": _utcnow_iso(),
            }

        directory = await people_engine.list_people(
            db, organization_id=organization_id, access=access, limit=20
        )
        names = [p["name"] for p in directory["people"]]
        if not names:
            answer = "No visible people in this organization."
        elif directory["total_visible"] > len(names):
            answer = (f"The organization has {directory['total_visible']} visible "
                      f"person(s); showing {len(names)}: {', '.join(names)}.")
        else:
            answer = f"The organization has {len(names)} person(s): {', '.join(names)}."
        return {
            "question": question,
            "intent": "people",
            "kind": "directory",
            "total": directory["total_visible"],
            "answers": directory["people"],
            "answer": answer,
            "scope": scope_label,
            "generated_at": _utcnow_iso(),
        }

    # ------------------------------------------------------------------ expertise (4F.2)

    async def _expertise_query(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        question: str,
        user: Any,
    ) -> dict[str, Any]:
        """Slice 4F.2 — universal skills & expertise questions.

        Deterministic routing: "who knows X" / "who is strongest in X" ->
        governed ranked experts; "what does <person> know" -> the person's
        evidence-derived expertise; a team/department mention scopes the
        search; otherwise the organization capability map answers "where does
        X expertise live". Results are governance-scoped and carry evidence
        counts — the score is always defensible.
        """
        from app.people.capability_engine import capability_engine
        from app.people.expertise_search import expertise_search
        from app.people.people_engine import people_engine

        access = await self._access(db, organization_id=organization_id, user=user)
        scope_label = "org" if access.org_wide else "project"
        lowered = question.lower().strip()

        # ---- "what does X know" / "what is X good at" -> person expertise
        person_phrase: Optional[str] = None
        for keyword in ("what does", "what is", "what are"):
            if keyword in lowered:
                person_phrase = lowered.split(keyword, 1)[1]
                break
        if person_phrase is not None:
            import re as _re

            stem = _re.split(
                r"\s+(?:knows?|understands?|good at|known for|best at|"
                r"proficient in|skilled in|expert in|expertise|skills?)\b",
                person_phrase, 1,
            )
            subject = stem[0].strip().strip("?").strip()
            predicate = stem[1].strip().strip("?").strip() if len(stem) > 1 else ""
            search = await people_engine.search(
                db, organization_id=organization_id, access=access,
                q=subject, limit=10,
            )
            if search["people"]:
                person = search["people"][0]
                result = await expertise_search.person_expertise(
                    db, organization_id=organization_id, person_id=person["id"],
                )
                if predicate.strip():
                    skill_result = await expertise_search.search(
                        db, organization_id=organization_id, access=access,
                        query=predicate.strip(), limit=5,
                    )
                    mine = [
                        e for e in result["expertise"]
                        if e["skill_id"] in {s["skill_id"] for s in skill_result["skills"]}
                    ]
                    if mine:
                        top = mine[0]
                        answer = (
                            f"{person['name']} has {top['skill_name']} expertise "
                            f"(score {top['score']:.0f}, confidence {top['confidence']:.2f}, "
                            f"{top['evidence_count']} evidence item(s))."
                        )
                    else:
                        answer = f"No evidence supports {person['name']} in that skill."
                    return {
                        "question": question,
                        "intent": "expertise",
                        "kind": "person_skill",
                        "total": len(mine),
                        "answers": mine,
                        "answer": answer,
                        "scope": scope_label,
                        "generated_at": _utcnow_iso(),
                    }
                names = [e["skill_name"] for e in result["expertise"][:5]]
                if names:
                    answer = (
                        f"{person['name']} has demonstrated expertise in: "
                        f"{', '.join(names)}."
                    )
                else:
                    answer = f"No evidence-derived expertise is visible for {person['name']}."
                return {
                    "question": question,
                    "intent": "expertise",
                    "kind": "person_expertise",
                    "total": result["total"],
                    "answers": result["expertise"],
                    "answer": answer,
                    "scope": scope_label,
                    "generated_at": _utcnow_iso(),
                }

        # ---- "who knows X [in the Y team]" -> governed ranked experts
        skill_phrase: Optional[str] = None
        for keyword in (
            "who knows", "who is the expert", "who are the experts",
            "who is an expert", "experts in", "expert in", "strongest in",
            "best at", "skilled in", "skilled at", "proficient in",
            "knows about", "does anyone know", "who can help with",
            "who could help", "works with", "expertise in",
        ):
            if keyword in lowered:
                skill_phrase = lowered.split(keyword, 1)[1]
                break
        if skill_phrase:
            scope_type: Optional[str] = None
            scope_id: Optional[str] = None
            import re as _re

            scope_match = _re.search(
                r"\b(in|on|within)\s+the\s+(.+?)\s+(team|department|business unit)\b",
                skill_phrase,
            )
            if scope_match:
                unit = scope_match.group(2).strip()
                scope_type = scope_match.group(3).replace(" ", "_")
                unit_search = await people_engine.search(
                    db, organization_id=organization_id, access=access,
                    q=unit, limit=5,
                )
                matched_unit = None
                if scope_type == "team" and unit_search["teams"]:
                    matched_unit = unit_search["teams"][0]
                elif scope_type == "department" and unit_search["departments"]:
                    matched_unit = unit_search["departments"][0]
                if scope_type == "business_unit":
                    scope_id = None
                if matched_unit is not None:
                    scope_id = matched_unit["id"]
                skill_phrase = skill_phrase.replace(scope_match.group(0), "")
            skills = await expertise_search.resolve_for_query(
                db, organization_id=organization_id, query=skill_phrase
            )
            if not skills:
                return {
                    "question": question,
                    "intent": "expertise",
                    "kind": "no_skill",
                    "total": 0,
                    "answers": [],
                    "answer": "No canonical skill matches that question.",
                    "scope": scope_label,
                    "generated_at": _utcnow_iso(),
                }
            result = await expertise_search.search(
                db, organization_id=organization_id, access=access,
                query=skill_phrase, scope_type=scope_type, scope_id=scope_id,
                limit=5, recent_only=("recent" in lowered),
            )
            experts = result["experts"]
            skill_label = skills[0].canonical_name
            if experts:
                top = experts[0]
                answer = (
                    f"{top['name']} appears to be the strongest visible "
                    f"{skill_label} expert (score {top['score']:.0f}, "
                    f"confidence {top['confidence']:.2f}, "
                    f"{top['evidence_count']} evidence item(s))."
                )
                if len(experts) > 1:
                    answer += " Also: " + ", ".join(e["name"] for e in experts[1:4]) + "."
            else:
                answer = f"No visible expertise is supported by evidence for {skill_label}."
            return {
                "question": question,
                "intent": "expertise",
                "kind": "experts",
                "total": result["total"],
                "answers": experts,
                "answer": answer,
                "scope": scope_label,
                "generated_at": _utcnow_iso(),
            }

        # ---- "where does our X expertise live / which team has X"
        if any(k in lowered for k in ("where does", "which team", "which department",
                                      "where is our", "does the company")):
            skills = await expertise_search.resolve_for_query(
                db, organization_id=organization_id, query=lowered
            )
            if skills:
                org_map = await capability_engine.org_map(
                    db, organization_id=organization_id
                )
                matched = [
                    c for c in org_map["capabilities"]
                    if c["skill_id"] in {s.id for s in skills}
                ]
                label = skills[0].canonical_name
                if matched:
                    top = max(matched, key=lambda c: c["avg_score"])
                    answer = (
                        f"{label} expertise exists across {top['member_count']} "
                        f"visible member(s) in the organization "
                        f"(average score {top['avg_score']:.0f})."
                    )
                else:
                    answer = f"No evidence-backed {label} expertise is visible."
                return {
                    "question": question,
                    "intent": "expertise",
                    "kind": "organization_map",
                    "total": len(matched),
                    "answers": matched,
                    "answer": answer,
                    "scope": "org" if access.org_wide else "project",
                    "generated_at": _utcnow_iso(),
                }

        return {
            "question": question,
            "intent": "expertise",
            "kind": "no_skill",
            "total": 0,
            "answers": [],
            "answer": "No skill in the question resolves to the canonical taxonomy.",
            "scope": scope_label,
            "generated_at": _utcnow_iso(),
        }

    async def _expertise_trust_query(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        question: str,
        user: Any,
    ) -> dict[str, Any]:
        """Slice 4F.3 — "why do you think X knows Y" / "can we trust X on Y".

        Deterministic: resolve the person, resolve the skill, then return the
        governed TRUST profile — what supports the claim (evidence trail with
        canonical sources), how reliable (confidence, outcome validation),
        how recent (freshness), what corroborates it (independent kinds/
        lineages) and what contradicts it (failed + expired evidence, never
        hidden). No person/skill resolves to nothing — the surface says so.
        """
        from app.people.expertise_search import expertise_search
        from app.people.people_engine import people_engine
        from app.intelligence.expertise_engine import expertise_engine

        access = await self._access(db, organization_id=organization_id, user=user)
        scope_label = "org" if access.org_wide else "project"
        lowered = question.lower().strip()

        # ---- resolve the person subject (deterministic, no LLM guessing)
        import re as _re

        subject: Optional[str] = None
        predicate = ""
        possessive = _re.search(
            r"\b([\w\s\.\-]+?)'s\s+([\w\-]+(?:\s+[\w\-]+)*)?\s*"
            r"(expertise|knowledge|skill)\b",
            lowered,
        )
        verb_markers = (
            r"\b(?:knows?(?: about)?|understands?|is an? (?:expert|specialist|pro)"
            r" in|is proficient in|is skilled in|is good at|is strong in|"
            r"expert in|expertise in|known for|rated for|trust(?:ed)?(?: for)?|"
            r"trust him with|trust her with|trust)\b"
        )
        if possessive:
            subject = possessive.group(1).strip()
            # the skill word(s) between the name and the noun go with the
            # predicate ("Py's Python expertise" -> "python expertise")
            predicate = " ".join(
                p for p in (possessive.group(2) or "", possessive.group(3)) if p
            )
            remainder = lowered[possessive.end():]
        else:
            verb_hit = _re.search(verb_markers, lowered)
            if verb_hit:
                subject = lowered[:verb_hit.start()].strip("? .!,-")
                predicate = lowered[verb_hit.end():].strip("? .!,")
            else:
                subject = lowered.strip("? .!,")
        predicate = _re.sub(
            r"^(?:\s*(?:the|for|on|in|with|about|regarding|currently|still|now|"
            r"like|that|their|his|her))+\s*", "", predicate,
        ).strip("? .!,")
        # disambiguate the name deterministically: drop leading words until a
        # visible person actually matches (never an LLM guess)
        subject_candidates: list[Optional[str]] = [None]
        if subject:
            words = subject.split()
            subject_candidates = [
                " ".join(words[i:])[:80] or None for i in range(min(len(words), 8))
            ] or [None]

        # ---- person lookup
        person: Optional[dict[str, Any]] = None
        for candidate in subject_candidates:
            if not candidate:
                continue
            found = await people_engine.search(
                db, organization_id=organization_id, access=access,
                q=candidate, limit=3,
            )
            if found["people"]:
                person = found["people"][0]
                break

        if person is None:
            markers = ("know", "expert", "skill", "expertise", "evidence",
                       "trust", "rate", "rated", "demonstrated")
            if not any(m in lowered for m in markers):
                return {
                    "question": question,
                    "intent": "expertise_trust",
                    "kind": "not_expertise",
                    "total": 0,
                    "answers": [],
                    "answer": ("That doesn't read as an expertise-trust question. "
                               "Ask e.g. \"why does <name> know <skill>?\" or "
                               "\"can we trust <name> on <skill>?\"."),
                    "scope": scope_label,
                    "generated_at": _utcnow_iso(),
                }
            return {
                "question": question,
                "intent": "expertise_trust",
                "kind": "no_person",
                "total": 0,
                "answers": [],
                "answer": ("No person matched that question. Name a visible "
                           "person, e.g. \"why does Keerthi know Python?\"."),
                "scope": scope_label,
                "generated_at": _utcnow_iso(),
            }

        profile_result = await expertise_search.person_expertise(
            db, organization_id=organization_id, person_id=person["id"],
        )
        cells = profile_result["expertise"]

        # ---- optional skill narrowing -> the one trust profile
        if predicate:
            skills = await expertise_search.resolve_for_query(
                db, organization_id=organization_id, query=predicate,
            )
            skill_ids = {s.id for s in skills}
            cell = next(
                (c for c in cells if c["skill_id"] in skill_ids), None,
            )
            if cell is not None and skills:
                skill_id = cell["skill_id"]
                trust = await expertise_engine.trust(
                    db, organization_id=organization_id,
                    person_id=person["id"], skill_id=skill_id, limit=12,
                )
                if trust is not None:
                    t = trust
                    evidence_lines = []
                    for row in t["recent_evidence"][:5]:
                        evidence_lines.append(
                            f"{row['strength']}/{row['evidence_kind']} from "
                            f"{row['source_type']}:{row['source_id']} "
                            f"({row['detail'] or row['evidence_type']})"
                        )
                    negative = t["failed_count"] + sum(
                        1 for c in t["contradictions"] if c.get("expired"))
                    answer = (
                        f"{t['person_name']} on {t['skill_name']}: "
                        f"lifecycle {t['lifecycle']}, score {t['score']:.0f}, "
                        f"confidence {t['confidence']:.2f}, freshness "
                        f"{t['freshness']}, {t['successful_count']} successful / "
                        f"{t['failed_count']} failed outcome(s) across "
                        f"{t['distinct_lineages']} independent source lineage(s) "
                        f"from {t['corroborated_kinds']} evidence kind(s)."
                    )
                    if negative:
                        answer += f" {negative} negative or expired item(s) remain visible and counted against it."
                    if evidence_lines:
                        answer += " Evidence: " + " | ".join(evidence_lines) + "."
                    else:
                        answer += " No current evidence row remains (expired)."
                    return {
                        "question": question,
                        "intent": "expertise_trust",
                        "kind": "trust_profile",
                        "total": 1,
                        "answers": [{**t, **{"person_id": person["id"]}}],
                        "answer": answer,
                        "scope": scope_label,
                        "generated_at": _utcnow_iso(),
                    }

        if not cells:
            return {
                "question": question,
                "intent": "expertise_trust",
                "kind": "no_expertise",
                "total": 0,
                "answers": [],
                "answer": (
                    f"No evidence-derived expertise is visible for "
                    f"{person['name']}, so there is nothing to trust yet."
                ),
                "scope": scope_label,
                "generated_at": _utcnow_iso(),
            }

        names = ", ".join(
            f"{c['skill_name']} ({c['lifecycle']}, "
            f"confidence {c['confidence']:.2f}, freshness {c['freshness']})"
            for c in cells[:4]
        )
        return {
            "question": question,
            "intent": "expertise_trust",
            "kind": "person_expertise",
            "total": len(cells),
            "answers": cells,
            "answer": (
                f"{person['name']} trust snapshot: " + names + ". "
                f"Ask me \"what evidence backs <name> on <skill>?\" for a cell."
            ),
            "scope": scope_label,
            "generated_at": _utcnow_iso(),
        }

    async def query(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        question: str,
        user: Any,
        limit: int = _MAX_DISCOVERY,
    ) -> dict[str, Any]:
        """One surface for the Company Brain: a natural question routes to the
        matching intelligence and returns only evidence the caller may see."""
        lowered = question.lower().strip()
        # temporal special case first: "what was our pricing in february"
        month_hit = next(
            (m for m in _MONTHS if m in lowered), None
        )
        if month_hit and ("was" in lowered or "were" in lowered):
            return await self._temporal_query(
                db, organization_id=organization_id, question=question,
                month=_MONTHS[month_hit], user=user,
            )
        intent = "discovery"
        for candidate, keywords in _INTENT_RULES:
            if any(keyword in lowered for keyword in keywords):
                intent = candidate
                break
        if intent == "changes":
            result = await self.changes(
                db, organization_id=organization_id, user=user, days=7, limit=limit
            )
            return {
                **result,
                "question": question,
                "intent": "changes",
                "generated_at": _utcnow_iso(),
            }
        if intent == "gaps":
            result = await self.gaps(db, organization_id=organization_id, user=user)
            return {
                **result,
                "question": question,
                "intent": "gaps",
                "generated_at": _utcnow_iso(),
            }
        if intent == "health":
            result = await self.health(db, organization_id=organization_id, user=user)
            return {
                **result,
                "question": question,
                "intent": "health",
                "generated_at": _utcnow_iso(),
            }
        if intent == "recommendations":
            result = await self.recommendations(
                db, organization_id=organization_id, user=user, limit=limit
            )
            return {
                **result,
                "question": question,
                "intent": "recommendations",
                "generated_at": _utcnow_iso(),
            }
        if intent == "contradictions":
            gaps = await self.gaps(db, organization_id=organization_id, user=user)
            return {
                "question": question,
                "intent": "contradictions",
                "total": sum(1 for g in gaps["gaps"] if g["kind"] == "contradiction"),
                "answers": [
                    g for g in gaps["gaps"] if g["kind"] == "contradiction"
                ],
                "scope": gaps["scope"],
                "generated_at": _utcnow_iso(),
            }
        if intent == "people":
            return await self._people_query(
                db, organization_id=organization_id, question=question, user=user
            )
        if intent == "expertise":
            return await self._expertise_query(
                db, organization_id=organization_id, question=question, user=user
            )
        if intent == "expertise_trust":
            return await self._expertise_trust_query(
                db, organization_id=organization_id, question=question, user=user
            )
        if intent in ("impact", "ownership"):
            access = await self._access(db, organization_id=organization_id, user=user)
            scanned = await self._scan_topics(
                db, organization_id=organization_id, access=access
            )
            best_topic: Optional[KnowledgeTopic] = None
            q_tokens = tokens(question)
            best_score = 0
            for entry in scanned.values():
                topic = entry["topic"]
                t_tokens = tokens(f"{topic.name} {' '.join(_json_loads(topic.aliases_json, []))}")
                overlap = len(q_tokens & t_tokens)
                if overlap > best_score:
                    best_score = overlap
                    best_topic = topic
            if best_topic is None:
                if intent == "ownership":
                    # "who owns X" matched no knowledge topic: answer with the
                    # universal responsibility record instead of a dead end.
                    return await self._ownership_query(
                        db, organization_id=organization_id,
                        question=question, user=user, intent="responsibility",
                    )
                return {
                    "question": question,
                    "intent": intent,
                    "total": 0,
                    "answers": [],
                    "answer": "No knowledge topic matches this question.",
                    "scope": "org" if access.org_wide else "project",
                    "generated_at": _utcnow_iso(),
                }
            if intent == "impact":
                result = await self.impact(
                    db, organization_id=organization_id,
                    topic_name=best_topic.name, user=user,
                )
                if result is None:
                    return {
                        "question": question, "intent": intent, "total": 0,
                        "answers": [], "scope": "org" if access.org_wide else "project",
                    }
                return {**result, "question": question, "intent": intent,
                        "generated_at": _utcnow_iso()}
            result = await self.ownership(
                db, organization_id=organization_id,
                topic_name=best_topic.name, user=user,
            )
            if result is None:
                return {
                    "question": question, "intent": intent, "total": 0,
                    "answers": [], "scope": "org" if access.org_wide else "project",
                }
            return {**result, "question": question, "intent": intent,
                    "generated_at": _utcnow_iso()}
        if intent in ("responsibility", "continuity", "responsibility_history",
                      "responsibility_gaps", "single_point"):
            return await self._ownership_query(
                db, organization_id=organization_id,
                question=question, user=user, intent=intent,
            )
        if intent in ("affected", "stakeholders", "provenance"):
            from app.knowledge.action_engine import action_engine

            access = await self._access(db, organization_id=organization_id, user=user)
            scanned = await self._scan_topics(
                db, organization_id=organization_id, access=access
            )
            best_topic: Optional[KnowledgeTopic] = None
            q_tokens = tokens(question)
            best_score = 0
            for entry in scanned.values():
                topic = entry["topic"]
                t_tokens = tokens(f"{topic.name} {' '.join(_json_loads(topic.aliases_json, []))}")
                overlap = len(q_tokens & t_tokens)
                if overlap > best_score:
                    best_score = overlap
                    best_topic = topic
            if best_topic is None:
                return {
                    "question": question, "intent": intent, "total": 0,
                    "answers": [], "scope": "org" if access.org_wide else "project",
                    "generated_at": _utcnow_iso(),
                }
            if intent == "affected":
                result = await action_engine.propagation(
                    db, organization_id=organization_id,
                    topic_name=best_topic.name, user=user, depth=3,
                )
                return {**result, "question": question, "intent": intent,
                        "generated_at": _utcnow_iso()}
            if intent == "stakeholders":
                ownership = await self.ownership(
                    db, organization_id=organization_id,
                    topic_name=best_topic.name, user=user,
                )
                affected = await action_engine.propagation(
                    db, organization_id=organization_id,
                    topic_name=best_topic.name, user=user, depth=2,
                )
                return {
                    "question": question,
                    "intent": intent,
                    "topic": best_topic.name,
                    "owner": (ownership or {}).get("owner"),
                    "stakeholders": [
                        hop["title"] for hop in (affected or {}).get("hops", [])
                        if hop.get("title") and hop["entity_type"] not in ("topic",)
                    ][:12],
                    "total": len(affected.get("hops", [])) if affected else 0,
                    "scope": "org" if access.org_wide else "project",
                    "generated_at": _utcnow_iso(),
                }
            result = await self.discover(
                db, organization_id=organization_id,
                query=question, user=user, limit=limit,
            )
            return {**result, "intent": intent, "question": question}
        if intent in ("worry", "decide", "missing", "next", "confident"):
            from app.knowledge.action_engine import action_engine

            kind = {
                "worry": ("risk", "verification_required"),
                "decide": ("decision_required",),
                "missing": ("gap",),
                "next": ("recommendation",),
            }.get(intent, ())
            insights = await action_engine.insights(
                db, organization_id=organization_id, user=user, limit=40,
                **({"kind": kind[0]} if intent == "next" else {}),
            )
            if intent == "confident":
                answers = self._least_confident(insights["insights"], limit)
            else:
                answers = [
                    i for i in insights["insights"]
                    if i["kind"] in kind and i["status"] == "active"
                ][:limit]
            return {
                "question": question,
                "intent": intent,
                "total": len(answers),
                "answers": answers,
                "scope": insights["scope"],
                "generated_at": _utcnow_iso(),
            }
        if intent in ("actions", "attention", "blocked", "overdue", "escalation"):
            from app.knowledge.action_ops_engine import action_ops_engine

            result = await action_ops_engine.center(
                db, organization_id=organization_id, user=user,
                attention=(intent == "attention"),
                blocked_only=(intent == "blocked"),
                overdue_only=(intent == "overdue"),
                escalated_only=(intent == "escalation"),
                limit=limit,
            )
            return {
                **result,
                "question": question,
                "intent": intent,
                "generated_at": _utcnow_iso(),
            }
        # --------------------------------------------------- Slice 4E.7 loop
        if intent == "company_changes":
            from app.knowledge.learning_engine import learning_engine

            result = await learning_engine.company_changes(
                db, organization_id=organization_id, since_hours=24, user=user,
            )
            return {**result, "question": question, "generated_at": _utcnow_iso()}
        if intent == "learned":
            from app.knowledge.learning_engine import learning_engine

            result = await learning_engine.learning_feed(
                db, organization_id=organization_id, user=user, limit=limit,
            )
            return {**result, "question": question, "generated_at": _utcnow_iso()}
        if intent == "companyhealth":
            from app.knowledge.learning_engine import learning_engine

            result = await learning_engine.company_health(
                db, organization_id=organization_id, user=user,
            )
            return {**result, "question": question, "generated_at": _utcnow_iso()}
        if intent in ("why", "should", "decisions"):
            from app.models.company_actions import CompanyAction
            from app.models.organizational_learning import DecisionOutcome, OrganizationalLearning

            access = await self._access(db, organization_id=organization_id, user=user)
            if intent == "why":
                # find the best-matching subject: an action first, then a topic.
                action_rows = list(
                    (
                        await db.execute(
                            select(CompanyAction)
                            .where(CompanyAction.organization_id == organization_id)
                            .order_by(CompanyAction.updated_at.desc())
                            .limit(_MAX_TOPICS_SCAN)
                        )
                    ).scalars().all()
                )
                q_tokens = tokens(question)
                best: Optional[tuple[str, str, str]] = None
                best_score = 0
                for action in action_rows:
                    label = f"{action.title} {action.why or ''} {action.source_problem or ''}"
                    overlap = len(q_tokens & tokens(label))
                    if overlap > best_score:
                        best_score = overlap
                        best = ("action", action.id, action.title)
                if best is None or best_score < 1:
                    scanned = await self._scan_topics(
                        db, organization_id=organization_id, access=access
                    )
                    for topic_id, entry in scanned.items():
                        topic: KnowledgeTopic = entry["topic"]
                        t_tokens = tokens(f"{topic.name} {' '.join(_json_loads(topic.aliases_json, []))}")
                        overlap = len(q_tokens & t_tokens)
                        if overlap > best_score:
                            best_score = overlap
                            best = ("topic", topic.id, topic.name)
                if best is None or best_score < 1:
                    return {
                        "question": question,
                        "intent": "why",
                        "total": 0,
                        "answer": "No company subject matches this question closely enough to explain.",
                        "reasons": [],
                        "evidence": [],
                        "scope": "org" if access.org_wide else "project",
                        "generated_at": _utcnow_iso(),
                    }
                from app.knowledge.learning_engine import learning_engine

                result = await learning_engine.explain(
                    db, organization_id=organization_id,
                    subject_type=best[0], subject_id=best[1], user=user,
                )
                return {
                    **result,
                    "question": question,
                    "intent": "why",
                    "scope": result.get("scope", "org" if access.org_wide else "project"),
                    "generated_at": _utcnow_iso(),
                }
            # should / decisions — the decision-feedback board, built
            # deterministically from measured outcomes and lessons.
            outcome_rows = list(
                (
                    await db.execute(
                        select(DecisionOutcome)
                        .where(DecisionOutcome.organization_id == organization_id)
                        .order_by(DecisionOutcome.measured_at.desc())
                        .limit(40)
                    )
                ).scalars().all()
            )
            lesson_rows = list(
                (
                    await db.execute(
                        select(OrganizationalLearning)
                        .where(OrganizationalLearning.organization_id == organization_id)
                        .order_by(OrganizationalLearning.observed_at.desc())
                        .limit(30)
                    )
                ).scalars().all()
            )
            met = sum(1 for r in outcome_rows if r.assessment in ("met", "outperformed"))
            decisions = [
                {
                    "id": r.id,
                    "decision_id": r.decision_id,
                    "expected_metric": r.expected_metric,
                    "expected_value": r.expected_value,
                    "actual_value": r.actual_value,
                    "variance_pct": r.variance_pct,
                    "assessment": r.assessment,
                    "outcome_type": r.outcome_type,
                    "factors": _json_loads(r.factors_json, []),
                    "measured_at": ensure_aware(r.measured_at).isoformat(),
                }
                for r in outcome_rows
            ]
            lessons = [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "title": r.title,
                    "lesson": r.lesson,
                    "observed_at": ensure_aware(r.observed_at).isoformat(),
                }
                for r in lesson_rows
            ]
            underperformed = [d for d in decisions if d["assessment"] == "underperformed"]
            track = (
                f"{met} of {len(decisions)} measured {'decision' if len(decisions) == 1 else 'decisions'} met or "
                f"exceeded their expectation" if decisions
                else "The company has not measured a decision outcome yet"
            )
            answer = (
                f"Decision history is the evidence: {track}. "
                + (
                    f"{len(underperformed)} underperformed (e.g. "
                    f"'{underperformed[0]['expected_metric']}') — review the detected factors before "
                    "committing to a similar move."
                    if underperformed
                    else "No similar move has underperformed on record."
                )
            )
            return {
                "question": question,
                "intent": intent,
                "total": len(decisions),
                "answer": answer,
                "decisions": decisions[:20],
                "lessons": lessons[:10],
                "recommendation_quality": [],
                "scope": "org" if access.org_wide else "project",
                "generated_at": _utcnow_iso(),
            }
        result = await self.discover(
            db, organization_id=organization_id,
            query=question, user=user, limit=limit,
        )
        return {**result, "intent": "discovery"}

    async def _temporal_query(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        question: str,
        month: int,
        user: Any,
    ) -> dict[str, Any]:
        """'what was our pricing in february' -> the understanding valid in
        February, with what replaced it."""
        from app.knowledge.action_engine import action_engine

        access = await self._access(db, organization_id=organization_id, user=user)
        scanned = await self._scan_topics(db, organization_id=organization_id, access=access)
        q_tokens = tokens(question)
        best_topic: Optional[KnowledgeTopic] = None
        best_score = 0
        for entry in scanned.values():
            topic = entry["topic"]
            t_tokens = tokens(f"{topic.name} {' '.join(_json_loads(topic.aliases_json, []))}")
            overlap = len(q_tokens & t_tokens)
            if overlap > best_score:
                best_score = overlap
                best_topic = topic
        if best_topic is None:
            return {
                "question": question,
                "intent": "temporal",
                "total": 0,
                "answer": "No knowledge topic matches this question.",
                "scope": "org" if access.org_wide else "project",
                "generated_at": _utcnow_iso(),
            }
        year = now_utc().year
        as_of = datetime(year, month, 1, tzinfo=timezone.utc)
        if as_of > now_utc():
            as_of = datetime(year - 1, month, 1, tzinfo=timezone.utc)
        result = await action_engine.state_at(
            db, organization_id=organization_id,
            topic_name=best_topic.name, as_of=as_of, user=user,
        )
        if result is None:
            return {
                "question": question,
                "intent": "temporal",
                "topic": _clean_topic_name(best_topic.name),
                "as_of": as_of.isoformat(),
                "total": 0,
                "answer": f"No understanding of '{_clean_topic_name(best_topic.name)}' was recorded by {as_of.date().isoformat()}.",
                "scope": "org" if access.org_wide else "project",
                "generated_at": _utcnow_iso(),
            }
        return {**result, "question": question, "intent": "temporal"}

    @staticmethod
    def _least_confident(insights: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        return sorted(
            [i for i in insights if i["status"] == "active"],
            key=lambda i: (i["confidence"], i["priority_score"]),
        )[:limit]


intelligence_engine = IntelligenceEngine()