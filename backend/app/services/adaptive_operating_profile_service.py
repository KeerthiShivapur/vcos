"""Adaptive Operating Profile Service - Universal Company Configuration.

This service manages the adaptive operating profile, capability lifecycle,
integration states, workflow configurations, and system recommendations.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.rls import set_tenant_context
from app.models.adaptive_operating_profile import (
    AdaptiveOperatingProfile,
    AdaptiveOperatingProfileVersion,
    CapabilityLifecycleRecord,
    CapabilityLifecycleState,
    IntegrationConfigRecord,
    IntegrationState,
    WorkflowConfigurationRecord,
    AdaptationRecommendationRecord,
    CapabilityKey,
    IntegrationState,
    CapabilityLifecycleState,
    AdaptationMode,
)
from app.models.organization import Organization
from app.models.user import User
from app.services.company_experience_service import company_experience_service
from app.services.permission_service import permission_service

logger = logging.getLogger("vcos.adaptive_operating_profile")


class AdaptiveOperatingProfileService:
    """Service for managing adaptive operating profiles and capability lifecycle."""

    # ------------------------------------------------------------ Profile Management

    async def get_profile(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Optional[AdaptiveOperatingProfile]:
        """Get the adaptive operating profile for an organization."""
        result = await db.execute(
            select(AdaptiveOperatingProfile).where(
                AdaptiveOperatingProfile.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_profile(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> AdaptiveOperatingProfile:
        """Get existing profile or create default."""
        profile = await self.get_profile(db, organization_id)
        if profile:
            return profile

        # Create default profile based on company experience config
        from app.services.company_experience_service import company_experience_service
        exp_config = await company_experience_service.get_or_create_experience_config(db, organization_id)

        profile = AdaptiveOperatingProfile(
            organization_id=organization_id,
            profile_name="default",
            # Map experience profile to operating model
            operating_model=OperatingModel.HYBRID,
            governance_profile=GovernanceProfile.STANDARD,
            scaling_profile=ScalingProfile.MEASURED,
            # Enable core capabilities by default
            enabled_capabilities=[
                CapabilityKey.EMPLOYEE_MANAGEMENT,
                CapabilityKey.WORK_MANAGEMENT,
                CapabilityKey.MEETINGS,
                CapabilityKey.MESSAGING,
                CapabilityKey.DOCUMENTS,
                CapabilityKey.SEARCH,
                CapabilityKey.AI_COMPANION,
            ],
            workflow_complexity="standard",
            default_approval_levels=1,
            feature_flags={
                "ai_companion_enabled": True,
                "company_brain_enabled": True,
            },
        )
        db.add(profile)
        await db.flush()
        return profile

    async def update_profile(
        self,
        db: AsyncSession,
        organization_id: str,
        data: dict,
        *,
        actor_id: str,
        actor_email: str,
    ) -> AdaptiveOperatingProfile:
        """Update adaptive operating profile with versioning."""
        profile = await self.get_or_create_profile(db, organization_id)

        # Create version snapshot before changes
        await self._create_version_snapshot(
            db, profile, actor_id, actor_email, data.get("change_reason", "Profile updated"), data
        )

        # Update allowed fields
        allowed_fields = {
            "operating_model", "governance_profile", "scaling_profile",
            "enabled_capabilities", "disabled_capabilities",
            "interface_density", "navigation_style", "dashboard_layout",
            "progressive_disclosure", "show_advanced_features",
            "workflow_complexity", "default_approval_levels",
            "segregation_of_duties", "delegation_enabled",
            "default_language", "supported_languages", "default_timezone",
            "date_format", "number_format", "currency", "working_calendar",
            "integration_configs", "feature_flags",
            "governance_profile", "require_mfa_for_admin",
            "session_timeout_minutes", "max_failed_login_attempts",
            "password_policy", "data_retention_days", "sensitive_data_fields",
            "scaling_profile", "max_concurrent_users", "query_timeout_seconds",
            "enable_caching", "cache_ttl_seconds",
            "ai_companion_enabled", "company_brain_enabled",
            "digital_twin_enabled", "background_intelligence_enabled",
            "auto_approve_low_risk", "max_auto_approval_amount",
            "notification_preferences", "email_notifications_enabled",
            "push_notifications_enabled", "in_app_notifications_enabled",
            "auto_adaptation_enabled", "adaptation_modes",
            "auto_transition_enabled", "transition_cooldown_days",
            "capability_lifecycle_config",
        }

        for key, value in data.items():
            if key in allowed_fields and value is not None:
                setattr(profile, key, value)

        profile.last_modified_by = actor_id
        profile.last_modified_at = utcnow()
        profile.version += 1

        await db.flush()
        await db.commit()
        return profile

    async def _create_version_snapshot(
        self,
        db: AsyncSession,
        profile: AdaptiveOperatingProfile,
        actor_id: str,
        actor_email: str,
        reason: str,
        changes: dict,
    ):
        """Create a version snapshot before changes."""
        # Capture current config snapshot
        config_snapshot = {
            "operating_model": profile.operating_model.value if hasattr(profile.operating_model, 'value') else str(profile.operating_model),
            "governance_profile": profile.governance_profile,
            "scaling_profile": profile.scaling_profile,
            "enabled_capabilities": profile.enabled_capabilities,
            "disabled_capabilities": profile.disabled_capabilities,
            "interface_density": profile.interface_density,
            "navigation_style": profile.navigation_style,
            "dashboard_layout": profile.dashboard_layout,
            "progressive_disclosure": profile.progressive_disclosure,
            "show_advanced_features": profile.show_advanced_features,
            "workflow_complexity": profile.workflow_complexity,
            "default_approval_levels": profile.default_approval_levels,
            "segregation_of_duties": profile.segregation_of_duties,
            "delegation_enabled": profile.delegation_enabled,
            "default_language": profile.default_language,
            "supported_languages": profile.supported_languages,
            "default_timezone": profile.default_timezone,
            "date_format": profile.date_format,
            "number_format": profile.number_format,
            "currency": profile.currency,
            "integration_configs": profile.integration_configs,
            "feature_flags": profile.feature_flags,
            "governance_profile": profile.governance_profile,
            "scaling_profile": profile.scaling_profile,
            "feature_flags": profile.feature_flags,
            "auto_adaptation_enabled": profile.auto_adaptation_enabled,
            "adaptation_modes": profile.adaptation_modes,
            "auto_transition_enabled": profile.auto_transition_enabled,
            "transition_cooldown_days": profile.transition_cooldown_days,
        }

        version = AdaptiveOperatingProfileVersion(
            profile_id=profile.id,
            organization_id=profile.organization_id,
            version=profile.version,
            effective_from=utcnow(),
            config_snapshot=config_snapshot,
            changed_by=profile.last_modified_by or "system",
            changed_by_email=actor_email,
            change_reason=reason,
            change_type="updated",
            affected_capabilities=list(changes.keys()),
            affected_workflows=[],
            affected_users=[],
            in_flight_policy="grandfather",
        )
        db.add(version)
        await db.flush()

    async def get_profile_versions(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int = 50,
    ) -> List[AdaptiveOperatingProfileVersion]:
        """Get version history for a profile."""
        profile = await self.get_profile(db, organization_id)
        if not profile:
            return []

        result = await db.execute(
            select(AdaptiveOperatingProfileVersion)
            .where(AdaptiveOperatingProfileVersion.profile_id == profile.id)
            .order_by(AdaptiveOperatingProfileVersion.version.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def rollback_to_version(
        self,
        db: AsyncSession,
        organization_id: str,
        version: int,
        actor_id: str,
        actor_email: str,
        reason: str,
    ) -> AdaptiveOperatingProfile:
        """Rollback profile to a previous version."""
        profile = await self.get_or_create_profile(db, organization_id)

        # Get the target version
        result = await db.execute(
            select(AdaptiveOperatingProfileVersion)
            .where(
                AdaptiveOperatingProfileVersion.profile_id == profile.id,
                AdaptiveOperatingProfileVersion.version == version,
            )
        )
        target_version = result.scalar_one_or_none()
        if not target_version:
            raise ValueError(f"Version {version} not found")

        # Create a new version with rollback type
        await self._create_version_snapshot(
            db, profile, actor_id, actor_email, f"Rollback to version {version}: {reason}",
            {"rollback_to_version": version}
        )

        # Restore configuration from snapshot
        snapshot = target_version.config_snapshot
        for key, value in snapshot.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        profile.version += 1
        profile.last_modified_by = "system"
        profile.last_modified_at = utcnow()

        await db.flush()
        await db.commit()

        logger.info(f"Rolled back profile for org {organization_id} to version {version}")
        return profile

    # ------------------------------------------------------------ Capability Lifecycle

    async def get_capability_record(
        self,
        db: AsyncSession,
        organization_id: str,
        capability_key: str,
    ) -> Optional[CapabilityLifecycleRecord]:
        """Get capability lifecycle record."""
        result = await db.execute(
            select(CapabilityLifecycleRecord).where(
                CapabilityLifecycleRecord.organization_id == organization_id,
                CapabilityLifecycleRecord.capability_key == capability_key,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_capability_record(
        self,
        db: AsyncSession,
        organization_id: str,
        capability_key: str,
    ) -> CapabilityLifecycleRecord:
        """Get or create capability lifecycle record."""
        record = await self.get_capability_record(db, organization_id, capability_key)
        if record:
            return record

        record = CapabilityLifecycleRecord(
            organization_id=organization_id,
            capability_key=capability_key,
            current_state=CapabilityLifecycleState.DISCOVERED,
        )
        db.add(record)
        await db.flush()
        return record

    async def validate_capability_prerequisites(
        self,
        db: AsyncSession,
        organization_id: str,
        capability_key: str,
    ) -> tuple[bool, List[str]]:
        """Validate prerequisites for a capability."""
        # Define prerequisite mapping
        prerequisites = {
            CapabilityKey.COMPANY_BRAIN: [CapabilityKey.SEARCH, CapabilityKey.DOCUMENTS],
            CapabilityKey.DIGITAL_TWIN: [CapabilityKey.PROJECTS, CapabilityKey.TASKS, CapabilityKey.CAPACITY],
            CapabilityKey.PAYROLL: [CapabilityKey.EMPLOYEE_MANAGEMENT, CapabilityKey.ATTENDANCE, CapabilityKey.LEAVE_MANAGEMENT],
            CapabilityKey.RECRUITMENT: [CapabilityKey.EMPLOYEE_MANAGEMENT, CapabilityKey.LEARNING],
            CapabilityKey.INTERVIEWS: [CapabilityKey.RECRUITMENT],
            CapabilityKey.PAYROLL: [CapabilityKey.EMPLOYEE_MANAGEMENT, CapabilityKey.ATTENDANCE, CapabilityKey.LEAVE_MANAGEMENT],
            CapabilityKey.DIGITAL_TWIN: [CapabilityKey.PROJECTS, CapabilityKey.TASKS],
        }

        missing = []
        for prereq in prerequisites.get(capability_key, []):
            record = await self.get_capability_record(db, organization_id, prereq.value)
            if not record or record.current_state != CapabilityLifecycleState.ENABLED:
                missing.append(prereq.value)

        return len(missing) == 0, missing

    async def validate_capability_configuration(
        self,
        db: AsyncSession,
        organization_id: str,
        capability_key: str,
    ) -> tuple[bool, List[str]]:
        """Validate capability configuration."""
        issues = []

        # Check if capability has required configuration
        if capability_key == CapabilityKey.PAYROLL:
            # Payroll needs tax configuration, payment provider, etc.
            pass  # Would check actual config
        elif capability_key == CapabilityKey.DIGITAL_TWIN:
            # Needs projects, tasks, capacity data
            pass

        return len(issues) == 0, issues

    async def validate_governance(
        self,
        db: AsyncSession,
        organization_id: str,
        capability_key: str,
    ) -> tuple[bool, List[str]]:
        """Validate governance requirements."""
        issues = []

        # Check if governance profile allows this capability
        profile = await self.get_profile(db, organization_id)
        if not profile:
            issues.append("No operating profile configured")
            return False, issues

        # Some capabilities require specific governance profiles
        restricted_capabilities = {
            CapabilityKey.PAYROLL: [GovernanceProfile.CONTROLLED, GovernanceProfile.REGULATED, GovernanceProfile.FEDERATED],
            CapabilityKey.COMPLIANCE: [GovernanceProfile.CONTROLLED, GovernanceProfile.REGULATED, GovernanceProfile.FEDERATED],
            CapabilityKey.AUDIT: [GovernanceProfile.CONTROLLED, GovernanceProfile.REGULATED, GovernanceProfile.FEDERATED],
            CapabilityKey.DIGITAL_TWIN: [GovernanceProfile.CONTROLLED, GovernanceProfile.REGULATED, GovernanceProfile.FEDERATED],
        }

        if capability_key in restricted_capabilities:
            required = restricted_capabilities[capability_key]
            if profile.governance_profile not in required:
                issues.append(f"Requires governance profile: {', '.join(r.value for r in required)}")

        return len(issues) == 0, issues

    async def validate_entitlement(
        self,
        db: AsyncSession,
        organization_id: str,
        capability_key: str,
    ) -> tuple[bool, List[str]]:
        """Validate commercial entitlement for capability."""
        issues = []

        # Check commercial entitlements
        # This would integrate with the entitlement service
        from app.services.entitlement_enforcement import entitlement_enforcement
        try:
            result = await entitlement_enforcement.check_entitlement(
                db, organization_id=organization_id, feature=capability_key.value
            )
            if not result.allowed:
                issues.append(f"Entitlement check failed: {result.reason}")
        except Exception as e:
            logger.warning(f"Entitlement check failed for {capability_key}: {e}")
            issues.append("Entitlement validation unavailable")

        return len(issues) == 0, issues

    async def advance_capability_lifecycle(
        self,
        db: AsyncSession,
        organization_id: str,
        capability_key: str,
        target_state: CapabilityLifecycleState,
        actor_id: str,
        actor_email: str,
    ) -> CapabilityLifecycleRecord:
        """Advance a capability through its lifecycle stages."""
        record = await self.get_or_create_capability_record(db, organization_id, capability_key)

        # Validate state transition
        valid_transitions = {
            CapabilityLifecycleState.DISCOVERED: [CapabilityLifecycleState.PREREQUISITES_VALIDATED],
            CapabilityLifecycleState.PREREQUISITES_VALIDATED: [CapabilityLifecycleState.CONFIGURATION_VALIDATED],
            CapabilityLifecycleState.CONFIGURATION_VALIDATED: [CapabilityLifecycleState.GOVERNANCE_VALIDATED],
            CapabilityLifecycleState.GOVERNANCE_VALIDATED: [CapabilityLifecycleState.ENTITLEMENT_VALIDATED],
            CapabilityLifecycleState.ENTITLEMENT_VALIDATED: [CapabilityLifecycleState.ACTIVATION_APPROVED],
            CapabilityLifecycleState.ACTIVATION_APPROVED: [CapabilityLifecycleState.ENABLED],
            CapabilityLifecycleState.ENABLED: [CapabilityLifecycleState.HEALTH_MONITORED, CapabilityLifecycleState.DEGRADED, CapabilityLifecycleState.BLOCKED, CapabilityLifecycleState.DISABLED],
            CapabilityLifecycleState.HEALTH_MONITORED: [CapabilityLifecycleState.DEGRADED, CapabilityLifecycleState.BLOCKED, CapabilityLifecycleState.DISABLED],
            CapabilityLifecycleState.DEGRADED: [CapabilityLifecycleState.ENABLED, CapabilityLifecycleState.BLOCKED, CapabilityLifecycleState.DISABLED],
            CapabilityLifecycleState.BLOCKED: [CapabilityLifecycleState.ENABLED, CapabilityLifecycleState.DISABLED],
            CapabilityLifecycleState.DISABLED: [CapabilityLifecycleState.DISCOVERED],
        }

        valid_next = valid_transitions.get(record.current_state, [])
        if target_state not in valid_next:
            raise ValueError(f"Invalid state transition: {record.current_state} -> {target_state}")

        # Validate prerequisites for each stage
        if target_state == CapabilityLifecycleState.PREREQUISITES_VALIDATED:
            ok, missing = await self.validate_capability_prerequisites(db, organization_id, capability_key)
            if not ok:
                record.missing_prerequisites = missing
                raise ValueError(f"Missing prerequisites: {missing}")
            record.prerequisites_met = True

        elif target_state == CapabilityLifecycleState.CONFIGURATION_VALIDATED:
            ok, issues = await self.validate_capability_configuration(db, organization_id, capability_key)
            if not ok:
                record.configuration_issues = issues
                raise ValueError(f"Configuration issues: {issues}")
            record.configuration_valid = True

        elif target_state == CapabilityLifecycleState.GOVERNANCE_VALIDATED:
            ok, issues = await self.validate_governance(db, organization_id, capability_key)
            if not ok:
                record.governance_issues = issues
                raise ValueError(f"Governance issues: {issues}")
            record.governance_approved = True

        elif target_state == CapabilityLifecycleState.ENTITLEMENT_VALIDATED:
            ok, issues = await self.validate_entitlement(db, organization_id, capability_key)
            if not ok:
                record.entitlement_issues = issues
                raise ValueError(f"Entitlement issues: {issues}")
            record.entitlement_verified = True

        elif target_state == CapabilityLifecycleState.ACTIVATION_APPROVED:
            record.approved_by = actor_id
            record.approved_at = utcnow()
            record.activation_approved = True

        elif target_state == CapabilityLifecycleState.ENABLED:
            # All validations must pass
            if not (record.prerequisites_met and record.configuration_valid and
                    record.governance_approved and record.entitlement_verified and record.activation_approved):
                raise ValueError("All validations must pass before enabling")

        # Update state
        record.previous_state = record.current_state
        record.current_state = target_state
        record.state_changed_at = utcnow()
        record.version += 1

        await db.flush()
        await db.commit()

        logger.info(f"Capability {capability_key} for org {organization_id} advanced to {target_state.value}")
        return record

    async def get_capability_status(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Dict[str, Any]:
        """Get status of all capabilities for an organization."""
        result = await db.execute(
            select(CapabilityLifecycleRecord).where(
                CapabilityLifecycleRecord.organization_id == organization_id
            )
        )
        records = result.scalars().all()

        return {
            "capabilities": [
                {
                    "key": r.capability_key,
                    "state": r.current_state.value,
                    "health": r.health_status,
                    "prerequisites_met": r.prerequisites_met,
                    "configuration_valid": r.configuration_valid,
                    "governance_approved": r.governance_approved,
                    "entitlement_verified": r.entitlement_verified,
                    "activation_approved": r.activation_approved,
                    "enabled": r.current_state == CapabilityLifecycleState.ENABLED,
                }
                for r in records
            ],
            "summary": {
                "total": len(records),
                "enabled": sum(1 for r in records if r.current_state == CapabilityLifecycleState.ENABLED),
                "degraded": sum(1 for r in records if r.health_status == "degraded"),
                "blocked": sum(1 for r in records if r.current_state == CapabilityLifecycleState.BLOCKED),
                "disabled": sum(1 for r in records if r.current_state == CapabilityLifecycleState.DISABLED),
            }
        }

    # ------------------------------------------------------------ Integration Management

    async def get_integration_config(
        self,
        db: AsyncSession,
        organization_id: str,
        integration_key: str,
    ) -> Optional[IntegrationConfigRecord]:
        """Get integration configuration."""
        result = await db.execute(
            select(IntegrationConfigRecord).where(
                IntegrationConfigRecord.organization_id == organization_id,
                IntegrationConfigRecord.integration_key == integration_key,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_integration_config(
        self,
        db: AsyncSession,
        organization_id: str,
        integration_key: str,
        integration_type: str,
    ) -> IntegrationConfigRecord:
        """Get or create integration config."""
        config = await self.get_integration_config(db, organization_id, integration_key)
        if config:
            return config

        config = IntegrationConfigRecord(
            organization_id=organization_id,
            integration_key=integration_key,
            integration_type=integration_key,
            state=IntegrationState.CONFIGURED,
        )
        db.add(config)
        await db.flush()
        return config

    async def update_integration_state(
        self,
        db: AsyncSession,
        organization_id: str,
        integration_key: str,
        state: IntegrationState,
        config: Optional[Dict] = None,
    ) -> IntegrationConfigRecord:
        """Update integration state with history."""
        config_record = await self.get_or_create_integration_config(
            db, organization_id, integration_key, integration_key
        )

        config_record.previous_state = config_record.state
        config_record.state = state
        config_record.state_changed_at = utcnow()

        if config:
            config_record.config.update(config)

        if state == IntegrationState.CONNECTED:
            config_record.last_sync_at = utcnow()
            config_record.last_sync_status = "success"
            config_record.last_sync_error = None

        await db.flush()
        await db.commit()

        return config_record

    async def record_sync_result(
        self,
        db: AsyncSession,
        organization_id: str,
        integration_key: str,
        success: bool,
        error: Optional[str] = None,
    ):
        """Record sync result for an integration."""
        config = await self.get_integration_config(db, organization_id, integration_key)
        if not config:
            return

        config.last_sync_at = utcnow()
        if success:
            config.last_successful_sync_at = utcnow()
            config.last_sync_status = "success"
            config.last_sync_error = None
            config.consecutive_failures = 0
            config.health_status = "healthy"
        else:
            config.last_sync_status = "failed"
            config.last_sync_error = error
            config.consecutive_failures += 1
            if config.consecutive_failures >= 3:
                config.health_status = "degraded"
            if config.consecutive_failures >= 5:
                config.health_status = "critical"

        await db.flush()
        await db.commit()

    async def get_integration_health(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Dict[str, Any]:
        """Get health status of all integrations."""
        result = await db.execute(
            select(IntegrationConfigRecord).where(
                IntegrationConfigRecord.organization_id == organization_id
            )
        )
        configs = result.scalars().all()

        return {
            "integrations": [
                {
                    "key": c.integration_key,
                    "type": c.integration_type,
                    "state": c.state.value,
                    "health": c.health_status,
                    "last_sync": c.last_sync_at.isoformat() if c.last_sync_at else None,
                    "last_status": c.last_sync_status,
                    "consecutive_failures": c.consecutive_failures,
                }
                for c in configs
            ],
            "summary": {
                "total": len(configs),
                "healthy": sum(1 for c in configs if c.health_status == "healthy"),
                "degraded": sum(1 for c in configs if c.health_status == "degraded"),
                "critical": sum(1 for c in configs if c.health_status == "critical"),
                "failed": sum(1 for c in configs if c.state == IntegrationState.FAILED),
            }
        }

    # ------------------------------------------------------------ Workflow Configuration

    async def get_workflow_config(
        self,
        db: AsyncSession,
        organization_id: str,
        workflow_key: str,
    ) -> Optional[WorkflowConfigurationRecord]:
        """Get workflow configuration."""
        result = await db.execute(
            select(WorkflowConfigurationRecord).where(
                WorkflowConfigurationRecord.organization_id == organization_id,
                WorkflowConfigurationRecord.workflow_key == workflow_key,
            )
        )
        return result.scalar_one_or_none()

    async def create_workflow_config(
        self,
        db: AsyncSession,
        organization_id: str,
        workflow_key: str,
        workflow_name: str,
        workflow_type: str,
        complexity: str = "standard",
        stages: Optional[List[Dict]] = None,
        actor_id: str = "system",
    ) -> WorkflowConfigurationRecord:
        """Create a new workflow configuration."""
        config = WorkflowConfigurationRecord(
            organization_id=organization_id,
            workflow_key=workflow_key,
            workflow_name=workflow_name,
            workflow_type=workflow_type,
            complexity=complexity,
            stages=stages or [],
            created_by=actor_id,
        )
        db.add(config)
        await db.flush()
        await db.commit()
        return config

    async def update_workflow_config(
        self,
        db: AsyncSession,
        organization_id: str,
        workflow_key: str,
        data: dict,
        actor_id: str,
    ) -> WorkflowConfigurationRecord:
        """Update workflow configuration with versioning."""
        config = await self.get_workflow_config(db, organization_id, workflow_key)
        if not config:
            raise ValueError(f"Workflow {workflow_key} not found")

        # Create new version
        config.version += 1
        config.effective_until = utcnow()

        new_config = WorkflowConfigurationRecord(
            organization_id=organization_id,
            workflow_key=workflow_key,
            workflow_name=data.get("workflow_name", config.workflow_name),
            workflow_type=data.get("workflow_type", config.workflow_type),
            complexity=data.get("complexity", config.complexity),
            stages=data.get("stages", config.stages),
            segregation_of_duties=data.get("segregation_of_duties", config.segregation_of_duties),
            delegation_enabled=data.get("delegation_enabled", config.delegation_enabled),
            timeout_hours=data.get("timeout_hours", config.timeout_hours),
            escalation_rules=data.get("escalation_rules", config.escalation_rules),
            failure_handling=data.get("failure_handling", config.failure_handling),
            policy_version=f"{config.version}.0",
            requires_segregation_of_duties=data.get("requires_segregation_of_duties", config.requires_segregation_of_duties),
            requires_dual_approval=data.get("requires_dual_approval", config.requires_dual_approval),
            created_by=actor_id,
            effective_from=utcnow(),
        )

        # Expire old config
        config.effective_until = utcnow()

        db.add(new_config)
        await db.flush()
        await db.commit()

        return new_config

    # ------------------------------------------------------------ Adaptation Recommendations

    async def create_recommendation(
        self,
        db: AsyncSession,
        organization_id: str,
        recommendation_type: str,
        title: str,
        description: str,
        rationale: str,
        evidence: List[Dict],
        confidence: float,
        impact_level: str,
        affected_capabilities: List[str],
        affected_workflows: List[str],
        estimated_effort: str,
        requires_approval: bool = True,
        triggered_by: str = "system",
        source_context: Optional[Dict] = None,
    ) -> AdaptationRecommendationRecord:
        """Create an adaptation recommendation."""
        recommendation = AdaptationRecommendationRecord(
            organization_id=organization_id,
            recommendation_type=recommendation_type,
            title=title,
            description=description,
            rationale=rationale,
            evidence=evidence,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            impact_level=impact_level,
            affected_capabilities=affected_capabilities,
            affected_workflows=affected_workflows,
            estimated_effort=estimated_effort,
            requires_approval=requires_approval,
            triggered_by=triggered_by,
            source_context=source_context or {},
            status="pending",
        )
        db.add(recommendation)
        await db.flush()
        await db.commit()
        return recommendation

    async def approve_recommendation(
        self,
        db: AsyncSession,
        recommendation_id: str,
        actor_id: str,
        actor_email: str,
    ) -> AdaptationRecommendationRecord:
        """Approve an adaptation recommendation."""
        result = await db.execute(
            select(AdaptationRecommendationRecord).where(
                AdaptationRecommendationRecord.id == recommendation_id
            )
        )
        recommendation = result.scalar_one_or_none()
        if not recommendation:
            raise ValueError(f"Recommendation {recommendation_id} not found")

        recommendation.status = "approved"
        recommendation.reviewed_by = actor_id
        recommendation.reviewed_at = utcnow()
        recommendation.governance_trail.append({
            "action": "approved",
            "by": actor_id,
            "email": actor_email,
            "at": utcnow().isoformat(),
        })

        await db.flush()
        await db.commit()
        return recommendation

    async def apply_recommendation(
        self,
        db: AsyncSession,
        recommendation_id: str,
        actor_id: str,
    ) -> AdaptationRecommendationRecord:
        """Apply an approved recommendation."""
        result = await db.execute(
            select(AdaptationRecommendationRecord).where(
                AdaptationRecommendationRecord.id == recommendation_id
            )
        )
        recommendation = result.scalar_one_or_none()
        if not recommendation:
            raise ValueError(f"Recommendation {recommendation_id} not found")

        if recommendation.status != "approved":
            raise ValueError("Recommendation must be approved before applying")

        # Apply the recommendation based on type
        # This would integrate with the appropriate services
        recommendation.status = "applied"
        recommendation.applied_at = utcnow()

        await db.flush()
        await db.commit()

        # Emit event
        from app.events.publisher import publish_event
        await publish_event(
            db,
            name="adaptation.recommendation.applied",
            organization_id=recommendation.organization_id,
            actor_id=actor_id,
            payload={
                "recommendation_id": recommendation_id,
                "type": recommendation.recommendation_type,
            },
        )

        return recommendation

    async def get_recommendations(
        self,
        db: AsyncSession,
        organization_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[AdaptationRecommendationRecord]:
        """Get recommendations for an organization."""
        query = select(AdaptationRecommendationRecord).where(
            AdaptationRecommendationRecord.organization_id == organization_id
        )
        if status:
            query = query.where(AdaptationRecommendationRecord.status == status)
        query = query.order_by(AdaptationRecommendationRecord.created_at.desc()).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    # ------------------------------------------------------------ Adaptation Engine

    async def analyze_and_recommend(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> List[AdaptationRecommendationRecord]:
        """Analyze organization state and generate recommendations."""
        recommendations = []

        profile = await self.get_profile(db, organization_id)
        if not profile:
            return recommendations

        org = await db.get(Organization, organization_id)
        if not org:
            return recommendations

        # Check capacity utilization
        from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service

        # Get a user for context
        user_result = await db.execute(
            select(User).where(User.organization_id == organization_id).limit(1)
        )
        user = user_result.scalars().first()

        if user:
            caller = await canonical_digital_twin_service.derive_twin_state(
                db, caller=user, scope_type="org", scope_id=organization_id
            )
            if caller:
                twin_state = await canonical_digital_twin_service.derive_twin_state(
                    db, caller=caller, scope_type="org", scope_id=organization_id
                )

                # Check capacity utilization
                utilization = getattr(twin_state, 'utilization', 0) if hasattr(twin_state, 'utilization') else 0
                if utilization > 90:
                    rec = await self.create_recommendation(
                        db, organization_id,
                        "capacity",
                        "Critical Capacity Utilization",
                        f"Organization capacity at {utilization}%",
                        "Digital Twin indicates critical capacity utilization",
                        [{"source": "digital_twin", "metric": "utilization", "value": utilization}],
                        0.95, "critical",
                        ["capacity", "projects", "tasks"],
                        ["project_execution", "resource_allocation"],
                        "high",
                        triggered_by="system",
                        source_context={"utilization": utilization, "source": "digital_twin"}
                    )
                    recommendations.append(rec)

        # Check for missing capabilities based on profile
        profile_config = await company_experience_service.get_experience_config(db, organization_id)
        if profile_config:
            suggested_profile = profile_config.suggested_profile
            if suggested_profile.value != profile_config.experience_profile.value:
                # Only recommend upgrade
                profile_order = {
                    CompanyExperienceProfile.STARTUP: 0,
                    CompanyExperienceProfile.GROWING: 1,
                    CompanyExperienceProfile.MID_MARKET: 2,
                    CompanyExperienceProfile.LARGE_ENTERPRISE: 3,
                    CompanyExperienceProfile.GLOBAL_ENTERPRISE: 4,
                }
                if profile_order[suggested_profile] > profile_order[profile_config.experience_profile]:
                    rec = await self.create_recommendation(
                        db, organization_id,
                        "capability",
                        f"Consider upgrading to {suggested_profile.value} profile",
                        f"Company growth suggests {suggested_profile.value} profile",
                        "Automatic profile detection based on employee count, org depth, etc.",
                        [{"source": "company_experience", "suggested_profile": suggested_profile.value}],
                        0.85, "medium",
                        ["profile", "modules", "navigation"],
                        ["navigation", "module_access"],
                        "low",
                        triggered_by="system",
                        source_context={"suggested_profile": suggested_profile.value}
                    )
                    recommendations.append(rec)

        return recommendations

    async def auto_apply_recommendations(
        self,
        db: AsyncSession,
        organization_id: str,
        actor_id: str,
    ) -> List[AdaptationRecommendationRecord]:
        """Auto-apply low-risk recommendations."""
        recommendations = await self.get_recommendations(db, organization_id, status="pending")
        applied = []

        for rec in recommendations:
            if rec.auto_applicable and rec.confidence > 0.9 and rec.impact_level == "low":
                try:
                    await self.apply_recommendation(db, rec.id, actor_id)
                    applied.append(rec)
                except Exception as e:
                    logger.warning(f"Failed to auto-apply recommendation {rec.id}: {e}")

        return applied

    # ------------------------------------------------------------ Analytics

    async def get_adaptation_analytics(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Dict[str, Any]:
        """Get comprehensive adaptation analytics."""
        profile = await self.get_profile(db, organization_id)
        capability_status = await self.get_capability_status(db, organization_id)
        integration_health = await self.get_integration_health(db, organization_id)
        recommendations = await self.get_recommendations(db, organization_id)

        # Get profile versions
        versions = await self.get_profile_versions(db, organization_id, limit=10)

        return {
            "profile": {
                "operating_model": profile.operating_model.value if profile else None,
                "governance_profile": profile.governance_profile,
                "scaling_profile": profile.scaling_profile,
                "enabled_capabilities_count": len(profile.enabled_capabilities) if profile else 0,
                "auto_adaptation_enabled": profile.auto_adaptation_enabled if profile else False,
            },
            "capabilities": capability_status,
            "integrations": integration_health,
            "recommendations": {
                "total": len(recommendations),
                "pending": sum(1 for r in recommendations if r.status == "pending"),
                "approved": sum(1 for r in recommendations if r.status == "approved"),
                "applied": sum(1 for r in recommendations if r.status == "applied"),
                "by_type": {},
            },
            "profile_versions": [
                {
                    "version": v.version,
                    "effective_from": v.effective_from.isoformat(),
                    "changed_by": v.changed_by,
                    "reason": v.change_reason,
                }
                for v in versions
            ],
        }


adaptive_operating_profile_service = AdaptiveOperatingProfileService()