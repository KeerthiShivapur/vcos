"""Feature Flags Service — Gate 19

Governed feature flag management with tenant isolation,
rollout strategies, dependency management, and evaluation tracking.

Architecture:
- Feature flags = CONTROL PLANE state (feature availability)
- Authorization = SEPARATE system (actor permissions)
- Governance = SEPARATE system (organizational policy)
- Canonical Mutation = SEPARATE system (company reality changes)
- These boundaries MUST NEVER collapse into one mechanism
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Set, Tuple
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select, and_, or_, func, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.feature_flags import (
    FeatureFlag,
    FeatureFlagEvaluation,
    FeatureFlagAuditLog,
    FeatureFlagHistory,
    FeatureFlagStatus,
    RolloutStrategy,
    FeatureFlagScope,
    RolloutPrecedence,
    VALID_STATUS_TRANSITIONS,
)
from app.models.organization import Organization
from app.models.role import Permission, RolePermission, UserRoleModelModel
from app.models.governance import GovernanceScope, ApprovalPolicy
from app.models.finance import Entitlement, Plan
from app.events.publisher import publish_event

logger = logging.getLogger("vcos.feature_flags.service")


class FeatureFlagError(Exception):
    """Base exception for feature flag errors."""
    pass


class FeatureFlagNotFoundError(FeatureFlagError):
    """Feature flag not found."""
    pass


class FeatureFlagConflictError(FeatureFlagError):
    """Feature flag conflict (dependency/circular)."""
    pass


class FeatureFlagValidationError(FeatureFlagError):
    """Feature flag validation error."""
    pass


class FeatureFlagGovernanceError(FeatureFlagError):
    """Feature flag governance violation."""
    pass


class FeatureFlagTenantIsolationError(FeatureFlagError):
    """Feature flag tenant isolation violation."""
    pass


@dataclass
class EvaluationResult:
    """Result of a feature flag evaluation.
    
    This is FEATURE AVAILABILITY only - not authorization.
    """
    flag_id: str
    flag_key: str
    available: bool  # Renamed from 'enabled' to clarify this is availability
    reason: str
    evaluated_at: datetime
    context: Dict[str, Any]
    flag_version: int
    flag_status: str
    rollout_strategy: str


@dataclass
class FeatureFlagPermissionCheck:
    """Result of a permission check for feature flag operations."""
    allowed: bool
    required_permission: str
    user_permissions: List[str]
    reason: Optional[str] = None


# Permission codes for feature flag operations
FEATURE_FLAG_PERMISSIONS = {
    "create": "feature_flags:create",
    "read": "feature_flags:read",
    "update": "feature_flags:update",
    "delete": "feature_flags:delete",
    "evaluate": "feature_flags:evaluate",
    "change_lifecycle": "feature_flags:lifecycle",
    "change_rollout": "feature_flags:rollout",
    "change_dependencies": "feature_flags:dependencies",
    "emergency_disable": "feature_flags:emergency",
    "view_analytics": "feature_flags:analytics",
    "view_audit": "feature_flags:audit",
    "governance_override": "feature_flags:governance_override",
}


class FeatureFlagService:
    """Service for managing feature flags with governance.
    
    All operations are:
    - Tenant-scoped (organization_id required)
    - Governed (permission checks required for mutations)
    - Audited (all changes logged)
    - Concurrency-safe (optimistic locking)
    - Longitudinal (history preserved)
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    # ============================================================
    # PERMISSION / GOVERNANCE INTEGRATION
    # ============================================================
    
    async def _check_permission(
        self,
        organization_id: str,
        user_id: str,
        permission_code: str,
        scope_id: Optional[str] = None,
    ) -> FeatureFlagPermissionCheck:
        """Check if user has permission for feature flag operation.
        
        Reuses existing VCOS permission system.
        """
        from app.models.permission_helpers import user_permission_codes
        
        user_perms = await user_permission_codes(
            self.session,
            organization_id=organization_id,
            user_id=user_id,
        )
        
        allowed = permission_code in user_perms
        
        return FeatureFlagPermissionCheck(
            allowed=allowed,
            required_permission=permission_code,
            user_permissions=list(user_perms),
            reason=None if allowed else f"Missing permission: {permission_code}",
        )
    
    async def _require_permission(
        self,
        organization_id: str,
        user_id: str,
        permission_code: str,
        scope_id: Optional[str] = None,
    ) -> None:
        """Require permission, raise if not granted."""
        check = await self._check_permission(organization_id, user_id, permission_code, scope_id)
        if not check.allowed:
            raise FeatureFlagGovernanceError(check.reason or "Permission denied")
    
    async def _record_audit(
        self,
        organization_id: str,
        feature_flag_id: Optional[str],
        actor_id: str,
        action: str,
        before_state: Optional[Dict[str, Any]],
        after_state: Optional[Dict[str, Any]],
        governance_context: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlagAuditLog:
        """Record audit log entry for feature flag operation."""
        audit = FeatureFlagAuditLog(
            organization_id=organization_id,
            feature_flag_id=feature_flag_id,
            actor_id=actor_id,
            action=action,
            before_state=before_state,
            after_state=after_state,
            governance_context=governance_context or {},
            reason=reason,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(audit)
        await self.session.flush()
        return audit
    
    async def _record_history_snapshot(
        self,
        flag: FeatureFlag,
        actor_id: Optional[str],
        action: str,
    ) -> FeatureFlagHistory:
        """Record historical configuration snapshot for longitudinal queries."""
        # Get the latest snapshot version for this flag
        latest = await self.session.execute(
            select(func.max(FeatureFlagHistory.snapshot_version)).where(
                FeatureFlagHistory.feature_flag_id == flag.id
            )
        )
        latest_version = latest.scalar() or 0
        
        # Close previous snapshot
        previous = await self.session.execute(
            select(FeatureFlagHistory).where(
                and_(
                    FeatureFlagHistory.feature_flag_id == flag.id,
                    FeatureFlagHistory.valid_to.is_(None),
                )
            )
        )
        prev_snapshot = previous.scalar_one_or_none()
        if prev_snapshot:
            prev_snapshot.valid_to = datetime.now(timezone.utc)
        
        # Create new snapshot
        snapshot = FeatureFlagHistory(
            organization_id=flag.organization_id,
            feature_flag_id=flag.id,
            key=flag.key,
            name=flag.name,
            description=flag.description,
            status=flag.status,
            rollout_strategy=flag.rollout_strategy,
            rollout_config=flag.rollout_config,
            scope=flag.scope,
            depends_on=flag.depends_on,
            conflicts_with=flag.conflicts_with,
            tags=flag.tags,
            metadata_json=flag.metadata_json,
            emergency_disabled=flag.emergency_disabled,
            governance_context=flag.governance_context,
            flag_version=flag.version,
            snapshot_version=latest_version + 1,
            valid_from=datetime.now(timezone.utc),
            actor_id=actor_id,
            action=action,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot
    
    def _flag_to_dict(self, flag: FeatureFlag) -> Dict[str, Any]:
        """Convert flag to dictionary for audit/history."""
        return {
            "id": flag.id,
            "key": flag.key,
            "name": flag.name,
            "description": flag.description,
            "status": flag.status,
            "rollout_strategy": flag.rollout_strategy,
            "rollout_config": flag.rollout_config,
            "scope": flag.scope,
            "depends_on": flag.depends_on,
            "conflicts_with": flag.conflicts_with,
            "owner_id": flag.owner_id,
            "team_id": flag.team_id,
            "tags": flag.tags,
            "metadata_json": flag.metadata_json,
            "enabled_at": flag.enabled_at.isoformat() if flag.enabled_at else None,
            "deprecated_at": flag.deprecated_at.isoformat() if flag.deprecated_at else None,
            "deprecated_reason": flag.deprecated_reason,
            "archived_at": flag.archived_at.isoformat() if flag.archived_at else None,
            "archived_reason": flag.archived_reason,
            "emergency_disabled": flag.emergency_disabled,
            "emergency_disabled_at": flag.emergency_disabled_at.isoformat() if flag.emergency_disabled_at else None,
            "emergency_disabled_by": flag.emergency_disabled_by,
            "emergency_disabled_reason": flag.emergency_disabled_reason,
            "exposure_count": flag.exposure_count,
            "last_evaluated_at": flag.last_evaluated_at.isoformat() if flag.last_evaluated_at else None,
            "fingerprint": flag.fingerprint,
            "version": flag.version,
            "governance_context": flag.governance_context,
            "created_at": flag.created_at.isoformat(),
            "updated_at": flag.updated_at.isoformat(),
        }
    
    # ============================================================
    # TENANT ISOLATION VERIFICATION
    # ============================================================
    
    def _verify_tenant_isolation(self, organization_id: str, flag: FeatureFlag) -> None:
        """Verify flag belongs to the requesting organization."""
        if flag.organization_id != organization_id:
            raise FeatureFlagTenantIsolationError(
                f"Feature flag {flag.id} does not belong to organization {organization_id}"
            )
    
    async def _verify_tenant_isolation_by_id(self, organization_id: str, flag_id: str) -> FeatureFlag:
        """Verify flag belongs to organization and return it."""
        flag = await self.get_flag(organization_id, flag_id)
        if not flag:
            raise FeatureFlagNotFoundError(f"Feature flag {flag_id} not found")
        self._verify_tenant_isolation(organization_id, flag)
        return flag
    
    # ============================================================
    # DEPENDENCY GRAPH VALIDATION (with tenant boundary)
    # ============================================================
    
    async def _validate_dependencies(
        self,
        organization_id: str,
        depends_on: List[str],
        exclude_key: Optional[str] = None,
    ) -> None:
        """Validate all dependencies exist within the same tenant."""
        for dep_key in depends_on:
            if dep_key == exclude_key:
                raise FeatureFlagValidationError("Flag cannot depend on itself")
            
            dep = await self.get_flag_by_key(organization_id, dep_key)
            if not dep:
                raise FeatureFlagValidationError(f"Dependency '{dep_key}' does not exist")
    
    async def _validate_conflicts(
        self,
        organization_id: str,
        conflicts_with: List[str],
    ) -> None:
        """Validate all conflicts exist within the same tenant."""
        for conflict_key in conflicts_with:
            conflict = await self.get_flag_by_key(organization_id, conflict_key)
            if not conflict:
                raise FeatureFlagValidationError(f"Conflict '{conflict_key}' does not exist")
    
    async def _check_circular_dependencies(
        self,
        organization_id: str,
        flag_key: str,
        depends_on: List[str],
        exclude_id: Optional[str] = None,
        visited: Optional[Set[str]] = None,
        proposed_deps: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """Check for circular dependencies in feature flag graph.
        
        Tenant boundary is enforced - dependencies must be within same tenant.
        """
        if visited is None:
            visited = set()
        if proposed_deps is None:
            proposed_deps = {}
        
        if flag_key in visited:
            raise FeatureFlagConflictError(f"Circular dependency detected involving '{flag_key}'")
        
        visited.add(flag_key)
        
        for dep_key in depends_on:
            # Only query within the same tenant
            dep = await self.session.execute(
                select(FeatureFlag).where(
                    and_(
                        FeatureFlag.organization_id == organization_id,
                        FeatureFlag.key == dep_key,
                    )
                )
            )
            dep_flag = dep.scalar_one_or_none()
            if dep_flag:
                # Use proposed dependencies for the current flag being updated
                next_deps = proposed_deps.get(dep_key, dep_flag.depends_on or [])
                await self._check_circular_dependencies(
                    organization_id, dep_key, next_deps, exclude_id, visited, proposed_deps
                )
        
        visited.discard(flag_key)
    
    async def _resolve_dependency_graph(
        self,
        organization_id: str,
        flag_keys: List[str],
    ) -> Dict[str, List[str]]:
        """Resolve full dependency graph for a set of flags.
        
        Returns mapping of flag_key -> list of all transitive dependencies.
        """
        result = {}
        visited = set()
        
        async def resolve(key: str, path: Set[str]) -> List[str]:
            if key in result:
                return result[key]
            if key in path:
                # Circular dependency - should have been caught earlier
                raise FeatureFlagConflictError(f"Circular dependency detected at {key}")
            
            path.add(key)
            flag = await self.get_flag_by_key(organization_id, key)
            if not flag:
                result[key] = []
                path.discard(key)
                return []
            
            deps = flag.depends_on or []
            all_deps = list(deps)
            for dep_key in deps:
                transitive = await resolve(dep_key, path)
                all_deps.extend(transitive)
            
            # Deduplicate while preserving order
            seen = set()
            unique_deps = []
            for d in all_deps:
                if d not in seen:
                    seen.add(d)
                    unique_deps.append(d)
            
            result[key] = unique_deps
            path.discard(key)
            return unique_deps
        
        for key in flag_keys:
            await resolve(key, set())
        
        return result
    
    # ============================================================
    # COMMERCIAL ENTITLEMENT INTEGRATION
    # ============================================================
    
    async def _get_organization_entitlements(self, organization_id: str) -> Dict[str, Any]:
        """Get resolved entitlements for an organization."""
        entitlements = await self.session.execute(
            select(Entitlement).where(
                and_(
                    Entitlement.organization_id == organization_id,
                    or_(
                        Entitlement.effective_to.is_(None),
                        Entitlement.effective_to > datetime.now(timezone.utc),
                    ),
                )
            )
        )
        return {e.key: e for e in entitlements.scalars().all()}
    
    async def _check_entitlement(
        self,
        organization_id: str,
        entitlement_key: str,
    ) -> Optional[Any]:
        """Check if organization has a specific entitlement."""
        entitlement = await self.session.execute(
            select(Entitlement).where(
                and_(
                    Entitlement.organization_id == organization_id,
                    Entitlement.key == entitlement_key,
                    or_(
                        Entitlement.effective_to.is_(None),
                        Entitlement.effective_to > datetime.now(timezone.utc),
                    ),
                )
            )
        )
        e = entitlement.scalar_one_or_none()
        if e:
            if e.entitlement_type == "boolean":
                return e.boolean_value
            elif e.entitlement_type == "limit":
                return e.numeric_value
            elif e.entitlement_type == "tier":
                return e.value
        return None
    
    async def get_feature_entitlement(
        self,
        organization_id: str,
        feature_key: str,
    ) -> Dict[str, Any]:
        """Get entitlement status for a feature.
        
        Distinguishes:
        - Entitlement: commercial right to access capability
        - Feature Flag: operational rollout availability
        - Authorization: actor permission
        """
        # Check if feature is gated by entitlement
        entitlement = await self._check_entitlement(
            organization_id, f"features.{feature_key}.enabled"
        )
        
        # Also check plan-level features
        plan_entitlement = await self._check_entitlement(
            organization_id, f"plan.features.{feature_key}"
        )
        
        return {
            "entitled": bool(entitlement) or bool(plan_entitlement),
            "entitlement_value": entitlement or plan_entitlement,
            "source": "entitlement" if entitlement else "plan" if plan_entitlement else "none",
        }
    
    # ============================================================
    # CRUD Operations
    # ============================================================
    
    async def create_flag(
        self,
        organization_id: str,
        key: str,
        name: str,
        actor_id: str,
        description: Optional[str] = None,
        status: str = "off",
        rollout_strategy: str = "all",
        rollout_config: Optional[Dict[str, Any]] = None,
        scope: str = "tenant",
        depends_on: Optional[List[str]] = None,
        conflicts_with: Optional[List[str]] = None,
        owner_id: Optional[str] = None,
        team_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Create a new feature flag with governance."""
        # Verify organization exists
        org = await self.session.get(Organization, organization_id)
        if not org:
            raise ValueError(f"Organization {organization_id} not found")
        
        # Check permission
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["create"])
        
        # Validate key format
        if not key or not key.replace("_", "").replace("-", "").isalnum():
            raise FeatureFlagValidationError("Key must be alphanumeric with underscores/hyphens")
        
        # Check for duplicate key
        existing = await self.session.execute(
            select(FeatureFlag).where(
                and_(
                    FeatureFlag.organization_id == organization_id,
                    FeatureFlag.key == key
                )
            )
        )
        if existing.scalar_one_or_none():
            raise FeatureFlagValidationError(f"Feature flag with key '{key}' already exists")
        
        # Validate scope - GLOBAL requires special permission
        if scope == "global":
            await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["governance_override"])
        
        # Validate dependencies exist within tenant
        if depends_on:
            await self._validate_dependencies(organization_id, depends_on)
        
        # Validate conflicts exist within tenant
        if conflicts_with:
            await self._validate_conflicts(organization_id, conflicts_with)
        
        # Check for circular dependencies
        if depends_on:
            await self._check_circular_dependencies(organization_id, key, depends_on)
        
        # Compute fingerprint for exact-once
        fingerprint_data = f"{organization_id}:{key}:{name}:{status}:{rollout_strategy}:{str(rollout_config)}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
        
        # Create flag
        flag = FeatureFlag(
            organization_id=organization_id,
            key=key,
            name=name,
            description=description,
            status=status,
            rollout_strategy=rollout_strategy,
            rollout_config=rollout_config or {},
            scope=scope,
            depends_on=depends_on or [],
            conflicts_with=conflicts_with or [],
            owner_id=owner_id,
            team_id=team_id,
            tags=tags or [],
            metadata_json=metadata or {},
            fingerprint=fingerprint,
            governance_context=governance_context or {},
        )
        
        if status == "enabled":
            flag.enabled_at = datetime.now(timezone.utc)
        
        self.session.add(flag)
        await self.session.flush()
        
        # Record audit
        await self._record_audit(
            organization_id=organization_id,
            feature_flag_id=flag.id,
            actor_id=actor_id,
            action="create",
            before_state=None,
            after_state=self._flag_to_dict(flag),
            governance_context=governance_context,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        # Record history snapshot
        await self._record_history_snapshot(flag, actor_id, "create")
        
        await self.session.refresh(flag)
        
        logger.info(f"Created feature flag {flag.id} ({key}) for org {organization_id} by {actor_id}")
        return flag
    
    async def get_flag(self, organization_id: str, flag_id: str) -> Optional[FeatureFlag]:
        """Get a feature flag by ID (tenant-scoped)."""
        result = await self.session.execute(
            select(FeatureFlag).where(
                and_(
                    FeatureFlag.id == flag_id,
                    FeatureFlag.organization_id == organization_id
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def get_flag_by_key(self, organization_id: str, key: str) -> Optional[FeatureFlag]:
        """Get a feature flag by key (tenant-scoped)."""
        result = await self.session.execute(
            select(FeatureFlag).where(
                and_(
                    FeatureFlag.organization_id == organization_id,
                    FeatureFlag.key == key
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def list_flags(
        self,
        organization_id: str,
        actor_id: str,
        status: Optional[str] = None,
        scope: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[FeatureFlag]:
        """List feature flags with filters (tenant-scoped, permission-checked)."""
        # Check read permission
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["read"])
        
        query = select(FeatureFlag).where(FeatureFlag.organization_id == organization_id)
        
        if status:
            query = query.where(FeatureFlag.status == status)
        if scope:
            query = query.where(FeatureFlag.scope == scope)
        if tags:
            for tag in tags:
                query = query.where(FeatureFlag.tags.contains([tag]))
        
        query = query.order_by(FeatureFlag.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update_flag(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        rollout_strategy: Optional[str] = None,
        rollout_config: Optional[Dict[str, Any]] = None,
        scope: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        conflicts_with: Optional[List[str]] = None,
        owner_id: Optional[str] = None,
        team_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        version: Optional[int] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Update a feature flag with optimistic concurrency and governance."""
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        # Check permission
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["update"])
        
        # Optimistic concurrency check
        if version is not None and flag.version != version:
            raise FeatureFlagValidationError("Feature flag has been modified by another process")
        
        # Capture before state for audit
        before_state = self._flag_to_dict(flag)
        
        # Validate status transition
        if status and status != flag.status:
            if not flag.can_transition_to(status):
                raise FeatureFlagValidationError(
                    f"Invalid status transition: {flag.status} -> {status}"
                )
            # Lifecycle changes require specific permission
            await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["change_lifecycle"])
        
        # Validate dependencies
        if depends_on is not None:
            await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["change_dependencies"])
            await self._validate_dependencies(organization_id, depends_on, exclude_key=flag.key)
            proposed_deps = {flag.key: depends_on}
            await self._check_circular_dependencies(organization_id, flag.key, depends_on, exclude_id=flag_id, proposed_deps=proposed_deps)
        
        # Validate conflicts
        if conflicts_with is not None:
            await self._validate_conflicts(organization_id, conflicts_with)
        
        # Validate rollout changes
        if rollout_strategy is not None or rollout_config is not None:
            await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["change_rollout"])
        
        # Validate scope changes
        if scope is not None and scope != flag.scope:
            if scope == "global" or flag.scope == "global":
                await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["governance_override"])
        
        # Apply updates
        if name is not None:
            flag.name = name
        if description is not None:
            flag.description = description
        if status is not None:
            old_status = flag.status
            flag.status = status
            if status == "enabled" and old_status != "enabled":
                flag.enabled_at = datetime.now(timezone.utc)
            elif status == "deprecated" and old_status != "deprecated":
                flag.deprecated_at = datetime.now(timezone.utc)
                flag.deprecated_reason = metadata.get("deprecated_reason") if metadata else None
            elif status == "archived" and old_status != "archived":
                flag.archived_at = datetime.now(timezone.utc)
                flag.archived_reason = metadata.get("archived_reason") if metadata else None
        if rollout_strategy is not None:
            flag.rollout_strategy = rollout_strategy
        if rollout_config is not None:
            flag.rollout_config = rollout_config
        if scope is not None:
            flag.scope = scope
        if depends_on is not None:
            flag.depends_on = depends_on
        if conflicts_with is not None:
            flag.conflicts_with = conflicts_with
        if owner_id is not None:
            flag.owner_id = owner_id
        if team_id is not None:
            flag.team_id = team_id
        if tags is not None:
            flag.tags = tags
        if metadata is not None:
            flag.metadata_json = {**flag.metadata_json, **metadata}
        if governance_context is not None:
            flag.governance_context = {**flag.governance_context, **governance_context}
        
        flag.version += 1
        await self.session.flush()
        
        # Record audit
        await self._record_audit(
            organization_id=organization_id,
            feature_flag_id=flag.id,
            actor_id=actor_id,
            action="update",
            before_state=before_state,
            after_state=self._flag_to_dict(flag),
            governance_context=governance_context,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        # Record history snapshot
        await self._record_history_snapshot(flag, actor_id, "update")
        
        await self.session.refresh(flag)
        
        logger.info(f"Updated feature flag {flag.id} ({flag.key}) for org {organization_id} by {actor_id}")
        return flag
    
    async def delete_flag(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """Delete a feature flag with governance."""
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        # Check permission
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["delete"])
        
        # Check if other flags depend on this one
        dependents = await self.session.execute(
            select(FeatureFlag).where(
                and_(
                    FeatureFlag.organization_id == organization_id,
                    FeatureFlag.depends_on.contains([flag.key])
                )
            )
        )
        if dependents.scalar_one_or_none():
            raise FeatureFlagConflictError(f"Cannot delete: other flags depend on '{flag.key}'")
        
        # Capture before state
        before_state = self._flag_to_dict(flag)
        
        await self.session.delete(flag)
        await self.session.flush()
        
        # Record audit
        await self._record_audit(
            organization_id=organization_id,
            feature_flag_id=flag_id,
            actor_id=actor_id,
            action="delete",
            before_state=before_state,
            after_state=None,
            governance_context=governance_context,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        logger.info(f"Deleted feature flag {flag_id} ({flag.key}) for org {organization_id} by {actor_id}")
        return True
    
    # ============================================================
    # EVALUATION (Feature Availability - NOT Authorization)
    # ============================================================
    
    async def evaluate_flag(
        self,
        organization_id: str,
        key: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        actor_roles: Optional[List[str]] = None,
        actor_permissions: Optional[List[str]] = None,
    ) -> EvaluationResult:
        """Evaluate a feature flag for a user/context.
        
        Returns FEATURE AVAILABILITY only.
        Caller MUST combine with authorization check.
        
        Does NOT require special permission - read access is sufficient.
        """
        flag = await self.get_flag_by_key(organization_id, key)
        if not flag:
            return EvaluationResult(
                flag_id="",
                flag_key=key,
                available=False,
                reason="flag_not_found",
                evaluated_at=datetime.now(timezone.utc),
                context=context or {},
                flag_version=0,
                flag_status="unknown",
                rollout_strategy="unknown",
            )
        
        # Evaluate feature availability
        available = flag.evaluate(
            organization_id=organization_id,
            user_id=user_id,
            context=context,
            actor_roles=actor_roles,
            actor_permissions=actor_permissions,
        )
        
        # Determine reason
        if flag.emergency_disabled:
            reason = "emergency_disabled"
        elif flag.status != "enabled":
            reason = f"status_{flag.status}"
        elif not available:
            reason = f"rollout_{flag.rollout_strategy}_excluded"
        else:
            reason = f"rollout_{flag.rollout_strategy}_included"
        
        # Record evaluation (audit trail for availability decisions)
        evaluation = FeatureFlagEvaluation(
            organization_id=organization_id,
            feature_flag_id=flag.id,
            user_id=user_id,
            result=available,
            context_json=context,
            flag_version=flag.version,
            flag_status=flag.status,
            flag_rollout_strategy=flag.rollout_strategy,
            rollout_config_snapshot=flag.rollout_config,
        )
        self.session.add(evaluation)
        
        # Update metrics
        flag.exposure_count += 1
        flag.last_evaluated_at = datetime.now(timezone.utc)
        
        await self.session.flush()
        
        return EvaluationResult(
            flag_id=flag.id,
            flag_key=flag.key,
            available=available,
            reason=reason,
            evaluated_at=datetime.now(timezone.utc),
            context=context or {},
            flag_version=flag.version,
            flag_status=flag.status,
            rollout_strategy=flag.rollout_strategy,
        )
    
    async def evaluate_multiple(
        self,
        organization_id: str,
        keys: List[str],
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        actor_roles: Optional[List[str]] = None,
        actor_permissions: Optional[List[str]] = None,
    ) -> Dict[str, EvaluationResult]:
        """Evaluate multiple feature flags."""
        # Batch fetch flags for efficiency
        flags = await self.session.execute(
            select(FeatureFlag).where(
                and_(
                    FeatureFlag.organization_id == organization_id,
                    FeatureFlag.key.in_(keys)
                )
            )
        )
        flag_map = {f.key: f for f in flags.scalars().all()}
        
        results = {}
        for key in keys:
            flag = flag_map.get(key)
            if not flag:
                results[key] = EvaluationResult(
                    flag_id="",
                    flag_key=key,
                    available=False,
                    reason="flag_not_found",
                    evaluated_at=datetime.now(timezone.utc),
                    context=context or {},
                    flag_version=0,
                    flag_status="unknown",
                    rollout_strategy="unknown",
                )
                continue
            
            available = flag.evaluate(
                organization_id=organization_id,
                user_id=user_id,
                context=context,
                actor_roles=actor_roles,
                actor_permissions=actor_permissions,
            )
            
            if flag.emergency_disabled:
                reason = "emergency_disabled"
            elif flag.status != "enabled":
                reason = f"status_{flag.status}"
            elif not available:
                reason = f"rollout_{flag.rollout_strategy}_excluded"
            else:
                reason = f"rollout_{flag.rollout_strategy}_included"
            
            evaluation = FeatureFlagEvaluation(
                organization_id=organization_id,
                feature_flag_id=flag.id,
                user_id=user_id,
                result=available,
                context_json=context,
                flag_version=flag.version,
                flag_status=flag.status,
                flag_rollout_strategy=flag.rollout_strategy,
                rollout_config_snapshot=flag.rollout_config,
            )
            self.session.add(evaluation)
            
            flag.exposure_count += 1
            flag.last_evaluated_at = datetime.now(timezone.utc)
            
            results[key] = EvaluationResult(
                flag_id=flag.id,
                flag_key=flag.key,
                available=available,
                reason=reason,
                evaluated_at=datetime.now(timezone.utc),
                context=context or {},
                flag_version=flag.version,
                flag_status=flag.status,
                rollout_strategy=flag.rollout_strategy,
            )
        
        await self.session.flush()
        return results
    
    async def evaluate_with_authorization(
        self,
        organization_id: str,
        key: str,
        user_id: str,
        required_permission: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Evaluate feature availability AND authorization together.
        
        This is the CORRECT way to check if an actor can use a feature:
        1. Is the feature available? (feature flag)
        2. Is the actor authorized? (permission system)
        
        Returns (allowed, reason).
        """
        # Get actor's permissions and roles
        from app.models.permission_helpers import user_permission_codes
        from sqlalchemy.orm import selectinload
        
        user_perms = await user_permission_codes(
            self.session,
            organization_id=organization_id,
            user_id=user_id,
        )
        
        # Get user's roles with eager loading
        user_roles = await self.session.execute(
            select(UserRoleModel)
            .options(selectinload(UserRoleModel.role))
            .where(
                and_(
                    UserRoleModel.organization_id == organization_id,
                    UserRoleModel.user_id == user_id,
                )
            )
        )
        role_names = [ur.role.name for ur in user_roles.scalars().all() if ur.role]
        
        # Evaluate feature availability
        eval_result = await self.evaluate_flag(
            organization_id=organization_id,
            key=key,
            user_id=user_id,
            context=context,
            actor_roles=role_names,
            actor_permissions=list(user_perms),
        )
        
        if not eval_result.available:
            return False, f"feature_unavailable: {eval_result.reason}"
        
        # Check authorization if required
        if required_permission:
            if required_permission not in user_perms:
                return False, f"unauthorized: missing permission {required_permission}"
        
        return True, "allowed"
    
    # ============================================================
    # STATUS TRANSITIONS (Governed)
    # ============================================================
    
    async def _transition_status(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        new_status: str,
        reason: Optional[str] = None,
        version: Optional[int] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Internal method for governed status transitions."""
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        if not flag.can_transition_to(new_status):
            raise FeatureFlagValidationError(f"Invalid status transition: {flag.status} -> {new_status}")
        
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["change_lifecycle"])
        
        before_state = self._flag_to_dict(flag)
        
        metadata = {"deprecated_reason": reason} if new_status == "deprecated" and reason else {}
        if new_status == "archived" and reason:
            metadata["archived_reason"] = reason
        
        flag = await self.update_flag(
            organization_id=organization_id,
            flag_id=flag_id,
            actor_id=actor_id,
            status=new_status,
            metadata=metadata,
            version=version,
            governance_context=governance_context,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        return flag
    
    async def enable_flag(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        version: Optional[int] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Enable a feature flag."""
        return await self._transition_status(
            organization_id, flag_id, actor_id, "enabled",
            version=version, governance_context=governance_context,
            request_id=request_id, ip_address=ip_address, user_agent=user_agent
        )
    
    async def disable_flag(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        version: Optional[int] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Disable a feature flag (set to 'off')."""
        return await self._transition_status(
            organization_id, flag_id, actor_id, "off",
            version=version, governance_context=governance_context,
            request_id=request_id, ip_address=ip_address, user_agent=user_agent
        )
    
    async def deprecate_flag(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        reason: str,
        version: Optional[int] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Deprecate a feature flag."""
        return await self._transition_status(
            organization_id, flag_id, actor_id, "deprecated",
            reason=reason, version=version, governance_context=governance_context,
            request_id=request_id, ip_address=ip_address, user_agent=user_agent
        )
    
    async def archive_flag(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        reason: Optional[str] = None,
        version: Optional[int] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Archive a feature flag (terminal state)."""
        return await self._transition_status(
            organization_id, flag_id, actor_id, "archived",
            reason=reason, version=version, governance_context=governance_context,
            request_id=request_id, ip_address=ip_address, user_agent=user_agent
        )
    
    # ============================================================
    # EMERGENCY KILL SWITCH (Governed)
    # ============================================================
    
    async def emergency_disable(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        reason: str,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Emergency disable a feature flag.
        
        This is a governed operation that:
        - Immediately makes feature unavailable
        - Preserves canonical company reality
        - Creates audit trail
        - Does NOT delete historical data
        - Requires emergency permission
        """
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        # Require emergency permission
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["emergency_disable"])
        
        before_state = self._flag_to_dict(flag)
        
        flag.emergency_disabled = True
        flag.emergency_disabled_at = datetime.now(timezone.utc)
        flag.emergency_disabled_by = actor_id
        flag.emergency_disabled_reason = reason
        flag.version += 1
        
        await self.session.flush()
        
        # Record audit
        await self._record_audit(
            organization_id=organization_id,
            feature_flag_id=flag.id,
            actor_id=actor_id,
            action="emergency_disable",
            before_state=before_state,
            after_state=self._flag_to_dict(flag),
            governance_context=governance_context,
            reason=reason,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        # Record history snapshot
        await self._record_history_snapshot(flag, actor_id, "emergency_disable")
        
        # Publish event for observability
        await publish_event(
            self.session,
            name="feature_flag.emergency_disabled",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "flag_id": flag.id,
                "flag_key": flag.key,
                "reason": reason,
                "disabled_at": flag.emergency_disabled_at.isoformat(),
            },
        )
        
        await self.session.refresh(flag)
        
        logger.warning(f"EMERGENCY DISABLE: feature flag {flag.id} ({flag.key}) for org {organization_id} by {actor_id}: {reason}")
        return flag
    
    async def emergency_enable(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        reason: str,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Re-enable a feature flag after emergency disable."""
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["emergency_disable"])
        
        if not flag.emergency_disabled:
            raise FeatureFlagValidationError("Feature flag is not emergency disabled")
        
        before_state = self._flag_to_dict(flag)
        
        flag.emergency_disabled = False
        flag.emergency_disabled_at = None
        flag.emergency_disabled_by = None
        flag.emergency_disabled_reason = None
        flag.version += 1
        
        await self.session.flush()
        
        await self._record_audit(
            organization_id=organization_id,
            feature_flag_id=flag.id,
            actor_id=actor_id,
            action="emergency_enable",
            before_state=before_state,
            after_state=self._flag_to_dict(flag),
            governance_context=governance_context,
            reason=reason,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        await self._record_history_snapshot(flag, actor_id, "emergency_enable")
        
        await publish_event(
            self.session,
            name="feature_flag.emergency_enabled",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "flag_id": flag.id,
                "flag_key": flag.key,
                "reason": reason,
            },
        )
        
        await self.session.refresh(flag)
        
        logger.info(f"EMERGENCY ENABLE: feature flag {flag.id} ({flag.key}) for org {organization_id} by {actor_id}: {reason}")
        return flag
    
    # ============================================================
    # ROLLOUT MANAGEMENT (Governed)
    # ============================================================
    
    async def set_percentage_rollout(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        percentage: float,
        version: Optional[int] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Set percentage-based rollout."""
        if not 0 <= percentage <= 100:
            raise FeatureFlagValidationError("Percentage must be between 0 and 100")
        
        return await self.update_flag(
            organization_id=organization_id,
            flag_id=flag_id,
            actor_id=actor_id,
            rollout_strategy="percentage",
            rollout_config={"percentage": percentage},
            version=version,
            governance_context=governance_context,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    
    async def set_segment_rollout(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        segments: List[str],
        version: Optional[int] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Set segment-based rollout."""
        return await self.update_flag(
            organization_id=organization_id,
            flag_id=flag_id,
            actor_id=actor_id,
            rollout_strategy="segment",
            rollout_config={"segments": segments},
            version=version,
            governance_context=governance_context,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    
    async def set_ring_rollout(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        rings: List[str],
        version: Optional[int] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Set ring-based rollout (canary, early, broad)."""
        valid_rings = {"canary", "early", "broad"}
        for ring in rings:
            if ring not in valid_rings:
                raise FeatureFlagValidationError(f"Invalid ring: {ring}. Must be one of {valid_rings}")
        
        return await self.update_flag(
            organization_id=organization_id,
            flag_id=flag_id,
            actor_id=actor_id,
            rollout_strategy="ring",
            rollout_config={"rings": rings},
            version=version,
            governance_context=governance_context,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    
    async def set_custom_rollout(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        custom_rules: List[Dict[str, Any]],
        version: Optional[int] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Set custom rollout rules."""
        return await self.update_flag(
            organization_id=organization_id,
            flag_id=flag_id,
            actor_id=actor_id,
            rollout_strategy="custom",
            rollout_config={"custom_rules": custom_rules},
            version=version,
            governance_context=governance_context,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    
    # ============================================================
    # ANALYTICS & HEALTH
    # ============================================================
    
    async def get_evaluation_stats(
        self,
        organization_id: str,
        actor_id: str,
        flag_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get evaluation statistics for a flag."""
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["view_analytics"])
        
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        since = datetime.now(timezone.utc) - timedelta(days=days)
        
        total = await self.session.execute(
            select(func.count(FeatureFlagEvaluation.id)).where(
                and_(
                    FeatureFlagEvaluation.organization_id == organization_id,
                    FeatureFlagEvaluation.feature_flag_id == flag_id,
                    FeatureFlagEvaluation.evaluated_at >= since,
                )
            )
        )
        
        enabled = await self.session.execute(
            select(func.count(FeatureFlagEvaluation.id)).where(
                and_(
                    FeatureFlagEvaluation.organization_id == organization_id,
                    FeatureFlagEvaluation.feature_flag_id == flag_id,
                    FeatureFlagEvaluation.evaluated_at >= since,
                    FeatureFlagEvaluation.result == True,
                )
            )
        )
        
        unique_users = await self.session.execute(
            select(func.count(func.distinct(FeatureFlagEvaluation.user_id))).where(
                and_(
                    FeatureFlagEvaluation.organization_id == organization_id,
                    FeatureFlagEvaluation.feature_flag_id == flag_id,
                    FeatureFlagEvaluation.evaluated_at >= since,
                    FeatureFlagEvaluation.user_id.is_not(None),
                )
            )
        )
        
        total_count = total.scalar() or 0
        enabled_count = enabled.scalar() or 0
        unique_count = unique_users.scalar() or 0
        
        return {
            "total_evaluations": total_count,
            "available_evaluations": enabled_count,
            "unavailable_evaluations": total_count - enabled_count,
            "unique_users": unique_count,
            "availability_rate": enabled_count / total_count if total_count > 0 else 0,
            "period_days": days,
        }
    
    async def get_flag_health(
        self,
        organization_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Get overall feature flag health for organization."""
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["view_analytics"])
        
        flags = await self.list_flags(organization_id, actor_id, limit=1000)
        
        total = len(flags)
        by_status = {}
        for flag in flags:
            by_status[flag.status] = by_status.get(flag.status, 0) + 1
        
        deprecated = [f for f in flags if f.status == "deprecated"]
        stale = [f for f in flags if f.status == "enabled" and 
                f.last_evaluated_at and 
                f.last_evaluated_at < datetime.now(timezone.utc) - timedelta(days=90)]
        emergency_disabled = [f for f in flags if f.emergency_disabled]
        
        return {
            "total_flags": total,
            "by_status": by_status,
            "deprecated_count": len(deprecated),
            "stale_enabled_count": len(stale),
            "emergency_disabled_count": len(emergency_disabled),
            "health_score": self._calculate_health_score(flags),
        }
    
    def _calculate_health_score(self, flags: List[FeatureFlag]) -> float:
        """Calculate health score (0-100)."""
        if not flags:
            return 100.0
        
        score = 100.0
        for flag in flags:
            if flag.emergency_disabled:
                score -= 10
            elif flag.status == "deprecated":
                score -= 5
            elif flag.status == "enabled" and flag.last_evaluated_at:
                days_since = (datetime.now(timezone.utc) - flag.last_evaluated_at).days
                if days_since > 90:
                    score -= 2
                elif days_since > 30:
                    score -= 1
            elif flag.status == "enabled" and not flag.last_evaluated_at:
                score -= 3  # Never evaluated
        
        return max(0.0, score)
    
    # ============================================================
    # AUDIT & HISTORY
    # ============================================================
    
    async def get_audit_log(
        self,
        organization_id: str,
        actor_id: str,
        flag_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[FeatureFlagAuditLog]:
        """Get audit log for feature flags."""
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["view_audit"])
        
        query = select(FeatureFlagAuditLog).where(
            FeatureFlagAuditLog.organization_id == organization_id
        )
        
        if flag_id:
            query = query.where(FeatureFlagAuditLog.feature_flag_id == flag_id)
        if action:
            query = query.where(FeatureFlagAuditLog.action == action)
        
        query = query.order_by(FeatureFlagAuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_history(
        self,
        organization_id: str,
        actor_id: str,
        flag_id: str,
        limit: int = 100,
    ) -> List[FeatureFlagHistory]:
        """Get historical configuration for a flag (longitudinal queries)."""
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["view_analytics"])
        
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        query = select(FeatureFlagHistory).where(
            and_(
                FeatureFlagHistory.organization_id == organization_id,
                FeatureFlagHistory.feature_flag_id == flag_id,
            )
        ).order_by(FeatureFlagHistory.valid_from.desc()).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_configuration_at(
        self,
        organization_id: str,
        actor_id: str,
        flag_id: str,
        at: datetime,
    ) -> Optional[FeatureFlagHistory]:
        """Get flag configuration at a specific point in time."""
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["view_analytics"])
        
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        result = await self.session.execute(
            select(FeatureFlagHistory).where(
                and_(
                    FeatureFlagHistory.organization_id == organization_id,
                    FeatureFlagHistory.feature_flag_id == flag_id,
                    FeatureFlagHistory.valid_from <= at,
                    or_(
                        FeatureFlagHistory.valid_to.is_(None),
                        FeatureFlagHistory.valid_to > at,
                    ),
                )
            ).order_by(FeatureFlagHistory.valid_from.desc()).limit(1)
        )
        return result.scalar_one_or_none()
    
    # ============================================================
    # PRIVATE ALPHA ROLLOUT
    # ============================================================
    
    async def get_private_alpha_config(
        self,
        organization_id: str,
    ) -> Dict[str, Any]:
        """Get private alpha rollout configuration for an organization."""
        # Check for private alpha entitlement
        alpha_entitled = await self._check_entitlement(organization_id, "private_alpha.enabled")
        
        # Get alpha flags
        flags = await self.session.execute(
            select(FeatureFlag).where(
                and_(
                    FeatureFlag.organization_id == organization_id,
                    FeatureFlag.tags.contains(["private_alpha"]),
                )
            )
        )
        
        alpha_flags = list(flags.scalars().all())
        
        return {
            "entitled": bool(alpha_entitled),
            "flags": [
                {
                    "id": f.id,
                    "key": f.key,
                    "name": f.name,
                    "status": f.status,
                    "rollout_strategy": f.rollout_strategy,
                    "rollout_config": f.rollout_config,
                }
                for f in alpha_flags
            ],
        }
    
    async def promote_to_alpha(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        ring: str = "canary",
        percentage: float = 10.0,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Promote a feature flag to private alpha rollout."""
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["change_lifecycle"])
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["change_rollout"])
        
        before_state = self._flag_to_dict(flag)
        
        # Set to alpha status with controlled rollout
        flag.status = "alpha"
        flag.rollout_strategy = "ring"
        flag.rollout_config = {"rings": [ring], "percentage": percentage}
        if "private_alpha" not in (flag.tags or []):
            flag.tags = (flag.tags or []) + ["private_alpha"]
        flag.version += 1
        
        await self.session.flush()
        
        await self._record_audit(
            organization_id=organization_id,
            feature_flag_id=flag.id,
            actor_id=actor_id,
            action="promote_to_alpha",
            before_state=before_state,
            after_state=self._flag_to_dict(flag),
            governance_context=governance_context,
            reason=f"Promoted to private alpha: {ring} ring, {percentage}%",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        await self._record_history_snapshot(flag, actor_id, "promote_to_alpha")
        
        await self.session.refresh(flag)
        return flag
    
    async def promote_alpha_to_beta(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        percentage: float = 50.0,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Promote from alpha to beta with broader rollout."""
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["change_lifecycle"])
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["change_rollout"])
        
        before_state = self._flag_to_dict(flag)
        
        flag.status = "beta"
        flag.rollout_strategy = "percentage"
        flag.rollout_config = {"percentage": percentage}
        if "private_alpha" in (flag.tags or []):
            flag.tags = [t for t in (flag.tags or []) if t != "private_alpha"]
        flag.version += 1
        
        await self.session.flush()
        
        await self._record_audit(
            organization_id=organization_id,
            feature_flag_id=flag.id,
            actor_id=actor_id,
            action="promote_alpha_to_beta",
            before_state=before_state,
            after_state=self._flag_to_dict(flag),
            governance_context=governance_context,
            reason=f"Promoted alpha to beta: {percentage}%",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        await self._record_history_snapshot(flag, actor_id, "promote_alpha_to_beta")
        
        await self.session.refresh(flag)
        return flag
    
    async def promote_beta_to_enabled(
        self,
        organization_id: str,
        flag_id: str,
        actor_id: str,
        governance_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FeatureFlag:
        """Promote from beta to fully enabled."""
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["change_lifecycle"])
        
        before_state = self._flag_to_dict(flag)
        
        flag.status = "enabled"
        flag.rollout_strategy = "all"
        flag.rollout_config = {}
        if "private_alpha" in (flag.tags or []):
            flag.tags = [t for t in (flag.tags or []) if t != "private_alpha"]
        flag.version += 1
        
        await self.session.flush()
        
        await self._record_audit(
            organization_id=organization_id,
            feature_flag_id=flag.id,
            actor_id=actor_id,
            action="promote_beta_to_enabled",
            before_state=before_state,
            after_state=self._flag_to_dict(flag),
            governance_context=governance_context,
            reason="Promoted beta to fully enabled",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        await self._record_history_snapshot(flag, actor_id, "promote_beta_to_enabled")
        
        await self.session.refresh(flag)
        return flag
    
    # ============================================================
    # FAILURE / RECOVERY INTEGRATION
    # ============================================================
    
    async def evaluate_during_failure(
        self,
        organization_id: str,
        key: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        failure_context: Optional[Dict[str, Any]] = None,
    ) -> EvaluationResult:
        """Evaluate feature flag during failure scenario.
        
        Integrates with 35-H failure under load infrastructure.
        Safe defaults: deny feature if evaluation fails.
        """
        try:
            return await self.evaluate_flag(
                organization_id=organization_id,
                key=key,
                user_id=user_id,
                context=context,
            )
        except Exception as e:
            logger.error(f"Feature flag evaluation failed for {key}: {e}")
            
            # Record failure evaluation
            if failure_context:
                failure_context = {**failure_context, "error": str(e)}
            
            return EvaluationResult(
                flag_id="",
                flag_key=key,
                available=False,
                reason="evaluation_failed",
                evaluated_at=datetime.now(timezone.utc),
                context=context or {},
                flag_version=0,
                flag_status="unknown",
                rollout_strategy="unknown",
            )
    
    # ============================================================
    # LONGITUDINAL QUERIES
    # ============================================================
    
    async def get_flag_timeline(
        self,
        organization_id: str,
        actor_id: str,
        flag_id: str,
    ) -> List[Dict[str, Any]]:
        """Get complete timeline of flag changes for longitudinal analysis."""
        await self._require_permission(organization_id, actor_id, FEATURE_FLAG_PERMISSIONS["view_audit"])
        
        flag = await self._verify_tenant_isolation_by_id(organization_id, flag_id)
        
        history = await self.get_history(organization_id, actor_id, flag_id, limit=1000)
        audit = await self.get_audit_log(organization_id, actor_id, flag_id=flag_id, limit=1000)
        
        # Merge and sort timeline
        timeline = []
        
        for h in history:
            timeline.append({
                "timestamp": h.valid_from.isoformat(),
                "type": "configuration",
                "action": h.action,
                "actor_id": h.actor_id,
                "version": h.flag_version,
                "snapshot_version": h.snapshot_version,
                "configuration": {
                    "status": h.status,
                    "rollout_strategy": h.rollout_strategy,
                    "rollout_config": h.rollout_config,
                    "emergency_disabled": h.emergency_disabled,
                },
            })
        
        for a in audit:
            timeline.append({
                "timestamp": a.created_at.isoformat(),
                "type": "audit",
                "action": a.action,
                "actor_id": a.actor_id,
                "reason": a.reason,
                "governance_context": a.governance_context,
            })
        
        # Sort by timestamp
        timeline.sort(key=lambda x: x["timestamp"])
        return timeline


# Convenience function
async def get_feature_flag_service(session: AsyncSession) -> FeatureFlagService:
    """Get feature flag service instance."""
    return FeatureFlagService(session)