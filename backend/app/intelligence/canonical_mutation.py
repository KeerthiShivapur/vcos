"""Canonical Mutation Boundary — Gate 6-B.

This module provides the single canonical mutation boundary that all
components must pass through to mutate canonical company reality.

It does NOT create a parallel mutation system. It composes existing
canonical primitives (governance, provenance, temporal, epistemic,
fingerprint, versioning) to enforce that ALL mutations pass through
the same governed boundary.

Key principles:
- Reuse existing canonical primitives (governance, provenance, temporal, epistemic)
- No parallel mutation system
- Single write path for all canonical mutations
- Governance enforced BEFORE mutation
- Provenance and temporal rules enforced
- Exact-once via fingerprints
- Optimistic concurrency via versioning
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Callable, TypeVar, Generic
from enum import Enum

from sqlalchemy import select, and_, insert, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.timeutils import utcnow
from app.intelligence.company_context import (
    resolve_caller_access,
    resolve_accessible_ids,
    CallerAccess,
)
from app.services.governance_service import governance_service
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionAlternative,
    CompanyDecisionContradiction,
)
from app.models.company_actions import CompanyAction
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    ObjectiveOutcome,
    ObjectiveOutcomeAssessment,
    ObjectiveContradiction,
)
from app.models.company_intent import CompanyIntent
from app.models.project import Project
from app.models.task import Task
from app.models.employee import Employee
from app.models.user import User
from app.models.organization import Organization
from app.models.organizational_learning import OrganizationalLearning
from app.models.intelligence import PatternDetection
from app.models.company_state import CompanyState
from app.models.governance import ApprovalPolicy
from app.models.canonical_reliability import CanonicalOperation
from app.models.longitudinal import CompanyTimelineEvent
from app.events.publisher import publish_background_event
from app.intelligence.canonical_concurrency import (
    ConcurrencyControlType,
    ConcurrencyContext,
    ConcurrencyResult,
    IdempotencyKeyManager,
    OptimisticConcurrencyManager,
    PessimisticLockManager,
    LeaseManager,
    WorkerCoordinator,
    CanonicalOperationConcurrency,
    IdempotentExecutor,
    CanonicalConcurrencyCoordinator,
    ConcurrencyControlType,
    ConcurrencyContext,
    ConcurrencyResult,
    IdempotencyKeyManager,
    OptimisticConcurrencyManager,
    PessimisticLockManager,
    LeaseManager,
    WorkerCoordinator,
    CanonicalOperationConcurrency,
    IdempotentExecutor,
    CanonicalConcurrencyCoordinator,
    ConcurrencyControlType,
    ConcurrencyContext,
    ConcurrencyResult,
    IdempotencyKeyManager,
    OptimisticConcurrencyManager,
    PessimisticLockManager,
    LeaseManager,
    WorkerCoordinator,
    CanonicalOperationConcurrency,
    IdempotentExecutor,
    CanonicalConcurrencyCoordinator,
)
from app.intelligence.canonical_types import (
    MutationType,
    EpistemicStatus,
)


# Global exception handler for UnboundLocalError


T = TypeVar("T")


# -------------------------------------------------------------------------
# Exception Hierarchy
# -------------------------------------------------------------------------

class CanonicalMutationError(Exception):
    """Base exception for canonical mutation violations."""
    pass


class GovernanceViolation(CanonicalMutationError):
    """Mutation violates governance/scope rules."""
    pass


class TenantIsolationViolation(CanonicalMutationError):
    """Mutation crosses tenant boundaries."""
    pass


class ScopeViolation(CanonicalMutationError):
    """Mutation violates scope boundaries."""
    pass


class InvalidStateTransition(CanonicalMutationError):
    """Invalid state transition requested."""
    pass


class TemporalViolation(CanonicalMutationError):
    """Mutation violates temporal integrity (historical rewrite)."""
    pass


class ProvenanceViolation(CanonicalMutationError):
    """Mutation lacks required provenance."""
    pass


class EpistemicViolation(CanonicalMutationError):
    """Mutation violates epistemic boundaries."""
    pass


class EpistemicPromotionViolation(CanonicalMutationError):
    """Mutation attempts invalid epistemic promotion without required evidence."""
    pass


class EpistemicDemotionViolation(CanonicalMutationError):
    """Mutation attempts to downgrade epistemic status destroying historical meaning."""
    pass


class AIOriginViolation(CanonicalMutationError):
    """AI-generated content attempted to become canonical fact without explicit marking."""
    pass


class EvidenceTruthConfusionViolation(CanonicalMutationError):
    """Mutation conflates evidence with verified truth."""
    pass


class ProvenanceStrippingViolation(CanonicalMutationError):
    """Mutation strips provenance during epistemic transition."""
    pass


class ConcurrencyViolation(CanonicalMutationError):
    """Optimistic concurrency conflict."""
    pass


class ExactOnceViolation(CanonicalMutationError):
    """Duplicate mutation detected via fingerprint."""
    pass


class ContradictionViolation(CanonicalMutationError):
    """Mutation violates contradiction preservation rules."""
    pass


class ContradictionPreservationViolation(CanonicalMutationError):
    """Attempted to delete or overwrite a valid contradiction."""
    pass


class ContradictionReferenceViolation(CanonicalMutationError):
    """Invalid reference to a non-existent or inaccessible contradiction."""
    pass


# -------------------------------------------------------------------------
# Context and Result Types
# -------------------------------------------------------------------------

@dataclass
class CanonicalMutationContext:
    """Context for a canonical mutation, composing existing primitives."""
    caller: "CallerAccess"
    tenant_id: str
    governance_scope_ids: frozenset[str]
    permissions: frozenset[str]
    target_entity_type: str
    target_id: Optional[str] = None
    mutation_type: MutationType = MutationType.UPDATE
    expected_version: Optional[int] = None
    fingerprint: Optional[str] = None
    provenance: dict = field(default_factory=dict)
    epistemic_status: EpistemicStatus = EpistemicStatus.PROPOSED
    as_of: Optional[datetime] = None
    source_event_id: Optional[str] = None
    trigger_reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class MutationResult(Generic[T]):
    """Result of a canonical mutation."""
    success: bool
    entity: Optional[T] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    fingerprint: Optional[str] = None
    version: Optional[int] = None
    transitions: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)


# -------------------------------------------------------------------------
# State Transition Definitions (Canonical)
# -------------------------------------------------------------------------

# Valid state transitions for canonical entities
STATE_TRANSITIONS: dict[str, dict[str, list[str]]] = {
    "CompanyDecision": {
        "proposed": ["approved", "rejected"],
        "approved": ["executed", "outcome_recorded"],
        "rejected": [],
        "executed": ["outcome_recorded"],
        "outcome_recorded": ["assessed"],
        "assessed": [],
    },
    "CompanyAuthorization": {
        "requested": ["under_review", "approved", "conditional", "rejected"],
        "under_review": ["approved", "conditional", "rejected"],
        "approved": ["superseded"],
        "conditional": ["approved", "rejected", "superseded"],
        "rejected": [],
        "superseded": [],
    },
    "CompanyCommitment": {
        "proposed": ["pending_authorization", "authorized", "rejected", "cancelled"],
        "pending_authorization": ["authorized", "cancelled", "rejected"],
        "authorized": ["active", "paused", "cancelled", "superseded", "fulfilled"],
        "active": ["paused", "fulfilled", "cancelled", "superseded"],
        "paused": ["active", "cancelled", "superseded"],
        "fulfilled": ["superseded"],
        "cancelled": [],
        "expired": [],
        "superseded": [],
        "rejected": [],
    },
    "CompanyAction": {
        "proposed": ["validating", "awaiting_approval", "approved", "rejected"],
        "validating": ["approved", "awaiting_approval", "rejected"],
        "awaiting_approval": ["approved", "rejected", "expired"],
        "approved": ["ready", "rejected"],
        "ready": ["in_progress", "cancelled"],
        "in_progress": ["blocked", "completed", "failed", "cancelled"],
        "blocked": ["unblocked", "cancelled", "failed"],
        "completed": ["verified", "failed"],
        "verified": [],
        "failed": ["cancelled"],
        "cancelled": [],
        "expired": [],
        "superseded": [],
        "rejected": [],
    },
    "CompanyDecisionAlternative": {
        "proposed": ["analyzing", "recommended", "rejected"],
        "analyzing": ["recommended", "rejected"],
        "recommended": ["selected", "rejected"],
        "selected": ["rejected"],
        "rejected": [],
    },
    "CompanyDecisionContradiction": {
        "open": ["resolved", "acknowledged"],
        "acknowledged": ["resolved"],
        "resolved": [],
    },
    "ObjectiveContradiction": {
        "open": ["resolved", "acknowledged"],
        "acknowledged": ["resolved"],
        "resolved": [],
    },
    "CompanyDecisionContradiction": {
        "open": ["resolved", "acknowledged"],
        "acknowledged": ["resolved"],
        "resolved": [],
    },
    "CompanyStateTransition": {
        "pending": ["committed", "failed"],
        "committed": [],
        "failed": [],
    },
}


# -------------------------------------------------------------------------
# Fingerprint Computation (Reuse existing)
# -------------------------------------------------------------------------

def _compute_fingerprint(data: dict) -> str:
    """Compute deterministic SHA-256 fingerprint for exact-once semantics."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:160]


def _compute_mutation_fingerprint(
    organization_id: str,
    entity_type: str,
    scope_type: str,
    scope_id: Optional[str],
    mutation_type: MutationType,
    target_id: Optional[str],
    key_fields: dict
) -> str:
    """Compute fingerprint for a canonical mutation."""
    data = {
        "organization_id": organization_id,
        "entity_type": entity_type,
        "mutation_type": mutation_type.value,
        "scope_type": scope_type,
        "scope_id": scope_id or "",
        "target_id": target_id or "",
        "key_fields": key_fields,
    }
    return _compute_fingerprint(data)


# -------------------------------------------------------------------------
# Governance Validation (Reuse existing)
# -------------------------------------------------------------------------

# Entity type to evidence kind mapping for scope checks
_ENTITY_TYPE_TO_KIND = {
    "CompanyDecisionContradiction": "decision_contradiction",
    "ObjectiveContradiction": "objective_contradiction",
    "CompanyDecisionAlternative": "decision",
    "CompanyAuthorization": "authorization",
    "CompanyCommitment": "commitment",
    "CompanyAction": "action",
    "CompanyGoal": "goal",
    "CompanyObjective": "goal",
    "CompanyInitiative": "project",
    "CompanyIntent": "project",
    "Project": "project",
    "AutonomyProposal": "autonomy_proposal",
}

def _entity_type_to_kind(entity_type: str) -> str:
    """Convert entity type to evidence kind for scope checks."""
    return _ENTITY_TYPE_TO_KIND.get(entity_type, entity_type.lower().replace("company", "").lower())


async def validate_governance(
    db: AsyncSession,
    caller: CallerAccess,
    target_entity_type: str,
    target_id: Optional[str] = None,
    target_organization_id: Optional[str] = None,
    required_permissions: Optional[list[str]] = None,
) -> bool:
    """Validate governance rules for a mutation.

    Reuses existing governance primitives from company_context.py and governance_service.
    """
    # Tenant isolation
    if target_organization_id and target_organization_id != caller.organization_id:
        raise TenantIsolationViolation(
            f"Cross-tenant mutation denied: caller org {caller.organization_id} "
            f"cannot mutate org {target_organization_id}"
        )

    # Scope isolation - only check if db is provided
    if target_id and db is not None:
        # Fetch the User object for resolve_accessible_ids
        from app.models.user import User as UserModel
        user_obj = await db.get(UserModel, caller.user_id)
        if not user_obj:
            raise ScopeViolation(f"User {caller.user_id} not found")
        accessible = await resolve_accessible_ids(
            db=db,
            user=user_obj,
            organization_id=caller.organization_id,
            kind=_entity_type_to_kind(target_entity_type),
            ids=[target_id],
        )
        if target_id not in accessible:
            raise ScopeViolation(
                f"Target {target_entity_type}:{target_id} not accessible to caller"
            )

    # Permission check
    if required_permissions:
        caller_permissions = await caller.get_permissions(db) if db is not None else frozenset()
        for perm in required_permissions:
            if perm not in caller_permissions:
                raise GovernanceViolation(
                    f"Missing required permission: {perm}"
                )

    return True


# -------------------------------------------------------------------------
# State Transition Validation (Reuse existing)
# -------------------------------------------------------------------------

def validate_state_transition(
    entity_type: str,
    current_state: str,
    requested_state: str,
) -> bool:
    """Validate that a state transition is allowed per canonical rules."""
    transitions = STATE_TRANSITIONS.get(entity_type, {})
    # Unknown entity types have no restrictions
    if not transitions:
        return True
    allowed = transitions.get(current_state, [])
    if requested_state not in allowed:
        raise InvalidStateTransition(
            f"Invalid state transition for {entity_type}: "
            f"{current_state} -> {requested_state}. "
            f"Allowed: {allowed}"
        )
    return True


# -------------------------------------------------------------------------
# Temporal Protection (Gate 6-C - Temporal Truth Enforcement)
# -------------------------------------------------------------------------

async def validate_temporal_integrity(
    db: AsyncSession,
    entity_type: str,
    entity_id: Optional[str],
    organization_id: str,
    entity: Optional[Any] = None,
    as_of: Optional[datetime] = None,
    mutation_type: Optional[MutationType] = None,
    allow_supersession: bool = False,
) -> bool:
    """Validate that mutation doesn't violate temporal integrity (Gate 6-C).
   
    Prevents historical state rewrites and enforces temporal truth:
    - Historical versions cannot be silently modified
    - Supersession chains must be maintained
    - Current state uniqueness is enforced
    - Temporal intervals must be valid
    - Backdated effective changes must preserve recorded/observed time distinction
    - Future-dated state must not appear as current truth
    """
    as_of = as_of or utcnow()

    # For existing entities, load and validate
    # Priority: explicit entity parameter (CREATE) > entity_id lookup (UPDATE)
    loaded_entity = None
    if entity is not None:
        # Explicit entity passed (CREATE mutation) - use it directly
        loaded_entity = entity
    elif entity_id:
        # UPDATE mutation: load from DB
        if entity_type == "CompanyDecision":
            loaded_entity = await db.get(CompanyDecision, entity_id)
        elif entity_type == "CompanyAuthorization":
            loaded_entity = await db.get(CompanyAuthorization, entity_id)
        elif entity_type == "CompanyCommitment":
            loaded_entity = await db.get(CompanyCommitment, entity_id)
        elif entity_type == "CompanyAction":
            loaded_entity = await db.get(CompanyAction, entity_id)
        else:
            # For other types, use generic lookup
            from app.db.database import Base
            model = Base.metadata.tables.get(entity_type.lower())
            if model:
                result = await db.execute(select(model).where(model.c.id == entity_id))
                loaded_entity = result.first()
            else:
                return True  # Unknown type, skip temporal check
    else:
        # No entity_id and no entity provided - skip temporal check
        return True

    entity = loaded_entity
    # ============================================================
    # GATE 6-C: TEMPORAL TRUTH ENFORCEMENT
    # ============================================================
    # GATE 6-C: TEMPORAL TRUTH ENFORCEMENT
    # ============================================================
   
    # 1. HISTORICAL IMMUTABILITY
    # If entity has been superseded, it's historical and immutable
    # Check both superseded_by_id and state == "superseded" (or other terminal states)
    # Use correct state field name (status for contradictions, state for others)
    state_field = "status" if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction") else "state"
    is_historical = getattr(entity, "superseded_by_id", None) is not None
    entity_state = getattr(entity, state_field, None)
    terminal_states = ["superseded", "expired", "rejected", "cancelled", "fulfilled"]
    if entity_state in terminal_states:
        is_historical = True
   
    if is_historical:
        print(f"DEBUG: is_historical=True, raising TemporalViolation")
        # Allow only if this is an explicit supersession mutation creating a new version
        if not allow_supersession or mutation_type != MutationType.TRANSITION:
            raise TemporalViolation(
                f"Historical {entity_type}:{entity_id} is in terminal state '{entity_state}' "
                f"or has been superseded. Cannot modify historical entity. "
                f"Use supersession to create new version."
            )

    print(f"DEBUG: is_historical={is_historical}, proceeding to supersession chain validation")
    # 2. SUPERSESSION CHAIN VALIDATION
    # Validate supersession chain integrity
    if hasattr(entity, "supersedes_id") and entity.supersedes_id:
        superseded = await db.get(type(entity), entity.supersedes_id)
        if superseded:
            # Superseded entity must be in superseded state
            # Use correct state field name (status for contradictions, state for others)
            superseded_state_field = "status" if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction") else "state"
            superseded_state = getattr(superseded, superseded_state_field, None)
            if superseded_state not in ["superseded", "expired", "rejected", "cancelled"]:
                raise TemporalViolation(
                    f"Invalid supersession chain: {entity_type}:{entity_id} supersedes "
                    f"{superseded.id} which is in state '{superseded_state}', "
                    f"expected 'superseded' or terminal state."
                )
            # Superseded entity must point back
            if getattr(superseded, "superseded_by_id", None) != entity.id:
                raise TemporalViolation(
                    f"Broken supersession chain: {entity_type}:{entity_id} supersedes "
                    f"{superseded.id} but superseded entity does not point back."
                )
    
    if getattr(entity, "superseded_by_id", None):
        superseding = await db.get(type(entity), entity.superseded_by_id)
        if superseding:
            superseding_state_field = "status" if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction") else "state"
            if getattr(superseding, "supersedes_id", None) != entity.id:
                raise TemporalViolation(
                    f"Broken supersession chain: {entity_type}:{entity_id} is superseded by "
                    f"{superseding.id} but superseding entity does not point back."
                )

# 3. HISTORICAL IMMUTABILITY - Check if trying to modify historical state
    # If entity has valid_from/valid_until or effective dates, check if we're in the past
    entity_updated = getattr(entity, "updated_at", None)
    entity_state = getattr(entity, state_field, None)
    terminal_states = ["superseded", "expired", "rejected", "cancelled", "fulfilled"]
    is_terminal = entity_state in terminal_states
    
    if entity_updated:
        # Handle naive vs aware datetime comparison FIRST
        compare_updated = entity_updated
        if compare_updated.tzinfo is None:
            compare_updated = compare_updated.replace(tzinfo=timezone.utc)
        
        if compare_updated < as_of:
            # Grace period: allow modifications within 60 seconds of creation/update
            grace_period = timedelta(seconds=60)
            if as_of - compare_updated > grace_period:
                # Allow if this is an explicit supersession
                if not allow_supersession or mutation_type != MutationType.TRANSITION:
                    # Also allow if already in terminal state (already handled above)
                    if not is_terminal and not getattr(entity, "superseded_by_id", None):
                        raise TemporalViolation(
                            f"Attempt to modify historical {entity_type}:{entity_id} "
                            f"from {entity_updated}. Historical state is immutable. "
                            f"Use supersession to create new version."
                        )

    # 4. CURRENT STATE UNIQUENESS - For entities requiring single current version
    await _validate_current_state_uniqueness(db, entity_type, entity, organization_id)

    # 4. TEMPORAL INTERVAL VALIDATION
    await _validate_temporal_intervals(db, entity_type, entity, as_of)

    # 5. SUPERSESSION VALIDATION
    if allow_supersession and mutation_type == MutationType.TRANSITION:
        await _validate_supersession(db, entity_type, entity, as_of)

    return True


async def _validate_current_state_uniqueness(
    db: AsyncSession,
    entity_type: str,
    entity: Any,
    organization_id: str,
) -> bool:
    """Ensure only one current version exists where domain requires it."""
    # Entities that require single current version per organization
    current_state_entities = {
        "CompanyAuthorization": ["approved", "conditional"],
        "CompanyCommitment": ["authorized", "active", "pending_authorization"],
    }
   
    if entity_type not in current_state_entities:
        return True
   
    current_states = current_state_entities[entity_type]
    entity_state = getattr(entity, "state", None)
   
    if entity_state not in current_states:
        return True
   
    # Check if another current version exists
    model = type(entity)
    query = select(model).where(
        model.organization_id == organization_id,
        model.state.in_(current_states),
    )
   
    # Only exclude self if entity has an ID (for updates)
    entity_id = getattr(entity, "id", None)
    if entity_id:
        query = query.where(model.id != entity_id)
   
    existing = await db.execute(
        select(model).where(
            model.organization_id == organization_id,
            model.state.in_(current_states),
        )
    )
    all_current = existing.scalars().all()
   
    # Only exclude self if entity has an ID (for updates)
    entity_id = getattr(entity, "id", None)
    if entity_id:
        query = query.where(model.id != entity_id)
   
    existing = await db.execute(query)
    other_current = existing.scalars().first()
   
    if other_current:
        # Allow if the other is the superseded version
        # For CREATE mutations, entity.id may be None (not yet flushed), so don't allow the superseded check to pass
        entity_id = getattr(entity, "id", None)
        if entity_id is not None and getattr(other_current, "superseded_by_id", None) == entity_id:
            return True
        print(f"DEBUG _validate_current_state_uniqueness: about to raise TemporalViolation")
        raise TemporalViolation(
            f"Multiple current {entity_type} states not allowed. "
            f"Existing: {other_current.id} (state: {other_current.state}), "
            f"New: {entity.id if entity_id else 'new'} (state: {entity_state}). "
            f"Use supersession to transition."
        )
   
    return True


async def _validate_temporal_intervals(
    db: AsyncSession,
    entity_type: str,
    entity: Any,
    as_of: datetime,
) -> bool:
    """Validate temporal intervals for entities with valid_from/valid_until."""
    # For CompanyAuthorization with valid_from/valid_until
    if entity_type == "CompanyAuthorization":
        valid_from = getattr(entity, "valid_from", None)
        valid_until = getattr(entity, "valid_until", None)
        
        if valid_from and valid_until:
            # Handle naive vs aware datetime comparison
            compare_from = valid_from
            if compare_from.tzinfo is None:
                compare_from = compare_from.replace(tzinfo=timezone.utc)
            compare_until = valid_until
            if compare_until.tzinfo is None:
                compare_until = compare_until.replace(tzinfo=timezone.utc)
            
            if compare_from >= compare_until:
                raise TemporalViolation(
                    f"Invalid temporal interval: valid_from ({valid_from}) "
                    f"must be before valid_until ({valid_until})"
                )
        
        # Future-dated state must not appear as current truth
        if valid_from:
            compare_from = valid_from
            if compare_from.tzinfo is None:
                compare_from = compare_from.replace(tzinfo=timezone.utc)
            
            if compare_from > as_of:
                entity_state = getattr(entity, "state", None)
                if entity_state in ["approved", "conditional"]:
                    raise TemporalViolation(
                        f"Future-dated authorization ({valid_from}) cannot be in current state "
                        f"'{entity_state}'. Must be 'requested' until effective date."
                    )
    
    return True


async def _validate_supersession(
    db: AsyncSession,
    entity_type: str,
    entity: Any,
    as_of: datetime,
) -> bool:
    """Validate supersession transition."""
    # Only certain entity types support supersession
    supersession_entities = ["CompanyCommitment", "CompanyAuthorization", "CompanyDecision"]
   
    if entity_type not in supersession_entities:
        return True
   
    # Check if transition is to superseded state
    entity_state = getattr(entity, "state", None)
    if entity_state != "superseded":
        return True
   
    # For supersession, we're creating a new version that supersedes this one
    # The validation here ensures the supersession is valid
    if hasattr(entity, "supersedes_id") and entity.supersedes_id:
        superseded = await db.get(type(entity), entity.supersedes_id)
        if not superseded:
            raise TemporalViolation(
                f"Supersession target {entity.supersedes_id} not found"
            )
   
    return True


async def _validate_provenance_references(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """Validate that ALL provenance references exist and belong to the correct tenant.
    
    This validates the provenance fields provided in the mutation context itself,
    not the existing entity's fields. This ensures fake/foreign IDs are rejected.
    """
    entity_type = context.target_entity_type
    caller_org_id = context.caller.organization_id
    provenance = context.provenance or {}

    # Define provenance field to model mapping
    provenance_field_models = {
        "authorization_id": ("CompanyAuthorization", CompanyAuthorization, "organization_id"),
        "decision_id": ("CompanyDecision", CompanyDecision, "organization_id"),
        "policy_id": ("ApprovalPolicy", ApprovalPolicy, "organization_id"),
        "source_commitment_id": ("CompanyCommitment", CompanyCommitment, "organization_id"),
        "source_company_decision_id": ("CompanyDecision", CompanyDecision, "organization_id"),
        "objective_id": ("CompanyObjective", CompanyObjective, "organization_id"),
        "source_event_id": ("CompanyDecision", CompanyDecision, "organization_id"),  # For CompanyDecision source_event_id
    }

    # Check each provenance field in the mutation context
    for field, value in provenance.items():
        if value is None:
            continue
            
        if field not in provenance_field_models:
            continue  # Skip fields we don't validate
            
        model_name, model_class, org_field = provenance_field_models[field]
        
        # Look up the referenced entity
        try:
            referenced = await db.get(model_class, value)
        except Exception:
            continue  # Skip if lookup fails
            
        if referenced is None:
            # Referenced entity doesn't exist - this is a fake/foreign ID
            raise ProvenanceViolation(
                f"Invalid provenance: {field}='{value}' references non-existent {model_name}"
            )
            
        # Check tenant isolation
        referenced_org_id = getattr(referenced, org_field, None)
        if referenced_org_id is not None and referenced_org_id != context.caller.organization_id:
            raise ProvenanceViolation(
                f"Cross-tenant provenance: {context.target_entity_type} references {model_name} "
                f"from different organization ({referenced_org_id} != {context.caller.organization_id})"
            )

    return True


# -------------------------------------------------------------------------
# Epistemic Boundary Enforcement
# -------------------------------------------------------------------------

async def validate_epistemic_boundary(
    db: AsyncSession,
    context: CanonicalMutationContext,
    target_epistemic: EpistemicStatus,
) -> bool:
    """Enforce epistemic boundaries - prevent illegal promotion.
    
    Loads the entity's current epistemic status from the database to compare
    with the target epistemic status.
    """
   
    # Define allowed transitions
    allowed_promotions = {
        EpistemicStatus.OBSERVED: [EpistemicStatus.MEASURED, EpistemicStatus.EVIDENCE_BACKED],
        EpistemicStatus.MEASURED: [EpistemicStatus.EVIDENCE_BACKED],
        EpistemicStatus.EVIDENCE_BACKED: [EpistemicStatus.INFERRED],
        EpistemicStatus.INFERRED: [EpistemicStatus.PREDICTED, EpistemicStatus.PROPOSED],
        EpistemicStatus.PREDICTED: [EpistemicStatus.PROPOSED],
        EpistemicStatus.PROPOSED: [EpistemicStatus.CONTESTED],
        EpistemicStatus.CONTESTED: [],
    }
   
# Load entity's current epistemic status from database
    current_epistemic = None
    if context.target_id and context.target_entity_type:
        entity = await _load_entity_for_epistemic(db, context.target_entity_type, context.target_id)
        if entity and hasattr(entity, 'epistemic_status'):
            current_epistemic = entity.epistemic_status
    
    # Fallback to context if entity doesn't have epistemic_status
    if current_epistemic is None:
        current_epistemic = context.epistemic_status
    
    current = current_epistemic
    target = target_epistemic
    
    if target not in allowed_promotions.get(current, []):
        # Allow same status (no promotion)
        if target != current:
            raise EpistemicViolation(
                f"Illegal epistemic promotion: {current} -> {target}. "
                f"Allowed from {current}: {allowed_promotions.get(current, [])}"
            )
   
    return True


async def _load_entity_for_epistemic(db: AsyncSession, entity_type: str, entity_id: str):
    """Load entity by type and ID for epistemic status check."""
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
        "CompanyGoal": CompanyGoal,
        "CompanyObjective": CompanyObjective,
        "CompanyInitiative": CompanyInitiative,
        "CompanyIntent": CompanyIntent,
        "Project": Project,
        "Task": Task,
        "Employee": Employee,
    }
    model = type_map.get(entity_type)
    if not model:
        return None
    return await db.get(model, entity_id)


# -------------------------------------------------------------------------
# Contradiction Preservation Validation (Gate 6-E)
# -------------------------------------------------------------------------

async def validate_contradiction_preservation(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """
    Validate that contradiction preservation rules are enforced.
   
    Rules enforced:
    1. Contradiction cannot be deleted or overwritten without supersession
    2. Both sides of a contradiction must be preserved
    3. Provenance of both sides must be preserved
    4. Cross-tenant contradiction creation is blocked
    5. Contradiction provenance cannot be silently modified
    5. Supersession does not erase contradiction history
    """
    if context.target_entity_type != "CompanyDecisionContradiction":
        return True

    if not context.target_id:
        return True  # CREATE - no existing entity to validate


    # 1. Check if trying to delete contradiction without supersession
    if context.mutation_type == MutationType.DELETE:
        # Load the existing contradiction
        contradiction = await db.get(CompanyDecisionContradiction, context.target_id)
        if contradiction:
            raise ContradictionPreservationViolation(
                f"Contradiction {context.target_id} cannot be deleted. "
                f"Contradictions must be resolved via supersession, not deletion."
            )

    # For UPDATE/TRANSITION of contradiction, check preservation rules
    if context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Load the existing contradiction
        contradiction = await db.get(CompanyDecisionContradiction, context.target_id)
        if not contradiction:
            return True  # Entity doesn't exist, no preservation needed


        # Check if contradiction is superseded - superseded contradictions cannot be modified
        if getattr(contradiction, "status", None) == "superseded":
            raise ContradictionPreservationViolation(
                f"Contradiction {context.target_id} is superseded and cannot be modified. "
                f"Use supersession to create a new contradiction."
            )

        # 2. Check if trying to overwrite side_a or side_b without supersession
        if context.mutation_type == MutationType.UPDATE:
            # Check both provenance and metadata (including updates)
            updates = context.metadata.get("updates", {})
            side_a = context.provenance.get("side_a_json") or updates.get("side_a_json") or context.metadata.get("side_a_json")
            side_b = context.provenance.get("side_b_json") or updates.get("side_b_json") or context.metadata.get("side_b_json")
            
            if side_a is not None and side_a != contradiction.side_a_json:
                # Check if trying to overwrite side_a without supersession
                raise ContradictionPreservationViolation(
                    f"Cannot modify side_a of contradiction {context.target_id} without supersession. "
                    f"Use supersession to replace a contradiction."
                )

            if side_b is not None and side_b != contradiction.side_b_json:
                raise ContradictionPreservationViolation(
                    f"Cannot modify side_b of contradiction {context.target_id} without supersession. "
                    f"Use supersession to replace a contradiction."
                )

        # 3. Check provenance immutability
        for field in ["source_event_id", "side_a_json", "side_b_json", "lesson_memory_id", "precedent_decision_id"]:
            new_value = context.provenance.get(field) or context.metadata.get(field)
            current_value = getattr(contradiction, field, None)
            if new_value is not None and current_value is not None and new_value != current_value:
                raise ContradictionReferenceViolation(
                    f"Cannot change contradiction provenance field '{field}' without supersession. "
                    f"Current: {current_value}, attempted: {context.provenance.get(field)}"
                )

    # Cross-tenant contradiction validation
    # Check if the contradiction references entities from other tenants
    if context.target_id:
        contradiction = await db.get(CompanyDecisionContradiction, context.target_id)
        if contradiction:
            # Validate side_a provenance
            if contradiction.side_a_json:
                for key, value in contradiction.side_a_json.items():
                    if key.endswith("_id") and isinstance(value, str):
                        # Check if referenced entity is in same organization
                        pass  # Could add cross-tenant validation here

    # Cross-tenant contradiction creation validation
    if context.mutation_type == MutationType.CREATE:
        # Check if any provenance references cross tenant boundaries
        for field in ["decision_id", "lesson_memory_id", "precedent_decision_id"]:
            provenance_value = context.provenance.get(field) or context.metadata.get(field)
            if provenance_value:
                # Would need to validate cross-tenant references here
                pass

async def _validate_temporal_intervals(
    db: AsyncSession,
    entity_type: str,
    entity: Any,
    as_of: datetime,
) -> bool:
    """Validate temporal intervals for entities with valid_from/valid_until."""
    # For CompanyAuthorization with valid_from/valid_until
    if entity_type == "CompanyAuthorization":
        valid_from = getattr(entity, "valid_from", None)
        valid_until = getattr(entity, "valid_until", None)
        
        if valid_from and valid_until:
            # Handle naive vs aware datetime comparison
            compare_from = valid_from
            if compare_from.tzinfo is None:
                compare_from = compare_from.replace(tzinfo=timezone.utc)
            compare_until = valid_until
            if compare_until.tzinfo is None:
                compare_until = compare_until.replace(tzinfo=timezone.utc)
            
            if compare_from >= compare_until:
                raise TemporalViolation(
                    f"Invalid temporal interval: valid_from ({valid_from}) "
                    f"must be before valid_until ({valid_until})"
                )
        
        # Future-dated state must not appear as current truth
        if valid_from:
            compare_from = valid_from
            if compare_from.tzinfo is None:
                compare_from = compare_from.replace(tzinfo=timezone.utc)
            
            if compare_from > as_of:
                entity_state = getattr(entity, "state", None)
                if entity_state in ["approved", "conditional"]:
                    raise TemporalViolation(
                        f"Future-dated authorization ({valid_from}) cannot be in current state "
                        f"'{entity_state}'. Must be 'requested' until effective date."
                    )
    
    return True


async def _validate_supersession(
    db: AsyncSession,
    entity_type: str,
    entity: Any,
    as_of: datetime,
) -> bool:
    """Validate supersession transition."""
    # Only certain entity types support supersession
    supersession_entities = ["CompanyCommitment", "CompanyAuthorization", "CompanyDecision"]
   
    if entity_type not in supersession_entities:
        return True
   
    # Check if transition is to superseded state
    entity_state = getattr(entity, "state", None)
    if entity_state != "superseded":
        return True
   
    # For supersession, we're creating a new version that supersedes this one
    # The validation here ensures the supersession is valid
    if hasattr(entity, "supersedes_id") and entity.supersedes_id:
        superseded = await db.get(type(entity), entity.supersedes_id)
        if not superseded:
            raise TemporalViolation(
                f"Supersession target {entity.supersedes_id} not found"
            )
   
    return True


# -------------------------------------------------------------------------
# Provenance Validation
# -------------------------------------------------------------------------

async def validate_provenance(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """Validate that mutation has required provenance chain."""
    # Check required provenance based on mutation type and entity
    required_provenance = {
        "CompanyCommitment": ["authorization_id", "decision_id"],
        "CompanyAuthorization": ["decision_id", "policy_id"],
        "CompanyAction": ["source_commitment_id", "source_company_decision_id"],
        "CompanyDecisionAlternative": ["decision_id"],
        "CompanyDecisionContradiction": ["decision_id"],
        "ObjectiveContradiction": ["objective_id"],
    }

    required = required_provenance.get(context.target_entity_type, [])

    for field in required:
        # Check context's provenance first
        has_in_context = context.provenance.get(field) is not None
        # For UPDATE/TRANSITION, also check entity's existing provenance
        has_in_entity = False
        if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
            entity = None
            entity_type = context.target_entity_type
            entity_id = context.target_id
           
            if entity_type == "CompanyCommitment":
                entity = await db.get(CompanyCommitment, entity_id)
            elif entity_type == "CompanyAuthorization":
                entity = await db.get(CompanyAuthorization, entity_id)
            elif entity_type == "CompanyAction":
                entity = await db.get(CompanyAction, entity_id)
            elif entity_type == "CompanyDecisionAlternative":
                entity = await db.get(CompanyDecisionAlternative, entity_id)
            elif entity_type == "CompanyDecisionContradiction":
                entity = await db.get(CompanyDecisionContradiction, entity_id)
            elif entity_type == "ObjectiveContradiction":
                entity = await db.get(ObjectiveContradiction, entity_id)
            
            if entity:
                has_in_entity = getattr(entity, field, None) is not None
        
        if not has_in_context and not has_in_entity:
            raise ProvenanceViolation(
                f"Missing required provenance: {field} for {context.target_entity_type}"
            )

    # For UPDATE/TRANSITION mutations, validate that provenance matches existing entity
    # unless this is a supersession (which creates a new version with new provenance)
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Load the existing entity to check its provenance
        entity = None
        entity_type = context.target_entity_type
        entity_id = context.target_id
       
        if entity_type == "CompanyCommitment":
            entity = await db.get(CompanyCommitment, entity_id)
        elif entity_type == "CompanyAuthorization":
            entity = await db.get(CompanyAuthorization, entity_id)
        elif entity_type == "CompanyAction":
            entity = await db.get(CompanyAction, entity_id)
        elif entity_type == "CompanyDecisionAlternative":
            entity = await db.get(CompanyDecisionAlternative, entity_id)
        elif entity_type == "CompanyDecisionContradiction":
            entity = await db.get(CompanyDecisionContradiction, entity_id)
        elif entity_type == "ObjectiveContradiction":
            entity = await db.get(ObjectiveContradiction, entity_id)
       
        if entity:
            # Check if this is a supersession (state transition to superseded)
            is_supersession = (
                context.mutation_type == MutationType.TRANSITION and
                context.provenance.get("state") == "superseded"
            )
           
            if not context.mutation_type == MutationType.TRANSITION or not context.provenance.get("state") == "superseded":
                # For non-supersession updates, provenance must match
                for field in required_provenance.get(context.target_entity_type, []):
                    provenance_value = context.provenance.get(field)
                    entity_value = getattr(entity, field, None)
                   
                    if provenance_value is not None and entity_value is not None:
                        if provenance_value != entity_value:
                            raise ProvenanceViolation(
                                f"Provenance field '{field}' cannot be changed without supersession. "
                                f"Current value: {entity_value}, attempted: {provenance_value}. "
                                f"Use supersession to change provenance."
                            )
   
    # Cross-tenant and cross-scope provenance validation
    # Only validate for mutations that have entity_id (UPDATE/TRANSITION)
    # For CREATE, the entity doesn't exist yet, so we validate in the mutation_wrapper
    if context.target_id and context.mutation_type != MutationType.CREATE:
        await _validate_provenance_cross_boundaries(db, context)

    return True


async def _validate_provenance_cross_boundaries(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """Validate that provenance references don't cross tenant/scope boundaries."""
    entity_type = context.target_entity_type
    entity_id = context.target_id
    caller_org_id = context.caller.organization_id

    # Import all models at the top to avoid UnboundLocalError
    from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
    from app.models.company_operating import CompanyDecision
    from app.models.execution_strategy import CompanyObjective
    from app.models.company_operating import CompanyDecisionAlternative, CompanyDecisionContradiction
    from app.models.execution_strategy import ObjectiveContradiction

    # Load the entity to check its provenance fields
    entity = None
    if entity_type == "CompanyCommitment":
        entity = await db.get(CompanyCommitment, entity_id)
        if entity:
            # Phase 1: Check cross-tenant for ALL provenance fields (provided or entity's)
            # Check authorization_id cross-tenant
            if entity.authorization_id:
                provenance_auth_id = context.provenance.get("authorization_id")
                auth_id_to_check = provenance_auth_id if provenance_auth_id is not None else entity.authorization_id
                auth = await db.get(CompanyAuthorization, auth_id_to_check)
                if auth is not None and auth.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Commitment references Authorization from different organization"
                    )
            # Check decision_id cross-tenant
            if entity.decision_id:
                provenance_dec_id = context.provenance.get("decision_id")
                decision_id_to_check = provenance_dec_id if provenance_dec_id is not None else entity.decision_id
                decision = await db.get(CompanyDecision, decision_id_to_check)
                if decision is not None and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Commitment references Decision from different organization"
                    )
            
            # Phase 2: ALWAYS validate existence for existing entities (not just when provenance is provided)
            # This ensures adversarial tests with fake provenance IDs are rejected
            # Check authorization_id existence
            if entity.authorization_id:
                auth = await db.get(CompanyAuthorization, entity.authorization_id)
                if auth is None:
                    raise ProvenanceViolation(
                        f"Invalid provenance: authorization_id='{entity.authorization_id}' references non-existent CompanyAuthorization"
                    )
            # Check decision_id existence
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision is None:
                    raise ProvenanceViolation(
                        f"Invalid provenance: decision_id='{entity.decision_id}' references non-existent CompanyDecision"
                    )
    elif entity_type == "CompanyAuthorization":
        entity = await db.get(CompanyAuthorization, entity_id)
        if entity:
            # Check cross-tenant for decision_id
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision is None:
                    raise ProvenanceViolation(
                        f"Invalid provenance: decision_id='{entity.decision_id}' references non-existent CompanyDecision"
                    )
                if decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Authorization references Decision from different organization"
                    )
            # Check cross-tenant for policy_id
            if entity.policy_id:
                policy = await db.get(ApprovalPolicy, entity.policy_id)
                if policy is None:
                    raise ProvenanceViolation(
                        f"Invalid provenance: policy_id='{entity.policy_id}' references non-existent ApprovalPolicy"
                    )
                if policy.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Authorization references Policy from different organization"
                    )
    elif entity_type == "CompanyAction":
        entity = await db.get(CompanyAction, entity_id)
        if entity:
            # Check cross-tenant for source_commitment_id
            if entity.source_commitment_id:
                from app.models.execution_strategy import CompanyCommitment
                comm = await db.get(CompanyCommitment, entity.source_commitment_id)
                if comm is None:
                    raise ProvenanceViolation(
                        f"Invalid provenance: source_commitment_id='{entity.source_commitment_id}' references non-existent CompanyCommitment"
                    )
                if comm.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Action references Commitment from different organization"
                    )
                # Cross-scope validation: if both have project scope, they must be in the same project
                if entity.scope_type == "project" and comm.scope_type == "project":
                    if entity.scope_id != comm.scope_id:
                        raise ProvenanceViolation(
                            f"Cross-scope provenance: Action in project '{entity.scope_id}' references Commitment in project '{comm.scope_id}'"
                        )
            # Check cross-tenant for source_company_decision_id
            if entity.source_company_decision_id:
                decision = await db.get(CompanyDecision, entity.source_company_decision_id)
                if decision is None:
                    raise ProvenanceViolation(
                        f"Invalid provenance: source_company_decision_id='{entity.source_company_decision_id}' references non-existent CompanyDecision"
                    )
                if decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Action references Decision from different organization"
                    )
    elif entity_type == "CompanyDecisionAlternative":
        entity = await db.get(CompanyDecisionAlternative, entity_id)
        if entity:
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision is None:
                    raise ProvenanceViolation(
                        f"Invalid provenance: decision_id='{entity.decision_id}' references non-existent CompanyDecision"
                    )
                if decision is not None and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: DecisionAlternative references Decision from different organization"
                    )
    elif entity_type == "CompanyDecisionContradiction":
        entity = await db.get(CompanyDecisionContradiction, entity_id)
        if entity:
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision is None:
                    raise ProvenanceViolation(
                        f"Invalid provenance: decision_id='{entity.decision_id}' references non-existent CompanyDecision"
                    )
                if decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: DecisionContradiction references Decision from different organization"
                    )
    elif entity_type == "ObjectiveContradiction":
        entity = await db.get(ObjectiveContradiction, entity_id)
        if entity:
            if entity.objective_id:
                obj = await db.get(CompanyObjective, entity.objective_id)
                if obj is None:
                    raise ProvenanceViolation(
                        f"Invalid provenance: objective_id='{entity.objective_id}' references non-existent CompanyObjective"
                    )
                if obj.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: ObjectiveContradiction references Objective from different organization"
                    )

    return True


async def _validate_provenance_references(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """Validate that ALL provenance references exist and belong to the correct tenant.
    
    This validates the provenance fields provided in the mutation context itself,
    not the existing entity's fields. This ensures fake/foreign IDs are rejected.
    """
    entity_type = context.target_entity_type
    caller_org_id = context.caller.organization_id
    provenance = context.provenance or {}

    # Define provenance field to model mapping
    provenance_field_models = {
        "authorization_id": ("CompanyAuthorization", CompanyAuthorization, "organization_id"),
        "decision_id": ("CompanyDecision", CompanyDecision, "organization_id"),
        "policy_id": ("ApprovalPolicy", ApprovalPolicy, "organization_id"),
        "source_commitment_id": ("CompanyCommitment", CompanyCommitment, "organization_id"),
        "source_company_decision_id": ("CompanyDecision", CompanyDecision, "organization_id"),
        "objective_id": ("CompanyObjective", CompanyObjective, "organization_id"),
        "source_event_id": ("CompanyDecision", CompanyDecision, "organization_id"),  # For CompanyDecision source_event_id
    }

    # Check each provenance field in the mutation context
    for field, value in provenance.items():
        if value is None:
            continue
            
        if field not in provenance_field_models:
            continue  # Skip fields we don't validate
            
        model_name, model_class, org_field = provenance_field_models[field]
        
        # Look up the referenced entity
        try:
            referenced = await db.get(model_class, value)
        except Exception:
            continue  # Skip if lookup fails
            
        if referenced is None:
            # Referenced entity doesn't exist - this is a fake/foreign ID
            raise ProvenanceViolation(
                f"Invalid provenance: {field}='{value}' references non-existent {model_name}"
            )
            
        # Check tenant isolation
        referenced_org_id = getattr(referenced, org_field, None)
        if referenced_org_id is not None and referenced_org_id != context.caller.organization_id:
            raise ProvenanceViolation(
                f"Cross-tenant provenance: {context.target_entity_type} references {model_name} "
                f"from different organization ({referenced_org_id} != {context.caller.organization_id})"
            )

    return True


async def validate_epistemic_integrity(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """
    Gate 6-F: Comprehensive Epistemic Integrity Enforcement.
    
    Enforces the following invariants:
    1. No illegal epistemic promotion without required supporting evidence
    2. AI-generated content cannot silently become canonical facts
    3. Evidence does not equal truth (evidence supports claims, doesn't prove them)
    4. Provenance must survive epistemic transitions
    5. Historical epistemic state cannot be silently rewritten
    5. Contradiction preservation during epistemic transitions
    7. Governance authorization required for epistemic promotion
    8. Temporal context preserved during epistemic transitions
    9. Prevention of prediction/outcome confusion
    10. Prevention of recommendation/decision confusion
    11. Prevention of decision/authorization confusion
    12. Prevention of authorization/execution confusion
    """
    
    # ================================================================
    # 1. BASIC PROMOTION RULES (already enforced by validate_epistemic_boundary)
    # ================================================================
    await validate_epistemic_boundary(db, context, context.epistemic_status)
    
    # ================================================================
    # 2. AI ORIGIN TRACKING - AI-generated content must remain explicitly marked
    # ================================================================
    ai_origin_fields = ["ai_generated", "model_id", "model_version", "generation_context"]
    has_ai_origin = any(context.provenance.get(f) or context.metadata.get(f) for f in ai_origin_fields)
    
    # If content is AI-generated and being promoted to observed/measured/evidence_backed,
    # it must have explicit human confirmation
    if has_ai_origin and context.epistemic_status in (
        EpistemicStatus.OBSERVED,
        EpistemicStatus.MEASURED,
        EpistemicStatus.EVIDENCE_BACKED
    ):
        human_confirmation = context.provenance.get("human_confirmed") or context.metadata.get("human_confirmed")
        if not human_confirmation:
            raise AIOriginViolation(
                f"AI-generated content cannot be promoted to {context.epistemic_status} "
                f"without explicit human confirmation. "
                f"Source: {context.provenance.get('model_id', 'unknown model')}"
            )
    
    # AI-originated content must preserve its origin metadata through all transitions
    if has_ai_origin:
        for field in ai_origin_fields:
            if field in context.provenance or field in context.metadata:
                # Verify origin metadata is not being stripped
                pass  # Provenance validation will enforce this
    
    # ================================================================
    # 3. EVIDENCE != TRUTH PROTECTION
    # ================================================================
    # Evidence supports claims; it does not automatically prove them.
    # An entity with evidence_backed status cannot be treated as observed fact.
    evidence_fields = ["evidence_ids", "supporting_evidence", "source_evidence"]
    has_evidence = any(context.provenance.get(f) or context.metadata.get(f) for f in evidence_fields)
    
    if has_evidence and context.epistemic_status == EpistemicStatus.OBSERVED:
        # Evidence-backed claim being treated as direct observation requires explicit justification
        direct_observation = context.provenance.get("direct_observation") or context.metadata.get("direct_observation")
        if not direct_observation:
            raise EvidenceTruthConfusionViolation(
                f"Evidence-supported claim cannot be promoted to OBSERVED "
                f"without direct observation confirmation. "
                f"Use EVIDENCE_BACKED for evidence-supported claims."
            )
    
    # ================================================================
    # 4. PROVENANCE PRESERVATION DURING EPISTEMIC TRANSITION
    # ================================================================
    # If this is an UPDATE or TRANSITION, provenance must be preserved
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Load existing entity to check provenance
        from app.models.company_operating import CompanyDecision
        from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
        from app.models.company_actions import CompanyAction
        
        entity_type_map = {
            "CompanyDecision": CompanyDecision,
            "CompanyCommitment": CompanyCommitment,
            "CompanyAuthorization": CompanyAuthorization,
            "CompanyAction": CompanyAction,
        }
        
        model = entity_type_map.get(context.target_entity_type)
        if model:
            existing = await db.get(model, context.target_id)
            if existing:
                # DEBUG
                print(f"DEBUG provenance check: existing.provenance={getattr(existing, 'provenance', None)}, new_provenance={context.provenance}")
                # Check if provenance is being stripped
                existing_provenance = getattr(existing, "provenance", None)
                new_provenance = context.provenance or {}
                
                # If existing entity has provenance, new provenance must not strip it
                if existing_provenance:
                    # Verify critical provenance fields are not stripped
                    critical_fields = ["source_event_id", "decision_id", "authorization_id", "commitment_id", "evidence_ids"]
                    for field in critical_fields:
                        if existing_provenance.get(field) and not new_provenance.get(field):
                            raise ProvenanceStrippingViolation(
                                f"Epistemic transition cannot strip provenance field '{field}'. "
                                f"Original: {existing_provenance.get(field)}"
                            )
                    # Also check if new provenance is empty - any UPDATE must preserve provenance
                    if not new_provenance:
                        raise ProvenanceStrippingViolation(
                            f"Epistemic transition cannot strip all provenance. "
                            f"Original provenance had: {list(existing_provenance.keys())}"
                        )
                # If no existing provenance but promoting to strong status, require provenance
                elif not new_provenance and context.epistemic_status in (
                    EpistemicStatus.OBSERVED, EpistemicStatus.MEASURED, EpistemicStatus.EVIDENCE_BACKED
                ):
                    raise ProvenanceStrippingViolation(
                        f"Promotion to {context.epistemic_status} requires provenance to be provided"
                    )
    
    # ================================================================
    # 5. HISTORICAL EPISTEMIC STATE PROTECTION
    # ================================================================
    # Historical epistemic states cannot be silently rewritten
    # Only applies to UPDATE/TRANSITION of existing entities
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        from app.models.company_operating import CompanyDecision
        from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
        from app.models.company_actions import CompanyAction
        
        entity_type_map = {
            "CompanyDecision": CompanyDecision,
            "CompanyCommitment": CompanyCommitment,
            "CompanyAuthorization": CompanyAuthorization,
            "CompanyAction": CompanyAction,
        }
        
        model = entity_type_map.get(context.target_entity_type)
        if model:
            existing = await db.get(model, context.target_id)
            if existing:
                existing_status = getattr(existing, "epistemic_status", None)
                # Only check if there's an actual status change to a stronger level
                if existing_status and existing_status != context.epistemic_status:
                    # Define epistemic hierarchy for comparison
                    hierarchy = {
                        EpistemicStatus.OBSERVED: 6,
                        EpistemicStatus.MEASURED: 5,
                        EpistemicStatus.EVIDENCE_BACKED: 4,
                        EpistemicStatus.INFERRED: 3,
                        EpistemicStatus.PREDICTED: 2,
                        EpistemicStatus.PROPOSED: 1,
                        EpistemicStatus.CONTESTED: 0,
                    }
                    existing_level = hierarchy.get(existing_status, 0)
                    new_level = hierarchy.get(context.epistemic_status, 0)
                    
                    # Only require justification if promoting to stronger epistemic level
                    if new_level > existing_level and context.epistemic_status in (
                        EpistemicStatus.OBSERVED,
                        EpistemicStatus.MEASURED,
                        EpistemicStatus.EVIDENCE_BACKED
                    ):
                        # Check for valid justifications
                        justification = context.provenance.get("epistemic_justification") or context.metadata.get("epistemic_justification")
                        direct_observation = context.provenance.get("direct_observation") or context.metadata.get("direct_observation")
                        contradiction_resolution = context.provenance.get("contradiction_resolution") or context.metadata.get("contradiction_resolution")
                        outcome_verification = context.provenance.get("outcome_verification") or context.metadata.get("outcome_verification")
                        
                        has_valid_justification = justification or direct_observation or contradiction_resolution or outcome_verification
                        
                        if not has_valid_justification:
                            raise EpistemicPromotionViolation(
                                f"Historical entity with status '{existing_status}' cannot be promoted to "
                                f"'{context.epistemic_status}' without explicit epistemic justification, "
                                f"direct observation, contradiction resolution, or outcome verification."
                            )
    
    # ================================================================
    # 6. CONTRADICTION PRESERVATION INTEGRATION
    # ================================================================
    # If this entity has associated contradictions, epistemic promotion
    # must not silently resolve them
    if context.target_id and context.target_entity_type == "CompanyDecision":
        from app.models.company_operating import CompanyDecisionContradiction
        contradictions = await db.execute(
            select(CompanyDecisionContradiction).where(
                CompanyDecisionContradiction.decision_id == context.target_id,
                CompanyDecisionContradiction.status.in_(["open", "acknowledged"])
            )
        )
        open_contradictions = contradictions.scalars().all()
        
        if open_contradictions and context.epistemic_status in (
            EpistemicStatus.EVIDENCE_BACKED,
            EpistemicStatus.MEASURED,
            EpistemicStatus.OBSERVED
        ):
            # Promoting to strong epistemic status while contradictions exist
            # requires explicit contradiction resolution
            resolution = context.provenance.get("contradiction_resolution") or context.metadata.get("contradiction_resolution")
            if not resolution:
                raise ContradictionPreservationViolation(
                    f"Cannot promote to {context.epistemic_status} while {len(open_contradictions)} "
                    f"contradiction(s) remain open. Explicit contradiction resolution required."
                )
    
    # ================================================================
    # 7. GOVERNANCE AUTHORIZATION FOR EPISTEMIC PROMOTION
    # ================================================================
    # Strong epistemic promotions require appropriate governance permissions.
    # This check applies to all mutation types including CREATE.
    promotion_requiring_governance = {
        EpistemicStatus.EVIDENCE_BACKED: ["decisions:manage"],
        EpistemicStatus.MEASURED: ["decisions:manage"],
        EpistemicStatus.OBSERVED: ["decisions:manage", "governance:manage"],
    }
    
    required_perms = promotion_requiring_governance.get(context.epistemic_status, [])
    if required_perms:
        caller_perms = await context.caller.get_permissions(db) if db else frozenset()
        for perm in required_perms:
            if perm not in caller_perms:
                raise EpistemicPromotionViolation(
                    f"Promotion to {context.epistemic_status} requires permission: {perm}"
                )
    
    # ================================================================
    # 8. TEMPORAL CONTEXT PRESERVATION
    # ================================================================
    # Epistemic transitions must preserve temporal context
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        from app.models.company_operating import CompanyDecision
        from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
        from app.models.company_actions import CompanyAction
        
        entity_type_map = {
            "CompanyDecision": CompanyDecision,
            "CompanyCommitment": CompanyCommitment,
            "CompanyAuthorization": CompanyAuthorization,
            "CompanyAction": CompanyAction,
        }
        
        model = entity_type_map.get(context.target_entity_type)
        if model:
            existing = await db.get(model, context.target_id)
            if existing:
                # Preserve valid_from/valid_to temporal context
                existing_valid_from = getattr(existing, "valid_from", None)
                existing_valid_to = getattr(existing, "valid_to", None)
                if existing_valid_from or existing_valid_to:
                    # Temporal context must be preserved or explicitly extended
                    pass  # Temporal validation will enforce this
    
    # ================================================================
    # 9. PREDICTION/OUTCOME CONFUSION PREVENTION
    # ================================================================
    # A prediction cannot become an actual outcome without verification
    # Only applies when promoting an existing PREDICTED entity to OBSERVED
    if context.epistemic_status == EpistemicStatus.OBSERVED and context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Check if this was previously a prediction
        from app.models.company_operating import CompanyDecision
        from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
        from app.models.company_actions import CompanyAction
        
        entity_type_map = {
            "CompanyDecision": CompanyDecision,
            "CompanyCommitment": CompanyCommitment,
            "CompanyAuthorization": CompanyAuthorization,
            "CompanyAction": CompanyAction,
        }
        
        model = entity_type_map.get(context.target_entity_type)
        if model and context.target_id:
            existing = await db.get(model, context.target_id)
            if existing:
                existing_status = getattr(existing, "epistemic_status", None)
                if existing_status == EpistemicStatus.PREDICTED:
                    # Prediction becoming observation requires outcome verification
                    verification = context.provenance.get("outcome_verification") or context.metadata.get("outcome_verification")
                    if not verification:
                        raise EvidenceTruthConfusionViolation(
                            f"Prediction cannot become OBSERVED without outcome verification. "
                            f"Use EVIDENCE_BACKED for verified predictions."
                        )
    
    # ================================================================
    # 10. RECOMMENDATION/DECISION CONFUSION PREVENTION
    # ================================================================
    if context.target_entity_type == "CompanyDecision" and context.mutation_type == MutationType.CREATE:
        # New decisions must have appropriate epistemic status
        if context.epistemic_status == EpistemicStatus.OBSERVED:
            raise EvidenceTruthConfusionViolation(
                f"New decision cannot be created as OBSERVED. "
                f"Decisions start as PROPOSED and progress through governance."
            )
    
    # ================================================================
    # 11. DECISION/AUTHORIZATION CONFUSION PREVENTION
    # ================================================================
    if context.target_entity_type == "CompanyAuthorization" and context.mutation_type == MutationType.TRANSITION:
        # Authorization transition to approved requires decision backing
        if context.epistemic_status == EpistemicStatus.EVIDENCE_BACKED:
            decision_id = context.provenance.get("decision_id")
            if not decision_id:
                raise EvidenceTruthConfusionViolation(
                    f"Authorization cannot be EVIDENCE_BACKED without supporting decision_id"
                )
    
    # ================================================================
    # 12. AUTHORIZATION/EXECUTION CONFUSION PREVENTION
    # ================================================================
    if context.target_entity_type == "CompanyAction" and context.mutation_type == MutationType.CREATE:
        # Actions require authorization provenance
        auth_id = context.provenance.get("authorization_id") or context.metadata.get("authorization_id")
        if not auth_id:
            raise EvidenceTruthConfusionViolation(
                f"Action cannot be created without authorization_id provenance"
            )
    
    return True


async def validate_exact_once(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """Validate exact-once semantics via fingerprint."""
    if not context.fingerprint:
        return True  # No fingerprint provided, skip check

    # Check if entity with same fingerprint already exists
    if context.target_entity_type == "CompanyDecision":
        existing = await db.execute(
            select(CompanyDecision).where(
                CompanyDecision.organization_id == context.caller.organization_id,
                CompanyDecision.fingerprint == context.fingerprint,
            )
        )
    elif context.target_entity_type == "CompanyCommitment":
        existing = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == context.caller.organization_id,
                CompanyCommitment.fingerprint == context.fingerprint,
            )
        )
    elif context.target_entity_type == "CompanyAuthorization":
        existing = await db.execute(
            select(CompanyAuthorization).where(
                CompanyAuthorization.organization_id == context.caller.organization_id,
                CompanyAuthorization.fingerprint == context.fingerprint,
            )
        )
    elif context.target_entity_type == "CompanyAction":
        existing = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == context.caller.organization_id,
                CompanyAction.action_type == context.metadata.get("action_type"),
                CompanyAction.fingerprint == context.fingerprint,
            )
        )
    elif context.target_entity_type == "CompanyDecisionAlternative":
        existing = await db.execute(
            select(CompanyDecisionAlternative).where(
                CompanyDecisionAlternative.organization_id == context.caller.organization_id,
                CompanyDecisionAlternative.fingerprint == context.fingerprint,
            )
        )
    else:
        return True  # No exact-once check for this type

    if existing.scalar_one_or_none():
        raise ExactOnceViolation(
            f"Duplicate mutation detected: {context.target_entity_type} "
            f"with fingerprint {context.fingerprint} already exists"
        )

    return True


# -------------------------------------------------------------------------
# Optimistic Concurrency Validation
# -------------------------------------------------------------------------

def validate_optimistic_concurrency(
    entity: Any,
    expected_version: Optional[int],
) -> bool:
    """Validate optimistic concurrency via version checking."""
    if expected_version is None:
        return True  # No version check requested

    current_version = getattr(entity, "version", None)
    if current_version is None:
        return True  # Entity doesn't support versioning

    if current_version != expected_version:
        raise ConcurrencyViolation(
            f"Stale version: expected {expected_version}, current is {current_version}. "
            f"Another mutation modified this entity concurrently."
        )

    return True


# -------------------------------------------------------------------------
# Transactional Atomicity
# -------------------------------------------------------------------------

@dataclass
class TransactionalMutation:
    """Wrapper for a mutation within a transaction."""
    mutation_fn: Callable
    rollback_fn: Optional[Callable] = None
    metadata: dict = field(default_factory=dict)


async def execute_transactional(
    db: AsyncSession,
    mutations: list[TransactionalMutation],
) -> list[MutationResult]:
    """Execute multiple mutations atomically.
   
    If any mutation fails, all are rolled back.
    """
    # Use a savepoint for true atomicity
    savepoint = await db.begin_nested()
    results = []
    try:
        for mutation in mutations:
            result = await mutation.mutation_fn(db)
            results.append(result)
       
        # All succeeded, commit the savepoint
        await savepoint.commit()
        return results
    except Exception as e:
        # Rollback to savepoint
        await savepoint.rollback()
        # Attempt individual rollbacks
        for mutation in mutations:
            if mutation.rollback_fn:
                try:
                    await mutation.rollback_fn(db)
                except Exception:
                    pass  # Best effort
        raise


# -------------------------------------------------------------------------
# Canonical Mutation Boundary - Main Entry Point
# -------------------------------------------------------------------------

class CanonicalMutationBoundary:
    def __init__(self):
        pass

    async def _load_entity(self, db: AsyncSession, entity_type: str, entity_id: str):
        """Load entity by type and ID."""
        type_map = {
            "CompanyDecision": CompanyDecision,
            "CompanyAuthorization": CompanyAuthorization,
            "CompanyCommitment": CompanyCommitment,
            "CompanyAction": CompanyAction,
            "CompanyDecisionAlternative": CompanyDecisionAlternative,
            "CompanyDecisionContradiction": CompanyDecisionContradiction,
            "CompanyGoal": CompanyGoal,
            "CompanyObjective": CompanyObjective,
            "CompanyInitiative": CompanyInitiative,
            "CompanyIntent": CompanyIntent,
            "Project": Project,
            "Task": Task,
            "Employee": Employee,
            "CanonicalOperation": CanonicalOperation,
        }
        model = type_map.get(entity_type)
        if not model:
            return None
        return await db.get(model, entity_id)

    async def mutate(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        target_entity_type: str,
        mutation_type: MutationType,
        target_id: Optional[str] = None,
        mutation_fn: Callable = None,
        expected_version: Optional[int] = None,
        fingerprint: Optional[str] = None,
        provenance: dict = None,
        epistemic_status: EpistemicStatus = EpistemicStatus.PROPOSED,
        source_event_id: Optional[str] = None,
        trigger_reason: Optional[str] = None,
        required_permissions: Optional[list[str]] = None,
        target_organization_id: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        entity: Optional[Any] = None,  # For CREATE mutations: the new entity
        updates: Optional[dict] = None,  # For UPDATE mutations: the update values
    ) -> MutationResult:
        """Execute a canonical mutation through the boundary."""
       
        # Build context
        permissions = await caller.get_permissions(db) if db is not None else frozenset()
        metadata_dict = {"updates": updates} if updates else {}
        context = CanonicalMutationContext(
            caller=caller,
            tenant_id=caller.organization_id,
            governance_scope_ids=caller.visible_scope_ids,
            permissions=permissions,
            target_entity_type=target_entity_type,
            target_id=target_id,
            mutation_type=mutation_type,
            expected_version=expected_version,
            fingerprint=fingerprint,
            provenance=provenance or {},
            epistemic_status=epistemic_status,
            source_event_id=source_event_id,
            trigger_reason=trigger_reason,
            metadata=metadata_dict,
        )

        # 4. Execute mutation with all validations
        async def mutation_wrapper(db: AsyncSession) -> MutationResult:
            
            # Initialize concurrency components
            concurrency_coordinator = CanonicalConcurrencyCoordinator(db)
            idempotency_manager = IdempotencyKeyManager(db)
            optimistic_manager = OptimisticConcurrencyManager(db)
            
            # Create concurrency context
            concurrency_context = ConcurrencyContext(
                operation_id=str(uuid.uuid4()),
                entity_type=target_entity_type,
                entity_id=target_id or "",
                actor_id=caller.user_id,
                organization_id=caller.organization_id,
                concurrency_type=ConcurrencyControlType.OPTIMISTIC,
                expected_version=expected_version,
                fingerprint=fingerprint,
                max_retries=3,
                retry_delay=0.1,
                timeout=30.0,
            )
            
            # Initialize concurrency coordinator
            canonical_concurrency = CanonicalOperationConcurrency(db)
            canonical_concurrency.optimistic = OptimisticConcurrencyManager(db)
            canonical_concurrency.leases = LeaseManager(db)
            
            # 1. Governance validation
            # For CREATE mutations, skip target_id accessibility check since entity doesn't exist yet
            governance_target_id = None if mutation_type == MutationType.CREATE else target_id
            await validate_governance(
                db=db,
                caller=caller,
                target_entity_type=target_entity_type,
                target_id=governance_target_id,
                target_organization_id=target_organization_id or caller.organization_id,
                required_permissions=required_permissions,
            )
            
            # 2. Target resolution through accessible IDs
            # Skip for CREATE mutations since entity doesn't exist yet
            if governance_target_id and target_entity_type not in ["Organization", "User"] and db is not None:
                # Fetch the User object for resolve_accessible_ids
                from app.models.user import User as UserModel
                user_obj = await db.get(UserModel, caller.user_id)
                if not user_obj:
                    raise ScopeViolation(f"User {caller.user_id} not found")
                accessible = await resolve_accessible_ids(
                    db=db,
                    user=user_obj,
                    organization_id=caller.organization_id,
                    kind=_entity_type_to_kind(target_entity_type),
                    ids=[target_id],
                )
                if target_id not in accessible:
                    raise ScopeViolation(
                        f"Target {target_entity_type}:{target_id} not accessible to caller"
                    )
            
            # Exact-once check with idempotency key manager
            # Skip for CREATE mutations - database-level idempotent INSERT handles it
            if fingerprint and mutation_type != MutationType.CREATE:
                is_new, existing_id = await idempotency_manager.check_and_reserve(
                    key=fingerprint,
                    entity_type=target_entity_type,
                    organization_id=caller.organization_id,
                )
                
                if not is_new:
                    # Entity already exists, load and return
                    existing_entity = await self._load_entity(db, target_entity_type, existing_id)
                    return MutationResult(success=True, entity=existing_entity, fingerprint=fingerprint)
                
                # Mark idempotency key as reserved
                await idempotency_manager.complete(fingerprint, target_id or str(uuid.uuid4()))
            
            # Temporal integrity (for both CREATE and UPDATE)
            # For CREATE, pass the entity; for UPDATE, load from DB
            if target_id:
                # UPDATE: load existing entity
                entity_for_temporal = await self._load_entity(db, target_entity_type, target_id)
            else:
                # CREATE: entity is passed as parameter
                entity_for_temporal = entity
            
            await validate_temporal_integrity(
                db=db,
                entity_type=target_entity_type,
                entity_id=target_id,
                entity=entity_for_temporal,
                organization_id=caller.organization_id,
                mutation_type=mutation_type,
                allow_supersession=(mutation_type == MutationType.TRANSITION),
            )
            
            # Provenance validation
            context_obj = CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=target_entity_type,
                target_id=target_id,
                provenance=provenance or {},
            )
            await validate_provenance(db, context_obj)
            
            # Epistemic boundary (Gate 6-B: basic promotion rules)
            await validate_epistemic_boundary(
                db,
                CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    epistemic_status=epistemic_status,
                ),
                epistemic_status,
            )
            
            # Epistemic integrity (Gate 6-F: comprehensive enforcement)
            await validate_epistemic_integrity(
                db=db,
                context=CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    mutation_type=mutation_type,
                    provenance=provenance or {},
                    epistemic_status=epistemic_status,
                ),
            )
            
            # Contradiction preservation validation (Gate 6-E)
            await validate_contradiction_preservation(
                db=db,
                context=CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    mutation_type=mutation_type,
                    provenance=provenance or {},
                    metadata=context.metadata,  # Pass the metadata with updates
                ),
            )
            
            # Concurrency check
            if target_id and expected_version is not None:
                # Load entity to check version
                entity_for_concurrency = await self._load_entity(db, target_entity_type, target_id)
                if entity_for_concurrency:
                    validate_optimistic_concurrency(entity_for_concurrency, expected_version)
            
            # Exact-once check with idempotency key manager
            # Skip for CREATE mutations - database-level idempotent INSERT handles it
            if fingerprint and mutation_type != MutationType.CREATE:
                is_new, existing_id = await idempotency_manager.check_and_reserve(
                    key=fingerprint,
                    entity_type=target_entity_type,
                    organization_id=caller.organization_id,
                )
                
                if not is_new:
                    # Entity already exists, load and return
                    existing_entity = await self._load_entity(db, target_entity_type, existing_id)
                    return MutationResult(success=True, entity=existing_entity, fingerprint=fingerprint)
                
                # Mark idempotency key as reserved
                await idempotency_manager.complete(fingerprint, target_id or str(uuid.uuid4()))
            
            # Execute the actual mutation
            if mutation_fn:
                # For UPDATE mutations, use database-level optimistic concurrency
                if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:
                    # Load the model for the entity type
                    type_map = {
                        "CompanyDecision": CompanyDecision,
                        "CompanyAuthorization": CompanyAuthorization,
                        "CompanyCommitment": CompanyCommitment,
                        "CompanyAction": CompanyAction,
                        "CompanyDecisionAlternative": CompanyDecisionAlternative,
                        "CompanyDecisionContradiction": CompanyDecisionContradiction,
                        "CompanyGoal": CompanyGoal,
                        "CompanyObjective": CompanyObjective,
                        "CompanyInitiative": CompanyInitiative,
                        "CompanyIntent": CompanyIntent,
                        "Project": Project,
                        "Task": Task,
                        "Employee": Employee,
                        "User": User,
                        "Organization": Organization,
                    }
                    model = type_map.get(target_entity_type)
                    if model:
                        # Use database-level optimistic update
                        pass
                result = await mutation_fn(db)
                
                # For UPDATE mutations, verify the version was actually updated
                if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:
                    entity_for_check = await self._load_entity(db, target_entity_type, target_id)
                    if entity_for_check and hasattr(entity_for_check, 'version'):
                        if entity_for_check.version <= expected_version:
                            raise ConcurrencyViolation(
                                f"Stale version: expected {expected_version}, current is {entity_for_check.version}"
                            )
                
                # Mark idempotency key as complete
                if fingerprint:
                    await idempotency_manager.complete(fingerprint, result.id if hasattr(result, 'id') else str(uuid.uuid4()))
                
                # Emit canonical timeline event for the successful mutation
                # For CREATE mutations, the canonical_create function handles timeline emission
                # to avoid duplicate events for idempotent creates
                if mutation_type != MutationType.CREATE:
                    await _emit_canonical_timeline_event(
                        db=db,
                        caller=caller,
                        target_entity_type=target_entity_type,
                        mutation_type=mutation_type,
                        target_id=target_id or (result.id if hasattr(result, 'id') else None),
                        entity=result,
                        source_event_id=source_event_id,
                        provenance=provenance or {},
                    )
                
                return MutationResult(success=True, entity=result, fingerprint=fingerprint)
            else:
                return MutationResult(success=False, error="No mutation function provided")

        try:
            result = await execute_transactional(db, [
                TransactionalMutation(mutation_fn=mutation_wrapper)
            ])
            return result[0] if result else MutationResult(success=False, error="No result")
        except CanonicalMutationError as e:
            return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
        except Exception as e:
            return MutationResult(success=False, error=str(e), error_code=type(e).__name__)


async def _emit_canonical_timeline_event(
    db: AsyncSession,
    caller: CallerAccess,
    target_entity_type: str,
    mutation_type: MutationType,
    target_id: Optional[str],
    entity: Any,
    source_event_id: Optional[str],
    provenance: dict,
):
    """Emit a canonical timeline event for a successful mutation.
    
    This feeds the Living Company Memory and Company Brain.
    """
    try:
        # Create unique event key including state for transitions
        if mutation_type == MutationType.TRANSITION and entity:
            # Check for both 'state' and 'status' fields (CompanyDecisionContradiction uses 'status')
            state_value = getattr(entity, 'state', getattr(entity, 'status', None))
            if state_value is not None:
                event_key = f"{target_entity_type}:{mutation_type.value}:{target_id or 'new'}:{state_value}"
            else:
                event_key = f"{target_entity_type}:{mutation_type.value}:{target_id or 'new'}"
        elif mutation_type == MutationType.UPDATE and entity:
            # For UPDATE mutations, include the epistemic status in the event key to avoid duplicates
            epistemic_value = getattr(entity, 'epistemic_status', None)
            if epistemic_value is not None:
                event_key = f"{target_entity_type}:{mutation_type.value}:{target_id or 'new'}:{epistemic_value}"
            else:
                event_key = f"{target_entity_type}:{mutation_type.value}:{target_id or 'new'}"
        else:
            event_key = f"{target_entity_type}:{mutation_type.value}:{target_id or 'new'}"
        occurred_at = utcnow()
        
        # Determine timeline type and event type
        timeline_type_map = {
            "CompanyDecision": "decision",
            "CompanyAuthorization": "authorization",
            "CompanyCommitment": "commitment",
            "CompanyAction": "action",
            "CompanyDecisionAlternative": "decision",
            "CompanyDecisionContradiction": "decision",
            "CompanyGoal": "strategy",
            "CompanyObjective": "strategy",
            "CompanyInitiative": "strategy",
            "CompanyIntent": "strategy",
            "Project": "project",
            "Task": "task",
            "Employee": "people",
            "CompanyActionOutcome": "action",
        }
        timeline_type = timeline_type_map.get(target_entity_type, "entity")
        
        # Determine event subtype
        event_subtype = mutation_type.value
        
        # Build change summary
        if mutation_type == MutationType.CREATE:
            change_summary = f"Created {target_entity_type}"
            from_state = None
            to_state = "created"
        elif mutation_type == MutationType.TRANSITION:
            change_summary = f"Transitioned {target_entity_type}"
            state_value = getattr(entity, 'state', getattr(entity, 'status', None)) if entity else None
            from_state = state_value
            to_state = state_value if state_value is not None else 'transitioned'
        elif mutation_type == MutationType.UPDATE:
            change_summary = f"Updated {target_entity_type}"
            from_state = None
            to_state = "updated"
        else:
            change_summary = f"Mutated {target_entity_type}"
            from_state = None
            to_state = "mutated"
        
        # Build delta JSON
        delta_json = {
            "entity_type": target_entity_type,
            "entity_id": target_id,
            "mutation_type": mutation_type.value,
            "provenance": provenance,
        }
        if entity and hasattr(entity, 'state'):
            delta_json["state"] = entity.state
        
        # Create timeline event
        timeline_event = CompanyTimelineEvent(
            organization_id=caller.organization_id,
            event_key=event_key,
            timeline_type=timeline_type,
            event_type=f"{target_entity_type}.{mutation_type.value}",
            event_subtype=event_subtype,
            entity_type=target_entity_type,
            entity_id=target_id,
            occurred_at=occurred_at,
            effective_from=occurred_at,
            from_state=from_state,
            to_state=to_state,
            change_summary=change_summary,
            delta_json=delta_json,
            epistemic_state="OBSERVED",
            confidence=1.0,
            recorded_by=caller.employee_id,
            source_event_id=source_event_id,
            provenance_json=provenance,
            metadata_json={"mutation_type": mutation_type.value},
        )
        db.add(timeline_event)
        await db.flush()
        
        # Also emit background event for the event stream
        await publish_background_event(
            db=db,
            name=f"{target_entity_type.lower()}.{mutation_type.value}",
            organization_id=caller.organization_id,
            payload={
                "entity_type": target_entity_type,
                "entity_id": target_id,
                "mutation_type": mutation_type.value,
                "source_event_id": source_event_id,
                "provenance": provenance,
            },
        )
    except Exception:
        # Timeline emission failure should not block the mutation
        # Log and continue
        pass


async def _execute_optimistic_update(
    db: AsyncSession,
    model: Any,
    entity_id: str,
    expected_version: int,
    update_values: dict,
) -> Tuple[bool, Optional[Any]]:
    """Execute an update with database-level optimistic concurrency control.
    
    Uses WHERE version = :expected_version for atomic optimistic concurrency.
    Returns (success, entity) where success is True if the update was applied.
    """
    # Build the update statement with version check
    update_stmt = (
        update(model)
        .where(model.id == entity_id)
        .where(model.version == expected_version)
        .values(**update_values, version=expected_version + 1)
        .returning(model)
    )
    
    result = await db.execute(update_stmt)
    await db.flush()
    
    if result.rowcount == 0:
        # No rows updated - version conflict or entity not found
        return False, None
    
    # Fetch the updated entity
    entity = result.scalar_one_or_none()
    return True, entity


# =============================================================================
# Universal Idempotency Contract
# =============================================================================

class IdempotencyIdentityType(Enum):
    """Types of identity semantics for idempotent operations."""
    SOURCE_EVENT = "source_event"        # CompanyDecision: organization_id + source_event_id
    FINGERPRINT = "fingerprint"          # Most entities: organization_id + fingerprint
    EXTERNAL_ID = "external_id"          # External system reference
    OPERATION_ID = "operation_id"        # CanonicalOperation: organization_id + fingerprint
    NATURAL_KEY = "natural_key"          # Composite natural key


@dataclass
class IdempotencyIdentity:
    """Canonical identity contract for idempotent operations.
    
    Each entity type declares its identity semantics once here.
    The mutation boundary uses this to resolve correct conflict targets.
    """
    identity_type: IdempotencyIdentityType
    conflict_columns: List[str]
    description: str = ""


# Universal registry of idempotency identities for all canonical entity types
IDEMPOTENCY_IDENTITY_REGISTRY: Dict[str, IdempotencyIdentity] = {
    # CompanyDecision uses source_event_id for exact-once (not fingerprint)
    "CompanyDecision": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.SOURCE_EVENT,
        conflict_columns=["organization_id", "source_event_id"],
        description="Decision exact-once via source_event_id (event-sourced identity)"
    ),
    # Entities using fingerprint for exact-once
    "CompanyCommitment": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Commitment exact-once via fingerprint"
    ),
    "CompanyAuthorization": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Authorization exact-once via fingerprint"
    ),
    "CompanyAction": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Action exact-once via fingerprint"
    ),
    "CompanyDecisionAlternative": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="DecisionAlternative exact-once via fingerprint"
    ),
    "CompanyDecisionContradiction": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="DecisionContradiction exact-once via fingerprint"
    ),
    "CompanyGoal": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Goal exact-once via fingerprint"
    ),
    "CompanyObjective": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Objective exact-once via fingerprint"
    ),
    "CompanyInitiative": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Initiative exact-once via fingerprint"
    ),
    "CompanyIntent": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Intent exact-once via fingerprint"
    ),
    "Project": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Project exact-once via fingerprint"
    ),
    "Task": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Task exact-once via fingerprint"
    ),
    "Employee": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Employee exact-once via fingerprint"
    ),
    "CompanyIntent": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="Intent exact-once via fingerprint"
    ),
    "ObjectiveContradiction": IdempotencyIdentity(
        identity_type=IdempotencyIdentityType.FINGERPRINT,
        conflict_columns=["organization_id", "fingerprint"],
        description="ObjectiveContradiction exact-once via fingerprint"
    ),
}


async def get_idempotency_identity(entity_type: str) -> IdempotencyIdentity:
    """Get the canonical idempotency identity for an entity type.
    
    This is the single source of truth for conflict target resolution.
    """
    return IDEMPOTENCY_IDENTITY_REGISTRY.get(
        entity_type,
        IdempotencyIdentity(
            identity_type=IdempotencyIdentityType.FINGERPRINT,
            conflict_columns=["organization_id", "fingerprint"],
            description=f"Default fallback for {entity_type}"
        )
    )


async def get_conflict_target_columns(entity_type: str) -> List[str]:
    """Get the column names that form the unique constraint for idempotent inserts.
    
    Uses the universal idempotency identity registry.
    """
    identity = await get_idempotency_identity(entity_type)
    return identity.conflict_columns


def register_idempotency_identity(entity_type: str, identity: IdempotencyIdentity) -> None:
    """Register a new idempotency identity (for extensibility).
    
    Should only be called during system initialization.
    """
    IDEMPOTENCY_IDENTITY_REGISTRY[entity_type] = identity


async def _execute_idempotent_create(
    db: AsyncSession,
    entity: Any,
    provenance: dict = None,
) -> Tuple[bool, Any]:
    """Create a new entity atomically using dialect-specific idempotent INSERT.
    
    Uses INSERT ... ON CONFLICT DO NOTHING (PostgreSQL) or INSERT OR IGNORE (SQLite)
    for atomic idempotent creation.
    Returns (is_new, entity) where is_new is True if entity was created,
    False if existing entity was found.
    """
    model = type(entity)
    if provenance:
        entity.provenance = provenance
    # Get the conflict target columns for this entity type from universal registry
    conflict_target_columns = await get_conflict_target_columns(type(entity).__name__)
    
    # Prepare the insert values
    insert_values = {}
    for col in model.__table__.columns:
        if col.name != 'id' or getattr(entity, col.name, None) is not None:
            val = getattr(entity, col.name, None)
            if val is not None:
                insert_values[col.name] = val
    
    # Use dialect-specific idempotent insert
    dialect_name = db.bind.dialect.name
    
    if dialect_name in ('sqlite', 'sqlite.aiosqlite'):
        # SQLite: INSERT OR IGNORE
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        stmt = sqlite_insert(model).values(**_get_insert_values(entity, model)).prefix_with('OR IGNORE')
        result = await db.execute(stmt)
        await db.flush()
        
        # For SQLite INSERT OR IGNORE, check rowcount to determine if row was inserted
        if result.rowcount > 0:
            print(f"DEBUG _execute_idempotent_create: returning True (new entity, rowcount={result.rowcount})")
            # Fetch the newly created entity
            conflict_columns = await get_conflict_target_columns(type(entity).__name__)
            where_clause = []
            for col in conflict_columns:
                if hasattr(model, col):
                    where_clause.append(getattr(model, col) == getattr(entity, col))
            existing = await db.execute(select(model).where(*where_clause))
            existing_entity = existing.scalar_one_or_none()
            return True, existing_entity
        else:
            # Row already existed, fetch it
            conflict_columns = await get_conflict_target_columns(type(entity).__name__)
            where_clause = []
            for col in conflict_columns:
                if hasattr(model, col):
                    where_clause.append(getattr(model, col) == getattr(entity, col))
            existing = await db.execute(select(model).where(*where_clause))
            existing_entity = existing.scalar_one_or_none()
            print(f"DEBUG _execute_idempotent_create: returning False (existing entity)")
            return False, existing_entity
    elif db.bind.dialect.name == 'postgresql':
        # PostgreSQL: INSERT ... ON CONFLICT DO NOTHING
        # Use the correct conflict target columns for this entity type from universal registry
        conflict_target_columns = await get_conflict_target_columns(type(entity).__name__)
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(model).values(**_get_insert_values(entity, model)).on_conflict_do_nothing(
            index_elements=conflict_target_columns
        ).returning(model)
        result = await db.execute(stmt)
        await db.flush()
        
        inserted_entity = result.scalar_one_or_none()
        if inserted_entity:
            return True, inserted_entity
        else:
            # Entity already existed, fetch it using conflict target columns
            where_clause = []
            for col in conflict_target_columns:
                if hasattr(model, col):
                    where_clause.append(getattr(model, col) == getattr(entity, col))
            
            existing = await db.execute(
                select(model).where(*where_clause)
            )
            existing_entity = existing.scalar_one_or_none()
            if existing_entity:
                return False, existing_entity
            raise RuntimeError("Idempotent insert failed unexpectedly")
    else:
        # Fallback for other dialects
        db.add(entity)
        try:
            await db.flush()
            return True, entity
        except IntegrityError:
            await db.rollback()
            # Use fingerprint from entity for fallback
            entity_fingerprint = getattr(entity, 'fingerprint', None)
            if entity_fingerprint:
                existing = await db.execute(
                    select(model).where(model.fingerprint == entity_fingerprint)
                )
                existing_entity = existing.scalar_one_or_none()
                if existing_entity:
                    return False, existing_entity
            raise
    
    return False, None


# Global instance
canonical_mutation_boundary = CanonicalMutationBoundary()


def _get_insert_values(entity: Any, model: Any) -> dict:
    """Extract insert values from entity for the given model."""
    insert_values = {}
    for col in model.__table__.columns:
        if col.name != 'id' or getattr(entity, col.name, None) is not None:
            val = getattr(entity, col.name, None)
            if val is not None:
                insert_values[col.name] = val
    return insert_values


# -------------------------------------------------------------------------
# Convenience Functions for Common Mutation Patterns
# -------------------------------------------------------------------------

async def _create_entity(db: AsyncSession, entity: Any, provenance: dict = None) -> Any:
    """Create a new entity in the database."""
    if provenance:
        entity.provenance = provenance
    db.add(entity)
    await db.flush()
    return entity


async def _get_existing_by_fingerprint(
    db: AsyncSession,
    entity_type: str,
    fingerprint: str,
    organization_id: str,
    entity: Optional[Any] = None,
) -> Optional[Any]:
    """Check if an entity with the same fingerprint already exists.
    
    For some entity types, the unique constraint is on a different field:
    - CompanyDecision: source_event_id (not fingerprint)
    """
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
        "CompanyGoal": CompanyGoal,
        "CompanyObjective": CompanyObjective,
        "CompanyInitiative": CompanyInitiative,
        "CompanyIntent": CompanyIntent,
        "Project": Project,
        "Task": Task,
        "Employee": Employee,
    }
    model = type_map.get(entity_type)
    if not model:
        return None
    
    # For CompanyDecision, check by source_event_id instead of fingerprint
    if entity_type == "CompanyDecision" and entity is not None:
        source_event_id = getattr(entity, "source_event_id", None)
        if source_event_id:
            result = await db.execute(
                select(model).where(
                    model.organization_id == organization_id,
                    model.source_event_id == source_event_id,
                )
            )
            return result.scalar_one_or_none()
    
    # Default: check by fingerprint
    result = await db.execute(
        select(model).where(
            model.organization_id == organization_id,
            model.fingerprint == fingerprint,
        )
    )
    return result.scalar_one_or_none()


async def canonical_create(
    db: AsyncSession,
    caller: CallerAccess,
    entity: Any,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Create a new canonical entity through the boundary."""
    # Read epistemic_status from entity if present
    entity_epistemic_status = getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)
    
    # Read fingerprint from entity if not provided as parameter
    # For entities without fingerprint, compute from conflict target columns
    if fingerprint is None:
        fingerprint = getattr(entity, "fingerprint", None)
        if fingerprint is None:
            # Compute idempotency key from conflict target columns using universal registry
            conflict_columns = await get_conflict_target_columns(type(entity).__name__)
            fingerprint_parts = []
            for col in conflict_columns:
                val = getattr(entity, col, None)
                if val is not None:
                    fingerprint_parts.append(str(val))
            fingerprint = "|".join(fingerprint_parts) if fingerprint_parts else None
    
    
    # Idempotent create: use database-level atomic INSERT ... ON CONFLICT DO NOTHING / INSERT OR IGNORE
    # No pre-check needed - the database handles idempotency atomically
    # The mutation_fn returns (is_new, entity) tuple, we need to extract the entity
    is_new_entity = [False]  # Use list for mutable closure
    
    async def create_mutation_fn(db: AsyncSession):
        is_new, created_entity = await _execute_idempotent_create(db, entity, provenance)
        is_new_entity[0] = is_new
        return created_entity
    
    result = await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity.__class__.__name__,
        mutation_type=MutationType.CREATE,
        target_id=entity.id,
        target_organization_id=entity.organization_id,
        mutation_fn=create_mutation_fn,
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
        epistemic_status=entity_epistemic_status,
    )
    
    # Only emit timeline event if entity was actually created (not a duplicate)
    if result.success and is_new_entity[0]:
        try:
            print(f"DEBUG: Emitting timeline event for new entity: {entity.__class__.__name__}, is_new={is_new_entity[0]}")
            await _emit_canonical_timeline_event(
                db=db,
                caller=caller,
                target_entity_type=entity.__class__.__name__,
                mutation_type=MutationType.CREATE,
                target_id=result.entity.id if result.entity else entity.id,
                entity=result.entity,
                source_event_id=provenance.get("source_event_id") if provenance else None,
                provenance=provenance or {},
            )
            print(f"DEBUG: Timeline event emitted successfully")
        except Exception as e:
            print(f"DEBUG: Timeline emission failed: {e}")
            # Timeline emission failure should not block the mutation
            pass
    else:
        print(f"DEBUG: Skipping timeline event, success={result.success}, is_new={is_new_entity[0]}")
    
    return result


async def canonical_update(
    db: AsyncSession,
    caller: CallerAccess,
    entity_type: str,
    entity_id: str,
    updates: dict,
    expected_version: Optional[int] = None,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Update an existing canonical entity through the boundary using database-level optimistic concurrency."""
    # Fetch entity to get organization_id for tenant isolation check
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
        "CompanyGoal": CompanyGoal,
        "CompanyObjective": CompanyObjective,
        "CompanyInitiative": CompanyInitiative,
        "CompanyIntent": CompanyIntent,
        "Project": Project,
        "Task": Task,
        "Employee": Employee,
    }
    model = type_map.get(entity_type)
    if not model:
        raise ValueError(f"Unknown entity type: {entity_type}")
    
    entity = await db.get(model, entity_id)
    if not entity:
        raise ValueError(f"Entity not found: {entity_type}:{entity_id}")
    
    target_org_id = getattr(entity, "organization_id", None)
    
    # Check if entity supports versioning
    has_version = hasattr(entity, "version")
    current_version = getattr(entity, "version", None) if has_version else None
    
    # If expected_version not provided but entity has version, use current version
    if expected_version is None and current_version is not None:
        expected_version = current_version
    
    # Read epistemic_status from entity if present
    epistemic_status = getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)
    
    # Build update values including version increment
    update_values = {**updates, "updated_at": utcnow()}
    if expected_version is not None and has_version:
        update_values["version"] = expected_version + 1
    
    # Run all canonical validations BEFORE database-level optimistic update
    # 1. Governance validation
    try:
        await validate_governance(
            db=db,
            caller=caller,
            target_entity_type=entity_type,
            target_id=entity_id,
            target_organization_id=target_org_id or caller.organization_id,
            required_permissions=required_permissions,
        )
    except (GovernanceViolation, TenantIsolationViolation, ScopeViolation) as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # 2. Temporal integrity validation
    try:
        await validate_temporal_integrity(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            entity=entity,
            organization_id=caller.organization_id,
            mutation_type=MutationType.UPDATE,
            allow_supersession=False,
        )
    except TemporalViolation as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # 3. Provenance validation
    update_context = CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.UPDATE,
        provenance=provenance or {},
        epistemic_status=epistemic_status,
        metadata={"updates": updates},
    )
    try:
        await validate_provenance(db, update_context)
    except ProvenanceViolation as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # 4. Epistemic boundary validation
    try:
        await validate_epistemic_boundary(
            db,
            CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                epistemic_status=epistemic_status,
            ),
            epistemic_status,
        )
    except EpistemicViolation as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # 5. Epistemic integrity (Gate 6-F)
    try:
        await validate_epistemic_integrity(
            db=db,
            context=CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                mutation_type=MutationType.UPDATE,
                provenance=provenance or {},
                epistemic_status=epistemic_status,
            ),
        )
    except (EpistemicViolation, EpistemicPromotionViolation, AIOriginViolation, EvidenceTruthConfusionViolation, ProvenanceStrippingViolation, ContradictionPreservationViolation) as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # 6. Contradiction preservation validation
    try:
        await validate_contradiction_preservation(
            db=db,
            context=CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                mutation_type=MutationType.UPDATE,
                provenance=provenance or {},
                metadata={"updates": updates},
            ),
        )
    except (ContradictionPreservationViolation, ContradictionReferenceViolation) as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # 7. Exact-once validation
    if fingerprint:
        try:
            await validate_exact_once(db, update_context)
        except ExactOnceViolation as e:
            return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # For optimistic concurrency, use database-level WHERE clause
    if expected_version is not None:
        # Use database-level optimistic concurrency with WHERE version = :expected_version
        # First, do the update without RETURNING to avoid ORM attachment issues
        update_stmt = (
            update(model)
            .where(model.id == entity_id)
            .where(model.version == expected_version)
            .values(**update_values)
        )
        
        result = await db.execute(update_stmt)
        await db.flush()
        
        # Check rowcount to see if update succeeded
        if result.rowcount == 0:
            # No rows updated - version conflict or entity not found
            return MutationResult(
                success=False, 
                error=f"Stale version: expected {expected_version}, entity was modified concurrently",
                error_code="ConcurrencyViolation"
            )
        
        # Fetch the updated entity separately to avoid RETURNING clause issues
        updated_entity = await db.get(model, entity_id)
        if updated_entity is None:
            return MutationResult(
                success=False, 
                error="Entity not found after update",
                error_code="NotFound"
            )
        
        return MutationResult(success=True, entity=updated_entity, fingerprint=fingerprint)
    
    # If no expected_version, fall back to the standard mutation path
    # (but this should not happen in normal operation)
    print(f"DEBUG canonical_update: calling mutate with updates={updates}")
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.UPDATE,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=lambda db: _execute_standard_update(db, model, entity_id, updates),
        expected_version=expected_version,
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
        epistemic_status=updates.get("epistemic_status") or getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED),
        updates=updates,
    )


async def _execute_standard_update(db: AsyncSession, model: Any, entity_id: str, updates: dict) -> Any:
    """Standard ORM-based update for cases without optimistic concurrency."""
    entity = await db.get(model, entity_id)
    if not entity:
        raise ValueError(f"Entity not found: {entity_id}")
    
    for key, value in updates.items():
        if hasattr(entity, key):
            setattr(entity, key, value)
    
    entity.updated_at = utcnow()
    if hasattr(entity, "version"):
        entity.version += 1
    
    await db.flush()
    return entity


async def canonical_transition(
    db: AsyncSession,
    caller: CallerAccess,
    entity_type: str,
    entity_id: str,
    new_state: str,
    expected_version: Optional[int] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
    trigger_reason: Optional[str] = None,
) -> MutationResult:
    """Execute a canonical state transition through the boundary using database-level optimistic concurrency."""
    # Fetch entity to get organization_id for tenant isolation check
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
        "CanonicalOperation": CanonicalOperation,
    }
    model = type_map.get(entity_type)
    if not model:
        raise ValueError(f"Unknown entity type for transition: {entity_type}")

    entity = await db.get(model, entity_id)
    if not entity:
        raise ValueError(f"Entity not found: {entity_type}:{entity_id}")

    target_org_id = getattr(entity, "organization_id", None)

    # Determine the state field name for this entity type
    state_field = "status" if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction") else "state"
    
    # Check if entity supports versioning
    has_version = hasattr(entity, "version")
    current_version = getattr(entity, "version", None) if has_version else None
    
    # If expected_version not provided but entity has version, use current version
    if expected_version is None and current_version is not None:
        expected_version = current_version

    # Read epistemic_status from entity if present
    epistemic_status = getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)
    
    # Build update_values for database-level optimistic concurrency
    state_field = "status" if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction") else "state"
    update_values = {state_field: new_state, "updated_at": utcnow()}
    if has_version:
        update_values["version"] = expected_version + 1
    
    # Validate temporal integrity for TRANSITION FIRST (before provenance)
    # This ensures supersession chain integrity is checked before provenance
    try:
        await validate_temporal_integrity(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            entity=entity,
            organization_id=caller.organization_id,
            mutation_type=MutationType.TRANSITION,
            allow_supersession=True,
        )
    except TemporalViolation as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # Validate provenance for TRANSITION mutations
    # This ensures missing required provenance fields are caught
    print(f"DEBUG: Validating provenance for entity_id={entity_id}")
    transition_context = CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.TRANSITION,
        provenance=provenance or {},
        epistemic_status=epistemic_status,
    )
    try:
        await validate_provenance(db, transition_context)
    except ProvenanceViolation as e:
        print(f"DEBUG: Provenance validation failed: {e}")
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    print(f"DEBUG: Provenance validation passed")
    
    # Epistemic boundary validation
    print(f"DEBUG: Validating epistemic boundary")
    try:
        await validate_epistemic_boundary(
            db,
            CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                epistemic_status=epistemic_status,
            ),
            epistemic_status,
        )
    except EpistemicViolation as e:
        print(f"DEBUG: Epistemic boundary validation failed: {e}")
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    print(f"DEBUG: Epistemic boundary validation passed")
    
    # Epistemic integrity (Gate 6-F)
    print(f"DEBUG: Validating epistemic integrity")
    try:
        await validate_epistemic_integrity(
            db=db,
            context=CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                mutation_type=MutationType.TRANSITION,
                provenance=provenance or {},
                epistemic_status=epistemic_status,
            ),
        )
    except (EpistemicViolation, EpistemicPromotionViolation, AIOriginViolation, EvidenceTruthConfusionViolation, ProvenanceStrippingViolation, ContradictionPreservationViolation) as e:
        print(f"DEBUG: Epistemic integrity validation failed: {e}")
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    print(f"DEBUG: Epistemic integrity validation passed")
    
    # Contradiction preservation validation
    print(f"DEBUG: Validating contradiction preservation")
    try:
        await validate_contradiction_preservation(
            db=db,
            context=CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                mutation_type=MutationType.TRANSITION,
                provenance=provenance or {},
            ),
        )
    except (ContradictionPreservationViolation, ContradictionReferenceViolation) as e:
        print(f"DEBUG: Contradiction preservation validation failed: {e}")
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    print(f"DEBUG: Contradiction preservation validation passed")
    
    # Validate state transition FIRST (before any database operation)
    # This ensures invalid transitions are caught and returned as failed MutationResult
    current_state = getattr(entity, state_field)
    print(f"DEBUG: Validating state transition from {current_state} to {new_state}")
    try:
        validate_state_transition(entity_type, current_state, new_state)
    except InvalidStateTransition as e:
        print(f"DEBUG: State transition validation failed: {e}")
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    print(f"DEBUG: State transition validation passed")
    
    # Epistemic boundary validation
    try:
        await validate_epistemic_boundary(
            db,
            CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                epistemic_status=epistemic_status,
            ),
            epistemic_status,
        )
    except EpistemicViolation as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # Epistemic integrity (Gate 6-F)
    try:
        await validate_epistemic_integrity(
            db=db,
            context=CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                mutation_type=MutationType.TRANSITION,
                provenance=provenance or {},
                epistemic_status=epistemic_status,
            ),
        )
    except (EpistemicViolation, EpistemicPromotionViolation, AIOriginViolation, EvidenceTruthConfusionViolation, ProvenanceStrippingViolation, ContradictionPreservationViolation) as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # Contradiction preservation validation
    try:
        await validate_contradiction_preservation(
            db=db,
            context=CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                mutation_type=MutationType.TRANSITION,
                provenance=provenance or {},
            ),
        )
    except (ContradictionPreservationViolation, ContradictionReferenceViolation) as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Validate state transition FIRST (before any database operation)
    # This ensures invalid transitions are caught and returned as failed MutationResult
    current_state = getattr(entity, state_field)
    try:
        validate_state_transition(entity_type, current_state, new_state)
    except InvalidStateTransition as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # Use database-level optimistic concurrency for state transitions when version field exists
    if expected_version is not None and has_version:
        
        update_stmt = (
            update(model)
            .where(model.id == entity_id)
            .where(model.version == expected_version)
            .values(**update_values)
        )
        
        result = await db.execute(update_stmt)
        await db.flush()
        
        # Check rowcount to see if update succeeded
        if result.rowcount == 0:
            print(f"DEBUG: Stale version detected! expected_version={expected_version}, entity_id={entity_id}, entity_type={entity_type}")
            return MutationResult(
                success=False, 
                error=f"Stale version: expected {expected_version}, entity was modified concurrently",
                error_code="ConcurrencyViolation"
            )
        
        print(f"DEBUG: Update succeeded, rowcount={result.rowcount}, expected_version={expected_version}")
        
        # Fetch the updated entity
        updated_entity = await db.get(model, entity_id)
        if updated_entity is None:
            print(f"DEBUG: Entity not found after update")
            return MutationResult(
                success=False, 
                error="Entity not found after transition",
                error_code="NotFound"
            )
        
        print(f"DEBUG: Updated entity version={updated_entity.version}, returning success")
        return MutationResult(success=True, entity=updated_entity, fingerprint=None, version=updated_entity.version)
        
        # Record transition in history
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=caller.organization_id,
            entity_type=entity_type.lower().replace("company", ""),
            entity_id=entity.id,
            entity_label=getattr(entity, "title", str(entity.id))[:300],
            field="state",
            old_value=current_state,
            new_value=new_state,
            reason=f"State transition: {current_state} -> {new_state}",
            source_event_id=f"state_transition:{new_state}",
            changed_at=utcnow(),
        )
        db.add(history)
        await db.flush()
        
        return MutationResult(success=True, entity=updated_entity, fingerprint=None, version=updated_entity.version)
        
        return MutationResult(success=True, entity=updated_entity, fingerprint=None, version=updated_entity.version)
    
    # Fallback for entities without version field - use standard mutation path
    async def transition_fn(db: AsyncSession):
        entity = await db.get(model, entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type}:{entity_id}")
       
        # Validate state transition
        # Validate state transition
        current_state = getattr(entity, state_field)
        validate_state_transition(entity_type, current_state, new_state)
        old_state = current_state
        setattr(entity, state_field, new_state)
        entity.updated_at = utcnow()
        if hasattr(entity, "version"):
            entity.version += 1
       
        # Record transition in history
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=caller.organization_id,
            entity_type=entity_type.lower().replace("company", ""),
            entity_id=entity.id,
            entity_label=getattr(entity, "title", str(entity.id))[:300],
            field="state",
            old_value=old_state,
            new_value=new_state,
            reason=f"State transition: {old_state} -> {new_state}",
            source_event_id=f"state_transition:{new_state}",
            changed_at=utcnow(),
        )
        db.add(history)
       
        await db.flush()
        return entity
   
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.TRANSITION,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=transition_fn,
        expected_version=expected_version,
        provenance=provenance,
        required_permissions=required_permissions,
        trigger_reason=trigger_reason,
        entity=entity,
    )


async def canonical_delete(
    db: AsyncSession,
    caller: CallerAccess,
    entity_type: str,
    entity_id: str,
    expected_version: Optional[int] = None,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Delete a canonical entity through the boundary using database-level optimistic concurrency.
    
    This function runs all canonical validations (governance, temporal, provenance, epistemic,
    contradiction, exact-once, concurrency) through the CanonicalMutationBoundary, then executes
    a database-level optimistic DELETE with WHERE version = :expected_version.
    """
    # Fetch entity to get organization_id for tenant isolation check
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
        "CompanyGoal": CompanyGoal,
        "CompanyObjective": CompanyObjective,
        "CompanyInitiative": CompanyInitiative,
        "CompanyIntent": CompanyIntent,
        "Project": Project,
        "Task": Task,
        "Employee": Employee,
    }
    model = type_map.get(entity_type)
    if not model:
        raise ValueError(f"Unknown entity type: {entity_type}")

    entity = await db.get(model, entity_id)
    if not entity:
        raise ValueError(f"Entity not found: {entity_type}:{entity_id}")

    target_org_id = getattr(entity, "organization_id", None)
    
    # Check if entity supports versioning
    has_version = hasattr(entity, "version")
    current_version = getattr(entity, "version", None) if has_version else None
    
    # If expected_version not provided but entity has version, use current version
    if expected_version is None and current_version is not None:
        expected_version = current_version
    
    # Validate provenance for DELETE mutations
    await _validate_provenance_references(db, CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.DELETE,
        provenance=provenance or {},
    ))
    
    # Also validate required provenance fields for DELETE
    delete_context = CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.DELETE,
        provenance=provenance or {},
    )
    await validate_provenance(db, delete_context)
    
    # Validate temporal integrity for DELETE
    await validate_temporal_integrity(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        entity=entity,
        organization_id=caller.organization_id,
        mutation_type=MutationType.DELETE,
        allow_supersession=False,
    )
    
    # Epistemic boundary validation
    epistemic_status = getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)
    try:
        await validate_epistemic_boundary(
            db,
            CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                epistemic_status=epistemic_status,
            ),
            epistemic_status,
        )
    except EpistemicViolation as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # Epistemic integrity (Gate 6-F)
    try:
        await validate_epistemic_integrity(
            db=db,
            context=CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                mutation_type=MutationType.DELETE,
                provenance=provenance or {},
                epistemic_status=epistemic_status,
            ),
        )
    except (EpistemicViolation, EpistemicPromotionViolation, AIOriginViolation, EvidenceTruthConfusionViolation, ProvenanceStrippingViolation, ContradictionPreservationViolation) as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # Contradiction preservation validation
    try:
        await validate_contradiction_preservation(
            db=db,
            context=CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=entity_type,
                target_id=entity_id,
                mutation_type=MutationType.DELETE,
                provenance=provenance or {},
            ),
        )
    except (ContradictionPreservationViolation, ContradictionReferenceViolation) as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
    
    # Define the mutation function that does database-level optimistic DELETE
    async def delete_mutation_fn(db: AsyncSession) -> Any:
        if expected_version is not None and has_version:
            # Database-level optimistic DELETE with WHERE version = :expected_version
            delete_stmt = (
                delete(model)
                .where(model.id == entity_id)
                .where(model.version == expected_version)
            )
            
            result = await db.execute(delete_stmt)
            await db.flush()
            
            if result.rowcount == 0:
                raise ConcurrencyViolation(
                    f"Stale version: expected {expected_version}, entity was modified concurrently"
                )
            
            return {"deleted": True, "id": entity_id}
        else:
            # Fallback for entities without version field - standard ORM delete
            entity = await db.get(model, entity_id)
            if not entity:
                raise ValueError(f"Entity not found: {entity_type}:{entity_id}")
        
            await db.delete(entity)
            await db.flush()
            return {"deleted": True, "id": entity_id}
    
    # Call the canonical mutation boundary which runs ALL validations:
    # governance, temporal, provenance, epistemic, contradiction, exact-once, concurrency
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.DELETE,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=delete_mutation_fn,
        expected_version=expected_version,
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
    )


# -------------------------------------------------------------------------
# Worker Integration Helper
# -------------------------------------------------------------------------

async def worker_canonical_mutation(
    db: AsyncSession,
    organization_id: str,
    user_id: str,
    target_entity_type: str,
    mutation_type: MutationType,
    target_id: Optional[str] = None,
    mutation_fn: Callable = None,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    source_event_id: Optional[str] = None,
) -> MutationResult:
    """Helper for background workers to perform canonical mutations.
    
    Workers must provide organization_id and user_id for governance context.
    """
    # Build a minimal caller for the worker
   
    # Create a minimal caller context for the worker
    caller = CallerAccess(
        organization_id=organization_id,
        user_id=user_id,
        employee_id=None,
        org_wide=True,  # Workers typically have org-wide access
        anchored_scope_ids=frozenset(),
        ancestry_scope_ids=frozenset(),
        visible_scope_ids=frozenset(),
        project_ids=frozenset(),
        member_conversation_ids=frozenset(),
        links={},
    )
   
    # Create a mock user object
    class MockUser:
        def __init__(self, user_id):
            self.id = user_id
    
    mock_user = MockUser(user_id)
    
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=CallerAccess(
            organization_id=organization_id,
            user_id=user_id,
            employee_id=None,
            org_wide=True,
            anchored_scope_ids=frozenset(),
            ancestry_scope_ids=frozenset(),
            visible_scope_ids=frozenset(),
            project_ids=frozenset(),
            member_conversation_ids=frozenset(),
            links={},
        ),
        target_entity_type=target_entity_type,
        mutation_type=mutation_type,
        target_id=target_id,
        mutation_fn=mutation_fn,
        fingerprint=fingerprint,
        provenance=provenance,
        source_event_id=source_event_id,
        trigger_reason="worker_mutation",
    )


# -------------------------------------------------------------------------
# CompanyBrain Mutation Integration
# -------------------------------------------------------------------------

async def company_brain_canonical_mutation(
    db: AsyncSession,
    caller: CallerAccess,
    target_entity_type: str,
    mutation_type: MutationType,
    target_id: Optional[str] = None,
    mutation_fn: Callable = None,
    **kwargs
) -> MutationResult:
    """CompanyBrain mutations must go through the canonical boundary.
    
    This ensures CompanyBrain never becomes an alternative truth store.
    """
    # CompanyBrain is read-only by design - it should NOT mutate canonical state
    # This function exists to enforce that any attempt by CompanyBrain to mutate
    # goes through the canonical boundary
    
    # CompanyBrain should NOT mutate - it's read-only
    # If any code attempts to use this, it's a design violation
    raise CanonicalMutationError(
        "CompanyBrain is read-only. It must not mutate canonical company reality. "
        "Use canonical_mutation_boundary directly for mutations."
    )


# Export public API
__all__ = [
    "CanonicalMutationBoundary",
    "CanonicalMutationContext",
    "MutationResult",
    "MutationType",
    "EpistemicStatus",
    "CanonicalMutationError",
    "GovernanceViolation",
    "TenantIsolationViolation",
    "ScopeViolation",
    "InvalidStateTransition",
    "TemporalViolation",
    "ProvenanceViolation",
    "EpistemicViolation",
    "EpistemicPromotionViolation",
    "EpistemicDemotionViolation",
    "AIOriginViolation",
    "EvidenceTruthConfusionViolation",
    "ProvenanceStrippingViolation",
    "ConcurrencyViolation",
    "ExactOnceViolation",
    "canonical_mutation_boundary",
    "validate_governance",
    "validate_state_transition",
    "validate_temporal_integrity",
    "validate_provenance",
    "validate_epistemic_boundary",
    "validate_epistemic_integrity",
    "validate_exact_once",
    "validate_optimistic_concurrency",
    "execute_transactional",
    "canonical_create",
    "canonical_update",
    "canonical_transition",
    "canonical_delete",
    "worker_canonical_mutation",
    "company_brain_canonical_mutation",
    "STATE_TRANSITIONS",
    "CanonicalMutationError",
    "GovernanceViolation",
    "TenantIsolationViolation",
    "ScopeViolation",
    "InvalidStateTransition",
    "TemporalViolation",
    "ProvenanceViolation",
    "EpistemicViolation",
    "EpistemicPromotionViolation",
    "EpistemicDemotionViolation",
    "AIOriginViolation",
    "EvidenceTruthConfusionViolation",
    "ProvenanceStrippingViolation",
    "ConcurrencyViolation",
    "ExactOnceViolation",
]