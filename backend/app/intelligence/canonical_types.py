"""Shared Canonical Types — 35-G.

This module contains shared types used by both canonical_mutation and canonical_concurrency
to avoid circular imports.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Callable, TypeVar, Generic, List, Dict, Set, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Callable, TypeVar, Generic, List, Dict, Set, Tuple
from enum import Enum


class MutationType(str, Enum):
    """Types of canonical mutations."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    TRANSITION = "transition"  # State transition


class EpistemicStatus(str, Enum):
    """Epistemic classification of canonical state."""
    OBSERVED = "observed"
    MEASURED = "measured"
    EVIDENCE_BACKED = "evidence_backed"
    INFERRED = "inferred"
    PREDICTED = "predicted"
    PROPOSED = "proposed"
    CONTESTED = "contested"


class ConcurrencyControlType(Enum):
    """Types of concurrency control mechanisms."""
    OPTIMISTIC = "optimistic"
    PESSIMISTIC = "pessimistic"
    LEASE_BASED = "lease_based"
    IDEMPOTENCY_KEY = "idempotency_key"


class ConcurrencyConflictResolution(Enum):
    """Strategies for resolving concurrency conflicts."""
    ABORT = "abort"
    RETRY = "retry"
    QUEUE = "queue"
    MERGE = "merge"
    COMPENSATE = "compensate"


@dataclass
class ConcurrencyContext:
    """Context for a concurrent operation."""
    operation_id: str
    entity_type: str
    entity_id: str
    actor_id: str
    organization_id: str
    concurrency_type: 'ConcurrencyControlType'
    expected_version: Optional[int] = None
    fingerprint: Optional[str] = None
    max_retries: int = 3
    retry_delay: float = 0.1
    timeout: float = 30.0


@dataclass
class ConcurrencyResult:
    """Result of a concurrent operation."""
    success: bool
    entity_id: Optional[str] = None
    version: Optional[int] = None
    conflict: bool = False
    conflict_details: Optional[str] = None
    retries: int = 0
    duration_ms: float = 0.0