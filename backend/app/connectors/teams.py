"""
Microsoft Teams Connector for VCOS.

Provides integration with Microsoft Teams for chat, channels, meetings, and calls.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp

from app.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    AuthType,
    RateLimitConfig,
    SyncCursor,
    SyncResult,
)

logger = logging.getLogger(__name__)


class TeamsConnector(BaseConnector):
    """Microsoft Teams Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="teams",
        display_name="Microsoft Teams",
        description="Microsoft Teams for chat, meetings, and collaboration",
        category="communication",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "tenant_id": {"type": "string"},
                "access_token": {"type": "string", "description": "Microsoft Graph access token"},
                "refresh_token": {"type": "string"},
            },
            "required": ["client_id", "client_secret", "redirect_uri", "tenant_id"],
        },
        required_scopes=[
            "Chat.Read",
            "Chat.ReadWrite",
            "Channel.ReadBasic.All",
            "ChannelMessage.Read.All",
            "ChannelMessage.Send",
            "OnlineMeeting.Read.All",
            "OnlineMeeting.ReadWrite.All",
            "User.Read.All",
            "Team.ReadBasic.All",
            "Calls.AccessMedia.All",
            "Calls.Initiate.All",
            "Calls.JoinGroupCall.All",
        ],
        supported_operations=[
            "list_teams",
            "get_team",
            "list_channels",
            "get_channel",
            "list_messages",
            "send_message",
            "reply_message",
            "list_members",
            "add_member",
            "remove_member",
            "create_meeting",
            "get_meeting",
            "list_meetings",
            "join_meeting",
            "start_call",
            "end_call",
            "record_meeting",
            "get_recording",
        ],
        webhook_events=[
            "chatMessageCreated",
            "chatMessageUpdated",
            "chatMessageDeleted",
            "channelCreated",
            "channelUpdated",
            "channelDeleted",
            "memberAdded",
            "memberRemoved",
            "meetingStarted",
            "meetingEnded",
            "callStarted",
            "callEnded",
            "recordingStarted",
            "recordingEnded",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=600,
            burst=50,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/microsoftteams.svg",
        documentation_url="https://docs.microsoft.com/en-us/graph/teams-concept-overview",
    )

    BASE_URL = "https://graph.microsoft.com/v1.0"
    TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.tenant_id = connection_config.get("tenant_id")
        self.access_token = connection_config.get("access_token")
        self.refresh_token = connection_config.get("refresh_token")
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with Microsoft Graph using OAuth2."""
        if self.access_token:
            self._authenticated = True
            logger.info("Teams authenticated with access token")
            return True

        client_id = self.connection_config.get("client_id")
        client_secret = self.connection_config.get("client_secret")
        tenant_id = self.connection_config.get("tenant_id")
        
        if client_id and client_secret and tenant_id:
            from app.connectors.base import TokenManager
            token_url = self.TOKEN_URL.format(tenant_id=tenant_id)
            self._token_manager = TokenManager(client_id, client_secret, token_url)
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info("Teams authenticated with OAuth2")
            return True

        raise ValueError("Teams requires access_token or OAuth2 credentials (client_id, client_secret, tenant_id)")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        elif self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make Microsoft Graph API request with error handling."""
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.BASE_URL, endpoint)
        headers = await self._get_headers()

        await self.rate_limiter.acquire()

        async def _request():
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=429,
                        message=f"Rate limited, retry after {retry_after}s"
                    )
                if resp.status >= 400:
                    error_text = await resp.text()
                    raise Exception(f"Microsoft Graph API error: {resp.status} - {error_text}")
                return await resp.json()

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
            "list_teams": self._list_teams,
            "list_channels": self._list_channels,
            "list_messages": self._list_messages,
            "list_members": self._list_members,
            "list_meetings": self._list_meetings,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_teams(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"$top": 100}
        if cursor and cursor.cursor:
            params["$skiptoken"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/me/joinedTeams", params=params)
            for team in data.get("value", []):
                yield {
                    "type": "team",
                    "id": team["id"],
                    "data": team,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if "@odata.nextLink" in data:
                # Extract nextLink for pagination
                import urllib.parse
                parsed = urllib.parse.urlparse(data["@odata.nextLink"])
                params = urllib.parse.parse_qs(parsed.query)
                params = {k: v[0] for k, v in params.items()}
            else:
                break

    async def _list_channels(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        team_id = filters.get("team_id")
        if not team_id:
            raise ValueError("team_id filter required")

        params = {"$top": 100}
        if cursor and cursor.cursor:
            params["$skiptoken"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/teams/{team_id}/channels", params=params)
            for channel in data.get("value", []):
                yield {
                    "type": "channel",
                    "id": channel["id"],
                    "data": channel,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if "@odata.nextLink" in data:
                import urllib.parse
                parsed = urllib.parse.urlparse(data["@odata.nextLink"])
                params = urllib.parse.parse_qs(parsed.query)
                params = {k: v[0] for k, v in params.items()}
            else:
                break

    async def _list_messages(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        team_id = filters.get("team_id")
        channel_id = filters.get("channel_id")
        if not team_id or not channel_id:
            raise ValueError("team_id and channel_id filters required")

        params = {"$top": 100}
        if filters and filters.get("start_date"):
            params["$filter"] = f"createdDateTime ge {filters['start_date']}"
        if cursor and cursor.cursor:
            params["$skiptoken"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/teams/{team_id}/channels/{channel_id}/messages", params=params)
            for message in data.get("value", []):
                yield {
                    "type": "message",
                    "id": message["id"],
                    "data": message,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if "@odata.nextLink" in data:
                import urllib.parse
                parsed = urllib.parse.urlparse(data["@odata.nextLink"])
                params = urllib.parse.parse_qs(parsed.query)
                params = {k: v[0] for k, v in params.items()}
            else:
                break

    async def _list_members(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        team_id = filters.get("team_id")
        if not team_id:
            raise ValueError("team_id filter required")

        params = {"$top": 100}
        if cursor and cursor.cursor:
            params["$skiptoken"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/teams/{team_id}/members", params=params)
            for member in data.get("value", []):
                yield {
                    "type": "member",
                    "id": member["id"],
                    "data": member,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if "@odata.nextLink" in data:
                import urllib.parse
                parsed = urllib.parse.urlparse(data["@odata.nextLink"])
                params = urllib.parse.parse_qs(parsed.query)
                params = {k: v[0] for k, v in params.items()}
            else:
                break

    async def _list_meetings(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"$top": 50}
        if filters and filters.get("start_time"):
            params["$filter"] = f"startDateTime ge {filters['start_time']}"
        if cursor and cursor.cursor:
            params["$skiptoken"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/me/onlineMeetings", params=params)
            for meeting in data.get("value", []):
                yield {
                    "type": "meeting",
                    "id": meeting["id"],
                    "data": meeting,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if "@odata.nextLink" in data:
                import urllib.parse
                parsed = urllib.parse.urlparse(data["@odata.nextLink"])
                params = urllib.parse.parse_qs(parsed.query)
                params = {k: v[0] for k, v in params.items()}
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
            "reply_message": self._reply_message,
            "create_meeting": self._create_meeting,
            "add_member": self._add_member,
            "remove_member": self._remove_member,
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
        team_id = msg_data.get("team_id")
        channel_id = msg_data.get("channel_id")
        if not team_id or not channel_id:
            raise ValueError("team_id and channel_id required")

        payload = {
            "body": {
                "contentType": "html",
                "content": msg_data.get("content", ""),
            }
        }
        await self._make_request("POST", f"/teams/{team_id}/channels/{channel_id}/messages", json=payload)

    async def _reply_message(self, msg_data: Dict[str, Any]):
        team_id = msg_data.get("team_id")
        channel_id = msg_data.get("channel_id")
        message_id = msg_data.get("message_id")
        if not team_id or not channel_id or not message_id:
            raise ValueError("team_id, channel_id, and message_id required")

        payload = {
            "body": {
                "contentType": "html",
                "content": msg_data.get("content", ""),
            }
        }
        await self._make_request("POST", f"/teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies", json=payload)

    async def _create_meeting(self, meeting_data: Dict[str, Any]):
        payload = {
            "subject": meeting_data.get("subject", "VCOS Meeting"),
            "startDateTime": meeting_data.get("start_time"),
            "endDateTime": meeting_data.get("end_time"),
            "participants": {
                "attendees": [
                    {
                        "identity": {
                            "user": {"id": attendee},
                        },
                        "role": "presenter",
                    }
                    for attendee in meeting_data.get("attendees", [])
                ]
            },
            "isBroadcast": meeting_data.get("is_broadcast", False),
            "allowedPresenters": meeting_data.get("allowed_presenters", "everyone"),
        }
        await self._make_request("POST", "/me/onlineMeetings", json=payload)

    async def _add_member(self, member_data: Dict[str, Any]):
        team_id = member_data.get("team_id")
        user_id = member_data.get("user_id")
        if not team_id or not user_id:
            raise ValueError("team_id and user_id required")

        payload = {
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": ["member"],
            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_id}')",
        }
        await self._make_request("POST", f"/teams/{team_id}/members", json=payload)

    async def _remove_member(self, member_data: Dict[str, Any]):
        team_id = member_data.get("team_id")
        user_id = member_data.get("user_id")
        if not team_id or not user_id:
            raise ValueError("team_id and user_id required")

        await self._make_request("DELETE", f"/teams/{team_id}/members/{user_id}")

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/me")
            return "id" in data
        except Exception as e:
            logger.error(f"Teams connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(TeamsConnector, TeamsConnector.CONFIG)