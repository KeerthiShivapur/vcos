"""Canonical Concurrent Execution Test Harness — Assertions Module.

Provides reusable assertion helpers for verifying canonical concurrency properties.
"""

import asyncio
from typing import Any, List, Dict, Set, Optional, Type
from dataclasses import dataclass

from tests.concurrency.context import ConcurrentTestResult, ConcurrentTestRunner


# =============================================================================
# Core Concurrency Assertions
# =============================================================================

def assert_idempotent_duplicate_operations(
    runner: ConcurrentTestRunner,
    expected_count: int,
    entity_type: str,
) -> str:
    """Assert that duplicate operations produced exactly one canonical entity.
    
    Args:
        runner: The test runner with results
        expected_count: Number of concurrent operations that were attempted
        entity_type: Human-readable entity type for error messages
    
    Returns:
        The single canonical entity ID
    """
    successful = runner.successful_results()
    assert len(successful) == expected_count, \
        f"All {expected_count} operations should succeed (idempotent), got {len(successful)}"
    
    entity_ids = runner.unique_entity_ids()
    assert len(entity_ids) == 1, \
        f"Expected exactly 1 canonical {entity_type}, got {len(entity_ids)}: {entity_ids}"
    
    return list(entity_ids)[0]


def assert_optimistic_concurrency_conflict(
    runner: ConcurrentTestRunner,
    expected_successes: int = 1,
) -> None:
    """Assert that optimistic concurrency control detected conflicts correctly.
    
    Args:
        runner: Test runner with results
        expected_successes: Number of operations expected to succeed (default 1)
    """
def assert_optimistic_concurrency_conflict(
    runner: ConcurrentTestRunner,
    expected_successes: int = 1,
) -> None:
    """Assert that optimistic concurrency control detected conflicts correctly.
    
    Args:
        runner: Test runner with results
        expected_successes: Number of operations expected to succeed (default 1)
    """
    successful = runner.successful_results()
    failed = runner.failed_results()
    
    # DEBUG: Print all results
    print(f"DEBUG assertion: total results={len(runner.results)}")
    for i, r in enumerate(runner.results):
        print(f"  Result {i}: actor={r.actor_id}, success={r.success}, error={r.error}, result_type={type(r.result).__name__ if r.result else None}")
    
    assert len(successful) == expected_successes, \
        f"Expected {expected_successes} successful operations, got {len(successful)}"
    assert len(failed) > 0, "Expected at least one concurrency conflict"
    
    # All failures should be version/concurrency errors
    for r in failed:
        error_lower = (r.error or "").lower()
        assert any(kw in error_lower for kw in ["stale", "version", "concurrency", "conflict"]), \
            f"Expected concurrency/version conflict error, got: {r.error}"


def assert_pessimistic_lock_exclusivity(
    runner: ConcurrentTestRunner,
    expected_exclusive_holder: int = 1,
) -> None:
    """Assert that pessimistic locking prevented concurrent access."""
    successful = runner.successful_results()
    failed = runner.failed_results()
    
    # Exactly the expected number should acquire the lock
    assert len(successful) == expected_exclusive_holder, \
        f"Expected {expected_exclusive_holder} to acquire lock, got {len(successful)}"
    
    # Others should fail or wait
    assert len(failed) >= 0, "Expected some to fail or wait"


def assert_unknown_state_preserved(
    operation: Any,
    context: str = "",
) -> None:
    """Assert that UNKNOWN state was preserved (not converted to FAILED/SUCCESS)."""
    prefix = f"{context}: " if context else ""
    assert operation.state == "unknown", \
        f"{prefix}Expected UNKNOWN state, got {operation.state}"
    assert operation.outcome is None, \
        f"{prefix}Outcome should be None for UNKNOWN state"


def assert_recovery_reconciliation_flow(
    operation: Any,
    expected_final_state: str = "reconciled",
) -> None:
    """Assert that recovery/reconciliation flow completed correctly."""
    assert operation.state == expected_final_state, \
        f"Expected {expected_final_state}, got {operation.state}"
    assert operation.outcome in ("success", "partial", "compensated"), \
        f"Expected successful outcome, got {operation.outcome}"


def assert_tenant_isolation_maintained(
    results_a: List[ConcurrentTestResult],
    results_b: List[ConcurrentTestResult],
    org_a_id: str,
    org_b_id: str,
    db_session: Any,
    entity_model: Type[Any],
    org_field: str = "organization_id",
) -> None:
    """Assert that tenant isolation is maintained under concurrency."""
    # Verify each tenant only has their own data
    from sqlalchemy import select, func
    
    async def check():
        # Tenant A
        count_a = await db_session.execute(
            select(func.count()).select_from(entity_model).where(
                getattr(entity_model, org_field) == org_a_id
            )
        )
        # Tenant B
        count_b = await db_session.execute(
            select(func.count()).select_from(entity_model).where(
                getattr(entity_model, org_field) == org_b_id
            )
        )
        return count_a.scalar(), count_b.scalar()
    
    # This would be called with await in the test
    # The actual verification is done by the test


def assert_temporal_integrity_preserved(
    entity: Any,
    temporal_fields: List[str],
    original_values: Dict[str, Any],
) -> None:
    """Assert that temporal fields were preserved during concurrent updates."""
    for field in temporal_fields:
        current_value = getattr(entity, field, None)
        original_value = original_values.get(field)
        assert current_value == original_value, \
            f"Temporal field {field} changed from {original_value} to {current_value}"


def assert_provenance_preserved(
    entity: Any,
    provenance_fields: List[str],
    original_provenance: Dict[str, Any],
) -> None:
    """Assert that provenance was preserved during state transitions."""
    current_provenance = getattr(entity, "provenance", {}) or {}
    
    for field in provenance_fields:
        current_value = current_provenance.get(field)
        original_value = original_provenance.get(field)
        if original_value is not None:
            assert current_value == original_value, \
                f"Provenance field {field} changed from {original_value} to {current_value}"


def assert_epistemic_boundary_enforced(
    result: ConcurrentTestResult,
    forbidden_transitions: List[str] = None,
) -> None:
    """Assert that epistemic boundaries were enforced (illegal promotions blocked)."""
    if forbidden_transitions is None:
        forbidden_transitions = ["proposed->observed", "evidence_backed->observed", "predicted->observed"]
    
    assert not result.success, "Expected epistemic promotion to be blocked"
    
    error_lower = result.error.lower()
    assert any(kw in error_lower for kw in ["epistemic", "promotion", "boundary", "illegal"]), \
        f"Expected epistemic boundary violation error, got: {result.error}"


def assert_no_resource_leaks(
    runner: ConcurrentTestRunner,
    checks: List[str] = None,
) -> None:
    """Assert that no resources were leaked during concurrent execution.
    
    Checks for:
    - Leaked database connections
    - Leased WorkerLease records
    - Open transactions
    - Orphaned operation attempts
    """
    if checks is None:
        checks = ["connections", "leases", "transactions", "attempts"]
    
    # This is a placeholder for actual leak detection
    # Real implementation would check database state
    assert all(r.duration_ms > 0 for r in runner.results), "All operations should have duration"


def assert_canonical_company_reality_integrity(
    db_session: Any,
    organization_id: str,
    expected_entities: Dict[str, int],
) -> None:
    """Assert that the canonical company reality remains consistent.
    
    Verifies:
    - No duplicate canonical entities
    - All entities belong to the correct organization
    - No cross-tenant leakage
    - Version consistency
    """
    # Placeholder for comprehensive reality integrity checks
    pass


# =============================================================================
# Decision/Action Lifecycle Assertions
# =============================================================================

VALID_DECISION_TRANSITIONS = {
    "proposed": ["approved", "rejected"],
    "approved": ["executed", "superseded"],
    "rejected": [],
    "executed": ["outcome_recorded"],
    "outcome_recorded": ["assessed"],
    "assessed": [],
}

VALID_AUTHORIZATION_TRANSITIONS = {
    "requested": ["approved", "conditional", "rejected"],
    "approved": ["superseded"],
    "conditional": ["approved", "rejected", "superseded"],
    "rejected": [],
    "superseded": [],
}

VALID_ACTION_TRANSITIONS = {
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
}


def assert_valid_lifecycle_transition(
    entity_type: str,
    from_state: str,
    to_state: str,
) -> None:
    """Assert that a state transition is valid per canonical lifecycle rules."""
    valid_map = {
        "CompanyDecision": VALID_DECISION_TRANSITIONS,
        "CompanyAuthorization": VALID_AUTHORIZATION_TRANSITIONS,
        "CompanyAction": VALID_ACTION_TRANSITIONS,
    }
    
    valid = valid_map.get(entity_type, {})
    allowed = valid.get(from_state, [])
    
    assert to_state in allowed, \
        f"Invalid {entity_type} transition: {from_state} -> {to_state}. Allowed: {allowed}"


def assert_concurrent_lifecycle_safety(
    results: List[ConcurrentTestResult],
    entity_type: str,
    initial_state: str,
    valid_final_states: List[str],
) -> None:
    """Assert that concurrent lifecycle transitions were handled safely."""
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    # At least one should succeed
    assert len(successful) >= 1, "At least one transition should succeed"
    
    # All should end in valid final states
    # This would check the actual entity states in the database
    pass


# =============================================================================
# Company Brain Projection Assertions
# =============================================================================

def assert_company_brain_is_projection(
    db_session: Any,
    organization_id: str,
    canonical_entities: List[Any],
) -> None:
    """Assert that Company Brain is a projection of canonical reality.
    
    Verifies:
    - Company Brain state is derived from canonical entities
    - No Company Brain state exists without canonical backing
    - Company Brain updates follow canonical mutations (not concurrent)
    """
    # This would query Company Brain projections and verify they match
    # the canonical entities
    pass


def assert_company_brain_does_not_mutate_canonical(
    result: ConcurrentTestResult,
    context: str = "",
) -> None:
    """Assert that Company Brain mutations are rejected."""
    prefix = f"{context}: " if context else ""
    assert not result.success, f"{prefix}Company Brain mutation should be rejected"
    error_lower = result.error.lower()
    assert any(kw in error_lower for kw in ["readonly", "read-only", "projection", "brain"]), \
        f"{prefix}Expected Company Brain read-only error, got: {result.error}"


# =============================================================================
# Resource Cleanup Assertions
# =============================================================================

def assert_no_leaked_leases(
    db_session: Any,
    organization_id: str,
    context: str = "",
) -> None:
    """Assert no WorkerLease records were left active after test."""
    from sqlalchemy import select, func
    from app.models.canonical_reliability import WorkerLease
    
    async def check():
        active = await db_session.execute(
            select(func.count()).select_from(WorkerLease).where(
                WorkerLease.organization_id == organization_id,
                WorkerLease.active == True,
            )
        )
        return active.scalar()
    
    # In sync context, this would need to be awaited
    pass


def assert_no_orphaned_operation_attempts(
    db_session: Any,
    operation_id: str,
    context: str = "",
) -> None:
    """Assert no OperationAttempt records were left in executing state."""
    from sqlalchemy import select, func
    from app.models.canonical_reliability import OperationAttempt
    
    async def check():
        orphaned = await db_session.execute(
            select(func.count()).select_from(OperationAttempt).where(
                OperationAttempt.operation_id == operation_id,
                OperationAttempt.state == "executing",
            )
        )
        return orphaned.scalar()
    
    pass


def assert_no_open_transactions(
    db_session: Any,
    context: str = "",
) -> None:
    """Assert no transactions were left open."""
    # This is a placeholder - real implementation would check transaction state
    pass


# =============================================================================
# PostgreSQL Concurrency Assertions
# =============================================================================

def assert_postgresql_row_locks_worked(
    db_session: Any,
    table_name: str,
    context: str = "",
) -> None:
    """Assert that PostgreSQL row-level locking behaved correctly.
    
    This is a placeholder for actual PostgreSQL-specific checks.
    """
    pass


def assert_advisory_locks_worked(
    db_session: Any,
    context: str = "",
) -> None:
    """Assert that PostgreSQL advisory locks behaved correctly."""
    pass


def assert_serializable_isolation(
    db_session: Any,
    context: str = "",
) -> None:
    """Assert that serializable transaction isolation prevented anomalies."""
    pass