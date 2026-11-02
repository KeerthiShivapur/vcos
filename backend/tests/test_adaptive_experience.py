"""Tests for Universal Adaptive Experience Architecture."""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_experience import (
    CompanyExperienceConfig,
    CompanyExperienceProfile,
    CompanyExperienceProfileHistory,
    resolve_experience_profile,
    get_profile_capabilities,
    PROFILE_CAPABILITY_MATRIX,
)
from app.models.organization import Organization
from app.models.user import User
from app.services.company_experience_service import CompanyExperienceService, company_experience_service
from app.core.timeutils import utcnow


class TestCompanyExperienceProfile:
    """Test the CompanyExperienceProfile enum and resolution."""

    def test_profile_values(self):
        """Test that all expected profiles exist."""
        assert CompanyExperienceProfile.STARTUP == "startup"
        assert CompanyExperienceProfile.GROWING == "growing"
        assert CompanyExperienceProfile.MID_MARKET == "mid_market"
        assert CompanyExperienceProfile.LARGE_ENTERPRISE == "large_enterprise"
        assert CompanyExperienceProfile.GLOBAL_ENTERPRISE == "global_enterprise"

    def test_resolve_startup_profile(self):
        """Test profile resolution for startup companies."""
        profile = resolve_experience_profile(
            employee_count=5,
            org_depth=1,
            org_unit_count=0,
            legal_entity_count=1,
            geo_count=1,
            governance_level="simple",
            workflow_complexity="simple",
        )
        assert profile == CompanyExperienceProfile.STARTUP

    def test_resolve_growing_profile(self):
        """Test profile resolution for growing companies."""
        # Need score > 30 for growing
        # employee_count=100 gives 10, depth=2 gives 10, org_units=5 gives 1, governance=standard gives 15 = 36
        profile = resolve_experience_profile(
            employee_count=100,
            org_depth=2,
            org_unit_count=5,
            legal_entity_count=1,
            geo_count=1,
            governance_level="standard",
            workflow_complexity="simple",
        )
        assert profile == CompanyExperienceProfile.GROWING

    def test_resolve_mid_market_profile(self):
        """Test profile resolution for mid-market companies."""
        profile = resolve_experience_profile(
            employee_count=200,
            org_depth=3,
            org_unit_count=10,
            legal_entity_count=1,
            geo_count=2,
            governance_level="standard",
            workflow_complexity="conditional",
        )
        assert profile == CompanyExperienceProfile.MID_MARKET

    def test_resolve_large_enterprise_profile(self):
        """Test profile resolution for large enterprises."""
        profile = resolve_experience_profile(
            employee_count=2000,
            org_depth=4,
            org_unit_count=50,
            legal_entity_count=3,
            geo_count=5,
            governance_level="delegated",
            workflow_complexity="complex",
        )
        assert profile == CompanyExperienceProfile.LARGE_ENTERPRISE

    def test_resolve_global_enterprise_profile(self):
        """Test profile resolution for global enterprises."""
        profile = resolve_experience_profile(
            employee_count=50000,
            org_depth=6,
            org_unit_count=200,
            legal_entity_count=10,
            geo_count=20,
            governance_level="federated",
            workflow_complexity="complex",
        )
        assert profile == CompanyExperienceProfile.GLOBAL_ENTERPRISE

    def test_governance_complexity_affects_profile(self):
        """Test that governance complexity can upgrade profile even for small companies."""
        # Small company with complex governance
        profile = resolve_experience_profile(
            employee_count=10,
            org_depth=1,
            org_unit_count=1,
            legal_entity_count=1,
            geo_count=1,
            governance_level="complex",
            workflow_complexity="simple",
        )
        # Should be at least growing due to governance complexity
        assert profile in [CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET]

    def test_small_company_can_have_complex_governance(self):
        """Test that a small company is not forced to have simple governance."""
        profile = resolve_experience_profile(
            employee_count=8,
            org_depth=1,
            org_unit_count=1,
            legal_entity_count=1,
            geo_count=1,
            governance_level="standard",
            workflow_complexity="conditional",
        )
        # Employee count is startup range, but governance adds points
        assert profile in [CompanyExperienceProfile.STARTUP, CompanyExperienceProfile.GROWING]


class TestProfileCapabilityMatrix:
    """Test the profile capability matrix."""

    def test_startup_capabilities(self):
        """Test startup profile capabilities."""
        caps = get_profile_capabilities(CompanyExperienceProfile.STARTUP)
        assert "modules" in caps
        assert "navigation_groups" in caps
        assert "modules_enabled_by_default" in caps
        assert "home" in caps["modules_enabled_by_default"]
        assert "workspace" in caps["modules_enabled_by_default"]
        assert "my-work" in caps["modules_enabled_by_default"]
        assert "my-day" in caps["modules_enabled_by_default"]
        assert "ai" in caps["modules_enabled_by_default"]

    def test_growing_capabilities(self):
        """Test growing profile capabilities."""
        caps = get_profile_capabilities(CompanyExperienceProfile.GROWING)
        assert "projects" in caps["modules_enabled_by_default"]
        assert "tasks" in caps["modules_enabled_by_default"]
        assert "goals" in caps["modules_enabled_by_default"]
        # departments and teams are in modules but not enabled_by_default for growing
        assert "departments" in caps["modules"]
        assert "teams" in caps["modules"]
        assert "people" in caps["modules"]

    def test_enterprise_has_all_modules(self):
        """Test that enterprise profiles have all modules."""
        for profile in [CompanyExperienceProfile.LARGE_ENTERPRISE, CompanyExperienceProfile.GLOBAL_ENTERPRISE]:
            caps = get_profile_capabilities(profile)
            assert caps["modules"] == ["all"]
            assert caps["modules_enabled_by_default"] == ["all"]

    def test_global_enterprise_has_advanced_features(self):
        """Test global enterprise has advanced features."""
        caps = get_profile_capabilities(CompanyExperienceProfile.GLOBAL_ENTERPRISE)
        assert "features" in caps
        assert "multi_entity" in caps["features"]
        assert "data_residency" in caps["features"]
        assert "sovereign_deployment" in caps["features"]


class TestCompanyExperienceConfig:
    """Test the CompanyExperienceConfig model."""

    @pytest.mark.asyncio
    async def test_create_default_config(self, db_session: AsyncSession):
        """Test creating a default experience config."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        config = CompanyExperienceConfig(organization_id=org.id)
        db_session.add(config)
        await db_session.flush()

        assert config.experience_profile == CompanyExperienceProfile.STARTUP
        assert config.progressive_disclosure is True
        assert config.show_advanced_features is False
        assert config.navigation_density == "comfortable"

    @pytest.mark.asyncio
    async def test_should_show_module_startup(self, db_session: AsyncSession):
        """Test module visibility for startup profile."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        config = CompanyExperienceConfig(
            organization_id=org.id,
            experience_profile=CompanyExperienceProfile.STARTUP,
        )
        db_session.add(config)
        await db_session.flush()

        # Startup modules should be visible
        assert config.should_show_module("home") is True
        assert config.should_show_module("workspace") is True
        assert config.should_show_module("my-work") is True
        assert config.should_show_module("my-day") is True
        assert config.should_show_module("ai") is True

        # Enterprise modules should not be visible by default
        assert config.should_show_module("finance") is False
        assert config.should_show_module("hr") is False
        assert config.should_show_module("enterprise") is False

    @pytest.mark.asyncio
    async def test_should_show_module_growing(self, db_session: AsyncSession):
        """Test module visibility for growing profile."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        config = CompanyExperienceConfig(
            organization_id=org.id,
            experience_profile=CompanyExperienceProfile.GROWING,
        )
        db_session.add(config)
        await db_session.flush()

        # Growing modules should be visible
        assert config.should_show_module("projects") is True
        assert config.should_show_module("tasks") is True
        assert config.should_show_module("goals") is True
        assert config.should_show_module("departments") is True
        assert config.should_show_module("teams") is True

    @pytest.mark.asyncio
    async def test_explicit_enabled_modules_override(self, db_session: AsyncSession):
        """Test that explicit enabled_modules overrides profile defaults."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        config = CompanyExperienceConfig(
            organization_id=org.id,
            experience_profile=CompanyExperienceProfile.STARTUP,
            enabled_modules=["home", "workspace", "finance"],  # Finance explicitly enabled
        )
        db_session.add(config)
        await db_session.flush()

        assert config.should_show_module("home") is True
        assert config.should_show_module("workspace") is True
        assert config.should_show_module("finance") is True  # Overridden
        assert config.should_show_module("hr") is False  # Not in explicit list


class TestCompanyExperienceService:
    """Test the CompanyExperienceService."""

    @pytest.mark.asyncio
    async def test_get_or_create_experience_config(self, db_session: AsyncSession):
        """Test getting or creating experience config."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        config = await company_experience_service.get_or_create_experience_config(db_session, org.id)
        assert config is not None
        assert config.organization_id == org.id
        assert config.experience_profile == CompanyExperienceProfile.STARTUP

    @pytest.mark.asyncio
    async def test_resolve_profile_for_organization(self, db_session: AsyncSession):
        """Test resolving profile for organization."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
            employee_count=100,
            organizational_depth=3,
            organizational_unit_count=10,
            legal_entity_count=2,
            geographic_footprint_count=3,
            governance_complexity="standard",
            workflow_complexity="conditional",
        )
        db_session.add(org)
        await db_session.flush()

        profile = await company_experience_service.resolve_profile_for_organization(db_session, org.id)
        assert profile == CompanyExperienceProfile.MID_MARKET

    @pytest.mark.asyncio
    async def test_get_visible_modules(self, db_session: AsyncSession):
        """Test getting visible modules."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        modules = await company_experience_service.get_visible_modules(db_session, org.id)
        assert "home" in modules
        assert "workspace" in modules
        assert "my-work" in modules
        assert "my-day" in modules

    @pytest.mark.asyncio
    async def test_get_navigation_groups(self, db_session: AsyncSession):
        """Test getting navigation groups."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        # Create default config
        config = CompanyExperienceConfig(organization_id=org.id)
        db_session.add(config)
        await db_session.flush()

        groups = await company_experience_service.get_navigation_groups(db_session, org.id)
        assert len(groups) > 0
        assert any(g["key"] == "workspace" for g in groups)
        assert any(g["key"] == "ai" for g in groups)

    @pytest.mark.asyncio
    async def test_get_navigation_groups_growing(self, db_session: AsyncSession):
        """Test navigation groups for growing company."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
            employee_count=50,
        )
        db_session.add(org)
        await db_session.flush()

        # Create config with growing profile
        config = CompanyExperienceConfig(
            organization_id=org.id,
            experience_profile=CompanyExperienceProfile.GROWING,
        )
        db_session.add(config)
        await db_session.flush()

        groups = await company_experience_service.get_navigation_groups(db_session, org.id)
        group_keys = [g["key"] for g in groups]
        assert "people" in group_keys
        assert "work" in group_keys

    @pytest.mark.asyncio
    async def test_transition_profile(self, db_session: AsyncSession):
        """Test transitioning between profiles."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        # Start with startup
        config = await company_experience_service.transition_profile(
            db_session, org.id, CompanyExperienceProfile.GROWING, "user1", "user1@test.com", "Company grew"
        )
        assert config.experience_profile == CompanyExperienceProfile.GROWING

        # Check history was recorded
        from sqlalchemy import select
        result = await db_session.execute(
            select(CompanyExperienceProfileHistory).where(
                CompanyExperienceProfileHistory.organization_id == org.id
            )
        )
        history = result.scalars().all()
        assert len(history) == 1
        assert history[0].previous_profile == "startup"
        assert history[0].new_profile == "growing"

    @pytest.mark.asyncio
    async def test_transition_profile_idempotent(self, db_session: AsyncSession):
        """Test that transitioning to same profile is idempotent."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        # Set to growing
        config = await company_experience_service.transition_profile(
            db_session, org.id, CompanyExperienceProfile.GROWING, "user1", "user1@test.com"
        )
        assert config.experience_profile == CompanyExperienceProfile.GROWING

        # Transition to same profile
        config2 = await company_experience_service.transition_profile(
            db_session, org.id, CompanyExperienceProfile.GROWING, "user1", "user1@test.com"
        )
        assert config2.experience_profile == CompanyExperienceProfile.GROWING
        # Should not create duplicate history
        from sqlalchemy import select
        result = await db_session.execute(
            select(CompanyExperienceProfileHistory).where(
                CompanyExperienceProfileHistory.organization_id == org.id
            )
        )
        history = result.scalars().all()
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_check_module_access(self, db_session: AsyncSession):
        """Test module access checking."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        config = CompanyExperienceConfig(
            organization_id=org.id,
            experience_profile=CompanyExperienceProfile.STARTUP,
        )
        db_session.add(config)
        await db_session.flush()

        # Startup modules accessible
        assert await company_experience_service.check_module_access(db_session, org.id, "home") is True
        assert await company_experience_service.check_module_access(db_session, org.id, "workspace") is True

        # Enterprise modules not accessible
        assert await company_experience_service.check_module_access(db_session, org.id, "finance") is False
        assert await company_experience_service.check_module_access(db_session, org.id, "enterprise") is False


class TestExperienceProfileHistory:
    """Test experience profile history/audit trail."""

    @pytest.mark.asyncio
    async def test_profile_history_recorded(self, db_session: AsyncSession):
        """Test that profile changes are recorded in history."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        config = CompanyExperienceConfig(organization_id=org.id)
        db_session.add(config)
        await db_session.flush()

        # Change profile
        config.experience_profile = CompanyExperienceProfile.GROWING
        config.previous_profile = CompanyExperienceProfile.STARTUP.value
        config.last_profile_change = utcnow()

        history = CompanyExperienceProfileHistory(
            organization_id=org.id,
            previous_profile=CompanyExperienceProfile.STARTUP.value,
            new_profile=CompanyExperienceProfile.GROWING.value,
            changed_by="user1",
            reason="Company growth",
        )
        db_session.add(history)
        await db_session.flush()

        from sqlalchemy import select
        result = await db_session.execute(
            select(CompanyExperienceProfileHistory).where(
                CompanyExperienceProfileHistory.organization_id == org.id
            )
        )
        history_records = result.scalars().all()
        assert len(history_records) == 1
        assert history_records[0].previous_profile == "startup"
        assert history_records[0].new_profile == "growing"
        assert history_records[0].reason == "Company growth"


class TestCanonicalRealityInvariance:
    """Test that profile changes preserve canonical company reality."""

    @pytest.mark.asyncio
    async def test_profile_change_preserves_organization_identity(self, db_session: AsyncSession):
        """Test that changing profile doesn't change organization identity."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
            employee_count=10,
        )
        db_session.add(org)
        await db_session.flush()

        original_id = org.id
        original_name = org.name

        # Transition through multiple profiles
        for profile in [
            CompanyExperienceProfile.GROWING,
            CompanyExperienceProfile.MID_MARKET,
            CompanyExperienceProfile.LARGE_ENTERPRISE,
        ]:
            config = await company_experience_service.transition_profile(
                db_session, org.id, profile, "user1", "user1@test.com"
            )
            await db_session.commit()

            # Verify organization identity unchanged
            await db_session.refresh(org)
            assert org.id == original_id
            assert org.name == original_name
            assert org.employee_count == 10  # Canonical state unchanged

    @pytest.mark.asyncio
    async def test_profile_change_preserves_employee_identities(self, db_session: AsyncSession):
        """Test that changing profile doesn't affect employee records."""
        from app.models.employee import Employee
        
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        # Create employees
        emp1 = Employee(
            organization_id=org.id,
            employee_number="E001",
            first_name="John",
            last_name="Doe",
            email="john@test.com",
        )
        emp2 = Employee(
            organization_id=org.id,
            employee_number="E002",
            first_name="Jane",
            last_name="Smith",
            email="jane@test.com",
        )
        db_session.add_all([emp1, emp2])
        await db_session.flush()

        emp1_id = emp1.id
        emp2_id = emp2.id

        # Transition profile
        await company_experience_service.transition_profile(
            db_session, org.id, CompanyExperienceProfile.LARGE_ENTERPRISE, "user1", "user1@test.com"
        )
        await db_session.commit()

        # Verify employees unchanged
        await db_session.refresh(emp1)
        await db_session.refresh(emp2)
        assert emp1.id == emp1_id
        assert emp2.id == emp2_id
        assert emp1.employee_number == "E001"
        assert emp2.employee_number == "E002"


class TestExperienceConfiguration:
    """Test experience configuration updates."""

    @pytest.mark.asyncio
    async def test_update_experience_config(self, db_session: AsyncSession):
        """Test updating experience configuration."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        config = await company_experience_service.update_experience_config(
            db_session, org.id,
            {
                "navigation_density": "compact",
                "show_advanced_features": True,
                "default_language": "es",
                "supported_languages": ["en", "es", "fr"],
            },
            actor_id="user1",
            actor_email="user1@test.com",
        )

        assert config.navigation_density == "compact"
        assert config.show_advanced_features is True
        assert config.default_language == "es"
        assert config.supported_languages == ["en", "es", "fr"]

    @pytest.mark.asyncio
    async def test_update_feature_flags(self, db_session: AsyncSession):
        """Test updating feature flags."""
        org_id = f"test-org-{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid4().hex[:8]}",
            timezone="UTC",
            language="en",
        )
        db_session.add(org)
        await db_session.flush()

        config = await company_experience_service.update_experience_config(
            db_session, org.id,
            {
                "feature_flags": {
                    "dark_mode": True,
                    "beta_features": False,
                    "advanced_analytics": True,
                }
            },
            actor_id="user1",
            actor_email="user1@test.com",
        )

        assert config.feature_flags["dark_mode"] is True
        assert config.feature_flags["beta_features"] is False
        assert config.feature_flags["advanced_analytics"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])