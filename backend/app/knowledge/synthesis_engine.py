"""Slice 4E.3 — Universal Knowledge Understanding & Synthesis.

What does all that information collectively mean?

4E.2 funnels every meaningful piece of company activity into the canonical
model. 4E.3 connects those sources: claims from different families that speak
about the same topic are synthesized into ONE topic-anchored understanding
claim with a full relationship graph:

    KnowledgeClaim (claim_type="synthesis", subject=the topic)
      ├── statement            (deterministic from the evidence)
      ├── topic                (canonical knowledge_topics row)
      ├── authority            (max authority among supporting claims)
      ├── confidence           (deterministic formula, see _confidence)
      ├── first_seen/last_seen
      ├── valid_from/valid_to  (temporal truth: evolution is supersession)
      ├── supporting_claims    (claim ids + resolved claims)
      ├── contradicting_claims (facet conflicts + the resolved winner)
      ├── supersedes           (previous understanding of the same topic)
      ├── related_entities     (projects, tasks, decisions, teams, ...)
      └── provenance           (evidence -> sources, excerpts)

Design laws (mirroring 4E.1/4E.2):
* deterministic first: synthesis, contradiction detection, authority
  resolution, confidence and risk are pure functions of persisted evidence —
  no LLM anywhere in the substrate,
* one internal language: an "understanding" IS a KnowledgeClaim; nothing is
  stored in a parallel model,
* change-driven: each successful universal ingest re-synthesizes the topics
  the source touches, in the same transaction; replaying events never
  re-runs handlers so it never duplicates knowledge,
* exact-once synthesis: re-synthesizing with unchanged evidence refreshes
  last_seen only — never a duplicate claim, never a spurious supersession,
* contradiction resolution: higher authority wins; ties break on valid_from;
  both sides stay as evidence (contradicting_claim_ids_json) so the system
  can always show why the loser lost,
* governance first: every read resolves caller access BEFORE assembly and
  never fetches what the caller cannot see,
* bounded: evidence selection, timelines, relations and contradiction groups
  are hard-capped — no full-org scans.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.intelligence.company_context import CallerAccess, resolve_caller_access
from app.core.timeutils import utcnow as now_utc
import json

def _load_provenance(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}

_AUTHORITY_LABELS = {
    1: "unverified",
    2: "team_record",
    3: "documented",
    4: "authoritative",
    5: "official",
}
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEvidence,
    KnowledgeRelation,
    KnowledgeSource,
    KnowledgeTopic,
)

logger = logging.getLogger("vcos.knowledge.synthesis")

# ---------------------------------------------------------------------------
# bounds — every read and every write is hard-capped
# ---------------------------------------------------------------------------

_MAX_EVIDENCE = 40            # candidate evidence claims per synthesis
_MAX_TIMELINE = 60            # timeline entries per topic
_MAX_PROBLEMS = 6             # negative-signal claims surfaced per topic
_MAX_DECISIONS = 6            # decision claims surfaced per topic
_MAX_RELATED = 12             # related entities surfaced per topic
_MAX_CONTRADICTIONS = 12      # contradiction pairs surfaced per topic
_MAX_GRAPH_EDGES = 12         # relation edges written per synthesis pass
_MAX_TOPICS_PER_SOURCE = 3    # topics derived from one source
_MAX_ANSWER_EVIDENCE = 12     # citations in an evidence-backed answer

# deterministic relevance formula: authority x freshness x mention
_AUTHORITY_NORM = {1: 0.25, 2: 0.45, 3: 0.65, 4: 0.85, 5: 1.0}

# facet extractors for contradiction detection (numbers, dates, durations)
_CURRENCY_RE = re.compile(
    r"(?:\u20b9|rs\.?|inr|usd|\$|\u20ac|\u00a3)?\s*(\d[\d,]*(?:\.\d+)?)\s*"
    r"(lakh|lac|cr|crore|k|m|mn|b|bn)",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_DURATION_RE = re.compile(r"(\d+)\s*(day|week|month|quarter|year|hour)s?", re.IGNORECASE)
_MONTHDAY_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_QUANTITY_RE = re.compile(
    r"(\d+)\s*(tasks|seats|gb|tb|users|customers|clients|employees|engineers|hours)",
    re.IGNORECASE,
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_CURRENCY_UNITS = {
    "lakh": 100_000.0,
    "lac": 100_000.0,
    "cr": 10_000_000.0,
    "crore": 10_000_000.0,
    "k": 1_000.0,
    "m": 1_000_000.0,
    "mn": 1_000_000.0,
    "b": 1_000_000_000.0,
    "bn": 1_000_000_000.0,
}

_NEGATIVE_SIGNAL = re.compile(
    r"\b(blocked|delay|delayed|behind|risk|at-risk|fail|failure|failed|degraded|"
    r"incident|issue|problem|overdue|stuck|paused|cancelled|cancel|escalat|"
    r"rejected|unhappy|churn|complaint|confus)\b",
    re.IGNORECASE,
)
_POSITIVE_SIGNAL = re.compile(
    r"\b(approved|approve|decided|decision|chose|escalated|launched|committed|"
    r"resolved|fixed|completed|unblocked|rolled out|rollout)\b",
    re.IGNORECASE,
)

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "from", "that", "this", "were", "was",
        "have", "has", "had", "our", "their", "its", "they", "them", "into",
        "about", "after", "before", "during", "across", "project", "task",
        "meeting", "message", "document", "policy", "decision", "update",
        "updated", "created", "status", "state", "title", "topic", "company",
        "team", "work", "will", "can", "should", "would", "going", "been",
        "being", "also", "just", "very", "next", "last", "over", "under",
        "more", "most", "new", "old", "now", "today", "yesterday", "week",
        "month", "year", "people", "please", "thanks", "thank", "hi", "hello",
    }
)


def _json_loads(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _snippet(text: Optional[str], length: int = 160) -> str:
    if not text:
        return ""
    text = " ".join(str(text).split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "\u2026"


def _topic_names_for_source(source: KnowledgeSource) -> list[str]:
    """Deterministic topic candidates for a source (bounded, no scans).

    category + keywords always qualify; meaningful title tokens (length >= 4,
    not stopwords) add at most one more candidate.
    """
    names: list[str] = []
    provenance = _load_provenance(source.provenance_json)
    category = (provenance.get("category") or source.source_status or "").strip()
    if category and category.lower() not in {n.lower() for n in names}:
        names.append(category[:120])
    for piece in str(provenance.get("keywords") or "").split(","):
        piece = piece.strip()[:120]
        if piece and piece.lower() not in {n.lower() for n in names}:
            names.append(piece)
    title_tokens = [t for t in re.split(r"[^a-z0-9]+", (source.title or "").lower()) if t]
    meaningful = [t for t in title_tokens if len(t) >= 4 and t not in _STOPWORDS]
    for token in meaningful[:1]:
        if token[:120] not in {n.lower() for n in names}:
            names.append(token[:120])
    return names[: _MAX_TOPICS_PER_SOURCE]


# ---------------------------------------------------------------------------
# deterministic facet extraction (contradiction substrate)
# ---------------------------------------------------------------------------


def _money_value(match: re.Match) -> tuple[float, str]:
    unit = (match.group(2) or "").lower()
    number = float(match.group(1).replace(",", ""))
    multiplier = _CURRENCY_UNITS.get(unit, 1.0)
    return number * multiplier, unit or "unit"


def extract_facets(text: str) -> list[dict[str, Any]]:
    """Extract comparable facets from a claim's text. Returns a list of
    ``{"key", "value", "unit", "raw"}`` where equal keys with different values
    are the substrate for contradiction detection."""
    facets: list[dict[str, Any]] = []
    for match in _CURRENCY_RE.finditer(text):
        value, unit = _money_value(match)
        facets.append(
            {"key": "currency", "value": round(value, 2), "unit": unit, "raw": match.group(0)}
        )
    for match in _PERCENT_RE.finditer(text):
        facets.append(
            {"key": "percent:%", "value": round(float(match.group(1)), 4), "unit": "%", "raw": match.group(0)}
        )
    for match in _DURATION_RE.finditer(text):
        unit = match.group(2).lower()
        facets.append(
            {"key": f"duration:{unit}", "value": int(match.group(1)), "unit": unit, "raw": match.group(0)}
        )
    for match in _MONTHDAY_RE.finditer(text):
        value = (_MONTHS[match.group(1)[:3].lower()], int(match.group(2)))
        facets.append(
            {"key": "date:monthday", "value": value, "unit": "monthday", "raw": match.group(0)}
        )
    for match in _ISO_DATE_RE.finditer(text):
        facets.append(
            {"key": "date:iso", "value": match.group(1), "unit": "iso", "raw": match.group(0)}
        )
    for match in _QUANTITY_RE.finditer(text):
        unit = match.group(2).lower()
        facets.append(
            {"key": f"quantity:{unit}", "value": int(match.group(1)), "unit": unit, "raw": match.group(0)}
        )
    return facets


def _facet_label(key: str) -> str:
    kind = key.split(":", 1)[0]
    return {
        "currency": "Budget",
        "percent": "Progress",
        "duration": "Duration",
        "quantity": "Scale",
        "date": "Date",
    }.get(kind, kind.title())


# ---------------------------------------------------------------------------
# synthesis engine
# ---------------------------------------------------------------------------


class SynthesisEngine:
    # -------------------------------------------------------------- access

    @staticmethod
    def _visible(access: Any, provenance: Optional[dict[str, Any]]) -> bool:
        if access.org_wide:
            return True
        project_id = (provenance or {}).get("project_id")
        if project_id and project_id in access.project_ids:
            return True
        conversation_id = (provenance or {}).get("conversation_id")
        if conversation_id and conversation_id in access.member_conversation_ids:
            return True
        return False

    async def _access(self, db: AsyncSession, *, organization_id: str, user: Any):
        if user is None:
            # event-driven writes have no caller: the system sees the whole
            # org (reads are still governed separately, per caller).
            return CallerAccess(
                organization_id=organization_id,
                user_id="system",
                employee_id=None,
                org_wide=True,
            )
        return await resolve_caller_access(db, organization_id=organization_id, user=user)

    # -------------------------------------------------------------- topics

    async def get_or_create_topic(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        category: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> KnowledgeTopic:
        topic = (
            await db.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == organization_id,
                    KnowledgeTopic.name == name,
                )
            )
        ).scalar_one_or_none()
        if topic is None:
            topic = KnowledgeTopic(
                organization_id=organization_id,
                name=name,
                category=category or None,
                entity_type=entity_type,
                entity_id=entity_id,
                status="active",
            )
            db.add(topic)
            await db.flush()
        elif not topic.category and category:
            topic.category = category
        return topic

    # -------------------------------------------------------- evidence core

    async def _collect_evidence(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic: KnowledgeTopic,
        access: Any,
        include_superseded: bool = False,
    ) -> list[KnowledgeClaim]:
        """Bounded candidate evidence claims mentioning the topic (visible).

        Selection is deterministic: newest claims first, capped, then scored
        by authority x freshness x mention and re-ranked.
        """
        aliases = [a.lower() for a in _json_loads(topic.aliases_json, []) if a]
        needles = {topic.name.lower(), *aliases}
        candidates = list(
            (
                await db.execute(
                    select(KnowledgeClaim)
                    .where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.claim_type != "synthesis",
                    )
                    .order_by(KnowledgeClaim.valid_from.desc())
                    .limit(_MAX_EVIDENCE * 4)
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
        scored: list[tuple[float, KnowledgeClaim]] = []
        for claim in candidates:
            if not include_superseded and claim.status == "superseded":
                continue
            source = by_source.get((claim.subject_type, claim.subject_id))
            if source is None or not self._visible(access, _load_provenance(source.provenance_json)):
                continue
            text = f"{source.title} {claim.object_text} {_load_provenance(source.provenance_json).get('category') or ''} {_load_provenance(source.provenance_json).get('keywords') or ''}"
            lowered = text.lower()
            if not any(needle in lowered for needle in needles):
                continue
            mention = 1.0
            if not any(needle in f"{claim.object_text}".lower() for needle in needles) and \
               not any(needle in (source.title or "").lower() for needle in needles):
                mention = 0.6
            authority_norm = _AUTHORITY_NORM.get(claim.authority_level, 0.25)
            freshness_norm = (source.freshness_score or 0) / 100.0
            relevance = authority_norm * (0.4 + 0.6 * freshness_norm) * mention
            scored.append((relevance, claim))
        scored.sort(key=lambda item: (-item[0], ensure_aware(item[1].valid_from)))
        return [claim for _, claim in scored[:_MAX_EVIDENCE]]

    async def _sources_for(
        self, db: AsyncSession, *, organization_id: str, claims: list[KnowledgeClaim]
    ) -> dict[tuple[str, str], KnowledgeSource]:
        if not claims:
            return {}
        rows = list(
            (
                await db.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.organization_id == organization_id,
                        KnowledgeSource.source_type.in_({c.subject_type for c in claims}),
                        KnowledgeSource.source_id.in_({c.subject_id for c in claims}),
                    )
                )
            ).scalars().all()
        )
        return {(s.source_type, s.source_id): s for s in rows}

    # --------------------------------------------------- contradiction core

    def _detect_contradictions(
        self, evidence: list[KnowledgeClaim]
    ) -> list[dict[str, Any]]:
        """Deterministic facet conflicts among active evidence claims.

        Two claims with the same facet (e.g. currency:lakh) but different
        values contradict. The winner is resolved by authority, then by
        valid_from. Both sides remain evidence — the loser is recorded as
        contradicted with its resolution.
        """
        groups: dict[str, list[tuple[KnowledgeClaim, dict[str, Any]]]] = {}
        for claim in evidence:
            for facet in extract_facets(claim.object_text):
                groups.setdefault(facet["key"], []).append((claim, facet))
        contradictions: list[dict[str, Any]] = []
        for key, members in groups.items():
            if len({claim.id for claim, _ in members}) < 2:
                continue  # a single claim cannot contradict itself
            distinct: dict[str, list[tuple[KnowledgeClaim, dict[str, Any]]]] = {}
            for claim, facet in members:
                distinct.setdefault(str(facet["value"]), []).append((claim, facet))
            if len(distinct) < 2:
                continue
            values = list(distinct)
            if len(contradictions) >= _MAX_CONTRADICTIONS:
                break
            ordered = sorted(
                values,
                key=lambda v: (
                    -max(c.authority_level for c, _ in distinct[v]),
                    -ensure_aware(max(c.valid_from for c, _ in distinct[v])).timestamp(),
                    v,
                ),
            )
            winner_value = ordered[0]
            winner_claim, _ = max(
                distinct[winner_value], key=lambda pair: (pair[0].authority_level, ensure_aware(pair[0].valid_from))
            )
            for value in ordered[1:]:
                loser_claim, _ = max(
                    distinct[value], key=lambda pair: (pair[0].authority_level, ensure_aware(pair[0].valid_from))
                )
                contradictions.append(
                    {
                        "facet": key,
                        "facet_label": _facet_label(key),
                        "value_a": str(distinct[winner_value][0][1]["raw"]).strip(),
                        "claim_a": winner_claim.id,
                        "value_b": str(distinct[value][0][1]["raw"]).strip(),
                        "claim_b": loser_claim.id,
                        "winner_claim_id": winner_claim.id,
                        "loser_claim_id": loser_claim.id,
                        "resolution": (
                            f"authority {winner_claim.authority_level} > "
                            f"{loser_claim.authority_level}"
                            if winner_claim.authority_level != loser_claim.authority_level
                            else "newer valid_from"
                        ),
                    }
                )
        return contradictions

    # ---------------------------------------------------- statement building

    def _build_statement(
        self,
        *,
        topic_name: str,
        evidence: list[KnowledgeClaim],
        contradictions: list[dict[str, Any]],
        resolved: dict[str, dict[str, Any]],
    ) -> tuple[str, str]:
        """Deterministic understanding statement + risk from the evidence."""
        sentences: list[str] = []
        problems: list[str] = []
        patterns: list[tuple[int, str]] = []
        decisions: list[tuple[Any, KnowledgeClaim]] = []

        for claim in evidence:
            text = claim.object_text
            if claim.subject_type == "pattern":
                count = claim.confidence or 1
                patterns.append((int(max(1, round(count))), _snippet(text, 120)))
            elif claim.subject_type == "decision":
                decisions.append((ensure_aware(claim.valid_from), claim))
            if _NEGATIVE_SIGNAL.search(text):
                problems.append(_snippet(text, 140))
        if decisions:
            decisions.sort(key=lambda pair: pair[0])
            _, latest = decisions[-1]
            sentences.append(
                f"Latest decision: {_snippet(latest.object_text, 140)}"
                f" (authority {latest.authority_level}, {latest.valid_from.date().isoformat() if ensure_aware(latest.valid_from) else 'recorded'})"
            )
        if patterns:
            patterns.sort(key=lambda pair: pair[0], reverse=True)
            count, detail = patterns[0]
            sentences.append(f"Recurring pattern: {detail} ({int(count)} occurrences)")
        for key in sorted(resolved)[:2]:
            entry = resolved[key]
            sentences.append(
                f"{entry['label']}: {entry['value']} (authoritative from {entry['source_type']})"
            )
        snapshot = "; ".join(
            _snippet(c.object_text, 140) for c in evidence[:_MAX_ANSWER_EVIDENCE]
        )
        if snapshot:
            sentences.append(f"Evidence: {snapshot}")
        if problems:
            sentences.append("Active concern: " + "; ".join(problems[:_MAX_PROBLEMS]))

        unresolved = contradictions
        if unresolved:
            state_phrase = "contested"
        elif problems or patterns:
            state_phrase = "escalating" if patterns else "active concern"
        else:
            state_phrase = "stable"
        body = " ".join(sentences)
        statement = f"Topic '{topic_name}': {state_phrase}." + (f" {body}" if body else "")
        risk = "high" if patterns and patterns[0][0] >= 3 or len(problems) >= 3 else (
            "medium" if problems or patterns else "low"
        )
        return statement, risk

    def _confidence(
        self,
        *,
        evidence: list[KnowledgeClaim],
        authority: int,
        newest_freshness: float,
        contradicted: int,
    ) -> float:
        auth_norm = _AUTHORITY_NORM.get(authority, 0.25)
        corroboration = min(1.0, _log2(1 + len(evidence)) / 3.0)
        agreeing = max(0, len(evidence) - contradicted)
        agreement = agreeing / len(evidence) if evidence else 0.0
        return round(
            0.35 * auth_norm + 0.25 * newest_freshness + 0.25 * corroboration + 0.15 * agreement,
            3,
        )

    async def _synthesis_claims(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_id: str,
        include_superseded: bool = True,
    ) -> list[KnowledgeClaim]:
        """All understanding claims for a topic, oldest first (the evolution)."""
        rows = list(
            (
                await db.execute(
                    select(KnowledgeClaim)
                    .where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.claim_type == "synthesis",
                        KnowledgeClaim.topic_id == topic_id,
                    )
                    .order_by(KnowledgeClaim.valid_from.asc())
                    .limit(_MAX_TIMELINE + 1)
                )
            ).scalars().all()
        )
        if not include_superseded:
            rows = [r for r in rows if r.status != "superseded"]
        return rows

    # ---------------------------------------------------------- persistence

    async def synthesize_for_source(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        source_type: str,
        source_id: str,
    ) -> dict[str, Any]:
        """Change-driven entry point: derive the topics a source touches and
        re-synthesize each (bounded, idempotent). Called after a successful
        canonical ingest so knowledge stays live without a second job queue."""
        source = (
            await db.execute(
                select(KnowledgeSource).where(
                    KnowledgeSource.organization_id == organization_id,
                    KnowledgeSource.source_type == source_type,
                    KnowledgeSource.source_id == source_id,
                )
            )
        ).scalar_one_or_none()
        if source is None:
            return {"status": "skipped", "reason": "source not found"}
        results: list[dict[str, Any]] = []
        for name in _topic_names_for_source(source):
            try:
                topic = await self.get_or_create_topic(
                    db, organization_id=organization_id, name=name,
                )
                results.append(
                    await self.synthesize_topic(
                        db, organization_id=organization_id, topic_id=topic.id,
                    )
                )
            except Exception:  # one topic must never break the ingest chain
                logger.exception("synthesis failed for topic %r in %s", name, organization_id)
                results.append({"status": "error", "topic": name})
        await db.flush()
        return {
            "status": "ok",
            "source_type": source_type,
            "source_id": source_id,
            "topics": results,
        }

    async def synthesize_topic(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_id: str,
        user: Any = None,
    ) -> dict[str, Any]:
        """One deterministic synthesis pass for a topic (idempotent).

        Persists the topic's current understanding as a topic-anchored
        KnowledgeClaim (claim_type="synthesis"), superseding the previous
        understanding when the statement actually changed. Unchanged evidence
        refreshes last_seen only — replay-safe by construction.
        """
        topic = await db.get(KnowledgeTopic, topic_id)
        if topic is None or topic.organization_id != organization_id:
            return {"status": "skipped", "reason": "topic not found"}
        access = await self._access(db, organization_id=organization_id, user=user)
        evidence = await self._collect_evidence(
            db, organization_id=organization_id, topic=topic, access=access
        )
        if not evidence:
            return {"status": "skipped", "reason": "no evidence", "topic": topic.name}

        sources = await self._sources_for(db, organization_id=organization_id, claims=evidence)
        contradictions = self._detect_contradictions(evidence)

        # resolved facets: for each contradicted facet the winning value
        resolved: dict[str, dict[str, Any]] = {}
        contradicted_claim_ids: set[str] = set()
        winner_source_types = {c.id: c.subject_type for c in evidence}
        for pair in contradictions:
            contradicted_claim_ids.add(pair["loser_claim_id"])
            resolved[pair["facet"]] = {
                "label": pair["facet_label"],
                "value": pair["value_a"],
                "source_type": winner_source_types.get(pair["claim_a"], "source"),
            }

        authority = max((c.authority_level for c in evidence), default=1)
        newest_freshness = 1.0
        for source in sources.values():
            if source.freshness_score is not None:
                newest_freshness = max(newest_freshness, source.freshness_score / 100.0)
        statement, risk = self._build_statement(
            topic_name=topic.name, evidence=evidence,
            contradictions=contradictions, resolved=resolved,
        )
        confidence = self._confidence(
            evidence=evidence, authority=authority,
            newest_freshness=newest_freshness,
            contradicted=len(contradicted_claim_ids),
        )
        now = now_utc()

        supporting = sorted(c.id for c in evidence if c.id not in contradicted_claim_ids)
        contradicting = [
            {
                "claim_id": pair["loser_claim_id"],
                "facet": pair["facet"],
                "facet_label": pair["facet_label"],
                "value": pair["value_b"],
                "winner_claim_id": pair["winner_claim_id"],
                "resolution": pair["resolution"],
            }
            for pair in contradictions
        ]
        related = await self._related_entities(
            db, organization_id=organization_id, evidence=evidence, topic=topic,
        )

        current = (
            await db.execute(
                select(KnowledgeClaim).where(
                    KnowledgeClaim.organization_id == organization_id,
                    KnowledgeClaim.claim_type == "synthesis",
                    KnowledgeClaim.topic_id == topic.id,
                    KnowledgeClaim.status != "superseded",
                ).order_by(KnowledgeClaim.valid_from.desc())
            )
        ).scalars().first()
        if current is not None and current.object_text == statement and current.confidence == confidence:
            current.last_seen = now
            await db.flush()
            return {
                "status": "ok", "topic": topic.name, "synthesized": False,
                "claim_id": current.id, "evidence": len(evidence),
            }

        claim = KnowledgeClaim(
            organization_id=organization_id,
            subject_type="topic",
            subject_id=topic.id,
            predicate="synthesizes",
            object_text=statement,
            claim_type="synthesis",
            status="authoritative" if authority >= 5 else "supported",
            authority_level=authority,
            confidence=confidence,
            context_type="topic",
            context_id=topic.id,
            valid_from=now,
            topic_id=topic.id,
            supporting_claim_ids_json=json.dumps(supporting),
            contradicting_claim_ids_json=json.dumps(contradicting),
            related_entities_json=json.dumps(related),
            last_seen=now,
            source_type="topic",
            source_id=topic.id,
            created_by=None,
        )
        db.add(claim)
        await db.flush()
        if current is not None:
            current.status = "superseded"
            current.valid_to = now
            current.superseded_by = claim.id

        for evidence_claim in evidence:
            source = sources.get((evidence_claim.subject_type, evidence_claim.subject_id))
            if source is None:
                continue
            db.add(
                KnowledgeEvidence(
                    organization_id=organization_id,
                    claim_id=claim.id,
                    source_type=evidence_claim.subject_type,
                    source_id=evidence_claim.subject_id,
                    excerpt=_snippet(evidence_claim.object_text, 400),
                    role="supporting" if evidence_claim.id not in contradicted_claim_ids else "contradicted",
                    confidence=evidence_claim.confidence,
                    valid_from=ensure_aware(evidence_claim.valid_from) or now,
                )
            )
        await self._enrich_graph(
            db, organization_id=organization_id,
            evidence_claims=evidence, sources=sources, topic=topic,
        )
        await db.flush()
        return {
            "status": "ok", "topic": topic.name, "synthesized": True,
            "claim_id": claim.id, "evidence": len(evidence),
            "authority": authority, "confidence": confidence, "risk": risk,
        }

    # ------------------------------------------------------- graph enrichment

    async def _related_entities(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        evidence: list[KnowledgeClaim],
        topic: KnowledgeTopic,
    ) -> list[dict[str, Any]]:
        """Entities the understanding is about: evidence sources + their
        anchors (project / team / conversation) — bounded and deterministic."""
        entities: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for claim in evidence:
            key = (claim.subject_type, claim.subject_id)
            if key in seen:
                continue
            seen.add(key)
            entities.append(
                {
                    "type": claim.subject_type,
                    "id": claim.subject_id,
                    "role": "evidence",
                    "title": _snippet(claim.object_text, 120),
                }
            )
        rows = list(
            (
                await db.execute(
                    select(KnowledgeRelation).where(
                        KnowledgeRelation.organization_id == organization_id,
                        KnowledgeRelation.target_type == "topic",
                        KnowledgeRelation.target_id == topic.id,
                    ).limit(_MAX_RELATED)
                )
            ).scalars().all()
        )
        for edge in rows:
            key = (edge.source_type, edge.source_id)
            if key in seen:
                continue
            seen.add(key)
            entities.append(
                {
                    "type": edge.source_type,
                    "id": edge.source_id,
                    "role": "related",
                    "title": None,
                    "relation": edge.relation_type,
                }
            )
        return entities[:_MAX_RELATED]

    async def _enrich_graph(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        evidence_claims: list[KnowledgeClaim],
        sources: dict[tuple[str, str], KnowledgeSource],
        topic: KnowledgeTopic,
    ) -> None:
        """Typed edges: source -> topic ("concerns") and source -> source
        ("relates_to") for entities sharing this topic. Idempotent under the
        unique edge constraint — on-conflict is a no-op."""
        from sqlalchemy.dialects import postgresql, sqlite

        edges: list[tuple[str, str, str, str, str]] = []
        for claim in evidence_claims[: _MAX_GRAPH_EDGES]:
            edges.append(
                (claim.subject_type, claim.subject_id, "topic", topic.id, "concerns")
            )
        entity_keys = [
            (claim.subject_type, claim.subject_id)
            for claim in evidence_claims
            if claim.subject_type in ("task", "decision", "meeting", "document", "policy", "message", "pattern")
        ]
        pairs: set[tuple[str, str, str, str]] = set()
        for i in range(len(entity_keys)):
            for j in range(i + 1, len(entity_keys)):
                if len(pairs) >= _MAX_GRAPH_EDGES:
                    break
                a, b = entity_keys[i], entity_keys[j]
                if a == b:
                    continue
                if a < b:
                    pairs.add((a[0], a[1], b[0], b[1]))
                else:
                    pairs.add((b[0], b[1], a[0], a[1]))
        for a_type, a_id, b_type, b_id in pairs:
            edges.append((a_type, a_id, b_type, b_id, "relates_to"))
        if not edges:
            return
        dialect = db.get_bind().dialect.name
        dialect_insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
        statement = dialect_insert(KnowledgeRelation).values(
            [
                {
                    "organization_id": organization_id,
                    "source_type": s_type,
                    "source_id": s_id,
                    "target_type": t_type,
                    "target_id": t_id,
                    "relation_type": relation,
                }
                for s_type, s_id, t_type, t_id, relation in edges
            ]
        ).on_conflict_do_nothing(
            index_elements=["source_type", "source_id", "target_type", "target_id", "relation_type"]
        )
        await db.execute(statement)

    # ------------------------------------------------------------ read paths

    async def topic_state(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """The state of a topic: current understanding, active problems,
        recent decisions, evidence, contradictions, related entities and
        historical evolution — assembled only from what the caller may see."""
        topic = (
            await db.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == organization_id,
                    KnowledgeTopic.name == topic_name,
                )
            )
        ).scalar_one_or_none()
        if topic is None:
            return None
        access = await self._access(db, organization_id=organization_id, user=user)
        evidence = await self._collect_evidence(
            db, organization_id=organization_id, topic=topic, access=access,
            include_superseded=True,
        )
        active = [c for c in evidence if c.status != "superseded"]
        sources = await self._sources_for(db, organization_id=organization_id, claims=evidence)
        by_family: dict[str, int] = {}
        for claim in active:
            by_family[claim.subject_type] = by_family.get(claim.subject_type, 0) + 1
        contradictions = self._detect_contradictions(active)
        synthesis = await self._synthesis_claims(
            db, organization_id=organization_id, topic_id=topic.id,
            include_superseded=True,
        )
        synthesis_visible = [
            c for c in synthesis
            if await self._claim_visible(
                db, organization_id=organization_id, claim=c, access=access
            )
        ]
        current = next(
            (c for c in reversed(synthesis_visible) if c.status != "superseded"),
            None,
        )
        evolution = [c for c in synthesis_visible if c.status == "superseded"]
        if not active and current is None:
            return None
        problems = [c for c in active if _NEGATIVE_SIGNAL.search(c.object_text)]
        decisions = [c for c in active if c.subject_type == "decision"]
        decisions.sort(key=lambda c: ensure_aware(c.valid_from), reverse=True)
        patterns = [c for c in active if c.subject_type == "pattern"]
        related = self._related_entity_shapes(evidence, sources)
        return {
            "topic": {"id": topic.id, "name": topic.name, "category": topic.category},
            "current_state": self._claim_shape(current) if current else None,
            "confidence": current.confidence if current else None,
            "risk": self._risk_for(active),
            "evidence": {
                "total": len(active),
                "by_family": by_family,
                "claims": [self._claim_shape(c, with_evidence=False) for c in active[:_MAX_EVIDENCE]],
            },
            "problems": [self._claim_shape(c) for c in problems[: _MAX_PROBLEMS]],
            "decisions": [self._claim_shape(c) for c in decisions[: _MAX_DECISIONS]],
            "patterns": [self._claim_shape(c) for c in patterns[: _MAX_DECISIONS]],
            "contradictions": contradictions[: _MAX_CONTRADICTIONS],
            "related_entities": related[:_MAX_RELATED],
            "evolution": {
                "versions": len(evolution),
                "latest_understanding_at": (
                    current.last_seen.isoformat() if current and current.last_seen else None
                ),
            },
            "scope": "org" if access.org_wide else "project",
        }

    def _related_entity_shapes(
        self,
        claims: list[KnowledgeClaim],
        sources: dict[tuple[str, str], KnowledgeSource],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for claim in claims:
            key = (claim.subject_type, claim.subject_id)
            if key in seen:
                continue
            seen.add(key)
            source = sources.get(key)
            out.append(
                {
                    "type": claim.subject_type,
                    "id": claim.subject_id,
                    "title": source.title if source else None,
                    "role": "evidence",
                }
            )
        return out

    @staticmethod
    def _risk_for(claims: list[KnowledgeClaim]) -> str:
        patterns = [c for c in claims if c.subject_type == "pattern"]
        problems = [c for c in claims if _NEGATIVE_SIGNAL.search(c.object_text)]
        if patterns and any(getattr(c, "confidence", 0) >= 3 for c in patterns):
            return "high"
        if len(problems) >= 3:
            return "high"
        if problems or patterns:
            return "medium"
        return "low"

    async def current_state(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """Knowledge snapshot: what the topic means right now, who said what
        when, how much evidence supports it, and whether it is decaying."""
        state = await self.topic_state(
            db, organization_id=organization_id, topic_name=topic_name, user=user
        )
        if state is None:
            return None
        sources = await self._sources_for_map(
            db, organization_id,
            {(s["subject_type"], s["subject_id"]) for s in state["evidence"]["claims"]},
        )
        latest_authoritative = max(
            (s for s in state["evidence"]["claims"] if s["authority_level"] >= 4),
            key=lambda c: ensure_aware(c["valid_from"]),
            default=None,
        )
        last_update = max(
            (
                ensure_aware(s.updated_at)
                for s in sources.values()
                if s.updated_at
            ),
            default=None,
        )
        freshness_label = "stale"
        if last_update is not None:
            age_days = max(0, (now_utc() - last_update).days)
            freshness_label = (
                "very_high" if age_days <= 1
                else "high" if age_days <= 7
                else "medium" if age_days <= 30
                else "low" if age_days <= 90
                else "stale"
            )
        return {
            "topic": state["topic"],
            "current_state": state["current_state"],
            "confidence": state["confidence"],
            "risk": state["risk"],
            "evidence": {
                "total": state["evidence"]["total"],
                "by_family": state["evidence"]["by_family"],
            },
            "latest_authoritative": (
                {
                    "claim_id": latest_authoritative["id"],
                    "statement": _snippet(latest_authoritative["object_text"], 200),
                    "valid_from": latest_authoritative["valid_from"],
                    "authority_level": latest_authoritative["authority_level"],
                }
                if latest_authoritative
                else None
            ),
            "last_knowledge_update": last_update.isoformat() if last_update else None,
            "freshness_label": freshness_label,
        }

    async def timeline(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        user: Any,
        limit: int = 30,
    ) -> Optional[dict[str, Any]]:
        """How the company's understanding of the topic developed over time."""
        topic = (
            await db.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == organization_id,
                    KnowledgeTopic.name == topic_name,
                )
            )
        ).scalar_one_or_none()
        if topic is None:
            return None
        limit = max(1, min(limit, _MAX_TIMELINE))
        access = await self._access(db, organization_id=organization_id, user=user)
        claims = await self._collect_evidence(
            db, organization_id=organization_id, topic=topic, access=access,
            include_superseded=True,
        )
        synthesis = [
            c for c in await self._synthesis_claims(
                db, organization_id=organization_id, topic_id=topic.id
            )
            if await self._claim_visible(
                db, organization_id=organization_id, claim=c, access=access
            )
        ]
        claims = [*claims, *synthesis]
        claims.sort(key=lambda c: ensure_aware(c.valid_from))
        entries = []
        for claim in claims[:_MAX_TIMELINE]:
            entries.append(
                {
                    "claim_id": claim.id,
                    "kind": claim.claim_type,
                    "family": claim.subject_type,
                    "predicate": claim.predicate,
                    "object_text": claim.object_text,
                    "status": claim.status,
                    "valid_from": ensure_aware(claim.valid_from).isoformat(),
                    "valid_to": ensure_aware(claim.valid_to).isoformat() if claim.valid_to else None,
                    "authority_level": claim.authority_level,
                }
            )
        return {
            "topic": {"id": topic.id, "name": topic.name},
            "total": len(entries),
            "events": entries[:limit],
        }

    async def contradictions(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        topic = (
            await db.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == organization_id,
                    KnowledgeTopic.name == topic_name,
                )
            )
        ).scalar_one_or_none()
        if topic is None:
            return None
        access = await self._access(db, organization_id=organization_id, user=user)
        active = await self._collect_evidence(
            db, organization_id=organization_id, topic=topic, access=access
        )
        pairs = self._detect_contradictions(active)
        return {
            "topic": {"id": topic.id, "name": topic.name},
            "total": len(pairs),
            "contradictions": pairs[:_MAX_CONTRADICTIONS],
        }

    async def evidence_answer(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        question: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """Evidence-backed answer: a deterministic statement plus the exact
        evidence chain that supports it (citations, never opinions)."""
        state = await self.topic_state(
            db, organization_id=organization_id, topic_name=topic_name, user=user
        )
        if state is None:
            return None
        current = state["current_state"]
        problem_sentence = ""
        if state["problems"]:
            problem_sentence = (
                " The active concern is: "
                + "; ".join(_snippet(p["object_text"], 120) for p in state["problems"][:3])
                + "."
            )
        decision_sentence = ""
        if state["decisions"]:
            latest = state["decisions"][0]
            decision_sentence = (
                f" The latest recorded decision "
                f"({str(latest['valid_from'] or '')[:10] or 'recorded'}) is: "
                f"{_snippet(latest['object_text'], 160)}."
            )
        statement = (
            current["object_text"]
            if current
            else f"Topic '{topic_name}': no consolidated understanding yet."
        )
        answer = (
            f"{_snippet(statement, 220)}{problem_sentence}{decision_sentence}"
        )
        citations = [
            {
                "type": claim["subject_type"],
                "id": claim["subject_id"],
                "claim_id": claim["id"],
                "excerpt": _snippet(claim["object_text"], 160),
                "authority_level": claim["authority_level"],
                "valid_from": claim["valid_from"],
            }
            for claim in state["evidence"]["claims"][:_MAX_ANSWER_EVIDENCE]
        ]
        return {
            "question": question,
            "topic": state["topic"],
            "answer": answer,
            "evidence": citations,
            "confidence": state["confidence"],
            "risk": state["risk"],
        }

    async def claim_detail(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        claim_id: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """One claim with its full relationship graph (governed)."""
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
        if not await self._claim_visible(db, organization_id=organization_id, claim=claim, access=access):
            return None
        evidence_rows = list(
            (
                await db.execute(
                    select(KnowledgeEvidence).where(
                        KnowledgeEvidence.organization_id == organization_id,
                        KnowledgeEvidence.claim_id == claim.id,
                    ).order_by(KnowledgeEvidence.valid_from.asc())
                )
            ).scalars().all()
        )
        source_keys = {(e.source_type, e.source_id) for e in evidence_rows}
        if claim.subject_type not in ("topic",):
            source_keys.add((claim.subject_type, claim.subject_id))
        sources = await self._sources_for_map(db, organization_id, source_keys)
        supporting_ids = _json_loads(claim.supporting_claim_ids_json, [])
        contradicting = _json_loads(claim.contradicting_claim_ids_json, [])
        supporting = await self._claim_resolution(db, organization_id, supporting_ids)
        superseded_claim = None
        if claim.superseded_by:
            superseded_claim = await db.get(KnowledgeClaim, claim.superseded_by)
        return {
            "claim": self._claim_shape(claim),
            "topic": (
                {"id": claim.topic_id}
                if claim.topic_id
                else None
            ),
            "authority": {
                "level": claim.authority_level,
                "label": _AUTHORITY_LABELS.get(claim.authority_level, "unverified"),
            },
            "supporting_claims": supporting,
            "contradicting_claims": contradicting,
            "related_entities": _json_loads(claim.related_entities_json, []),
            "superseded_by": (
                {"id": superseded_claim.id, "object_text": superseded_claim.object_text}
                if superseded_claim
                else None
            ),
            "evidence": [
                {
                    "source_type": e.source_type,
                    "source_id": e.source_id,
                    "title": (sources.get((e.source_type, e.source_id)).title
                              if sources.get((e.source_type, e.source_id)) else None),
                    "excerpt": e.excerpt,
                    "role": e.role,
                    "confidence": e.confidence,
                }
                for e in evidence_rows
            ],
            "provenance": {
                "source_type": claim.source_type,
                "source_id": claim.source_id,
                "created_by": claim.created_by,
            },
        }

    async def _claim_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        claim: KnowledgeClaim,
        access: Any,
    ) -> bool:
        if claim.subject_type != "topic":
            source = (
                await db.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.organization_id == organization_id,
                        KnowledgeSource.source_type == claim.subject_type,
                        KnowledgeSource.source_id == claim.subject_id,
                    )
                )
            ).scalar_one_or_none()
            return source is not None and self._visible(
                access, _load_provenance(source.provenance_json)
            )
        evidence_rows = list(
            (
                await db.execute(
                    select(KnowledgeEvidence).where(
                        KnowledgeEvidence.organization_id == organization_id,
                        KnowledgeEvidence.claim_id == claim.id,
                    ).limit(_MAX_EVIDENCE)
                )
            ).scalars().all()
        )
        if not evidence_rows:
            return False
        sources = list(
            (
                await db.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.organization_id == organization_id,
                        KnowledgeSource.source_type.in_({e.source_type for e in evidence_rows}),
                        KnowledgeSource.source_id.in_({e.source_id for e in evidence_rows}),
                    )
                )
            ).scalars().all()
        )
        return any(
            self._visible(access, _load_provenance(s.provenance_json)) for s in sources
        )

    async def _sources_for_map(
        self, db: AsyncSession, organization_id: str, keys: set[tuple[str, str]]
    ) -> dict[tuple[str, str], KnowledgeSource]:
        """Bounded lookup of canonical sources by (type, id) keys."""
        if not keys:
            return {}
        rows = list(
            (
                await db.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.organization_id == organization_id,
                        KnowledgeSource.source_type.in_({k[0] for k in keys}),
                        KnowledgeSource.source_id.in_({k[1] for k in keys}),
                    ).limit(len(keys))
                )
            ).scalars().all()
        )
        return {(s.source_type, s.source_id): s for s in rows}

    async def _claim_resolution(
        self, db: AsyncSession, organization_id: str, claim_ids: list[str]
    ) -> list[dict[str, Any]]:
        if not claim_ids:
            return []
        rows = (
            await db.execute(
                select(KnowledgeClaim).where(
                    KnowledgeClaim.organization_id == organization_id,
                    KnowledgeClaim.id.in_(claim_ids),
                )
            )
        ).scalars().all()
        return [self._claim_shape(c) for c in rows]

    @staticmethod
    def _claim_shape(claim: Optional[KnowledgeClaim], with_evidence: bool = False) -> Optional[dict[str, Any]]:
        if claim is None:
            return None
        return {
            "id": claim.id,
            "subject_type": claim.subject_type,
            "subject_id": claim.subject_id,
            "predicate": claim.predicate,
            "object_text": claim.object_text,
            "claim_type": claim.claim_type,
            "status": claim.status,
            "authority_level": claim.authority_level,
            "authority_label": _AUTHORITY_LABELS.get(claim.authority_level, "unverified"),
            "confidence": claim.confidence,
            "topic_id": claim.topic_id,
            "valid_from": ensure_aware(claim.valid_from).isoformat() if claim.valid_from else None,
            "valid_to": ensure_aware(claim.valid_to).isoformat() if claim.valid_to else None,
            "superseded_by": claim.superseded_by,
            "last_seen": ensure_aware(claim.last_seen).isoformat() if claim.last_seen else None,
        }


def _log2(value: float) -> float:
    import math

    return math.log2(max(value, 1.0))


synthesis_engine = SynthesisEngine()