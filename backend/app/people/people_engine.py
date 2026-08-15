"""Slice 4F.1 — Universal People Intelligence Engine.

One governed people surface for the Company Brain: canonical person identity,
temporal membership / roles / reporting windows, identity resolution, and the
People Graph — all of it resolved through the same governance kernel as every
other brain surface (caller -> user -> roles -> scopes -> visible people).

Laws enforced here (inherited from 4C-4E, preserved):

* Access is resolved BEFORE data is assembled. A scoped caller only ever sees
  the people reachable from their visible scope anchors: people anchored by
  visible scopes (team / department / business_unit / project / employee),
  their own person, and the ancestor-manager chain of visible people — never
  invisible subordinates (downward-only governance).
* Identity resolution is deterministic: one strong identifier maps to one
  person, and conflicting mappings are flagged ``ambiguous`` — the engine
  never silently merges two people.
* State moves forward, history is retained: windows are closed, never
  deleted; the timeline is append-only and keyed by ``event_id`` so event
  replay is exact-once.
* Identity != employment != role. The canonical person is ``Employee``
  (Phase 2 substrate); this slice adds the temporal + identity planes that
  Phase 2 could not express. Declared profiles are never treated as
  expertise (that is 4F.2+ work).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.timeutils import ensure_aware, utcnow
from app.intelligence.company_context import CallerAccess
from app.models.department import BusinessUnit, Department, Location
from app.models.employee import Employee
from app.models.governance import GovernanceScope
from app.models.people_intelligence import (
    IDENTITY_SOURCES,
    MEMBERSHIP_STATUSES,
    PeopleTimeline,
    PersonIdentity,
    PersonMembership,
    PersonRoleAssignment,
    RELATIONSHIP_TYPES,
    ReportingRelationship,
    ROLE_TYPES,
)
from app.models.project import ProjectMember
from app.models.team import Team, TeamMember

logger = logging.getLogger("vcos.people")

# Relationship columns must be eagerly loaded: reads run in async sessions
# where lazy attribute access would raise.
_PERSON_OPTIONS = (
    selectinload(Employee.department),
    selectinload(Employee.team),
    selectinload(Employee.location),
)

MAX_PEOPLE_LIST = 200
MAX_SEARCH_PEOPLE = 20
MAX_SEARCH_UNITS = 10
MAX_TIMELINE = 50
MAX_GRAPH_NODES = 400
MAX_ANCESTOR_DEPTH = 16
MAX_DIRECT_DEPTH = 16

# Membership status -> live Employee.status mirror (only values the employee
# model actually has are mirrored; richer statuses live in the window row).
_STATUS_TO_EMPLOYEE = {
    "active": "active",
    "invited": "active",
    "probation": "probation",
    "notice": "notice",
    "contractor": "active",
    "consultant": "active",
    "partner": "active",
    "external": "active",
    "suspended": "inactive",
    "inactive": "inactive",
    "departed": "inactive",
}


class PeopleError(ValueError):
    """Domain error; routes map it to an HTTP status."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    return ensure_aware(value).isoformat()


class PeopleEngine:
    # ------------------------------------------------------------------ identity

    async def register_identity(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        person_id: str,
        source: str,
        source_key: str,
        kind: str = "primary",
        verified: bool = False,
        note: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Link one strong identifier to one canonical person.

        A source_key already active on ANOTHER person is never merged
        silently: it raises an ambiguity error. Re-registering the same key
        on the same person is an idempotent refresh.
        """
        if source not in IDENTITY_SOURCES:
            raise PeopleError(f"unknown identity source '{source}'", status=400)
        person = await db.get(Employee, person_id)
        if person is None or person.organization_id != organization_id:
            raise PeopleError("person not found in this organization", status=404)

        existing = (
            await db.execute(
                select(PersonIdentity).where(
                    PersonIdentity.organization_id == organization_id,
                    PersonIdentity.source == source,
                    PersonIdentity.source_key == source_key,
                )
            )
        ).scalars().first()
        if existing is not None:
            if existing.person_id != person_id and existing.status == "active":
                raise PeopleError(
                    f"identifier '{source}:{source_key}' is already linked to another "
                    f"person ({existing.person_id}) — refusing to merge silently",
                    status=409,
                )
            if existing.person_id == person_id:
                existing.kind = kind
                existing.verified = verified or existing.verified
                existing.status = "active"
                existing.note = note or existing.note
                await self.journal(
                    db, organization_id, person_id, kind="identity.linked",
                    title=f"Identity refreshed: {source}",
                    detail=f"Identifier '{source_key}' remains linked to the person.",
                    meta={"source": source, "source_key": source_key, "kind": kind,
                          "verified": existing.verified},
                    source_type="people.identity", source_id=existing.id,
                    actor_id=actor_id,
                )
                return self._identity_payload(existing)
            # retired mapping — allow re-link to the new person
            existing.status = "retired"
        row = PersonIdentity(
            organization_id=organization_id,
            person_id=person_id,
            source=source,
            source_key=source_key,
            kind=kind,
            verified=verified,
            status="active",
            note=note,
            created_by=actor_id,
        )
        db.add(row)
        await db.flush()
        await self.journal(
            db, organization_id, person_id, kind="identity.linked",
            title=f"Identity linked: {source}",
            detail=f"Identifier '{source_key}' is now a {kind} identity of the person.",
            meta={"source": source, "source_key": source_key, "kind": kind,
                  "verified": verified},
            source_type="people.identity", source_id=row.id, actor_id=actor_id,
        )
        return self._identity_payload(row)

    @staticmethod
    def _identity_payload(row: PersonIdentity) -> dict[str, Any]:
        return {
            "id": row.id,
            "person_id": row.person_id,
            "source": row.source,
            "source_key": row.source_key,
            "kind": row.kind,
            "verified": row.verified,
            "status": row.status,
        }

    async def resolve_identity(
        self, db: AsyncSession, *, organization_id: str, source: str, source_key: str
    ) -> dict[str, Any]:
        """Resolve an identifier to a canonical person — or admit ambiguity.

        Returns ``{"person_id": ... | None, "ambiguous": bool, "note": ...}``.
        A retired mapping resolves to nothing; an active key always resolves
        to exactly one person because conflicting links are refused at write.
        """
        row = (
            await db.execute(
                select(PersonIdentity).where(
                    PersonIdentity.organization_id == organization_id,
                    PersonIdentity.source == source,
                    PersonIdentity.source_key == source_key,
                )
            )
        ).scalars().first()
        if row is None:
            return {"person_id": None, "ambiguous": False, "note": "unknown_identifier"}
        if row.status != "active":
            return {"person_id": None, "ambiguous": False, "note": "identifier_retired"}
        return {"person_id": row.person_id, "ambiguous": False, "note": "resolved"}

    async def identities_of(
        self, db: AsyncSession, *, organization_id: str, person_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(PersonIdentity)
                .where(
                    PersonIdentity.organization_id == organization_id,
                    PersonIdentity.person_id == person_id,
                )
                .order_by(PersonIdentity.created_at.asc())
                .limit(50)
            )
        ).scalars().all()
        return [self._identity_payload(row) for row in rows]

    # ------------------------------------------------------------------ canonical sync

    async def ensure_person(
        self, db: AsyncSession, *, organization_id: str, person_id: str
    ) -> None:
        """Make sure a canonical person has membership + email identity rows.

        Idempotent: replay-safe for event-driven handlers. Does not mutate
        existing windows.
        """
        person = await db.get(Employee, person_id)
        if person is None or person.organization_id != organization_id:
            return
        open_window = (
            await db.execute(
                select(PersonMembership).where(
                    PersonMembership.organization_id == organization_id,
                    PersonMembership.person_id == person_id,
                    PersonMembership.valid_to.is_(None),
                )
            )
        ).scalars().first()
        if open_window is None:
            status = _STATUS_TO_EMPLOYEE.get(person.status or "active", "active")
            db.add(
                PersonMembership(
                    organization_id=organization_id,
                    person_id=person_id,
                    employment_status=status,
                    valid_from=ensure_aware(person.joining_date and datetime.combine(
                        person.joining_date, datetime.min.time(), timezone.utc
                    )) if person.joining_date else utcnow(),
                    employment_type=person.employment_type,
                    designation_snapshot=person.designation,
                    source_type="employee.sync", source_id=person.id,
                )
            )
        email_identity = (
            await db.execute(
                select(PersonIdentity).where(
                    PersonIdentity.organization_id == organization_id,
                    PersonIdentity.person_id == person_id,
                    PersonIdentity.source == "email",
                    PersonIdentity.source_key == person.email,
                )
            )
        ).scalars().first()
        if email_identity is None:
            db.add(
                PersonIdentity(
                    organization_id=organization_id,
                    person_id=person_id,
                    source="email",
                    source_key=person.email,
                    kind="primary",
                    verified=True,
                    status="active",
                )
            )

    # ------------------------------------------------------------------ membership

    async def set_membership(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        person_id: str,
        employment_status: str,
        valid_from: Optional[datetime] = None,
        employment_type: Optional[str] = None,
        note: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Close the previous open membership window and open a new one.

        The closed window survives — the full membership history is always
        reconstructable. Mirrors the employee status when the mapped value is
        one the employee model knows.
        """
        if employment_status not in MEMBERSHIP_STATUSES:
            raise PeopleError(f"unknown membership status '{employment_status}'", status=400)
        person = await db.get(Employee, person_id)
        if person is None or person.organization_id != organization_id:
            raise PeopleError("person not found in this organization", status=404)
        opened_at = utcnow()
        now = ensure_aware(valid_from) if valid_from else opened_at

        previous = (
            await db.execute(
                select(PersonMembership).where(
                    PersonMembership.organization_id == organization_id,
                    PersonMembership.person_id == person_id,
                    PersonMembership.valid_to.is_(None),
                )
            )
        ).scalars().first()
        if previous is not None:
            if previous.employment_status == employment_status:
                return self._membership_payload(previous)
            previous.valid_to = now

        row = PersonMembership(
            organization_id=organization_id,
            person_id=person_id,
            employment_status=employment_status,
            valid_from=now,
            employment_type=employment_type or person.employment_type,
            designation_snapshot=person.designation,
            note=note,
            source_type=source_type,
            source_id=source_id,
            actor_id=actor_id,
        )
        db.add(row)
        await db.flush()
        mirrored = _STATUS_TO_EMPLOYEE.get(employment_status)
        if mirrored and mirrored != person.status:
            person.status = mirrored
        await self.journal(
            db, organization_id, person_id, kind="membership.changed",
            title=f"Membership changed to {employment_status}",
            detail=note or f"Employment status is now '{employment_status}'.",
            meta={"employment_status": employment_status, "previous": (
                previous.employment_status if previous else None
            )},
            event_id=event_id, source_type=source_type, source_id=source_id,
            actor_id=actor_id,
        )
        return self._membership_payload(row)

    @staticmethod
    def _membership_payload(row: PersonMembership) -> dict[str, Any]:
        return {
            "id": row.id,
            "person_id": row.person_id,
            "employment_status": row.employment_status,
            "employment_type": row.employment_type,
            "designation_snapshot": row.designation_snapshot,
            "valid_from": _iso(row.valid_from),
            "valid_to": _iso(row.valid_to),
            "source_type": row.source_type,
            "source_id": row.source_id,
        }

    async def membership_history(
        self, db: AsyncSession, *, organization_id: str, person_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(PersonMembership)
                .where(
                    PersonMembership.organization_id == organization_id,
                    PersonMembership.person_id == person_id,
                )
                .order_by(PersonMembership.valid_from.asc())
            )
        ).scalars().all()
        return [self._membership_payload(row) for row in rows]

    # ------------------------------------------------------------------ roles

    async def assign_role(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        person_id: str,
        role_title: str,
        role_type: str = "functional",
        is_primary: bool = False,
        valid_from: Optional[datetime] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Open a new role window for a person.

        A person may hold many roles concurrently; at most one open primary
        role per person — assigning a new primary closes the previous primary
        and mirrors the designation onto the employee profile.
        """
        role_title = (role_title or "").strip()
        if not role_title:
            raise PeopleError("role_title is required", status=400)
        if role_type not in ROLE_TYPES:
            raise PeopleError(f"unknown role type '{role_type}'", status=400)
        person = await db.get(Employee, person_id)
        if person is None or person.organization_id != organization_id:
            raise PeopleError("person not found in this organization", status=404)
        opened_at = utcnow()
        now = ensure_aware(valid_from) if valid_from else opened_at

        primary_demoted: Optional[str] = None
        if is_primary:
            open_primary = (
                await db.execute(
                    select(PersonRoleAssignment).where(
                        PersonRoleAssignment.organization_id == organization_id,
                        PersonRoleAssignment.person_id == person_id,
                        PersonRoleAssignment.is_primary.is_(True),
                        PersonRoleAssignment.valid_to.is_(None),
                    )
                )
            ).scalars().first()
            if open_primary is not None:
                open_primary.valid_to = now
                primary_demoted = open_primary.id

        row = PersonRoleAssignment(
            organization_id=organization_id,
            person_id=person_id,
            role_title=role_title,
            role_type=role_type,
            is_primary=is_primary,
            valid_from=now,
            source_type=source_type,
            source_id=source_id,
            actor_id=actor_id,
        )
        db.add(row)
        await db.flush()
        if is_primary:
            person.designation = role_title
        await self.journal(
            db, organization_id, person_id, kind="role.assigned",
            title=f"Role assigned: {role_title}",
            detail=f"Assigned {role_type} role '{role_title}'"
                   + (" as primary role" if is_primary else ""),
            meta={"role_title": role_title, "role_type": role_type,
                  "is_primary": is_primary, "demoted_primary": primary_demoted},
            event_id=event_id, source_type=source_type, source_id=source_id,
            actor_id=actor_id,
        )
        return self._role_payload(row)

    async def change_role(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        assignment_id: str,
        role_title: Optional[str] = None,
        role_type: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Change a role in place: the old window closes, a continuation
        window opens with the new title/type — history is preserved."""
        row = await db.get(PersonRoleAssignment, assignment_id)
        if row is None or row.organization_id != organization_id:
            raise PeopleError("role assignment not found", status=404)
        if row.valid_to is not None:
            raise PeopleError("role assignment is already closed", status=400)
        if role_type is not None and role_type not in ROLE_TYPES:
            raise PeopleError(f"unknown role type '{role_type}'", status=400)
        new_title = (role_title or row.role_title).strip()
        new_type = role_type or row.role_type
        if not new_title:
            raise PeopleError("role_title is required", status=400)

        now = utcnow()
        row.valid_to = now
        continuation = PersonRoleAssignment(
            organization_id=organization_id,
            person_id=row.person_id,
            role_title=new_title,
            role_type=new_type,
            is_primary=row.is_primary,
            valid_from=now,
            source_type=source_type or row.source_type,
            source_id=source_id or row.source_id,
            actor_id=actor_id,
        )
        db.add(continuation)
        await db.flush()
        if row.is_primary:
            person = await db.get(Employee, row.person_id)
            if person is not None:
                person.designation = new_title
        await self.journal(
            db, organization_id, row.person_id, kind="role.changed",
            title=f"Role changed: {row.role_title} -> {new_title}",
            detail=f"Role type '{row.role_type}' -> '{new_type}'.",
            meta={"assignment_id": row.id, "old_title": row.role_title,
                  "new_title": new_title, "new_type": new_type},
            event_id=event_id, source_type=source_type, source_id=source_id,
            actor_id=actor_id,
        )
        return self._role_payload(continuation)

    async def remove_role(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        assignment_id: str,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Close a role window. The closed window remains in history."""
        row = await db.get(PersonRoleAssignment, assignment_id)
        if row is None or row.organization_id != organization_id:
            raise PeopleError("role assignment not found", status=404)
        if row.valid_to is not None:
            return self._role_payload(row)
        now = utcnow()
        row.valid_to = now
        if row.is_primary:
            person = await db.get(Employee, row.person_id)
            if person is not None and person.designation == row.role_title:
                person.designation = None
        await self.journal(
            db, organization_id, row.person_id, kind="role.removed",
            title=f"Role removed: {row.role_title}",
            detail=f"The {row.role_type} role '{row.role_title}' is no longer active.",
            meta={"assignment_id": row.id, "role_title": row.role_title},
            event_id=event_id, source_type=source_type, source_id=source_id,
            actor_id=actor_id,
        )
        return self._role_payload(row)

    async def roles_of(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
        open_only: bool = False,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(PersonRoleAssignment)
            .where(
                PersonRoleAssignment.organization_id == organization_id,
                PersonRoleAssignment.person_id == person_id,
            )
        )
        if open_only:
            stmt = stmt.where(PersonRoleAssignment.valid_to.is_(None))
        rows = (
            await db.execute(stmt.order_by(PersonRoleAssignment.valid_from.asc()))
        ).scalars().all()
        return [self._role_payload(row) for row in rows]

    @staticmethod
    def _role_payload(row: PersonRoleAssignment) -> dict[str, Any]:
        return {
            "id": row.id,
            "person_id": row.person_id,
            "role_title": row.role_title,
            "role_type": row.role_type,
            "is_primary": row.is_primary,
            "valid_from": _iso(row.valid_from),
            "valid_to": _iso(row.valid_to),
            "source_type": row.source_type,
            "source_id": row.source_id,
        }

    # ------------------------------------------------------------------ reporting

    async def set_reporting(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        person_id: str,
        relationship_type: str,
        manager_person_id: Optional[str] = None,
        valid_from: Optional[datetime] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Open a new reporting window (or close all open ones of a type when
        manager_person_id is None). The open ``reports_to`` window mirrors
        ``Employee.manager_id`` so the live org chart stays coherent; closed
        windows keep the full reporting history."""
        if relationship_type not in RELATIONSHIP_TYPES:
            raise PeopleError(f"unknown relationship type '{relationship_type}'", status=400)
        person = await db.get(Employee, person_id)
        if person is None or person.organization_id != organization_id:
            raise PeopleError("person not found in this organization", status=404)
        manager: Optional[Employee] = None
        if manager_person_id:
            manager = await db.get(Employee, manager_person_id)
            if manager is None or manager.organization_id != organization_id:
                raise PeopleError("manager person not found in this organization", status=404)
            if manager.id == person_id:
                raise PeopleError("a person cannot report to themselves", status=400)
        now = utcnow()
        opened_at = ensure_aware(valid_from) if valid_from else now

        open_windows = (
            await db.execute(
                select(ReportingRelationship).where(
                    ReportingRelationship.organization_id == organization_id,
                    ReportingRelationship.person_id == person_id,
                    ReportingRelationship.relationship_type == relationship_type,
                    ReportingRelationship.valid_to.is_(None),
                )
            )
        ).scalars().all()
        for window in open_windows:
            window.valid_to = opened_at

        if manager is None:
            if relationship_type == "reports_to" and person.manager_id is not None:
                person.manager_id = None
            await self.journal(
                db, organization_id, person_id, kind="relationship.changed",
                title=f"Reporting cleared: {relationship_type}",
                detail=f"The {relationship_type} relationship is no longer active.",
                meta={"relationship_type": relationship_type, "manager_person_id": None},
                event_id=event_id, source_type=source_type, source_id=source_id,
                actor_id=actor_id,
            )
            return {"closed": len(open_windows), "relationship_type": relationship_type,
                    "manager_person_id": None}

        row = ReportingRelationship(
            organization_id=organization_id,
            person_id=person_id,
            relationship_type=relationship_type,
            manager_person_id=manager.id,
            valid_from=opened_at,
            source_type=source_type,
            source_id=source_id,
            actor_id=actor_id,
        )
        db.add(row)
        await db.flush()
        if relationship_type == "reports_to":
            person.manager_id = manager.id
        await self.journal(
            db, organization_id, person_id, kind="relationship.changed",
            title=f"Now {relationship_type}: {manager.full_name}",
            detail=f"{person.full_name} now has a {relationship_type} relationship "
                   f"with {manager.full_name}.",
            meta={"relationship_type": relationship_type, "manager_person_id": manager.id},
            event_id=event_id, source_type=source_type, source_id=source_id,
            actor_id=actor_id,
        )
        return self._reporting_payload(row)

    async def reporting_of(
        self, db: AsyncSession, *, organization_id: str, person_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(ReportingRelationship).where(
                    ReportingRelationship.organization_id == organization_id,
                    ReportingRelationship.person_id == person_id,
                    ReportingRelationship.valid_to.is_(None),
                )
            )
        ).scalars().all()
        return [self._reporting_payload(row) for row in rows]

    @staticmethod
    def _reporting_payload(row: ReportingRelationship) -> dict[str, Any]:
        return {
            "id": row.id,
            "person_id": row.person_id,
            "relationship_type": row.relationship_type,
            "manager_person_id": row.manager_person_id,
            "valid_from": _iso(row.valid_from),
            "valid_to": _iso(row.valid_to),
            "source_type": row.source_type,
            "source_id": row.source_id,
        }

    # ------------------------------------------------------------------ journal

    async def journal(
        self,
        db: AsyncSession,
        organization_id: str,
        person_id: str,
        *,
        kind: str,
        title: str,
        detail: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
        event_id: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> bool:
        """Append one immutable timeline row. Exact-once by event_id."""
        existing = None
        if event_id:
            existing = (
                await db.execute(
                    select(PeopleTimeline).where(
                        PeopleTimeline.organization_id == organization_id,
                        PeopleTimeline.person_id == person_id,
                        PeopleTimeline.event_id == event_id,
                    )
                )
            ).scalars().first()
        if existing is not None:
            return False
        db.add(
            PeopleTimeline(
                organization_id=organization_id,
                person_id=person_id,
                kind=kind,
                title=title,
                detail=detail,
                meta=meta,
                event_id=event_id,
                source_type=source_type,
                source_id=source_id,
                actor_id=actor_id,
                occurred_at=occurred_at or utcnow(),
            )
        )
        return True

    # ------------------------------------------------------------------ governance

    async def visible_person_ids(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess
    ) -> Optional[frozenset[str]]:
        """Visible people for a caller. None = org-wide (every person).

        Scoped callers see: their own person, people anchored by visible
        scopes (team / department / business_unit / project / employee
        entities), and the ancestor-manager chain of visible people — never
        invisible subordinates (downward-only governance).
        """
        if access.org_wide:
            return None
        visible: set[str] = set()
        if access.employee_id:
            visible.add(access.employee_id)

        entity_ids: list[tuple[str, str]] = []
        if access.visible_scope_ids:
            scopes = (
                await db.execute(
                    select(GovernanceScope).where(
                        GovernanceScope.organization_id == organization_id,
                        GovernanceScope.id.in_(set(access.visible_scope_ids)),
                        GovernanceScope.entity_id.isnot(None),
                    )
                )
            ).scalars().all()
            entity_ids = [(s.scope_type, s.entity_id) for s in scopes if s.entity_id]

        team_entities = {eid for stype, eid in entity_ids if stype == "team"}
        department_entities = {eid for stype, eid in entity_ids if stype == "department"}
        project_entities = {eid for stype, eid in entity_ids if stype == "project"}
        bu_entities = {eid for stype, eid in entity_ids if stype == "business_unit"}
        employee_entities = {eid for stype, eid in entity_ids if stype == "employee"}

        if team_entities:
            rows = await db.execute(
                select(Employee.id).where(
                    Employee.organization_id == organization_id,
                    Employee.team_id.in_(team_entities),
                )
            )
            visible.update(rows.scalars().all())
            rows = await db.execute(
                select(TeamMember.employee_id).where(
                    TeamMember.organization_id == organization_id,
                    TeamMember.team_id.in_(team_entities),
                )
            )
            visible.update(rows.scalars().all())
            leads = await db.execute(
                select(Team.lead_id).where(
                    Team.organization_id == organization_id,
                    Team.id.in_(team_entities),
                    Team.lead_id.isnot(None),
                )
            )
            visible.update(leads.scalars().all())
        if department_entities:
            rows = await db.execute(
                select(Employee.id).where(
                    Employee.organization_id == organization_id,
                    Employee.department_id.in_(department_entities),
                )
            )
            visible.update(rows.scalars().all())
            teams_in_dept = await db.execute(
                select(Team.id).where(
                    Team.organization_id == organization_id,
                    Team.department_id.in_(department_entities),
                )
            )
            sub_teams = list(teams_in_dept.scalars().all())
            if sub_teams:
                rows = await db.execute(
                    select(Employee.id).where(
                        Employee.organization_id == organization_id,
                        Employee.team_id.in_(sub_teams),
                    )
                )
                visible.update(rows.scalars().all())
                rows = await db.execute(
                    select(TeamMember.employee_id).where(
                        TeamMember.organization_id == organization_id,
                        TeamMember.team_id.in_(sub_teams),
                    )
                )
                visible.update(rows.scalars().all())
        if project_entities:
            rows = await db.execute(
                select(ProjectMember.employee_id).where(
                    ProjectMember.project_id.in_(project_entities),
                )
            )
            visible.update(rows.scalars().all())
        if bu_entities:
            rows = await db.execute(
                select(Employee.id).where(
                    Employee.organization_id == organization_id,
                    Employee.business_unit_id.in_(bu_entities),
                )
            )
            visible.update(rows.scalars().all())
        if employee_entities:
            visible.update(employee_entities)

        # Ancestor-manager chain of every visible person (bounded walk), so
        # "who manages X" is always answerable within governance.
        if visible:
            managers: set[str] = set()
            queue = list(visible)
            guard = 0
            while queue and guard < MAX_ANCESTOR_DEPTH * MAX_DIRECT_DEPTH:
                current = queue.pop(0)
                guard += 1
                row = (
                    await db.execute(
                        select(Employee.manager_id).where(
                            Employee.organization_id == organization_id,
                            Employee.id == current,
                            Employee.manager_id.isnot(None),
                        )
                    )
                ).scalars().first()
                if row and row not in visible and row not in managers:
                    managers.add(row)
                    queue.append(row)
            visible.update(managers)
        return frozenset(visible)

    @staticmethod
    def _visible_filter(access: CallerAccess, visible: Optional[frozenset[str]]) -> Any:
        if access.org_wide or visible is None:
            return None
        return Employee.id.in_(set(visible))

    async def _require_visible(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess,
        visible: Optional[frozenset[str]], person_id: str,
    ) -> Employee:
        person = await db.get(
            Employee, person_id, options=_PERSON_OPTIONS
        )
        if person is None or person.organization_id != organization_id:
            raise PeopleError("person not found", status=404)
        if visible is not None and person.id not in visible:
            raise PeopleError("person not found", status=404)
        return person

    # ------------------------------------------------------------------ reads

    async def list_people(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess,
        query: Optional[str] = None, limit: int = MAX_PEOPLE_LIST,
    ) -> dict[str, Any]:
        visible = await self.visible_person_ids(db, organization_id=organization_id, access=access)
        scope = "org_wide" if visible is None else "scoped"
        total_stmt = select(func.count(Employee.id)).where(
            Employee.organization_id == organization_id
        )
        if visible is not None:
            total_stmt = total_stmt.where(Employee.id.in_(set(visible)))
        total = (await db.execute(total_stmt)).scalar_one()

        stmt = (
            select(Employee)
            .where(Employee.organization_id == organization_id)
        )
        if visible is not None:
            stmt = stmt.where(Employee.id.in_(set(visible)))
        if query:
            like = f"%{query.strip().lower().replace('%', r'\%').replace('_', r'\_')}%"
            stmt = stmt.where(
                or_(
                    func.lower(Employee.first_name).like(like, escape="\\"),
                    func.lower(Employee.last_name).like(like, escape="\\"),
                    func.lower(Employee.display_name).like(like, escape="\\"),
                    func.lower(Employee.email).like(like, escape="\\"),
                    func.lower(Employee.designation).like(like, escape="\\"),
                    func.lower(Employee.first_name.concat(" ").concat(Employee.last_name)).like(like, escape="\\"),
                )
            )
        rows = (
            await db.execute(
                stmt.options(*_PERSON_OPTIONS)
                .order_by(func.lower(Employee.first_name), func.lower(Employee.last_name))
                .limit(max(1, min(limit, MAX_PEOPLE_LIST)))
            )
        ).scalars().all()
        people = [await self._person_brief(db, organization_id, row, visible) for row in rows]
        return {
            "scope": scope,
            "total_visible": total,
            "returned": len(people),
            "people": people,
        }

    async def _person_brief(
        self, db: AsyncSession, organization_id: str, person: Employee,
        visible: Optional[frozenset[str]],
    ) -> dict[str, Any]:
        primary = (
            await db.execute(
                select(PersonRoleAssignment.role_title).where(
                    PersonRoleAssignment.organization_id == organization_id,
                    PersonRoleAssignment.person_id == person.id,
                    PersonRoleAssignment.is_primary.is_(True),
                    PersonRoleAssignment.valid_to.is_(None),
                )
            )
        ).scalars().first()
        manager_name = None
        if person.manager_id:
            manager = await db.get(Employee, person.manager_id, options=_PERSON_OPTIONS)
            if manager is not None and (visible is None or manager.id in visible):
                manager_name = manager.full_name
        department_name = person.department.name if person.department else None
        team_name = person.team.name if person.team else None
        return {
            "id": person.id,
            "name": person.full_name,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "email": person.email,
            "designation": person.designation,
            "primary_role": primary,
            "department": department_name,
            "team": team_name,
            "status": person.status,
            "manager_id": person.manager_id,
            "manager_name": manager_name,
        }

    async def get_profile(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess,
        person_id: str, include_history: bool = False,
    ) -> dict[str, Any]:
        visible = await self.visible_person_ids(db, organization_id=organization_id, access=access)
        person = await self._require_visible(
            db, organization_id=organization_id, access=access, visible=visible, person_id=person_id
        )
        memberships = await self.membership_history(db, organization_id=organization_id, person_id=person_id)
        roles = await self.roles_of(db, organization_id=organization_id, person_id=person_id)
        reporting = await self.reporting_of(db, organization_id=organization_id, person_id=person_id)
        identities = await self.identities_of(db, organization_id=organization_id, person_id=person_id)
        profile = {
            "id": person.id,
            "name": person.full_name,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "email": person.email,
            "phone": person.phone,
            "designation": person.designation,
            "status": person.status,
            "employment_type": person.employment_type,
            "joining_date": person.joining_date.isoformat() if person.joining_date else None,
            "department": person.department.name if person.department else None,
            "team": person.team.name if person.team else None,
            "location": person.location.name if person.location else None,
            "business_unit": (
                (await db.get(BusinessUnit, person.business_unit_id)).name
                if person.business_unit_id else None
            ),
            "manager_id": person.manager_id,
            "manager_name": (await db.get(Employee, person.manager_id, options=_PERSON_OPTIONS)).full_name
            if person.manager_id else None,
            "current_membership": memberships[-1] if memberships else None,
            "open_roles": [r for r in roles if r["valid_to"] is None],
            "roles_count": len(roles),
            "current_reporting": reporting,
            "identity_count": len(identities),
            "identities": identities,
            "expertise_score": person.expertise_score,
            "profile_completion": person.profile_completion,
            "scope": "org_wide" if visible is None else "scoped",
        }
        if include_history:
            profile["history"] = {
                "memberships": memberships,
                "roles": roles,
                "reporting": await self._reporting_history(
                    db, organization_id=organization_id, person_id=person_id
                ),
                "timeline": await self.timeline(db, organization_id=organization_id, person_id=person_id),
            }
        return profile

    async def _reporting_history(
        self, db: AsyncSession, *, organization_id: str, person_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(ReportingRelationship)
                .where(
                    ReportingRelationship.organization_id == organization_id,
                    ReportingRelationship.person_id == person_id,
                )
                .order_by(ReportingRelationship.valid_from.asc())
            )
        ).scalars().all()
        return [self._reporting_payload(row) for row in rows]

    async def timeline(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
        limit: int = MAX_TIMELINE,
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(PeopleTimeline)
                .where(
                    PeopleTimeline.organization_id == organization_id,
                    PeopleTimeline.person_id == person_id,
                )
                .order_by(PeopleTimeline.occurred_at.desc(), PeopleTimeline.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": row.id,
                "kind": row.kind,
                "title": row.title,
                "detail": row.detail,
                "meta": row.meta,
                "occurred_at": _iso(row.occurred_at),
                "event_id": row.event_id,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "actor_id": row.actor_id,
            }
            for row in rows
        ]

    async def as_of(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess,
        person_id: str, at: datetime,
    ) -> dict[str, Any]:
        """Reconstruct the person's world at a point in time."""
        visible = await self.visible_person_ids(db, organization_id=organization_id, access=access)
        person = await self._require_visible(
            db, organization_id=organization_id, access=access, visible=visible, person_id=person_id
        )
        moment = ensure_aware(at)
        memberships = [
            m for m in await self.membership_history(db, organization_id=organization_id, person_id=person_id)
            if self._open_at(m, moment)
        ]
        roles = [
            r for r in await self.roles_of(db, organization_id=organization_id, person_id=person_id)
            if self._open_at(r, moment)
        ]
        reporting_rows = (
            await db.execute(
                select(ReportingRelationship).where(
                    ReportingRelationship.organization_id == organization_id,
                    ReportingRelationship.person_id == person_id,
                )
            )
        ).scalars().all()
        reporting = [
            self._reporting_payload(row) for row in reporting_rows if self._open_at(row, moment)
        ]
        manager_name = None
        reports_to = [r for r in reporting if r["relationship_type"] == "reports_to"]
        if reports_to:
            manager = await db.get(Employee, reports_to[-1]["manager_person_id"], options=_PERSON_OPTIONS)
            if manager is not None:
                manager_name = manager.full_name
        return {
            "person_id": person_id,
            "name": person.full_name,
            "at": _iso(moment),
            "membership": memberships[-1] if memberships else None,
            "membership_history_at": memberships,
            "roles_at": roles,
            "roles_history_at": [r for r in roles],  # already filtered to the moment
            "reporting_at": reporting,
            "manager_name": manager_name,
            "scope": "org_wide" if visible is None else "scoped",
        }

    @staticmethod
    def _open_at(window: Any, moment: datetime) -> bool:
        starts_raw = window.valid_from if hasattr(window, "valid_from") else window["valid_from"]
        ends_raw = window.valid_to if hasattr(window, "valid_to") else window["valid_to"]

        def _parse(value: Any) -> Any:
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value

        starts_raw, ends_raw = _parse(starts_raw), _parse(ends_raw)
        if starts_raw is None:
            return False
        starts = ensure_aware(starts_raw)
        if starts > moment:
            return False
        if ends_raw is not None:
            ends = ensure_aware(ends_raw)
            if ends <= moment:
                return False
        return True

    async def reporting_line(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess,
        person_id: str,
    ) -> dict[str, Any]:
        """The chain of managers above a person (current reports_to windows)."""
        visible = await self.visible_person_ids(db, organization_id=organization_id, access=access)
        person = await self._require_visible(
            db, organization_id=organization_id, access=access, visible=visible, person_id=person_id
        )
        chain: list[dict[str, Any]] = []
        seen: set[str] = {person_id}
        current = person
        guard = 0
        while guard < MAX_DIRECT_DEPTH:
            guard += 1
            window = (
                await db.execute(
                    select(ReportingRelationship).where(
                        ReportingRelationship.organization_id == organization_id,
                        ReportingRelationship.person_id == current.id,
                        ReportingRelationship.relationship_type == "reports_to",
                        ReportingRelationship.valid_to.is_(None),
                    )
                )
            ).scalars().first()
            manager_id = window.manager_person_id if window else current.manager_id
            if not manager_id or manager_id in seen:
                break
            seen.add(manager_id)
            manager = await db.get(Employee, manager_id, options=_PERSON_OPTIONS)
            if manager is None:
                break
            chain.append(
                {
                    "id": manager.id,
                    "name": manager.full_name,
                    "designation": manager.designation,
                    "department": manager.department.name if manager.department else None,
                    "visible": visible is None or manager.id in visible,
                }
            )
            current = manager
        return {
            "person_id": person_id,
            "person_name": person.full_name,
            "manager_chain": chain,
            "scope": "org_wide" if visible is None else "scoped",
        }

    async def related_people(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess,
        person_id: str,
    ) -> dict[str, Any]:
        """Deterministic "why are these people related" surface: same team,
        same department, same business unit, manager, direct reports, shared
        manager, mentor/mentee relationships."""
        visible = await self.visible_person_ids(db, organization_id=organization_id, access=access)
        person = await self._require_visible(
            db, organization_id=organization_id, access=access, visible=visible, person_id=person_id
        )
        if visible is None:
            candidates = (
                await db.execute(
                    select(Employee)
                    .where(Employee.organization_id == organization_id)
                    .options(*_PERSON_OPTIONS)
                )
            ).scalars().all()
        else:
            candidates = (
                await db.execute(
                    select(Employee)
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.id.in_(set(visible) - {person_id}),
                    )
                    .options(*_PERSON_OPTIONS)
                )
            ).scalars().all()
        seen_ids: set[str] = set()
        relations: list[dict[str, Any]] = []
        reporting = await self._reporting_history(
            db, organization_id=organization_id, person_id=person_id
        )
        open_mentor = [r for r in reporting if r["valid_to"] is None and r["relationship_type"] == "mentor"]
        mentees = (
            await db.execute(
                select(ReportingRelationship.person_id).where(
                    ReportingRelationship.organization_id == organization_id,
                    ReportingRelationship.manager_person_id == person_id,
                    ReportingRelationship.relationship_type == "mentor",
                    ReportingRelationship.valid_to.is_(None),
                )
            )
        ).scalars().all()

        def add(peer: Employee, reason: str, via: Optional[str] = None) -> None:
            if peer.id == person_id or peer.id in seen_ids:
                return
            seen_ids.add(peer.id)
            item = {
                "person_id": peer.id,
                "name": peer.full_name,
                "designation": peer.designation,
                "department": peer.department.name if peer.department else None,
                "team": peer.team.name if peer.team else None,
                "relation": reason,
            }
            if via:
                item["via"] = via
            relations.append(item)

        for peer in candidates:
            if peer.id == person_id:
                continue
            if person.manager_id and peer.id == person.manager_id:
                add(peer, "manager")
            elif person.team_id and peer.team_id == person.team_id:
                add(peer, "same_team", via=person.team.name if person.team else None)
            elif person.department_id and peer.department_id == person.department_id:
                add(peer, "same_department", via=person.department.name if person.department else None)
            elif person.business_unit_id and peer.business_unit_id == person.business_unit_id:
                add(
                    peer, "same_business_unit",
                    via=(await db.get(BusinessUnit, person.business_unit_id)).name
                    if person.business_unit_id else None,
                )
            elif peer.manager_id and peer.manager_id == person.manager_id:
                add(peer, "shared_manager",
                    via=(await db.get(Employee, person.manager_id, options=_PERSON_OPTIONS)).full_name
                    if person.manager_id else None)
            elif peer.manager_id == person.id:
                add(peer, "direct_report")
        for m in open_mentor:
            mentor = await db.get(Employee, m["manager_person_id"], options=_PERSON_OPTIONS)
            if mentor is not None and (visible is None or mentor.id in visible):
                add(mentor, "mentor")
        for mentee_id in mentees:
            mentee = await db.get(Employee, mentee_id, options=_PERSON_OPTIONS)
            if mentee is not None:
                add(mentee, "mentee")
        return {
            "person_id": person_id,
            "person_name": person.full_name,
            "count": len(relations),
            "relations": relations,
            "scope": "org_wide" if visible is None else "scoped",
        }

    async def org_chart(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess
    ) -> dict[str, Any]:
        """Live org chart from current open reports_to windows (fallback:
        Employee.manager_id snapshot). Children only include visible people —
        invisible subordinates are never revealed."""
        visible = await self.visible_person_ids(db, organization_id=organization_id, access=access)
        if visible is None:
            rows = (
                await db.execute(
                    select(Employee)
                    .where(Employee.organization_id == organization_id)
                    .options(*_PERSON_OPTIONS)
                )
            ).scalars().all()
        else:
            rows = (
                await db.execute(
                    select(Employee)
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.id.in_(set(visible)),
                    )
                    .options(*_PERSON_OPTIONS)
                )
            ).scalars().all()
        manager_by_person: dict[str, Optional[str]] = {}
        for person in rows:
            window = (
                await db.execute(
                    select(ReportingRelationship.manager_person_id).where(
                        ReportingRelationship.organization_id == organization_id,
                        ReportingRelationship.person_id == person.id,
                        ReportingRelationship.relationship_type == "reports_to",
                        ReportingRelationship.valid_to.is_(None),
                    )
                )
            ).scalars().first()
            manager_by_person[person.id] = window or person.manager_id
        people = {person.id: person for person in rows}
        visible_set = set(people) if visible is not None else set(people)
        children: dict[str, list[dict[str, Any]]] = {}
        roots: list[dict[str, Any]] = []

        def node(person: Employee) -> dict[str, Any]:
            return {
                "id": person.id,
                "name": person.full_name,
                "designation": person.designation,
                "department": person.department.name if person.department else None,
                "team": person.team.name if person.team else None,
            }

        for person in rows:
            parent = manager_by_person.get(person.id)
            if parent and parent in visible_set:
                children.setdefault(parent, []).append(node(person))
            else:
                roots.append(node(person))
        for key in children:
            children[key].sort(key=lambda n: n["name"].lower())
        roots.sort(key=lambda n: n["name"].lower())
        chart_roots = []
        for root in roots:
            chart_roots.append(self._chart_node(root, children))
        return {
            "scope": "org_wide" if visible is None else "scoped",
            "nodes": len(rows),
            "roots": chart_roots,
        }

    def _chart_node(
        self, node: dict[str, Any], children: dict[str, list[dict[str, Any]]]
    ) -> dict[str, Any]:
        result = dict(node)
        direct = children.get(node["id"], [])
        if direct:
            result["children"] = [self._chart_node(child, children) for child in direct]
        return result

    async def people_graph(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess,
        depth: int = 3,
    ) -> dict[str, Any]:
        """The People Graph: person nodes + team/department entity nodes,
        edges for reporting, membership, department, role. Fully governed —
        only visible people appear, and with them the units they belong to."""
        visible = await self.visible_person_ids(db, organization_id=organization_id, access=access)
        if visible is None:
            rows = (
                await db.execute(
                    select(Employee)
                    .where(Employee.organization_id == organization_id)
                    .options(*_PERSON_OPTIONS)
                )
            ).scalars().all()
        else:
            rows = (
                await db.execute(
                    select(Employee)
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.id.in_(set(visible)),
                    )
                    .options(*_PERSON_OPTIONS)
                )
            ).scalars().all()
        people = {person.id: person for person in rows}
        visible_set = set(people) if visible is not None else set(people)

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        node_keys: set[tuple[str, str]] = set()

        def add_node(ntype: str, nid: str, label: str) -> None:
            key = (ntype, nid)
            if key in node_keys:
                return
            node_keys.add(key)
            nodes.append({"id": nid, "type": ntype, "label": label})

        for person in rows:
            add_node("person", person.id, person.full_name)
            if person.team_id and person.team is not None:
                add_node("team", person.team.id, person.team.name)
                edges.append({"source": person.id, "target": person.team.id, "relation": "member_of"})
            if person.department_id and person.department is not None:
                add_node("department", person.department.id, person.department.name)
                edges.append({"source": person.id, "target": person.department.id, "relation": "in_department"})

        reporting_rows = (
            await db.execute(
                select(ReportingRelationship).where(
                    ReportingRelationship.organization_id == organization_id,
                    ReportingRelationship.valid_to.is_(None),
                )
            )
        ).scalars().all()
        for rel in reporting_rows:
            if rel.person_id not in visible_set or rel.manager_person_id not in visible_set:
                continue
            manager = people[rel.manager_person_id]
            add_node("person", rel.manager_person_id, manager.full_name)
            edges.append({
                "source": rel.person_id,
                "target": rel.manager_person_id,
                "relation": rel.relationship_type,
            })

        role_rows = (
            await db.execute(
                select(PersonRoleAssignment).where(
                    PersonRoleAssignment.organization_id == organization_id,
                    PersonRoleAssignment.valid_to.is_(None),
                    PersonRoleAssignment.person_id.in_(set(visible_set)),
                )
            )
        ).scalars().all()
        for role in role_rows:
            key = ("role", role.role_title)
            add_node("role", f"role:{role.role_title}", role.role_title)
            edges.append({"source": role.person_id, "target": f"role:{role.role_title}",
                          "relation": "holds"})
            _ = key

        if len(nodes) > MAX_GRAPH_NODES:
            nodes = nodes[:MAX_GRAPH_NODES]
            edges = edges[: MAX_GRAPH_NODES * 4]
        nodes.sort(key=lambda n: (n["type"], n["label"].lower()))
        edges.sort(key=lambda e: (e["source"], e["target"], e["relation"]))
        return {
            "scope": "org_wide" if visible is None else "scoped",
            "nodes": nodes,
            "edges": edges,
            "depth": depth,
        }

    async def units_summary(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess
    ) -> dict[str, Any]:
        """Departments and teams with visible member counts."""
        visible = await self.visible_person_ids(db, organization_id=organization_id, access=access)
        employee_filter = Employee.id.in_(set(visible)) if visible is not None else None

        departments = (
            await db.execute(
                select(Department).where(Department.organization_id == organization_id)
            )
        ).scalars().all()
        teams = (
            await db.execute(
                select(Team).where(Team.organization_id == organization_id)
            )
        ).scalars().all()
        dept_rows: list[dict[str, Any]] = []
        for department in departments:
            stmt = select(func.count(Employee.id)).where(
                Employee.organization_id == organization_id,
                Employee.department_id == department.id,
            )
            if employee_filter is not None:
                stmt = stmt.where(employee_filter)
            count = (await db.execute(stmt)).scalar_one()
            dept_rows.append({
                "id": department.id,
                "name": department.name,
                "head_id": department.head_id,
                "members_count": count,
            })
        team_rows: list[dict[str, Any]] = []
        for team in teams:
            stmt = select(func.count(Employee.id)).where(
                Employee.organization_id == organization_id,
                Employee.team_id == team.id,
            )
            if employee_filter is not None:
                stmt = stmt.where(employee_filter)
            count = (await db.execute(stmt)).scalar_one()
            team_rows.append({
                "id": team.id,
                "name": team.name,
                "department_id": team.department_id,
                "lead_id": team.lead_id,
                "members_count": count,
            })
        dept_rows.sort(key=lambda d: d["name"].lower())
        team_rows.sort(key=lambda t: t["name"].lower())
        return {
            "scope": "org_wide" if visible is None else "scoped",
            "departments": dept_rows,
            "teams": team_rows,
        }

    async def unit_members(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess,
        unit_kind: str, unit_id: str,
    ) -> dict[str, Any]:
        """Members of a team / department / business_unit / location."""
        visible = await self.visible_person_ids(db, organization_id=organization_id, access=access)
        unit_kind = unit_kind.strip().lower()
        if unit_kind not in ("team", "department", "business_unit", "location"):
            raise PeopleError("unit_kind must be team|department|business_unit|location", status=400)
        if unit_kind == "team":
            unit = await db.get(Team, unit_id)
            column = Employee.team_id
        elif unit_kind == "department":
            unit = await db.get(Department, unit_id)
            column = Employee.department_id
        elif unit_kind == "business_unit":
            unit = await db.get(BusinessUnit, unit_id)
            column = Employee.business_unit_id
        else:
            unit = await db.get(Location, unit_id)
            column = Employee.location_id
        if unit is None or unit.organization_id != organization_id:
            raise PeopleError("unit not found", status=404)
        stmt = select(Employee).where(
            Employee.organization_id == organization_id,
            column == unit_id,
        )
        if visible is not None:
            stmt = stmt.where(Employee.id.in_(set(visible)))
        rows = (
            await db.execute(
                stmt.order_by(func.lower(Employee.first_name)).options(*_PERSON_OPTIONS)
            )
        ).scalars().all()
        return {
            "unit_kind": unit_kind,
            "unit_id": unit_id,
            "unit_name": unit.name,
            "members_count": len(rows),
            "scope": "org_wide" if visible is None else "scoped",
            "members": [await self._person_brief(db, organization_id, row, visible) for row in rows],
        }

    async def search(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess,
        q: str, limit: int = MAX_SEARCH_PEOPLE,
    ) -> dict[str, Any]:
        """Governed people/team/department search for brain mentions."""
        query = (q or "").strip()
        if not query:
            return {"people": [], "teams": [], "departments": []}
        visible = await self.visible_person_ids(db, organization_id=organization_id, access=access)
        like = f"%{query.lower().replace('%', r'\%').replace('_', r'\_')}%"

        people_stmt = (
            select(Employee)
            .where(
                Employee.organization_id == organization_id,
                or_(
                    func.lower(Employee.first_name).like(like, escape="\\"),
                    func.lower(Employee.last_name).like(like, escape="\\"),
                    func.lower(Employee.display_name).like(like, escape="\\"),
                    func.lower(Employee.email).like(like, escape="\\"),
                    func.lower(Employee.designation).like(like, escape="\\"),
                    func.lower(Employee.first_name.concat(" ").concat(Employee.last_name)).like(like, escape="\\"),
                ),
            )
        )
        if visible is not None:
            people_stmt = people_stmt.where(Employee.id.in_(set(visible)))
        people_rows = (
            await db.execute(
                people_stmt.order_by(func.lower(Employee.first_name))
                .limit(max(1, min(limit, MAX_SEARCH_PEOPLE)))
                .options(*_PERSON_OPTIONS)
            )
        ).scalars().all()
        people = [await self._person_brief(db, organization_id, row, visible) for row in people_rows]

        visible_team_ids: Optional[set[str]] = None
        visible_dept_ids: Optional[set[str]] = None
        if visible is not None and visible:
            team_rows = await db.execute(
                select(Employee.team_id).where(
                    Employee.organization_id == organization_id,
                    Employee.id.in_(set(visible)),
                    Employee.team_id.isnot(None),
                )
            )
            visible_team_ids = set(team_rows.scalars().all())
            dept_rows = await db.execute(
                select(Employee.department_id).where(
                    Employee.organization_id == organization_id,
                    Employee.id.in_(set(visible)),
                    Employee.department_id.isnot(None),
                )
            )
            visible_dept_ids = set(dept_rows.scalars().all())

        teams_stmt = select(Team).where(
            Team.organization_id == organization_id,
            func.lower(Team.name).like(like, escape="\\"),
        )
        if visible_team_ids is not None:
            teams_stmt = teams_stmt.where(Team.id.in_(visible_team_ids))
        teams = [
            {"id": team.id, "name": team.name, "type": "team",
             "department_id": team.department_id}
            for team in (
                await db.execute(teams_stmt.limit(MAX_SEARCH_UNITS))
            ).scalars().all()
        ]

        depts_stmt = select(Department).where(
            Department.organization_id == organization_id,
            func.lower(Department.name).like(like, escape="\\"),
        )
        if visible_dept_ids is not None:
            depts_stmt = depts_stmt.where(Department.id.in_(visible_dept_ids))
        departments = [
            {"id": department.id, "name": department.name, "type": "department"}
            for department in (
                await db.execute(depts_stmt.limit(MAX_SEARCH_UNITS))
            ).scalars().all()
        ]
        return {"people": people, "teams": teams, "departments": departments}


people_engine = PeopleEngine()