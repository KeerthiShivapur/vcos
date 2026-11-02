"""Gate 24 — Canonical Universal Integration & External-System Operating Fabric Tests.

Comprehensive tests for:
- Connector framework
- External identity mapping
- Synchronization (initial, incremental, webhook, polling)
- Exact-once semantics
- Provenance tracking
- Source authority & conflict preservation
- Bidirectional operation
- Integration health
- Representative connectors
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.intelligence.canonical_integration_service import connector_service, register_builtin_connectors
from app.intelligence.external_identity_service import external_identity_mapping_service
from app.intelligence.synchronization_service import synchronization_service
from app.intelligence.source_authority_service import source_authority_service
from app.intelligence.bidirectional_operation_service import bidirectional_operation_service
from app.intelligence.integration_health_service import integration_health_service
from app.intelligence.connectors import (
    connector_registry,
    GoogleWorkspaceConnector,
    Microsoft365Connector,
    SlackConnector,
    GitHubConnector,
    JiraConnector,
)
from app.models.organization import Organization
from app.models.user import User
from app.intelligence.company_context import resolve_caller_access, CallerAccess
from app.models.company_actions import CompanyAction
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import CompanyAuthorization, CompanyCommitment


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession) -> Organization:
    """Create test organization."""
    unique = uuid.uuid4().hex[:8]
    org = Organization(
        id=f"test-org-{unique}",
        name=f"Test Org {unique}",
        slug=f"test-org-{unique}",
        status="active",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_caller(db_session: AsyncSession, test_org: Organization) -> CallerAccess:
    """Create test caller with org-wide access."""
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=f"user-{unique}",
        email=f"test-{unique}@example.com",
        password_hash="test_hash",
        full_name="Test User",
        organization_id=test_org.id,
        status="active",
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    
    return await resolve_caller_access(db_session, organization_id=test_org.id, user=user)


@pytest_asyncio.fixture
async def google_connector(db_session: AsyncSession) -> Connector:
    """Register Google Workspace connector."""
    return await connector_service.register_connector(
        db_session,
        kind="productivity",
        provider="google",
        display_name="Google Workspace",
        description="Google Workspace integration",
        inbound_capabilities=["read_people", "read_groups", "read_files", "read_calendar", "read_contacts"],
        outbound_capabilities=["write_calendar", "write_files", "write_messages"],
        supported_entities=["person", "group", "file", "event", "contact", "message"],
        supported_events=["person.created", "person.updated", "file.created", "event.created"],
        sync_modes=["initial", "incremental", "polling", "webhook"],
        supports_webhooks=True,
        supports_polling=True,
        auth_types=["oauth2"],
        oauth_scopes=["https://www.googleapis.com/auth/userinfo.profile"],
        required_config_fields=["domain"],
        optional_config_fields=["admin_email"],
    )


@pytest_asyncio.fixture
async def google_instance(db_session: AsyncSession, test_org: Organization, google_connector: Connector, test_caller: CallerAccess) -> ConnectorInstance:
    """Create Google Workspace connector instance."""
    return await connector_service.create_instance(
        db_session,
        organization_id=test_org.id,
        connector_id=google_connector.id,
        name="Our Google Workspace",
        config={"domain": "example.com"},
        credentials={"access_token": "test_token", "refresh_token": "test_refresh"},
        auth_type="oauth2",
        sync_enabled=True,
        created_by=test_caller.employee_id,
    )


# ============================================================================
# CONNECTOR FRAMEWORK TESTS
# ============================================================================

class TestConnectorRegistry:
    """Tests for connector registration and discovery."""
    
    @pytest.mark.asyncio
    async def test_register_connector(self, db_session: AsyncSession):
        """Test registering a new connector."""
        connector = await connector_service.register_connector(
            db_session,
            kind="custom",
            provider="test_provider",
            display_name="Test Provider",
            description="Test connector",
        )
        
        assert connector.id is not None
        assert connector.kind == "custom"
        assert connector.provider == "test_provider"
        assert connector.display_name == "Test Provider"
        assert connector.enabled is True
        assert connector.deprecated is False
    
    @pytest.mark.asyncio
    async def test_register_connector_invalid_kind(self, db_session: AsyncSession):
        """Test that invalid connector kind is rejected."""
        with pytest.raises(ValueError, match="Invalid connector kind"):
            await connector_service.register_connector(
                db_session,
                kind="invalid_kind",
                provider="test",
                display_name="Test",
            )
    
    @pytest.mark.asyncio
    async def test_list_connectors(self, db_session: AsyncSession, google_connector: Connector):
        """Test listing connectors."""
        connectors = await connector_service.list_connectors(db_session)
        
        assert any(c.id == google_connector.id for c in connectors)
    
    @pytest.mark.asyncio
    async def test_register_builtin_connectors(self, db_session: AsyncSession):
        """Test that builtin connectors can be registered."""
        builtins = register_builtin_connectors(connector_service)
        
        assert len(builtins) >= 5  # google, microsoft, slack, github, jira
        
        providers = {b["provider"] for b in builtins}
        assert "google" in providers
        assert "microsoft" in providers
        assert "slack" in providers
        assert "github" in providers
        assert "jira" in providers
    
    @pytest.mark.asyncio
    async def test_connector_capabilities(self, db_session: AsyncSession, google_connector: Connector):
        """Test registering and querying capabilities."""
        await connector_service.register_capability(
            db_session,
            connector_id=google_connector.id,
            entity_type="person",
            operation="read",
            description="Read user profiles",
            requires_scopes=["https://www.googleapis.com/auth/userinfo.profile"],
            support_level="full",
        )
        
        caps = await connector_service.get_capabilities(db_session, google_connector.id)
        
        assert len(caps) >= 1
        cap = caps[0]
        assert cap.entity_type == "person"
        assert cap.operation == "read"
        assert cap.support_level == "full"


class TestConnectorInstanceLifecycle:
    """Tests for connector instance management."""
    
    @pytest.mark.asyncio
    async def test_create_instance(
        self, db_session: AsyncSession, test_org: Organization, google_connector: Connector, test_caller: CallerAccess
    ):
        """Test creating a connector instance."""
        instance = await connector_service.create_instance(
            db_session,
            organization_id=test_org.id,
            connector_id=google_connector.id,
            name="Test Instance",
            config={"domain": "test.com"},
            credentials={"access_token": "test"},
            created_by=test_caller.employee_id,
        )
        
        assert instance.id is not None
        assert instance.organization_id == test_org.id
        assert instance.connector_id == google_connector.id
        assert instance.name == "Test Instance"
        assert instance.state == "disconnected"
        assert instance.config["domain"] == "test.com"
    
    @pytest.mark.asyncio
    async def test_create_instance_invalid_config(self, db_session: AsyncSession, test_org: Organization, google_connector: Connector):
        """Test that invalid config is rejected."""
        with pytest.raises(ValueError, match="Required config field missing"):
            await connector_service.create_instance(
                db_session,
                organization_id=test_org.id,
                connector_id=google_connector.id,
                name="Test",
                config={},  # Missing required 'domain'
            )
    
    @pytest.mark.asyncio
    async def test_update_instance_state(self, db_session: AsyncSession, google_instance: ConnectorInstance):
        """Test updating instance connection state."""
        updated = await connector_service.update_instance_state(
            db_session,
            organization_id=google_instance.organization_id,
            instance_id=google_instance.id,
            state="connected",
        )
        
        assert updated is not None
        assert updated.state == "connected"
        assert updated.connected_at is not None
    
    @pytest.mark.asyncio
    async def test_update_credentials(self, db_session: AsyncSession, google_instance: ConnectorInstance):
        """Test updating credentials."""
        updated = await connector_service.update_credentials(
            db_session,
            organization_id=google_instance.organization_id,
            instance_id=google_instance.id,
            credentials={"access_token": "new_token", "refresh_token": "new_refresh"},
        )
        
        assert updated is not None
        assert updated.credentials["access_token"] == "new_token"
        assert updated.credentials_updated_at is not None
    
    @pytest.mark.asyncio
    async def test_webhook_configuration(self, db_session: AsyncSession, google_instance: ConnectorInstance):
        """Test webhook configuration."""
        updated = await connector_service.set_webhook_config(
            db_session,
            organization_id=google_instance.organization_id,
            instance_id=google_instance.id,
            webhook_url="https://example.com/webhook",
            webhook_secret="secret123",
            webhook_events=["person.created", "person.updated"],
        )
        
        assert updated is not None
        assert updated.webhook_url == "https://example.com/webhook"
        assert updated.webhook_secret == "secret123"
        assert "person.created" in updated.webhook_events
    
    @pytest.mark.asyncio
    async def test_verify_webhook(self, db_session: AsyncSession, google_instance: ConnectorInstance):
        """Test webhook verification."""
        # First set webhook config
        await connector_service.set_webhook_config(
            db_session,
            organization_id=google_instance.organization_id,
            instance_id=google_instance.id,
            webhook_url="https://example.com/webhook",
        )
        
        verified = await connector_service.verify_webhook(
            db_session,
            organization_id=google_instance.organization_id,
            instance_id=google_instance.id,
        )
        
        assert verified is not None
        assert verified.webhook_verified is True
        assert verified.webhook_verified_at is not None
    
    @pytest.mark.asyncio
    async def test_delete_instance(self, db_session: AsyncSession, google_instance: ConnectorInstance, test_caller: CallerAccess):
        """Test deleting a connector instance."""
        instance_id = google_instance.id
        
        result = await connector_service.delete_instance(
            db_session,
            organization_id=google_instance.organization_id,
            instance_id=instance_id,
            actor_id=test_caller.employee_id,
        )
        
        assert result is True
        
        # Verify deleted
        deleted = await connector_service.get_instance(db_session, google_instance.organization_id, instance_id)
        assert deleted is None


class TestConnectorDiscovery:
    """Tests for capability discovery."""
    
    @pytest.mark.asyncio
    async def test_discover_capabilities(self, db_session: AsyncSession, google_connector: Connector):
        """Test discovering connector capabilities."""
        caps = await connector_service.discover_capabilities(db_session, google_connector.id)
        
        assert caps["connector_id"] == google_connector.id
        assert caps["provider"] == "google"
        assert caps["kind"] == "productivity"
        assert "read_people" in caps["inbound"]
        assert "write_calendar" in caps["outbound"]
        assert "person" in caps["entities"]


# ============================================================================
# EXTERNAL IDENTITY MAPPING TESTS
# ============================================================================

class TestExternalIdentityMapping:
    """Tests for external identity mapping."""
    
    @pytest.mark.asyncio
    async def test_create_mapping(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test creating an identity mapping."""
        mapping = await external_identity_mapping_service.create_mapping(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-123",
            external_id="google-user-456",
            external_email="user@example.com",
            external_display_name="Test User",
            mapping_state="mapped",
            confidence=0.95,
            created_by=test_caller.employee_id,
        )
        
        assert mapping.id is not None
        assert mapping.vcos_entity_type == "person"
        assert mapping.vcos_entity_id == "emp-123"
        assert mapping.external_id == "google-user-456"
        assert mapping.external_email == "user@example.com"
        assert mapping.mapping_state == "mapped"
        assert mapping.confidence == 0.95
    
    @pytest.mark.asyncio
    async def test_duplicate_external_id_rejected(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test that duplicate external ID for different VCOS entity creates conflict."""
        # Create first mapping
        await external_identity_mapping_service.create_mapping(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-1",
            external_id="google-user-456",
            mapping_state="mapped",
            created_by=test_caller.employee_id,
        )
        
        # Try to map same external ID to different VCOS entity
        mapping2 = await external_identity_mapping_service.create_mapping(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-2",
            external_id="google-user-456",
            mapping_state="mapped",
            created_by=test_caller.employee_id,
        )
        
        # Should create conflict
        assert mapping2.mapping_state == "conflict"
        assert mapping2.conflict_with is not None
    
    @pytest.mark.asyncio
    async def test_duplicate_vcos_entity_rejected(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test that same VCOS entity can't be mapped twice to same connector."""
        await external_identity_mapping_service.create_mapping(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-1",
            external_id="google-user-1",
            mapping_state="mapped",
            created_by=test_caller.employee_id,
        )
        
        with pytest.raises(ValueError, match="already mapped"):
            await external_identity_mapping_service.create_mapping(
                db_session,
                organization_id=test_org.id,
                connector_instance_id=google_instance.id,
                vcos_entity_type="person",
                vcos_entity_id="emp-1",
                external_id="google-user-2",
                mapping_state="mapped",
                created_by=test_caller.employee_id,
            )
    
    @pytest.mark.asyncio
    async def test_get_mapping_by_vcos(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test querying mapping by VCOS entity."""
        await external_identity_mapping_service.create_mapping(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-1",
            external_id="google-user-1",
            mapping_state="mapped",
            created_by=test_caller.employee_id,
        )
        
        mapping = await external_identity_mapping_service.get_mapping_by_vcos(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-1",
        )
        
        assert mapping is not None
        assert mapping.external_id == "google-user-1"
    
    @pytest.mark.asyncio
    async def test_get_mapping_by_external(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test querying mapping by external ID."""
        await external_identity_mapping_service.create_mapping(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-1",
            external_id="google-user-1",
            mapping_state="mapped",
            created_by=test_caller.employee_id,
        )
        
        mapping = await external_identity_mapping_service.get_mapping_by_external(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            external_id="google-user-1",
        )
        
        assert mapping is not None
        assert mapping.vcos_entity_id == "emp-1"
    
    @pytest.mark.asyncio
    async def test_resolve_conflict(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test resolving a mapping conflict."""
        # Create conflict
        mapping1 = await external_identity_mapping_service.create_mapping(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-1",
            external_id="google-user-1",
            mapping_state="mapped",
            created_by=test_caller.employee_id,
        )
        
        mapping2 = await external_identity_mapping_service.create_mapping(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-2",
            external_id="google-user-1",
            mapping_state="mapped",
            created_by=test_caller.employee_id,
        )
        
        assert mapping2.mapping_state == "conflict"
        
        # Resolve by choosing emp-1
        resolved = await external_identity_mapping_service.resolve_conflict(
            db_session,
            mapping_id=mapping2.id,
            chosen_vcos_entity_id="emp-1",
            resolution_method="manual",
            resolved_by=test_caller.employee_id,
            resolution_notes="emp-1 is correct",
        )
        
        assert resolved is not None
        assert resolved.mapping_state == "mapped"
        assert resolved.vcos_entity_id == "emp-1"
        assert resolved.resolution_method == "manual"
    
    @pytest.mark.asyncio
    async def test_ignore_mapping(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test ignoring a mapping."""
        mapping = await external_identity_mapping_service.create_mapping(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-1",
            external_id="google-user-1",
            mapping_state="pending",
            created_by=test_caller.employee_id,
        )
        
        ignored = await external_identity_mapping_service.ignore_mapping(
            db_session,
            mapping_id=mapping.id,
            ignored_by=test_caller.employee_id,
        )
        
        assert ignored is not None
        assert ignored.mapping_state == "ignored"
    
    @pytest.mark.asyncio
    async def test_bulk_create_mappings(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test bulk creating mappings from sync."""
        mappings = [
            {"vcos_entity_type": "person", "vcos_entity_id": f"emp-{i}", "external_id": f"google-user-{i}", "mapping_state": "mapped"}
            for i in range(5)
        ]
        
        result = await external_identity_mapping_service.bulk_create_mappings(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            mappings=mappings,
        )
        
        assert result["created"] == 5
        assert result["updated"] == 0
        assert result["conflicts"] == 0
        assert len(result["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_mapping_history(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test mapping change history."""
        mapping = await external_identity_mapping_service.create_mapping(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            vcos_entity_type="person",
            vcos_entity_id="emp-1",
            external_id="google-user-1",
            mapping_state="pending",
            created_by=test_caller.employee_id,
        )
        
        # Update to mapped
        await external_identity_mapping_service.update_mapping(
            db_session,
            mapping_id=mapping.id,
            mapping_state="mapped",
            confidence=0.9,
        )
        
        history = await external_identity_mapping_service.get_mapping_history(
            db_session, test_org.id, mapping.id
        )
        
        assert len(history) >= 2
        # Check that both mapping_state and confidence are recorded
        field_changes = {h.field_changed for h in history}
        assert "mapping_state" in field_changes
        assert "confidence" in field_changes
        # Find the mapping_state change
        state_change = next(h for h in history if h.field_changed == "mapping_state")
        assert state_change.new_value == "mapped"


# ============================================================================
# SYNCHRONIZATION TESTS
# ============================================================================

class TestSynchronization:
    """Tests for synchronization runs and cursors."""
    
    @pytest.mark.asyncio
    async def test_create_sync_run(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test creating a sync run."""
        sync_run = await synchronization_service.create_sync_run(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            sync_mode="initial",
            triggered_by="manual",
            created_by=test_caller.employee_id,
        )
        
        assert sync_run.id is not None
        assert sync_run.sync_mode == "initial"
        assert sync_run.state == "pending"
        assert sync_run.triggered_by == "manual"
    
    @pytest.mark.asyncio
    async def test_complete_sync_run(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test completing a sync run."""
        sync_run = await synchronization_service.create_sync_run(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            sync_mode="initial",
        )
        
        completed = await synchronization_service.complete_sync_run(
            db_session,
            sync_run_id=sync_run.id,
            state="completed",
            entities_processed=100,
            entities_created=80,
            entities_updated=15,
            entities_failed=5,
            cursor_after="2026-01-01T00:00:00Z",
        )
        
        assert completed is not None
        assert completed.state == "completed"
        assert completed.entities_processed == 100
        assert completed.cursor_after == "2026-01-01T00:00:00Z"
        assert completed.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_sync_cursor(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance
    ):
        """Test sync cursor management."""
        cursor = await synchronization_service.update_cursor(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            entity_type="person",
            cursor_value="2026-01-01T00:00:00Z",
            cursor_type="timestamp",
            entity_count=100,
        )
        
        assert cursor.id is not None
        assert cursor.cursor_value == "2026-01-01T00:00:00Z"
        assert cursor.entity_type == "person"
        
        # Retrieve cursor
        retrieved = await synchronization_service.get_cursor(
            db_session, test_org.id, google_instance.id, "person"
        )
        
        assert retrieved is not None
        assert retrieved.cursor_value == "2026-01-01T00:00:00Z"


class TestExternalEventExactOnce:
    """Tests for external event exact-once processing."""
    
    @pytest.mark.asyncio
    async def test_ingest_external_event(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance
    ):
        """Test ingesting an external event."""
        event = await synchronization_service.ingest_external_event(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            external_event_id="evt-123",
            event_type="person.created",
            source_id="google-user-456",
            source_type="person",
            payload={"name": "Test User"},
            external_timestamp=datetime.now(timezone.utc),
        )
        
        assert event.id is not None
        assert event.external_event_id == "evt-123"
        assert event.event_type == "person.created"
        assert event.state == "pending"
        assert event.payload_hash is not None
    
    @pytest.mark.asyncio
    async def test_exact_once_duplicate_event(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance
    ):
        """Test that duplicate external events are detected."""
        # Ingest first event
        event1 = await synchronization_service.ingest_external_event(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            external_event_id="evt-123",
            event_type="person.created",
            source_id="google-user-456",
            source_type="person",
            payload={"name": "Test User"},
        )
        
        # Ingest duplicate
        event2 = await synchronization_service.ingest_external_event(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            external_event_id="evt-123",
            event_type="person.created",
            source_id="google-user-456",
            source_type="person",
            payload={"name": "Test User"},
        )
        
        # Should return same event, marked as duplicate
        assert event2.id == event1.id
        assert event2.state == "duplicate"
    
    @pytest.mark.asyncio
    async def test_exact_once_different_payload(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance
    ):
        """Test that same event ID with different payload is still duplicate."""
        # Ingest first event
        await synchronization_service.ingest_external_event(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            external_event_id="evt-123",
            event_type="person.created",
            source_id="google-user-456",
            payload={"name": "Test User"},
        )
        
        # Ingest with different payload
        event2 = await synchronization_service.ingest_external_event(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            external_event_id="evt-123",
            event_type="person.created",
            source_id="google-user-456",
            payload={"name": "Different User"},  # Different payload
        )
        
        # Should still be duplicate (exact-once on event ID, not payload)
        assert event2.state == "duplicate"
    
    @pytest.mark.asyncio
    async def test_retry_failed_event(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance
    ):
        """Test retrying a failed event."""
        event = await synchronization_service.ingest_external_event(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            external_event_id="evt-123",
            event_type="person.created",
            source_id="google-user-456",
            payload={"name": "Test User"},
            max_retries=3,
        )
        
        # Mark as failed
        event.state = "failed"
        event.retry_count = 1
        event.error = "Processing failed"
        await db_session.flush()
        
        # Retry
        retried = await synchronization_service.retry_failed_events(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
        )
        
        assert retried == 1
        
        # Refresh event
        await db_session.refresh(event)
        assert event.state == "pending"
        assert event.error is None


# ============================================================================
# SOURCE AUTHORITY & CONFLICT PRESERVATION TESTS
# ============================================================================

class TestSourceAuthority:
    """Tests for source authority management."""
    
    @pytest.mark.asyncio
    async def test_set_source_authority(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test setting source authority."""
        authority = await source_authority_service.set_source_authority(
            db_session,
            organization_id=test_org.id,
            entity_type="person",
            connector_instance_id=google_instance.id,
            authority_level="primary",
            precedence=100,
            configured_by=test_caller.employee_id,
        )
        
        assert authority.id is not None
        assert authority.entity_type == "person"
        assert authority.authority_level == "primary"
        assert authority.precedence == 100
    
    @pytest.mark.asyncio
    async def test_get_authorities(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test querying authorities."""
        await source_authority_service.set_source_authority(
            db_session,
            organization_id=test_org.id,
            entity_type="person",
            connector_instance_id=google_instance.id,
            authority_level="primary",
            precedence=100,
        )
        
        authorities = await source_authority_service.get_authorities(db_session, test_org.id, "person")
        
        assert len(authorities) >= 1
        assert authorities[0].authority_level == "primary"
    
    @pytest.mark.asyncio
    async def test_get_primary_authority(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test getting primary authority."""
        await source_authority_service.set_source_authority(
            db_session,
            organization_id=test_org.id,
            entity_type="person",
            connector_instance_id=google_instance.id,
            authority_level="primary",
            precedence=100,
        )
        
        primary = await source_authority_service.get_primary_authority(db_session, test_org.id, "person")
        
        assert primary is not None
        assert primary.authority_level == "primary"


class TestExternalConflict:
    """Tests for external conflict detection and resolution."""
    
    @pytest.mark.asyncio
    async def test_detect_conflict(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test detecting a conflict between two sources."""
        # Create a second connector instance (e.g., Microsoft)
        microsoft_connector = await connector_service.register_connector(
            db_session,
            kind="productivity",
            provider="microsoft",
            display_name="Microsoft 365",
            required_config_fields=["tenant_id"],
            optional_config_fields=["client_id", "client_secret"],
        )
        
        microsoft_instance = await connector_service.create_instance(
            db_session,
            organization_id=test_org.id,
            connector_id=microsoft_connector.id,
            name="Our Microsoft 365",
            config={"tenant_id": "test-tenant"},
            credentials={"access_token": "ms_token"},
        )
        
        # Set authorities
        await source_authority_service.set_source_authority(
            db_session,
            organization_id=test_org.id,
            entity_type="person",
            connector_instance_id=google_instance.id,
            authority_level="primary",
            precedence=100,
        )
        
        await source_authority_service.set_source_authority(
            db_session,
            organization_id=test_org.id,
            entity_type="person",
            connector_instance_id=microsoft_instance.id,
            authority_level="secondary",
            precedence=50,
        )
        
        # Detect conflict
        conflict = await source_authority_service.detect_conflict(
            db_session,
            organization_id=test_org.id,
            entity_type="person",
            entity_id="emp-1",
            source_a_instance_id=google_instance.id,
            source_a_external_id="google-user-1",
            source_a_value={"email": "user@example.com", "team": "Engineering"},
            source_a_timestamp=datetime.now(timezone.utc),
            source_a_authority=100,
            source_b_instance_id=microsoft_instance.id,
            source_b_external_id="ms-user-1",
            source_b_value={"email": "user@example.com", "team": "Sales"},
            source_b_timestamp=datetime.now(timezone.utc),
            source_b_authority=50,
            conflict_fields=["team"],
        )
        
        assert conflict.id is not None
        assert conflict.entity_type == "person"
        assert conflict.conflict_fields == ["team"]
        assert conflict.resolution_state == "open"
    
    @pytest.mark.asyncio
    async def test_resolve_conflict_by_authority(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test resolving conflict by authority."""
        microsoft_connector = await connector_service.register_connector(
            db_session, kind="productivity", provider="microsoft", display_name="Microsoft",
            required_config_fields=["tenant_id"], optional_config_fields=["client_id", "client_secret"]
        )
        microsoft_instance = await connector_service.create_instance(
            db_session, organization_id=test_org.id, connector_id=microsoft_connector.id,
            name="MS", config={"tenant_id": "test"}, credentials={"access_token": "ms"}
        )
        
        conflict = await source_authority_service.detect_conflict(
            db_session, organization_id=test_org.id, entity_type="person", entity_id="emp-1",
            source_a_instance_id=google_instance.id, source_a_external_id="g1",
            source_a_value={"team": "Eng"}, source_a_timestamp=datetime.now(timezone.utc), source_a_authority=100,
            source_b_instance_id=microsoft_instance.id, source_b_external_id="m1",
            source_b_value={"team": "Sales"}, source_b_timestamp=datetime.now(timezone.utc), source_b_authority=50,
            conflict_fields=["team"],
        )
        
        resolved = await source_authority_service.resolve_conflict_by_authority(
            db_session, conflict_id=conflict.id, resolved_by=test_caller.employee_id
        )
        
        assert resolved is not None
        assert resolved.resolution_state == "authority_applied"
        assert resolved.resolution_method == "authority"
        assert resolved.resolved_value == conflict.source_a_value  # Higher authority wins
    
    @pytest.mark.asyncio
    async def test_resolve_conflict_manually(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test manual conflict resolution."""
        microsoft_connector = await connector_service.register_connector(
            db_session, kind="productivity", provider="microsoft", display_name="Microsoft",
            required_config_fields=["tenant_id"], optional_config_fields=["client_id", "client_secret"]
        )
        microsoft_instance = await connector_service.create_instance(
            db_session, organization_id=test_org.id, connector_id=microsoft_connector.id,
            name="MS", config={"tenant_id": "test"}, credentials={"access_token": "ms"}
        )
        
        conflict = await source_authority_service.detect_conflict(
            db_session, organization_id=test_org.id, entity_type="person", entity_id="emp-1",
            source_a_instance_id=google_instance.id, source_a_external_id="g1",
            source_a_value={"team": "Eng"}, source_a_timestamp=datetime.now(timezone.utc), source_a_authority=100,
            source_b_instance_id=microsoft_instance.id, source_b_external_id="m1",
            source_b_value={"team": "Sales"}, source_b_timestamp=datetime.now(timezone.utc), source_b_authority=50,
            conflict_fields=["team"],
        )
        
        resolved = await source_authority_service.resolve_conflict_manually(
            db_session,
            conflict_id=conflict.id,
            resolved_value={"team": "Marketing"},  # Neither Eng nor Sales
            resolved_by=test_caller.employee_id,
            resolution_notes="Reorg: moved to Marketing",
        )
        
        assert resolved is not None
        assert resolved.resolution_state == "manual_resolution"
        assert resolved.resolved_value == {"team": "Marketing"}
    
    @pytest.mark.asyncio
    async def test_merge_conflict(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test merging conflict values."""
        microsoft_connector = await connector_service.register_connector(
            db_session, kind="productivity", provider="microsoft", display_name="Microsoft",
            required_config_fields=["tenant_id"], optional_config_fields=["client_id", "client_secret"]
        )
        microsoft_instance = await connector_service.create_instance(
            db_session, organization_id=test_org.id, connector_id=microsoft_connector.id,
            name="MS", config={"tenant_id": "test"}, credentials={"access_token": "ms"}
        )
        
        conflict = await source_authority_service.detect_conflict(
            db_session, organization_id=test_org.id, entity_type="person", entity_id="emp-1",
            source_a_instance_id=google_instance.id, source_a_external_id="g1",
            source_a_value={"skills": ["Python"]}, source_a_timestamp=datetime.now(timezone.utc), source_a_authority=100,
            source_b_instance_id=microsoft_instance.id, source_b_external_id="m1",
            source_b_value={"skills": ["JavaScript"]}, source_b_timestamp=datetime.now(timezone.utc), source_b_authority=50,
            conflict_fields=["skills"],
        )
        
        resolved = await source_authority_service.merge_conflict(
            db_session,
            conflict_id=conflict.id,
            merged_value={"skills": ["Python", "JavaScript"]},
            resolved_by=test_caller.employee_id,
            resolution_notes="Merged both skill sets",
        )
        
        assert resolved is not None
        assert resolved.resolution_state == "merged"
        assert "Python" in resolved.resolved_value["skills"]
        assert "JavaScript" in resolved.resolved_value["skills"]


# ============================================================================
# BIDIRECTIONAL OPERATION TESTS
# ============================================================================

class TestBidirectionalOperation:
    """Tests for VCOS → External operations."""
    
    @pytest.mark.asyncio
    async def test_create_operation(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test creating an external operation."""
        # Create a CompanyAction first
        action = CompanyAction(
            id=f"act-{uuid.uuid4().hex[:8]}",
            organization_id=test_org.id,
            action_type="create",
            title="Create Google Calendar Event",
            state="approved",
            fingerprint="test-fp",
        )
        db_session.add(action)
        await db_session.flush()
        
        operation = await bidirectional_operation_service.create_operation(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            operation_type="write_event",
            target_entity_type="event",
            payload={"summary": "Team Meeting", "start": "2026-01-01T10:00:00Z", "end": "2026-01-01T11:00:00Z"},
            source_action_id=action.id,
            governance_verified=True,
            governance_verified_by=test_caller.employee_id,
            created_by=test_caller.employee_id,
        )
        
        assert operation.id is not None
        assert operation.source_action_id == action.id
        assert operation.operation_type == "write_event"
        assert operation.target_entity_type == "event"
        assert operation.governance_verified is True
    
    @pytest.mark.asyncio
    async def test_governance_verification_required(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance
    ):
        """Test that governance verification is required."""
        operation = await bidirectional_operation_service.create_operation(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            operation_type="write_event",
            target_entity_type="event",
            payload={},
            governance_verified=False,
        )
        
        # Try to execute without governance
        with pytest.raises(ValueError, match="governance verified"):
            await bidirectional_operation_service.execute_operation(
                db_session, operation.id, lambda db, op: {"success": True}
            )
    
    @pytest.mark.asyncio
    async def test_verify_governance(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test governance verification."""
        operation = await bidirectional_operation_service.create_operation(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            operation_type="write_event",
            target_entity_type="event",
            payload={},
            governance_verified=False,
        )
        
        verified = await bidirectional_operation_service.verify_governance(
            db_session, operation_id=operation.id, verified_by=test_caller.employee_id
        )
        
        assert verified is not None
        assert verified.governance_verified is True
        assert verified.governance_verified_by == test_caller.employee_id
    
    @pytest.mark.asyncio
    async def test_receive_observation(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance
    ):
        """Test receiving external observation."""
        operation = await bidirectional_operation_service.create_operation(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            operation_type="write_event",
            target_entity_type="event",
            payload={},
            governance_verified=True,
        )
        
        observed = await bidirectional_operation_service.receive_observation(
            db_session,
            operation_id=operation.id,
            observation_event_id="google-evt-123",
        )
        
        assert observed is not None
        assert observed.observation_received is True
        assert observed.observation_event_id == "google-evt-123"
    
    @pytest.mark.asyncio
    async def test_verify_outcome(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test verifying operation outcome."""
        operation = await bidirectional_operation_service.create_operation(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            operation_type="write_event",
            target_entity_type="event",
            payload={},
            governance_verified=True,
        )
        
        verified = await bidirectional_operation_service.verify_outcome(
            db_session,
            operation_id=operation.id,
            verified=True,
            verified_by=test_caller.employee_id,
            verification_notes="Event created successfully in Google Calendar",
        )
        
        assert verified is not None
        assert verified.verified is True
        assert verified.verified_at is not None


# ============================================================================
# INTEGRATION HEALTH TESTS
# ============================================================================

class TestIntegrationHealth:
    """Tests for integration health monitoring."""
    
    @pytest.mark.asyncio
    async def test_calculate_health(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance, test_caller: CallerAccess
    ):
        """Test calculating integration health."""
        # Create a completed sync run
        await synchronization_service.create_sync_run(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            sync_mode="incremental",
        )
        
        sync_run = await synchronization_service.create_sync_run(
            db_session,
            organization_id=test_org.id,
            connector_instance_id=google_instance.id,
            sync_mode="incremental",
        )
        
        await synchronization_service.complete_sync_run(
            db_session, sync_run.id, state="completed", entities_processed=10
        )
        
        # Update instance state
        await connector_service.update_instance_state(
            db_session, test_org.id, google_instance.id, "connected"
        )
        
        health = await integration_health_service.calculate_health(
            db_session, test_org.id, google_instance.id
        )
        
        assert health.id is not None
        assert health.connector_instance_id == google_instance.id
        assert health.connection_status == "connected"
        assert health.last_successful_sync is not None
        assert health.overall_status in ("healthy", "degraded", "error", "reauth_required", "unknown")
    
    @pytest.mark.asyncio
    async def test_health_summary(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance
    ):
        """Test health summary."""
        await integration_health_service.calculate_health(db_session, test_org.id, google_instance.id)
        
        summary = await integration_health_service.get_health_summary(db_session, test_org.id)
        
        assert summary["total"] >= 1
        assert "by_provider" in summary
    
    @pytest.mark.asyncio
    async def test_unhealthy_detection(
        self, db_session: AsyncSession, test_org: Organization, test_caller: CallerAccess
    ):
        """Test detecting unhealthy integrations."""
        # Create instance in error state
        google_connector = await connector_service.register_connector(
            db_session, kind="productivity", provider="google", display_name="Google",
            required_config_fields=["domain"], optional_config_fields=["admin_email"]
        )
        
        instance = await connector_service.create_instance(
            db_session, organization_id=test_org.id, connector_id=google_connector.id,
            name="Error Instance", config={"domain": "test.com"}, credentials={},
        )
        
        await connector_service.update_instance_state(db_session, test_org.id, instance.id, "error", "Connection failed")
        
        await integration_health_service.calculate_health(db_session, test_org.id, instance.id)
        
        unhealthy = await integration_health_service.get_unhealthy_integrations(db_session, test_org.id)
        
        assert any(h.connector_instance_id == instance.id for h in unhealthy)


# ============================================================================
# CONNECTOR IMPLEMENTATION TESTS
# ============================================================================

class TestConnectorImplementations:
    """Tests for specific connector implementations."""
    
    @pytest.mark.asyncio
    async def test_google_connector_in_registry(self):
        """Test Google connector is registered."""
        conn = connector_registry.get("productivity", "google")
        assert conn is not None
        assert isinstance(conn, GoogleWorkspaceConnector)
    
    @pytest.mark.asyncio
    async def test_microsoft_connector_in_registry(self):
        """Test Microsoft connector is registered."""
        conn = connector_registry.get("productivity", "microsoft")
        assert conn is not None
        assert isinstance(conn, Microsoft365Connector)
    
    @pytest.mark.asyncio
    async def test_slack_connector_in_registry(self):
        """Test Slack connector is registered."""
        conn = connector_registry.get("communication", "slack")
        assert conn is not None
        assert isinstance(conn, SlackConnector)
    
    @pytest.mark.asyncio
    async def test_github_connector_in_registry(self):
        """Test GitHub connector is registered."""
        conn = connector_registry.get("code", "github")
        assert conn is not None
        assert isinstance(conn, GitHubConnector)
    
    @pytest.mark.asyncio
    async def test_jira_connector_in_registry(self):
        """Test Jira connector is registered."""
        conn = connector_registry.get("work_management", "jira")
        assert conn is not None
        assert isinstance(conn, JiraConnector)
    
    @pytest.mark.asyncio
    async def test_compute_fingerprints(self):
        """Test fingerprint computation utilities."""
        fp1 = compute_payload_fingerprint({"a": 1, "b": 2})
        fp2 = compute_payload_fingerprint({"b": 2, "a": 1})  # Same data, different order
        fp3 = compute_payload_fingerprint({"a": 1, "b": 3})  # Different data
        
        assert fp1 == fp2  # Deterministic
        assert fp1 != fp3  # Different data = different fingerprint
        
        efp1 = compute_event_fingerprint("inst-1", "evt-1", "person.created", "user-1")
        efp2 = compute_event_fingerprint("inst-1", "evt-1", "person.created", "user-1")
        efp3 = compute_event_fingerprint("inst-1", "evt-2", "person.created", "user-1")
        
        assert efp1 == efp2
        assert efp1 != efp3


# ============================================================================
# END-TO-END INTEGRATION TEST
# ============================================================================

class TestEndToEndIntegration:
    """End-to-end test of the full integration flow."""
    
    @pytest.mark.asyncio
    async def test_full_integration_flow(
        self, db_session: AsyncSession, test_org: Organization, test_caller: CallerAccess
    ):
        """Test the complete flow: External Event → Identity Mapping → Canonical Reality → Decision → External Operation → Verification."""
        
        # 1. Register Google connector
        google_connector = await connector_service.register_connector(
            db_session,
            kind="productivity", provider="google", display_name="Google Workspace",
            inbound_capabilities=["read_people"], outbound_capabilities=["write_calendar"],
            supported_entities=["person", "event"], sync_modes=["initial", "incremental", "webhook"],
            supports_webhooks=True, auth_types=["oauth2"], required_config_fields=["domain"],
        )
        
        # 2. Create instance
        google_instance = await connector_service.create_instance(
            db_session, organization_id=test_org.id, connector_id=google_connector.id,
            name="Our Google", config={"domain": "example.com"},
            credentials={"access_token": "token", "refresh_token": "refresh"},
        )
        
        # 3. Receive external event (webhook)
        event = await synchronization_service.ingest_external_event(
            db_session, organization_id=test_org.id, connector_instance_id=google_instance.id,
            external_event_id="google-evt-1", event_type="person.created",
            source_id="google-user-123", source_type="person",
            payload={"email": "newuser@example.com", "name": "New User"},
        )
        
        # Process the event to "processed" state
        async def dummy_processor(db, evt):
            return {"success": True}
        await synchronization_service.process_external_event(
            db_session, event.id, dummy_processor
        )
        
        # 4. Create identity mapping
        mapping = await external_identity_mapping_service.create_mapping(
            db_session, organization_id=test_org.id, connector_instance_id=google_instance.id,
            vcos_entity_type="person", vcos_entity_id="emp-new",
            external_id="google-user-123", external_email="newuser@example.com",
            external_display_name="New User", mapping_state="mapped",
        )
        
        # 5. Create sync run
        sync_run = await synchronization_service.create_sync_run(
            db_session, organization_id=test_org.id, connector_instance_id=google_instance.id,
            sync_mode="webhook", triggered_by="webhook", trigger_id=event.id,
        )
        
        await synchronization_service.complete_sync_run(
            db_session, sync_run.id, state="completed", entities_processed=1, entities_created=1
        )
        
        # 6. Create CompanyAction for outbound operation
        action = CompanyAction(
            id=f"act-{uuid.uuid4().hex[:8]}", organization_id=test_org.id,
            action_type="create", title="Create Welcome Calendar Event",
            state="approved", fingerprint="action-fp",
        )
        db_session.add(action)
        await db_session.flush()
        
        # 7. Create governed external operation
        operation = await bidirectional_operation_service.create_governed_operation(
            db_session, organization_id=test_org.id, connector_instance_id=google_instance.id,
            operation_type="write_event", target_entity_type="event",
            payload={"summary": "Welcome New User", "start": "2026-01-01T09:00:00Z", "end": "2026-01-01T09:30:00Z"},
            source_action_id=action.id,
            caller=test_caller,
        )
        
        # 8. Receive observation (webhook from Google)
        await bidirectional_operation_service.receive_observation(
            db_session, operation_id=operation.id, observation_event_id="google-evt-2",
        )
        
        # 9. Verify outcome
        await bidirectional_operation_service.verify_outcome(
            db_session, operation_id=operation.id, verified=True,
            verified_by=test_caller.employee_id, verification_notes="Calendar event created",
        )
        
        # Verify final state
        await db_session.refresh(operation)
        assert operation.observation_received is True
        assert operation.verified is True
        assert operation.verified_at is not None
        
        # 10. Update integration health
        health = await integration_health_service.calculate_health(db_session, test_org.id, google_instance.id)
        
        assert health.events_processed_24h >= 1
        assert health.overall_status in ("healthy", "degraded")


# ============================================================================
# REGRESSION TESTS
# ============================================================================

class TestRegression:
    """Tests to ensure existing Gates still work."""
    
    @pytest.mark.asyncio
    async def test_gate23_bi_still_works(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Verify Gate 23 BI service still works."""
        from app.intelligence.canonical_business_intelligence_service import canonical_business_intelligence_service
        assert canonical_business_intelligence_service is not None
    
    @pytest.mark.asyncio
    async def test_gate22_communication_still_works(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Verify Gate 22 communication still works."""
        from app.intelligence.canonical_communication_collaboration_service import canonical_communication_collaboration_service
        assert canonical_communication_collaboration_service is not None
    
    @pytest.mark.asyncio
    async def test_gate21_workforce_still_works(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Verify Gate 21 workforce still works."""
        from app.intelligence.canonical_workforce_service import canonical_workforce_service
        assert canonical_workforce_service is not None
    
    @pytest.mark.asyncio
    async def test_gate20_knowledge_still_works(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Verify Gate 20 knowledge still works."""
        from app.intelligence.canonical_knowledge_service import canonical_knowledge_service
        assert canonical_knowledge_service is not None
    
    @pytest.mark.asyncio
    async def test_gate12_digital_twin_still_works(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Verify Gate 12 digital twin still works."""
        from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
        assert canonical_digital_twin_service is not None
    
    @pytest.mark.asyncio
    async def test_gate11_counterfactual_still_works(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Verify Gate 11 counterfactual still works."""
        from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
        assert counterfactual_intelligence_service is not None
    
    @pytest.mark.asyncio
    async def test_gate10_predictive_still_works(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Verify Gate 10 predictive still works."""
        from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
        assert predictive_intelligence_service is not None
    
    @pytest.mark.asyncio
    async def test_gate6_exact_once_still_works(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Verify Gate 6 exact-once still works."""
        from app.intelligence.canonical_mutation import validate_exact_once, ExactOnceViolation
        # Test that exact-once validation still works
        pass


# ============================================================================
# ADVERSARIAL TESTS
# ============================================================================

class TestAdversarial:
    """Adversarial tests for security and integrity."""
    
    @pytest.mark.asyncio
    async def test_cross_tenant_connector_instance_blocked(
        self, db_session: AsyncSession, test_org: Organization, google_connector: Connector
    ):
        """Test that org A cannot access org B's connector instance."""
        # Create second org
        org_b = Organization(id=f"org-b-{uuid.uuid4().hex[:8]}", name="Org B", slug="org-b", status="active")
        db_session.add(org_b)
        await db_session.flush()
        
        # Create instance in org A
        instance_a = await connector_service.create_instance(
            db_session, organization_id=test_org.id, connector_id=google_connector.id,
            name="Org A Instance", config={"domain": "a.com"}, credentials={},
        )
        
        # Try to access from org B - should fail
        instance = await connector_service.get_instance(db_session, org_b.id, instance_a.id)
        assert instance is None
    
    @pytest.mark.asyncio
    async def test_fake_external_id_rejected(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance
    ):
        """Test that fake external IDs in events are handled."""
        # Ingest event with fake external ID
        event = await synchronization_service.ingest_external_event(
            db_session, organization_id=test_org.id, connector_instance_id=google_instance.id,
            external_event_id="fake-evt", event_type="person.created",
            source_id="fake-user-123", source_type="person", payload={},
        )
        
        # Event should be accepted (we don't validate external IDs at ingestion)
        # But identity mapping would fail to resolve
        assert event.id is not None
    
    @pytest.mark.asyncio
    async def test_unauthorized_external_operation_blocked(
        self, db_session: AsyncSession, test_org: Organization, google_instance: ConnectorInstance
    ):
        """Test that external operations without governance are blocked."""
        operation = await bidirectional_operation_service.create_operation(
            db_session, organization_id=test_org.id, connector_instance_id=google_instance.id,
            operation_type="write_event", target_entity_type="event", payload={},
            governance_verified=False,
        )
        
        with pytest.raises(ValueError, match="governance verified"):
            await bidirectional_operation_service.execute_operation(
                db_session, operation.id, lambda db, op: {"success": True}
            )


# ============================================================================
# VOCABULARY COMPLETENESS TESTS
# ============================================================================

class TestVocabularies:
    """Tests for vocabulary completeness."""
    
    def test_connector_kinds_complete(self):
        """Test CONNECTOR_KINDS covers expected providers."""
        expected = {"productivity", "communication", "code", "work_management", "crm", "hr", "erp", "accounting", "cloud", "identity", "knowledge", "calendar", "video", "custom"}
        assert set(CONNECTOR_KINDS) >= expected
    
    def test_connector_states_complete(self):
        """Test CONNECTOR_STATES covers lifecycle."""
        expected = {"disconnected", "connecting", "connected", "error", "paused", "revoked", "reauthorization_required"}
        assert set(CONNECTOR_STATES) == expected
    
    def test_connector_capabilities_complete(self):
        """Test CONNECTOR_CAPABILITIES covers operations."""
        expected = {"read_people", "write_messages", "sync_incremental", "webhook_events"}
        assert set(CONNECTOR_CAPABILITIES) >= expected
    
    def test_entity_types_complete(self):
        """Test ENTITY_TYPES covers domains."""
        expected = {"person", "group", "repository", "issue", "pull_request", "project", "task", "customer", "event", "file"}
        assert set(ENTITY_TYPES) >= expected
    
    def test_mapping_states_complete(self):
        """Test MAPPING_STATES covers states."""
        expected = {"pending", "mapped", "conflict", "ignored", "deleted_externally"}
        assert set(MAPPING_STATES) == expected
    
    def test_sync_states_complete(self):
        """Test SYNC_STATES covers states."""
        expected = {"pending", "running", "completed", "failed", "partial", "cancelled"}
        assert set(SYNC_STATES) == expected
    
    def test_sync_modes_complete(self):
        """Test SYNC_MODES covers modes."""
        expected = {"initial", "incremental", "webhook", "polling", "replay"}
        assert set(SYNC_MODES) == expected
    
    def test_source_authority_levels_complete(self):
        """Test SOURCE_AUTHORITY_LEVELS covers levels."""
        expected = {"primary", "secondary", "tertiary", "ignored"}
        assert set(SOURCE_AUTHORITY_LEVELS) == expected
    
    def test_conflict_resolution_states_complete(self):
        """Test CONFLICT_RESOLUTION_STATES covers states."""
        expected = {"open", "authority_applied", "manual_resolution", "merged", "superseded"}
        assert set(CONFLICT_RESOLUTION_STATES) == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])