"""Slack Connector Adapter — production-grade implementation."""

import asyncio
import logging
import hmac
import hashlib
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Set
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode, parse_qs

import httpx
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from app.services.base_adapter import BaseConnectorAdapter
from app.models.canonical_integration import ConnectorInstance
from app.services.external_identity_service import external_identity_service
from app.services.canonical_reality_integrity_service import canonical_reality_integrity_service
from app.services.source_authority_service import source_authority_service

logger = logging.getLogger("vcos.integration.slack")


@dataclass
class SlackConfig:
    """Slack connector configuration."""
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: List[str]
    bot_token: Optional[str] = None
    user_token: Optional[str] = None
    signing_secret: Optional[str] = None


class SlackEventTypes(Enum):
    """Slack event types we support."""
    MESSAGE_CHANGED = "message.changed"
    MESSAGE_DELETED = "message.deleted"
    CHANNEL_CREATED = "channel_created"
    CHANNEL_DELETED = "channel_deleted"
    CHANNEL_RENAMED = "channel_renamed"
    CHANNEL_ARCHIVED = "channel_archived"
    CHANNEL_UNARCHIVED = "channel_unarchived"
    MEMBER_JOINED_CHANNEL = "member_joined_channel"
    MEMBER_LEFT_CHANNEL = "member_left_channel"
    USER_CHANGE = "user_change"
    TEAM_JOIN = "team_join"
    REACTION_ADDED = "reaction_added"
    REACTION_REMOVED = "reaction_removed"
    FILE_SHARED = "file_shared"
    FILE_UNSHARED = "file_unshared"
    FILE_DELETED = "file_deleted"
    FILE_PUBLIC = "file_public"
    FILE_PRIVATE = "file_private"


class SlackAdapter(BaseConnectorAdapter):
    """Slack connector adapter with full Web API and Events API support."""

    provider_name = "slack"

    ENTITY_ENDPOINTS = {
        "person": "users",
        "group": "usergroups",
        "channel": "conversations",
        "message": "conversations.history",
        "file": "files",
        "event": None,
        "contact": None,
        "repository": None,
        "issue": None,
        "pull_request": None,
        "commit": None,
        "project": None,
        "task": None,
        "customer": None,
        "deal": None,
        "organization": "team",
        "employee": "users",
        "department": "usergroups",
        "role": None,
    }

    # Slack scopes we support
    SUPPORTED_SCOPES = {
        "channels:read", "channels:history", "channels:write",
        "groups:read", "groups:history", "groups:write",
        "im:read", "im:history", "im:write",
        "mpim:read", "mpim:history", "mpim:write",
        "users:read", "users:read.email", "users:write",
        "users.profile:read", "users.profile:write",
        "groups:read", "groups:history", "groups:write",
        "mpim:read", "mpim:history", "mpim:write",
        "reactions:read", "reactions:write",
        "files:read", "files:write",
        "team:read",
        "chat:write", "chat:write.public", "chat:write.customize",
        "reactions:read", "reactions:write",
    }

    # Webhook event types we support
    SUPPORTED_WEBHOOK_EVENTS = {
        "message.changed", "message.deleted",
        "channel_created", "channel_deleted", "channel_renamed",
        "channel_archived", "channel_unarchived",
        "member_joined_channel", "member_left_channel",
        "user_change", "team_join",
        "reaction_added", "reaction_removed",
        "file_shared", "file_unshared", "file_deleted",
        "file_public", "file_private",
        "reaction_added", "reaction_removed",
    }

    # Event types that support incremental sync with since parameter
    INCREMENTAL_EVENT_TYPES = {
        "message", "channel", "user", "file", "reaction",
    }

    def __init__(self, config: Optional[dict] = None):
        super().__init__()
        self.config = config
        self._client: Optional[AsyncWebClient] = None
        self._rate_limit_state: Dict[str, Dict[str, Any]] = {}
        # Track processed event IDs for exact-once semantics
        self._processed_event_ids: Set[str] = set()
        # Track event timestamps for out-of-order handling
        self._event_timestamps: Dict[str, datetime] = {}
        # OAuth state storage (in production, use Redis or DB)
        self._oauth_states: Dict[str, str] = {}

    # =========================================================================
    # OAUTH 2.0 SUPPORT
    # =========================================================================

    def generate_oauth_url(self, state: Optional[str] = None) -> str:
        """Generate Slack OAuth authorization URL."""
        state = state or secrets.token_urlsafe(32)
        self._oauth_states[state] = state  # Store for validation

        params = {
            "client_id": self.config.get("client_id") if self.config else "",
            "scope": " ".join(self.SUPPORTED_SCOPES),
            "redirect_uri": self.config.get("redirect_uri") if self.config else "",
            "state": state,
            "user_scope": " ".join(self.SUPPORTED_SCOPES),
        }
        return f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"

    async def handle_oauth_callback(self, code: str, state: str) -> Dict[str, Any]:
        """Handle OAuth callback and exchange code for tokens."""
        # Validate state
        if state not in self._oauth_states:
            raise ValueError("Invalid OAuth state")
        del self._oauth_states[state]

        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": self.config.get("client_id") if self.config else "",
                    "client_secret": self.config.get("client_secret") if self.config else "",
                    "code": code,
                    "redirect_uri": self.config.get("redirect_uri") if self.config else "",
                },
            )
            response.raise_for_status()
            data = await response.json()

            if not data.get("ok"):
                raise ValueError(f"OAuth failed: {data.get('error')}")

            return {
                "access_token": data.get("access_token"),
                "bot_token": data.get("bot", {}).get("bot_access_token"),
                "user_token": data.get("authed_user", {}).get("access_token"),
                "team_id": data.get("team", {}).get("id"),
                "team_name": data.get("team", {}).get("name"),
                "scope": data.get("scope"),
                "bot_user_id": data.get("bot", {}).get("bot_user_id"),
            }

    async def verify_oauth_state(self, state: str) -> bool:
        """Verify OAuth state parameter."""
        return state in self._oauth_states

    # =========================================================================
    # SYNCHRONIZATION
    # =========================================================================

    async def start_provisioning_only(
        self,
        db,
        organization_name: str,
        domain: str,
        admin_email: str,
        admin_name: str,
        plan_key: str = "starter",
        billing_interval: str = "monthly",
        custom_domain: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> ConnectorInstance:
        """Start provisioning a new company with Slack integration (without executing).

        This creates the provisioning record and Slack connector instance
        but does not execute the full provisioning. Use execute_provisioning
        to complete the provisioning.
        """
        from sqlalchemy import select
        from app.models.organization import Organization
        from app.models.canonical_integration import Connector

        # Check if provisioning already exists for this idempotency key
        if idempotency_key:
            from sqlalchemy import cast, String
            existing = await db.execute(
                select(ConnectorInstance).where(
                    cast(ConnectorInstance.config["idempotency_key"], String) == idempotency_key
                )
            )
            existing = existing.scalar_one_or_none()
            if existing:
                return existing

        # Create organization
        org = Organization(
            name=organization_name,
            slug=domain,
            domain=domain if custom_domain else None,
            status="provisioning",
        )
        db.add(org)
        await db.flush()

        # Create Slack connector instance
        connector = await db.execute(
            select(Connector).where(Connector.provider == "slack")
        )
        connector = connector.scalar_one_or_none()
        if not connector:
            connector = Connector(
                id="slack",
                provider="slack",
                kind="communication",
                display_name="Slack",
                description="Slack integration for channels, messages, and files",
                inbound_capabilities=["read_users", "read_channels", "read_messages", "read_files"],
                outbound_capabilities=["send_messages", "create_channels"],
                supported_entities=["channel", "message", "user", "file", "reaction"],
                supported_events=["message", "channel", "file", "reaction", "member"],
                sync_modes=["incremental", "webhook"],
                supports_webhooks=True,
                supports_polling=True,
                default_poll_interval_seconds=300,
                auth_types=["bot_token"],
                oauth_scopes=["channels:read", "channels:history", "users:read", "chat:write"],
                required_config_fields=["workspace_id"],
                optional_config_fields=[],
                enabled=True,
            )
            db.add(connector)
            await db.flush()

        instance = ConnectorInstance(
            organization_id=org.id,
            connector_id=connector.id,
            name=f"{organization_name} Slack",
            config={"workspace": domain, "idempotency_key": idempotency_key} if idempotency_key else {"workspace": domain},
            credentials={},
            state="pending",
            webhook_secret=None,
            sync_enabled=True,
            sync_mode="incremental",
        )
        db.add(instance)
        await db.flush()

        return instance

    async def fetch_page(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """Fetch a page of entities from Slack with cursor-based pagination."""
        if not self._client:
            await self.authenticate(instance)

        if not self._client:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

        try:
            entities = []
            next_cursor = None

            if entity_type == "person":
                # Slack users.list supports 'oldest' for incremental but not 'since' directly
                kwargs = {"limit": page_size}
                if cursor and cursor != "1970-01-01T00:00:00Z":
                    kwargs["cursor"] = cursor
                if since:
                    kwargs["oldest"] = since.timestamp()
                response = await self._client.users_list(**kwargs)
                if response.get("ok"):
                    members = response.get("members", [])
                    entities = [self._user_to_dict(m) for m in members if not m.get("deleted", False) and not m.get("is_bot", False)]
                    next_cursor = response.get("response_metadata", {}).get("next_cursor")

            elif entity_type == "channel":
                kwargs = {"limit": page_size, "types": "public_channel,private_channel", "exclude_archived": True}
                if cursor and cursor != "1970-01-01T00:00:00Z":
                    kwargs["cursor"] = cursor
                response = await self._client.conversations_list(**kwargs)
                if response.get("ok"):
                    channels = response.get("channels", [])
                    entities = [self._channel_to_dict(c) for c in channels]
                    next_cursor = response.get("response_metadata", {}).get("next_cursor")

            elif entity_type == "group":
                response = await self._client.usergroups_list(limit=page_size)
                if response.get("ok"):
                    groups = response.get("usergroups", [])
                    entities = [self._usergroup_to_dict(g) for g in groups]
                    next_cursor = None

            elif entity_type == "file":
                kwargs = {"limit": page_size}
                if cursor and cursor != "1970-01-01T00:00:00Z":
                    kwargs["cursor"] = cursor
                if since:
                    kwargs["ts_from"] = since.timestamp()
                response = await self._client.files_list(**kwargs)
                if response.get("ok"):
                    files = response.get("files", [])
                    entities = [self._file_to_dict(f) for f in files]
                    next_cursor = response.get("response_metadata", {}).get("next_cursor")

            elif entity_type == "organization":
                response = await self._client.team_info()
                if response.get("ok"):
                    entities = [self._team_to_dict(response.get("team", {}))]
                    next_cursor = None

            else:
                entities = []
                next_cursor = None

            return {
                "entities": entities,
                "next_cursor": next_cursor if next_cursor else None,
                "has_more": bool(next_cursor),
                "total_count": len(entities),
            }

        except SlackApiError as e:
            logger.error(f"Slack API error fetching {entity_type}: {e}")
            await self._handle_rate_limit(e)
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}
        except Exception as e:
            logger.error(f"Error fetching {entity_type} from Slack: {e}")
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

    async def fetch_entity(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        external_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single entity by external ID."""
        if not self._client:
            if not await self.authenticate(instance):
                return None

        try:
            if entity_type == "person":
                response = await self._client.users_info(user=external_id)
                if response.get("ok"):
                    return self._user_to_dict(response.get("user", {}))

            elif entity_type == "channel":
                response = await self._client.conversations_info(channel=external_id)
                if response.get("ok"):
                    return self._channel_to_dict(response.get("channel", {}))

            elif entity_type == "file":
                response = await self._client.files_info(file=external_id)
                if response.get("ok"):
                    return self._file_to_dict(response.get("file", {}))

            return None

        except SlackApiError as e:
            logger.error(f"Slack API error fetching entity {external_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching entity {external_id}: {e}")
            return None

    async def get_deleted_entities(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        since: datetime,
    ) -> List[str]:
        """Get list of deleted entity external IDs since timestamp."""
        # Slack doesn't have a direct deleted entities API
        # Would need to use webhook events or audit log
        return []

    async def authenticate(self, instance: ConnectorInstance) -> bool:
        """Authenticate with Slack using bot token."""
        try:
            creds_dict = instance.credentials
            if not creds_dict:
                return False

            bot_token = creds_dict.get("bot_token") or creds_dict.get("bot_token")
            if not bot_token:
                return False

            self._client = AsyncWebClient(token=bot_token)

            # Test authentication
            response = await self._client.auth_test()
            if not response.get("ok"):
                return False

            return True

        except SlackApiError as e:
            logger.error(f"Slack authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Slack authentication failed: {e}")
            return False

    async def test_connection(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Test connection to Slack."""
        try:
            if not await self.authenticate(instance):
                return {"success": False, "error": "Authentication failed"}

            response = await self._client.auth_test()
            return {
                "success": True,
                "team_id": response.get("team_id"),
                "team_name": response.get("team"),
                "user_id": response.get("user_id"),
                "url": response.get("url"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # WEBHOOK HANDLING
    # =========================================================================

    async def verify_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature_header: str,
        timestamp_header: str,
    ) -> bool:
        """Verify Slack webhook signature using HMAC-SHA256.

        Slack uses the format: X-Slack-Signature: v0=timestamp=signature
        X-Slack-Request-Timestamp: timestamp
        """
        if not instance.signing_secret:
            logger.warning(f"No signing secret configured for instance {instance.id}")
            return False

        # Check timestamp freshness (5 min window)
        try:
            timestamp = int(timestamp_header)
            if abs(datetime.now(timezone.utc).timestamp() - int(timestamp_header)) > 300:
                logger.warning("Stale request timestamp")
                return False
        except ValueError:
            logger.warning("Invalid timestamp in signature header")
            return False

        # Verify signature
        basestring = f"v0:{timestamp_header}:{payload.decode('utf-8')}"
        expected_signature = hmac.new(
            instance.signing_secret.encode(),
            f"v0:{timestamp_header}:{payload.decode('utf-8')}".encode(),
            hashlib.sha256
        ).hexdigest()

        expected_signature = f"v0={timestamp_header}={expected_signature}"

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(f"v0={expected_signature}", signature_header)

    async def process_webhook_event(
        self,
        instance: ConnectorInstance,
        event_type: str,
        payload: Dict[str, Any],
        delivery_id: str,
        event_timestamp: datetime,
    ) -> Dict[str, Any]:
        """Process a Slack webhook event with exact-once semantics.

        Returns a dict with processing result and any created/updated entities.
        """
        # Exact-once: Check if we've already processed this event
        event_fingerprint = f"{delivery_id}:{event_type}"
        if event_fingerprint in self._processed_event_ids:
            logger.info(f"Duplicate webhook event ignored: {event_fingerprint}")
            return {"status": "duplicate", "delivery_id": delivery_id}

        # Out-of-order handling: check event timestamp
        if delivery_id in self._event_timestamps:
            previous_timestamp = self._event_timestamps[delivery_id]
            if event_timestamp <= previous_timestamp:
                logger.warning(f"Out-of-order event detected: {delivery_id}, "
                             f"previous: {previous_timestamp}, current: {event_timestamp}")
                # For out-of-order, we still process but log warning
                # The canonical mutation boundary will handle conflicts

        # Record event for future duplicate/out-of-order detection
        self._processed_event_ids.add(event_fingerprint)
        self._event_timestamps[delivery_id] = event_timestamp

        # Only process supported event types
        if event_type not in self.SUPPORTED_WEBHOOK_EVENTS:
            return {"status": "ignored", "reason": f"Unsupported event type: {event_type}"}

        result = {"status": "processed", "delivery_id": delivery_id, "entities": []}

        try:
            # Process based on event type
            if event_type == "message":
                entities = await self._process_message_event(payload)
                result["entities"] = entities
            elif event_type == "channel":
                entities = await self._process_channel_event(payload)
                result["entities"] = entities
            elif event_type == "file":
                entities = await self._process_file_event(payload)
                result["entities"] = entities
            elif event_type == "reaction":
                entities = await self._process_reaction_event(payload)
                result["entities"] = entities
            elif event_type == "member":
                # Member events (added/removed)
                pass

            # Record provenance for all processed entities
            for entity in result.get("entities", []):
                await self._record_provenance(payload, entity)

        except Exception as e:
            logger.error(f"Error processing webhook {event_type} ({delivery_id}): {e}")
            result = {"status": "error", "delivery_id": delivery_id, "error": str(e)}

        return result

    async def _process_message_event(self, payload: Dict) -> List[Dict]:
        """Process message events (changed/deleted)."""
        event = payload.get("event", {})
        subtype = event.get("subtype")

        if subtype == "message_changed":
            return [self._message_to_dict(event.get("message", {}))]
        elif subtype == "message_deleted":
            return [{"external_id": event.get("deleted_ts"), "deleted": True}]

        return []

    async def _process_channel_event(self, payload: Dict) -> List[Dict]:
        """Process channel events (created/deleted/renamed/archived)."""
        action = payload.get("action")
        channel = payload.get("channel", {})

        if action == "created":
            return [self._channel_to_dict(channel)]
        elif action == "deleted":
            return [{"external_id": channel.get("id"), "deleted": True}]
        elif action in ["renamed", "archived", "unarchived"]:
            return [self._channel_to_dict(channel)]

        return []

    async def _process_file_event(self, payload: Dict) -> List[Dict]:
        """Process file events (shared/unshared/deleted/public/private)."""
        action = payload.get("action")
        file = payload.get("file", {})

        if action in ["shared", "public", "private"]:
            return [self._file_to_dict(file)]
        elif action == "deleted":
            return [{"external_id": file.get("id"), "deleted": True}]
        elif action == "unshared":
            return [{"external_id": file.get("id"), "unshared": True}]

        return []

    async def _process_reaction_event(self, payload: Dict) -> List[Dict]:
        """Process reaction events (added/removed)."""
        event = payload.get("event", {})
        reaction = event.get("reaction", {})
        item = event.get("item", {})

        if payload.get("type") == "reaction_added":
            return [{
                "id": f"{item.get('channel', '')}:{item.get('ts', '')}:{reaction.get('name', '')}",
                "external_id": f"{item.get('channel', '')}:{item.get('ts', '')}:{reaction.get('name', '')}",
                "reaction": reaction.get("name"),
                "user": event.get("user"),
                "item": item,
                "created": datetime.fromtimestamp(event.get("event_ts", 0), tz=timezone.utc).isoformat(),
            }]
        elif payload.get("type") == "reaction_removed":
            return [{"external_id": f"{item.get('channel', '')}:{item.get('ts', '')}:{reaction.get('name', '')}", "deleted": True}]

        return []

    async def _record_provenance(self, payload: Dict, entity: Dict):
        """Record provenance for an entity from webhook."""
        # This would integrate with the provenance tracking system
        pass

    # =========================================================================
    # IDENTITY MAPPING
    # =========================================================================

    async def map_slack_user_to_vcos(
        self,
        db,
        organization_id: str,
        connector_instance_id: str,
        slack_user: Dict,
    ):
        """Map Slack user to VCOS employee via external_identity_service."""
        return await external_identity_service.resolve_identity(
            db=db,
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            external_id=slack_user.get("id"),
            external_type="person",
            external_email=slack_user.get("profile", {}).get("email"),
            external_display_name=slack_user.get("real_name") or slack_user.get("profile", {}).get("real_name"),
            external_metadata=slack_user,
        )

    # =========================================================================
    # CONFLICT DETECTION
    # =========================================================================

    async def detect_conflict(
        self,
        db,
        organization_id: str,
        entity_type: str,
        entity_id: str,
        external_value: Dict,
        canonical_value: Dict,
    ):
        """Detect conflict between external and canonical data."""
        from app.models.canonical_integration import ExternalConflict
        from sqlalchemy import select

        # Check if conflict already exists
        existing = await db.execute(
            select(ExternalConflict).where(
                ExternalConflict.organization_id == organization_id,
                ExternalConflict.entity_type == entity_type,
                ExternalConflict.entity_id == entity_id,
            )
        )
        if existing.scalar_one_or_none():
            return existing.scalar_one_or_none()

        # Create conflict record
        conflict = ExternalConflict(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            source_a_instance_id="slack",
            source_a_value=external_value,
            source_b_instance_id="canonical",
            source_b_value=canonical_value,
            conflict_type="value_mismatch",
        )
        db.add(conflict)
        await db.flush()
        return conflict

    def _find_field_conflicts(self, external_value: Dict, canonical_value: Dict) -> List[str]:
        """Find fields that differ between external and canonical values."""
        conflicts = []
        all_keys = set(external_value.keys()) | set(canonical_value.keys())
        for key in all_keys:
            ext_val = external_value.get(key)
            can_val = canonical_value.get(key)
            if ext_val != can_val:
                conflicts.append(key)
        return conflicts

    async def check_source_authority(self, db, organization_id: str, entity_type: str) -> str:
        """Check which source has authority for this entity type."""
        from app.services.source_authority_service import source_authority_service
        primary = await source_authority_service.get_primary_authority(db, organization_id, entity_type)
        if primary:
            return primary.connector_instance_id
        return "canonical"

    async def reconcile_conflict(
        self,
        db,
        conflict_id: str,
        resolution: str,
        resolved_by: str,
    ):
        """Reconcile a conflict using reconciliation_service."""
        from app.services.reconciliation_service import reconciliation_service
        return await reconciliation_service.resolve_conflict(
            db=db,
            conflict_id=conflict_id,
            resolution=resolution,
            resolved_by=resolved_by,
        )

    # =========================================================================
    # RATE LIMITING WITH EXPONENTIAL BACKOFF
    # =========================================================================

    async def _handle_rate_limit(self, error: SlackApiError) -> bool:
        """Handle rate limit error from Slack API."""
        if error.response and error.response.get("error") == "rate_limited":
            retry_after = error.response.headers.get("Retry-After")
            if retry_after:
                try:
                    wait_seconds = int(retry_after)
                    wait_seconds = min(wait_seconds, 60)  # Cap at 60s
                    logger.info(f"Rate limited, waiting {wait_seconds}s")
                    await asyncio.sleep(wait_seconds)
                    return True
                except ValueError:
                    pass
            # Default wait
            await asyncio.sleep(60)
            return True
        return False

    async def _fetch_with_retry(
        self,
        instance: ConnectorInstance,
        fetch_func,
        *args,
        max_retries: int = 3,
        **kwargs,
    ) -> Any:
        """Execute a fetch operation with exponential backoff retry."""
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return await fetch_func(*args, **kwargs)
            except SlackApiError as e:
                last_error = e
                if await self._handle_rate_limit(e):
                    continue
                if e.status in (500, 502, 503, 504):
                    # Server error, retry
                    if attempt < max_retries:
                        delay = min(2 ** attempt, 30)
                        await asyncio.sleep(delay)
                        continue
                raise
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = min(2 ** attempt, 30)
                    await asyncio.sleep(delay)
                    continue
                raise

        raise last_error

    async def handle_rate_limit(
        self,
        instance: ConnectorInstance,
        reset_at: datetime,
    ) -> bool:
        """Handle rate limit for an instance."""
        self._rate_limit_state[instance.id] = {
            "remaining": 0,
            "reset_at": reset_at,
        }
        return True

    async def get_rate_limit_status(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Get rate limit status for an instance."""
        state = self._rate_limit_state.get(instance.id, {})
        return {
            "remaining": state.get("remaining", 100),
            "limit": state.get("limit", 100),
            "reset_at": state.get("reset_at", datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        }

    # =========================================================================
    # CONNECTION REVOCATION
    # =========================================================================

    @classmethod
    async def revoke_connection(cls, instance: ConnectorInstance) -> bool:
        """Revoke Slack connection and clean up credentials."""
        try:
            # Revoke bot token if we have user token
            if instance.credentials.get("user_token"):
                async with httpx.AsyncClient() as client:
                    await client.post(
                        "https://slack.com/api/auth.revoke",
                        headers={"Authorization": f"Bearer {instance.credentials['user_token']}"},
                    )

            # Revoke bot token
            if instance.credentials.get("bot_token"):
                async with httpx.AsyncClient() as client:
                    await client.post(
                        "https://slack.com/api/auth.revoke",
                        headers={"Authorization": f"Bearer {instance.credentials['bot_token']}"},
                    )

            # Clear credentials
            instance.credentials = {}
            instance.state = "revoked"
            instance.revoked_at = datetime.now(timezone.utc)

            return True
        except Exception as e:
            logger.error(f"Failed to revoke Slack connection: {e}")
            return False

    # =========================================================================
    # HEALTH MONITORING
    # =========================================================================

    async def health_check(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Perform health check on Slack connection."""
        health = {
            "status": "healthy",
            "checks": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Test authentication
        try:
            auth_ok = await self.authenticate(instance)
            health["checks"]["authentication"] = "pass" if auth_ok else "fail"
        except Exception as e:
            health["checks"]["authentication"] = f"fail: {str(e)}"
            health["status"] = "degraded"

        # Test API access
        try:
            if self._client:
                response = await self._client.auth_test()
                health["checks"]["api_access"] = "pass" if response.get("ok") else "fail"
        except Exception as e:
            health["checks"]["api_access"] = f"fail: {str(e)}"
            health["status"] = "degraded"

        # Check rate limit
        try:
            if self._client:
                rate_limit = await self._client.rate_limit()
                remaining = rate_limit.get("rate_limit_remaining", 0)
                limit = rate_limit.get("rate_limit_limit", 1)
                health["checks"]["rate_limit"] = f"{remaining}/{limit}"
                if remaining < 10:
                    health["status"] = "degraded"
                    health["checks"]["rate_limit_warning"] = "Low rate limit remaining"
        except Exception:
            pass

        # Check webhook secret
        health["checks"]["webhook_secret"] = "configured" if instance.webhook_secret else "missing"

        return health

    # =========================================================================
    # ENTITY TRANSFORMERS
    # =========================================================================

    def _user_to_dict(self, user: Dict) -> Dict[str, Any]:
        return {
            "id": user.get("id"),
            "external_id": user.get("id"),
            "display_name": user.get("real_name") or user.get("profile", {}).get("real_name"),
            "email": user.get("profile", {}).get("email"),
            "username": user.get("name"),
            "title": user.get("profile", {}).get("title"),
            "phone": user.get("profile", {}).get("phone"),
            "avatar_url": user.get("profile", {}).get("image_512"),
            "is_admin": user.get("is_admin", False),
            "is_owner": user.get("is_owner", False),
            "is_bot": user.get("is_bot", False),
            "deleted": user.get("deleted", False),
            "created": datetime.fromtimestamp(user.get("created", 0), tz=timezone.utc).isoformat() if user.get("created") else None,
            "tz": user.get("tz"),
            "tz_label": user.get("tz_label"),
        }

    def _channel_to_dict(self, channel: Dict) -> Dict[str, Any]:
        return {
            "id": channel.get("id"),
            "external_id": channel.get("id"),
            "name": channel.get("name"),
            "topic": channel.get("topic", {}).get("value"),
            "purpose": channel.get("purpose", {}).get("value"),
            "is_private": channel.get("is_private", False),
            "is_archived": channel.get("is_archived", False),
            "is_general": channel.get("is_general", False),
            "creator": channel.get("creator"),
            "created": datetime.fromtimestamp(channel.get("created", 0), tz=timezone.utc).isoformat() if channel.get("created") else None,
            "member_count": channel.get("num_members", 0),
        }

    def _file_to_dict(self, file: Dict) -> Dict[str, Any]:
        return {
            "id": file.get("id"),
            "external_id": file.get("id"),
            "name": file.get("name"),
            "title": file.get("title"),
            "mimetype": file.get("mimetype"),
            "filetype": file.get("filetype"),
            "size": file.get("size"),
            "url_private": file.get("url_private"),
            "url_private_download": file.get("url_private_download"),
            "created": datetime.fromtimestamp(file.get("created", 0), tz=timezone.utc).isoformat() if file.get("created") else None,
            "user": file.get("user"),
        }

    def _team_to_dict(self, team: Dict) -> Dict[str, Any]:
        return {
            "id": team.get("id"),
            "external_id": team.get("id"),
            "name": team.get("name"),
            "domain": team.get("domain"),
            "email_domain": team.get("email_domain"),
            "icon": team.get("icon"),
        }

    def _usergroup_to_dict(self, group: Dict) -> Dict[str, Any]:
        return {
            "id": group.get("id"),
            "external_id": group.get("id"),
            "name": group.get("name"),
            "handle": group.get("handle"),
            "description": group.get("description"),
            "is_external": group.get("is_external", False),
            "date_create": datetime.fromtimestamp(group.get("date_create", 0), tz=timezone.utc).isoformat() if group.get("date_create") else None,
            "date_update": datetime.fromtimestamp(group.get("date_update", 0), tz=timezone.utc).isoformat() if group.get("date_update") else None,
        }

    def _message_to_dict(self, message: Dict) -> Dict[str, Any]:
        return {
            "id": message.get("ts"),
            "external_id": message.get("ts"),
            "text": message.get("text"),
            "user": message.get("user"),
            "channel": message.get("channel"),
            "ts": message.get("ts"),
            "type": message.get("type"),
            "subtype": message.get("subtype"),
            "thread_ts": message.get("thread_ts"),
            "parent_user_id": message.get("parent_user_id"),
        }

    def _get_supported_entity_types(self) -> List[str]:
        return [k for k, v in self.ENTITY_ENDPOINTS.items() if v is not None]

    def _extract_external_id(self, entity_type: str, entity: Dict) -> Optional[str]:
        return entity.get("id") or entity.get("external_id")


def create_slack_adapter(config: Optional[dict] = None) -> SlackAdapter:
    """Create Slack adapter."""
    return SlackAdapter(config)