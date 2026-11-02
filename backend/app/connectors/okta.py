"""
Okta Identity Connector for VCOS.

Provides integration with Okta for user/group management,
SSO configuration, and lifecycle events.
"""

import asyncio
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


class OktaConnector(BaseConnector):
    """Okta Identity Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="okta",
        display_name="Okta",
        description="Enterprise identity and access management platform",
        category="identity",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Okta domain (e.g., company.okta.com)"},
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "api_token": {"type": "string", "description": "Alternative: API token for server-to-server"},
            },
            "required": ["domain"],
            "oneOf": [
                {"required": ["client_id", "client_secret", "redirect_uri"]},
                {"required": ["api_token"]},
            ],
        },
        required_scopes=["okta.users.read", "okta.groups.read", "okta.apps.read"],
        supported_operations=[
            "list_users",
            "get_user",
            "create_user",
            "update_user",
            "deactivate_user",
            "reactivate_user",
            "list_groups",
            "get_group",
            "create_group",
            "update_group",
            "add_user_to_group",
            "remove_user_from_group",
            "list_applications",
            "get_application",
            "assign_user_to_app",
            "list_user_sessions",
            "clear_user_sessions",
        ],
        webhook_events=[
            "user.lifecycle.create",
            "user.lifecycle.activate",
            "user.lifecycle.deactivate",
            "user.lifecycle.update",
            "user.lifecycle.suspend",
            "user.lifecycle.unsuspend",
            "user.lifecycle.delete",
            "group.lifecycle.create",
            "group.lifecycle.update",
            "group.lifecycle.delete",
            "group.user_membership.add",
            "group.user_membership.remove",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=300,
            burst=20,
        ),
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.domain = connection_config.get("domain")
        self.api_token = connection_config.get("api_token")
        self.base_url = f"https://{self.domain}/api/v1"
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with Okta using API token or OAuth2."""
        if self.api_token:
            self._authenticated = True
            logger.info(f"Okta authenticated with API token for {self.domain}")
            return True

        # OAuth2 flow
        client_id = self.connection_config.get("client_id")
        client_secret = self.connection_config.get("client_secret")
        if client_id and client_secret:
            from app.connectors.base import TokenManager
            token_url = f"https://{self.domain}/oauth2/v1/token"
            self._token_manager = TokenManager(client_id, client_secret, token_url)
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info(f"Okta authenticated with OAuth2 for {self.domain}")
            return True

        raise ValueError("Okta requires either api_token or OAuth2 credentials")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"SSWS {self.api_token}"
        elif self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def pull_data(
        self,
        operation: str,
        cursor: Optional[SyncCursor] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Pull data from Okta based on operation."""
        if not self._authenticated:
            await self.authenticate()

        handlers = {
            "list_users": self._list_users,
            "list_groups": self._list_groups,
            "list_applications": self._list_applications,
            "list_user_sessions": self._list_user_sessions,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List users with pagination and incremental sync."""
        params = {"limit": 200}
        if cursor and cursor.cursor:
            params["after"] = cursor.cursor
        if filters:
            if filters.get("status"):
                params["filter"] = f"status eq \"{filters['status']}\""
            if filters.get("since"):
                params["search"] = f"lastUpdated gt \"{filters['since']}\""

        while True:
            async with self.session.get(
                f"{self.base_url}/users",
                headers=await self._get_headers(),
                params=params,
            ) as resp:
                resp.raise_for_status()
                users = await resp.json()

                for user in users:
                    yield {
                        "type": "user",
                        "id": user["id"],
                        "external_id": user.get("profile", {}).get("employeeNumber"),
                        "data": {
                            "id": user["id"],
                            "status": user["status"],
                            "created": user["created"],
                            "activated": user.get("activated"),
                            "lastLogin": user.get("lastLogin"),
                            "lastUpdated": user["lastUpdated"],
                            "profile": user["profile"],
                            "credentials": user.get("credentials"),
                            "_links": user.get("_links"),
                        },
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                # Handle pagination
                link_header = resp.headers.get("Link", "")
                next_url = self._parse_next_link(link_header)
                if not next_url:
                    break
                params = {}  # URL already has params

    async def _list_groups(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List groups with pagination."""
        params = {"limit": 200}
        if cursor and cursor.cursor:
            params["after"] = cursor.cursor

        while True:
            async with self.session.get(
                f"{self.base_url}/groups",
                headers=await self._get_headers(),
                params=params,
            ) as resp:
                resp.raise_for_status()
                groups = await resp.json()

                for group in groups:
                    yield {
                        "type": "group",
                        "id": group["id"],
                        "data": {
                            "id": group["id"],
                            "type": group["type"],
                            "profile": group["profile"],
                            "_links": group.get("_links"),
                        },
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                link_header = resp.headers.get("Link", "")
                next_url = self._parse_next_link(link_header)
                if not next_url:
                    break

    async def _list_applications(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List applications."""
        params = {"limit": 200}
        if cursor and cursor.cursor:
            params["after"] = cursor.cursor

        while True:
            async with self.session.get(
                f"{self.base_url}/apps",
                headers=await self._get_headers(),
                params=params,
            ) as resp:
                resp.raise_for_status()
                apps = await resp.json()

                for app in apps:
                    yield {
                        "type": "application",
                        "id": app["id"],
                        "data": {
                            "id": app["id"],
                            "name": app["name"],
                            "label": app["label"],
                            "status": app["status"],
                            "signOnMode": app.get("signOnMode"),
                            "settings": app.get("settings"),
                            "_links": app.get("_links"),
                        },
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                link_header = resp.headers.get("Link", "")
                next_url = self._parse_next_link(link_header)
                if not next_url:
                    break

    async def _list_user_sessions(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List user sessions."""
        user_id = filters.get("user_id") if filters else None
        if not user_id:
            raise ValueError("user_id filter required for list_user_sessions")

        params = {"limit": 200}
        if cursor and cursor.cursor:
            params["after"] = cursor.cursor

        while True:
            async with self.session.get(
                f"{self.base_url}/users/{user_id}/sessions",
                headers=await self._get_headers(),
                params=params,
            ) as resp:
                resp.raise_for_status()
                sessions = await resp.json()

                for session in sessions:
                    yield {
                        "type": "session",
                        "id": session["id"],
                        "data": session,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                link_header = resp.headers.get("Link", "")
                next_url = self._parse_next_link(link_header)
                if not next_url:
                    break

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        """Push data to Okta."""
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_user": self._create_user,
            "update_user": self._update_user,
            "deactivate_user": self._deactivate_user,
            "reactivate_user": self._reactivate_user,
            "create_group": self._create_group,
            "update_group": self._update_group,
            "add_user_to_group": self._add_user_to_group,
            "remove_user_from_group": self._remove_user_from_group,
            "assign_user_to_app": self._assign_user_to_app,
        }

        handler = handlers.get(operation)
        if not handler:
            result.success = False
            result.errors.append({"error": f"Unsupported push operation: {operation}"})
            return result

        for item in data:
            try:
                await handler(item)
                if "create" in operation:
                    result.records_created += 1
                else:
                    result.records_updated += 1
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})
                logger.error(f"Push failed for {operation}: {e}")

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_user(self, user_data: Dict[str, Any]):
        """Create a new user in Okta."""
        payload = {
            "profile": user_data.get("profile", {}),
            "credentials": user_data.get("credentials", {}),
        }
        async with self.session.post(
            f"{self.base_url}/users?activate={user_data.get('activate', 'false')}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_user(self, user_data: Dict[str, Any]):
        """Update an existing user."""
        user_id = user_data.get("id")
        if not user_id:
            raise ValueError("User ID required for update")

        payload = {"profile": user_data.get("profile", {})}
        async with self.session.post(
            f"{self.base_url}/users/{user_id}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _deactivate_user(self, user_data: Dict[str, Any]):
        """Deactivate a user."""
        user_id = user_data.get("id")
        async with self.session.post(
            f"{self.base_url}/users/{user_id}/lifecycle/deactivate",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def _reactivate_user(self, user_data: Dict[str, Any]):
        """Reactivate a user."""
        user_id = user_data.get("id")
        async with self.session.post(
            f"{self.base_url}/users/{user_id}/lifecycle/reactivate",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def _create_group(self, group_data: Dict[str, Any]):
        """Create a new group."""
        payload = {
            "profile": group_data.get("profile", {}),
            "type": group_data.get("type", "OKTA_GROUP"),
        }
        async with self.session.post(
            f"{self.base_url}/groups",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_group(self, group_data: Dict[str, Any]):
        """Update a group."""
        group_id = group_data.get("id")
        payload = {"profile": group_data.get("profile", {})}
        async with self.session.post(
            f"{self.base_url}/groups/{group_id}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _add_user_to_group(self, data: Dict[str, Any]):
        """Add user to group."""
        group_id = data.get("group_id")
        user_id = data.get("user_id")
        async with self.session.put(
            f"{self.base_url}/groups/{group_id}/users/{user_id}",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def _remove_user_from_group(self, data: Dict[str, Any]):
        """Remove user from group."""
        group_id = data.get("group_id")
        user_id = data.get("user_id")
        async with self.session.delete(
            f"{self.base_url}/groups/{group_id}/users/{user_id}",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def _assign_user_to_app(self, data: Dict[str, Any]):
        """Assign user to application."""
        app_id = data.get("application_id")
        user_id = data.get("user_id")
        async with self.session.post(
            f"{self.base_url}/apps/{app_id}/users/{user_id}",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def test_connection(self) -> bool:
        """Test Okta connection."""
        try:
            async with self.session.get(
                f"{self.base_url}/users/me",
                headers=await self._get_headers(),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Okta connection test failed: {e}")
            return False

    def _parse_next_link(self, link_header: str) -> Optional[str]:
        """Parse Link header for next page URL."""
        if not link_header:
            return None
        for link in link_header.split(","):
            if 'rel="next"' in link:
                return link.split(";")[0].strip("<> ")
        return None


# Register with global registry
from app.connectors.base import connector_registry
connector_registry.register(OktaConnector, OktaConnector.CONFIG)