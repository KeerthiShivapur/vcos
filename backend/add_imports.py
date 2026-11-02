with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Add the missing imports at the top
imports = b'''"""Canonical Mutation Boundary \xe2\x80\x94 Gate 6-B.

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


# Global exception handler for UnboundLocalError


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


'''

# Check if the file already has imports
if content.startswith(b'async def validate_provenance'):
    # Prepend the imports
    content = imports + b'\n' + content
    with open('app/intelligence/canonical_mutation.py', 'wb') as f:
        f.write(content)
    print("Added imports at the top of the file")
else:
    print("File already has imports or different structure")

print("Done")