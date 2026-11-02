"""Gate 24 — Slack Connector.

Implements Slack integration for channels, messages, users, and files.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, AsyncIterator

from app.intelligence.connectors.base import BaseConnector, connector_registry
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.connectors.slack")


class SlackConnector(BaseConnector):
    """Slack connector implementation."""
    
    @property
    def provider(self) -> str:
        return "slack"
    
    @property
    def kind(self) -> str:
        return "communication"
    
    async def authenticate(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """Authenticate with Slack using OAuth2."""
        credentials = instance.credentials
        
        if not credentials:
            return False, "No credentials configured"
        
        bot_token = credentials.get("bot_token")
        if not bot_token:
            return False, "No bot token configured"
        
        # Test the token
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {bot_token}"},
                )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return True, None
                return False, data.get("error", "Authentication failed")
        except Exception as e:
            return False, f"Authentication test failed: {str(e)}"
        
        return False, "Authentication failed"
    
    async def test_connection(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """Test Slack connection."""
        return await self.authenticate(instance)
    
    async def full_sync(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Full sync of Slack data."""
        ok, error = await self.authenticate(instance)
        if not ok:
            raise RuntimeError(f"Authentication failed: {error}")
        
        credentials = instance.credentials
        bot_token = credentials.get("bot_token")
        
        # Sync users
        if "read_people" in instance.connector.inbound_capabilities:
            async for user in self._sync_users(bot_token):
                yield user
        
        # Sync channels
        if "read_channels" in instance.connector.inbound_capabilities:
            async for channel in self._sync_channels(bot_token):
                yield channel
        
        # Sync messages (if needed)
        if "read_messages" in instance.connector.inbound_capabilities:
            async for message in self._sync_messages(bot_token, since, until):
                yield message
    
    async def _sync_users(self, bot_token: str) -> AsyncIterator[dict[str, Any]]:
        """Sync Slack users."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            cursor = None
            while True:
                params = {"limit": 200}
                if cursor:
                    params["cursor"] = cursor
                
                response = await client.get(
                    "https://slack.com/api/users.list",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    params=params,
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                if not data.get("ok"):
                    break
                
                for user in data.get("members", []):
                    if user.get("deleted") or user.get("is_bot"):
                        continue
                    
                    yield {
                        "entity_type": "person",
                        "external_id": user["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": user["id"],
                            "external_email": user.get("profile", {}).get("email"),
                            "external_display_name": user.get("profile", {}).get("display_name") or user.get("real_name"),
                            "external_avatar_url": user.get("profile", {}).get("image_512"),
                            "external_metadata": {
                                "title": user.get("profile", {}).get("title"),
                                "phone": user.get("profile", {}).get("phone"),
                                "status_text": user.get("profile", {}).get("status_text"),
                                "status_emoji": user.get("profile", {}).get("status_emoji"),
                                "is_admin": user.get("is_admin"),
                                "is_owner": user.get("is_owner"),
                                "tz": user.get("tz"),
                                "tz_label": user.get("tz_label"),
                            },
                        },
                    }
                
                cursor = data.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
    
    async def _sync_channels(self, bot_token: str) -> AsyncIterator[dict[str, Any]]:
        """Sync Slack channels."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            cursor = None
            while True:
                params = {"limit": 200, "types": "public_channel,private_channel"}
                if cursor:
                    params["cursor"] = cursor
                
                response = await client.get(
                    "https://slack.com/api/conversations.list",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    params=params,
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                if not data.get("ok"):
                    break
                
                for channel in data.get("channels", []):
                    yield {
                        "entity_type": "channel",
                        "external_id": channel["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": channel["id"],
                            "external_display_name": channel.get("name"),
                            "external_metadata": {
                                "is_private": channel.get("is_private"),
                                "is_archived": channel.get("is_archived"),
                                "is_general": channel.get("is_general"),
                                "topic": channel.get("topic", {}).get("value"),
                                "purpose": channel.get("purpose", {}).get("value"),
                                "num_members": channel.get("num_members"),
                                "created": channel.get("created"),
                            },
                        },
                    }
                
                cursor = data.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
    
    async def _sync_messages(
        self, bot_token: str, since: Optional[datetime], until: Optional[datetime]
    ) -> AsyncIterator[dict[str, Any]]:
        """Sync Slack messages (limited - requires channel membership)."""
        # This would require iterating through channels and fetching history
        # For now, we don't sync messages in full sync due to volume
        return
        yield
    
    async def incremental_sync(
        self,
        instance: ConnectorInstance,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Incremental sync - Slack doesn't have great incremental for users/channels."""
        async for entity in self.full_sync(instance, since=since):
            yield entity
    
    async def poll_events(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Poll for Slack events (Events API via Socket Mode or webhooks)."""
        # Slack recommends using Socket Mode or webhooks for real-time events
        # Polling is not the primary method
        return
        yield
    
    async def execute_operation(
        self,
        instance: ConnectorInstance,
        operation_type: str,
        target_entity_type: str,
        target_external_id: Optional[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an operation on Slack."""
        ok, error = await self.authenticate(instance)
        if not ok:
            return {"success": False, "error": error}
        
        credentials = instance.credentials
        bot_token = credentials.get("bot_token")
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            if operation_type == "write_message" and target_entity_type == "channel":
                channel = target_external_id or payload.get("channel")
                text = payload.get("text")
                blocks = payload.get("blocks")
                
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"},
                    json={"channel": channel, "text": text, "blocks": blocks},
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        return {
                            "success": True,
                            "external_operation_id": data.get("ts"),
                            "data": data,
                        }
                
                return {"success": False, "error": response.text}
            
            elif operation_type == "write_message" and target_entity_type == "person":
                # DM
                user = target_external_id
                text = payload.get("text")
                
                # First open IM
                response = await client.post(
                    "https://slack.com/api/conversations.open",
                    headers={"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"},
                    json={"users": user},
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        channel = data["channel"]["id"]
                        response = await client.post(
                            "https://slack.com/api/chat.postMessage",
                            headers={"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"},
                            json={"channel": channel, "text": text},
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            if data.get("ok"):
                                return {
                                    "success": True,
                                    "external_operation_id": data.get("ts"),
                                    "data": data,
                                }
                
                return {"success": False, "error": "Failed to send DM"}
        
        return {"success": False, "error": f"Operation {operation_type} not implemented"}
    
    async def get_webhook_events(
        self,
        instance: ConnectorInstance,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Parse Slack webhook payload (Events API)."""
        events = []
        
        # URL verification challenge
        if payload.get("type") == "url_verification":
            return []
        
        # Event callback
        if payload.get("type") == "event_callback":
            event = payload.get("event", {})
            event_type = event.get("type", "")
            
            events.append({
                "external_event_id": payload.get("event_id", ""),
                "event_type": f"slack.{event_type}",
                "source_id": event.get("channel") or event.get("user") or event.get("message", {}).get("ts"),
                "source_type": "channel" if "channel" in event else "person",
                "payload": event,
                "external_timestamp": datetime.fromtimestamp(float(event.get("event_ts", "0"))) if event.get("event_ts") else datetime.now(timezone.utc),
            })
        
        return events
    
    async def refresh_credentials(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str], Optional[dict]]:
        """Refresh Slack OAuth2 token (not typically needed for bot tokens)."""
        return True, None, instance.credentials
    
    async def get_rate_limit_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Get Slack API rate limit status."""
        return {"remaining": "unknown", "reset_at": None}
    
    async def resolve_identity(
        self,
        instance: ConnectorInstance,
        external_id: str,
    ) -> Optional[dict[str, Any]]:
        """Resolve a Slack user ID to identity attributes."""
        ok, error = await self.authenticate(instance)
        if not ok:
            return None
        
        credentials = instance.credentials
        bot_token = credentials.get("bot_token")
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://slack.com/api/users.info",
                headers={"Authorization": f"Bearer {bot_token}"},
                params={"user": external_id},
            )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                user = data.get("user", {})
                return {
                    "external_id": user["id"],
                    "external_email": user.get("profile", {}).get("email"),
                    "external_display_name": user.get("profile", {}).get("display_name") or user.get("real_name"),
                    "external_avatar_url": user.get("profile", {}).get("image_512"),
                    "external_metadata": {
                        "title": user.get("profile", {}).get("title"),
                        "is_admin": user.get("is_admin"),
                        "is_owner": user.get("is_owner"),
                    },
                }
        
        return None


    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Discover and return the connector's capabilities."""
        return {
            "inbound_capabilities": ["read_users", "read_channels", "read_messages", "read_files"],
            "outbound_capabilities": ["send_message", "create_channel", "invite_user", "post_message", "update_message", "delete_message", "add_reaction", "create_thread"],
            "supported_entities": ["user", "channel", "message", "file", "reaction", "thread"],
            "supported_events": ["message.posted", "message.updated", "message.deleted", "channel.created", "channel.archived", "member.joined", "member.left", "reaction.added", "reaction.removed", "thread.created"],
            "sync_modes": ["full", "incremental", "webhook", "polling"],
            "auth_types": ["oauth2", "bot_token"],
            "oauth_scopes": [
                "channels:read", "channels:manage", "chat:write", "chat:write.public", "channels:read",
                "groups:read", "im:read", "im:write", "mpim:read", "mpim:write",
                "files:read", "files:write", "reactions:read", "reactions:write"
            ],
            "required_config_fields": ["client_id", "client_secret"],
            "optional_config_fields": ["bot_token", "signing_secret"],
            "rate_limits": {
                "api": {"requests_per_second": 50, "burst": 100},
                "chat_postMessage": {"requests_per_minute": 30},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("bot_token") and not credentials.get("user_token"):
            return False, "No bot_token or user_token configured"
        return True, None

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return {
                "status": "unhealthy",
                "last_check": utcnow().isoformat(),
                "details": {"error": error},
                "latency_ms": 0,
            }
        return {
            "status": "healthy",
            "last_check": utcnow().isoformat(),
            "details": {"authenticated": True},
            "latency_ms": 0,
        }

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        # Slack uses HMAC-SHA256 with signing secret
        import hmac
        import hashlib
        credentials = instance.credentials
        signing_secret = credentials.get("signing_secret")
        if not signing_secret:
            return False
        expected = hmac.new(signing_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        return await self.validate_webhook_signature(instance, payload, signature, timestamp)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.get_health_status(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)


    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Discover and return the connector's capabilities."""
        return {
            "inbound_capabilities": ["read_users", "read_channels", "read_messages", "read_files"],
            "outbound_capabilities": ["send_message", "create_channel", "invite_user", "post_message", "update_message", "delete_message", "add_reaction", "create_thread"],
            "supported_entities": ["user", "channel", "message", "file", "reaction", "thread"],
            "supported_events": ["message.posted", "message.updated", "message.deleted", "channel.created", "channel.archived", "member.joined", "member.left", "reaction.added", "reaction.removed", "thread.created"],
            "sync_modes": ["full", "incremental", "webhook", "polling"],
            "auth_types": ["oauth2", "bot_token"],
            "oauth_scopes": [
                "channels:read", "channels:manage", "chat:write", "chat:write.public", "channels:read",
                "groups:read", "im:read", "im:write", "mpim:read", "mpim:write",
                "files:read", "files:write", "reactions:read", "reactions:write"
            ],
            "required_config_fields": ["client_id", "client_secret"],
            "optional_config_fields": ["bot_token", "signing_secret"],
            "rate_limits": {
                "api": {"requests_per_second": 50, "burst": 100},
                "chat_postMessage": {"requests_per_minute": 30},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("bot_token") and not credentials.get("user_token"):
            return False, "No bot_token or user_token configured"
        return True, None

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return {
                "status": "unhealthy",
                "last_check": utcnow().isoformat(),
                "details": {"error": error},
                "latency_ms": 0,
            }
        return {
            "status": "healthy",
            "last_check": utcnow().isoformat(),
            "details": {"authenticated": True},
            "latency_ms": 0,
        }

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        # Slack uses HMAC-SHA256 with signing secret
        import hmac
        import hashlib
        credentials = instance.credentials
        signing_secret = credentials.get("signing_secret")
        if not signing_secret:
            return False
        expected = hmac.new(signing_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        return await self.validate_webhook_signature(instance, payload, signature, timestamp)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.get_health_status(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)


# Register the connector
connector_registry.register(SlackConnector())