"""Slice 4F.4 — Ownership & Responsibility Intelligence engine.

Canonical, temporal, evidence-backed ownership: who is responsible for what,
why the record says so, for which scope and time window, what changed, where
responsibility is missing or dangerously concentrated, and who would take
over. This is the single governed surface the whole company asks; the app's
per-entity owner columns (project.owner_id, goal.owner_id, ...) land here as
declared evidence through change-driven handlers and reconcile exactly-once.

Hard rules (from the 4F.4 directive):
  * History is never destroyed: a change closes the old window, opens a new
    one, and appends to the ownership_changes ledger.
  * Analysis NEVER auto-fixes. Mismatches, gaps and single-point risks are
    surfaced as advisory signals; only an explicit governed write changes a
    responsibility.
  * Delegation integrates 4C read-only: continuity reads governed scope
    delegations, it never creates a second delegation mechanism.
  * Every read is a bounded indexed lookup; analysis runs in bounded batches.
    No full rescan, ever.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.ownership_intelligence import (
    RESPONSIBILITY_TYPES,
    OwnershipChange,
    OwnershipRelationship,
    OwnershipSignal,
)

# Analysis batch guard: one analyze pass touches at most this many objects.
ANALYZE_BATCH = 200
# A responsibility window is "unowned" work when observed has this many
# successful evidence items while the declared owner has none.
OBSERVED_EVIDENCE_THRESHOLD = 3
# Single-person dependency: an owner holding this many active responsibilities
# without a single backup on any of them.
SINGLE_POINT_ACTIVE_THRESHOLD = 3
# How far back observed evidence must sit within to count as current.
OBSERVED_WINDOW_DAYS = 90
# Confidence used for observed (never auto-applied) findings.
OBSERVED_CONFIDENCE = 0.83


class OwnershipError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _row_relationship(row: OwnershipRelationship) -> dict[str, Any]:
    return {
        "id": row.id,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "object_name": row.object_name,
        "responsibility_type": row.responsibility_type,
        "owner_id": row.owner_id,
        "owner_label": row.owner_label,
        "scope_id": row.scope_id,
        "status": row.status,
        "declared_start": row.declared_start,
        "declared_end": row.declared_end,
        "source": row.source,
        "backup_owner_id": row.backup_owner_id,
        "backup_owner_label": row.backup_owner_label,
        "escalation_scope_id": row.escalation_scope_id,
        "confidence": row.confidence,
        "evidence": json.loads(row.evidence_json or "{}"),
        "closed_at": row.closed_at,
        "closed_reason": row.closed_reason,
        "superseded_by_id": row.superseded_by_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _row_change(row: OwnershipChange) -> dict[str, Any]:
    return {
        "id": row.id,
        "relationship_id": row.relationship_id,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "object_name": row.object_name,
        "responsibility_type": row.responsibility_type,
        "action": row.action,
        "from_owner_id": row.from_owner_id,
        "from_owner_label": row.from_owner_label,
        "to_owner_id": row.to_owner_id,
        "to_owner_label": row.to_owner_label,
        "reason": row.reason,
        "actor_id": row.actor_id,
        "event_name": row.event_name,
        "source_event_id": row.source_event_id,
        "occurred_at": row.occurred_at,
    }


def _row_signal(row: OwnershipSignal) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "object_name": row.object_name,
        "owner_id": row.owner_id,
        "severity": row.severity,
        "detail": row.detail,
        "status": row.status,
        "resolved_at": row.resolved_at,
        "noted_by": row.noted_by,
        "created_at": row.created_at,
    }


def visible_relationship(row: OwnershipRelationship, access: Any) -> bool:
    """Governance visibility: org-wide callers and scope-anchored callers on
    their visible (self+descendant) scopes may see a record. Org-level records
    (no scope) are visible to every qualified brain reader."""
    if access is None or getattr(access, "org_wide", False):
        return True
    if row.scope_id is None:
        return True
    visible = getattr(access, "visible_scope_ids", frozenset()) or frozenset()
    return row.scope_id in visible


def _filter_visible(rows: list[Any], access: Any) -> list[Any]:
    if access is None or getattr(access, "org_wide", False):
        return rows
    visible = getattr(access, "visible_scope_ids", frozenset()) or frozenset()
    return [r for r in rows if r.scope_id is None or r.scope_id in visible]


async def _resolve_object(
    db: AsyncSession, *, organization_id: str, object_type: str, object_id: str
) -> tuple[str, Optional[dict[str, str]]]:
    """Resolve a canonical object to its current name (bounded single lookup).

    Returns (status, resolved): "unknown_type" for custom/role objects (the
    record stays truthful, coverage checks surface the id), "missing" when a
    known object type has no such row (rejected - no invented objects),
    "known" with the snapshot when the row exists in this organization."""
    model = None
    label_col = "name"
    if object_type == "project":
        from app.models.project import Project

        model = Project
    elif object_type == "goal":
        from app.models.goal import Goal

        model = Goal
    elif object_type == "unit":
        from app.models.team import Team

        model = Team
    elif object_type == "customer":
        from app.models.customer import Customer

        model = Customer
    elif object_type == "partner":
        from app.models.partner import Partner

        model = Partner
    elif object_type == "budget":
        from app.models.finance import Budget

        model = Budget
    elif object_type == "knowledge":
        from app.models.knowledge import KnowledgeTopic

        model = KnowledgeTopic
    elif object_type == "decision":
        from app.models.knowledge import Decision

        model = Decision
        label_col = "title"
    elif object_type == "compliance":
        from app.models.enterprise import ComplianceControl

        model = ComplianceControl
    if model is None:
        return "unknown_type", None
    row = await db.get(model, object_id)
    if row is None:
        return "missing", None
    if getattr(row, "organization_id", None) and row.organization_id != organization_id:
        return "missing", None
    return "known", {"object_id": object_id,
                     "object_name": str(getattr(row, label_col, "") or "")[:255]}


async def _employee_label(db: AsyncSession, *, organization_id: str, employee_id: str) -> str:
    from app.models.employee import Employee

    row = await db.get(Employee, employee_id)
    if row is None or (row.organization_id and row.organization_id != organization_id):
        return employee_id
    full = f"{row.first_name or ''} {row.last_name or ''}".strip()
    return str(row.display_name or full or row.email or employee_id)[:255]


async def _employee_exists(db: AsyncSession, *, organization_id: str, employee_id: str) -> bool:
    from app.models.employee import Employee

    row = await db.get(Employee, employee_id)
    if row is None:
        return False
    return not row.organization_id or row.organization_id == organization_id


async def _employee_active(db: AsyncSession, *, organization_id: str, employee_id: str) -> bool:
    from app.models.employee import Employee

    row = await db.get(Employee, employee_id)
    if row is None or (row.organization_id and row.organization_id != organization_id):
        return False
    return getattr(row, "status", "active") == "active"


async def _graph_owns(
    db: AsyncSession, *, organization_id: str, employee_id: str,
    object_type: str, object_id: str, relation: str, evidence: Optional[str],
    active: bool = True,
) -> None:
    """Best-effort graph edge write guarded by a savepoint: the canonical
    ownership record must never be poisoned by a duplicate edge insert (the
    live event worker and the drain endpoint can race on the same event)."""
    from sqlalchemy.exc import IntegrityError

    from app.intelligence import graph_engine

    try:
        async with db.begin_nested():
            await graph_engine.upsert_edge(
                db, organization_id=organization_id,
                source_type="employee", source_id=employee_id,
                target_type=object_type, target_id=object_id,
                relation=relation, weight=1.0 if active else 0.0,
                evidence=evidence, record_update=False,
            )
    except IntegrityError:
        pass


async def _emit(
    db: AsyncSession, *, name: str, organization_id: str, actor_id: Optional[str],
    payload: dict[str, Any],
) -> None:
    from app.services.event_service import event_service

    await event_service.emit(
        db, name=name, actor_id=actor_id, organization_id=organization_id, payload=payload,
    )


class OwnershipEngine:
    """Bounded, temporal ownership & responsibility intelligence."""

    # ------------------------------------------------------------------ #
    # Canonical writes (the only way a responsibility changes hands).     #
    # ------------------------------------------------------------------ #

    async def record(
        self, db: AsyncSession, *, organization_id: str,
        object_type: str, object_id: str, object_name: Optional[str] = None,
        responsibility_type: str = "primary", owner_id: str,
        owner_label: Optional[str] = None, scope_id: Optional[str] = None,
        source: Optional[str] = None, evidence: Optional[dict[str, Any]] = None,
        backup_owner_id: Optional[str] = None, backup_owner_label: Optional[str] = None,
        declared_start: Optional[datetime] = None, declared_end: Optional[datetime] = None,
        actor_id: Optional[str] = None, event: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Open (or transfer) a responsibility window. The single governed
        write path; never overwrites history."""
        if responsibility_type not in RESPONSIBILITY_TYPES:
            raise OwnershipError(f"unknown responsibility type: {responsibility_type}")
        if not owner_id:
            raise OwnershipError("owner_id is required")
        if not await _employee_exists(db, organization_id=organization_id,
                                      employee_id=owner_id):
            raise OwnershipError("owner not found in this organization", status=404)
        status, resolved = await _resolve_object(
            db, organization_id=organization_id,
            object_type=object_type, object_id=object_id,
        )
        if status == "missing":
            raise OwnershipError(
                f"{object_type} object not found in this organization", status=404)
        name = (object_name or (resolved or {}).get("object_name") or object_id)[:255]
        if owner_label is None:
            owner_label = await _employee_label(db, organization_id=organization_id,
                                                employee_id=owner_id)
        if backup_owner_id and not backup_owner_label:
            backup_owner_label = await _employee_label(db, organization_id=organization_id,
                                                       employee_id=backup_owner_id)
        source = source or ("transfer" if responsibility_type != "primary" else "declared")

        previous: Optional[OwnershipRelationship] = None
        if responsibility_type == "primary":
            previous = (
                await db.execute(
                    select(OwnershipRelationship).where(
                        OwnershipRelationship.organization_id == organization_id,
                        OwnershipRelationship.object_type == object_type,
                        OwnershipRelationship.object_id == object_id,
                        OwnershipRelationship.responsibility_type == "primary",
                        OwnershipRelationship.status == "active",
                    ).limit(2)
                )
            ).scalars().first()

        is_transfer = previous is not None and previous.owner_id != owner_id
        if previous is not None and previous.owner_id == owner_id:
            # Idempotent re-record of the same owner: refresh snapshot fields.
            previous.object_name = name
            previous.owner_label = owner_label
            previous.scope_id = scope_id if scope_id is not None else previous.scope_id
            previous.backup_owner_id = backup_owner_id or previous.backup_owner_id
            previous.backup_owner_label = backup_owner_label or previous.backup_owner_label
            previous.source = source
            previous.confidence = 1.0 if source in ("declared", "transfer") else previous.confidence
            previous.evidence_json = json.dumps(evidence or {})
            await db.flush()
            return {"relationship": _row_relationship(previous), "change": None, "transferred": False}

        relationship = OwnershipRelationship(
            organization_id=organization_id,
            object_type=object_type, object_id=object_id, object_name=name,
            responsibility_type=responsibility_type,
            owner_id=owner_id, owner_label=owner_label,
            scope_id=scope_id,
            status="active",
            declared_start=ensure_aware(declared_start) if declared_start else utcnow(),
            declared_end=ensure_aware(declared_end) if declared_end else None,
            source=source,
            backup_owner_id=backup_owner_id, backup_owner_label=backup_owner_label,
            escalation_scope_id=scope_id,
            confidence=1.0 if source in ("declared", "transfer") else OBSERVED_CONFIDENCE,
            evidence_json=json.dumps(evidence or {}),
        )
        if is_transfer:
            # the new window starts exactly when the old one ends: half-open
            # interval [start, end) keeps as_of deterministic at the boundary.
            boundary = utcnow()
            previous.status = "closed"
            previous.closed_at = boundary
            previous.closed_reason = "superseded by transfer"
            previous.superseded_by_id = relationship.id
            if not declared_start:
                relationship.declared_start = boundary
        db.add(relationship)
        await db.flush()
        change = OwnershipChange(
            organization_id=organization_id,
            relationship_id=relationship.id,
            object_type=object_type, object_id=object_id, object_name=name,
            responsibility_type=responsibility_type,
            action="transferred" if is_transfer else "assigned",
            from_owner_id=previous.owner_id if previous else None,
            from_owner_label=previous.owner_label if previous else None,
            to_owner_id=owner_id, to_owner_label=owner_label,
            reason=None, actor_id=actor_id,
            event_name=getattr(event, "name", None) if event else None,
            source_event_id=getattr(event, "id", None) if event else None,
            occurred_at=utcnow(),
        )
        db.add(change)
        await db.flush()
        await _graph_owns(
            db, organization_id=organization_id, employee_id=owner_id,
            object_type=object_type, object_id=object_id,
            relation="owns",
            evidence=f"{responsibility_type} responsibility for {name}"[:500],
            active=True,
        )
        await _emit(
            db, name="ownership.assigned" if not is_transfer else "ownership.transferred",
            organization_id=organization_id, actor_id=actor_id,
            payload={
                "object_type": object_type, "object_id": object_id, "object_name": name,
                "responsibility_type": responsibility_type,
                "owner_id": owner_id, "owner_label": owner_label,
                "scope_id": scope_id, "source": source,
                "backup_owner_id": backup_owner_id,
                "relationship_id": relationship.id,
            },
        )
        return {"relationship": _row_relationship(relationship), "change": _row_change(change),
                "transferred": bool(is_transfer)}

    async def reconcile(
        self, db: AsyncSession, *, organization_id: str,
        object_type: str, object_id: str, object_name: Optional[str] = None,
        owner_id: Optional[str], owner_label: Optional[str] = None,
        scope_id: Optional[str] = None, source: str = "declared",
        evidence: Optional[dict[str, Any]] = None,
        actor_id: Optional[str] = None, event: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Exact-once change-driven reconciliation: create when missing,
        transfer when changed, no-op otherwise."""
        if not owner_id:
            return {"relationship": None, "change": None, "transferred": False}
        return await self.record(
            db, organization_id=organization_id,
            object_type=object_type, object_id=object_id, object_name=object_name,
            responsibility_type="primary", owner_id=owner_id, owner_label=owner_label,
            scope_id=scope_id, source=source, evidence=evidence,
            actor_id=actor_id, event=event,
        )

    async def close(
        self, db: AsyncSession, *, organization_id: str,
        object_type: str, object_id: str, responsibility_type: str = "primary",
        reason: Optional[str] = None, actor_id: Optional[str] = None,
        event: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Close the active window (archive/cancel/owner departures)."""
        relationship = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.object_type == object_type,
                    OwnershipRelationship.object_id == object_id,
                    OwnershipRelationship.responsibility_type == responsibility_type,
                    OwnershipRelationship.status == "active",
                ).limit(2)
            )
        ).scalars().first()
        if relationship is None:
            return {"relationship": None, "change": None}
        relationship.status = "closed"
        relationship.closed_at = utcnow()
        relationship.closed_reason = reason
        await db.flush()
        change = OwnershipChange(
            organization_id=organization_id,
            relationship_id=relationship.id,
            object_type=object_type, object_id=object_id, object_name=relationship.object_name,
            responsibility_type=responsibility_type,
            action="closed",
            from_owner_id=relationship.owner_id, from_owner_label=relationship.owner_label,
            to_owner_id=None, reason=reason, actor_id=actor_id,
            event_name=getattr(event, "name", None) if event else None,
            source_event_id=getattr(event, "id", None) if event else None,
            occurred_at=utcnow(),
        )
        db.add(change)
        await db.flush()
        await _graph_owns(
            db, organization_id=organization_id, employee_id=relationship.owner_id,
            object_type=object_type, object_id=object_id,
            relation="owns", evidence=reason, active=False,
        )
        await _emit(
            db, name="ownership.closed",
            organization_id=organization_id, actor_id=actor_id,
            payload={
                "object_type": object_type, "object_id": object_id,
                "object_name": relationship.object_name,
                "responsibility_type": responsibility_type,
                "owner_id": relationship.owner_id, "reason": reason or "closed",
            },
        )
        return {"relationship": _row_relationship(relationship), "change": _row_change(change)}

    async def close_all_for_owner(
        self, db: AsyncSession, *, organization_id: str, owner_id: str,
        reason: Optional[str] = None, actor_id: Optional[str] = None,
        event: Optional[Any] = None, limit: int = 200,
    ) -> dict[str, Any]:
        """Close every active responsibility of a person (bounded, indexed).
        Only closes windows - responsibility must be reassigned by a human."""
        rows = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.owner_id == owner_id,
                    OwnershipRelationship.status == "active",
                ).limit(limit)
            )
        ).scalars().all()
        closed: list[dict[str, Any]] = []
        for row in rows:
            if row.responsibility_type == "backup":
                row.backup_owner_id = None
                row.backup_owner_label = None
                await db.flush()
                continue
            result = await self.close(
                db, organization_id=organization_id,
                object_type=row.object_type, object_id=row.object_id,
                responsibility_type=row.responsibility_type,
                reason=reason or f"owner no longer responsible ({row.owner_label})",
                actor_id=actor_id, event=event,
            )
            if result.get("relationship"):
                closed.append(result["relationship"])
        return {"closed": closed, "total": len(rows)}

    async def set_backup(
        self, db: AsyncSession, *, organization_id: str,
        object_type: str, object_id: str, backup_owner_id: str,
        responsibility_type: str = "primary", actor_id: Optional[str] = None,
        event: Optional[Any] = None,
    ) -> dict[str, Any]:
        relationship = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.object_type == object_type,
                    OwnershipRelationship.object_id == object_id,
                    OwnershipRelationship.responsibility_type == responsibility_type,
                    OwnershipRelationship.status == "active",
                ).limit(2)
            )
        ).scalars().first()
        if relationship is None:
            raise OwnershipError("no active responsibility to back up", status=404)
        if backup_owner_id == relationship.owner_id:
            raise OwnershipError("a backup owner cannot be the primary owner")
        backup_label = await _employee_label(db, organization_id=organization_id,
                                             employee_id=backup_owner_id)
        same = relationship.backup_owner_id == backup_owner_id
        relationship.backup_owner_id = backup_owner_id
        relationship.backup_owner_label = backup_label
        await db.flush()
        change = OwnershipChange(
            organization_id=organization_id, relationship_id=relationship.id,
            object_type=object_type, object_id=object_id,
            object_name=relationship.object_name,
            responsibility_type=relationship.responsibility_type,
            action="backup_set",
            to_owner_id=backup_owner_id, to_owner_label=backup_label,
            actor_id=actor_id,
            event_name=getattr(event, "name", None) if event else None,
            source_event_id=getattr(event, "id", None) if event else None,
            occurred_at=utcnow(),
        )
        db.add(change)
        await db.flush()
        if not same:
            await _graph_owns(
                db, organization_id=organization_id, employee_id=backup_owner_id,
                object_type=object_type, object_id=object_id,
                relation="backup_for",
                evidence=f"Backup owner of {relationship.object_name}"[:500],
                active=True,
            )
            await _emit(
                db, name="ownership.backup_set",
                organization_id=organization_id, actor_id=actor_id,
                payload={"object_type": object_type, "object_id": object_id,
                         "object_name": relationship.object_name,
                         "owner_id": relationship.owner_id,
                         "backup_owner_id": backup_owner_id,
                         "relationship_id": relationship.id},
            )
        return {"relationship": _row_relationship(relationship),
                "change": _row_change(change) if not same else None}

    async def remove_backup(
        self, db: AsyncSession, *, organization_id: str,
        object_type: str, object_id: str, responsibility_type: str = "primary",
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        relationship = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.object_type == object_type,
                    OwnershipRelationship.object_id == object_id,
                    OwnershipRelationship.responsibility_type == responsibility_type,
                    OwnershipRelationship.status == "active",
                ).limit(2)
            )
        ).scalars().first()
        if relationship is None or relationship.backup_owner_id is None:
            return {"relationship": _row_relationship(relationship) if relationship else None,
                    "change": None}
        removed = relationship.backup_owner_id
        relationship.backup_owner_id = None
        relationship.backup_owner_label = None
        await db.flush()
        change = OwnershipChange(
            organization_id=organization_id, relationship_id=relationship.id,
            object_type=object_type, object_id=object_id,
            object_name=relationship.object_name,
            responsibility_type=relationship.responsibility_type,
            action="backup_removed", from_owner_id=removed, actor_id=actor_id,
            occurred_at=utcnow(),
        )
        db.add(change)
        await db.flush()
        await _graph_owns(
            db, organization_id=organization_id, employee_id=removed,
            object_type=object_type, object_id=object_id,
            relation="backup_for", evidence="backup removed", active=False,
        )
        await _emit(db, name="ownership.backup_removed", organization_id=organization_id,
                    actor_id=actor_id,
                    payload={"object_type": object_type, "object_id": object_id,
                             "object_name": relationship.object_name,
                             "backup_owner_id": removed,
                             "relationship_id": relationship.id})
        return {"relationship": _row_relationship(relationship), "change": _row_change(change)}

    # ------------------------------------------------------------------ #
    # Reads — bounded indexed lookups only.                              #
    # ------------------------------------------------------------------ #

    async def current(
        self, db: AsyncSession, *, organization_id: str,
        object_type: str, object_id: str, access: Any = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.object_type == object_type,
                    OwnershipRelationship.object_id == object_id,
                    OwnershipRelationship.status == "active",
                ).order_by(OwnershipRelationship.responsibility_type.asc()).limit(limit)
            )
        ).scalars().all()
        relations = [_row_relationship(r) for r in _filter_visible(list(rows), access)]
        primaries = [r for r in relations if r["responsibility_type"] == "primary"]
        return {
            "object_type": object_type, "object_id": object_id,
            "object_name": (relations[0] or {}).get("object_name", object_id)
            if relations else object_id,
            "primary": primaries[0] if primaries else None,
            "relationships": relations,
            "total": len(relations),
        }

    async def history(
        self, db: AsyncSession, *, organization_id: str,
        object_type: str, object_id: str, access: Any = None, limit: int = 50,
    ) -> dict[str, Any]:
        changes = (
            await db.execute(
                select(OwnershipChange)
                .where(
                    OwnershipChange.organization_id == organization_id,
                    OwnershipChange.object_type == object_type,
                    OwnershipChange.object_id == object_id,
                )
                .order_by(OwnershipChange.occurred_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        closed = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.object_type == object_type,
                    OwnershipRelationship.object_id == object_id,
                    OwnershipRelationship.status.in_(("closed", "expired")),
                ).order_by(OwnershipRelationship.declared_start.desc()).limit(limit)
            )
        ).scalars().all()
        change_rows = _filter_visible(list(changes), access)
        closed_rows = _filter_visible(list(closed), access)
        merged = [_row_change(c) for c in change_rows] + [
            _row_relationship(r) for r in closed_rows
        ]
        ledgers = sorted(
            merged,
            key=lambda e: ensure_aware(e.get("occurred_at") or e.get("declared_start")),
            reverse=True,
        )
        return {
            "object_type": object_type, "object_id": object_id,
            "events": ledgers[:limit], "total": len(ledgers),
        }

    async def as_of(
        self, db: AsyncSession, *, organization_id: str,
        object_type: str, object_id: str, at: datetime, access: Any = None,
    ) -> dict[str, Any]:
        """The responsibility world of one object at one moment (temporal
        reconstruction — answers "who owned X when the incident happened")."""
        moment = ensure_aware(at)
        rows = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.object_type == object_type,
                    OwnershipRelationship.object_id == object_id,
                ).limit(50)
            )
        ).scalars().all()
        visible = _filter_visible(list(rows), access)
        active_then = []
        for r in visible:
            start = ensure_aware(r.declared_start)
            end = r.declared_end or r.closed_at
            if start <= moment and (end is None or ensure_aware(end) > moment):
                active_then.append(_row_relationship(r))
        primary = [r for r in active_then if r["responsibility_type"] == "primary"]
        return {
            "object_type": object_type, "object_id": object_id,
            "at": moment.isoformat(),
            "object_name": (active_then[0] or {}).get("object_name", object_id)
            if active_then else object_id,
            "primary": primary[0] if primary else None,
            "relationships": active_then,
        }

    async def responsibilities_of(
        self, db: AsyncSession, *, organization_id: str, owner_id: str,
        access: Any = None, active_only: bool = True, limit: int = 100,
    ) -> dict[str, Any]:
        statuses = ("active",) if active_only else ("active", "closed", "expired")
        rows = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.owner_id == owner_id,
                    OwnershipRelationship.status.in_(statuses),
                ).order_by(OwnershipRelationship.declared_start.desc()).limit(limit)
            )
        ).scalars().all()
        relations = [_row_relationship(r) for r in _filter_visible(list(rows), access)]
        backup_rows = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.backup_owner_id == owner_id,
                    OwnershipRelationship.status == "active",
                ).order_by(OwnershipRelationship.declared_start.desc()).limit(limit)
            )
        ).scalars().all()
        backup_relations = [
            _row_relationship(r)
            for r in _filter_visible(list(backup_rows), access)
            if r.backup_owner_id == owner_id
        ]
        return {
            "owner_id": owner_id,
            "active": [r for r in relations if r["status"] == "active"],
            "history": [r for r in relations if r["status"] != "active"],
            "backup_roles": len(backup_relations),
            "total": len(relations),
        }

    async def continuity(
        self, db: AsyncSession, *, organization_id: str,
        object_type: str, object_id: str, access: Any = None,
    ) -> dict[str, Any]:
        """Who takes over: primary -> backup -> governed delegation (4C, read
        only) -> escalation authority. Never invents a successor."""
        current = await self.current(db, organization_id=organization_id,
                                     object_type=object_type, object_id=object_id,
                                     access=access)
        primary = current.get("primary")
        result: dict[str, Any] = {
            "object_type": object_type, "object_id": object_id,
            "object_name": current.get("object_name"),
            "primary": primary,
            "backup": None, "delegation": None, "escalation": None,
            "gaps": [],
        }
        if primary is None:
            return result
        if primary.get("backup_owner_id"):
            result["backup"] = {
                "owner_id": primary["backup_owner_id"],
                "owner_label": primary.get("backup_owner_label"),
            }
        scope_id = primary.get("scope_id")
        if scope_id:
            from app.models.enterprise import AccessGrant

            now = utcnow()
            grants = (
                await db.execute(
                    select(AccessGrant).where(
                        AccessGrant.organization_id == organization_id,
                        AccessGrant.resource_type == "scope",
                        AccessGrant.resource_id == scope_id,
                        AccessGrant.status == "active",
                        or_(AccessGrant.starts_at.is_(None), AccessGrant.starts_at <= now),
                        or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > now),
                    ).order_by(AccessGrant.created_at.desc()).limit(5)
                )
            ).scalars().all()
            if grants:
                result["delegation"] = {
                    "scope_id": scope_id,
                    "grants": [
                        {
                            "permission_code": g.permission_code,
                            "granted_to_user": g.granted_to_user,
                            "expires_at": g.expires_at,
                        }
                        for g in grants
                    ],
                }
        if primary.get("escalation_scope_id"):
            from app.models.governance import GovernanceScope

            scope = await db.get(GovernanceScope, primary["escalation_scope_id"])
            if scope is not None and scope.organization_id == organization_id:
                result["escalation"] = {
                    "scope_id": scope.id,
                    "scope_name": scope.name,
                    "scope_type": scope.scope_type,
                }
        else:
            result["escalation"] = {"scope_id": None, "scope_name": "no escalation scope set"}
        return result

    # ------------------------------------------------------------------ #
    # Analysis — bounded, advisory only, never auto-fixes.               #
    # ------------------------------------------------------------------ #

    async def active_batch(
        self, db: AsyncSession, *, organization_id: str,
        offset: int = 0, limit: int = ANALYZE_BATCH,
    ) -> list[dict[str, Any]]:
        """The next bounded batch of active primaries (dry-run reads only)."""
        limit = min(max(limit, 1), ANALYZE_BATCH)
        rows = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.responsibility_type == "primary",
                    OwnershipRelationship.status == "active",
                ).order_by(OwnershipRelationship.updated_at.asc())
                .offset(offset).limit(limit)
            )
        ).scalars().all()
        return [_row_relationship(r) for r in rows]

    async def analyze(
        self, db: AsyncSession, *, organization_id: str,
        offset: int = 0, limit: int = ANALYZE_BATCH, commit: bool = True,
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """One bounded analysis pass (<= ``limit`` active primaries): surface
        gaps (owner left), single-point risks (no backup, overloaded) and
        declared-vs-observed mismatches. Only writes advisory signals."""
        limit = min(max(limit, 1), ANALYZE_BATCH)
        rows = (
            await db.execute(
                select(OwnershipRelationship).where(
                    OwnershipRelationship.organization_id == organization_id,
                    OwnershipRelationship.responsibility_type == "primary",
                    OwnershipRelationship.status == "active",
                ).order_by(OwnershipRelationship.updated_at.asc())
                .offset(offset).limit(limit)
            )
        ).scalars().all()
        summary = {"scanned": 0, "signals_written": 0, "mismatch": 0, "gap": 0,
                   "single_point": 0, "next_offset": offset + min(len(rows), limit)}
        if not rows:
            summary["next_offset"] = 0
            await _emit(db, name="ownership.coverage_checked",
                        organization_id=organization_id, actor_id=actor_id,
                        payload={"scanned": 0, "next_offset": 0})
            return summary

        by_owner: dict[str, int] = {}
        for row in rows:
            by_owner[row.owner_id] = by_owner.get(row.owner_id, 0) + 1
            summary["scanned"] += 1

        for row in rows:
            if not await _employee_active(db, organization_id=organization_id,
                                          employee_id=row.owner_id):
                detail = (f"{row.owner_label} is no longer an active employee "
                          f"but still owns {row.object_name} ({row.object_type})")
                await self._upsert_signal(db, organization_id=organization_id,
                                          kind="gap", severity="critical",
                                          row=row, detail=detail, actor_id=actor_id)
                summary["gap"] += 1
                summary["signals_written"] += 1
                received = await self._recommend_candidates(
                    db, organization_id=organization_id, row=row)
                if received:
                    await self._note_signal(
                        db, organization_id=organization_id, row=row,
                        kind="gap", note=f"Suggested candidates: {received}",
                        actor_id=actor_id)
                continue
            if row.backup_owner_id is None and by_owner.get(row.owner_id, 0) >= SINGLE_POINT_ACTIVE_THRESHOLD:
                detail = (f"{row.owner_label} holds {by_owner[row.owner_id]} "
                          f"active responsibilities with no backup on this one"
                          f" ({row.object_name}) - single-person dependency risk")
                await self._upsert_signal(db, organization_id=organization_id,
                                          kind="single_point", severity="warning",
                                          row=row, detail=detail, actor_id=actor_id)
                summary["single_point"] += 1
                summary["signals_written"] += 1
                continue
            observed = await self._observed_controller(
                db, organization_id=organization_id, row=row)
            if observed is None:
                continue
            if observed["employee_id"] != row.owner_id and observed["count"] >= OBSERVED_EVIDENCE_THRESHOLD:
                detail = (f"Declared owner {row.owner_label}, but recent activity "
                          f"evidence points to {observed['employee_label']} "
                          f"({observed['count']} successful evidence items). "
                          f"Potential responsibility mismatch; ownership was NOT changed.")
                await self._upsert_signal(db, organization_id=organization_id,
                                          kind="mismatch", severity="warning",
                                          row=row, detail=detail, actor_id=actor_id)
                summary["mismatch"] += 1
                summary["signals_written"] += 1
        await _emit(db, name="ownership.coverage_checked",
                    organization_id=organization_id, actor_id=actor_id,
                    payload={"scanned": summary["scanned"],
                             "signals": summary["signals_written"],
                             "next_offset": summary["next_offset"]})
        return summary

    async def _observed_controller(
        self, db: AsyncSession, *, organization_id: str, row: OwnershipRelationship,
    ) -> Optional[dict[str, Any]]:
        """Bounded: top practice actor for one object from current successful
        evidence within OBSERVED_WINDOW_DAYS."""
        from app.models.skills_intelligence import ExpertiseEvidence

        cutoff = ensure_aware(utcnow()) - timedelta(days=OBSERVED_WINDOW_DAYS)
        now = ensure_aware(utcnow())
        counts = (
            await db.execute(
                select(ExpertiseEvidence.person_id, func.count(ExpertiseEvidence.id))
                .where(
                    ExpertiseEvidence.organization_id == organization_id,
                    ExpertiseEvidence.source_type == row.object_type,
                    ExpertiseEvidence.source_id == row.object_id,
                    ExpertiseEvidence.outcome == "successful",
                    or_(ExpertiseEvidence.valid_to.is_(None),
                        ExpertiseEvidence.valid_to > now),
                    ExpertiseEvidence.occurred_at >= cutoff,
                )
                .group_by(ExpertiseEvidence.person_id)
                .order_by(func.count(ExpertiseEvidence.id).desc())
                .limit(3)
            )
        ).all()
        if not counts:
            return None
        person_id, count = counts[0]
        label = await _employee_label(db, organization_id=organization_id,
                                      employee_id=person_id)
        return {"employee_id": person_id, "employee_label": label, "count": count}

    async def _recommend_candidates(
        self, db: AsyncSession, *, organization_id: str, row: OwnershipRelationship,
        limit: int = 3,
    ) -> str:
        """Read-only suggestions for a gap — never assign."""
        from app.models.employee import Employee

        owner = await db.get(Employee, row.owner_id)
        department_id = getattr(owner, "department_id", None) if owner else None
        if department_id:
            same_unit = (
                await db.execute(
                    select(Employee.id, Employee.display_name)
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.status == "active",
                        Employee.department_id == department_id,
                        Employee.id != row.owner_id,
                    ).limit(limit)
                )
            ).all()
        else:
            same_unit = []
        labels = [str(label or eid)[:80] for eid, label in same_unit]
        return ", ".join(labels[:limit]) if labels else ""

    async def _upsert_signal(
        self, db: AsyncSession, *, organization_id: str, kind: str,
        severity: str, row: OwnershipRelationship, detail: str,
        actor_id: Optional[str],
    ) -> Optional[OwnershipSignal]:
        existing = (
            await db.execute(
                select(OwnershipSignal).where(
                    OwnershipSignal.organization_id == organization_id,
                    OwnershipSignal.kind == kind,
                    OwnershipSignal.object_type == row.object_type,
                    OwnershipSignal.object_id == row.object_id,
                    OwnershipSignal.status == "open",
                ).limit(2)
            )
        ).scalars().first()
        if existing is not None:
            return existing
        signal = OwnershipSignal(
            organization_id=organization_id, kind=kind,
            object_type=row.object_type, object_id=row.object_id,
            object_name=row.object_name, owner_id=row.owner_id,
            severity=severity, detail=detail, status="open",
        )
        db.add(signal)
        await db.flush()
        await _emit(db, name={
            "gap": "ownership.gap_detected",
            "single_point": "ownership.single_point_detected",
            "mismatch": "ownership.mismatch_detected",
        }[kind], organization_id=organization_id, actor_id=actor_id,
                    payload={"object_type": row.object_type, "object_id": row.object_id,
                             "object_name": row.object_name,
                             "owner_id": row.owner_id, "detail": detail[:300]})
        return signal

    async def _note_signal(
        self, db: AsyncSession, *, organization_id: str, kind: str,
        row: OwnershipRelationship, note: str, actor_id: Optional[str],
    ) -> None:
        signal = (
            await db.execute(
                select(OwnershipSignal).where(
                    OwnershipSignal.organization_id == organization_id,
                    OwnershipSignal.kind == kind,
                    OwnershipSignal.object_type == row.object_type,
                    OwnershipSignal.object_id == row.object_id,
                    OwnershipSignal.status == "open",
                ).limit(2)
            )
        ).scalars().first()
        if signal is None:
            return
        signal.detail = (signal.detail + "\n" + note)[:500]
        await db.flush()

    async def signals(
        self, db: AsyncSession, *, organization_id: str,
        kind: Optional[str] = None, status: str = "open", limit: int = 200,
    ) -> dict[str, Any]:
        where = [
            OwnershipSignal.organization_id == organization_id,
            OwnershipSignal.status == status,
        ]
        if kind:
            where.append(OwnershipSignal.kind == kind)
        rows = (
            await db.execute(
                select(OwnershipSignal).where(and_(*where))
                .order_by(OwnershipSignal.created_at.desc()).limit(limit)
            )
        ).scalars().all()
        return {"signals": [_row_signal(r) for r in rows], "total": len(rows)}

    async def resolve_signal(
        self, db: AsyncSession, *, organization_id: str, signal_id: str,
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        signal = await db.get(OwnershipSignal, signal_id)
        if signal is None or signal.organization_id != organization_id:
            raise OwnershipError("signal not found", status=404)
        signal.status = "resolved"
        signal.resolved_at = utcnow()
        signal.noted_by = actor_id
        await db.flush()
        await _emit(db, name="ownership.signal_resolved",
                    organization_id=organization_id, actor_id=actor_id,
                    payload={"signal_id": signal.id, "kind": signal.kind,
                             "object_type": signal.object_type,
                             "object_id": signal.object_id})
        return {"signal": _row_signal(signal)}

    async def summary(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        open_signals = (
            await db.execute(
                select(OwnershipSignal.kind, func.count(OwnershipSignal.id))
                .where(
                    OwnershipSignal.organization_id == organization_id,
                    OwnershipSignal.status == "open",
                )
                .group_by(OwnershipSignal.kind)
            )
        ).all()
        counts = (await db.execute(
            select(func.count(OwnershipRelationship.id)).where(
                OwnershipRelationship.organization_id == organization_id,
                OwnershipRelationship.status == "active",
            )
        )).scalar() or 0
        return {
            "active_relationships": int(counts),
            "open_signals": {kind: int(cnt) for kind, cnt in open_signals},
        }

    async def coverage_check(
        self, db: AsyncSession, *, organization_id: str,
        candidates: list[dict[str, Any]], limit: int = 200,
    ) -> dict[str, Any]:
        """For an explicitly named bounded list of objects (project/unit/...):
        which lack a primary responsibility? Analysis only — no auto-create."""
        bounded = candidates[:limit]
        unassigned = []
        for cand in bounded:
            object_type = cand.get("object_type")
            object_id = cand.get("object_id")
            if not object_type or not object_id:
                continue
            primary = (
                await db.execute(
                    select(OwnershipRelationship).where(
                        OwnershipRelationship.organization_id == organization_id,
                        OwnershipRelationship.object_type == object_type,
                        OwnershipRelationship.object_id == object_id,
                        OwnershipRelationship.responsibility_type == "primary",
                        OwnershipRelationship.status == "active",
                    ).limit(2)
                )
            ).scalars().first()
            if primary is None:
                unassigned.append({
                    "object_type": object_type, "object_id": object_id,
                    "object_name": cand.get("object_name") or object_id,
                })
        await _emit(db, name="ownership.coverage_checked",
                    organization_id=organization_id, actor_id=None,
                    payload={"checked": len(bounded),
                             "unassigned": len(unassigned)})
        return {"checked": len(bounded), "unassigned": unassigned,
                "unassigned_total": len(unassigned)}


ownership_engine = OwnershipEngine()