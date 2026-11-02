"""Failure Injection Framework — 35-H.

Provides deterministic failure injection for testing canonical reliability
under failure conditions. Test-only infrastructure that does not alter
production semantics.
"""

import asyncio
import random
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.canonical_reliability import (
    FAILURE_CLASSES,
    CanonicalOperation,
    OperationAttempt,
    WorkerLease,
)


class FailureType(Enum):
    """Types of failures that can be injected."""
    
    # Database failures
    DATABASE_CONNECTION_LOST = "database_connection_lost"
    DATABASE_DEADLOCK = "database_deadlock"
    DATABASE_TIMEOUT = "database_timeout"
    DATABASE_SERIALIZATION_FAILURE = "database_serialization_failure"
    DATABASE_CONSTRAINT_VIOLATION = "database_constraint_violation"
    
    # Connection failures
    CONNECTION_REFUSED = "connection_refused"
    CONNECTION_TIMEOUT = "connection_timeout"
    CONNECTION_RESET = "connection_reset"
    NETWORK_UNREACHABLE = "network_unreachable"
    
    # Worker failures
    WORKER_CRASH = "worker_crash"
    WORKER_OOM = "worker_oom"
    WORKER_CRASH_DURING_EXECUTION = "worker_crash_during_execution"
    WORKER_LEASE_EXPIRED = "worker_lease_expired"
    
    # External system failures
    EXTERNAL_TIMEOUT = "external_timeout"
    EXTERNAL_HTTP_500 = "external_http_500"
    EXTERNAL_RATE_LIMIT = "external_rate_limit"
    EXTERNAL_PARTIAL_RESPONSE = "external_partial_response"
    EXTERNAL_DUPLICATE_DELIVERY = "external_duplicate_delivery"
    EXTERNAL_OUT_OF_ORDER = "external_out_of_order"
    EXTERNAL_UNKNOWN_OUTCOME = "external_unknown_outcome"
    
    # Infrastructure failures
    REDIS_UNAVAILABLE = "redis_unavailable"
    OBJECT_STORAGE_UNAVAILABLE = "object_storage_unavailable"
    NETWORK_INTERRUPTION = "network_interruption"
    DNS_FAILURE = "dns_failure"
    
    # Resource exhaustion
    CONNECTION_POOL_EXHAUSTED = "connection_pool_exhausted"
    MEMORY_EXHAUSTED = "memory_exhausted"
    CPU_EXHAUSTED = "cpu_exhausted"
    DISK_FULL = "disk_full"
    
    # Distributed operation failures
    DUPLICATE_DELIVERY = "duplicate_delivery"
    OUT_OF_ORDER_EVENTS = "out_of_order_events"
    RETRY_STORM = "retry_storm"
    
    # Recovery failures
    RECOVERY_FAILED = "recovery_failed"
    RECONCILIATION_FAILED = "reconciliation_failed"
    COMPENSATION_FAILED = "compensation_failed"
    
    # Authorization/Authorization failures
    AUTHORIZATION_REVOKED = "authorization_revoked"
    ROLE_REMOVED = "role_removed"
    LEASE_EXPIRED = "lease_expired"


@dataclass
class FailureInjection:
    """Configuration for a single failure injection."""
    
    failure_type: FailureType
    probability: float = 1.0  # 0.0 to 1.0
    target_operations: List[str] = field(default_factory=list)  # Empty = all operations
    target_workers: List[str] = field(default_factory=list)  # Empty = all workers
    delay_before_failure: float = 0.0  # seconds
    duration: float = 0.0  # 0 = permanent until cleared
    custom_exception: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def should_trigger(self, operation_type: str = "", worker_id: str = "") -> bool:
        """Check if this failure should trigger for the given operation/worker."""
        if self.probability < 1.0 and random.random() > self.probability:
            return False
        if self.target_operations and not any(op in self.target_operations for op in [operation_type]):
            return False
        if self.target_workers and worker_id not in self.target_workers:
            return False
        return True


@dataclass
class FailureScenario:
    """A named scenario composed of multiple failure injections."""
    
    name: str
    description: str
    injections: List[FailureInjection]
    setup: Optional[Callable] = None
    teardown: Optional[Callable] = None


class FailureInjectionContext:
    """Context manager for failure injection during tests."""
    
    def __init__(self):
        self.active_injections: List[FailureInjection] = []
        self.original_methods: Dict[str, Any] = {}
        self._patches: List[Any] = []
    
    def add_injection(self, injection: FailureInjection):
        """Add a failure injection to the context."""
        self.active_injections.append(injection)
    
    def add_scenario(self, scenario: FailureScenario):
        """Add all injections from a scenario."""
        for injection in scenario.injections:
            self.add_injection(injection)
        if scenario.setup:
            scenario.setup()
    
    def clear(self):
        """Clear all injections and restore original methods."""
        for patch_obj in self._patches:
            try:
                patch_obj.stop()
            except Exception:
                pass
        self._patches.clear()
        self.active_injections.clear()
        self.original_methods.clear()
    
    def should_inject(self, failure_type: FailureType, operation_type: str = "", worker_id: str = "") -> bool:
        """Check if any active injection should trigger for the given failure type."""
        for injection in self.active_injections:
            if injection.failure_type == failure_type and injection.should_trigger(operation_type="", worker_id=""):
                return True
        return False
    
    def get_injection(self, failure_type: FailureType) -> Optional[FailureInjection]:
        """Get the first matching injection for a failure type."""
        for injection in self.active_injections:
            if injection.failure_type == failure_type:
                return injection
        return None


# Global failure injection context (test-only)
_failure_context: Optional[FailureInjectionContext] = None


def get_failure_context() -> FailureInjectionContext:
    """Get the global failure injection context."""
    global _failure_context
    if _failure_context is None:
        _failure_context = FailureInjectionContext()
    return _failure_context


def set_failure_context(context: FailureInjectionContext):
    """Set the global failure injection context."""
    global _failure_context
    _failure_context = context


@asynccontextmanager
async def failure_injection(scenario: FailureScenario):
    """Context manager for running a failure scenario."""
    context = get_failure_context()
    context.add_scenario(scenario)
    try:
        yield context
    finally:
        context.clear()


# =============================================================================
# PREDEFINED FAILURE SCENARIOS
# =============================================================================

def create_database_failure_scenario() -> FailureScenario:
    """Scenario: Database connection failures during operations."""
    return FailureScenario(
        name="database_failure",
        description="Database connection failures during operations",
        injections=[
            FailureInjection(
                failure_type=FailureType.DATABASE_CONNECTION_LOST,
                probability=1.0,
                duration=5.0,
            ),
            FailureInjection(
                failure_type=FailureType.DATABASE_DEADLOCK,
                probability=0.3,
            ),
            FailureInjection(
                failure_type=FailureType.DATABASE_TIMEOUT,
                probability=0.2,
            ),
        ],
    )


def create_external_timeout_scenario() -> FailureScenario:
    """Scenario: External system timeouts during operations."""
    return FailureScenario(
        name="external_timeout",
        description="External system timeouts during operations",
        injections=[
            FailureInjection(
                failure_type=FailureType.EXTERNAL_TIMEOUT,
                probability=1.0,
            ),
            FailureInjection(
                failure_type=FailureType.EXTERNAL_UNKNOWN_OUTCOME,
                probability=0.5,
            ),
        ],
    )


def create_worker_crash_scenario() -> FailureScenario:
    """Scenario: Worker crashes during operation execution."""
    return FailureScenario(
        name="worker_crash",
        description="Worker crashes during operation execution",
        injections=[
            FailureInjection(
                failure_type=FailureType.WORKER_CRASH_DURING_EXECUTION,
                probability=1.0,
            ),
        ],
    )


def create_external_unknown_outcome_scenario() -> FailureScenario:
    """Scenario: External system executes but VCOS loses connection before response."""
    return FailureScenario(
        name="external_unknown_outcome",
        description="External system executes but VCOS loses connection before receiving response",
        injections=[
            FailureInjection(
                failure_type=FailureType.EXTERNAL_UNKNOWN_OUTCOME,
                probability=1.0,
            ),
        ],
    )


def create_retry_storm_scenario() -> FailureScenario:
    """Scenario: Retry storm with many concurrent retries."""
    return FailureScenario(
        name="retry_storm",
        description="High volume of retries causing resource exhaustion",
        injections=[
            FailureInjection(
                failure_type=FailureType.RETRY_STORM,
                probability=1.0,
            ),
        ],
    )


def create_duplicate_delivery_scenario() -> FailureScenario:
    """Scenario: Duplicate webhook/external event delivery."""
    return FailureScenario(
        name="duplicate_delivery",
        description="Same external event delivered multiple times",
        injections=[
            FailureInjection(
                failure_type=FailureType.DUPLICATE_DELIVERY,
                probability=1.0,
            ),
        ],
    )


def create_out_of_order_scenario() -> FailureScenario:
    """Scenario: Events arrive out of order."""
    return FailureScenario(
        name="out_of_order_events",
        description="Events arrive out of temporal order",
        injections=[
            FailureInjection(
                failure_type=FailureType.OUT_OF_ORDER_EVENTS,
                probability=1.0,
            ),
        ],
    )


def create_concurrent_failure_scenario() -> FailureScenario:
    """Scenario: Concurrent operations with failures."""
    return FailureScenario(
        name="concurrent_failure",
        description="Multiple concurrent operations with mixed failures",
        injections=[
            FailureInjection(
                failure_type=FailureType.DATABASE_DEADLOCK,
                probability=0.3,
            ),
            FailureInjection(
                failure_type=FailureType.WORKER_CRASH_DURING_EXECUTION,
                probability=0.2,
            ),
            FailureInjection(
                failure_type=FailureType.EXTERNAL_TIMEOUT,
                probability=0.3,
            ),
        ],
    )


# =============================================================================
# FAILURE INJECTION DECORATORS
# =============================================================================

def inject_failure(failure_type: FailureType, probability: float = 1.0):
    """Decorator to inject a failure into a test function."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            context = get_failure_context()
            injection = FailureInjection(
                failure_type=failure_type,
                probability=probability,
            )
            context.add_injection(injection)
            try:
                return await func(*args, **kwargs)
            finally:
                context.clear()
        return wrapper
    return decorator


def with_failure_injection(failure_type: FailureType, probability: float = 1.0):
    """Context manager for failure injection."""
    @asynccontextmanager
    async def _context():
        context = get_failure_context()
        injection = FailureInjection(
            failure_type=failure_type,
            probability=probability,
        )
        context.add_injection(injection)
        try:
            yield context
        finally:
            context.clear()
    return _context()


# =============================================================================
# FAILURE INJECTION HELPERS FOR TESTS
# =============================================================================

class FailureInjector:
    """Helper class for injecting failures in tests."""
    
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.context = get_failure_context()
        self.active_injections: List[FailureInjection] = []
    
    def inject(self, failure_type: FailureType, **kwargs) -> FailureInjection:
        """Add a failure injection."""
        injection = FailureInjection(failure_type=failure_type, **kwargs)
        self.active_injections.append(injection)
        self.context.add_injection(injection)
        return injection
    
    def inject_database_failure(self, failure_type: FailureType, **kwargs) -> FailureInjection:
        """Inject a database-related failure."""
        return self.inject(failure_type, **kwargs)
    
    def inject_worker_crash(self, **kwargs) -> FailureInjection:
        """Inject a worker crash."""
        return self.inject(FailureType.WORKER_CRASH_DURING_EXECUTION, **kwargs)
    
    def inject_external_timeout(self, **kwargs) -> FailureInjection:
        """Inject an external system timeout."""
        return self.inject(FailureType.EXTERNAL_TIMEOUT, **kwargs)
    
    def inject_external_unknown(self, **kwargs) -> FailureInjection:
        """Inject an external unknown outcome."""
        return self.inject(FailureType.EXTERNAL_UNKNOWN_OUTCOME, **kwargs)
    
    def inject_retry_storm(self, **kwargs) -> FailureInjection:
        """Inject a retry storm."""
        return self.inject(FailureType.RETRY_STORM, **kwargs)
    
    def clear(self):
        """Clear all active injections."""
        for injection in self.active_injections:
            # Remove from context
            if injection in self.context.active_injections:
                self.context.active_injections.remove(injection)
        self.active_injections.clear()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.clear()


async def with_failure_injection(
    failure_type: FailureType,
    func: Callable,
    *args,
    probability: float = 1.0,
    **kwargs
) -> Any:
    """Execute a function with a failure injection."""
    context = get_failure_context()
    injection = FailureInjection(
        failure_type=failure_type,
        probability=probability,
    )
    context.add_injection(injection)
    try:
        return await func(*args, **kwargs)
    finally:
        context.clear()


# =============================================================================
# PREDEFINED SCENARIOS REGISTRY
# =============================================================================

SCENARIOS = {
    "database_failure": create_database_failure_scenario(),
    "external_timeout": create_external_timeout_scenario(),
    "worker_crash": create_worker_crash_scenario(),
    "external_unknown_outcome": create_external_unknown_outcome_scenario(),
    "retry_storm": create_retry_storm_scenario(),
    "duplicate_delivery": create_duplicate_delivery_scenario(),
    "out_of_order_events": create_out_of_order_scenario(),
    "concurrent_failure": create_concurrent_failure_scenario(),
}


def get_scenario(name: str) -> Optional[FailureScenario]:
    """Get a predefined scenario by name."""
    return SCENARIOS.get(name)


def run_scenario(name: str, func: Callable, *args, **kwargs):
    """Run a function within a named failure scenario."""
    scenario = get_scenario(name)
    if not scenario:
        raise ValueError(f"Unknown scenario: {name}")
    
    context = get_failure_context()
    context.add_scenario(scenario)
    try:
        if asyncio.iscoroutinefunction(func):
            return asyncio.run(func(*args, **kwargs))
        else:
            return func(*args, **kwargs)
    finally:
        context.clear()


# Export all
__all__ = [
    "FailureType",
    "FailureInjection",
    "FailureScenario",
    "FailureInjectionContext",
    "FailureInjector",
    "get_failure_context",
    "set_failure_context",
    "failure_injection",
    "inject_failure",
    "with_failure_injection",
    "FailureInjector",
    "with_failure_injection",
    "create_database_failure_scenario",
    "create_external_timeout_scenario",
    "create_worker_crash_scenario",
    "create_external_unknown_outcome_scenario",
    "create_retry_storm_scenario",
    "create_duplicate_delivery_scenario",
    "create_out_of_order_scenario",
    "create_concurrent_failure_scenario",
    "inject_failure",
    "with_failure_injection",
    "FailureInjector",
    "with_failure_injection",
    "SCENARIOS",
    "get_scenario",
    "run_scenario",
]