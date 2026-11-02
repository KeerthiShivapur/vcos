"""
Slack Connector for VCOS.

Provides integration with Slack for messaging, channels, users, and workflows.
"""

import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urljoin

from app.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    AuthType,
    RateLimitConfig,
    SyncCursor,
    SyncResult,
)

logger = logging.getLogger(__name__)


class SlackConnector(BaseConnector):
    """Slack Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="slack",
        display_name="Slack",
        description="Team communication and collaboration platform",
        category="communication",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "bot_token": {"type": "string", "description": "Bot User OAuth Token (xoxb-)"},
                "user_token": {"type": "string", "description": "User OAuth Token (xoxp-)"},
                "signing_secret": {"type": "string", "description": "For webhook verification"},
            },
            "required": ["client_id", "client_secret", "redirect_uri"],
        },
        required_scopes=[
            "channels:read",
            "channels:write",
            "chat:write",
            "users:read",
            "groups:read",
            "reactions:read",
            "files:read",
            "links:read",
        ],
        supported_operations=[
            "list_channels",
            "get_channel",
            "create_channel",
            "archive_channel",
            "list_users",
            "get_user",
            "send_message",
            "update_message",
            "delete_message",
            "add_reaction",
            "remove_reaction",
            "get_reactions",
            "list_files",
            "upload_file",
            "get_channel_history",
            "create_reminder",
            "set_user_status",
            "invite_to_channel",
            "remove_from_channel",
        ],
        webhook_events=[
            "message",
            "reaction_added",
            "reaction_removed",
            "channel_created",
            "channel_deleted",
            "channel_archive",
            "channel_unarchive",
            "member_joined_channel",
            "member_left_channel",
            "reaction_added",
            "reaction_removed",
            "file_shared",
            "file_created",
            "file_deleted",
            "app_mention",
            "app_uninstalled",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=1,
            requests_per_minute=50,
            burst=10,
        ),
    )

    BASE_URL = "https://slack.com/api"
    TOKEN_URL = "https://slack.com/api/oauth.v2.access"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.bot_token = connection_config.get("bot_token")
        self.user_token = connection_config.get("user_token")
        self.signing_secret = connection_config.get("signing_secret")
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with Slack using bot token or OAuth2."""
        if self.bot_token:
            self._authenticated = True
            logger.info("Slack authenticated with bot token")
            return True

        if self.user_token:
            self._authenticated = True
            logger.info("Slack authenticated with user token")
            return True

        # OAuth2 flow
        client_id = self.connection_config.get("client_id")
        client_secret = self.connection_config.get("client_secret")
        if client_id and client_secret:
            from app.connectors.base import TokenManager
            self._token_manager = TokenManager(client_id, client_secret, self.TOKEN_URL)
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info("Slack authenticated with OAuth2")
            return True

        raise ValueError("Slack requires bot_token, user_token, or OAuth2 credentials")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        }
        if self.bot_token:
            headers["Authorization"] = f"Bearer {self.bot_token}"
        elif self.user_token:
            headers["Authorization"] = f"Bearer {self.user_token}"
        elif self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make Slack API request with error handling."""
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.BASE_URL, endpoint)
        headers = await self._get_headers()

        await self.rate_limiter.acquire()

        async def _request():
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    error = data.get("error", "unknown_error")
                    if error == "ratelimited":
                        retry_after = int(resp.headers.get("Retry-After", "60"))
                        raise aiohttp.ClientResponseError(
                            resp.request_info,
                            resp.history,
                            status=429,
                            message=f"Rate limited, retry after {retry_after}s"
                        )
                    raise Exception(f"Slack API error: {error}")
                return data

        return await self.retry_policy.execute(_request)

    async def pull_data(
        self,
        operation: str,
        cursor: Optional[SyncCursor] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not self._authenticated:
            await self.authenticate()

        handlers = {
            "list_channels": self._list_channels,
            "list_users": self._list_users,
            "get_channel_history": self._get_channel_history,
            "list_files": self._list_files,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_channels(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 200, "exclude_archived": "true"}
        if filters and filters.get("include_archived"):
            params["exclude_archived"] = "false"
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "conversations.list", params=params)
            for channel in data.get("channels", []):
                yield {
                    "type": "channel",
                    "id": channel["id"],
                    "data": channel,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("response_metadata", {}).get("next_cursor"):
                params["cursor"] = data["response_metadata"]["next_cursor"]
            else:
                break

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 200}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "users.list", params=params)
            for user in data.get("members", []):
                yield {
                    "type": "user",
                    "id": user["id"],
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("response_metadata", {}).get("next_cursor"):
                params["cursor"] = data["response_metadata"]["next_cursor"]
            else:
                break

    async def _get_channel_history(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        channel_id = filters.get("channel_id")
        if not channel_id:
            raise ValueError("channel_id filter required")

        params = {"channel": channel_id, "limit": 200}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor
        if filters and filters.get("oldest"):
            params["oldest"] = filters["oldest"]
        if filters and filters.get("latest"):
            params["latest"] = filters["latest"]

        while True:
            data = await self._make_request("GET", "conversations.history", params=params)
            for message in data.get("messages", []):
                yield {
                    "type": "message",
                    "id": message["ts"],
                    "data": message,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("has_more") and data.get("response_metadata", {}).get("next_cursor"):
                params["cursor"] = data["response_metadata"]["next_cursor"]
            else:
                break

    async def _list_files(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"count": 200}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor
        if filters and filters.get("user"):
            params["user"] = filters["user"]
        if filters and filters.get("channel"):
            params["channel"] = filters["channel"]

        while True:
            data = await self._make_request("GET", "files.list", params=params)
            for file in data.get("files", []):
                yield {
                    "type": "file",
                    "id": file["id"],
                    "data": file,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("response_metadata", {}).get("next_cursor"):
                params["cursor"] = data["response_metadata"]["next_cursor"]
            else:
                break

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "send_message": self._send_message,
            "update_message": self._update_message,
            "delete_message": self._delete_message,
            "create_channel": self._create_channel,
            "archive_channel": self._archive_channel,
            "invite_to_channel": self._invite_to_channel,
            "remove_from_channel": self._remove_from_channel,
            "add_reaction": self._add_reaction,
            "remove_reaction": self._remove_reaction,
            "set_user_status": self._set_user_status,
            "upload_file": self._upload_file,
        }

        handler = handlers.get(operation)
        if not handler:
            result.success = False
            result.errors.append({"error": f"Unsupported push operation: {operation}"})
            return result

        for item in data:
            try:
                await handler(item)
                result.records_created += 1 if "create" in operation or "send" in operation else 0
                result.records_updated += 1 if "update" in operation else 0
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _send_message(self, msg_data: Dict[str, Any]):
        payload = {
            "channel": msg_data.get("channel"),
            "text": msg_data.get("text", ""),
            "blocks": msg_data.get("blocks"),
            "thread_ts": msg_data.get("thread_ts"),
            "reply_broadcast": msg_data.get("reply_broadcast", False),
            "unfurl_links": msg_data.get("unfurl_links", True),
            "unfurl_media": msg_data.get("unfurl_media", True),
        }
        await self._make_request("POST", "chat.postMessage", json=payload)

    async def _update_message(self, msg_data: Dict[str, Any]):
        payload = {
            "channel": msg_data.get("channel"),
            "ts": msg_data.get("ts"),
            "text": msg_data.get("text", ""),
            "blocks": msg_data.get("blocks"),
        }
        await self._make_request("POST", "chat.update", json=payload)

    async def _delete_message(self, msg_data: Dict[str, Any]):
        payload = {
            "channel": msg_data.get("channel"),
            "ts": msg_data.get("ts"),
        }
        await self._make_request("POST", "chat.delete", json=payload)

    async def _create_channel(self, channel_data: Dict[str, Any]):
        payload = {
            "name": channel_data.get("name"),
            "is_private": channel_data.get("is_private", False),
        }
        await self._make_request("POST", "conversations.create", json=payload)

    async def _archive_channel(self, channel_data: Dict[str, Any]):
        payload = {"channel": channel_data.get("channel_id")}
        await self._make_request("POST", "conversations.archive", json=payload)

    async def _invite_to_channel(self, data: Dict[str, Any]):
        payload = {
            "channel": data.get("channel_id"),
            "users": data.get("user_ids", []),
        }
        await self._make_request("POST", "conversations.invite", json=payload)

    async def _remove_from_channel(self, data: Dict[str, Any]):
        payload = {
            "channel": data.get("channel_id"),
            "user": data.get("user_id"),
        }
        await self._make_request("POST", "conversations.kick", json=payload)

    async def _add_reaction(self, data: Dict[str, Any]):
        payload = {
            "channel": data.get("channel"),
            "timestamp": data.get("timestamp"),
            "name": data.get("reaction"),
        }
        await self._make_request("POST", "reactions.add", json=payload)

    async def _remove_reaction(self, data: Dict[str, Any]):
        payload = {
            "channel": data.get("channel"),
            "timestamp": data.get("timestamp"),
            "name": data.get("reaction"),
        }
        await self._make_request("POST", "reactions.remove", json=payload)

    async def _set_user_status(self, data: Dict[str, Any]):
        payload = {
            "profile": {
                "status_text": data.get("status_text", ""),
                "status_emoji": data.get("status_emoji", ""),
                "status_expiration": data.get("status_expiration", 0),
            }
        }
        await self._make_request("POST", "users.profile.set", json=payload)

    async def _upload_file(self, file_data: Dict[str, Any]):
        # For file uploads, we'd need multipart/form-data
        # This is a simplified version
        payload = {
            "channels": file_data.get("channels", []),
            "title": file_data.get("title"),
            "initial_comment": file_data.get("initial_comment"),
        }
        # Actual file upload would use aiohttp.FormData
        await self._make_request("POST", "files.upload", data=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "auth.test")
            return data.get("ok", False)
        except Exception as e:
            logger.error(f"Slack connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(SlackConnector, SlackConnector.CONFIG)