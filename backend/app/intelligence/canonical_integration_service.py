from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Callable, TYPE_CHECKING

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.core.timeutils import utcnow
from app.events.publisher import publish_event

if TYPE_CHECKING:
    from app.api.v1.workspace import DeepLinkResolveResponse
else:
    from app.api.v1.workspace import DeepLinkResolveResponse

logger = logging.getLogger("vcos.integration.connectors")


@dataclass
class GameStartResponse:
    """Response for starting a game session."""
    game: str
    session_id: str
    state: dict
    cooldown_until: str


@dataclass
class GameActionResponse:
    """Response for a game action."""
    state: dict
    result: Optional[dict]
    completed: bool
    score: Optional[int]


from app.models.organization import Organization
from app.models.user import User
from app.models.workspace import (
    WorkspaceSettings,
    GameSession,
    WorkspaceSession,
    VirtualOfficeFloor,
    VirtualOfficeRoom,
)
from app.models.notification import Notification
from app.intelligence.builtin_connectors import register_builtin_connectors
from app.models.canonical_integration import (
    Connector,
    ConnectorInstance,
    ConnectorCapability,
    ExternalIdentityMapping,
    ExternalIdentityMappingHistory,
    SyncRun,
    SyncCursor,
    ExternalEvent,
    SourceAuthority,
    ExternalConflict,
    ExternalOperation,
    IntegrationHealth,
    NotificationCenterResponse,
    CONNECTOR_KINDS,
    CONNECTOR_STATES,
    CONNECTOR_CAPABILITIES,
    ENTITY_TYPES,
    MAPPING_STATES,
    SYNC_STATES,
    SYNC_MODES,
    EXTERNAL_EVENT_STATES,
    SOURCE_AUTHORITY_LEVELS,
    CONFLICT_RESOLUTION_STATES,
    compute_payload_fingerprint,
    compute_event_fingerprint,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.workspace import (
    WorkspaceSettings,
    GameSession,
    WorkspaceSession,
    VirtualOfficeFloor,
    VirtualOfficeRoom,
)
from app.intelligence.canonical_mutation import (
    canonical_create,
    canonical_update,
    canonical_transition,
    canonical_delete,
    validate_optimistic_concurrency,
    validate_exact_once,
    ExactOnceViolation,
    ConcurrencyViolation,
    MutationType,
    EpistemicStatus,
    CanonicalMutationContext,
)
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
from app.intelligence.builtin_connectors import register_builtin_connectors
from app.services.governance_service import governance_service
from app.models.organization import Organization
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
from app.intelligence.builtin_connectors import register_builtin_connectors
from app.services.governance_service import governance_service
from app.models.organization import Organization
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
from app.intelligence.builtin_connectors import register_builtin_connectors


# ------------------------------------------------------------ Game Helpers

def _initialize_game_state(game_id: str) -> dict:
    """Initialize game state for a new session."""
    states = {
        "brain_blitz": {"level": 1, "score": 0, "challenge": "memory_sequence", "sequence": [1, 3, 2, 4]},
        "what_happens_next": {"level": 1, "score": 0, "scenario": "project_delay", "options": ["delay", "escalate", "replan", "accept"]},
        "emoji_detective": {"level": 1, "score": 0, "puzzle": "🏢💻📊📈", "answer": "business_growth"},
        "tiny_genius": {"level": 1, "score": 0, "question": "What does ROI stand for?", "options": ["Return on Investment", "Rate of Interest", "Risk of Inflation", "Revenue on Income"]},
        "company_chaos": {"level": 1, "score": 0, "scenario": "server_outage", "role": "engineer", "actions": ["restart", "investigate", "escalate", "communicate"]},
    }
    return states.get(game_id, {"level": 1, "score": 0})


def _process_game_action(game_id: str, state: dict, action: dict) -> tuple[dict, Optional[dict], bool, Optional[int]]:
    """Process a game action and return new state."""
    score = state.get("score", 0)
    
    if game_id == "tiny_genius":
        if action.get("answer") == "Return on Investment":
            score += 10
        return {"level": state["level"] + 1, "score": score, "completed": True}, {"correct": True}, True, score
    
    elif game_id == "brain_blitz":
        if action.get("input") == state.get("sequence"):
            score += 20
        return {"level": state["level"] + 1, "score": score}, {"correct": True}, state["level"] >= 5, score
    
    return state, None, False, score


# ------------------------------------------------------------ Connector Service Class

class ConnectorService:
    """Universal connector framework service.
    
    Provides the canonical service layer for:
    - Connector registration & discovery
    - Connector instance lifecycle management
    - Configuration validation
    - Capability discovery
    - Connection testing & health checks
    
    This is the provider-neutral foundation that all specific connectors build upon.
    """
    
    # ------------------------------------------------------------ Connector Registry
    
    async def register_connector(
        self,
        db: AsyncSession,
        *,
        kind: str,
        provider: str,
        display_name: str,
        description: Optional[str] = None,
        version: str = "1.0.0",
        inbound_capabilities: Optional[list[str]] = None,
        outbound_capabilities: Optional[list[str]] = None,
        supported_entities: Optional[list[str]] = None,
        supported_events: Optional[list[str]] = None,
        sync_modes: Optional[list[str]] = None,
        supports_webhooks: bool = False,
        supports_polling: bool = True,
        default_poll_interval_seconds: int = 300,
        auth_types: Optional[list[str]] = None,
        oauth_scopes: Optional[list[str]] = None,
        required_config_fields: Optional[list[str]] = None,
        optional_config_fields: Optional[list[str]] = None,
        security_requirements: Optional[dict] = None,
        credential_rotation_supported: bool = True,
        health_check_endpoint: Optional[str] = None,
        rate_limits: Optional[dict] = None,
        category: str = "integration",
        tags: Optional[list[str]] = None,
        documentation_url: Optional[str] = None,
        icon_url: Optional[str] = None,
        enabled: bool = True,
        created_by: Optional[str] = None,
    ) -> Connector:
        'Register a new connector type in the global registry.'
        
        if kind not in CONNECTOR_KINDS:
            raise ValueError(f"Invalid connector kind: {kind}. Must be one of: {CONNECTOR_KINDS}")
        
        # Validate capabilities
        for cap in (inbound_capabilities or []):
            if cap not in CONNECTOR_CAPABILITIES:
                raise ValueError(f"Invalid inbound capability: {cap}")
        for cap in (outbound_capabilities or []):
            if cap not in CONNECTOR_CAPABILITIES:
                raise ValueError(f"Invalid outbound capability: {cap}")
        
        # Validate entities
        for entity in (supported_entities or []):
            if entity not in ENTITY_TYPES:
                raise ValueError(f"Invalid entity type: {entity}")
        
        connector = Connector(
            kind=kind,
            provider=provider,
            display_name=display_name,
            description=description,
            version=version,
            inbound_capabilities=inbound_capabilities or [],
            outbound_capabilities=outbound_capabilities or [],
            supported_entities=supported_entities or [],
            supported_events=supported_events or [],
            sync_modes=sync_modes or ["incremental", "polling"],
            supports_webhooks=supports_webhooks,
            supports_polling=supports_polling,
            default_poll_interval_seconds=default_poll_interval_seconds,
            auth_types=auth_types or ["oauth2"],
            oauth_scopes=oauth_scopes or [],
            required_config_fields=required_config_fields or [],
            optional_config_fields=optional_config_fields or [],
            security_requirements=security_requirements,
            credential_rotation_supported=credential_rotation_supported,
            health_check_endpoint=health_check_endpoint,
            rate_limits=rate_limits,
            category=category,
            tags=tags or [],
            documentation_url=documentation_url,
            icon_url=icon_url,
            enabled=enabled,
            created_by=created_by,
        )
        
        db.add(connector)
        await db.flush()
        
        await publish_event(
            db,
            name="connector.registered",
            organization_id="system",
            actor_id=created_by,
            payload={"connector_id": connector.id, "kind": kind, "provider": provider},
        )
        
        logger.info("Registered connector: %s (%s)", provider, kind)
        return connector
    
    async def get_connector(self, db: AsyncSession, connector_id: str) -> Optional[Connector]:
        'Get a connector by ID.'
        return await db.get(Connector, connector_id)
    
    async def get_connector_by_kind_provider(
        self, db: AsyncSession, kind: str, provider: str
    ) -> Optional[Connector]:
        'Get a connector by kind and provider.'
        result = await db.execute(
            select(Connector).where(
                Connector.kind == kind,
                Connector.provider == provider,
            )
        )
        return result.scalar_one_or_none()
    
    async def list_connectors(
        self,
        db: AsyncSession,
        *,
        kind: Optional[str] = None,
        enabled_only: bool = True,
    ) -> list[Connector]:
        'List available connectors.'
        query = select(Connector)
        if kind:
            query = query.where(Connector.kind == kind)
        if enabled_only:
            query = query.where(Connector.enabled.is_(True))
        query = query.order_by(Connector.kind, Connector.provider)
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def update_connector(
        self,
        db: AsyncSession,
        connector_id: str,
        **fields: Any,
    ) -> Optional[Connector]:
        'Update a connector registration.'
        connector = await self.get_connector(db, connector_id)
        if connector is None:
            return None
        
        for key, value in fields.items():
            if value is not None and hasattr(connector, key):
                setattr(connector, key, value)
        
        connector.updated_at = utcnow()
        await db.flush()
        return connector
    
    async def deprecate_connector(
        self,
        db: AsyncSession,
        connector_id: str,
        reason: str,
        deprecated_by: Optional[str] = None,
    ) -> Optional[Connector]:
        'Deprecate a connector.'
        connector = await self.get_connector(db, connector_id)
        if connector is None:
            return None
        
        connector.deprecated = True
        connector.deprecated_at = utcnow()
        connector.deprecated_reason = reason
        connector.enabled = False
        connector.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="connector.deprecated",
            organization_id="system",
            actor_id=deprecated_by,
            payload={"connector_id": connector_id, "reason": reason},
        )
        
        return connector
    
    # ------------------------------------------------------------ Connector Capabilities
    
    async def register_capability(
        self,
        db: AsyncSession,
        *,
        connector_id: str,
        entity_type: str,
        operation: str,
        description: Optional[str] = None,
        requires_scopes: Optional[list[str]] = None,
        rate_limit: Optional[dict] = None,
        support_level: str = "full",
        limitations: Optional[list[str]] = None,
    ) -> ConnectorCapability:
        'Register a capability for a connector.'
        
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Invalid entity type: {entity_type}")
        
        connector = await self.get_connector(db, connector_id)
        if connector is None:
            raise ValueError(f"Connector not found: {connector_id}")
        
        capability = ConnectorCapability(
            connector_id=connector_id,
            entity_type=entity_type,
            operation=operation,
            description=description,
            requires_scopes=requires_scopes or [],
            rate_limit=rate_limit,
            support_level=support_level,
            limitations=limitations or [],
        )
        
        db.add(capability)
        await db.flush()
        return capability
    
    async def get_capabilities(
        self, db: AsyncSession, connector_id: str
    ) -> list[ConnectorCapability]:
        'Get all capabilities for a connector.'
        result = await db.execute(
            select(ConnectorCapability).where(ConnectorCapability.connector_id == connector_id)
        )
        return list(result.scalars().all())
    
    # ------------------------------------------------------------ Connector Instance Management
    
    async def create_instance(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_id: str,
        name: str,
        description: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        credentials: Optional[dict[str, Any]] = None,
        auth_type: str = "oauth2",
        auth_config: Optional[dict[str, Any]] = None,
        sync_enabled: bool = True,
        sync_mode: str = "incremental",
        poll_interval_seconds: int = 300,
        full_sync_schedule: Optional[str] = None,
        webhook_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        webhook_events: Optional[list[str]] = None,
        requested_scopes: Optional[list[str]] = None,
        admin_id: Optional[str] = None,
        admin_notes: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> ConnectorInstance:
        'Create a new connector instance for an organization.'
        
        connector = await self.get_connector(db, connector_id)
        if connector is None:
            raise ValueError(f"Connector not found: {connector_id}")
        
        if not connector.enabled:
            raise ValueError(f"Connector is not enabled: {connector_id}")
        
        if connector.deprecated:
            raise ValueError(f"Connector is deprecated: {connector_id}")
        
        # Validate config against connector requirements
        errors = self._validate_instance_config(connector, config or {})
        if errors:
            raise ValueError(f"Invalid instance config: {', '.join(errors)}")
        
        # Validate credentials
        if credentials:
            cred_errors = self._validate_credentials(connector, credentials)
            if cred_errors:
                raise ValueError(f"Invalid credentials: {', '.join(cred_errors)}")
        
        instance = ConnectorInstance(
            organization_id=organization_id,
            connector_id=connector_id,
            name=name,
            description=description,
            config=config or {},
            credentials=credentials or {},
            auth_type=auth_type,
            auth_config=auth_config or {},
            sync_enabled=sync_enabled,
            sync_mode=sync_mode,
            poll_interval_seconds=poll_interval_seconds,
            full_sync_schedule=full_sync_schedule,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            webhook_events=webhook_events or [],
            requested_scopes=requested_scopes or [],
            admin_id=admin_id,
            admin_notes=admin_notes,
            created_by=created_by,
        )
        
        db.add(instance)
        await db.flush()
        
        await publish_event(
            db,
            name="connector_instance.created",
            organization_id=organization_id,
            actor_id=created_by,
            payload={"instance_id": instance.id, "connector_id": connector_id, "name": name},
        )
        
        logger.info("Created connector instance: %s for org %s", name, organization_id)
        return instance
    
    def _validate_instance_config(
        self, connector: Connector, config: dict[str, Any]
    ) -> list[str]:
        'Validate instance config against connector requirements.'
        errors = []
        
        required = connector.required_config_fields or []
        optional = connector.optional_config_fields or []
        
        for field in required:
            if field not in config:
                errors.append(f"Required config field missing: {field}")
        
        # Check for unknown fields only if connector defines allowed fields
        allowed = set(required + optional)
        if allowed:
            for field in config:
                if field not in allowed:
                    errors.append(f"Unknown config field: {field}")
        
        return errors
    
    def _validate_credentials(
        self, connector: Connector, credentials: dict[str, Any]
    ) -> list[str]:
        'Validate credentials based on auth type.'
        errors = []
        
        # This is a basic validation; specific auth types would have more detailed checks
        if not credentials:
            return errors
        
        return errors
    
    async def get_instance(
        self, db: AsyncSession, organization_id: str, instance_id: str
    ) -> Optional[ConnectorInstance]:
        'Get a connector instance by ID.'
        instance = await db.get(ConnectorInstance, instance_id)
        if instance is None or instance.organization_id != organization_id:
            return None
        return instance
    
    async def list_instances(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        connector_id: Optional[str] = None,
        state: Optional[str] = None,
    ) -> list[ConnectorInstance]:
        'List connector instances for an organization.'
        query = select(ConnectorInstance).where(
            ConnectorInstance.organization_id == organization_id
        )
        if connector_id:
            query = query.where(ConnectorInstance.connector_id == connector_id)
        if state:
            query = query.where(ConnectorInstance.state == state)
        query = query.order_by(ConnectorInstance.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def update_instance(
        self,
        db: AsyncSession,
        organization_id: str,
        instance_id: str,
        **fields: Any,
    ) -> Optional[ConnectorInstance]:
        'Update a connector instance.'
        instance = await self.get_instance(db, organization_id, instance_id)
        if instance is None:
            return None
        
        # Validate config changes
        if "config" in fields and fields["config"] is not None:
            connector = await self.get_connector(db, instance.connector_id)
            if connector:
                errors = self._validate_instance_config(connector, fields["config"])
                if errors:
                    raise ValueError(f"Invalid instance config: {', '.join(errors)}")
        
        for key, value in fields.items():
            if value is not None and hasattr(instance, key):
                setattr(instance, key, value)
        
        instance.updated_at = utcnow()
        await db.flush()
        return instance
    
    async def update_instance_state(
        self,
        db: AsyncSession,
        organization_id: str,
        instance_id: str,
        state: str,
        error: Optional[str] = None,
    ) -> Optional[ConnectorInstance]:
        'Update the connection state of an instance.'
        if state not in CONNECTOR_STATES:
            raise ValueError(f"Invalid state: {state}")
        
        instance = await self.get_instance(db, organization_id, instance_id)
        if instance is None:
            return None
        
        old_state = instance.state
        instance.state = state
        instance.error = error
        
        if state == "connected" and old_state != "connected":
            instance.connected_at = utcnow()
            instance.disconnected_at = None
        elif state == "disconnected" and old_state == "connected":
            instance.disconnected_at = utcnow()
        
        if error:
            instance.last_error_at = utcnow()
        
        instance.updated_at = utcnow()
        await db.flush()
        
        await publish_event(
            db,
            name="connector_instance.state_changed",
            organization_id=organization_id,
            payload={
                "instance_id": instance_id,
                "old_state": old_state,
                "new_state": state,
                "error": error,
            },
        )
        
        return instance
    
    async def update_credentials(
        self,
        db: AsyncSession,
        organization_id: str,
        instance_id: str,
        credentials: dict[str, Any],
        expires_at: Optional[datetime] = None,
    ) -> Optional[ConnectorInstance]:
        'Update connector instance credentials.'
        instance = await self.get_instance(db, organization_id, instance_id)
        if instance is None:
            return None
        
        connector = await self.get_connector(db, instance.connector_id)
        if connector:
            errors = self._validate_credentials(connector, credentials)
            if errors:
                raise ValueError(f"Invalid credentials: {', '.join(errors)}")
        
        instance.credentials = credentials
        instance.credentials_updated_at = utcnow()
        if expires_at:
            instance.credentials_expires_at = expires_at
        instance.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="connector_instance.credentials_updated",
            organization_id=organization_id,
            payload={"instance_id": instance_id},
        )
        
        return instance
    
    async def set_webhook_config(
        self,
        db: AsyncSession,
        organization_id: str,
        instance_id: str,
        webhook_url: str,
        webhook_secret: Optional[str] = None,
        webhook_events: Optional[list[str]] = None,
    ) -> Optional[ConnectorInstance]:
        'Configure webhook for a connector instance.'
        instance = await self.get_instance(db, organization_id, instance_id)
        if instance is None:
            return None
        
        connector = await self.get_connector(db, instance.connector_id)
        if connector and not connector.supports_webhooks:
            raise ValueError(f"Connector does not support webhooks: {connector.provider}")
        
        instance.webhook_url = webhook_url
        if webhook_secret:
            instance.webhook_secret = webhook_secret
        if webhook_events:
            instance.webhook_events = webhook_events
        instance.updated_at = utcnow()
        
        await db.flush()
        return instance
    
    async def verify_webhook(
        self,
        db: AsyncSession,
        organization_id: str,
        instance_id: str,
    ) -> Optional[ConnectorInstance]:
        'Mark webhook as verified.'
        instance = await self.get_instance(db, organization_id, instance_id)
        if instance is None:
            return None
        
        instance.webhook_verified = True
        instance.webhook_verified_at = utcnow()
        instance.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="connector_instance.webhook_verified",
            organization_id=organization_id,
            payload={"instance_id": instance_id},
        )
        
        return instance
    
    async def delete_instance(
        self,
        db: AsyncSession,
        organization_id: str,
        instance_id: str,
        actor_id: Optional[str] = None,
    ) -> bool:
        'Delete a connector instance.'
        instance = await self.get_instance(db, organization_id, instance_id)
        if instance is None:
            return False
        
        await db.delete(instance)
        await db.flush()
        
        await publish_event(
            db,
            name="connector_instance.deleted",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"instance_id": instance_id},
        )
        
        return True
    
    # ------------------------------------------------------------ Connection Testing
    
    async def test_connection(
        self,
        db: AsyncSession,
        organization_id: str,
        instance_id: str,
    ) -> dict[str, Any]:
        'Test a connector instance connection.'
        instance = await self.get_instance(db, organization_id, instance_id)
        if instance is None:
            return {"success": False, "error": "Instance not found"}
        
        connector = await self.get_connector(db, instance.connector_id)
        if connector is None:
            return {"success": False, "error": "Connector not found"}
        
        # This is a base implementation; specific connectors should override
        # with actual connection testing logic
        ok = True
        reason = "base connection test passed"
        
        if instance.state == "error":
            ok = False
            reason = instance.error or "previous error state"
        
        new_state = "connected" if ok else "error"
        await self.update_instance_state(db, organization_id, instance_id, new_state, reason if not ok else None)
        
        return {
            "success": ok,
            "state": new_state,
            "detail": reason,
            "tested_at": utcnow().isoformat(),
        }
    
    # ------------------------------------------------------------ Capability Discovery
    
    async def discover_capabilities(
        self, db: AsyncSession, connector_id: str
    ) -> dict[str, Any]:
        'Discover capabilities for a connector.'
        connector = await self.get_connector(db, connector_id)
        if connector is None:
            return {}
        
        capabilities = await self.get_capabilities(db, connector_id)
        
        return {
            "connector_id": connector_id,
            "provider": connector.provider,
            "kind": connector.kind,
            "inbound": connector.inbound_capabilities,
            "outbound": connector.outbound_capabilities,
            "entities": connector.supported_entities,
            "events": connector.supported_events,
            "sync_modes": connector.sync_modes,
            "supports_webhooks": connector.supports_webhooks,
            "supports_polling": connector.supports_polling,
            "detailed_capabilities": [
                {
                    "entity_type": cap.entity_type,
                    "operation": cap.operation,
                    "description": cap.description,
                    "requires_scopes": cap.requires_scopes,
                    "support_level": cap.support_level,
                }
                for cap in capabilities
],
        }

    async def resolve_deep_link(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
        path: str,
    ) -> DeepLinkResolveResponse:
        """Resolve a deep link path to canonical entity data and target URL.
        
        Supports paths like:
            - /company/project/123
            - /company/customer/456
            - /company/meeting/789
            - /company/person/abc
            - /company/task/def
            - /company/decision/ghi
            - /company/commitment/jkl
        
        Returns canonical data and target URL for the web/desktop client.
        """
        path = path.strip("/")
        parts = path.split("/")
        
        if len(parts) < 2:
            raise HTTPException(status_code=400, detail="Invalid deep link path")
        
        # Expected: company/<entity_type>/<entity_id>
        if parts[0] != "company" or len(parts) != 3:
            raise HTTPException(status_code=400, detail="Deep link format: /company/<type>/<id>")
        
        entity_type = parts[1]
        entity_id = parts[2]
        
        # Resolve entity and get canonical data
        canonical_data = await _resolve_entity(db, organization_id, entity_type, entity_id)
        
        if not canonical_data:
            raise HTTPException(status_code=404, detail="Entity not found or not accessible")
        
        # Build target URL
        target_url = _build_deep_link(entity_type, entity_id)
        
        return DeepLinkResolveResponse(
            target_type=entity_type,
            target_id=entity_id,
            target_url=target_url,
            canonical_data=canonical_data,
        )

    # ------------------------------------------------------------ Workspace Settings

    async def get_workspace_settings(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
    ) -> WorkspaceSettings:
        """Get user's workspace personalization settings."""
        result = await db.execute(
            select(WorkspaceSettings).where(
                WorkspaceSettings.organization_id == organization_id,
                WorkspaceSettings.user_id == user_id,
            )
        )
        settings = result.scalar_one_or_none()
        
        if not settings:
            settings = WorkspaceSettings(
                organization_id=organization_id,
                user_id=user_id,
                pinned_items=[],
                shortcuts=[],
                navigation_arrangement={},
                dashboard_arrangement={},
                notification_preferences={},
                favorite_views=[],
                theme="system",
                locale="en",
            )
            db.add(settings)
            await db.flush()
        
        return settings
    
    async def update_workspace_settings(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
        **fields: Any,
    ) -> WorkspaceSettings:
        'Update workspace personalization settings.'
        settings = await self.get_workspace_settings(db, organization_id, user_id)
        
        for key, value in fields.items():
            if value is not None and hasattr(settings, key):
                setattr(settings, key, value)
        
        settings.updated_at = utcnow()
        await db.flush()
        
        return settings


    # ------------------------------------------------------------ Joy & Break Games

    async def list_games(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
    ) -> dict:
        'List available Joy & Break games with cooldown status.'
        from app.models.workspace import GameSession
        
        games = [
            {"id": "brain_blitz", "name": "Brain Blitz", "description": "Quick mental challenges"},
            {"id": "what_happens_next", "name": "What Happens Next?", "description": "Predict the outcome"},
            {"id": "emoji_detective", "name": "Emoji Detective", "description": "Decode the message"},
            {"id": "tiny_genius", "name": "Tiny Genius", "description": "Micro-trivia"},
            {"id": "company_chaos", "name": "Company Chaos", "description": "Fictional scenario simulator"},
        ]
        
        for game in games:
            recent = await db.execute(
                select(GameSession).where(
                    GameSession.organization_id == organization_id,
                    GameSession.user_id == user_id,
                    GameSession.game_id == game["id"],
                    GameSession.started_at >= datetime.now(timezone.utc) - timedelta(hours=12),
                ).order_by(GameSession.started_at.desc())
            )
            last_session = recent.scalars().first()
            if last_session:
                game["available"] = False
                game["cooldown_until"] = (last_session.started_at + timedelta(hours=12)).isoformat()
            else:
                game["available"] = True
                game["cooldown_until"] = None
        
        return {"games": games}
    
    async def start_game(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
        game: str,
    ) -> GameStartResponse:
        'Start a Joy & Break game session.'
        from app.models.workspace import GameSession
        
        valid_games = ["brain_blitz", "what_happens_next", "emoji_detective", "tiny_genius", "company_chaos"]
        if game not in valid_games:
            raise ValueError(f"Invalid game: {game}")
        
        # Check cooldown
        recent = await db.execute(
            select(GameSession).where(
                GameSession.organization_id == organization_id,
                GameSession.user_id == user_id,
                GameSession.game_id == game,
                GameSession.started_at >= datetime.now(timezone.utc) - timedelta(hours=12),
            )
        )
        if recent.scalars().first():
            raise Exception("Game on cooldown. Try again in 12 hours.")
        
        # Create session
        session = GameSession(
            organization_id=organization_id,
            user_id=user_id,
            game_id=game,
            state={"level": 1, "score": 0},
        )
        db.add(session)
        await db.flush()
        
        # Initialize game state
        initial_state = _initialize_game_state(game)
        
        return GameStartResponse(
            game=game,
            session_id=session.id,
            state=initial_state,
            cooldown_until=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        )
    
    async def game_action(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
        session_id: str,
        action: dict,
    ) -> GameActionResponse:
        'Process a game action.'
        from app.models.workspace import GameSession
        
        session = await db.get(GameSession, session_id)
        if not session or session.organization_id != organization_id or session.user_id != user_id:
            raise ValueError("Game session not found")
        
        # Process action based on game type
        new_state, result, completed, score = _process_game_action(
            session.game_id, session.state, action
        )
        
        session.state = new_state
        if completed:
            session.completed_at = datetime.now(timezone.utc)
            session.final_score = score
        
        await db.flush()
        
        return GameActionResponse(
            state=new_state,
            result=result,
            completed=completed,
            score=score,
        )


    # ------------------------------------------------------------ Notifications

    async def get_notifications(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[dict]:
        'Get notification center data as a list of notifications.'
        from app.models.notification import Notification
        
        query = select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.recipient_id == user_id,
        )
        
        if unread_only:
            query = query.where(Notification.is_read == False)
        
        query = query.order_by(Notification.created_at.desc()).limit(limit)
        result = await db.execute(query)
        notifications = result.scalars().all()
        
        return [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "priority": n.priority,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "link": n.link,
            }
            for n in notifications
        ]
    
    async def mark_notification_read(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
        notification_id: str,
    ) -> dict:
        'Mark a notification as read.'
        from app.models.notification import Notification
        
        notification = await db.get(Notification, notification_id)
        if not notification or notification.organization_id != organization_id or notification.recipient_id != user_id:
            raise ValueError("Notification not found")
        
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.flush()
        
        return {"success": True}
    
    async def mark_all_notifications_read(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
    ) -> dict:
        'Mark all notifications as read.'
        from app.models.notification import Notification
        
        await db.execute(
            select(Notification).where(
                Notification.organization_id == organization_id,
                Notification.recipient_id == user_id,
                Notification.is_read == False,
            ).update({Notification.is_read: True, Notification.read_at: datetime.now(timezone.utc)})
        )
        
        return {"success": True}


# ------------------------------------------------------------ Deep Link Helpers

async def _resolve_entity(
    db: AsyncSession,
    organization_id: str,
    entity_type: str,
    entity_id: str,
) -> Optional[dict]:
    'Resolve an entity to its canonical data.'
    from app.models.project import Project
    from app.models.task import Task
    from app.models.meeting import Meeting
    from app.models.employee import Employee
    from app.models.customer import Customer
    from app.models.company_operating import CompanyDecision
    from app.models.execution_strategy import CompanyCommitment
    from app.models.company_actions import CompanyAction
    
    type_to_model = {
        "project": Project,
        "task": Task,
        "meeting": Meeting,
        "person": Employee,
        "customer": "customer",  # Would need Customer model
        "decision": CompanyDecision,
        "commitment": CompanyCommitment,
        "action": CompanyAction,
        "task": Task,
    }
    
    model = type_to_model.get(entity_type)
    if not model:
        return None
    
    if isinstance(model, str):
        # Handle string case (e.g., "customer" without model)
        return None
    
    result = await db.execute(
        select(model).where(
            model.id == entity_id,
            model.organization_id == organization_id,
        )
    )
    entity = result.scalar_one_or_none()
    
    if not entity:
        return None
    
    return {
        "id": entity.id,
        "type": entity_type,
        "title": getattr(entity, "title", getattr(entity, "name", str(entity.id))),
        "status": getattr(entity, "state", getattr(entity, "status", None)),
    }


def _build_deep_link(entity_type: str, entity_id: str) -> str:
    'Build deep link for entity.'
    type_map = {
        "person": "/people",
        "project": "/projects",
        "task": "/tasks",
        "meeting": "/meetings",
        "decision": "/decisions",
        "commitment": "/commitments",
        "action": "/actions",
        "customer": "/customers",
    }
    base = type_map.get(entity_type, "/search")
    return f"{base}/{entity_id}"


# ------------------------------------------------------------ Game Helpers

def _initialize_game_state(game_id: str) -> dict:
    """Initialize game state for a new session."""
    states = {
        "brain_blitz": {"level": 1, "score": 0, "challenge": "memory_sequence", "sequence": [1, 3, 2, 4]},
        "what_happens_next": {"level": 1, "score": 0, "scenario": "project_delay", "options": ["delay", "escalate", "replan", "accept"]},
        "emoji_detective": {"level": 1, "score": 0, "puzzle": "🏢💻📊📈", "answer": "business_growth"},
        "tiny_genius": {"level": 1, "score": 0, "question": "What does ROI stand for?", "options": ["Return on Investment", "Rate of Interest", "Risk of Inflation", "Revenue on Income"]},
        "company_chaos": {"level": 1, "score": 0, "scenario": "server_outage", "role": "engineer", "actions": ["restart", "investigate", "escalate", "communicate"]},
    }
    return states.get(game_id, {"level": 1, "score": 0})


def _process_game_action(game_id: str, state: dict, action: dict) -> tuple[dict, Optional[dict], bool, Optional[int]]:

    """Process a game action and return new state."""

    score = state.get("score", 0)
    
    if game_id == "tiny_genius":
        if action.get("answer") == "Return on Investment":
            score += 10
        return {"level": state["level"] + 1, "score": score, "completed": True}, {"correct": True}, True, score
    
    elif game_id == "brain_blitz":
        if action.get("input") == state.get("sequence"):
            score += 20
        return {"level": state["level"] + 1, "score": score}, {"correct": True}, state["level"] >= 5, score
    
    return state, None, False, score


# ------------------------------------------------------------ Connector Service Class

connector_service = ConnectorService()
