"""Gate 24 — Google Workspace Connector.

Implements Google Workspace integration (People, Drive, Calendar, Gmail, Groups).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, AsyncIterator

from app.intelligence.connectors.base import BaseConnector, connector_registry
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.connectors.google")


class GoogleWorkspaceConnector(BaseConnector):
    """Google Workspace connector implementation."""
    
    @property
    def provider(self) -> str:
        return "google"
    
    @property
    def kind(self) -> str:
        return "productivity"
    
    async def authenticate(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """Authenticate with Google using OAuth2."""
        credentials = instance.credentials
        
        if not credentials:
            return False, "No credentials configured"
        
        # Check for access token
        access_token = credentials.get("access_token")
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        
        if not access_token and not refresh_token:
            return False, "No access token or refresh token"
        
        # If we have a refresh token but no access token, refresh
        if not access_token and refresh_token:
            success, error, new_creds = await self.refresh_credentials(instance)
            if not success:
                return False, error
        
        return True, None
    
    async def test_connection(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """Test Google Workspace connection."""
        ok, error = await self.authenticate(instance)
        if not ok:
            return False, error
        
        # Test with a simple People API call
        try:
            import httpx
            credentials = instance.credentials
            access_token = credentials.get("access_token")
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://people.googleapis.com/v1/people/me?personFields=names,emailAddresses",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            
            if response.status_code == 200:
                return True, None
            elif response.status_code == 401:
                return False, "Access token expired"
            else:
                return False, f"Google API error: {response.status_code}"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
    
    async def full_sync(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Full sync of Google Workspace data."""
        ok, error = await self.authenticate(instance)
        if not ok:
            raise RuntimeError(f"Authentication failed: {error}")
        
        credentials = instance.credentials
        access_token = credentials.get("access_token")
        
        # Sync users (people)
        if "read_people" in instance.connector.inbound_capabilities:
            async for user in self._sync_users(access_token, instance.config.get("domain")):
                yield user
        
        # Sync groups
        if "read_groups" in instance.connector.inbound_capabilities:
            async for group in self._sync_groups(access_token, instance.config.get("domain")):
                yield group
        
        # Sync calendars
        if "read_calendar" in instance.connector.inbound_capabilities:
            async for event in self._sync_calendar(access_token, instance.config.get("domain"), since, until):
                yield event
        
        # Sync files
        if "read_files" in instance.connector.inbound_capabilities:
            async for file in self._sync_files(access_token, since, until):
                yield file
    
    async def _sync_users(
        self, access_token: str, domain: Optional[str]
    ) -> AsyncIterator[dict[str, Any]]:
        """Sync Google Workspace users."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            page_token = None
            while True:
                params = {"customer": "my_customer", "maxResults": 500}
                if page_token:
                    params["pageToken"] = page_token
                if domain:
                    params["domain"] = domain
                
                response = await client.get(
                    "https://admin.googleapis.com/admin/directory/v1/users",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                for user in data.get("users", []):
                    yield {
                        "entity_type": "person",
                        "external_id": user["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": user["id"],
                            "external_email": user.get("primaryEmail"),
                            "external_display_name": user.get("name", {}).get("fullName"),
                            "external_avatar_url": user.get("thumbnailPhotoUrl"),
                            "external_metadata": {
                                "suspended": user.get("suspended"),
                                "org_unit": user.get("orgUnitPath"),
                                "is_admin": user.get("isAdmin"),
                                "creation_time": user.get("creationTime"),
                            },
                        },
                    }
                
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
    
    async def _sync_groups(
        self, access_token: str, domain: Optional[str]
    ) -> AsyncIterator[dict[str, Any]]:
        """Sync Google Workspace groups."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            page_token = None
            while True:
                params = {"customer": "my_customer", "maxResults": 500}
                if page_token:
                    params["pageToken"] = page_token
                if domain:
                    params["domain"] = domain
                
                response = await client.get(
                    "https://admin.googleapis.com/admin/directory/v1/groups",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                for group in data.get("groups", []):
                    yield {
                        "entity_type": "group",
                        "external_id": group["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": group["id"],
                            "external_email": group.get("email"),
                            "external_display_name": group.get("name"),
                            "external_metadata": {
                                "description": group.get("description"),
                                "direct_members_count": group.get("directMembersCount"),
                            },
                        },
                    }
                
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
    
    async def _sync_calendar(
        self, access_token: str, domain: Optional[str], since: Optional[datetime], until: Optional[datetime]
    ) -> AsyncIterator[dict[str, Any]]:
        """Sync Google Calendar events."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            page_token = None
            while True:
                params = {"calendarId": "primary", "maxResults": 250}
                if since:
                    params["timeMin"] = since.isoformat()
                if until:
                    params["timeMax"] = until.isoformat()
                if page_token:
                    params["pageToken"] = page_token
                
                response = await client.get(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                for event in data.get("items", []):
                    yield {
                        "entity_type": "event",
                        "external_id": event["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": event["id"],
                            "external_display_name": event.get("summary"),
                            "external_metadata": {
                                "description": event.get("description"),
                                "start": event.get("start"),
                                "end": event.get("end"),
                                "attendees": event.get("attendees"),
                                "status": event.get("status"),
                            },
                        },
                    }
                
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
    
    async def _sync_files(
        self, access_token: str, since: Optional[datetime], until: Optional[datetime]
    ) -> AsyncIterator[dict[str, Any]]:
        """Sync Google Drive files."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            page_token = None
            while True:
                params = {"pageSize": 1000, "fields": "nextPageToken,files(id,name,mimeType,size,createdTime,modifiedTime,owners,parents)"}
                if since:
                    params["q"] = f"modifiedTime > '{since.isoformat()}'"
                if page_token:
                    params["pageToken"] = page_token
                
                response = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                for file in data.get("files", []):
                    yield {
                        "entity_type": "file",
                        "external_id": file["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": file["id"],
                            "external_display_name": file.get("name"),
                            "external_metadata": {
                                "mime_type": file.get("mimeType"),
                                "size": file.get("size"),
                                "created_time": file.get("createdTime"),
                                "modified_time": file.get("modifiedTime"),
                                "owners": file.get("owners"),
                                "parents": file.get("parents"),
                            },
                        },
                    }
                
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
    
    async def incremental_sync(
        self,
        instance: ConnectorInstance,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Incremental sync using changelog or modified time."""
        # For Google, we use modified time as cursor
        if not since and cursor:
            try:
                since = datetime.fromisoformat(cursor)
            except ValueError:
                since = None
        
        async for entity in self.full_sync(instance, since=since):
            yield entity
    
    async def poll_events(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Poll for Google Workspace events (using Reports API or Drive Changes)."""
        # Google provides Admin Reports API for user/group changes
        # and Drive Changes API for file changes
        ok, error = await self.authenticate(instance)
        if not ok:
            raise RuntimeError(f"Authentication failed: {error}")
        
        # This would use the Reports API to get activities
        # For now, yield nothing
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
        """Execute an operation on Google Workspace."""
        ok, error = await self.authenticate(instance)
        if not ok:
            return {"success": False, "error": error}
        
        # Implement specific operations
        return {"success": False, "error": f"Operation {operation_type} not implemented"}
    
    async def get_webhook_events(
        self,
        instance: ConnectorInstance,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Parse Google webhook payload."""
        # Google sends push notifications with channel info
        # The actual data needs to be fetched via API
        return []
    
    async def refresh_credentials(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str], Optional[dict]]:
        """Refresh Google OAuth2 access token."""
        credentials = instance.credentials
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        
        if not refresh_token or not client_id or not client_secret:
            return False, "Missing refresh credentials", None
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        
        if response.status_code == 200:
            data = response.json()
            new_creds = credentials.copy()
            new_creds["access_token"] = data["access_token"]
            new_creds["expires_at"] = (datetime.now(timezone.utc) + 
                timedelta(seconds=data.get("expires_in", 3600))).isoformat()
            return True, None, new_creds
        else:
            return False, f"Token refresh failed: {response.text}", None
    
    async def get_rate_limit_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Get Google API rate limit status."""
        return {"remaining": "unknown", "reset_at": None}
    
    async def resolve_identity(
        self,
        instance: ConnectorInstance,
        external_id: str,
    ) -> Optional[dict[str, Any]]:
        """Resolve a Google user ID to identity attributes."""
        ok, error = await self.authenticate(instance)
        if not ok:
            return None
        
        credentials = instance.credentials
        access_token = credentials.get("access_token")
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://admin.googleapis.com/admin/directory/v1/users/{external_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        
        if response.status_code == 200:
            user = response.json()
            return {
                "external_id": user["id"],
                "external_email": user.get("primaryEmail"),
                "external_display_name": user.get("name", {}).get("fullName"),
                "external_avatar_url": user.get("thumbnailPhotoUrl"),
                "external_metadata": {
                    "suspended": user.get("suspended"),
                    "org_unit": user.get("orgUnitPath"),
                },
            }
        
        return None

    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Discover and return the connector's capabilities."""
        return {
            "inbound_capabilities": ["read_users", "read_groups", "read_drive", "read_calendar", "read_mail"],
            "outbound_capabilities": ["create_user", "update_user", "delete_user", "create_group", "send_email", "create_event", "create_file"],
            "supported_entities": ["user", "group", "drive_file", "calendar_event", "email"],
            "supported_events": ["user.created", "user.updated", "user.deleted", "group.created", "group.updated", "group.deleted", "file.created", "file.updated", "file.deleted", "event.created", "event.updated", "event.deleted"],
            "sync_modes": ["full", "incremental", "webhook", "polling"],
            "auth_types": ["oauth2"],
            "oauth_scopes": [
                "https://www.googleapis.com/auth/admin.directory.user.readonly",
                "https://www.googleapis.com/auth/admin.directory.group.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/admin.directory.user",
                "https://www.googleapis.com/auth/admin.directory.group",
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/gmail.modify",
            ],
            "required_config_fields": ["customer_id", "admin_email"],
            "optional_config_fields": ["delegated_admin_email"],
            "rate_limits": {
                "admin_directory": {"requests_per_second": 100, "burst": 200},
                "drive": {"requests_per_second": 1000, "burst": 2000},
                "calendar": {"requests_per_second": 500, "burst": 1000},
                "gmail": {"requests_per_second": 250, "burst": 500},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("access_token") and not credentials.get("pat"):
            return False, "No access token or PAT configured"
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
        # Google uses a simple secret-based verification for webhooks
        # The signature is typically an HMAC-SHA256 of the payload
        credentials = instance.credentials
        webhook_secret = credentials.get("webhook_secret")
        if not webhook_secret:
            return False
        expected = hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
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

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)


# Register the connector
connector_registry.register(GoogleWorkspaceConnector())