"""Feature Flags Tests — Gate 19

Tests for feature flag models, service, and API.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.models.feature_flags import (
    FeatureFlag,
    FeatureFlagEvaluation,
    FeatureFlagAuditLog,
    FeatureFlagHistory,
    FeatureFlagStatus,
    RolloutStrategy,
    FeatureFlagScope,
    VALID_STATUS_TRANSITIONS,
)
from app.services.feature_flags_service import (
    FeatureFlagService,
    FeatureFlagValidationError,
    FeatureFlagConflictError,
    FeatureFlagNotFoundError,
    FeatureFlagGovernanceError,
    FeatureFlagTenantIsolationError,
    EvaluationResult,
    FEATURE_FLAG_PERMISSIONS,
    get_feature_flag_service,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.role import Permission, Role, RolePermission, UserRole


@pytest.fixture
async def test_org(db_session: AsyncSession) -> Organization:
    """Create a test organization."""
    org = Organization(
        id=f"org-{uuid4().hex[:12]}",
        name="Test Organization",
        slug="test-org",
    )
    db_session.add(org)
    await db_session.flush()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def test_user(db_session: AsyncSession, test_org: Organization) -> User:
    """Create a test user with admin permissions."""
    user = User(
        id=f"usr-{uuid4().hex[:12]}",
        organization_id=test_org.id,
        email="test@example.com",
        full_name="Test User",
        password_hash="hashed",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    
    # Create permission and role for feature flag management
    perm_codes = [
        "feature_flags:create",
        "feature_flags:read",
        "feature_flags:update",
        "feature_flags:delete",
        "feature_flags:evaluate",
        "feature_flags:lifecycle",
        "feature_flags:rollout",
        "feature_flags:dependencies",
        "feature_flags:emergency",
        "feature_flags:analytics",
        "feature_flags:audit",
        "feature_flags:governance_override",
    ]
    
    for code in perm_codes:
        perm = Permission(
            id=f"perm-{uuid4().hex[:10]}",
            code=code,
            name=code.replace(":", " ").title(),
            resource="feature_flags",
            action=code.split(":")[1],
        )
        db_session.add(perm)
    
    await db_session.flush()
    
    # Create role with all permissions
    role = Role(
        id=f"role-{uuid4().hex[:10]}",
        organization_id=test_org.id,
        name="Feature Flag Admin",
        code="feature_flag_admin",
        is_system=True,
    )
    db_session.add(role)
    await db_session.flush()
    
    # Link permissions to role
    perms = await db_session.execute(
        select(Permission).where(Permission.code.in_(perm_codes))
    )
    for perm in perms.scalars().all():
        rp = RolePermission(role_id=role.id, permission_id=perm.id)
        db_session.add(rp)
    
    # Assign role to user
    ur = UserRole(user_id=user.id, role_id=role.id, organization_id=test_org.id)
    db_session.add(ur)
    
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def feature_flag_service(db_session: AsyncSession) -> FeatureFlagService:
    """Get feature flag service."""
    return await get_feature_flag_service(db_session)


class TestFeatureFlagModel:
    """Tests for FeatureFlag model."""
    
    async def test_create_feature_flag(self, db_session: AsyncSession, test_org: Organization):
        """Test creating a feature flag."""
        flag = FeatureFlag(
            organization_id=test_org.id,
            key="test_flag",
            name="Test Flag",
            description="A test feature flag",
            status="enabled",
            rollout_strategy="percentage",
            rollout_config={"percentage": 50.0},
            scope="tenant",
            depends_on=[],
            conflicts_with=[],
            tags=["test"],
            metadata_json={"env": "test"},
        )
        db_session.add(flag)
        await db_session.flush()
        await db_session.refresh(flag)
        
        assert flag.id.startswith("ff-")
        assert flag.key == "test_flag"
        assert flag.status == "enabled"
        assert flag.rollout_strategy == "percentage"
        assert flag.rollout_config == {"percentage": 50.0}
        assert flag.emergency_disabled is False
        assert flag.version == 1
    
    async def test_unique_key_per_org(self, db_session: AsyncSession, test_org: Organization):
        """Test unique constraint on organization_id + key."""
        flag1 = FeatureFlag(
            organization_id=test_org.id,
            key="duplicate_key",
            name="Flag 1",
        )
        flag2 = FeatureFlag(
            organization_id=test_org.id,
            key="duplicate_key",
            name="Flag 2",
        )
        db_session.add(flag1)
        await db_session.flush()
        
        db_session.add(flag2)
        with pytest.raises(Exception):  # IntegrityError
            await db_session.flush()
    
    async def test_evaluate_all_strategy(self, db_session: AsyncSession, test_org: Organization):
        """Test evaluation with 'all' strategy."""
        flag = FeatureFlag(
            organization_id=test_org.id,
            key="all_flag",
            name="All Flag",
            status="enabled",
            rollout_strategy="all",
        )
        db_session.add(flag)
        await db_session.flush()
        
        # Should be available for any user
        result = flag.evaluate(test_org.id, user_id="user-1")
        assert result is True
        
        result = flag.evaluate(test_org.id, user_id=None)
        assert result is True
    
    async def test_evaluate_percentage_strategy(self, db_session: AsyncSession, test_org: Organization):
        """Test evaluation with percentage strategy."""
        flag = FeatureFlag(
            organization_id=test_org.id,
            key="percent_flag",
            name="Percent Flag",
            status="enabled",
            rollout_strategy="percentage",
            rollout_config={"percentage": 50.0},
        )
        db_session.add(flag)
        await db_session.flush()
        
        # Deterministic based on user_id + flag_id
        user_id = "user-123"
        result1 = flag.evaluate(test_org.id, user_id=user_id)
        result2 = flag.evaluate(test_org.id, user_id=user_id)
        assert result1 == result2  # Deterministic
        
        # Different users get different results (probabilistically)
        results = [flag.evaluate(test_org.id, user_id=f"user-{i}") for i in range(100)]
        enabled_count = sum(1 for r in results if r)
        # Should be roughly 50% (allow some variance)
        assert 30 <= enabled_count <= 70
    
    async def test_evaluate_disabled_flag(self, db_session: AsyncSession, test_org: Organization):
        """Test evaluation when flag is disabled."""
        flag = FeatureFlag(
            organization_id=test_org.id,
            key="disabled_flag",
            name="Disabled Flag",
            status="off",
            rollout_strategy="all",
        )
        db_session.add(flag)
        await db_session.flush()
        
        result = flag.evaluate(test_org.id, user_id="user-1")
        assert result is False
    
    async def test_evaluate_deprecated_flag(self, db_session: AsyncSession, test_org: Organization):
        """Test evaluation when flag is deprecated."""
        flag = FeatureFlag(
            organization_id=test_org.id,
            key="deprecated_flag",
            name="Deprecated Flag",
            status="deprecated",
            rollout_strategy="all",
        )
        db_session.add(flag)
        await db_session.flush()
        
        result = flag.evaluate(test_org.id, user_id="user-1")
        assert result is False
    
    async def test_emergency_disabled_overrides(self, db_session: AsyncSession, test_org: Organization):
        """Test emergency disabled overrides everything."""
        flag = FeatureFlag(
            organization_id=test_org.id,
            key="emergency_flag",
            name="Emergency Flag",
            status="enabled",
            rollout_strategy="all",
            emergency_disabled=True,
        )
        db_session.add(flag)
        await db_session.flush()
        
        result = flag.evaluate(test_org.id, user_id="user-1")
        assert result is False
    
    async def test_valid_status_transitions(self):
        """Test valid status transitions."""
        assert "enabled" in VALID_STATUS_TRANSITIONS["off"]
        assert "beta" in VALID_STATUS_TRANSITIONS["off"]
        assert "archived" in VALID_STATUS_TRANSITIONS["off"]
        assert "enabled" in VALID_STATUS_TRANSITIONS["beta"]
        assert "off" in VALID_STATUS_TRANSITIONS["beta"]
        assert "archived" in VALID_STATUS_TRANSITIONS["deprecated"]
        assert "off" in VALID_STATUS_TRANSITIONS["deprecated"]
        assert VALID_STATUS_TRANSITIONS["archived"] == []


class TestFeatureFlagService:
    """Tests for FeatureFlagService."""
    
    async def test_create_flag(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test creating a feature flag via service."""
        flag = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="service_flag",
            name="Service Flag",
            actor_id=test_user.id,
            description="Created via service",
            status="enabled",
            rollout_strategy="percentage",
            rollout_config={"percentage": 25.0},
        )
        
        assert flag.id.startswith("ff-")
        assert flag.key == "service_flag"
        assert flag.status == "enabled"
        assert flag.rollout_config == {"percentage": 25.0}
        assert flag.enabled_at is not None
        assert flag.version == 1
    
    async def test_create_flag_duplicate_key(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test creating duplicate key raises error."""
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="unique_key",
            name="First Flag",
            actor_id=test_user.id,
        )
        
        with pytest.raises(FeatureFlagValidationError) as exc:
            await feature_flag_service.create_flag(
                organization_id=test_org.id,
                key="unique_key",
                name="Second Flag",
                actor_id=test_user.id,
            )
        assert "already exists" in str(exc.value)
    
    async def test_create_flag_invalid_dependency(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test creating flag with non-existent dependency."""
        with pytest.raises(FeatureFlagValidationError) as exc:
            await feature_flag_service.create_flag(
                organization_id=test_org.id,
                key="flag_with_dep",
                name="Flag With Dependency",
                actor_id=test_user.id,
                depends_on=["nonexistent_flag"],
            )
        assert "does not exist" in str(exc.value)
    
    async def test_create_flag_circular_dependency(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test circular dependency detection."""
        # Create flag A
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="flag_a",
            name="Flag A",
            actor_id=test_user.id,
        )
        
        # Create flag B depending on A
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="flag_b",
            name="Flag B",
            actor_id=test_user.id,
            depends_on=["flag_a"],
        )
        
        # Try to update A to depend on B (circular)
        with pytest.raises(FeatureFlagConflictError) as exc:
            await feature_flag_service.update_flag(
                organization_id=test_org.id,
                flag_id=(await feature_flag_service.get_flag_by_key(test_org.id, "flag_a")).id,
                actor_id=test_user.id,
                depends_on=["flag_b"],
            )
        assert "Circular dependency" in str(exc.value)
    
    async def test_get_flag(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test getting a flag by ID."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="get_flag",
            name="Get Flag",
            actor_id=test_user.id,
        )
        
        retrieved = await feature_flag_service.get_flag(test_org.id, created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.key == "get_flag"
        
        # Non-existent
        retrieved = await feature_flag_service.get_flag(test_org.id, "nonexistent")
        assert retrieved is None
    
    async def test_get_flag_by_key(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test getting a flag by key."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="by_key_flag",
            name="By Key Flag",
            actor_id=test_user.id,
        )
        
        retrieved = await feature_flag_service.get_flag_by_key(test_org.id, "by_key_flag")
        assert retrieved is not None
        assert retrieved.key == "by_key_flag"
        
        retrieved = await feature_flag_service.get_flag_by_key(test_org.id, "nonexistent")
        assert retrieved is None
    
    async def test_list_flags(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test listing flags with filters."""
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="flag_enabled",
            name="Enabled Flag",
            actor_id=test_user.id,
            status="enabled",
            tags=["prod"],
        )
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="flag_disabled",
            name="Disabled Flag",
            actor_id=test_user.id,
            status="off",
            tags=["dev"],
        )
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="flag_beta",
            name="Beta Flag",
            actor_id=test_user.id,
            status="beta",
            tags=["prod"],
        )
        
        # All flags
        all_flags = await feature_flag_service.list_flags(test_org.id, test_user.id)
        assert len(all_flags) == 3
        
        # Filter by status
        enabled = await feature_flag_service.list_flags(test_org.id, test_user.id, status="enabled")
        assert len(enabled) == 1
        assert enabled[0].key == "flag_enabled"
        
        # Filter by tags
        prod = await feature_flag_service.list_flags(test_org.id, test_user.id, tags=["prod"])
        assert len(prod) == 2
    
    async def test_update_flag(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test updating a flag."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="update_flag",
            name="Update Flag",
            actor_id=test_user.id,
            status="off",
        )
        
        original_version = created.version
        
        updated = await feature_flag_service.update_flag(
            organization_id=test_org.id,
            flag_id=created.id,
            actor_id=test_user.id,
            name="Updated Name",
            status="enabled",
            version=original_version,
        )
        
        assert updated.name == "Updated Name"
        assert updated.status == "enabled"
        assert updated.enabled_at is not None
        assert updated.version == original_version + 1
    
    async def test_update_flag_optimistic_concurrency(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test optimistic concurrency control."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="concurrency_flag",
            name="Concurrency Flag",
            actor_id=test_user.id,
        )
        
        original_version = created.version
        
        # Update with correct version
        await feature_flag_service.update_flag(
            organization_id=test_org.id,
            flag_id=created.id,
            actor_id=test_user.id,
            name="First Update",
            version=original_version,
        )
        
        # Update with stale version should fail
        with pytest.raises(FeatureFlagValidationError) as exc:
            await feature_flag_service.update_flag(
                organization_id=test_org.id,
                flag_id=created.id,
                actor_id=test_user.id,
                name="Stale Update",
                version=original_version,  # Old version
            )
        assert "modified by another process" in str(exc.value)
    
    async def test_update_flag_invalid_transition(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test invalid status transition."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="transition_flag",
            name="Transition Flag",
            actor_id=test_user.id,
            status="archived",  # Terminal state
        )
        
        with pytest.raises(FeatureFlagValidationError) as exc:
            await feature_flag_service.update_flag(
                organization_id=test_org.id,
                flag_id=created.id,
                actor_id=test_user.id,
                status="enabled",
                version=created.version,
            )
        assert "Invalid status transition" in str(exc.value)
    
    async def test_delete_flag(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test deleting a flag."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="delete_flag",
            name="Delete Flag",
            actor_id=test_user.id,
        )
        
        result = await feature_flag_service.delete_flag(test_org.id, created.id, test_user.id)
        assert result is True
        
        # Verify deleted
        retrieved = await feature_flag_service.get_flag(test_org.id, created.id)
        assert retrieved is None
    
    async def test_delete_flag_with_dependents(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test deleting flag that has dependents."""
        # Create flag A
        flag_a = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="flag_a",
            name="Flag A",
            actor_id=test_user.id,
        )
        
        # Create flag B depending on A
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="flag_b",
            name="Flag B",
            actor_id=test_user.id,
            depends_on=["flag_a"],
        )
        
        # Try to delete A - should fail
        with pytest.raises(FeatureFlagConflictError) as exc:
            await feature_flag_service.delete_flag(test_org.id, flag_a.id, test_user.id)
        assert "depend on" in str(exc.value)
    
    async def test_evaluate_flag(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test evaluating a flag."""
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="eval_flag",
            name="Eval Flag",
            actor_id=test_user.id,
            status="enabled",
            rollout_strategy="percentage",
            rollout_config={"percentage": 100.0},
        )
        
        result = await feature_flag_service.evaluate_flag(
            organization_id=test_org.id,
            key="eval_flag",
            user_id="user-1",
        )
        
        assert result.flag_key == "eval_flag"
        assert result.available is True
        assert result.reason == "rollout_percentage_included"
        assert result.flag_version == 1
    
    async def test_evaluate_nonexistent_flag(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test evaluating non-existent flag."""
        result = await feature_flag_service.evaluate_flag(
            organization_id=test_org.id,
            key="nonexistent",
            user_id="user-1",
        )
        
        assert result.available is False
        assert result.reason == "flag_not_found"
        assert result.flag_id == ""
    
    async def test_evaluate_multiple(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test evaluating multiple flags."""
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="multi_1",
            name="Multi 1",
            actor_id=test_user.id,
            status="enabled",
        )
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="multi_2",
            name="Multi 2",
            actor_id=test_user.id,
            status="off",
        )
        
        results = await feature_flag_service.evaluate_multiple(
            organization_id=test_org.id,
            keys=["multi_1", "multi_2", "nonexistent"],
            user_id="user-1",
        )
        
        assert results["multi_1"].available is True
        assert results["multi_2"].available is False
        assert results["nonexistent"].available is False
    
    async def test_status_transitions(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test status transition helpers."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="transition_flag",
            name="Transition Flag",
            actor_id=test_user.id,
            status="off",
        )
        
        # Enable
        flag = await feature_flag_service.enable_flag(test_org.id, created.id, test_user.id, version=created.version)
        assert flag.status == "enabled"
        assert flag.enabled_at is not None
        
        # Disable
        flag = await feature_flag_service.disable_flag(test_org.id, flag.id, test_user.id, version=flag.version)
        assert flag.status == "off"
        
        # Deprecate
        flag = await feature_flag_service.deprecate_flag(
            test_org.id, flag.id, test_user.id, "No longer needed", version=flag.version
        )
        assert flag.status == "deprecated"
        assert flag.deprecated_at is not None
        assert flag.deprecated_reason == "No longer needed"
        
        # Archive
        flag = await feature_flag_service.archive_flag(test_org.id, flag.id, test_user.id, version=flag.version)
        assert flag.status == "archived"
        assert flag.archived_at is not None
    
    async def test_set_percentage_rollout(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test setting percentage rollout."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="rollout_flag",
            name="Rollout Flag",
            actor_id=test_user.id,
            status="enabled",
        )
        
        flag = await feature_flag_service.set_percentage_rollout(
            test_org.id, created.id, test_user.id, 75.0, version=created.version
        )
        
        assert flag.rollout_strategy == "percentage"
        assert flag.rollout_config == {"percentage": 75.0}
    
    async def test_set_invalid_percentage(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test setting invalid percentage."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="invalid_pct",
            name="Invalid Percentage",
            actor_id=test_user.id,
            status="enabled",
        )
        
        with pytest.raises(FeatureFlagValidationError) as exc:
            await feature_flag_service.set_percentage_rollout(
                test_org.id, created.id, test_user.id, 150.0, version=created.version
            )
        assert "between 0 and 100" in str(exc.value)
    
    async def test_set_ring_rollout(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test setting ring rollout."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="ring_flag",
            name="Ring Flag",
            actor_id=test_user.id,
            status="enabled",
        )
        
        flag = await feature_flag_service.set_ring_rollout(
            test_org.id, created.id, test_user.id, ["canary", "early"], version=created.version
        )
        
        assert flag.rollout_strategy == "ring"
        assert flag.rollout_config == {"rings": ["canary", "early"]}
    
    async def test_set_invalid_ring(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test setting invalid ring."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="invalid_ring",
            name="Invalid Ring",
            actor_id=test_user.id,
            status="enabled",
        )
        
        with pytest.raises(FeatureFlagValidationError) as exc:
            await feature_flag_service.set_ring_rollout(
                test_org.id, created.id, test_user.id, ["invalid_ring"], version=created.version
            )
        assert "Invalid ring" in str(exc.value)
    
    async def test_emergency_disable(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test emergency disable."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="emergency_flag",
            name="Emergency Flag",
            actor_id=test_user.id,
            status="enabled",
        )
        
        flag = await feature_flag_service.emergency_disable(
            test_org.id, created.id, test_user.id, "Production incident"
        )
        
        assert flag.emergency_disabled is True
        assert flag.emergency_disabled_by == test_user.id
        assert flag.emergency_disabled_reason == "Production incident"
        
        # Evaluation should return False
        result = await feature_flag_service.evaluate_flag(test_org.id, "emergency_flag", "user-1")
        assert result.available is False
        assert result.reason == "emergency_disabled"
    
    async def test_emergency_enable(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test emergency enable after disable."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="emergency_flag2",
            name="Emergency Flag 2",
            actor_id=test_user.id,
            status="enabled",
        )
        
        await feature_flag_service.emergency_disable(
            test_org.id, created.id, test_user.id, "Production incident"
        )
        
        flag = await feature_flag_service.emergency_enable(
            test_org.id, created.id, test_user.id, "Incident resolved"
        )
        
        assert flag.emergency_disabled is False
        assert flag.emergency_disabled_reason is None
        
        # Evaluation should work again
        result = await feature_flag_service.evaluate_flag(test_org.id, "emergency_flag2", "user-1")
        assert result.available is True
    
    async def test_get_evaluation_stats(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test getting evaluation statistics."""
        flag = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="stats_flag",
            name="Stats Flag",
            actor_id=test_user.id,
            status="enabled",
        )
        
        # Evaluate a few times
        for i in range(5):
            await feature_flag_service.evaluate_flag(
                organization_id=test_org.id,
                key="stats_flag",
                user_id=f"user-{i}",
            )
        
        stats = await feature_flag_service.get_evaluation_stats(test_org.id, test_user.id, flag.id, days=30)
        
        assert stats["total_evaluations"] == 5
        assert stats["available_evaluations"] == 5
        assert stats["unavailable_evaluations"] == 0
        assert stats["unique_users"] == 5
        assert stats["availability_rate"] == 1.0
    
    async def test_get_flag_health(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test getting flag health."""
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="healthy_flag",
            name="Healthy Flag",
            actor_id=test_user.id,
            status="enabled",
        )
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="deprecated_flag",
            name="Deprecated Flag",
            actor_id=test_user.id,
            status="deprecated",
        )
        
        health = await feature_flag_service.get_flag_health(test_org.id, test_user.id)
        
        assert health["total_flags"] == 2
        assert health["by_status"]["enabled"] == 1
        assert health["by_status"]["deprecated"] == 1
        assert health["deprecated_count"] == 1
        assert 0 <= health["health_score"] <= 100
    
    async def test_audit_log(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test audit log recording."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="audit_flag",
            name="Audit Flag",
            actor_id=test_user.id,
            status="enabled",
        )
        
        await feature_flag_service.update_flag(
            organization_id=test_org.id,
            flag_id=created.id,
            actor_id=test_user.id,
            name="Updated Name",
            version=created.version,
        )
        
        audit_logs = await feature_flag_service.get_audit_log(test_org.id, test_user.id, flag_id=created.id)
        
        assert len(audit_logs) >= 2  # create + update
        assert any(a.action == "create" for a in audit_logs)
        assert any(a.action == "update" for a in audit_logs)
    
    async def test_history_snapshots(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test historical configuration snapshots."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="history_flag",
            name="History Flag",
            actor_id=test_user.id,
            status="off",
        )
        
        await feature_flag_service.enable_flag(test_org.id, created.id, test_user.id, version=created.version)
        
        history = await feature_flag_service.get_history(test_org.id, test_user.id, created.id)
        
        assert len(history) >= 2  # create + enable
        # Check snapshot versions increment
        versions = [h.snapshot_version for h in history]
        assert max(versions) >= 2
    
    async def test_longitudinal_query(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test longitudinal query - get configuration at point in time."""
        from datetime import datetime, timezone, timedelta
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="longitudinal_flag",
            name="Longitudinal Flag",
            actor_id=test_user.id,
            status="off",
        )
        
        # Wait a moment
        await asyncio.sleep(0.1)
        
        mid_time = datetime.now(timezone.utc)
        
        await feature_flag_service.enable_flag(test_org.id, created.id, test_user.id, version=created.version)
        
        # Query configuration at mid_time (should be 'off')
        config_at_mid = await feature_flag_service.get_configuration_at(
            test_org.id, test_user.id, created.id, mid_time
        )
        
        assert config_at_mid is not None
        assert config_at_mid.status == "off"
    
    async def test_private_alpha_promotion(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test private alpha promotion flow."""
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="alpha_flag",
            name="Alpha Flag",
            actor_id=test_user.id,
            status="off",
        )
        
        # Promote to alpha
        flag = await feature_flag_service.promote_to_alpha(
            test_org.id, created.id, test_user.id, ring="canary", percentage=10.0
        )
        
        assert flag.status == "alpha"
        assert flag.rollout_strategy == "ring"
        assert flag.rollout_config == {"rings": ["canary"], "percentage": 10.0}
        assert "private_alpha" in flag.tags
        
        # Promote to beta
        flag = await feature_flag_service.promote_alpha_to_beta(
            test_org.id, flag.id, test_user.id, percentage=50.0
        )
        
        assert flag.status == "beta"
        assert flag.rollout_strategy == "percentage"
        assert flag.rollout_config == {"percentage": 50.0}
        assert "private_alpha" not in flag.tags
        
        # Promote to enabled
        flag = await feature_flag_service.promote_beta_to_enabled(test_org.id, flag.id, test_user.id)
        
        assert flag.status == "enabled"
        assert flag.rollout_strategy == "all"
    
    async def test_entitlement_check(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test entitlement check for feature."""
        entitlement = await feature_flag_service.get_feature_entitlement(test_org.id, "some_feature")
        
        assert "entitled" in entitlement
        assert "source" in entitlement
    
    async def test_evaluate_with_authorization(self, feature_flag_service: FeatureFlagService, test_org: Organization, test_user: User):
        """Test combined feature availability + authorization evaluation."""
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="auth_flag",
            name="Auth Flag",
            actor_id=test_user.id,
            status="enabled",
            rollout_strategy="all",
        )
        
        allowed, reason = await feature_flag_service.evaluate_with_authorization(
            organization_id=test_org.id,
            key="auth_flag",
            user_id=test_user.id,
            required_permission="some:permission",
        )
        
        # User has all feature flag permissions but not "some:permission"
        assert allowed is False
        assert "unauthorized" in reason


class TestFeatureFlagAPI:
    """Tests for Feature Flags API endpoints."""
    
    async def test_create_flag_api(self, client, test_org: Organization, test_user: User):
        """Test POST /api/v1/feature-flags"""
        # Need to authenticate as test_user
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = await client.post(
            "/api/v1/feature-flags",
            json={
                "key": "api_flag",
                "name": "API Flag",
                "description": "Created via API",
                "status": "enabled",
                "rollout_strategy": "percentage",
                "rollout_config": {"percentage": 50},
            },
            headers=headers,
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["key"] == "api_flag"
        assert data["status"] == "enabled"
        assert data["rollout_config"] == {"percentage": 50}
        assert data["emergency_disabled"] is False
        assert data["version"] == 1
    
    async def test_list_flags_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test GET /api/v1/feature-flags"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="list_flag_1",
            name="List Flag 1",
            actor_id=test_user.id,
            status="enabled",
        )
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="list_flag_2",
            name="List Flag 2",
            actor_id=test_user.id,
            status="off",
        )
        
        response = await client.get(
            "/api/v1/feature-flags",
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
    
    async def test_get_flag_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test GET /api/v1/feature-flags/{flag_id}"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="get_api_flag",
            name="Get API Flag",
            actor_id=test_user.id,
        )
        
        response = await client.get(
            f"/api/v1/feature-flags/{created.id}",
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == created.id
        assert data["key"] == "get_api_flag"
    
    async def test_get_flag_by_key_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test GET /api/v1/feature-flags/by-key/{key}"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="by_key_api",
            name="By Key API",
            actor_id=test_user.id,
        )
        
        response = await client.get(
            "/api/v1/feature-flags/by-key/by_key_api",
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "by_key_api"
    
    async def test_update_flag_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test PATCH /api/v1/feature-flags/{flag_id}"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="update_api",
            name="Update API",
            actor_id=test_user.id,
            status="off",
        )
        
        response = await client.patch(
            f"/api/v1/feature-flags/{created.id}",
            json={
                "name": "Updated via API",
                "status": "enabled",
                "version": created.version,
            },
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated via API"
        assert data["status"] == "enabled"
        assert data["version"] == created.version + 1
    
    async def test_delete_flag_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test DELETE /api/v1/feature-flags/{flag_id}"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="delete_api",
            name="Delete API",
            actor_id=test_user.id,
        )
        
        response = await client.delete(
            f"/api/v1/feature-flags/{created.id}",
            headers=headers,
        )
        
        assert response.status_code == 204
        
        # Verify deleted
        response = await client.get(
            f"/api/v1/feature-flags/{created.id}",
            headers=headers,
        )
        assert response.status_code == 404
    
    async def test_evaluate_flag_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test POST /api/v1/feature-flags/evaluate"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="eval_api",
            name="Eval API",
            actor_id=test_user.id,
            status="enabled",
            rollout_strategy="all",
        )
        
        response = await client.post(
            "/api/v1/feature-flags/evaluate",
            json={
                "key": "eval_api",
                "user_id": "user-1",
                "context": {"env": "test"},
            },
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["flag_key"] == "eval_api"
        assert data["available"] is True
        assert data["context"] == {"env": "test"}
        assert "flag_version" in data
    
    async def test_evaluate_batch_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test POST /api/v1/feature-flags/evaluate-batch"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="batch_1",
            name="Batch 1",
            actor_id=test_user.id,
            status="enabled",
        )
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="batch_2",
            name="Batch 2",
            actor_id=test_user.id,
            status="off",
        )
        
        response = await client.post(
            "/api/v1/feature-flags/evaluate-batch",
            json={
                "keys": ["batch_1", "batch_2", "nonexistent"],
                "user_id": "user-1",
            },
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["batch_1"]["available"] is True
        assert data["batch_2"]["available"] is False
        assert data["nonexistent"]["available"] is False
    
    async def test_evaluate_with_auth_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test POST /api/v1/feature-flags/evaluate-with-auth"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="auth_api_flag",
            name="Auth API Flag",
            actor_id=test_user.id,
            status="enabled",
            rollout_strategy="all",
        )
        
        response = await client.post(
            "/api/v1/feature-flags/evaluate-with-auth",
            json={
                "key": "auth_api_flag",
                "user_id": test_user.id,
                "required_permission": "nonexistent:permission",
            },
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is False
        assert data["feature_available"] is True
        assert data["authorized"] is False
        assert "unauthorized" in data["reason"]
    
    async def test_enable_disable_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test POST /enable and /disable"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="enable_api",
            name="Enable API",
            actor_id=test_user.id,
            status="off",
        )
        
        # Enable
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/enable",
            params={"version": created.version},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "enabled"
        
        # Disable
        flag = response.json()
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/disable",
            params={"version": flag["version"]},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "off"
    
    async def test_deprecate_archive_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test POST /deprecate and /archive"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="deprecate_api",
            name="Deprecate API",
            actor_id=test_user.id,
            status="enabled",
        )
        
        # Deprecate
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/deprecate",
            json={"reason": "Replaced by new feature", "version": created.version},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deprecated"
        
        # Archive
        flag = response.json()
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/archive",
            json={"version": flag["version"]},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "archived"
    
    async def test_emergency_disable_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test POST /emergency-disable"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="emergency_api",
            name="Emergency API",
            actor_id=test_user.id,
            status="enabled",
        )
        
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/emergency-disable",
            json={"reason": "Critical production issue"},
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["emergency_disabled"] is True
        assert data["emergency_disabled_reason"] == "Critical production issue"
        
        # Evaluate should return unavailable
        eval_response = await client.post(
            "/api/v1/feature-flags/evaluate",
            json={"key": "emergency_api", "user_id": "user-1"},
            headers=headers,
        )
        assert eval_response.status_code == 200
        assert eval_response.json()["available"] is False
        assert eval_response.json()["reason"] == "emergency_disabled"
    
    async def test_emergency_enable_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test POST /emergency-enable"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="emergency_api2",
            name="Emergency API 2",
            actor_id=test_user.id,
            status="enabled",
        )
        
        # Disable first
        await client.post(
            f"/api/v1/feature-flags/{created.id}/emergency-disable",
            json={"reason": "Critical production issue"},
            headers=headers,
        )
        
        # Enable
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/emergency-enable",
            json={"reason": "Issue resolved"},
            headers=headers,
        )
        
        assert response.status_code == 200
        assert response.json()["emergency_disabled"] is False
    
    async def test_rollout_percentage_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test POST /rollout/percentage"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="pct_api",
            name="Percentage API",
            actor_id=test_user.id,
            status="enabled",
        )
        
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/rollout/percentage",
            json={"percentage": 25.0, "version": created.version},
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["rollout_strategy"] == "percentage"
        assert data["rollout_config"] == {"percentage": 25.0}
    
    async def test_rollout_rings_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test POST /rollout/rings"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="rings_api",
            name="Rings API",
            actor_id=test_user.id,
            status="enabled",
        )
        
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/rollout/rings",
            json={"rings": ["canary", "early"], "version": created.version},
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["rollout_strategy"] == "ring"
        assert data["rollout_config"] == {"rings": ["canary", "early"]}
    
    async def test_rollout_custom_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test POST /rollout/custom"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="custom_api",
            name="Custom API",
            actor_id=test_user.id,
            status="enabled",
        )
        
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/rollout/custom",
            json={
                "custom_rules": [
                    {"type": "role", "values": ["admin"], "operator": "any"}
                ],
                "version": created.version
            },
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["rollout_strategy"] == "custom"
        assert "custom_rules" in data["rollout_config"]
    
    async def test_private_alpha_promotion_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test private alpha promotion endpoints"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="alpha_api",
            name="Alpha API",
            actor_id=test_user.id,
            status="off",
        )
        
        # Promote to alpha
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/promote-to-alpha",
            json={"ring": "canary", "percentage": 10.0},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "alpha"
        
        # Promote to beta
        flag = response.json()
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/promote-alpha-to-beta",
            json={"percentage": 50.0, "version": flag["version"]},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "beta"
        
        # Promote to enabled
        flag = response.json()
        response = await client.post(
            f"/api/v1/feature-flags/{created.id}/promote-beta-to-enabled",
            json={"version": flag["version"]},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "enabled"
    
    async def test_stats_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test GET /stats"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="stats_api",
            name="Stats API",
            actor_id=test_user.id,
            status="enabled",
        )
        
        # Evaluate
        await feature_flag_service.evaluate_flag(test_org.id, "stats_api", "user-1")
        
        response = await client.get(
            f"/api/v1/feature-flags/{created.id}/stats",
            params={"days": 30},
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_evaluations"] >= 1
    
    async def test_health_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test GET /health/overview"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="health_1",
            name="Health 1",
            actor_id=test_user.id,
            status="enabled",
        )
        await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="health_2",
            name="Health 2",
            actor_id=test_user.id,
            status="deprecated",
        )
        
        response = await client.get(
            "/api/v1/feature-flags/health/overview",
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_flags"] >= 2
        assert "by_status" in data
        assert "health_score" in data
        assert 0 <= data["health_score"] <= 100
    
    async def test_audit_log_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test GET /audit"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="audit_api",
            name="Audit API",
            actor_id=test_user.id,
            status="enabled",
        )
        
        response = await client.get(
            f"/api/v1/feature-flags/{created.id}/audit",
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["action"] == "create"
        assert data[0]["feature_flag_id"] == created.id
    
    async def test_history_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test GET /history"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="history_api",
            name="History API",
            actor_id=test_user.id,
            status="off",
        )
        
        await feature_flag_service.enable_flag(test_org.id, created.id, test_user.id, version=created.version)
        
        response = await client.get(
            f"/api/v1/feature-flags/{created.id}/history",
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        assert any(h["action"] == "create" for h in data)
        assert any(h["action"] == "update" for h in data)
    
    async def test_configuration_at_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test GET /configuration-at"""
        from app.core.security import create_access_token
        from datetime import datetime, timezone
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="config_at_api",
            name="Config At API",
            actor_id=test_user.id,
            status="off",
        )
        
        at_time = datetime.now(timezone.utc).isoformat()
        
        await feature_flag_service.enable_flag(test_org.id, created.id, test_user.id, version=created.version)
        
        response = await client.get(
            f"/api/v1/feature-flags/{created.id}/configuration-at",
            params={"at": at_time},
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "off"  # Was 'off' at the recorded time
    
    async def test_timeline_api(self, client, test_org: Organization, test_user: User, feature_flag_service):
        """Test GET /timeline"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        created = await feature_flag_service.create_flag(
            organization_id=test_org.id,
            key="timeline_api",
            name="Timeline API",
            actor_id=test_user.id,
            status="off",
        )
        
        await feature_flag_service.enable_flag(test_org.id, created.id, test_user.id, version=created.version)
        
        response = await client.get(
            f"/api/v1/feature-flags/{created.id}/timeline",
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["flag_id"] == created.id
        assert data["flag_key"] == "timeline_api"
        assert len(data["timeline"]) >= 2
    
    async def test_entitlement_api(self, client, test_org: Organization, test_user: User):
        """Test GET /entitlement"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = await client.get(
            "/api/v1/feature-flags/some_feature/entitlement",
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "entitled" in data
        assert "source" in data
    
    async def test_private_alpha_config_api(self, client, test_org: Organization, test_user: User):
        """Test GET /private-alpha/config"""
        from app.core.security import create_access_token
        access_token = create_access_token(test_user.id, test_org.id)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = await client.get(
            "/api/v1/feature-flags/private-alpha/config",
            headers=headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "entitled" in data
        assert "flags" in data


import asyncio
from datetime import datetime, timezone