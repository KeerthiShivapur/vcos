"""Company Experience Service — Universal Adaptive Experience Architecture.

This service manages the company experience configuration and provides
the adaptive experience engine that resolves the appropriate interface
based on company complexity, user role, and governance scope.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.rls import set_tenant_context
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
from app.services.permission_service import permission_service

logger = logging.getLogger("vcos.company_experience")


class CompanyExperienceService:
    """Service for managing company experience configuration and adaptive UI."""

    # ------------------------------------------------------------ Configuration

    async def get_experience_config(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Optional[CompanyExperienceConfig]:
        """Get the experience configuration for an organization."""
        result = await db.execute(
            select(CompanyExperienceConfig).where(
                CompanyExperienceConfig.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_experience_config(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> CompanyExperienceConfig:
        """Get existing config or create default."""
        config = await self.get_experience_config(db, organization_id)
        if config:
            return config

        # Create default config
        config = CompanyExperienceConfig(organization_id=organization_id)
        db.add(config)
        await db.flush()
        return config

    async def update_experience_config(
        self,
        db: AsyncSession,
        organization_id: str,
        data: dict,
        *,
        actor_id: str,
        actor_email: str,
    ) -> CompanyExperienceConfig:
        """Update company experience configuration."""
        config = await self.get_or_create_experience_config(db, organization_id)

        # Track profile change
        previous_profile = config.experience_profile
        new_profile_value = data.get("experience_profile")
        if new_profile_value and new_profile_value != previous_profile.value:
            # Record history
            history = CompanyExperienceProfileHistory(
                organization_id=organization_id,
                previous_profile=previous_profile.value,
                new_profile=new_profile_value,
                changed_by=actor_id,
                reason=data.get("profile_change_reason"),
            )
            db.add(history)
            config.previous_profile = previous_profile.value
            config.last_profile_change = utcnow()

        # Update fields
        allowed_fields = {
            "experience_profile",
            "employee_count",
            "organizational_depth",
            "organizational_unit_count",
            "legal_entity_count",
            "geographic_footprint_count",
            "governance_complexity",
            "workflow_complexity",
            "enabled_modules",
            "default_dashboard_layout",
            "navigation_density",
            "progressive_disclosure",
            "show_advanced_features",
            "default_language",
            "supported_languages",
            "timezone",
            "date_format",
            "number_format",
            "feature_flags",
            "governance_complexity",
            "workflow_complexity",
            "enabled_modules",
            "default_dashboard_layout",
            "navigation_density",
            "progressive_disclosure",
            "show_advanced_features",
            "default_language",
            "supported_languages",
            "timezone",
            "date_format",
            "number_format",
            "feature_flags",
        }

        for key, value in data.items():
            if key in allowed_fields and value is not None:
                setattr(config, key, value)

        config.configured_by = actor_id
        config.configured_at = utcnow()

        if new_profile_value and new_profile_value != previous_profile.value:
            config.experience_profile = CompanyExperienceProfile(new_profile_value)
            config.last_profile_change = utcnow()

        await db.flush()
        await db.commit()
        return config

    # ------------------------------------------------------------ Profile Resolution

    async def resolve_profile_for_organization(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> CompanyExperienceProfile:
        """Resolve the appropriate experience profile for an organization."""
        org = await db.get(Organization, organization_id)
        if not org:
            return CompanyExperienceProfile.STARTUP

        config = await self.get_experience_config(db, organization_id)
        if config and config.experience_profile:
            return config.experience_profile

        # Auto-resolve based on company complexity
        return resolve_experience_profile(
            employee_count=org.employee_count,
            org_depth=org.organizational_depth,
            org_unit_count=org.organizational_unit_count,
            legal_entity_count=org.legal_entity_count,
            geo_count=org.geographic_footprint_count,
            governance_level=org.governance_complexity,
            workflow_complexity=org.workflow_complexity,
        )

    async def get_profile_capabilities(
        self,
        profile: CompanyExperienceProfile,
    ) -> Dict[str, Any]:
        """Get capability matrix for a profile."""
        from app.models.company_experience import get_profile_capabilities
        return get_profile_capabilities(profile)

    # ------------------------------------------------------------ Module Visibility

    async def should_show_module(
        self,
        db: AsyncSession,
        organization_id: str,
        module_key: str,
        user_role: Optional[str] = None,
    ) -> bool:
        """Determine if a module should be visible for the given organization/user."""
        config = await self.get_experience_config(db, organization_id)
        if not config:
            # Default to startup profile
            from app.models.company_experience import CompanyExperienceProfile
            return CompanyExperienceProfile.STARTUP.value in module_key

        return config.should_show_module(module_key)

    async def get_visible_modules(
        self,
        db: AsyncSession,
        organization_id: str,
        user_role: Optional[str] = None,
    ) -> List[str]:
        """Get list of modules visible for the organization/user."""
        config = await self.get_experience_config(db, organization_id)
        if not config:
            return ["home", "workspace", "my-work", "my-day", "company-home", "ai"]

        profile = config.experience_profile
        from app.models.company_experience import get_profile_capabilities
        caps = get_profile_capabilities(config.experience_profile)
        return caps.get("modules_enabled_by_default", [])

    # ------------------------------------------------------------ Navigation

    async def get_navigation_groups(
        self,
        db: AsyncSession,
        organization_id: str,
        user_role: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get navigation groups adapted to the company profile."""
        config = await self.get_experience_config(db, organization_id)
        if not config:
            return []

        profile = config.experience_profile
        from app.models.company_experience import get_profile_capabilities
        caps = get_profile_capabilities(config.experience_profile)
        nav_groups = caps.get("navigation_groups", ["workspace", "ai"])

        # Build navigation groups based on profile
        base_groups = {
            "workspace": {"label": "Workspace", "items": ["home", "workspace", "my-work", "my-day"]},
            "ai": {"label": "AI", "items": ["ai", "company-brain"]},
            "people": {"label": "People", "items": ["people", "departments", "teams"]},
            "work": {"label": "Work", "items": ["projects", "tasks", "goals", "approvals"]},
            "customers": {"label": "Customers", "items": ["customers", "crm", "contracts"]},
            "finance": {"label": "Finance", "items": ["finance", "budgets", "expenses", "procurement"]},
            "hr": {"label": "HR", "items": ["hr", "hiring", "performance", "learning", "payroll"]},
            "intelligence": {"label": "Intelligence", "items": ["brain", "insights", "patterns", "twin"]},
            "knowledge": {"label": "Knowledge", "items": ["knowledge", "wiki", "documents", "decisions"]},
            "governance": {"label": "Governance", "items": ["governance", "approvals", "decisions", "compliance"]},
            "platform": {"label": "Platform", "items": ["enterprise", "integrations", "api", "security", "compliance"]},
            "admin": {"label": "Admin", "items": ["settings", "users", "roles", "audit", "feature-flags"]},
        }

        visible_groups = []
        for group_key in nav_groups:
            if group_key not in base_groups:
                continue

            group = base_groups[group_key]
            # Filter items by visibility
            visible_items = [
                item for item in group["items"]
                if await self.should_show_module(None, None, item)  # Simplified for now
            ]
            
            if not visible_items:
                continue

            visible_groups.append({
                "key": group_key,
                "label": group["label"],
                "items": visible_items,
            })

        return visible_groups

    # ------------------------------------------------------------ Profile Transitions

    async def transition_profile(
        self,
        db: AsyncSession,
        organization_id: str,
        new_profile: "CompanyExperienceProfile",
        actor_id: str,
        actor_email: str,
        reason: Optional[str] = None,
    ) -> CompanyExperienceConfig:
        """Transition organization to a new experience profile."""
        config = await self.get_or_create_experience_config(db, organization_id)
        previous = config.experience_profile

        if previous == new_profile:
            return config

        config.previous_profile = previous.value
        config.experience_profile = new_profile
        config.last_profile_change = utcnow()
        config.configured_by = "system"  # or actor_id
        config.configured_at = utcnow()

        # Record history
        history = CompanyExperienceProfileHistory(
            organization_id=organization_id,
            previous_profile=previous.value,
            new_profile=new_profile.value,
            changed_by=actor_id,
            reason=reason or f"Transition from {previous.value} to {new_profile.value}",
        )
        db.add(history)
        await db.commit()

        # Emit event for UI update
        from app.events.publisher import publish_event
        await publish_event(
            db,
            name="company.experience_profile.changed",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "previous_profile": previous.value,
                "new_profile": new_profile.value,
                "reason": reason,
            },
        )

        logger.info(f"Organization {organization_id} transitioned from {previous.value} to {new_profile.value}")
        return config

    # ------------------------------------------------------------ Capabilities

    async def get_organization_capabilities(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Dict[str, Any]:
        """Get all capabilities available to an organization."""
        config = await self.get_experience_config(db, organization_id)
        if not config:
            return get_profile_capabilities(CompanyExperienceProfile.STARTUP)

        return get_profile_capabilities(config.experience_profile)

    async def check_module_access(
        self,
        db: AsyncSession,
        organization_id: str,
        module_key: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """Check if a module is accessible (config + permissions)."""
        # First check experience config
        config = await self.get_experience_config(db, organization_id)
        if not config or not config.should_show_module(module_key):
            return False

        # Then check permissions
        if module_key in ["admin", "enterprise", "governance", "finance", "hr"]:
            # These require explicit permissions
            # The actual permission check happens in the API layer
            pass

        return True


company_experience_service = CompanyExperienceService()