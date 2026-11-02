"""Canonical Concurrency Integration — 35-G Integration Layer.

This module integrates the concurrency primitives with the canonical mutation boundary
to ensure all mutations go through the concurrency control fabric.

This module composes existing canonical primitives rather than creating a parallel system.
"""

from typing import Optional, Any, Callable, TypeVar
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

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

from app.intelligence.canonical_mutation import (
    CanonicalMutationContext,
    MutationType,
    EpistemicStatus,
    validate_governance,
    validate_temporal_integrity,
    validate_epistemic_boundary,
    validate_epistemic_integrity,
    validate_contradiction_preservation,
    validate_provenance,
    validate_exact_once,
    validate_optimistic_concurrency,
    CanonicalMutationContext,
    MutationType,
    EpistemicStatus,
    validate_governance,
    validate_temporal_integrity,
    validate_epistemic_boundary,
    validate_epistemic_integrity,
    validate_contradiction_preservation,
    validate_provenance,
    validate_exact_once,
    validate_optimistic_concurrency,
)