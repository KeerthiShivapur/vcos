"""Slice 4C — governance kernel service.

One authorization kernel for every organization size. Role assignments
(RBAC) anchor to an optional governance scope tree; delegations and approval
policies carry the same scope axis (ABAC context). Every evaluation is a
bounded query — the user's own roles, the user's own grants, and an ancestry
walk capped at MAX_SCOPE_DEPTH. No operation scans the organization.

Authority model at a scope: org-wide roles/grants + roles/grants anchored at
the scope or any of its ancestors.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.enterprise import AccessGrant
from app.models.governance import ApprovalPolicy, GovernanceScope
from app.models.role import Permission, RolePermission, UserRoleModel

MAX_SCOPE_DEPTH = 32
SWEEP_BATCH_LIMIT = 5000


class GovernanceError(ValueError):
    pass


class GovernanceService:
    # ------------------------------------------------------------------ scopes
    async def get_scope(
        self, db: AsyncSession, *, organization_id: str, scope_id: str
    ) -> Optional[GovernanceScope]:
        scope = await db.get(GovernanceScope, scope_id)
        if scope is None or scope.organization_id != organization_id:
            return None
        return scope

    async def list_scopes(self, db: AsyncSession, *, organization_id: str) -> list[GovernanceScope]:
        rows = await db.execute(
            select(GovernanceScope)
            .where(GovernanceScope.organization_id == organization_id)
            .order_by(GovernanceScope.depth, GovernanceScope.name)
        )
        return list(rows.scalars().all())

    async def create_scope(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        scope_type: str,
        parent_id: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> GovernanceScope:
        depth = 0
        if parent_id:
            parent = await self.get_scope(db, organization_id=organization_id, scope_id=parent_id)
            if parent is None:
                raise GovernanceError("Parent scope not found")
            depth = parent.depth + 1
            if depth > MAX_SCOPE_DEPTH:
                raise GovernanceError("Scope depth limit reached")
        scope = GovernanceScope(
            organization_id=organization_id,
            name=name,
            scope_type=scope_type,
            parent_id=parent_id,
            entity_id=entity_id,
            depth=depth,
        )
        db.add(scope)
        await db.flush()
        return scope

    async def update_scope(
        self, db: AsyncSession, *, organization_id: str, scope_id: str, name: Optional[str] = None
    ) -> GovernanceScope:
        scope = await self.get_scope(db, organization_id=organization_id, scope_id=scope_id)
        if scope is None:
            raise GovernanceError("Scope not found")
        if name is not None:
            scope.name = name
        await db.flush()
        return scope

    async def delete_scope(
        self, db: AsyncSession, *, organization_id: str, scope_id: str
    ) -> None:
        scope = await self.get_scope(db, organization_id=organization_id, scope_id=scope_id)
        if scope is None:
            raise GovernanceError("Scope not found")
        children = (
            await db.execute(
                select(GovernanceScope.id).where(GovernanceScope.parent_id == scope_id).limit(1)
            )
        ).scalars().first()
        if children:
            raise GovernanceError("Scope has child scopes and cannot be deleted")
        assignments = (
            await db.execute(select(UserRoleModel.id).where(UserRoleModel.scope_id == scope_id).limit(1))
        ).scalars().first()
        if assignments:
            raise GovernanceError("Scope has role assignments and cannot be deleted")
        grants = (
            await db.execute(
                select(AccessGrant.id).where(
                    AccessGrant.resource_type == "scope",
                    AccessGrant.resource_id == scope_id,
                    AccessGrant.status == "active",
                ).limit(1)
            )
        ).scalars().first()
        if grants:
            raise GovernanceError("Scope has active delegations and cannot be deleted")
        policies = (
            await db.execute(
                select(ApprovalPolicy.id).where(ApprovalPolicy.scope_id == scope_id).limit(1)
            )
        ).scalars().first()
        if policies:
            raise GovernanceError("Scope has approval policies and cannot be deleted")
        await db.delete(scope)
        await db.flush()

    async def ancestor_scope_ids(
        self, db: AsyncSession, *, organization_id: str, scope_id: str
    ) -> list[str]:
        """The scope plus every ancestor (scope-first). Bounded by tree depth."""
        ids: list[str] = []
        current = await self.get_scope(db, organization_id=organization_id, scope_id=scope_id)
        guard = 0
        while current is not None and guard <= MAX_SCOPE_DEPTH:
            ids.append(current.id)
            if current.parent_id is None:
                break
            current = await db.get(GovernanceScope, current.parent_id)
            guard += 1
        return ids

    # ------------------------------------------------- effective permissions
    async def scoped_role_codes(
        self, db: AsyncSession, *, organization_id: str, user_id: str, scope_ids: list[str]
    ) -> set[str]:
        if not scope_ids:
            return set()
        rows = await db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRoleModel, UserRoleModel.role_id == RolePermission.role_id)
            .where(
                UserRoleModel.user_id == user_id,
                UserRoleModel.organization_id == organization_id,
                UserRoleModel.scope_id.in_(scope_ids),
            )
        )
        return set(rows.scalars().all())

    async def delegation_codes_at_scopes(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_id: str,
        scope_ids: list[str],
    ) -> set[str]:
        if not scope_ids:
            return set()
        now = utcnow()
        rows = await db.execute(
            select(AccessGrant.permission_code).where(
                AccessGrant.organization_id == organization_id,
                AccessGrant.granted_to_user == user_id,
                AccessGrant.status == "active",
                AccessGrant.resource_type == "scope",
                AccessGrant.resource_id.in_(scope_ids),
                or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > now),
                or_(AccessGrant.starts_at.is_(None), AccessGrant.starts_at <= now),
            )
        )
        return set(rows.scalars().all())

    async def effective_permission_codes(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_id: str,
        scope_id: Optional[str] = None,
    ) -> set[str]:
        """Union of org-wide authority and scope-anchored authority.

        Bounded: one roles query, one grants query, one ancestry walk.
        """
        from app.services.permission_service import permission_service

        codes = await permission_service.user_permission_codes(db, user_id, organization_id)
        if scope_id:
            ancestry = await self.ancestor_scope_ids(
                db, organization_id=organization_id, scope_id=scope_id
            )
            codes |= await self.scoped_role_codes(
                db, organization_id=organization_id, user_id=user_id, scope_ids=ancestry
            )
            codes |= await self.delegation_codes_at_scopes(
                db, organization_id=organization_id, user_id=user_id, scope_ids=ancestry
            )
        return codes

    async def has_permission(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_id: str,
        permission_code: str,
        scope_id: Optional[str] = None,
    ) -> bool:
        codes = await self.effective_permission_codes(
            db, organization_id=organization_id, user_id=user_id, scope_id=scope_id
        )
        return permission_code in codes

    # ------------------------------------------------------- scoped roles
    async def list_assignments(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_id: Optional[str] = None,
        scope_id: Optional[str] = None,
        role_id: Optional[str] = None,
    ) -> list[UserRoleModel]:
        stmt = select(UserRoleModel).where(UserRoleModel.organization_id == organization_id)
        if user_id:
            stmt = stmt.where(UserRoleModel.user_id == user_id)
        if scope_id:
            stmt = stmt.where(UserRoleModel.scope_id == scope_id)
        if role_id:
            stmt = stmt.where(UserRoleModel.role_id == role_id)
        rows = await db.execute(stmt.order_by(UserRoleModel.created_at.desc()).limit(500))
        return list(rows.scalars().all())

    async def assign_role_at_scope(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        actor_user_id: str,
        user_id: str,
        role_id: str,
        scope_id: Optional[str] = None,
    ) -> UserRoleModel:
        """Assign a role to a user at a scope (null scope = org-wide).

        No privilege escalation: the actor must already hold every permission
        the role grants at that scope.
        """
        from app.models.role import Role
        from app.models.user import User
        from app.services.permission_service import permission_service

        target = await db.get(User, user_id)
        if target is None or target.organization_id != organization_id:
            raise GovernanceError("Target user not found")
        role = await db.get(Role, role_id)
        if role is None or role.organization_id != organization_id:
            raise GovernanceError("Role not found")
        if scope_id:
            scope = await self.get_scope(db, organization_id=organization_id, scope_id=scope_id)
            if scope is None:
                raise GovernanceError("Scope not found")
        role_codes = await permission_service.role_permission_codes(db, role_id)
        actor_codes = await self.effective_permission_codes(
            db, organization_id=organization_id, user_id=actor_user_id, scope_id=scope_id
        )
        missing = role_codes - actor_codes
        if missing:
            raise GovernanceError(
                f"You cannot assign this role: you do not hold {sorted(missing)[0]} at that scope"
            )
        assignment = UserRoleModel(
            user_id=user_id,
            role_id=role_id,
            organization_id=organization_id,
            scope_id=scope_id,
        )
        db.add(assignment)
        await db.flush()
        return assignment

    async def remove_assignment(
        self, db: AsyncSession, *, organization_id: str, assignment_id: str
    ) -> UserRoleModel:
        assignment = await db.get(UserRoleModel, assignment_id)
        if assignment is None or assignment.organization_id != organization_id:
            raise GovernanceError("Assignment not found")
        await db.delete(assignment)
        await db.flush()
        return assignment

    # --------------------------------------------------------- delegations
    async def list_delegations(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        granted_to: Optional[str] = None,
        granted_by: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[AccessGrant]:
        stmt = select(AccessGrant).where(AccessGrant.organization_id == organization_id)
        if granted_to:
            stmt = stmt.where(AccessGrant.granted_to_user == granted_to)
        if granted_by:
            stmt = stmt.where(AccessGrant.granted_by == granted_by)
        if status:
            stmt = stmt.where(AccessGrant.status == status)
        rows = await db.execute(stmt.order_by(AccessGrant.created_at.desc()).limit(500))
        return list(rows.scalars().all())

    async def create_delegation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        actor_user_id: str,
        granted_to_user: str,
        permission_code: str,
        scope_id: Optional[str] = None,
        reason: Optional[str] = None,
        starts_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ) -> AccessGrant:
        """Delegate a permission the actor holds to another member.

        Bounded and targeted: one grant row, one notification (the delegate).
        """
        from app.models.user import User

        if granted_to_user == actor_user_id:
            raise GovernanceError("You cannot delegate authority to yourself")
        target = await db.get(User, granted_to_user)
        if target is None or target.organization_id != organization_id:
            raise GovernanceError("Delegate user not found")
        if scope_id:
            scope = await self.get_scope(db, organization_id=organization_id, scope_id=scope_id)
            if scope is None:
                raise GovernanceError("Scope not found")
        if not await self.has_permission(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            permission_code=permission_code,
            scope_id=scope_id,
        ):
            raise GovernanceError("You cannot delegate a permission you do not hold")
        if starts_at and expires_at and starts_at >= expires_at:
            raise GovernanceError("expires_at must be after starts_at")
        grant = AccessGrant(
            organization_id=organization_id,
            granted_by=actor_user_id,
            granted_to_user=granted_to_user,
            permission_code=permission_code,
            resource_type="scope" if scope_id else None,
            resource_id=scope_id,
            reason=reason,
            starts_at=starts_at,
            expires_at=expires_at,
            status="active",
        )
        db.add(grant)
        await db.flush()
        return grant

    async def revoke_delegation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        grant_id: str,
        actor_user_id: str,
    ) -> AccessGrant:
        from app.services.permission_service import permission_service

        grant = await db.get(AccessGrant, grant_id)
        if grant is None or grant.organization_id != organization_id:
            raise GovernanceError("Delegation not found")
        is_delegator = grant.granted_by == actor_user_id
        is_governor = "governance:manage" in await permission_service.user_permission_codes(
            db, actor_user_id, organization_id
        )
        if not (is_delegator or is_governor):
            raise GovernanceError("Not authorized to revoke this delegation")
        grant.status = "revoked"
        await db.flush()
        return grant

    async def expire_overdue(
        self, db: AsyncSession, *, organization_id: Optional[str] = None
    ) -> list[AccessGrant]:
        """Mark active delegations past expiry as expired (bounded sweep).

        Emits the canonical `governance.delegation.expired` event and audit
        row per grant, so the lifecycle is visible even when the sweep runs
        from a worker. Authorization never depends on this sweep — evaluation
        denies expired delegations lazily.
        """
        from app.services.audit_service import audit_service
        from app.services.event_service import event_service

        now = utcnow()
        stmt = select(AccessGrant).where(
            AccessGrant.status == "active",
            AccessGrant.expires_at.is_not(None),
            AccessGrant.expires_at < now,
        )
        if organization_id:
            stmt = stmt.where(AccessGrant.organization_id == organization_id)
        rows = await db.execute(stmt.order_by(AccessGrant.created_at.asc()).limit(SWEEP_BATCH_LIMIT))
        expired = list(rows.scalars().all())
        for grant in expired:
            grant.status = "expired"
            await event_service.emit(
                db,
                name="governance.delegation.expired",
                actor_id=None,
                organization_id=grant.organization_id,
                payload={
                    "grant_id": grant.id,
                    "granted_to_user": grant.granted_to_user,
                    "permission_code": grant.permission_code,
                },
            )
            await audit_service.log(
                db,
                organization_id=grant.organization_id,
                action="governance.delegation.expired",
                actor_id=None,
                actor_email=None,
                resource_type="delegation",
                resource_id=grant.id,
                details={
                    "granted_to_user": grant.granted_to_user,
                    "permission_code": grant.permission_code,
                },
                severity="warning",
            )
        await db.flush()
        return expired

    # ------------------------------------------------------ approval policies
    async def list_policies(self, db: AsyncSession, *, organization_id: str) -> list[ApprovalPolicy]:
        rows = await db.execute(
            select(ApprovalPolicy)
            .where(ApprovalPolicy.organization_id == organization_id)
            .order_by(ApprovalPolicy.approval_type, ApprovalPolicy.name)
        )
        return list(rows.scalars().all())

    async def create_policy(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        approval_type: str,
        required_permission: str,
        scope_id: Optional[str] = None,
        self_approval_allowed: bool = False,
        description: Optional[str] = None,
    ) -> ApprovalPolicy:
        from app.models.role import Permission

        perm = (
            await db.execute(select(Permission).where(Permission.code == required_permission).limit(1))
        ).scalar_one_or_none()
        if perm is None:
            raise GovernanceError("required_permission is not in the permission catalog")
        if scope_id:
            scope = await self.get_scope(db, organization_id=organization_id, scope_id=scope_id)
            if scope is None:
                raise GovernanceError("Scope not found")
        policy = ApprovalPolicy(
            organization_id=organization_id,
            name=name,
            approval_type=approval_type,
            description=description,
            required_permission=required_permission,
            scope_id=scope_id,
            self_approval_allowed=self_approval_allowed,
            is_active=True,
        )
        db.add(policy)
        await db.flush()
        return policy

    async def update_policy(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        policy_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        required_permission: Optional[str] = None,
        scope_id: Optional[str] = None,
        self_approval_allowed: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> ApprovalPolicy:
        policy = await db.get(ApprovalPolicy, policy_id)
        if policy is None or policy.organization_id != organization_id:
            raise GovernanceError("Policy not found")
        if name is not None:
            policy.name = name
        if description is not None:
            policy.description = description
        if required_permission is not None:
            from app.models.role import Permission

            perm = (
                await db.execute(select(Permission).where(Permission.code == required_permission).limit(1))
            ).scalar_one_or_none()
            if perm is None:
                raise GovernanceError("required_permission is not in the permission catalog")
            policy.required_permission = required_permission
        if scope_id is not None:
            if scope_id:
                scope = await self.get_scope(db, organization_id=organization_id, scope_id=scope_id)
                if scope is None:
                    raise GovernanceError("Scope not found")
            policy.scope_id = scope_id
        if self_approval_allowed is not None:
            policy.self_approval_allowed = self_approval_allowed
        if is_active is not None:
            policy.is_active = is_active
        await db.flush()
        return policy


governance_service = GovernanceService()
