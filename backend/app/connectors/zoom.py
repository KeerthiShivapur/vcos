"""
Zoom Connector for VCOS.

Provides integration with Zoom for meetings, webinars, recordings, and users.
"""

import logging
from datetime import datetime
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


class ZoomConnector(BaseConnector):
    """Zoom Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="zoom",
        display_name="Zoom",
        description="Video conferencing, webinars, and collaboration platform",
        category="communication",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "account_id": {"type": "string", "description": "Zoom Account ID"},
                "access_token": {"type": "string", "description": "OAuth access token"},
                "refresh_token": {"type": "string"},
            },
            "required": ["client_id", "client_secret", "redirect_uri", "account_id"],
        },
        required_scopes=[
            "meeting:read",
            "meeting:write",
            "meeting:admin",
            "recording:read",
            "recording:write",
            "user:read",
            "user:write",
            "webinar:read",
            "webinar:write",
            "cloud_recording:read",
            "cloud_recording:write",
        ],
        supported_operations=[
            "list_meetings",
            "get_meeting",
            "create_meeting",
            "update_meeting",
            "delete_meeting",
            "list_recordings",
            "get_recording",
            "delete_recording",
            "list_users",
            "get_user",
            "create_user",
            "update_user",
            "list_webinars",
            "get_webinar",
            "create_webinar",
            "list_past_meetings",
            "get_meeting_participants",
            "get_meeting_polls",
            "create_meeting_poll",
        ],
        webhook_events=[
            "meeting.created",
            "meeting.updated",
            "meeting.deleted",
            "meeting.started",
            "meeting.ended",
            "meeting.participant_joined",
            "meeting.participant_left",
            "recording.completed",
            "recording.deleted",
            "webinar.created",
            "webinar.updated",
            "webinar.started",
            "webinar.ended",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=100,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/zoom.svg",
        documentation_url="https://marketplace.zoom.us/docs/api-reference/",
    )

    BASE_URL = "https://api.zoom.us/v2"
    TOKEN_URL = "https://zoom.us/oauth/token"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.account_id = connection_config.get("account_id")
        self.access_token = connection_config.get("access_token")
        self.refresh_token = connection_config.get("refresh_token")
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with Zoom using OAuth2 or JWT."""
        if self.access_token:
            self._authenticated = True
            logger.info("Zoom authenticated with access token")
            return True

        client_id = self.connection_config.get("client_id")
        client_secret = self.connection_config.get("client_secret")
        account_id = self.connection_config.get("account_id")
        
        if client_id and client_secret and account_id:
            from app.connectors.base import TokenManager
            self._token_manager = TokenManager(client_id, client_secret, self.TOKEN_URL)
            # For server-to-server OAuth, we need account_id in the request
            self._token_manager._initial_token = self._get_server_token
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info("Zoom authenticated with server-to-server OAuth")
            return True

        raise ValueError("Zoom requires access_token or OAuth2 credentials (client_id, client_secret, account_id)")

    async def _get_server_token(self):
        """Get token using server-to-server OAuth."""
        data = {
            "grant_type": "account_credentials",
            "account_id": self.account_id,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.TOKEN_URL,
                data=data,
                auth=aiohttp.BasicAuth(self.connection_config["client_id"], self.connection_config["client_secret"])
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Token request failed: {await resp.text()}")
                token_data = await resp.json()
                self._token_manager._store_tokens(token_data)

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
        """Make Zoom API request with error handling."""
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
                    raise Exception(f"Zoom API error: {resp.status} - {error_text}")
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
            "list_meetings": self._list_meetings,
            "list_recordings": self._list_recordings,
            "list_users": self._list_users,
            "list_webinars": self._list_webinars,
            "list_past_meetings": self._list_past_meetings,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_meetings(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        user_id = filters.get("user_id", "me")
        params = {"page_size": 100, "type": "scheduled"}
        if filters and filters.get("from"):
            params["from"] = filters["from"]
        if filters and filters.get("to"):
            params["to"] = filters["to"]
        if cursor and cursor.cursor:
            params["next_page_token"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/users/{user_id}/meetings", params=params)
            for meeting in data.get("meetings", []):
                yield {
                    "type": "meeting",
                    "id": meeting["id"],
                    "data": meeting,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            next_token = data.get("next_page_token")
            if next_token:
                params["next_page_token"] = next_token
            else:
                break

    async def _list_recordings(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        user_id = filters.get("user_id", "me")
        params = {"page_size": 100}
        if filters and filters.get("from"):
            params["from"] = filters["from"]
        if filters and filters.get("to"):
            params["to"] = filters["to"]
        if filters and filters.get("meeting_id"):
            params["meeting_id"] = filters["meeting_id"]
        if cursor and cursor.cursor:
            params["next_page_token"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/users/{user_id}/recordings", params=params)
            for recording in data.get("meetings", []):
                yield {
                    "type": "recording",
                    "id": recording["uuid"],
                    "data": recording,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            next_token = data.get("next_page_token")
            if next_token:
                params["next_page_token"] = next_token
            else:
                break

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page_size": 100, "status": "active"}
        if cursor and cursor.cursor:
            params["next_page_token"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/users", params=params)
            for user in data.get("users", []):
                yield {
                    "type": "user",
                    "id": user["id"],
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            next_token = data.get("next_page_token")
            if next_token:
                params["next_page_token"] = next_token
            else:
                break

    async def _list_webinars(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        user_id = filters.get("user_id", "me")
        params = {"page_size": 100}
        if cursor and cursor.cursor:
            params["next_page_token"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/users/{user_id}/webinars", params=params)
            for webinar in data.get("webinars", []):
                yield {
                    "type": "webinar",
                    "id": webinar["id"],
                    "data": webinar,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            next_token = data.get("next_page_token")
            if next_token:
                params["next_page_token"] = next_token
            else:
                break

    async def _list_past_meetings(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        user_id = filters.get("user_id", "me")
        params = {"page_size": 100, "type": "past"}
        if filters and filters.get("from"):
            params["from"] = filters["from"]
        if filters and filters.get("to"):
            params["to"] = filters["to"]
        if cursor and cursor.cursor:
            params["next_page_token"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/users/{user_id}/meetings", params=params)
            for meeting in data.get("meetings", []):
                yield {
                    "type": "past_meeting",
                    "id": meeting["id"],
                    "data": meeting,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            next_token = data.get("next_page_token")
            if next_token:
                params["next_page_token"] = next_token
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
            "create_meeting": self._create_meeting,
            "update_meeting": self._update_meeting,
            "delete_meeting": self._delete_meeting,
            "create_user": self._create_user,
            "update_user": self._update_user,
            "create_webinar": self._create_webinar,
            "create_meeting_poll": self._create_meeting_poll,
        }

        handler = handlers.get(operation)
        if not handler:
            result.success = False
            result.errors.append({"error": f"Unsupported push operation: {operation}"})
            return result

        for item in data:
            try:
                await handler(item)
                result.records_created += 1 if "create" in operation else 0
                result.records_updated += 1 if "update" in operation else 0
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_meeting(self, meeting_data: Dict[str, Any]):
        user_id = meeting_data.get("user_id", "me")
        payload = {
            "topic": meeting_data.get("topic", "VCOS Meeting"),
            "type": meeting_data.get("type", 2),  # 2 = scheduled
            "start_time": meeting_data.get("start_time"),
            "duration": meeting_data.get("duration", 60),
            "timezone": meeting_data.get("timezone", "UTC"),
            "password": meeting_data.get("password"),
            "agenda": meeting_data.get("agenda"),
            "settings": {
                "host_video": meeting_data.get("host_video", True),
                "participant_video": meeting_data.get("participant_video", True),
                "join_before_host": meeting_data.get("join_before_host", False),
                "mute_upon_entry": meeting_data.get("mute_upon_entry", True),
                "watermark": meeting_data.get("watermark", False),
                "use_pmi": meeting_data.get("use_pmi", False),
                "approval_type": meeting_data.get("approval_type", 2),
                "registration_type": meeting_data.get("registration_type", 1),
                "audio": meeting_data.get("audio", "both"),
                "auto_recording": meeting_data.get("auto_recording", "none"),
            },
        }
        await self._make_request("POST", f"/users/{user_id}/meetings", json=payload)

    async def _update_meeting(self, meeting_data: Dict[str, Any]):
        meeting_id = meeting_data.get("meeting_id")
        if not meeting_id:
            raise ValueError("meeting_id required")

        payload = {
            "topic": meeting_data.get("topic"),
            "start_time": meeting_data.get("start_time"),
            "duration": meeting_data.get("duration"),
            "timezone": meeting_data.get("timezone"),
            "password": meeting_data.get("password"),
            "agenda": meeting_data.get("agenda"),
            "settings": meeting_data.get("settings", {}),
        }
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        await self._make_request("PATCH", f"/meetings/{meeting_id}", json=payload)

    async def _delete_meeting(self, meeting_data: Dict[str, Any]):
        meeting_id = meeting_data.get("meeting_id")
        if not meeting_id:
            raise ValueError("meeting_id required")

        await self._make_request("DELETE", f"/meetings/{meeting_id}")

    async def _create_user(self, user_data: Dict[str, Any]):
        payload = {
            "action": "create",
            "user_info": {
                "email": user_data.get("email"),
                "type": user_data.get("type", 2),  # 2 = licensed
                "first_name": user_data.get("first_name"),
                "last_name": user_data.get("last_name"),
                "password": user_data.get("password"),
                "timezone": user_data.get("timezone", "UTC"),
                "language": user_data.get("language", "en-US"),
            },
        }
        await self._make_request("POST", "/users", json=payload)

    async def _update_user(self, user_data: Dict[str, Any]):
        user_id = user_data.get("user_id")
        if not user_id:
            raise ValueError("user_id required")

        payload = {
            "first_name": user_data.get("first_name"),
            "last_name": user_data.get("last_name"),
            "type": user_data.get("type"),
            "timezone": user_data.get("timezone"),
            "language": user_data.get("language"),
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        await self._make_request("PATCH", f"/users/{user_id}", json=payload)

    async def _create_webinar(self, webinar_data: Dict[str, Any]):
        user_id = webinar_data.get("user_id", "me")
        payload = {
            "topic": webinar_data.get("topic", "VCOS Webinar"),
            "type": webinar_data.get("type", 5),  # 5 = webinar
            "start_time": webinar_data.get("start_time"),
            "duration": webinar_data.get("duration", 60),
            "timezone": webinar_data.get("timezone", "UTC"),
            "password": webinar_data.get("password"),
            "agenda": webinar_data.get("agenda"),
            "settings": {
                "host_video": webinar_data.get("host_video", True),
                "panelists_video": webinar_data.get("panelists_video", True),
                "practice_session": webinar_data.get("practice_session", False),
                "hd_video": webinar_data.get("hd_video", True),
                "approval_type": webinar_data.get("approval_type", 2),
                "registration_type": webinar_data.get("registration_type", 1),
                "audio": webinar_data.get("audio", "both"),
                "auto_recording": webinar_data.get("auto_recording", "cloud"),
            },
        }
        await self._make_request("POST", f"/users/{user_id}/webinars", json=payload)

    async def _create_meeting_poll(self, poll_data: Dict[str, Any]):
        meeting_id = poll_data.get("meeting_id")
        if not meeting_id:
            raise ValueError("meeting_id required")

        payload = {
            "polling_type": "poll",
            "questions": poll_data.get("questions", []),
        }
        await self._make_request("POST", f"/meetings/{meeting_id}/polls", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/users/me")
            return "id" in data
        except Exception as e:
            logger.error(f"Zoom connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(ZoomConnector, ZoomConnector.CONFIG)