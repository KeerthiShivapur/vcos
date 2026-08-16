"""Slice 4F.5 — Work Collaboration Intelligence engine.

The canonical, change-driven engine behind "how work flows between people".
Every collaboration claim is evidence-backed (Work Collaboration Graph):

    durable event -> normalize -> bounded person pairs -> evidence (exact-once)
                     -> relationship window (counters, strength, health,
                        monthly evolution markers) -> unit-pair rollup
                     -> person/org accumulators -> advisory signals

Boundary laws (from the 4F.5 directive):
  * Change-driven: only the pairs an event actually evidences are touched.
    There is NO full rescan and NO O(N²) all-pairs pass anywhere.
  * Exact-once: (organization_id, source_event_id, person pair) is unique in
    the evidence ledger; replays converge instead of double-counting.
  * Bounded: attendees/members/recipients/participants are hard-capped per
    event; strength is a bounded deterministic function (decaying
    exponential over weighted positive evidence, deflated by failure ratio);
    confidence grows with evidence count and is capped.
  * History is never destroyed: evidence is append-only; monthly markers roll
    so evolution (emerging/strengthening/stable/weakening/dormant) is
    always derivable with the evidence trail behind it.
  * Analysis NEVER changes the organization: concentration risk, slowdowns
    and gaps are signals. A gap names a missing relationship ("low-evidence
    required collaboration"), never a failing team or person.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.collaboration_intelligence import (
    CollaborationEvidence,
    CollaborationOrgRollup,
    CollaborationPersonRollup,
    CollaborationRelationship,
    CollaborationSignal,
    CollaborationUnitPair,
)
from app.models.communication import ConversationMember, Message

logger = logging.getLogger("vcos.intelligence.work_collaboration")

# Per-organization in-process write locks: serialize collaboration graph
# writes within this process (drain endpoint + periodic event worker) so
# concurrent dispatch passes never interleave multi-row updates.
_ORG_WRITE_LOCKS: dict[str, asyncio.Lock] = {}


def _org_write_lock(organization_id: str) -> asyncio.Lock:
    lock = _ORG_WRITE_LOCKS.get(organization_id)
    if lock is None:
        lock = asyncio.Lock()
        _ORG_WRITE_LOCKS[organization_id] = lock
    return lock

# Hard bounds — one event may touch at most this many pairs.
MAX_MEETING_ATTENDEES = 16      # full attendee pairing bounded: 16 -> 120 pairs
MAX_DECISION_PARTICIPANTS = 12  # maker paired with at most this many contributors
MAX_PROJECT_PAIRED_MEMBERS = 24  # owner paired with at most this many members
MAX_MESSAGE_RECIPIENTS = 24     # sender paired with at most this many recipients
MAX_GAP_PROJECTS_PER_PASS = 100
MAX_GAP_UNIT_PAIRS = 400

# Evolution / dormancy windows (days).
DORMANT_DAYS = 90
EMERGING_DAYS = 30
RECENT_FAILURE_DAYS = 30

# Strength is a bounded saturating function of weighted positive evidence.
STRENGTH_SCALE = 10.0
POSITIVE_WEIGHTS = {
    "successful_interactions": 1.0,
    "shared_tasks": 0.7,
    "shared_decisions": 0.8,
    "shared_meetings": 0.5,
    "meaningful_messages": 0.04,
}

# A message counts as "meaningful work communication" when it carries real
# content, replies to someone, or explicitly mentions someone.
MIN_MEANINGFUL_MESSAGE_CHARS = 20

# Confidence: 0.4 base, +0.03 per evidence item, capped (evidence-backed).
CONFIDENCE_BASE = 0.40
CONFIDENCE_PER_EVIDENCE = 0.03
CONFIDENCE_MAX = 0.97

# Concentration advisory: a person carries this share of the org's total
# collaboration strength with this many active relationships.
CONCENTRATION_WARNING_SHARE = 0.30
CONCENTRATION_CRITICAL_SHARE = 0.45
CONCENTRATION_MIN_RELATIONSHIPS = 5

# Gap advisory: required (project-anchored) collaboration with a unit pair
# whose evidence is below this strength is surfaced as a gap — never a blame.
GAP_STRENGTH_THRESHOLD = 0.15
GAP_MIN_EVIDENCE = 2

# Event -> (points, outcome, detail template). Negative events deflate
# strength deterministically and are never hidden.
EVENT_POINTS: dict[str, tuple[float, str]] = {
    "task.created": (0.4, "neutral"),
    "task.completed": (1.0, "success"),
    "task.transitioned": (0.3, "neutral"),
    "task.blocked": (-0.5, "failure"),
    "task.unblocked": (0.5, "neutral"),
    "project.started": (0.6, "neutral"),
    "project.completed": (1.2, "success"),
    "project.cancelled": (-0.6, "failure"),
    "decision.made": (0.8, "neutral"),
    "decision.executed": (0.8, "neutral"),
    "decision.implemented": (1.2, "success"),
    "approval.approved": (0.9, "success"),
    "approval.rejected": (-1.0, "failure"),
    "meeting.ended": (0.5, "neutral"),
    "meeting.completed": (0.6, "neutral"),
}

COLLABORATION_EVENTS: tuple[str, ...] = tuple(EVENT_POINTS) + ("messaging.message_sent",)

# Health derivation order-of-precedence (deterministic).
_HEALTH_ORDER = (
    "dormant", "blocked", "at_risk", "weakening",
    "strengthening", "emerging", "strong", "healthy", "low_evidence",
)


class CollaborationError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


# ------------------------------------------------------------- math core


def derive_strength(
    *, successful: int, failed: int, shared_tasks: int, shared_decisions: int,
    shared_meetings: int, meaningful_messages: int,
) -> float:
    """Bounded deterministic strength in [0, 1): saturates on weighted
    positive evidence and is deterministically deflated by failures."""
    positive = (
        successful * POSITIVE_WEIGHTS["successful_interactions"]
        + shared_tasks * POSITIVE_WEIGHTS["shared_tasks"]
        + shared_decisions * POSITIVE_WEIGHTS["shared_decisions"]
        + shared_meetings * POSITIVE_WEIGHTS["shared_meetings"]
        + meaningful_messages * POSITIVE_WEIGHTS["meaningful_messages"]
    )
    failure_ratio = failed / (successful + failed + 1)
    decay = 1.0 - 0.5 * min(1.0, failure_ratio * 2.5)
    raw = positive * decay
    strength = 1.0 - __import__("math").exp(-raw / STRENGTH_SCALE)
    return round(min(0.95, strength), 4)


def derive_confidence(evidence_count: int) -> float:
    return round(min(CONFIDENCE_MAX, CONFIDENCE_BASE + evidence_count * CONFIDENCE_PER_EVIDENCE), 4)


def derive_health(
    *, strength: float, successful: int, failed: int, evidence_count: int,
    now: datetime, first_seen: datetime, last_activity_at: datetime,
    cur_month: float, prev_month: float,
) -> str:
    """Deterministic health state, evaluated in fixed precedence order."""
    age_days = max(0, (ensure_aware(now) - ensure_aware(last_activity_at)).days) if last_activity_at else 0
    fresh_days = max(0, (ensure_aware(now) - ensure_aware(first_seen)).days) if first_seen else 0
    failure_ratio = failed / (successful + failed + 1) if evidence_count else 0.0
    if evidence_count and age_days >= DORMANT_DAYS:
        return "dormant"
    if failed >= 2 and failure_ratio >= 0.5:
        return "blocked"
    if failed >= 1 and failure_ratio >= 0.33:
        return "at_risk"
    if prev_month >= 4 and cur_month < 0.5 * prev_month:
        return "weakening"
    if prev_month >= 2 and cur_month >= 1.5 * prev_month + 2:
        return "strengthening"
    if strength >= 0.7 and successful >= 5:
        return "strong"
    if strength >= 0.35 and successful >= 3:
        return "healthy"
    if fresh_days <= EMERGING_DAYS and evidence_count >= 2 and strength >= 0.2:
        return "emerging"
    return "low_evidence"


def derive_quality(
    *, strength: float, successful: int, failed: int, evidence_count: int,
) -> Optional[str]:
    """Quality is orthogonal to strength: volume is never quality."""
    failure_ratio = failed / (successful + failed + 1) if (successful + failed) else 0.0
    if failed >= 2 and failure_ratio >= 0.4:
        return "problematic"
    if successful >= 5 and failed == 0 and strength >= 0.6:
        return "high_quality"
    if evidence_count >= 25:
        return "high_volume"
    return None


def next_key(at: Optional[datetime] = None) -> str:
    at = ensure_aware(at or utcnow())
    return at.strftime("%Y-%m")


def _canonical(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _row_rel(row: CollaborationRelationship) -> dict[str, Any]:
    return {
        "id": row.id,
        "person_a_id": row.person_a_id,
        "person_a_label": row.person_a_label,
        "person_b_id": row.person_b_id,
        "person_b_label": row.person_b_label,
        "relationship_kind": row.relationship_kind,
        "scope_type": row.scope_type,
        "scope_id": row.scope_id,
        "shared_tasks": row.shared_tasks,
        "shared_decisions": row.shared_decisions,
        "shared_meetings": row.shared_meetings,
        "meaningful_messages": row.meaningful_messages,
        "successful_interactions": row.successful_interactions,
        "failed_interactions": row.failed_interactions,
        "strength": row.strength,
        "confidence": row.confidence,
        "health_state": row.health_state,
        "quality": row.quality,
        "status": row.status,
        "month_key": row.month_key,
        "points_cur_month": row.points_cur_month,
        "points_prev_month": row.points_prev_month,
        "source_type": row.source_type,
        "last_source_id": row.last_source_id,
        "last_source_title": row.last_source_title,
        "first_seen": row.first_seen.isoformat() if row.first_seen else None,
        "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        "last_activity_at": row.last_activity_at.isoformat() if row.last_activity_at else None,
        "evidence_count": row.evidence_count,
        "recent_evidence": json.loads(row.recent_evidence_json or "[]"),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _row_unit(row: CollaborationUnitPair) -> dict[str, Any]:
    return {
        "id": row.id,
        "unit_type": row.unit_type,
        "unit_a_id": row.unit_a_id,
        "unit_a_label": row.unit_a_label,
        "unit_b_id": row.unit_b_id,
        "unit_b_label": row.unit_b_label,
        "shared_tasks": row.shared_tasks,
        "shared_decisions": row.shared_decisions,
        "shared_meetings": row.shared_meetings,
        "meaningful_messages": row.meaningful_messages,
        "successful_interactions": row.successful_interactions,
        "failed_interactions": row.failed_interactions,
        "evidence_count": row.evidence_count,
        "strength": row.strength,
        "confidence": row.confidence,
        "health_state": row.health_state,
        "quality": row.quality,
        "status": row.status,
        "first_seen": row.first_seen.isoformat() if row.first_seen else None,
        "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        "last_activity_at": row.last_activity_at.isoformat() if row.last_activity_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _row_signal(row: CollaborationSignal) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "subject_label": row.subject_label,
        "severity": row.severity,
        "detail": row.detail,
        "evidence": json.loads(row.evidence_json or "[]"),
        "status": row.status,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class WorkCollaborationEngine:
    """Change-driven Work Collaboration Graph (person / team / project)."""

    # ------------------------------------------------------- normalization

    async def _employee_label(self, db: AsyncSession, organization_id: str, person_id: str) -> Optional[str]:
        from app.models.employee import Employee

        row = (
            await db.execute(
                select(Employee.first_name, Employee.last_name).where(
                    Employee.organization_id == organization_id, Employee.id == person_id
                )
            )
        ).first()
        if row is None:
            return None
        return " ".join(part for part in (row.first_name, row.last_name) if part) or None

    async def _valid_person(self, db: AsyncSession, organization_id: str, person_id: Optional[str]) -> Optional[str]:
        from app.models.employee import Employee

        if not person_id:
            return None
        found = (
            await db.execute(
                select(Employee.id).where(
                    Employee.organization_id == organization_id, Employee.id == person_id
                )
            )
        ).scalar_one_or_none()
        return found or None

    async def _event_actor(self, db: AsyncSession, organization_id: str, event: Any, payload: dict) -> Optional[str]:
        """Resolve the acting person id from an event (employee id or the
        user-linked employee), validated against this organization."""
        actor_id = payload.get("actor_id") or payload.get("employee_id") or payload.get("actor_employee_id")
        if actor_id:
            person = await self._valid_person(db, organization_id, actor_id)
            if person:
                return person
        from app.models.employee import Employee

        raw = getattr(event, "actor_id", None)
        if raw:
            person = await self._valid_person(db, organization_id, raw)
            if person:
                return person
            linked = (
                await db.execute(
                    select(Employee.id).where(
                        Employee.organization_id == organization_id, Employee.user_id == raw
                    )
                )
            ).scalar_one_or_none()
            return linked or None
        return None

    async def _bookings(
        self, db: AsyncSession, *, organization_id: str, event_name: str,
        event: Any, payload: dict, actor_id: Optional[str],
    ) -> list[dict[str, Any]]:
        """Normalize one event into bounded person-pair bookings (deterministic).

        Returns [] when the event evidences nothing meaningful, so the engine
        never fabricates edges: an edge exists ONLY where evidence exists.
        """
        from app.models.employee import Employee
        from app.models.knowledge import Decision, DecisionParticipant
        from app.models.meeting import MeetingAttendee
        from app.models.project import Project, ProjectMember
        from app.models.task import Task

        config = EVENT_POINTS.get(event_name)
        points = config[0] if config else 0.2
        outcome = config[1] if config else "neutral"
        scope_type, scope_id = "org", ""
        project_id = payload.get("project_id") or None
        source_type = event_name.split(".")[0]
        source_id = payload.get("source_id") or payload.get("entity_id") or payload.get(f"{source_type}_id")
        source_title = payload.get("title") or payload.get("name") or ""

        if event_name == "messaging.message_sent":
            return await self._message_bookings(
                db, organization_id=organization_id, payload=payload, actor_id=actor_id,
            )

        pair_ids: set[tuple[str, str]] = set()
        actor = await self._valid_person(db, organization_id, actor_id)

        if event_name.startswith("task."):
            task_id = payload.get("task_id")
            assignee = await self._valid_person(db, organization_id, payload.get("assignee_id"))
            reporter = await self._valid_person(db, organization_id, payload.get("reporter_id"))
            if task_id:
                row = await db.get(Task, task_id)
                if row is not None and row.organization_id == organization_id:
                    assignee = assignee or row.assignee_id
                    reporter = reporter or row.reporter_id
                    project_id = project_id or row.project_id
                    source_title = source_title or row.title
            if not assignee or not reporter or assignee == reporter:
                return []
            pair_ids.add((assignee, reporter))
        elif event_name.startswith("project."):
            project_id = payload.get("project_id")
            if not project_id:
                return []
            project = await db.get(Project, project_id)
            if project is None or project.organization_id != organization_id:
                return []
            owner = await self._valid_person(db, organization_id, project.owner_id)
            members = (
                await db.execute(
                    select(ProjectMember.employee_id)
                    .where(
                        ProjectMember.organization_id == organization_id,
                        ProjectMember.project_id == project_id,
                    )
                    .limit(MAX_PROJECT_PAIRED_MEMBERS)
                )
            ).scalars().all()
            if owner and members:
                for member in list(dict.fromkeys(members)):
                    if member and member != owner and (member, owner) not in pair_ids and (owner, member) not in pair_ids:
                        pair_ids.add((owner, member))
            scope_type, scope_id = "project", project_id
            source_title = source_title or project.name
        elif event_name.startswith("decision."):
            decision_id = payload.get("decision_id") or payload.get("entity_id")
            if not decision_id:
                return []
            decision = await db.get(Decision, decision_id)
            maker = await self._valid_person(
                db, organization_id, payload.get("decision_maker_id") or (decision.decision_maker_id if decision else None)
            )
            participants = (
                await db.execute(
                    select(DecisionParticipant.employee_id)
                    .where(
                        DecisionParticipant.organization_id == organization_id,
                        DecisionParticipant.decision_id == decision_id,
                    )
                    .limit(MAX_DECISION_PARTICIPANTS)
                )
            ).scalars().all()
            contributor_ids = list(dict.fromkeys([p for p in participants if p]))
            if maker is None and actor:
                maker = actor
            for participant in contributor_ids:
                if participant and participant != maker:
                    pair_ids.add((maker, participant))
            project_id = project_id or (decision.project_id if decision else None)
            source_title = source_title or (decision.title if decision else "")
            if project_id:
                scope_type, scope_id = "project", project_id
            else:
                scope_type, scope_id = "org", ""
        elif event_name.startswith("approval."):
            requester = await self._valid_person(db, organization_id, payload.get("requester_id"))
            if not requester or not actor or actor == requester:
                return []
            pair_ids.add((requester, actor))
        elif event_name.startswith("meeting."):
            attendees = [a for a in (payload.get("attendees") or []) if a]
            if not attendees:
                meeting_id = payload.get("meeting_id") or payload.get("id")
                if meeting_id:
                    attendees = (
                        await db.execute(
                            select(MeetingAttendee.employee_id)
                            .where(
                                MeetingAttendee.organization_id == organization_id,
                                MeetingAttendee.meeting_id == meeting_id,
                            )
                            .limit(MAX_MEETING_ATTENDEES)
                        )
                    ).scalars().all()
            attendees = list(dict.fromkeys([a for a in attendees[:MAX_MEETING_ATTENDEES] if a]))
            for i in range(len(attendees)):
                for j in range(i + 1, len(attendees)):
                    pair_ids.add((attendees[i], attendees[j]))
            source_title = payload.get("title") or source_title
        else:
            return []

        if not pair_ids:
            return []

        bookings: list[dict[str, Any]] = []
        for pa, pb in pair_ids:
            a, b = _canonical(pa, pb)
            bookings.append(
                {
                    "a_id": a, "b_id": b,
                    "a_label": await self._employee_label(db, organization_id, a) or a,
                    "b_label": await self._employee_label(db, organization_id, b) or b,
                    "scope_type": scope_type, "scope_id": scope_id,
                    "outcome": outcome, "points": points,
                    "source_type": source_type, "source_id": source_id,
                    "source_title": source_title, "project_id": project_id,
                    "detail": self._detail(event_name, payload, source_title),
                }
            )
        return bookings

    def _detail(self, event_name: str, payload: dict, source_title: str) -> str:
        title = source_title or payload.get("title") or payload.get("name") or event_name
        return f"{event_name}: {title}"[:300]

    async def _message_bookings(
        self, db: AsyncSession, *, organization_id: str, payload: dict, actor_id: Optional[str],
    ) -> list[dict[str, Any]]:
        """Messaging evidence: sender paired with bounded conversation members,
        only for MEANINGFUL work communication (real content / reply / mention).
        Casual chatter never inflates the graph."""
        from app.models.communication import ConversationMember, Message

        message_id = payload.get("message_id")
        message = await db.get(Message, message_id) if message_id else None
        if message is None or message.organization_id != organization_id:
            return []
        content = message.content or ""
        meaningful = (
            len(content.strip()) >= MIN_MEANINGFUL_MESSAGE_CHARS
            or bool(message.reply_to)
            or bool(message.mentions)
        )
        if not meaningful:
            return []
        sender = await self._valid_person(db, organization_id, message.sender_id)
        if not sender:
            return []
        conversation_id = message.conversation_id
        recipients = (
            await db.execute(
                select(ConversationMember.employee_id)
                .where(
                    ConversationMember.organization_id == organization_id,
                    ConversationMember.conversation_id == conversation_id,
                    ConversationMember.employee_id != sender,
                )
                .limit(MAX_MESSAGE_RECIPIENTS)
            )
        ).scalars().all()
        bookings: list[dict[str, Any]] = []
        seen: set[str] = set()
        for recipient in recipients:
            if not recipient or recipient in seen:
                continue
            seen.add(recipient)
            a, b = _canonical(sender, recipient)
            bookings.append(
                {
                    "a_id": a, "b_id": b,
                    "a_label": await self._employee_label(db, organization_id, a) or a,
                    "b_label": await self._employee_label(db, organization_id, b) or b,
                    "scope_type": "org", "scope_id": "",
                    "outcome": "neutral", "points": 0.2,
                    "source_type": "conversation",
                    "source_id": conversation_id,
                    "source_title": content.strip()[:60] or "Message",
                    "project_id": None,
                    "detail": f"Meaningful conversation: {content.strip()[:80]}"[:300],
                }
            )
        return bookings

    # ------------------------------------------------------ exact-once apply

    async def record_event(
        self, db: AsyncSession, *, organization_id: str, event: Any, payload: dict,
    ) -> dict[str, Any]:
        """Apply one durable event to the Work Collaboration Graph.

        Replays are exact-once: the evidence ledger is keyed on
        (org, source_event_id, pair) — a replayed event converges instead of
        double-counting. Handlers never commit: the EventBus owns the
        transaction, exactly like 4F.1/4F.4.

        Concurrency: writes are serialized per organization with an in-process
        lock so concurrent dispatch passes (the 60s event worker plus an
        on-demand drain for the same tenant) never interleave multi-row
        updates on shared relationship/rollup rows. The web process is a
        single event loop, so one per-org lock is sufficient; cross-process
        workers stay safe via the bus's atomic job claim.
        """
        event_name = getattr(event, "name", "") or payload.get("event_name") or ""
        if event_name not in COLLABORATION_EVENTS:
            return {"status": "ignored"}
        source_event_id = getattr(event, "id", None)
        if not source_event_id:
            source_event_id = payload.get("event_id")
        if not source_event_id:
            return {"status": "skipped", "reason": "no durable event id"}

        org_id = organization_id or payload.get("organization_id") or getattr(event, "organization_id", None)
        if not org_id:
            return {"status": "skipped", "reason": "no organization"}

        lock = _org_write_lock(org_id)
        await lock.acquire()
        try:
            return await self._record_event_locked(
                db, organization_id=org_id, event=event, payload=payload,
                event_name=event_name, source_event_id=source_event_id,
            )
        finally:
            lock.release()

    async def _record_event_locked(
        self, db: AsyncSession, *, organization_id: str, event: Any, payload: dict,
        event_name: str, source_event_id: str,
    ) -> dict[str, Any]:
        org_id = organization_id
        actor_id = await self._event_actor(db, org_id, event, payload)
        bookings = await self._bookings(
            db, organization_id=org_id, event_name=event_name,
            event=event, payload=payload, actor_id=actor_id,
        )
        applied = 0
        for booking in bookings:
            if await self._evidence_applied(
                db, organization_id=org_id, source_event_id=source_event_id,
                a_id=booking["a_id"], b_id=booking["b_id"],
            ):
                continue
            await self._apply_booking(
                db, organization_id=org_id, event_name=event_name,
                source_event_id=source_event_id, actor_id=actor_id, booking=booking,
            )
            applied += 1
        return {"status": "ok", "applied": applied, "pairs": len(bookings)}

    async def _evidence_applied(
        self, db: AsyncSession, *, organization_id: str,
        source_event_id: str, a_id: str, b_id: str,
    ) -> bool:
        found = (
            await db.execute(
                select(CollaborationEvidence.id).where(
                    CollaborationEvidence.organization_id == organization_id,
                    CollaborationEvidence.source_event_id == source_event_id,
                    CollaborationEvidence.person_a_id == a_id,
                    CollaborationEvidence.person_b_id == b_id,
                )
            )
        ).scalars().first()
        return found is not None

    async def _apply_booking(
        self, db: AsyncSession, *, organization_id: str, event_name: str,
        source_event_id: str, actor_id: Optional[str], booking: dict[str, Any],
    ) -> None:
        now = utcnow()
        a_id, b_id = booking["a_id"], booking["b_id"]
        outcome = booking["outcome"]
        points = booking["points"]
        detail = booking["detail"]

        counters: dict[str, int] = {}
        if event_name.startswith("task.") and event_name not in ("task.transitioned", "task.blocked", "task.unblocked"):
            counters["shared_tasks"] = 1
        elif event_name.startswith("project.") and event_name != "project.cancelled":
            counters["shared_tasks"] = 1
        elif event_name.startswith("decision."):
            counters["shared_decisions"] = 1
        elif event_name.startswith("meeting."):
            counters["shared_meetings"] = 1
        elif event_name == "messaging.message_sent":
            counters["meaningful_messages"] = 1
        if outcome == "success":
            counters["successful_interactions"] = 1
        elif outcome == "failure":
            counters["failed_interactions"] = 1

        relationship, created = await self._get_or_create_relationship(
            db, organization_id=organization_id, a_id=a_id, b_id=b_id,
            a_label=booking["a_label"], b_label=booking["b_label"],
            scope_type=booking["scope_type"], scope_id=booking["scope_id"],
        )
        old_health = relationship.health_state
        old_status = relationship.status
        old_strength = relationship.strength
        was_dormant = old_status == "dormant"

        relationship.shared_tasks += counters.get("shared_tasks", 0)
        relationship.shared_decisions += counters.get("shared_decisions", 0)
        relationship.shared_meetings += counters.get("shared_meetings", 0)
        relationship.meaningful_messages += counters.get("meaningful_messages", 0)
        relationship.successful_interactions += counters.get("successful_interactions", 0)
        relationship.failed_interactions += counters.get("failed_interactions", 0)

        # Monthly evolution markers (bounded: two counters + a key).
        mkey = next_key(now)
        if relationship.month_key != mkey:
            relationship.points_prev_month = relationship.points_cur_month
            relationship.points_cur_month = 0.0
            relationship.month_key = mkey
        relationship.points_cur_month = round(max(0.0, relationship.points_cur_month + points), 4)

        relationship.evidence_count += 1
        relationship.last_activity_at = now
        relationship.last_seen = now
        if relationship.first_seen is None:
            relationship.first_seen = now
        relationship.source_type = booking.get("source_type") or event_name.split(".")[0]
        relationship.last_source_id = booking.get("source_id") or None
        relationship.last_source_title = booking.get("source_title") or None
        # Dormancy is age-based: fresh evidence always re-opens a pair.
        if was_dormant:
            relationship.status = "active"

        relationship.strength = derive_strength(
            successful=relationship.successful_interactions,
            failed=relationship.failed_interactions,
            shared_tasks=relationship.shared_tasks,
            shared_decisions=relationship.shared_decisions,
            shared_meetings=relationship.shared_meetings,
            meaningful_messages=relationship.meaningful_messages,
        )
        relationship.confidence = derive_confidence(relationship.evidence_count)
        relationship.health_state = derive_health(
            strength=relationship.strength,
            successful=relationship.successful_interactions,
            failed=relationship.failed_interactions,
            evidence_count=relationship.evidence_count,
            now=now,
            first_seen=relationship.first_seen,
            last_activity_at=relationship.last_activity_at,
            cur_month=relationship.points_cur_month,
            prev_month=relationship.points_prev_month,
        )
        relationship.quality = derive_quality(
            strength=relationship.strength,
            successful=relationship.successful_interactions,
            failed=relationship.failed_interactions,
            evidence_count=relationship.evidence_count,
        )

        recent = json.loads(relationship.recent_evidence_json or "[]")
        recent = [
            {
                "event_name": event_name,
                "outcome": outcome,
                "points": points,
                "detail": detail,
                "occurred_at": now.isoformat(),
            }
        ] + recent[:4]
        relationship.recent_evidence_json = json.dumps(recent, default=str)

        evidence = CollaborationEvidence(
            organization_id=organization_id,
            relationship_id=relationship.id,
            person_a_id=a_id,
            person_a_label=booking["a_label"],
            person_b_id=b_id,
            person_b_label=booking["b_label"],
            scope_type=booking["scope_type"],
            scope_id=booking["scope_id"],
            event_name=event_name,
            source_event_id=source_event_id,
            actor_id=actor_id,
            source_type=booking["source_type"],
            source_id=booking["source_id"],
            source_title=booking["source_title"],
            project_id=booking["project_id"],
            outcome=outcome,
            points=points,
            detail=detail,
            occurred_at=now,
        )
        db.add(evidence)

        await self._roll_units(
            db, organization_id=organization_id, booking=booking,
            counters=counters, outcome=outcome, points=points,
            event_name=event_name, now=now,
        )
        await self._roll_person_and_org(
            db, organization_id=organization_id, booking=booking,
            rel=relationship, old_strength=old_strength,
            created=created, was_dormant=was_dormant, actor_id=actor_id, now=now,
        )
        await self._maintain_signals(
            db, organization_id=organization_id, relationship=relationship,
            old_health=old_health, points=points, detail=detail,
        )

    # ------------------------------------------------------- unit pairs

    async def _unit_ids(
        self, db: AsyncSession, organization_id: str, person_id: str,
    ) -> tuple[Optional[str], Optional[str]]:
        from app.models.employee import Employee

        row = (
            await db.execute(
                select(Employee.team_id, Employee.department_id).where(
                    Employee.organization_id == organization_id, Employee.id == person_id
                )
            )
        ).first()
        if row is None:
            return None, None
        return row[0], row[1]

    async def _unit_label(self, db: AsyncSession, organization_id: str, unit_type: str, unit_id: str) -> str:
        if unit_type == "team":
            from app.models.team import Team

            row = await db.get(Team, unit_id)
        else:
            from app.models.department import Department

            row = await db.get(Department, unit_id)
        if row is None or getattr(row, "organization_id", None) != organization_id:
            return unit_id
        return getattr(row, "name", None) or unit_id

    async def _roll_units(
        self, db: AsyncSession, *, organization_id: str, booking: dict[str, Any],
        counters: dict[str, int], outcome: str, points: float,
        event_name: str, now: datetime,
    ) -> None:
        team_a, dept_a = await self._unit_ids(db, organization_id, booking["a_id"])
        team_b, dept_b = await self._unit_ids(db, organization_id, booking["b_id"])
        for unit_type, ua, ub in (
            ("department", dept_a, dept_b),
            ("team", team_a, team_b),
        ):
            if not ua or not ub or ua == ub:
                continue
            x, y = _canonical(ua, ub)
            pair = (
                await db.execute(
                    select(CollaborationUnitPair).where(
                        CollaborationUnitPair.organization_id == organization_id,
                        CollaborationUnitPair.unit_type == unit_type,
                        CollaborationUnitPair.unit_a_id == x,
                        CollaborationUnitPair.unit_b_id == y,
                    )
                )
            ).scalar_one_or_none()
            if pair is None:
                pair = CollaborationUnitPair(
                    organization_id=organization_id,
                    unit_type=unit_type,
                    unit_a_id=x,
                    unit_a_label=await self._unit_label(db, organization_id, unit_type, x),
                    unit_b_id=y,
                    unit_b_label=await self._unit_label(db, organization_id, unit_type, y),
                )
                db.add(pair)
                await db.flush()
            pair.shared_tasks += counters.get("shared_tasks", 0)
            pair.shared_decisions += counters.get("shared_decisions", 0)
            pair.shared_meetings += counters.get("shared_meetings", 0)
            pair.meaningful_messages += counters.get("meaningful_messages", 0)
            pair.successful_interactions += counters.get("successful_interactions", 0)
            pair.failed_interactions += counters.get("failed_interactions", 0)
            pair.evidence_count += 1
            mkey = next_key(now)
            if pair.month_key != mkey:
                pair.points_prev_month = pair.points_cur_month
                pair.points_cur_month = 0.0
                pair.month_key = mkey
            pair.points_cur_month = round(max(0.0, pair.points_cur_month + points), 4)
            pair.last_seen = now
            pair.last_activity_at = now
            if pair.first_seen is None:
                pair.first_seen = now
            pair.strength = derive_strength(
                successful=pair.successful_interactions,
                failed=pair.failed_interactions,
                shared_tasks=pair.shared_tasks,
                shared_decisions=pair.shared_decisions,
                shared_meetings=pair.shared_meetings,
                meaningful_messages=pair.meaningful_messages,
            )
            pair.confidence = derive_confidence(pair.evidence_count)
            pair.health_state = derive_health(
                strength=pair.strength,
                successful=pair.successful_interactions,
                failed=pair.failed_interactions,
                evidence_count=pair.evidence_count,
                now=now,
                first_seen=pair.first_seen,
                last_activity_at=pair.last_activity_at,
                cur_month=pair.points_cur_month,
                prev_month=pair.points_prev_month,
            )
            pair.quality = derive_quality(
                strength=pair.strength,
                successful=pair.successful_interactions,
                failed=pair.failed_interactions,
                evidence_count=pair.evidence_count,
            )

    # ------------------------------------------------------- accumulators

    async def _get_or_create_relationship(
        self, db: AsyncSession, *, organization_id: str, a_id: str, b_id: str,
        a_label: str, b_label: str, scope_type: str, scope_id: str,
    ) -> CollaborationRelationship:
        row = (
            await db.execute(
                select(CollaborationRelationship).where(
                    CollaborationRelationship.organization_id == organization_id,
                    CollaborationRelationship.person_a_id == a_id,
                    CollaborationRelationship.person_b_id == b_id,
                    CollaborationRelationship.scope_type == scope_type,
                    CollaborationRelationship.scope_id == scope_id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return row, False
        row = CollaborationRelationship(
            organization_id=organization_id,
            person_a_id=a_id,
            person_a_label=a_label or a_id,
            person_b_id=b_id,
            person_b_label=b_label or b_id,
            relationship_kind=await self._relationship_kind(
                db, organization_id=organization_id, a_id=a_id, b_id=b_id,
            ),
            scope_type=scope_type,
            scope_id=scope_id,
        )
        db.add(row)
        await db.flush()
        return row, True

    async def _relationship_kind(
        self, db: AsyncSession, *, organization_id: str, a_id: str, b_id: str,
    ) -> str:
        ta, da = await self._unit_ids(db, organization_id, a_id)
        tb, db_id = await self._unit_ids(db, organization_id, b_id)
        if ta and ta == tb:
            return "same_team"
        if da and da == db_id:
            return "same_department"
        return "cross_department"

    async def _roll_person_and_org(
        self, db: AsyncSession, *, organization_id: str, booking: dict[str, Any],
        rel: CollaborationRelationship, old_strength: float,
        created: bool, was_dormant: bool, actor_id: Optional[str], now: datetime,
    ) -> None:
        for person_id, label in ((rel.person_a_id, rel.person_a_label), (rel.person_b_id, rel.person_b_label)):
            rollup = (
                await db.execute(
                    select(CollaborationPersonRollup).where(
                        CollaborationPersonRollup.organization_id == organization_id,
                        CollaborationPersonRollup.person_id == person_id,
                    )
                )
            ).scalar_one_or_none()
            if rollup is None:
                rollup = CollaborationPersonRollup(
                    organization_id=organization_id,
                    person_id=person_id,
                    person_label=label or person_id,
                )
                db.add(rollup)
                await db.flush()
            if rollup.first_seen is None:
                rollup.first_seen = now
            if created or was_dormant:
                rollup.active_relationships += 1
            rollup.total_strength = round(max(0.0, rollup.total_strength - old_strength + rel.strength), 4)
            rollup.total_evidence += 1
            mkey = next_key(now)
            if rollup.month_key != mkey:
                rollup.total_points_prev_month = rollup.total_points_cur_month
                rollup.total_points_cur_month = 0.0
                rollup.month_key = mkey
            rollup.total_points_cur_month = round(max(0.0, rollup.total_points_cur_month + rel.points_cur_month), 4)

        org_rollup = (
            await db.execute(
                select(CollaborationOrgRollup).where(
                    CollaborationOrgRollup.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        if org_rollup is None:
            org_rollup = CollaborationOrgRollup(organization_id=organization_id)
            db.add(org_rollup)
            await db.flush()
        if created or was_dormant:
            org_rollup.active_relationships += 1
        org_rollup.total_strength = round(max(0.0, org_rollup.total_strength - old_strength + rel.strength), 4)
        org_rollup.total_evidence += 1

    # ------------------------------------------------------- advisory signals

    async def _maintain_signals(
        self, db: AsyncSession, *, organization_id: str,
        relationship: CollaborationRelationship, old_health: str,
        points: float, detail: str,
    ) -> None:
        """Advisory-only findings tied to THIS relationship and its people.
        Signals never change the organization; stale ones auto-resolve."""
        person_ids = (relationship.person_a_id, relationship.person_b_id)
        if old_health in ("strong", "healthy", "strengthening") and relationship.health_state in (
            "weakening", "dormant",
        ):
            subject = f"{relationship.person_a_id}:{relationship.person_b_id}"
            await self._upsert_signal(
                db,
                organization_id=organization_id,
                kind="slowdown",
                subject_type="relationship",
                subject_id=subject,
                subject_label=f"{relationship.person_a_label} <-> {relationship.person_b_label}",
                severity="warning",
                detail=(
                    f"Collaboration slowed: {old_health} -> {relationship.health_state} "
                    f"(evidence {relationship.evidence_count}, current month {relationship.points_cur_month})."
                ),
                evidence=[detail],
            )
        if relationship.health_state in ("blocked", "at_risk") and old_health in ("healthy", "strong", "strengthening"):
            subject = f"{relationship.person_a_id}:{relationship.person_b_id}"
            await self._upsert_signal(
                db,
                organization_id=organization_id,
                kind="negative_shift",
                subject_type="relationship",
                subject_id=subject,
                subject_label=f"{relationship.person_a_label} <-> {relationship.person_b_label}",
                severity="critical" if relationship.health_state == "blocked" else "warning",
                detail=(
                    f"Negative collaboration shift: {old_health} -> {relationship.health_state} "
                    f"({relationship.failed_interactions} failed, {relationship.successful_interactions} successful)."
                ),
                evidence=[detail],
            )

        # Concentration advisory for the touched people (O(1) accumulators).
        org_rollup = (
            await db.execute(
                select(CollaborationOrgRollup).where(
                    CollaborationOrgRollup.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        org_strength = org_rollup.total_strength if org_rollup else 0.0
        for person_id in person_ids:
            rollup = (
                await db.execute(
                    select(CollaborationPersonRollup).where(
                        CollaborationPersonRollup.organization_id == organization_id,
                        CollaborationPersonRollup.person_id == person_id,
                    )
                )
            ).scalar_one_or_none()
            if rollup is None or org_strength <= 0:
                continue
            share = rollup.total_strength / org_strength
            if share >= CONCENTRATION_WARNING_SHARE and rollup.active_relationships >= CONCENTRATION_MIN_RELATIONSHIPS:
                severity = "critical" if share >= CONCENTRATION_CRITICAL_SHARE else "warning"
                await self._upsert_signal(
                    db,
                    organization_id=organization_id,
                    kind="concentration",
                    subject_type="person",
                    subject_id=person_id,
                    subject_label=rollup.person_label or person_id,
                    severity=severity,
                    detail=(
                        f"Potential collaboration concentration: {person_id} carries "
                        f"{share:.0%} of collaboration strength across "
                        f"{rollup.active_relationships} active relationships."
                    ),
                    evidence=[f"share {share:.3f}", f"strength {rollup.total_strength:.3f}"],
                )
            else:
                await self._resolve_signal(
                    db, organization_id=organization_id, kind="concentration",
                    subject_type="person", subject_id=person_id,
                )

    async def _upsert_signal(
        self, db: AsyncSession, *, organization_id: str, kind: str, subject_type: str,
        subject_id: str, subject_label: str, severity: str, detail: str, evidence: list[str],
    ) -> None:
        existing = (
            await db.execute(
                select(CollaborationSignal).where(
                    CollaborationSignal.organization_id == organization_id,
                    CollaborationSignal.kind == kind,
                    CollaborationSignal.subject_type == subject_type,
                    CollaborationSignal.subject_id == subject_id,
                    CollaborationSignal.status == "open",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.detail = detail
            existing.severity = severity
            existing.evidence_json = json.dumps(evidence, default=str)
            return
        db.add(
            CollaborationSignal(
                organization_id=organization_id,
                kind=kind,
                subject_type=subject_type,
                subject_id=subject_id,
                subject_label=subject_label,
                severity=severity,
                detail=detail,
                evidence_json=json.dumps(evidence, default=str),
            )
        )

    async def _resolve_signal(
        self, db: AsyncSession, *, organization_id: str, kind: str,
        subject_type: str, subject_id: str,
    ) -> None:
        rows = (
            await db.execute(
                select(CollaborationSignal).where(
                    CollaborationSignal.organization_id == organization_id,
                    CollaborationSignal.kind == kind,
                    CollaborationSignal.subject_type == subject_type,
                    CollaborationSignal.subject_id == subject_id,
                    CollaborationSignal.status == "open",
                )
            )
        ).scalars().all()
        for row in rows:
            row.status = "resolved"
            row.resolved_at = utcnow()

    # ------------------------------------------------------- gap analysis

    async def resolve_signal_by_id(
        self, db: AsyncSession, *, organization_id: str, signal_id: str,
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Acknowledge/resolve one advisory signal (single bounded lookup).
        Resolving a signal never changes the collaboration graph."""
        signal = await db.get(CollaborationSignal, signal_id)
        if signal is None or signal.organization_id != organization_id:
            raise CollaborationError("signal not found", status=404)
        if signal.status == "open":
            signal.status = "resolved"
            signal.resolved_at = utcnow()
            signal.noted_by = actor_id
            await db.flush()
        return {"resolved": signal.id, "kind": signal.kind}

    async def analyze_gaps(
        self, db: AsyncSession, *, organization_id: str, batch: int = MAX_GAP_PROJECTS_PER_PASS,
    ) -> dict[str, Any]:
        """Bounded pass over active projects: any two departments that share
        an active project have a REQUIRED collaboration relationship; if that
        unit pair carries almost no evidence, surface it as a gap (advisory,
        never a blame) — e.g. Legal<Product with zero evidence."""
        from app.models.department import Department
        from app.models.employee import Employee
        from app.models.project import Project, ProjectMember

        projects = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization_id,
                    Project.status.in_(("active", "completed")),
                )
                .order_by(Project.updated_at.desc())
                .limit(batch)
            )
        ).scalars().all()
        dept_of: dict[str, Optional[str]] = {}
        unit_pairs_seen: set[tuple[str, str]] = set()
        for project in projects:
            members = (
                await db.execute(
                    select(ProjectMember.employee_id)
                    .where(
                        ProjectMember.organization_id == organization_id,
                        ProjectMember.project_id == project.id,
                    )
                    .limit(MAX_PROJECT_PAIRED_MEMBERS)
                )
            ).scalars().all()
            dept_ids: set[str] = set()
            for member_id in members:
                if member_id not in dept_of:
                    row = (
                        await db.execute(
                            select(Employee.department_id).where(
                                Employee.organization_id == organization_id, Employee.id == member_id
                            )
                        )
                    ).scalar_one_or_none()
                    dept_of[member_id] = row
                if dept_of.get(member_id):
                    dept_ids.add(dept_of[member_id])
            from itertools import combinations

            for x, y in combinations(sorted(dept_ids), 2):
                unit_pairs_seen.add(_canonical(x, y))

        found = 0
        for x, y in unit_pairs_seen:
            if len(unit_pairs_seen) > MAX_GAP_UNIT_PAIRS:
                break
            pair = (
                await db.execute(
                    select(CollaborationUnitPair).where(
                        CollaborationUnitPair.organization_id == organization_id,
                        CollaborationUnitPair.unit_type == "department",
                        CollaborationUnitPair.unit_a_id == x,
                        CollaborationUnitPair.unit_b_id == y,
                    )
                )
            ).scalar_one_or_none()
            missing = pair is None or (
                pair.evidence_count < GAP_MIN_EVIDENCE and pair.strength < GAP_STRENGTH_THRESHOLD
            )
            label_x = await self._unit_label(db, organization_id, "department", x)
            label_y = await self._unit_label(db, organization_id, "department", y)
            subject = _canonical(x, y)[0] + ":" + _canonical(x, y)[1]
            if missing:
                await self._upsert_signal(
                    db,
                    organization_id=organization_id,
                    kind="gap",
                    subject_type="unit_pair",
                    subject_id=subject,
                    subject_label=f"{label_x} <-> {label_y}",
                    severity="warning",
                    detail=(
                        f"Required collaboration between {label_x} and {label_y} has "
                        f"{0 if pair is None else pair.evidence_count} evidence item(s) — "
                        "shared project work exists but little collaboration is visible."
                    ),
                    evidence=[f"department pair {label_x}/{label_y}"],
                )
                found += 1
            else:
                await self._resolve_signal(
                    db, organization_id=organization_id, kind="gap",
                    subject_type="unit_pair", subject_id=subject,
                )
        return {"projects_scanned": len(projects), "unit_pairs_checked": len(unit_pairs_seen), "gaps": found}

    # ------------------------------------------------------- governed reads

    async def _visible_person_set(
        self, db: AsyncSession, *, organization_id: str, access: Any,
    ) -> Optional[frozenset[str]]:
        if access is None or getattr(access, "org_wide", False):
            return None
        from app.people.people_engine import people_engine

        return await people_engine.visible_person_ids(db, organization_id=organization_id, access=access)

    def _edge_visible(self, row: CollaborationRelationship, visible: Optional[frozenset[str]]) -> bool:
        if visible is None:
            return True
        return row.person_a_id in visible and row.person_b_id in visible

    async def relationship_detail(
        self, db: AsyncSession, *, organization_id: str, person_a: str, person_b: str,
        access: Any = None, limit: int = 10,
    ) -> dict[str, Any]:
        row = (
            await db.execute(
                select(CollaborationRelationship).where(
                    CollaborationRelationship.organization_id == organization_id,
                    CollaborationRelationship.person_a_id == min(person_a, person_b),
                    CollaborationRelationship.person_b_id == max(person_a, person_b),
                )
                .order_by(CollaborationRelationship.evidence_count.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise CollaborationError("No collaboration relationship between these people.", status=404)
        visible = await self._visible_person_set(db, organization_id=organization_id, access=access)
        if not self._edge_visible(row, visible):
            raise CollaborationError("No collaboration relationship between these people.", status=404)
        evidence = (
            await db.execute(
                select(CollaborationEvidence)
                .where(
                    CollaborationEvidence.organization_id == organization_id,
                    CollaborationEvidence.relationship_id == row.id,
                )
                .order_by(CollaborationEvidence.occurred_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return {
            **_row_rel(row),
            "evidence": [
                {
                    "id": e.id,
                    "event_name": e.event_name,
                    "outcome": e.outcome,
                    "points": e.points,
                    "source_type": e.source_type,
                    "source_id": e.source_id,
                    "source_title": e.source_title,
                    "project_id": e.project_id,
                    "detail": e.detail,
                    "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                }
                for e in evidence
            ],
            "explain": self._explain_strength(row),
        }

    def _explain_strength(self, row: CollaborationRelationship) -> dict[str, Any]:
        return {
            "formula": (
                "strength = 1 - exp(-weighted_positive/10) adjusted by failure ratio; "
                "confidence grows with evidence and is capped"
            ),
            "weighted_positive": round(
                row.successful_interactions * POSITIVE_WEIGHTS["successful_interactions"]
                + row.shared_tasks * POSITIVE_WEIGHTS["shared_tasks"]
                + row.shared_decisions * POSITIVE_WEIGHTS["shared_decisions"]
                + row.shared_meetings * POSITIVE_WEIGHTS["shared_meetings"]
                + row.meaningful_messages * POSITIVE_WEIGHTS["meaningful_messages"],
                4,
            ),
            "failure_ratio": round(
                row.failed_interactions / (row.successful_interactions + row.failed_interactions + 1), 4
            ),
            "evidence_count": row.evidence_count,
        }

    async def person_relationships(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
        access: Any = None, limit: int = 20,
    ) -> dict[str, Any]:
        from app.people.people_engine import people_engine

        try:
            profile = await people_engine.get_profile(
                db, organization_id=organization_id, access=access, person_id=person_id
            )
        except Exception:
            profile = None
        visible = await self._visible_person_set(db, organization_id=organization_id, access=access)
        rows = (
            await db.execute(
                select(CollaborationRelationship).where(
                    or_(
                        and_(
                            CollaborationRelationship.organization_id == organization_id,
                            CollaborationRelationship.person_a_id == person_id,
                        ),
                        and_(
                            CollaborationRelationship.organization_id == organization_id,
                            CollaborationRelationship.person_b_id == person_id,
                        ),
                    )
                )
                .order_by(CollaborationRelationship.strength.desc())
                .limit(limit)
            )
        ).scalars().all()
        edges = []
        for row in rows:
            other = row.person_b_id if row.person_a_id == person_id else row.person_a_id
            other_label = row.person_b_label if row.person_a_id == person_id else row.person_a_label
            if visible is not None and other not in visible:
                continue
            edges.append({**_row_rel(row), "other_person_id": other, "other_person_label": other_label})
        rollup = (
            await db.execute(
                select(CollaborationPersonRollup).where(
                    CollaborationPersonRollup.organization_id == organization_id,
                    CollaborationPersonRollup.person_id == person_id,
                )
            )
        ).scalar_one_or_none()
        org_rollup = (
            await db.execute(
                select(CollaborationOrgRollup).where(
                    CollaborationOrgRollup.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        share = None
        if rollup is not None and org_rollup is not None and org_rollup.total_strength > 0:
            share = round(rollup.total_strength / org_rollup.total_strength, 4)
        return {
            "person_id": person_id,
            "person_label": (profile or {}).get("name") or (
                rollup.person_label if rollup else person_id
            ),
            "relationships": edges,
            "rollup": {
                "active_relationships": rollup.active_relationships if rollup else 0,
                "total_strength": rollup.total_strength if rollup else 0.0,
                "total_evidence": rollup.total_evidence if rollup else 0,
                "share_of_org_strength": share,
            } if rollup else None,
        }

    async def _unit_visible_members(
        self, db: AsyncSession, *, organization_id: str, unit_type: str, unit_id: str,
        visible: Optional[frozenset[str]],
    ) -> frozenset[str]:
        """Member ids of a unit restricted to the caller's visible set (no gating
        for org-wide callers)."""
        if visible is None:
            return frozenset()
        from app.models.employee import Employee

        if unit_type == "team":
            fk = Employee.team_id
        else:
            fk = Employee.department_id
        rows = (
            await db.execute(
                select(Employee.id).where(
                    Employee.organization_id == organization_id,
                    fk == unit_id,
                )
            )
        ).scalars().all()
        return frozenset(rows) & visible

    async def unit_relationships(
        self, db: AsyncSession, *, organization_id: str, unit_type: str, unit_id: str,
        access: Any = None, limit: int = 20,
    ) -> dict[str, Any]:
        if unit_type not in ("team", "department"):
            raise CollaborationError("unit_type must be team or department", status=400)
        label = await self._unit_label(db, organization_id, unit_type, unit_id)
        visible = await self._visible_person_set(db, organization_id=organization_id, access=access)
        if visible is not None and not await self._unit_visible_members(
            db, organization_id=organization_id, unit_type=unit_type,
            unit_id=unit_id, visible=visible,
        ):
            raise CollaborationError("Unit not found.", status=404)
        rows = (
            await db.execute(
                select(CollaborationUnitPair).where(
                    or_(
                        and_(
                            CollaborationUnitPair.organization_id == organization_id,
                            CollaborationUnitPair.unit_type == unit_type,
                            CollaborationUnitPair.unit_a_id == unit_id,
                        ),
                        and_(
                            CollaborationUnitPair.organization_id == organization_id,
                            CollaborationUnitPair.unit_type == unit_type,
                            CollaborationUnitPair.unit_b_id == unit_id,
                        ),
                    )
                )
                .order_by(CollaborationUnitPair.strength.desc())
                .limit(limit)
            )
        ).scalars().all()
        pairs = []
        for row in rows:
            other = row.unit_b_id if row.unit_a_id == unit_id else row.unit_a_id
            if visible is not None and not await self._unit_visible_members(
                db, organization_id=organization_id, unit_type=unit_type,
                unit_id=other, visible=visible,
            ):
                continue
            other_label = row.unit_b_label if row.unit_a_id == unit_id else row.unit_a_label
            pairs.append({**_row_unit(row), "other_unit_id": other, "other_unit_label": other_label})
        return {"unit_type": unit_type, "unit_id": unit_id, "unit_label": label, "pairs": pairs}

    async def _resolve_unit(
        self, db: AsyncSession, *, organization_id: str, unit_name: str,
    ) -> Optional[tuple[str, str]]:
        """Resolve a team/department by name (bounded, deterministic token
        overlap over indexed org-scoped lists)."""
        q_tokens = {t for t in unit_name.lower().replace("_", " ").split() if len(t) >= 2}
        if not q_tokens:
            return None
        from app.models.department import Department
        from app.models.team import Team

        best: Optional[tuple[int, str, str]] = None
        for model, utype in ((Team, "team"), (Department, "department")):
            rows = (
                await db.execute(
                    select(model.id, model.name).where(
                        model.organization_id == organization_id
                    ).limit(50)
                )
            ).all()
            for rid, name in rows:
                label = str(name or "")
                overlap = len(q_tokens & {t for t in label.lower().split() if len(t) >= 2})
                if not overlap:
                    continue
                if best is None or overlap > best[0]:
                    best = (overlap, utype, rid)
        if best is None:
            return None
        return best[1], best[2]

    async def people_across_units(
        self, db: AsyncSession, *, organization_id: str, unit_name: str,
        access: Any = None, limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Bridge detection (advisory): people whose collaboration evidence
        spans multiple units relative to one unit's relationships. Returns
        people with the most cross-unit edges, never a verdict."""
        resolved = await self._resolve_unit(db, organization_id=organization_id, unit_name=unit_name)
        if resolved is None:
            return []
        unit_type, unit_id = resolved
        from app.models.employee import Employee

        unit_members = set(
            (
                await db.execute(
                    select(Employee.id).where(
                        Employee.organization_id == organization_id,
                        Employee.department_id == unit_id if unit_type == "department"
                        else Employee.team_id == unit_id,
                    ).limit(200)
                )
            ).scalars().all()
        )
        visible = await self._visible_person_set(db, organization_id=organization_id, access=access)
        edges = (
            await db.execute(
                select(CollaborationRelationship)
                .where(CollaborationRelationship.organization_id == organization_id)
                .order_by(CollaborationRelationship.strength.desc())
                .limit(400)
            )
        ).scalars().all()
        other_unit_names: dict[str, str] = {}
        member_cross: dict[str, set[str]] = {}
        for edge in edges:
            if visible is not None and not self._edge_visible(edge, visible):
                continue
            for member, other, other_label in (
                (edge.person_a_id, edge.person_b_id, edge.person_b_label),
                (edge.person_b_id, edge.person_a_id, edge.person_a_label),
            ):
                if member not in unit_members or edge.relationship_kind == "same_team":
                    continue
                if other in unit_members:
                    continue
                member_cross.setdefault(member, set()).add(edge.id)
                other_unit_names[other] = other_label
        bridges = [
            {
                "person_id": pid,
                "person_label": await self._employee_label(db, organization_id, pid) or pid,
                "cross_units": len(other_ids),
                "evidence_edges": len(other_ids),
            }
            for pid, other_ids in member_cross.items()
        ]
        bridges.sort(key=lambda b: -b["cross_units"])
        return bridges[:limit]

    async def unit_pair_explain(
        self, db: AsyncSession, *, organization_id: str,
        unit_a_name: str, unit_b_name: str, access: Any = None,
    ) -> dict[str, Any]:
        """Why a unit pair collaborates weakly (or not at all): the canonical
        unit-pair window with counters, strength, confidence and evidence.
        Never a blame — the absence of evidence is itself the finding."""
        unit_a = await self._resolve_unit(db, organization_id=organization_id, unit_name=unit_a_name)
        unit_b = (
            await self._resolve_unit(db, organization_id=organization_id, unit_name=unit_b_name)
            if unit_b_name and unit_b_name != "all" else None
        )
        if unit_a is None:
            return {"unit_a": unit_a_name, "unit_b": unit_b_name, "pair": None}
        unit_type, unit_a_id = unit_a
        rows = (
            await db.execute(
                select(CollaborationUnitPair).where(
                    CollaborationUnitPair.organization_id == organization_id,
                    CollaborationUnitPair.unit_type == unit_type,
                    or_(
                        CollaborationUnitPair.unit_a_id == unit_a_id,
                        CollaborationUnitPair.unit_b_id == unit_a_id,
                    ),
                )
                .order_by(CollaborationUnitPair.strength.desc())
                .limit(20)
            )
        ).scalars().all()
        if unit_b is not None:
            _, unit_b_id = unit_b
            rows = [
                r for r in rows
                if (r.unit_a_id == unit_b_id or r.unit_b_id == unit_b_id)
            ]
            if not rows:
                label_b = await self._unit_label(db, organization_id, unit_type, unit_b_id)
                label_a = await self._unit_label(db, organization_id, unit_type, unit_a_id)
                return {
                    "unit_a": unit_a_name, "unit_b": unit_b_name,
                    "pair": {
                        "unit_a_id": unit_a_id, "unit_a_label": label_a,
                        "unit_b_id": unit_b_id, "unit_b_label": label_b,
                        "shared_tasks": 0, "shared_meetings": 0,
                        "meaningful_messages": 0, "successful_interactions": 0,
                        "failed_interactions": 0, "evidence_count": 0,
                        "strength": 0.0, "confidence": 0.0,
                        "health_state": "low_evidence", "quality": None,
                        "status": "active",
                        "note": "no collaboration evidence between these units",
                    },
                }
        if not rows:
            label_a = await self._unit_label(db, organization_id, unit_type, unit_a_id)
            return {
                "unit_a": unit_a_name, "unit_b": unit_b_name,
                "pair": {
                    "unit_a_id": unit_a_id, "unit_a_label": label_a,
                    "shared_tasks": 0, "shared_meetings": 0,
                    "meaningful_messages": 0, "successful_interactions": 0,
                    "failed_interactions": 0, "evidence_count": 0,
                    "strength": 0.0, "confidence": 0.0,
                    "health_state": "low_evidence", "quality": None,
                    "status": "active",
                    "note": "no collaboration evidence for this unit",
                },
            }
        row = rows[0]
        other = row.unit_b_id if row.unit_a_id == unit_a_id else row.unit_a_id
        other_label = row.unit_b_label if row.unit_a_id == unit_a_id else row.unit_a_label
        return {
            "unit_a": unit_a_name, "unit_b": unit_b_name,
            "pair": {**_row_unit(row), "other_unit_id": other, "other_unit_label": other_label},
        }

    async def overview(
        self, db: AsyncSession, *, organization_id: str, access: Any = None,
    ) -> dict[str, Any]:
        visible = await self._visible_person_set(db, organization_id=organization_id, access=access)
        health_counts: dict[str, int] = {}
        total = 0
        strong_edges: list[dict[str, Any]] = []
        weakening_edges: list[dict[str, Any]] = []
        cross_functional = 0
        rows = (
            await db.execute(
                select(CollaborationRelationship)
                .where(
                    CollaborationRelationship.organization_id == organization_id,
                    CollaborationRelationship.scope_type == "org",
                )
                .order_by(CollaborationRelationship.strength.desc())
                .limit(300)
            )
        ).scalars().all()
        for row in rows:
            if not self._edge_visible(row, visible):
                continue
            total += 1
            health_counts[row.health_state] = health_counts.get(row.health_state, 0) + 1
            if row.relationship_kind == "cross_department":
                cross_functional += 1
            if len(strong_edges) < 5 and row.health_state in ("strong", "healthy"):
                strong_edges.append(_row_rel(row))
            if len(weakening_edges) < 5 and row.health_state == "weakening":
                weakening_edges.append(_row_rel(row))
        signals = (
            await db.execute(
                select(CollaborationSignal).where(
                    CollaborationSignal.organization_id == organization_id,
                    CollaborationSignal.status == "open",
                )
                .order_by(CollaborationSignal.created_at.desc())
                .limit(20)
            )
        ).scalars().all()
        rollup = (
            await db.execute(
                select(CollaborationOrgRollup).where(
                    CollaborationOrgRollup.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        return {
            "organization_id": organization_id,
            "total_relationships": total,
            "cross_functional_relationships": cross_functional,
            "health": health_counts,
            "strongest": strong_edges,
            "weakening": weakening_edges,
            "open_signals": [_row_signal(s) for s in signals],
            "org_rollup": {
                "active_relationships": rollup.active_relationships if rollup else 0,
                "total_strength": rollup.total_strength if rollup else 0.0,
                "total_evidence": rollup.total_evidence if rollup else 0,
            } if rollup else None,
        }

    async def changes(
        self, db: AsyncSession, *, organization_id: str, access: Any = None,
        days: int = 30, limit: int = 20,
    ) -> dict[str, Any]:
        visible = await self._visible_person_set(db, organization_id=organization_id, access=access)
        since = utcnow() - timedelta(days=days)
        rows = (
            await db.execute(
                select(CollaborationRelationship)
                .where(
                    CollaborationRelationship.organization_id == organization_id,
                    CollaborationRelationship.scope_type == "org",
                    CollaborationRelationship.updated_at >= since,
                )
                .order_by(CollaborationRelationship.updated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        items = []
        for row in rows:
            if not self._edge_visible(row, visible):
                continue
            items.append(
                {
                    **_row_rel(row),
                    "change": (
                        "emerging" if row.health_state == "emerging"
                        else "strengthening" if row.health_state == "strengthening"
                        else "weakening" if row.health_state == "weakening"
                        else "dormant" if row.health_state == "dormant"
                        else row.health_state
                    ),
                }
            )
        return {"days": days, "total": len(items), "changes": items}

    async def signals(
        self, db: AsyncSession, *, organization_id: str, access: Any = None,
        kind: Optional[str] = None, status: str = "open", limit: int = 20,
    ) -> dict[str, Any]:
        query = (
            select(CollaborationSignal)
            .where(
                CollaborationSignal.organization_id == organization_id,
                CollaborationSignal.status == status,
            )
            .order_by(CollaborationSignal.created_at.desc())
        )
        if kind:
            query = query.where(CollaborationSignal.kind == kind)
        rows = (await db.execute(query.limit(limit))).scalars().all()
        return {"kind": kind, "status": status, "total": len(rows), "signals": [_row_signal(r) for r in rows]}

    async def project_view(
        self, db: AsyncSession, *, organization_id: str, project_id: str,
        access: Any = None, limit: int = 20,
    ) -> dict[str, Any]:
        from app.models.project import Project

        project = await db.get(Project, project_id)
        if project is None or project.organization_id != organization_id:
            raise CollaborationError("Project not found", status=404)
        visible = await self._visible_person_set(db, organization_id=organization_id, access=access)
        evidence_rows = (
            await db.execute(
                select(CollaborationEvidence)
                .where(
                    CollaborationEvidence.organization_id == organization_id,
                    CollaborationEvidence.project_id == project_id,
                )
                .order_by(CollaborationEvidence.occurred_at.desc())
                .limit(200)
            )
        ).scalars().all()
        person_evidence: dict[str, int] = {}
        pair_evidence: dict[str, dict[str, Any]] = {}
        for e in evidence_rows:
            person_evidence[e.person_a_id] = person_evidence.get(e.person_a_id, 0) + 1
            person_evidence[e.person_b_id] = person_evidence.get(e.person_b_id, 0) + 1
            key = f"{e.person_a_id}:{e.person_b_id}"
            entry = pair_evidence.setdefault(
                key,
                {
                    "person_a_id": e.person_a_id,
                    "person_a_label": e.person_a_label,
                    "person_b_id": e.person_b_id,
                    "person_b_label": e.person_b_label,
                    "evidence_count": 0,
                    "successes": 0,
                    "failures": 0,
                },
            )
            entry["evidence_count"] += 1
            if e.outcome == "success":
                entry["successes"] += 1
            elif e.outcome == "failure":
                entry["failures"] += 1
        total_evidence = len(evidence_rows) or 1
        people = [
            {
                "person_id": pid,
                "evidence_count": count,
                "share_of_project_evidence": round(count / total_evidence, 4),
            }
            for pid, count in sorted(person_evidence.items(), key=lambda kv: -kv[1])[:10]
        ]
        pairs = list(pair_evidence.values())
        pairs.sort(key=lambda p: -p["evidence_count"])
        if visible is not None:
            pairs = [p for p in pairs if p["person_a_id"] in visible and p["person_b_id"] in visible]
        dependency = None
        if pairs:
            top = pairs[0]
            share = top["evidence_count"] / total_evidence
            if share >= 0.5:
                dependency = {
                    "person_a_id": top["person_a_id"],
                    "person_a_label": top["person_a_label"],
                    "person_b_id": top["person_b_id"],
                    "person_b_label": top["person_b_label"],
                    "share_of_project_evidence": round(share, 4),
                    "advisory": (
                        "this project's collaboration evidence concentrates in one pair — "
                        "potential single-point dependency, review (advisory only)."
                    ),
                }
        return {
            "project_id": project_id,
            "project_name": project.name,
            "total_evidence": len(evidence_rows),
            "people": people,
            "top_pairs": pairs[:10],
            "dependency_concentration": dependency,
        }

    # ------------------------------------------------------- small helpers

    async def burn_evidence(
        self, db: AsyncSession, *, organization_id: str, event_name: str, limit: int = 200,
    ) -> None:
        """Test/dev helper: purge applied evidence for an event (state-safe by
        recompute on next apply; counters follow the 4F.5 idempotency law)."""
        rows = (
            await db.execute(
                select(CollaborationEvidence).where(
                    CollaborationEvidence.organization_id == organization_id,
                    CollaborationEvidence.event_name == event_name,
                ).limit(limit)
            )
        ).scalars().all()
        for row in rows:
            await db.delete(row)
        await db.flush()


work_collaboration_engine = WorkCollaborationEngine()