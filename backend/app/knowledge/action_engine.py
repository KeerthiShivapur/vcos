"""Slice 4E.5 — Knowledge Intelligence Operating Layer (Knowledge-to-Action).

4E.1-4E.4 build the canonical knowledge substrate and turn it into
intelligence ("what does the company know / what does it mean"). 4E.5 makes
that intelligence OPERATIONAL: the system continuously turns organizational
knowledge into insights, gaps, risks, decisions and recommendations — and it
recommends and orchestrates, never silently mutating company state.

    knowledge substrate (claims, topics, sources, relations)
      -> KnowledgeActionEngine.materialize: one deterministic pass
           -> universal KnowledgeIntelInsight rows (12 kinds, exact-once by
              (kind, fingerprint), lifecycle active -> acknowledged ->
              resolved, rows never deleted, audit events per transition)
           -> meaningful in-app notifications for high/critical insights
      -> read surfaces (all governed, bounded, deterministic):
           insights / detail (with evidence lineage)
           temporal state at a past date (what was true, what replaced it)
           evolution trace (why did it change, what superseded it)
           impact propagation chains (vendor -> ... -> customers -> risks)
           coverage map (per business area, with weak-area reasons)
           health center (score + drill-down counts + reasons)
           executive brief (since yesterday: what matters and top attention)
      -> recommendation lifecycle (detected -> candidate -> reviewed ->
           accepted/rejected -> converted -> executed -> verified), where
           conversion calls the GOVERNED tasks/decisions operating layers
           only on an explicit user action with an audited trail.

Design laws (mirroring the 4E series):
* deterministic first — every insight is a pure function of persisted claims;
  no LLM invents anything; wording is generated from the evidence,
* no silent mutations — the engine NEVER creates tasks or decisions; it only
  materializes insight/recommendation rows. Conversion is a user action that
  goes through the governed task/decision services,
* governance inherited — every read resolves caller access BEFORE assembly
  and filters insight rows by the visibility of their evidence claims,
* exact-once — (kind, fingerprint) unique keys; replays update, never
  duplicate; conditions that clear are resolved, never deleted,
* bounded, change-driven — one capped pass over topics (100) and claims
  (400), per-kind and total insight caps, capped propagation breadth/depth.
"""

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.intelligence.company_context import CallerAccess, resolve_caller_access
from app.knowledge.canonical_service import _load_provenance, now_utc
from app.knowledge.intelligence_engine import (
    _clean_topic_name,
    _fingerprint,
    _snippet,
    intelligence_engine,
)
from app.knowledge.synthesis_engine import (
    _AUTHORITY_NORM,
    _json_loads,
    extract_facets,
    synthesis_engine,
)
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEvidence,
    KnowledgeIntelInsight,
    KnowledgeIntelInsightEvent,
    KnowledgeRecommendation,
    KnowledgeRelation,
    KnowledgeSource,
    KnowledgeTopic,
)
from app.models.user import User

logger = logging.getLogger("vcos.knowledge.action")

# ---------------------------------------------------------------------------
# bounds — one capped pass, capped outputs
# ---------------------------------------------------------------------------

_MAX_TOPICS_SCAN = 100
_MAX_CLAIM_SCAN = 400
_MAX_INSIGHTS_PER_KIND = 12
_MAX_INSIGHTS = 64
_MAX_NOTIFY_USERS = 30
_MAX_PROPAGATION_NODES = 120
_MAX_PROPAGATION_DEPTH = 4
_MAX_TRACE = 60
_INSIGHT_WINDOW_DAYS = 7
_GAP_HORIZON_DAYS = 30
_GAP_CRITICAL_DAYS = 5

_FRESH_OK = frozenset({"very_high", "high", "medium"})

_INSIGHT_KINDS = frozenset(
    {
        "discovery", "change", "contradiction", "risk", "opportunity", "gap",
        "dependency", "impact", "trend", "recommendation",
        "verification_required", "decision_required",
    }
)

# ---------------------------------------------------------------------------
# deterministic rules data
# ---------------------------------------------------------------------------

# Required knowledge facets for an operational topic with an approaching
# date: keywords that count as "an authoritative source exists".
_REQUIRED_FACETS: list[tuple[str, tuple[str, ...]]] = [
    ("rollback plan", ("rollback", "roll-back", "fallback", "revert")),
    ("security sign-off", ("security sign", "security approval", "security review", "security clearance")),
    ("vendor contingency", ("contingency", "backup vendor", "alternate vendor", "redundant path")),
    ("final customer approval", ("customer approval", "client approval", "stakeholder approval", "customer sign")),
    ("budget approval", ("budget approval", "approved budget", "budget sign", "funding approved")),
]

_CUSTOMER_KEYWORDS = (
    "customer", "client", "renewal", "opportunity", "lead", "contract",
    "escalation", "onboarding", "churn", "account",
)

_AREA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Strategy": ("strategy", "vision", "roadmap", "goal", "objective", "direction", "positioning"),
    "Product": ("product", "feature", "release", "backlog", "sprint", "user story", "usability"),
    "Engineering": ("engineering", "architecture", "deployment", "infrastructure", "code", "api", "platform", "technical", "security", "devops"),
    "Sales": ("sales", "pipeline", "quota", "proposal", "deal", "lead", "revenue forecast"),
    "Marketing": ("marketing", "campaign", "brand", "content", "seo", "demand", "advertising"),
    "Finance": ("finance", "budget", "cost", "spend", "forecast", "expense", "revenue", "pricing", "currency", "audit"),
    "HR": ("hr", "hiring", "hiring", "onboarding", "compensation", "benefit", "policy", "people", "recruiting"),
    "Operations": ("operations", "ops", "workflow", "process", "sop", "runbook", "vendor", "supply", "delivery", "rollout"),
    "Customers": ("customer", "client", "renewal", "contract", "escalation", "churn", "account", "support", "onboarding"),
}

_SEVERITY_WEIGHT = {"low": 0.25, "medium": 0.5, "high": 0.8, "critical": 1.0}


def _priority(confidence: float, severity: str, urgency: str) -> float:
    """Deterministic, explainable priority: confidence dominates, then
    severity, then urgency (all 0..1)."""
    return round(
        confidence * 0.6 + _SEVERITY_WEIGHT.get(severity, 0.5) * 0.25
        + _SEVERITY_WEIGHT.get(urgency, 0.5) * 0.15,
        3,
    )


def _covered_by(facets_keywords: tuple[str, ...], texts: list[str]) -> bool:
    lowered = " ".join(t.lower() for t in texts if t)
    return any(k in lowered for k in facets_keywords)


def _area_of(topic_name: str, categories: list[str], keywords: list[str]) -> Optional[str]:
    blob = " ".join([topic_name or "", *categories, *keywords]).lower()
    best_area: Optional[str] = None
    best_hits = 0
    for area, keys in _AREA_KEYWORDS.items():
        hits = sum(1 for k in keys if k in blob)
        if hits > best_hits:
            best_hits, best_area = hits, area
    return best_area if best_hits else None


class KnowledgeActionEngine:
    """The 4E.5 operating layer on top of the 4E.4 intelligence engine."""

    # ------------------------------------------------------------ access

    async def _access(self, db: AsyncSession, *, organization_id: str, user: Any) -> CallerAccess:
        if user is None:
            return CallerAccess(
                organization_id=organization_id,
                user_id="system",
                employee_id=None,
                org_wide=True,
            )
        return await resolve_caller_access(db, organization_id=organization_id, user=user)

    async def _visible_claims(
        self, db: AsyncSession, *, organization_id: str, claim_ids: list[str], access: CallerAccess
    ) -> list[KnowledgeClaim]:
        if not claim_ids:
            return []
        rows = list(
            (
                await db.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.id.in_(claim_ids[:40]),
                    )
                )
            ).scalars().all()
        )
        visible = []
        for claim in rows:
            if await synthesis_engine._claim_visible(
                db, organization_id=organization_id, claim=claim, access=access
            ):
                visible.append(claim)
        return visible

    # ----------------------------------------------------- materialization

    async def materialize(
        self, db: AsyncSession, *, organization_id: str, user: Any = None,
    ) -> dict[str, int]:
        """One deterministic pass: derive every insight candidate from the
        persisted substrate and upsert exactly-once (never deleting history,
        resolving conditions that cleared). Notifications are emitted for new
        high/critical insights."""
        access = CallerAccess(
            organization_id=organization_id, user_id="system", employee_id=None, org_wide=True
        )
        scanned = await intelligence_engine._scan_topics(
            db, organization_id=organization_id, access=access
        )
        current_fingerprints: set[tuple[str, str]] = set()
        candidates: list[dict[str, Any]] = []

        for topic_id, entry in scanned.items():
            topic: KnowledgeTopic = entry["topic"]
            name = _clean_topic_name(topic.name) or topic.name
            claims = [c for c in entry["claims"] if c.status != "superseded"]
            if not claims:
                continue
            sources = entry["sources"]
            evolution = await intelligence_engine._synthesis_evolution(
                db, organization_id=organization_id, topic_id=topic_id, access=access
            )
            current = evolution[-1] if evolution else None
            contradictions = synthesis_engine._detect_contradictions(claims)
            unresolved = [p for p in contradictions if p["resolution"] == "newer valid_from"]

            latest_authority = max((c.authority_level for c in claims), default=1)
            newest_source = max(
                (sources.get((c.subject_type, c.subject_id)) for c in claims),
                key=lambda s: ensure_aware(s.source_updated_at)
                if s and s.source_updated_at else now_utc(),
                default=None,
            )
            freshness = newest_source.freshness_label if newest_source else "stale"
            categories = sorted(
                {
                    str((_load_provenance(sources.get((c.subject_type, c.subject_id)).provenance_json) or {}).get("category") or "")
                    for c in claims
                    if sources.get((c.subject_type, c.subject_id))
                }
            )
            keywords = sorted(
                {
                    kw
                    for c in claims
                    if sources.get((c.subject_type, c.subject_id))
                    for kw in (_load_provenance(sources.get((c.subject_type, c.subject_id)).provenance_json) or {}).get("keywords") or []
                }
            )
            claim_texts = [c.object_text for c in claims]
            all_texts = [*claim_texts, *[c.object_text for c in evolution], name]

            # 1. change — understanding superseded in the window
            now = now_utc()
            for index, claim in enumerate(evolution):
                prior = evolution[index - 1] if index > 0 else None
                if ensure_aware(claim.valid_from) < now - timedelta(days=_INSIGHT_WINDOW_DAYS):
                    continue
                if prior is None or prior.object_text == claim.object_text:
                    continue
                fingerprint = _fingerprint("change", topic_id, claim.id)
                current_fingerprints.add(("change", fingerprint))
                state_text = claim.object_text.lower()
                severity = "high" if ("contested" in state_text or "escalating" in state_text) else "medium"
                candidates.append(
                    {
                        "kind": "change",
                        "fingerprint": fingerprint,
                        "title": f"Understanding changed: '{name}'",
                        "summary": (
                            f"From: {_snippet(prior.object_text, 200)} "
                            f"\u2192 To: {_snippet(claim.object_text, 200)}"
                        ),
                        "severity": severity,
                        "confidence": round(claim.confidence, 3),
                        "impact": "medium",
                        "urgency": "medium",
                        "source_claims": [claim.id, prior.id],
                        "source_entities": [],
                        "evidence": [claim.id],
                        "topic_id": topic_id,
                        "topic_name": name,
                    }
                )

            # 2. contradiction — equal-authority unresolved pair
            for pair in unresolved[:_MAX_INSIGHTS_PER_KIND]:
                fingerprint = _fingerprint("contradiction", topic_id, pair["claim_a"], pair["claim_b"])
                current_fingerprints.add(("contradiction", fingerprint))
                candidates.append(
                    {
                        "kind": "contradiction",
                        "fingerprint": fingerprint,
                        "title": f"Contradiction on '{name}'",
                        "summary": (
                            f"'{pair['facet_label']}' {pair['value_a']} vs {pair['value_b']} has "
                            f"equal-authority sources; the losing side ('{pair['value_b']}') may be "
                            "stale documentation."
                        ),
                        "severity": "high",
                        "confidence": 0.85,
                        "impact": "high",
                        "urgency": "high",
                        "source_claims": [pair["claim_a"], pair["claim_b"]],
                        "source_entities": [],
                        "evidence": [pair["claim_a"], pair["claim_b"]],
                        "topic_id": topic_id,
                        "topic_name": name,
                    }
                )

            # 3. risk — escalating pattern or stale critical knowledge
            risk_reason: Optional[str] = None
            if current and "escalating" in current.object_text.lower():
                risk_reason = (
                    f"Repeated observations around '{name}' signal an escalating "
                    "pattern; current understanding flags it as escalating."
                )
            elif latest_authority >= 4 and freshness not in _FRESH_OK:
                risk_reason = (
                    f"Critically authoritative knowledge on '{name}' is {freshness}; "
                    "a decision could be driven by outdated facts."
                )
            if risk_reason:
                fingerprint = _fingerprint("risk", topic_id, "escalating" if "escalating" in risk_reason else "stale_critical")
                current_fingerprints.add(("risk", fingerprint))
                candidates.append(
                    {
                        "kind": "risk",
                        "fingerprint": fingerprint,
                        "title": f"Risk around '{name}'",
                        "summary": risk_reason,
                        "severity": "high" if latest_authority >= 4 else "medium",
                        "confidence": 0.75,
                        "impact": "high",
                        "urgency": "high",
                        "source_claims": [c.id for c in claims[:_MAX_INSIGHTS_PER_KIND]],
                        "source_entities": [],
                        "evidence": [c.id for c in claims[:6]],
                        "topic_id": topic_id,
                        "topic_name": name,
                    }
                )

            # 4. gap — approaching date without a required authoritative facet
            date_facets = [f for c in all_texts for f in extract_facets(c) if f["key"].startswith("date:")]
            for facet in date_facets[:3]:
                when = self._facet_date(facet)
                if when is None:
                    continue
                days_left = (when - date.today()).days
                if days_left > _GAP_HORIZON_DAYS:
                    continue
                for facet_name, facet_keywords in _REQUIRED_FACETS:
                    if _covered_by(facet_keywords, all_texts):
                        continue
                    fingerprint = _fingerprint("gap", topic_id, facet_name)
                    current_fingerprints.add(("gap", fingerprint))
                    severity = "high" if days_left <= _GAP_CRITICAL_DAYS else ("medium" if days_left <= 14 else "low")
                    candidates.append(
                        {
                            "kind": "gap",
                            "fingerprint": fingerprint,
                            "title": f"Missing: {facet_name} for '{name}'",
                            "summary": (
                                f"'{name}' is dated {facet['raw']} ({days_left} days away) but "
                                f"'{facet_name}' has no authoritative source."
                            ),
                            "severity": severity,
                            "confidence": 0.8,
                            "impact": "high" if severity == "high" else "medium",
                            "urgency": "high" if severity == "high" else "medium",
                            "source_claims": [c.id for c in claims[:6]],
                            "source_entities": [],
                            "evidence": [c.id for c in claims[:4]],
                            "topic_id": topic_id,
                            "topic_name": name,
                        }
                    )

            # 5. verification_required — thin or stale support
            if current is not None:
                sources_for = [
                    sources.get((c.subject_type, c.subject_id))
                    for c in claims[:4]
                    if sources.get((c.subject_type, c.subject_id))
                ]
                single_source = len({s.source_id for s in sources_for}) <= 1
                stale_support = any(
                    (s.freshness_label or "stale") not in _FRESH_OK for s in sources_for[:4]
                )
                if current.confidence < 0.5 or (single_source and (stale_support or freshness not in _FRESH_OK)):
                    fingerprint = _fingerprint("verification_required", topic_id)
                    current_fingerprints.add(("verification_required", fingerprint))
                    reasons = []
                    if current.confidence < 0.5:
                        reasons.append(f"computed confidence is {round(current.confidence, 2)}")
                    if single_source:
                        reasons.append("only one supporting source")
                    if stale_support:
                        reasons.append("supporting sources are stale")
                    candidates.append(
                        {
                            "kind": "verification_required",
                            "fingerprint": fingerprint,
                            "title": f"Verify '{name}'",
                            "summary": (
                                f"'{name}' may be unreliable: {', '.join(reasons)}. "
                                "Confirm against an authoritative source before acting on it."
                            ),
                            "severity": "medium",
                            "confidence": 0.7,
                            "impact": "medium",
                            "urgency": "medium",
                            "source_claims": [current.id],
                            "source_entities": [],
                            "evidence": [c.id for c in claims[:4]],
                            "topic_id": topic_id,
                            "topic_name": name,
                        }
                    )

            # 6. dependency — topics share evidence entities
            subjects = {(c.subject_type, c.subject_id) for c in claims}
            other_topics = self._topics_sharing_subjects(
                scanned, topic_id, subjects
            )
            for other_id, shared in list(other_topics.items())[:_MAX_INSIGHTS_PER_KIND]:
                other = scanned[other_id]["topic"]
                other_name = _clean_topic_name(other.name) or other.name
                fingerprint = _fingerprint("dependency", topic_id, other_id)
                current_fingerprints.add(("dependency", fingerprint))
                candidates.append(
                    {
                        "kind": "dependency",
                        "fingerprint": fingerprint,
                        "title": f"'{name}' and '{other_name}' are connected",
                        "summary": (
                            f"'{name}' and '{other_name}' share {len(shared)} evidence "
                            "entities — a change to one can affect the other."
                        ),
                        "severity": "low",
                        "confidence": 0.6,
                        "impact": "medium",
                        "urgency": "low",
                        "source_claims": [c.id for c in claims[:6]],
                        "source_entities": [{"type": s, "id": e} for s, e in list(shared)[:6]],
                        "evidence": [c.id for c in claims[:4]],
                        "topic_id": topic_id,
                        "topic_name": name,
                    }
                )

            # 7. trend — monotonic facet trajectory over the evolution
            for trend in self._trends(evolution):
                fingerprint = _fingerprint("trend", topic_id, trend["facet"])
                current_fingerprints.add(("trend", fingerprint))
                candidates.append(
                    {
                        "kind": "trend",
                        "fingerprint": fingerprint,
                        "title": f"'{name}' is {trend['direction']}",
                        "summary": trend["summary"],
                        "severity": "medium",
                        "confidence": 0.65,
                        "impact": "medium",
                        "urgency": "medium",
                        "source_claims": trend["claims"],
                        "source_entities": [],
                        "evidence": trend["claims"],
                        "topic_id": topic_id,
                        "topic_name": name,
                    }
                )

            # 8. discovery — the topic itself is new
            if ensure_aware(topic.created_at) >= now - timedelta(days=_INSIGHT_WINDOW_DAYS):
                fingerprint = _fingerprint("discovery", topic_id)
                current_fingerprints.add(("discovery", fingerprint))
                candidates.append(
                    {
                        "kind": "discovery",
                        "fingerprint": fingerprint,
                        "title": f"New knowledge arrived: '{name}'",
                        "summary": (
                            f"'{name}' entered the company knowledge base "
                            f"{_INSIGHT_WINDOW_DAYS} days ago with "
                            f"{len({c.subject_type for c in claims})} source families."
                        ),
                        "severity": "low",
                        "confidence": 0.6,
                        "impact": "low",
                        "urgency": "low",
                        "source_claims": [c.id for c in claims[:6]],
                        "source_entities": [],
                        "evidence": [c.id for c in claims[:4]],
                        "topic_id": topic_id,
                        "topic_name": name,
                    }
                )

            # 9. impact — the latest change's blast radius
            if current is not None and current.status != "superseded":
                impact_result = await intelligence_engine.impact(
                    db, organization_id=organization_id, topic_name=topic.name, user=None,
                )
                if impact_result and impact_result.get("affected", {}).get("total", 0) >= 1:
                    affected = impact_result["affected"]
                    by_family = {k: v["count"] for k, v in affected.get("by_family", {}).items()}
                    fingerprint = _fingerprint("impact", topic_id, current.id)
                    current_fingerprints.add(("impact", fingerprint))
                    candidates.append(
                        {
                            "kind": "impact",
                            "fingerprint": fingerprint,
                            "title": f"Change to '{name}' affects {affected['total']} entities",
                            "summary": (
                                f"Current knowledge on '{name}' is connected to "
                                f"{affected['total']} affected entities "
                                f"({', '.join(f'{k}: {v}' for k, v in sorted(by_family.items()))})."
                            ),
                            "severity": "medium",
                            "confidence": round(current.confidence, 3),
                            "impact": "high" if affected["total"] >= 5 else "medium",
                            "urgency": "medium",
                            "source_claims": [current.id],
                            "source_entities": [
                                {"type": k, "id": e["id"]}
                                for k, v in affected.get("by_family", {}).items()
                                for e in v.get("entities", [])[:6]
                            ],
                            "evidence": [current.id],
                            "topic_id": topic_id,
                            "topic_name": name,
                        }
                    )

            # 10. opportunity — momentum on a customer-facing topic
            if any(kw in name.lower() for kw in _CUSTOMER_KEYWORDS):
                if any(c.subject_type == "pattern" for c in claims) or len(claims) >= 4:
                    fingerprint = _fingerprint("opportunity", topic_id)
                    current_fingerprints.add(("opportunity", fingerprint))
                    candidates.append(
                        {
                            "kind": "opportunity",
                            "fingerprint": fingerprint,
                            "title": f"Momentum in '{name}'",
                            "summary": (
                                f"'{name}' is customer-facing and accumulating evidence "
                                f"({len(claims)} claims, {len({c.subject_type for c in claims})} families) "
                                "— worth an explicit read on whether this is opportunity or risk."
                            ),
                            "severity": "low",
                            "confidence": 0.55,
                            "impact": "medium",
                            "urgency": "low",
                            "source_claims": [c.id for c in claims[:6]],
                            "source_entities": [],
                            "evidence": [c.id for c in claims[:4]],
                            "topic_id": topic_id,
                            "topic_name": name,
                        }
                    )

        # recommendation insights — wrap the 4E.4 materializer (exact-once there)
        rec_rows = await intelligence_engine.recommendations(
            db, organization_id=organization_id, user=None, limit=_MAX_INSIGHTS_PER_KIND * 3
        )
        for item in rec_rows.get("recommendations", []):
            if item["risk"] not in ("high", "medium"):
                continue
            fingerprint = _fingerprint("recommendation", item["kind"], item["fingerprint"])
            current_fingerprints.add(("recommendation", fingerprint))
            candidates.append(
                {
                    "kind": "recommendation",
                    "fingerprint": fingerprint,
                    "title": f"Recommended: {item['kind'].replace('_', ' ')}",
                    "summary": item["reason"],
                    "severity": "high" if item["risk"] == "high" else "medium",
                    "confidence": item["confidence"],
                    "impact": "high" if item["risk"] == "high" else "medium",
                    "urgency": "high" if item["risk"] == "high" else "medium",
                    "source_claims": item.get("evidence", [])[:12],
                    "source_entities": item.get("entities", []),
                    "evidence": item.get("evidence", [])[:12],
                    "topic_id": None,
                    "topic_name": None,
                }
            )

        # decision_required — active gap/risk insight + no open decision + no
        # accepted recommendation already steering the topic
        active_by_topic = self._active_insights_by_topic(
            candidates, ("gap", "risk", "contradiction")
        )
        for topic_id, (kind, candidate) in active_by_topic.items():
            if await self._open_decision_for(
                db, organization_id=organization_id, topic_name=candidate["topic_name"]
            ):
                continue
            fingerprint = _fingerprint("decision_required", topic_id, kind)
            current_fingerprints.add(("decision_required", fingerprint))
            candidates.append(
                {
                    "kind": "decision_required",
                    "fingerprint": fingerprint,
                    "title": f"Decision needed: '{candidate['topic_name']}'",
                    "summary": (
                        f"An unresolved {kind} around '{candidate['topic_name']}' has no "
                        "open decision or accepted recommendation — leadership needs to decide."
                    ),
                    "severity": "high",
                    "confidence": 0.7,
                    "impact": "high",
                    "urgency": "high",
                    "source_claims": candidate.get("source_claims", [])[:6],
                    "source_entities": [],
                    "evidence": candidate.get("evidence", [])[:6],
                    "topic_id": topic_id,
                    "topic_name": candidate["topic_name"],
                }
            )

        # exact-once persistence + conditions-cleared resolution
        existing = list(
            (
                await db.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.organization_id == organization_id,
                    ).order_by(KnowledgeIntelInsight.created_at.desc()).limit(_MAX_INSIGHTS * 3)
                )
            ).scalars().all()
        )
        by_fingerprint: dict[tuple[str, str], KnowledgeIntelInsight] = {
            (r.kind, r.fingerprint): r for r in existing
        }
        created = updated = resolved = notified = 0
        for row in existing:
            if row.status != "active" or row.resolved_by is not None:
                continue
            if (row.kind, row.fingerprint) not in current_fingerprints:
                row.status = "resolved"
                row.resolved_at = now
                row.updated_at = now
                resolved += 1
        per_kind: dict[str, int] = {}
        for item in candidates:
            per_kind[item["kind"]] = per_kind.get(item["kind"], 0) + 1
            if per_kind[item["kind"]] > _MAX_INSIGHTS_PER_KIND:
                continue
            if sum(per_kind.values()) > _MAX_INSIGHTS:
                break
            key = (item["kind"], item["fingerprint"])
            row = by_fingerprint.get(key)
            priority = _priority(item["confidence"], item["severity"], item["urgency"])
            if row is None:
                row = KnowledgeIntelInsight(
                    organization_id=organization_id,
                    kind=item["kind"],
                    title=item["title"],
                    summary=item["summary"],
                    severity=item["severity"],
                    confidence=item["confidence"],
                    impact=item["impact"],
                    urgency=item["urgency"],
                    priority_score=priority,
                    status="active",
                    fingerprint=item["fingerprint"],
                    source_event=f"insight.{item['kind']}",
                    source_claims_json=json.dumps(item["source_claims"]),
                    source_entities_json=json.dumps(item["source_entities"]),
                    evidence_json=json.dumps(item["evidence"]),
                    topic_id=item.get("topic_id"),
                    topic_name=item.get("topic_name"),
                )
                db.add(row)
                await db.flush()
                db.add(
                    KnowledgeIntelInsightEvent(
                        organization_id=organization_id,
                        insight_id=row.id,
                        action="created",
                        actor_id="system",
                        details_json=json.dumps(
                            {"priority_score": priority, "severity": item["severity"]}
                        ),
                    )
                )
                created += 1
                if item["severity"] in ("high", "critical"):
                    notified += await self._notify(
                        db, organization_id=organization_id, insight=row
                    )
            else:
                row.title = item["title"]
                row.summary = item["summary"]
                row.severity = item["severity"]
                row.confidence = item["confidence"]
                row.impact = item["impact"]
                row.urgency = item["urgency"]
                row.priority_score = priority
                row.source_claims_json = json.dumps(item["source_claims"])
                row.source_entities_json = json.dumps(item["source_entities"])
                row.evidence_json = json.dumps(item["evidence"])
                if row.resolved_by is None and row.status == "resolved":
                    row.status = "active"
                    row.resolved_at = None
                row.updated_at = now
                updated += 1
        await db.flush()
        return {"created": created, "updated": updated, "resolved": resolved, "notified": notified}

    # -------------------------------------------------------- helpers

    def _facet_date(self, facet: dict[str, Any]) -> Optional[date]:
        if facet["key"] == "date:iso":
            try:
                return date.fromisoformat(str(facet["value"])[:10])
            except ValueError:
                return None
        if facet["key"] == "date:monthday":
            month, day = facet["value"]
            year = date.today().year
            when = date(year, month, day)
            if when < date.today() - timedelta(days=_GAP_HORIZON_DAYS):
                when = date(year + 1, month, day)
            return when
        return None

    def _topics_sharing_subjects(
        self,
        scanned: dict[str, dict[str, Any]],
        topic_id: str,
        subjects: set[tuple[str, str]],
    ) -> dict[str, list[tuple[str, str]]]:
        shared: dict[str, list[tuple[str, str]]] = {}
        for other_id, other_entry in scanned.items():
            if other_id == topic_id:
                continue
            other_subjects = {
                (c.subject_type, c.subject_id) for c in other_entry["claims"]
            }
            overlap = subjects & other_subjects
            if overlap:
                shared[other_id] = sorted(overlap, key=lambda item: (item[0], item[1]))
        return shared

    def _trends(self, evolution: list[KnowledgeClaim]) -> list[dict[str, Any]]:
        if len(evolution) < 2:
            return []
        per_facet: dict[str, list[tuple[str, float]]] = {}
        seen: dict[str, set[str]] = {}
        for claim in evolution:
            for facet in extract_facets(claim.object_text):
                if not facet["key"].startswith(("currency", "percent", "duration", "quantity")):
                    continue
                value = facet["value"]
                if isinstance(value, float):
                    marker = (facet["key"], facet["raw"])
                    if marker in seen.get(facet["key"], set()):
                        continue
                    seen.setdefault(facet["key"], set()).add(marker)
                    per_facet.setdefault(facet["key"], []).append(
                        (ensure_aware(claim.valid_from).isoformat(), value)
                    )
        trends: list[dict[str, Any]] = []
        for key, series in per_facet.items():
            if len(series) < 2:
                continue
            values = [v for _, v in series]
            rising = all(values[i + 1] > values[i] for i in range(len(values) - 1))
            falling = all(values[i + 1] < values[i] for i in range(len(values) - 1))
            if not (rising or falling):
                continue
            direction = "rising" if rising else "falling"
            trends.append(
                {
                    "facet": key,
                    "direction": direction,
                    "summary": (
                        f"'{key}' has been {direction}: "
                        + " \u2192 ".join(str(v) for v in values)
                        + f" across {len(series)} understanding versions."
                    ),
                    "claims": [c.id for c in evolution[-3:]],
                }
            )
        return trends

    @staticmethod
    def _active_insights_by_topic(
        candidates: list[dict[str, Any]], kinds: tuple[str, ...]
    ) -> dict[str, tuple[str, dict[str, Any]]]:
        out: dict[str, tuple[str, dict[str, Any]]] = {}
        for item in candidates:
            if item["kind"] not in kinds or not item.get("topic_id"):
                continue
            key = item["topic_id"]
            if key not in out or _SEVERITY_WEIGHT.get(item["severity"], 0) > _SEVERITY_WEIGHT.get(
                out[key][1]["severity"], 0
            ):
                out[key] = (item["kind"], item)
        return out

    async def _open_decision_for(
        self, db: AsyncSession, *, organization_id: str, topic_name: Optional[str]
    ) -> bool:
        if not topic_name:
            return False
        from app.knowledge.decision_service import decision_service

        for status in ("proposed", "in_progress"):
            rows = await decision_service.list_all(
                db, organization_id=organization_id, status=status,
                search=topic_name.lower(), limit=5,
            )
            if rows:
                return True
        return False

    async def _notify(
        self, db: AsyncSession, *, organization_id: str, insight: KnowledgeIntelInsight,
    ) -> int:
        from app.services.notification_service import NotificationService

        users = list(
            (
                await db.execute(
                    select(User).where(
                        User.organization_id == organization_id,
                        User.status == "active",
                    ).order_by(User.created_at.asc()).limit(_MAX_NOTIFY_USERS)
                )
            ).scalars().all()
        )
        for user in users:
            await NotificationService().create(
                db,
                organization_id=organization_id,
                recipient_id=user.id,
                type="knowledge.insight",
                title=insight.title,
                body=(
                    f"{insight.summary} Confidence {round(insight.confidence, 2)}, "
                    f"{insight.impact} impact. Review in the Knowledge Command Center."
                ),
                actor_id="system",
                priority="high" if insight.severity == "critical" else "normal",
                entity_type="knowledge_insight",
                entity_id=insight.id,
                metadata={
                    "kind": insight.kind,
                    "severity": insight.severity,
                    "insight_id": insight.id,
                },
            )
        return len(users)

    # ------------------------------------------------------- read surfaces

    async def insights(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 40,
    ) -> dict[str, Any]:
        access = await self._access(db, organization_id=organization_id, user=user)
        await self.materialize(db, organization_id=organization_id)
        rows = (
            await db.execute(
                select(KnowledgeIntelInsight)
                .where(
                    KnowledgeIntelInsight.organization_id == organization_id,
                    *([KnowledgeIntelInsight.kind == kind] if kind else []),
                    *([KnowledgeIntelInsight.status == status] if status else []),
                    *([KnowledgeIntelInsight.severity == severity] if severity else []),
                )
                .order_by(KnowledgeIntelInsight.priority_score.desc(), KnowledgeIntelInsight.updated_at.desc())
                .limit(limit + 1)
            )
        ).scalars().all()
        out: list[dict[str, Any]] = []
        for row in rows[:limit]:
            claims = await self._visible_claims(
                db, organization_id=organization_id,
                claim_ids=_json_loads(row.source_claims_json, []), access=access,
            )
            if not access.org_wide and not claims:
                continue
            out.append(self._shape(db, organization_id=organization_id, row=row, claims=claims))
        kinds = {i["kind"]: 0 for i in out}
        for i in out:
            kinds[i["kind"]] += 1
        return {
            "total": len(out),
            "kinds": sorted(kinds),
            "by_kind": kinds,
            "scope": "org" if access.org_wide else "project",
            "insights": out,
        }

    async def insight_detail(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        insight_id: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        access = await self._access(db, organization_id=organization_id, user=user)
        row = (
            await db.execute(
                select(KnowledgeIntelInsight).where(
                    KnowledgeIntelInsight.organization_id == organization_id,
                    KnowledgeIntelInsight.id == insight_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        claims = await self._visible_claims(
            db, organization_id=organization_id,
            claim_ids=_json_loads(row.source_claims_json, []), access=access,
        )
        if not access.org_wide and not claims:
            return None
        events = list(
            (
                await db.execute(
                    select(KnowledgeIntelInsightEvent)
                    .where(KnowledgeIntelInsightEvent.insight_id == insight_id)
                    .order_by(KnowledgeIntelInsightEvent.created_at.asc())
                    .limit(50)
                )
            ).scalars().all()
        )
        return {
            **self._shape(db, organization_id=organization_id, row=row, claims=claims),
            "lineage": {
                "claims": [
                    {
                        "id": c.id,
                        "statement": _snippet(c.object_text, 220),
                        "status": c.status,
                        "confidence": c.confidence,
                        "authority_level": c.authority_level,
                        "valid_from": ensure_aware(c.valid_from).isoformat(),
                        "source_type": c.subject_type,
                        "source_id": c.subject_id,
                    }
                    for c in claims
                ],
                "entities": _json_loads(row.source_entities_json, []),
                "source_event": row.source_event,
            },
            "audit": [
                {
                    "action": e.action,
                    "actor_id": e.actor_id,
                    "note": e.note,
                    "at": ensure_aware(e.created_at).isoformat(),
                }
                for e in events
            ],
        }

    async def acknowledge(
        self, db: AsyncSession, *, organization_id: str, insight_id: str, user: Any, note: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(KnowledgeIntelInsight).where(
                    KnowledgeIntelInsight.organization_id == organization_id,
                    KnowledgeIntelInsight.id == insight_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        now = now_utc()
        row.status = "acknowledged"
        row.acknowledged_at = now
        row.updated_at = now
        db.add(
            KnowledgeIntelInsightEvent(
                organization_id=organization_id, insight_id=insight_id,
                action="acknowledged",
                actor_id=getattr(user, "id", "system"),
                note=note,
            )
        )
        await db.flush()
        return {"id": row.id, "status": row.status, "acknowledged_at": ensure_aware(now).isoformat()}

    async def resolve(
        self, db: AsyncSession, *, organization_id: str, insight_id: str, user: Any, note: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(KnowledgeIntelInsight).where(
                    KnowledgeIntelInsight.organization_id == organization_id,
                    KnowledgeIntelInsight.id == insight_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        now = now_utc()
        row.status = "resolved"
        row.resolved_at = now
        row.resolved_by = getattr(user, "id", "system")
        row.updated_at = now
        db.add(
            KnowledgeIntelInsightEvent(
                organization_id=organization_id, insight_id=insight_id,
                action="resolved",
                actor_id=getattr(user, "id", "system"),
                note=note,
            )
        )
        await db.flush()
        return {"id": row.id, "status": row.status, "resolved_at": ensure_aware(now).isoformat()}

    def _shape(
        self, db: AsyncSession, *, organization_id: str, row: KnowledgeIntelInsight, claims: list[KnowledgeClaim],
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "kind": row.kind,
            "title": row.title,
            "summary": row.summary,
            "severity": row.severity,
            "confidence": row.confidence,
            "impact": row.impact,
            "urgency": row.urgency,
            "priority_score": row.priority_score,
            "status": row.status,
            "topic_id": row.topic_id,
            "topic_name": _clean_topic_name(row.topic_name) if row.topic_name else None,
            "created_at": ensure_aware(row.created_at).isoformat(),
            "updated_at": ensure_aware(row.updated_at).isoformat(),
            "evidence_count": len(_json_loads(row.evidence_json, [])),
            "claim_ids": [c.id for c in claims],
        }

    # ---------------------------------------------------- temporal reasoning

    async def state_at(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        as_of: datetime,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """What was true at ``as_of``: the understanding claim valid then,
        its replacement (what superseded it) and when."""
        access = await self._access(db, organization_id=organization_id, user=user)
        topic = (
            await db.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == organization_id,
                    KnowledgeTopic.name == topic_name,
                    KnowledgeTopic.status == "active",
                )
            )
        ).scalar_one_or_none()
        if topic is None:
            return None
        evolution = [
            c for c in await intelligence_engine._synthesis_evolution(
                db, organization_id=organization_id, topic_id=topic.id, access=access
            )
            if await synthesis_engine._claim_visible(
                db, organization_id=organization_id, claim=c, access=access
            )
        ]
        candidates = [
            c for c in evolution
            if ensure_aware(c.valid_from) <= as_of
            and (c.valid_to is None or ensure_aware(c.valid_to) > as_of)
        ]
        if not candidates:
            return None
        claim_at = max(candidates, key=lambda c: ensure_aware(c.valid_from))
        idx = evolution.index(claim_at)
        replacement = evolution[idx + 1] if idx + 1 < len(evolution) else None
        return {
            "topic": {"id": topic.id, "name": _clean_topic_name(topic.name)},
            "as_of": as_of.isoformat(),
            "state": {
                "claim_id": claim_at.id,
                "statement": claim_at.object_text,
                "confidence": claim_at.confidence,
                "authority_level": claim_at.authority_level,
                "valid_from": ensure_aware(claim_at.valid_from).isoformat(),
                "valid_to": ensure_aware(claim_at.valid_to).isoformat()
                if claim_at.valid_to else None,
            },
            "replaced_by": {
                "claim_id": replacement.id,
                "at": ensure_aware(replacement.valid_from).isoformat(),
                "statement": _snippet(replacement.object_text, 240),
            } if replacement else None,
        }

    async def evolution_trace(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """The full supersession chain: what was true, when it changed, what
        replaced it — old versions retained, never erased."""
        access = await self._access(db, organization_id=organization_id, user=user)
        topic = (
            await db.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == organization_id,
                    KnowledgeTopic.name == topic_name,
                    KnowledgeTopic.status == "active",
                )
            )
        ).scalar_one_or_none()
        if topic is None:
            return None
        evolution = [
            c for c in await intelligence_engine._synthesis_evolution(
                db, organization_id=organization_id, topic_id=topic.id, access=access
            )
            if await synthesis_engine._claim_visible(
                db, organization_id=organization_id, claim=c, access=access
            )
        ][:_MAX_TRACE]
        steps = []
        for index, claim in enumerate(evolution):
            prior = evolution[index - 1] if index > 0 else None
            steps.append(
                {
                    "claim_id": claim.id,
                    "at": ensure_aware(claim.valid_from).isoformat(),
                    "statement": claim.object_text,
                    "status": claim.status,
                    "confidence": claim.confidence,
                    "supersedes": prior.id if prior else None,
                    "replaced_by": claim.superseded_by,
                }
            )
        return {
            "topic": {"id": topic.id, "name": _clean_topic_name(topic.name)},
            "total": len(steps),
            "steps": steps,
        }

    # --------------------------------------------------- impact propagation

    async def propagation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        topic_name: str,
        user: Any,
        depth: int = 3,
    ) -> Optional[dict[str, Any]]:
        """Multi-hop impact chains: a change to this knowledge reaches
        entities that never mention it directly (vendor -> systems ->
        projects -> customers -> contracts -> risks)."""
        access = await self._access(db, organization_id=organization_id, user=user)
        topic = (
            await db.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == organization_id,
                    KnowledgeTopic.name == topic_name,
                    KnowledgeTopic.status == "active",
                )
            )
        ).scalar_one_or_none()
        if topic is None:
            return None
        scanned = await intelligence_engine._scan_topics(
            db, organization_id=organization_id, access=access
        )
        entry = scanned.get(topic.id)
        if entry is None:
            return None
        sources = entry["sources"]
        start = sorted({(c.subject_type, c.subject_id) for c in entry["claims"]})
        queue: list[tuple[str, str, int, str, str]] = [
            (stype, sid, 0, "evidence_of", topic.name) for stype, sid in start
        ]
        visited: set[tuple[str, str]] = set()
        hops: list[dict[str, Any]] = []
        max_depth = max(1, min(depth, _MAX_PROPAGATION_DEPTH))
        while queue and len(visited) < _MAX_PROPAGATION_NODES:
            stype, sid, level, relation, via = queue.pop(0)
            key = (stype, sid)
            if key in visited:
                continue
            visited.add(key)
            source = sources.get(key)
            hops.append(
                {
                    "entity_type": stype,
                    "entity_id": sid,
                    "title": (source.title if source else None) or sid,
                    "relation": relation,
                    "via": via,
                    "depth": level,
                }
            )
            if level >= max_depth:
                continue
            neighbors = list(
                (
                    await db.execute(
                        select(KnowledgeRelation).where(
                            KnowledgeRelation.organization_id == organization_id,
                            KnowledgeRelation.source_type == stype,
                            KnowledgeRelation.source_id == sid,
                        ).limit(_MAX_PROPAGATION_NODES)
                    )
                ).scalars().all()
            ) + list(
                (
                    await db.execute(
                        select(KnowledgeRelation).where(
                            KnowledgeRelation.organization_id == organization_id,
                            KnowledgeRelation.target_type == stype,
                            KnowledgeRelation.target_id == sid,
                        ).limit(_MAX_PROPAGATION_NODES)
                    )
                ).scalars().all()
            )
            for edge in neighbors:
                if edge.source_type == stype and edge.source_id == sid:
                    nxt = (edge.target_type, edge.target_id, level + 1, edge.relation_type, via)
                else:
                    nxt = (edge.source_type, edge.source_id, level + 1, edge.relation_type, via)
                if (nxt[0], nxt[1]) in visited:
                    continue
                queue.append(nxt)
        by_family: dict[str, int] = {}
        for hop in hops:
            by_family[hop["entity_type"]] = by_family.get(hop["entity_type"], 0) + 1
        return {
            "topic": {"id": topic.id, "name": _clean_topic_name(topic.name)},
            "total": len(hops),
            "depth": max_depth,
            "by_family": {
                k: v for k, v in sorted(by_family.items(), key=lambda item: -item[1])
            },
            "hops": hops,
            "scope": "org" if access.org_wide else "project",
        }

    # ------------------------------------------------------------ coverage

    async def coverage(
        self, db: AsyncSession, *, organization_id: str, user: Any,
    ) -> dict[str, Any]:
        """Coverage per business area: how much of the area's knowledge is
        authoritative and fresh — and why weak areas are weak."""
        access = await self._access(db, organization_id=organization_id, user=user)
        scanned = await intelligence_engine._scan_topics(
            db, organization_id=organization_id, access=access
        )
        areas: dict[str, dict[str, Any]] = {
            area: {"total": 0, "authoritative": 0, "stale": 0, "weak_reasons": []}
            for area in _AREA_KEYWORDS
        }
        for topic_id, entry in scanned.items():
            topic = entry["topic"]
            claims = [c for c in entry["claims"] if c.status != "superseded"]
            sources = entry["sources"]
            categories = sorted(
                {
                    str((_load_provenance(sources.get((c.subject_type, c.subject_id)).provenance_json) or {}).get("category") or "")
                    for c in claims if sources.get((c.subject_type, c.subject_id))
                }
            )
            keywords = sorted(
                {
                    kw
                    for c in claims if sources.get((c.subject_type, c.subject_id))
                    for kw in (_load_provenance(sources.get((c.subject_type, c.subject_id)).provenance_json) or {}).get("keywords") or []
                }
            )
            area = _area_of(_clean_topic_name(topic.name) or topic.name, categories, keywords)
            if area is None:
                continue
            bucket = areas[area]
            bucket["total"] += 1
            newest = max(
                (sources.get((c.subject_type, c.subject_id)) for c in claims),
                key=lambda s: ensure_aware(s.source_updated_at) if s and s.source_updated_at else now_utc(),
                default=None,
            )
            authoritative = any(c.authority_level >= 2 for c in claims)
            fresh = bool(newest and (newest.freshness_label or "") in _FRESH_OK)
            if authoritative and fresh:
                bucket["authoritative"] += 1
            elif not authoritative:
                bucket["weak_reasons"].append(f"'{_clean_topic_name(topic.name)}' has no authoritative source")
            elif not fresh:
                bucket["stale"] += 1
                bucket["weak_reasons"].append(f"'{_clean_topic_name(topic.name)}' is stale")
        out = []
        for area, bucket in areas.items():
            total = bucket["total"]
            coverage_pct = round(100.0 * bucket["authoritative"] / total) if total else 0
            reasons = bucket["weak_reasons"][:5]
            if coverage_pct < 60 and not reasons:
                reasons.append("knowledge exists but lacks authoritative, fresh sources")
            out.append(
                {
                    "area": area,
                    "coverage": coverage_pct,
                    "total_topics": total,
                    "authoritative": bucket["authoritative"],
                    "stale": bucket["stale"],
                    "weak_reasons": reasons,
                }
            )
        out.sort(key=lambda item: item["coverage"])
        return {
            "total": len(out),
            "areas": out,
            "scope": "org" if access.org_wide else "project",
            "generated_at": now_utc().isoformat(),
        }

    # -------------------------------------------------------- health center

    async def health_center(
        self, db: AsyncSession, *, organization_id: str, user: Any,
    ) -> dict[str, Any]:
        """Company knowledge-health center: a 0-100 score plus drill-down
        counts (contradictions, critical gaps, unverified, stale, orphan)
        and the seven explainable bars from 4E.4."""
        access = await self._access(db, organization_id=organization_id, user=user)
        await self.materialize(db, organization_id=organization_id)
        base = await intelligence_engine.health(db, organization_id=organization_id, user=user)
        bars = base.get("bars", [])
        bar_score = {
            b["name"]: min(100, int(round(b.get("score", 0) * 100))) for b in bars
        }
        score = int(round(sum(bar_score.values()) / len(bar_score))) if bar_score else 0
        rows = list(
            (
                await db.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.organization_id == organization_id,
                        KnowledgeIntelInsight.status == "active",
                    ).limit(_MAX_INSIGHTS * 3)
                )
            ).scalars().all()
        )
        contradictions = sum(1 for r in rows if r.kind == "contradiction")
        critical_gaps = sum(
            1 for r in rows if r.kind == "gap" and r.severity in ("high", "critical")
        )
        unverified = sum(1 for r in rows if r.kind == "verification_required")
        stale_knowledge = sum(1 for r in rows if r.kind == "risk")
        topics = list(
            (
                await db.execute(
                    select(KnowledgeTopic).where(
                        KnowledgeTopic.organization_id == organization_id,
                        KnowledgeTopic.status == "active",
                    ).limit(_MAX_TOPICS_SCAN)
                )
            ).scalars().all()
        )
        orphan = 0
        for topic in topics:
            relations = list(
                (
                    await db.execute(
                        select(KnowledgeRelation).where(
                            KnowledgeRelation.organization_id == organization_id,
                            KnowledgeRelation.source_type == "topic",
                            KnowledgeRelation.source_id == topic.id,
                        ).limit(1)
                    )
                ).scalars().all()
            )
            if not relations:
                orphan += 1
        return {
            "score": score,
            "bars": bars,
            "drill_down": {
                "contradictions": contradictions,
                "critical_gaps": critical_gaps,
                "unverified_claims": unverified,
                "stale_knowledge": stale_knowledge,
                "orphan_topics": orphan,
                "total_topics": len(topics),
            },
            "why_weak": base.get("why_weak", []),
            "scope": "org" if access.org_wide else "project",
            "generated_at": now_utc().isoformat(),
        }

    # ------------------------------------------------------ executive brief

    async def brief(
        self, db: AsyncSession, *, organization_id: str, user: Any, since_hours: int = 24,
    ) -> dict[str, Any]:
        """The continuously generated executive knowledge brief: what
        changed, what emerged, what needs a decision, what is affected —
        and the top three things that need attention."""
        access = await self._access(db, organization_id=organization_id, user=user)
        await self.materialize(db, organization_id=organization_id)
        cutoff = now_utc() - timedelta(hours=since_hours)
        rows = list(
            (
                await db.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.organization_id == organization_id,
                        KnowledgeIntelInsight.status == "active",
                    ).order_by(KnowledgeIntelInsight.priority_score.desc())
                    .limit(_MAX_INSIGHTS)
                )
            ).scalars().all()
        )
        recent = [r for r in rows if ensure_aware(r.updated_at) >= cutoff]
        changes = [r for r in recent if r.kind == "change"]
        risks = [r for r in recent if r.kind == "risk"]
        gaps = [r for r in recent if r.kind == "gap" and r.severity in ("high", "critical")]
        decisions = [r for r in recent if r.kind == "decision_required"]
        impacts = [r for r in recent if r.kind == "impact"]
        customers = [
            r for r in recent
            if r.kind in ("opportunity", "contradiction")
            or any(kw in (r.topic_name or "").lower() for kw in _CUSTOMER_KEYWORDS)
        ]
        strategic = [r for r in recent if r.kind in ("opportunity", "trend")]
        projects_affected = sorted(
            {
                e["id"]
                for r in impacts
                for e in (_json_loads(r.source_entities_json, []) or [])
                if e.get("type") == "project"
            }
        )
        attention = sorted(
            recent[:12],
            key=lambda r: r.priority_score,
            reverse=True,
        )[:3]
        return {
            "since_hours": since_hours,
            "generated_at": now_utc().isoformat(),
            "counts": {
                "significant_changes": len(changes),
                "emerging_risks": len(risks),
                "major_knowledge_gaps": len(gaps),
                "decisions_potentially_affected": len(decisions),
                "projects_impacted": len(projects_affected),
                "customer_changes": len(customers),
                "strategic_signals": len(strategic),
            },
            "attention": [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "title": r.title,
                    "summary": _snippet(r.summary, 240),
                    "severity": r.severity,
                    "priority_score": r.priority_score,
                }
                for r in attention
            ],
            "scope": "org" if access.org_wide else "project",
        }

    # ------------------------------------------- recommendation lifecycle

    _LIFECYCLE_FLOW = {
        "review": (("detected", "candidate"), "reviewed"),
        "accept": (("reviewed",), "accepted"),
        "reject": (("reviewed", "candidate", "detected"), "rejected"),
        "convert": (("accepted", "reviewed"), "converted"),
        "execute": (("converted", "accepted"), "executed"),
        "verify": (("converted", "executed"), "verified"),
    }

    async def recommendation_lifecycle(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        recommendation_id: str,
        user: Any,
        action: str,
        note: Optional[str] = None,
        target: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Advance a recommendation through its governed lifecycle. The
        engine only materializes candidates; every transition is an explicit,
        audited user action. ``convert`` creates a task or a decision through
        the existing governed operating services — never silently."""
        row = (
            await db.execute(
                select(KnowledgeRecommendation).where(
                    KnowledgeRecommendation.organization_id == organization_id,
                    KnowledgeRecommendation.id == recommendation_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if action not in self._LIFECYCLE_FLOW:
            raise ValueError(f"unknown lifecycle action '{action}'")
        allowed, next_state = self._LIFECYCLE_FLOW[action]
        if row.lifecycle not in allowed:
            raise ValueError(
                f"cannot '{action}' from lifecycle '{row.lifecycle}'"
            )
        now = now_utc()
        actor_id = getattr(user, "id", "system")
        audit = _json_loads(row.lifecycle_audit_json, []) or []
        audit.append(
            {"action": action, "at": now.isoformat(), "actor_id": actor_id, "note": note}
        )
        row.lifecycle = next_state
        row.lifecycle_audit_json = json.dumps(audit)
        if action == "review":
            row.reviewed_by, row.reviewed_at, row.review_note = actor_id, now, note
        elif action == "accept":
            row.decided_by, row.decided_at, row.decision_note = actor_id, now, note
        elif action == "reject":
            row.decided_by, row.decided_at, row.decision_note = actor_id, now, note
            row.status = "resolved"
            row.resolved_at = now
        elif action == "convert":
            if target not in ("task", "decision"):
                raise ValueError("convert target must be 'task' or 'decision'")
            if target == "task":
                task_id = await self._create_task_from_recommendation(
                    db, organization_id=organization_id, row=row, user=user,
                    project_id=project_id,
                )
                row.task_id, row.converted_at = task_id, now
            else:
                decision_id = await self._create_decision_from_recommendation(
                    db, organization_id=organization_id, row=row, user=user,
                )
                row.decision_id, row.converted_at = decision_id, now
        elif action == "execute":
            if not row.task_id and not row.decision_id:
                raise ValueError("convert the recommendation before executing it")
            row.executed_by, row.executed_at = actor_id, now
        elif action == "verify":
            if not note:
                raise ValueError("verification needs a note")
            row.verified_by, row.verified_at = actor_id, now
            row.verification_outcome = "verified"
            row.verification_note = note
            row.status = "resolved"
            row.resolved_at = now
        await db.flush()
        return {
            "id": row.id,
            "kind": row.kind,
            "lifecycle": row.lifecycle,
            "status": row.status,
            "task_id": row.task_id,
            "decision_id": row.decision_id,
            "audit": audit,
        }

    async def _create_task_from_recommendation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        row: KnowledgeRecommendation,
        user: Any,
        project_id: Optional[str],
    ) -> str:
        from app.work.task_service import task_service

        actor = await self._employee(db, organization_id=organization_id, user=user)
        data = {
            "title": f"[Knowledge] {row.reason.split('.')[0][:180]}",
            "description": (
                f"Recommended by knowledge intelligence ({row.kind}).\n"
                f"Reason: {row.reason}\n"
                f"Evidence claims: {', '.join(_json_loads(row.evidence_json, []) or [])}"
            ),
            "project_id": project_id,
            "priority": "high" if row.risk == "high" else "medium",
            "status": "backlog",
        }
        if not project_id:
            data.pop("project_id")
        task = await task_service.create(
            db, organization_id=organization_id, data=data,
            actor=actor, ip_address="api",
        )
        return task.id

    async def _create_decision_from_recommendation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        row: KnowledgeRecommendation,
        user: Any,
    ) -> str:
        from app.knowledge.decision_service import decision_service

        actor = await self._employee(db, organization_id=organization_id, user=user)
        payload = {
            "title": f"[Knowledge] {row.reason.split('.')[0][:180]}",
            "description": (
                f"Decision proposed by knowledge intelligence ({row.kind}).\n"
                f"Reason: {row.reason}\n"
                f"Evidence claims: {', '.join(_json_loads(row.evidence_json, []) or [])}"
            ),
            "status": "proposed",
            "options": [
                {"title": "Accept the recommendation", "description": row.reason},
                {"title": "Gather more evidence", "description": "Investigate the cited claims before deciding."},
                {"title": "Defer", "description": "No decision right now."},
            ],
        }
        entity = await decision_service.create(
            db, organization_id=organization_id, payload=payload,
            actor=actor, ip_address="api",
        )
        return entity.id

    async def _employee(self, db: AsyncSession, *, organization_id: str, user: Any):
        from app.people.employee_service import employee_service

        return await employee_service.get_by_user(
            db, organization_id=organization_id, user_id=getattr(user, "id", None)
        )


action_engine = KnowledgeActionEngine()