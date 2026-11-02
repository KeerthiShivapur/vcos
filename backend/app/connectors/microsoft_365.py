"""
Microsoft 365 / Entra ID Connector for VCOS.

Provides integration with Microsoft Graph API for:
- User and group management (Entra ID)
- Outlook email and calendar
- OneDrive and SharePoint
- Teams meetings and channels
- Organizational units and roles
"""

import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlencode

from app.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    AuthType,
    RateLimitConfig,
    SyncCursor,
    SyncResult,
)

logger = logging.getLogger(__name__)


class Microsoft365Connector(BaseConnector):
    """Microsoft 365 / Entra ID Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="microsoft_365",
        display_name="Microsoft 365",
        description="Microsoft's productivity suite with Entra ID, Outlook, Teams, SharePoint",
        category="identity",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "tenant_id": {"type": "string", "description": "Microsoft Entra tenant ID"},
                "scopes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["client_id", "client_secret", "redirect_uri", "tenant_id"],
        },
        required_scopes=[
            "https://graph.microsoft.com/User.Read.All",
            "https://graph.microsoft.com/Group.Read.All",
            "https://graph.microsoft.com/Mail.Read",
            "https://graph.microsoft.com/Calendars.Read",
            "https://graph.microsoft.com/Files.Read.All",
            "https://graph.microsoft.com/Team.ReadBasic.All",
            "https://graph.microsoft.com/ChannelMessage.Read.All",
            "offline_access",
        ],
        supported_operations=[
            # User/Group operations (Entra ID)
            "list_users",
            "get_user",
            "create_user",
            "update_user",
            "delete_user",
            "list_groups",
            "get_group",
            "create_group",
            "update_group",
            "delete_group",
            "list_group_members",
            "add_group_member",
            "remove_group_member",
            # Outlook/Mail
            "list_messages",
            "get_message",
            "send_message",
            "create_draft",
            # Calendar
            "list_events",
            "get_event",
            "create_event",
            "update_event",
            "delete_event",
            "list_calendars",
            "get_calendar",
            # OneDrive/SharePoint
            "list_drives",
            "get_drive",
            "list_drive_items",
            "get_drive_item",
            "upload_file",
            "download_file",
            # Teams
            "list_teams",
            "get_team",
            "list_channels",
            "get_channel",
            "list_channel_messages",
            "send_channel_message",
        ],
        webhook_events=[
            "user.created",
            "user.updated",
            "user.deleted",
            "group.created",
            "group.updated",
            "group.deleted",
            "group.member.added",
            "group.member.removed",
            "message.created",
            "message.updated",
            "message.deleted",
            "event.created",
            "event.updated",
            "event.deleted",
            "file.created",
            "file.updated",
            "file.deleted",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=600,
            burst=20,
        ),
    )

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    AUTHORIZE_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.client_id = connection_config.get("client_id")
        self.client_secret = connection_config.get("client_secret")
        self.redirect_uri = connection_config.get("redirect_uri")
        self.tenant_id = connection_config.get("tenant_id")
        self.scopes = connection_config.get("scopes", [
            "https://graph.microsoft.com/User.Read.All",
            "https://graph.microsoft.com/Group.Read.All",
            "https://graph.microsoft.com/Mail.Read",
            "https://graph.microsoft.com/Calendars.Read",
            "https://graph.microsoft.com/Files.Read.All",
            "https://graph.microsoft.com/Team.ReadBasic.All",
            "https://graph.microsoft.com/ChannelMessage.Read.All",
            "offline_access",
        ])
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with Microsoft using OAuth2 client credentials or authorization code flow."""
        from app.connectors.base import TokenManager

        self._token_manager = TokenManager(
            self.client_id,
            self.client_secret,
            self.TOKEN_URL.format(tenant_id=self.tenant_id),
        )
        await self._token_manager.get_access_token()
        self._authenticated = True
        logger.info("Microsoft 365 authenticated")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    # =========================================================================
    # USER OPERATIONS (Entra ID)
    # =========================================================================

    async def list_users(
        self,
        cursor: Optional[str] = None,
        limit: int = 100,
        filter_query: Optional[str] = None,
    ) -> SyncResult:
        """List users from Entra ID."""
        params = {"$top": min(limit, 999), "$select": "id,displayName,userPrincipalName,mail,jobTitle,department,officeLocation,accountEnabled,createdDateTime"}
        if filter_query:
            params["$filter"] = filter_query
        if cursor:
            params["$skiptoken"] = cursor

        response = await self._request("GET", "/users", params=params)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.nextLink")
        if next_cursor:
            import urllib.parse
            parsed = urllib.parse.urlparse(next_cursor)
            next_cursor = urllib.parse.parse_qs(parsed.query).get("$skiptoken", [None])[0]

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific user from Entra ID."""
        response = await self._request("GET", f"/users/{user_id}")
        return response.json()

    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user in Entra ID."""
        required_fields = ["accountEnabled", "displayName", "mailNickname", "userPrincipalName", "passwordProfile"]
        for field in required_fields:
            if field not in user_data:
                raise ValueError(f"Required field missing: {field}")
        
        response = await self._request("POST", "/users", json=user_data)
        return response.json()

    async def update_user(self, user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing user in Entra ID."""
        response = await self._request("PATCH", f"/users/{user_id}", json=user_data)
        return response.json()

    async def delete_user(self, user_id: str) -> bool:
        """Delete a user from Entra ID."""
        response = await self._request("DELETE", f"/users/{user_id}")
        return response.status_code == 204

    # =========================================================================
    # GROUP OPERATIONS
    # =========================================================================

    async def list_groups(
        self,
        cursor: Optional[str] = None,
        limit: int = 100,
        filter_query: Optional[str] = None,
    ) -> SyncResult:
        """List groups from Entra ID."""
        params = {"$top": min(limit, 999), "$select": "id,displayName,description,groupTypes,mail,mailEnabled,securityEnabled,createdDateTime"}
        if filter_query:
            params["$filter"] = filter_query
        if cursor:
            params["$skiptoken"] = cursor

        response = await self._request("GET", "/groups", params=params)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.nextLink")
        if next_cursor:
            import urllib.parse
            parsed = urllib.parse.urlparse(next_cursor)
            next_cursor = urllib.parse.parse_qs(parsed.query).get("$skiptoken", [None])[0]

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific group from Entra ID."""
        response = await self._request("GET", f"/groups/{group_id}")
        return response.json()

    async def create_group(self, group_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new group in Entra ID."""
        required_fields = ["displayName", "mailEnabled", "mailNickname", "securityEnabled"]
        for field in required_fields:
            if field not in group_data:
                raise ValueError(f"Required field missing: {field}")
        
        response = await self._request("POST", "/groups", json=group_data)
        return response.json()

    async def list_group_members(
        self,
        group_id: str,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> SyncResult:
        """List members of a group."""
        params = {"$top": min(limit, 999)}
        if cursor:
            params["$skiptoken"] = cursor

        response = await self._request("GET", f"/groups/{group_id}/members", params=params)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.nextLink")
        if next_cursor:
            import urllib.parse
            parsed = urllib.parse.urlparse(next_cursor)
            next_cursor = urllib.parse.parse_qs(parsed.query).get("$skiptoken", [None])[0]

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def add_group_member(self, group_id: str, user_id: str) -> bool:
        """Add a member to a group."""
        response = await self._request("POST", f"/groups/{group_id}/members/$ref", json={"@odata.id": f"{self.GRAPH_BASE_URL}/directoryObjects/{user_id}"})
        return response.status_code == 204

    async def remove_group_member(self, group_id: str, user_id: str) -> bool:
        """Remove a member from a group."""
        response = await self._request("DELETE", f"/groups/{group_id}/members/{user_id}/$ref")
        return response.status_code == 204

    # =========================================================================
    # OUTLOOK MAIL OPERATIONS
    # =========================================================================

    async def list_messages(
        self,
        user_id: str = "me",
        cursor: Optional[str] = None,
        limit: int = 50,
        filter_query: Optional[str] = None,
    ) -> SyncResult:
        """List messages from Outlook."""
        params = {"$top": min(limit, 100), "$select": "id,subject,from,toRecipients,receivedDateTime,hasAttachments,importance,isRead"}
        if filter_query:
            params["$filter"] = filter_query
        if cursor:
            params["$skiptoken"] = cursor

        response = await self._request("GET", f"/users/{user_id}/messages", params=params)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.nextLink")
        if next_cursor:
            import urllib.parse
            parsed = urllib.parse.urlparse(next_cursor)
            next_cursor = urllib.parse.parse_qs(parsed.query).get("$skiptoken", [None])[0]

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def get_message(self, message_id: str, user_id: str = "me") -> Optional[Dict[str, Any]]:
        """Get a specific message."""
        response = await self._request("GET", f"/users/{user_id}/messages/{message_id}")
        return response.json()

    async def send_message(self, message_data: Dict[str, Any], user_id: str = "me") -> Dict[str, Any]:
        """Send an email message."""
        if "message" not in message_data:
            raise ValueError("message field is required")
        response = await self._request("POST", f"/users/{user_id}/sendMail", json=message_data)
        return {"success": True, "message_id": message_data.get("message", {}).get("id")}

    # =========================================================================
    # CALENDAR OPERATIONS
    # =========================================================================

    async def list_events(
        self,
        user_id: str = "me",
        cursor: Optional[str] = None,
        limit: int = 50,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> SyncResult:
        """List calendar events."""
        params = {
            "$top": min(limit, 100),
            "$select": "id,subject,start,end,location,attendees,organizer,isOnlineMeeting,onlineMeetingUrl",
            "$orderby": "start/dateTime",
        }
        if start_time and end_time:
            params["$filter"] = f"start/dateTime ge '{start_time}' and end/dateTime le '{end_time}'"
        if cursor:
            params["$skiptoken"] = cursor

        response = await self._request("GET", f"/users/{user_id}/events", params=params)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.nextLink")
        if next_cursor:
            import urllib.parse
            parsed = urllib.parse.urlparse(next_cursor)
            next_cursor = urllib.parse.parse_qs(parsed.query).get("$skiptoken", [None])[0]

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def get_event(self, event_id: str, user_id: str = "me") -> Optional[Dict[str, Any]]:
        """Get a specific calendar event."""
        response = await self._request("GET", f"/users/{user_id}/events/{event_id}")
        return response.json()

    async def create_event(self, event_data: Dict[str, Any], user_id: str = "me") -> Dict[str, Any]:
        """Create a calendar event."""
        required_fields = ["subject", "start", "end"]
        for field in required_fields:
            if field not in event_data:
                raise ValueError(f"Required field missing: {field}")
        
        response = await self._request("POST", f"/users/{user_id}/events", json=event_data)
        return response.json()

    async def update_event(self, event_id: str, event_data: Dict[str, Any], user_id: str = "me") -> Dict[str, Any]:
        """Update a calendar event."""
        response = await self._request("PATCH", f"/users/{user_id}/events/{event_id}", json=event_data)
        return response.json()

    async def delete_event(self, event_id: str, user_id: str = "me") -> bool:
        """Delete a calendar event."""
        response = await self._request("DELETE", f"/users/{user_id}/events/{event_id}")
        return response.status_code == 204

    async def list_calendars(self, user_id: str = "me") -> List[Dict[str, Any]]:
        """List user's calendars."""
        response = await self._request("GET", f"/users/{user_id}/calendars")
        return response.json().get("value", [])

    # =========================================================================
    # ONEDRIVE/SHAREPOINT OPERATIONS
    # =========================================================================

    async def list_drives(self, user_id: str = "me") -> List[Dict[str, Any]]:
        """List user's drives."""
        response = await self._request("GET", f"/users/{user_id}/drives")
        return response.json().get("value", [])

    async def get_drive(self, drive_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific drive."""
        response = await self._request("GET", f"/drives/{drive_id}")
        return response.json()

    async def list_drive_items(
        self,
        drive_id: str,
        item_id: str = "root",
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> SyncResult:
        """List items in a drive folder."""
        params = {"$top": min(limit, 200)}
        if cursor:
            params["$skiptoken"] = cursor

        response = await self._request("GET", f"/drives/{drive_id}/items/{item_id}/children", params=params)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.nextLink")
        if next_cursor:
            import urllib.parse
            parsed = urllib.parse.urlparse(next_cursor)
            next_cursor = urllib.parse.parse_qs(parsed.query).get("$skiptoken", [None])[0]

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def upload_file(
        self,
        drive_id: str,
        parent_id: str,
        filename: str,
        content: bytes,
    ) -> Dict[str, Any]:
        """Upload a file to OneDrive/SharePoint."""
        # For large files, use upload session
        upload_url = f"/drives/{drive_id}/items/{parent_id}:/{filename}:/content"
        response = await self._request("PUT", upload_url, data=content, headers={"Content-Type": "application/octet-stream"})
        return response.json()

    # =========================================================================
    # TEAMS OPERATIONS
    # =========================================================================

    async def list_teams(
        self,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> SyncResult:
        """List Teams the user has access to."""
        params = {"$top": min(limit, 100)}
        if cursor:
            params["$skiptoken"] = cursor

        response = await self._request("GET", "/me/joinedTeams", params=params)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.nextLink")
        if next_cursor:
            import urllib.parse
            parsed = urllib.parse.urlparse(next_cursor)
            next_cursor = urllib.parse.parse_qs(parsed.query).get("$skiptoken", [None])[0]

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def get_team(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific team."""
        response = await self._request("GET", f"/teams/{team_id}")
        return response.json()

    async def list_channels(
        self,
        team_id: str,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> SyncResult:
        """List channels in a team."""
        params = {"$top": min(limit, 100)}
        if cursor:
            params["$skiptoken"] = cursor

        response = await self._request("GET", f"/teams/{team_id}/channels", params=params)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.nextLink")
        if next_cursor:
            import urllib.parse
            parsed = urllib.parse.urlparse(next_cursor)
            next_cursor = urllib.parse.parse_qs(parsed.query).get("$skiptoken", [None])[0]

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def list_channel_messages(
        self,
        team_id: str,
        channel_id: str,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> SyncResult:
        """List messages in a channel."""
        params = {"$top": min(limit, 50), "$orderby": "lastModifiedDateTime desc"}
        if cursor:
            params["$skiptoken"] = cursor

        response = await self._request("GET", f"/teams/{team_id}/channels/{channel_id}/messages", params=params)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.nextLink")
        if next_cursor:
            import urllib.parse
            parsed = urllib.parse.urlparse(next_cursor)
            next_cursor = urllib.parse.parse_qs(parsed.query).get("$skiptoken", [None])[0]

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def send_channel_message(
        self,
        team_id: str,
        channel_id: str,
        message: str,
    ) -> Dict[str, Any]:
        """Send a message to a Teams channel."""
        response = await self._request("POST", f"/teams/{team_id}/channels/{channel_id}/messages", json={"body": {"content": message}})
        return response.json()

    # =========================================================================
    # WEBHOOK SUPPORT
    # =========================================================================

    async def create_subscription(
        self,
        resource: str,
        change_types: List[str],
        notification_url: str,
        expiration: datetime,
        client_state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Microsoft Graph subscription for webhook notifications."""
        subscription_data = {
            "changeType": ",".join(change_types),
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": expiration.isoformat() + "Z",
            "clientState": client_state,
        }
        response = await self._request("POST", "/subscriptions", json=subscription_data)
        return response.json()

    async def delete_subscription(self, subscription_id: str) -> bool:
        """Delete a subscription."""
        response = await self._request("DELETE", f"/subscriptions/{subscription_id}")
        return response.status_code == 204

    async def renew_subscription(self, subscription_id: str, expiration: datetime) -> Dict[str, Any]:
        """Renew a subscription."""
        response = await self._request("PATCH", f"/subscriptions/{subscription_id}", json={
            "expirationDateTime": expiration.isoformat() + "Z",
        })
        return response.json()

    # =========================================================================
    # INCREMENTAL SYNC SUPPORT
    # =========================================================================

    async def get_delta_link(self, resource: str) -> str:
        """Get a delta link for incremental sync."""
        response = await self._request("GET", f"/{resource}/delta")
        return response.json().get("@odata.deltaLink", "")

    async def sync_changes(
        self,
        delta_link: str,
        limit: int = 1000,
    ) -> SyncResult:
        """Sync changes using delta link."""
        response = await self._request("GET", delta_link)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.deltaLink") or data.get("@odata.nextLink")
        
        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )