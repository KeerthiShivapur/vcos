"""
Google Workspace Connector for VCOS.

Provides integration with Google Workspace Admin SDK for user/group management,
organizational units, and Drive audit.
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


class GoogleWorkspaceConnector(BaseConnector):
    """Google Workspace Admin SDK Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="google_workspace",
        display_name="Google Workspace",
        description="Google's productivity and collaboration suite",
        category="identity",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "admin_email": {"type": "string", "description": "Admin email for impersonation"},
                "scopes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["client_id", "client_secret", "redirect_uri"],
        },
        required_scopes=[
            "https://www.googleapis.com/auth/admin.directory.user.readonly",
            "https://www.googleapis.com/auth/admin.directory.group.readonly",
            "https://www.googleapis.com/auth/admin.directory.orgunit.readonly",
            "https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly",
            "https://www.googleapis.com/auth/admin.reports.audit.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
        supported_operations=[
            "list_users",
            "get_user",
            "create_user",
            "update_user",
            "delete_user",
            "suspend_user",
            "unsuspend_user",
            "list_groups",
            "get_group",
            "create_group",
            "update_group",
            "delete_group",
            "list_group_members",
            "add_group_member",
            "remove_group_member",
            "list_org_units",
            "get_org_unit",
            "create_org_unit",
            "update_org_unit",
            "delete_org_unit",
            "list_roles",
            "list_role_assignments",
            "list_drive_activity",
            "list_login_activity",
        ],
        webhook_events=[
            "user.created",
            "user.updated",
            "user.deleted",
            "user.suspended",
            "user.unsuspended",
            "group.created",
            "group.updated",
            "group.deleted",
            "group.member.added",
            "group.member.removed",
            "org_unit.created",
            "org_unit.updated",
            "org_unit.deleted",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=20,
            requests_per_minute=1200,
            burst=50,
        ),
    )

    ADMIN_BASE_URL = "https://www.googleapis.com/admin/directory/v1"
    REPORTS_BASE_URL = "https://www.googleapis.com/admin/reports/v1"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

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
        self.admin_email = connection_config.get("admin_email")
        self.scopes = connection_config.get("scopes", [
            "https://www.googleapis.com/auth/admin.directory.user",
            "https://www.googleapis.com/auth/admin.directory.group",
            "https://www.googleapis.com/auth/admin.directory.orgunit",
        ])
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with Google using service account or OAuth2."""
        from app.connectors.base import TokenManager

        # Check for service account
        if self.connection_config.get("service_account_key"):
            # Service account auth would be implemented here
            pass

        # OAuth2 flow
        self._token_manager = TokenManager(
            self.client_id,
            self.client_secret,
            self.TOKEN_URL,
        )
        await self._token_manager.get_access_token()
        self._authenticated = True
        logger.info("Google Workspace authenticated")
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

    async def pull_data(
        self,
        operation: str,
        cursor: Optional[SyncCursor] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not self._authenticated:
            await self.authenticate()

        handlers = {
            "list_users": self._list_users,
            "list_groups": self._list_groups,
            "list_org_units": self._list_org_units,
            "list_roles": self._list_roles,
            "list_role_assignments": self._list_role_assignments,
            "list_drive_activity": self._list_drive_activity,
            "list_login_activity": self._list_login_activity,
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
        url = f"{self.ADMIN_BASE_URL}/users"
        params = {
            "customer": "my_customer",
            "maxResults": 500,
            "projection": "full",
            "showDeleted": "false",
            "orderBy": "email",
        }

        if cursor and cursor.cursor:
            params["pageToken"] = cursor.cursor

        while True:
            async with self.session.get(
                url,
                headers=await self._get_headers(),
                params=params,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for user in data.get("users", []):
                    yield {
                        "type": "user",
                        "id": user["id"],
                        "external_id": user.get("externalIds", [{}])[0].get("value") if user.get("externalIds") else None,
                        "data": user,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                if "nextPageToken" in data:
                    params["pageToken"] = data["nextPageToken"]
                else:
                    break

    async def _list_groups(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = f"{self.ADMIN_BASE_URL}/groups"
        params = {
            "customer": "my_customer",
            "maxResults": 500,
        }

        if cursor and cursor.cursor:
            params["pageToken"] = cursor.cursor

        while True:
            async with self.session.get(
                url,
                headers=await self._get_headers(),
                params=params,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for group in data.get("groups", []):
                    yield {
                        "type": "group",
                        "id": group["id"],
                        "data": group,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                if "nextPageToken" in data:
                    params["pageToken"] = data["nextPageToken"]
                else:
                    break

    async def _list_org_units(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = f"{self.ADMIN_BASE_URL}/customer/my_customer/orgunits"
        params = {"type": "all"}

        async with self.session.get(
            url,
            headers=await self._get_headers(),
            params=params,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

            for ou in data.get("organizationUnits", []):
                yield {
                    "type": "org_unit",
                    "id": ou["orgUnitId"],
                    "data": ou,
                    "synced_at": datetime.utcnow().isoformat(),
                }

    async def _list_roles(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = f"{self.ADMIN_BASE_URL}/customer/my_customer/roles"
        params = {"maxResults": 100}

        async with self.session.get(
            url,
            headers=await self._get_headers(),
            params=params,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

            for role in data.get("roleAssignments", []):
                yield {
                    "type": "role",
                    "id": role["roleAssignmentId"],
                    "data": role,
                    "synced_at": datetime.utcnow().isoformat(),
                }

    async def _list_role_assignments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = f"{self.ADMIN_BASE_URL}/customer/my_customer/roleassignments"
        params = {"maxResults": 100}

        if cursor and cursor.cursor:
            params["pageToken"] = cursor.cursor

        while True:
            async with self.session.get(
                url,
                headers=await self._get_headers(),
                params=params,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for assignment in data.get("items", []):
                    yield {
                        "type": "role_assignment",
                        "id": assignment["roleAssignmentId"],
                        "data": assignment,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                if "nextPageToken" in data:
                    params["pageToken"] = data["nextPageToken"]
                else:
                    break

    async def _list_drive_activity(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = f"{self.REPORTS_BASE_URL}/activity/users/all/applications/drive"
        params = {
            "maxResults": 1000,
            "eventName": "create,edit,delete,move,permission_change",
        }

        if cursor and cursor.cursor:
            params["startTime"] = cursor.cursor
        elif filters and filters.get("since"):
            params["startTime"] = filters["since"]

        async with self.session.get(
            url,
            headers=await self._get_headers(),
            params=params,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

            for item in data.get("items", []):
                yield {
                    "type": "drive_activity",
                    "id": item["id"]["time"] + item["id"]["uniqueQualifier"],
                    "data": item,
                    "synced_at": datetime.utcnow().isoformat(),
                }

    async def _list_login_activity(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = f"{self.REPORTS_BASE_URL}/activity/users/all/applications/login"
        params = {"maxResults": 1000}

        if cursor and cursor.cursor:
            params["startTime"] = cursor.cursor
        elif filters and filters.get("since"):
            params["startTime"] = filters["since"]

        async with self.session.get(
            url,
            headers=await self._get_headers(),
            params=params,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

            for item in data.get("items", []):
                yield {
                    "type": "login_activity",
                    "id": item["id"]["time"] + item["id"]["uniqueQualifier"],
                    "data": item,
                    "synced_at": datetime.utcnow().isoformat(),
                }

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_user": self._create_user,
            "update_user": self._update_user,
            "delete_user": self._delete_user,
            "suspend_user": self._suspend_user,
            "unsuspend_user": self._unsuspend_user,
            "create_group": self._create_group,
            "update_group": self._update_group,
            "delete_group": self._delete_group,
            "add_group_member": self._add_group_member,
            "remove_group_member": self._remove_group_member,
            "create_org_unit": self._create_org_unit,
            "update_org_unit": self._update_org_unit,
            "delete_org_unit": self._delete_org_unit,
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
                result.records_updated += 1 if "update" in operation or "suspend" in operation else 0
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_user(self, user_data: Dict[str, Any]):
        payload = {
            "primaryEmail": user_data.get("primaryEmail"),
            "name": user_data.get("name", {}),
            "password": user_data.get("password", "TempPass123!"),
            "orgUnitPath": user_data.get("orgUnitPath", "/"),
            "recoveryEmail": user_data.get("recoveryEmail"),
            "recoveryPhone": user_data.get("recoveryPhone"),
        }
        async with self.session.post(
            f"{self.ADMIN_BASE_URL}/users",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_user(self, user_data: Dict[str, Any]):
        user_key = user_data.get("id") or user_data.get("primaryEmail")
        payload = {k: v for k, v in user_data.items() if k not in ["id", "primaryEmail", "kind", "etag"]}
        async with self.session.put(
            f"{self.ADMIN_BASE_URL}/users/{user_key}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _delete_user(self, user_data: Dict[str, Any]):
        user_key = user_data.get("id") or user_data.get("primaryEmail")
        async with self.session.delete(
            f"{self.ADMIN_BASE_URL}/users/{user_key}",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def _suspend_user(self, user_data: Dict[str, Any]):
        user_key = user_data.get("id") or user_data.get("primaryEmail")
        payload = {"suspended": True}
        async with self.session.put(
            f"{self.ADMIN_BASE_URL}/users/{user_key}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _unsuspend_user(self, user_data: Dict[str, Any]):
        user_key = user_data.get("id") or user_data.get("primaryEmail")
        payload = {"suspended": False}
        async with self.session.put(
            f"{self.ADMIN_BASE_URL}/users/{user_key}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _create_group(self, group_data: Dict[str, Any]):
        payload = {
            "email": group_data.get("email"),
            "name": group_data.get("name"),
            "description": group_data.get("description", ""),
        }
        async with self.session.post(
            f"{self.ADMIN_BASE_URL}/groups",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_group(self, group_data: Dict[str, Any]):
        group_key = group_data.get("id") or group_data.get("email")
        payload = {k: v for k, v in group_data.items() if k not in ["id", "email", "kind", "etag"]}
        async with self.session.put(
            f"{self.ADMIN_BASE_URL}/groups/{group_key}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _delete_group(self, group_data: Dict[str, Any]):
        group_key = group_data.get("id") or group_data.get("email")
        async with self.session.delete(
            f"{self.ADMIN_BASE_URL}/groups/{group_key}",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def _add_group_member(self, data: Dict[str, Any]):
        group_key = data.get("group_id") or data.get("group_email")
        payload = {
            "email": data.get("member_email"),
            "role": data.get("role", "MEMBER"),
        }
        async with self.session.post(
            f"{self.ADMIN_BASE_URL}/groups/{group_key}/members",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _remove_group_member(self, data: Dict[str, Any]):
        group_key = data.get("group_id") or data.get("group_email")
        member_key = data.get("member_id") or data.get("member_email")
        async with self.session.delete(
            f"{self.ADMIN_BASE_URL}/groups/{group_key}/members/{member_key}",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def _create_org_unit(self, ou_data: Dict[str, Any]):
        payload = {
            "name": ou_data.get("name"),
            "parentOrgUnitPath": ou_data.get("parentOrgUnitPath", "/"),
            "description": ou_data.get("description", ""),
        }
        async with self.session.post(
            f"{self.ADMIN_BASE_URL}/customer/my_customer/orgunits",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_org_unit(self, ou_data: Dict[str, Any]):
        ou_id = ou_data.get("orgUnitId")
        payload = {k: v for k, v in ou_data.items() if k != "orgUnitId"}
        async with self.session.put(
            f"{self.ADMIN_BASE_URL}/customer/my_customer/orgunits/{ou_id}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _delete_org_unit(self, ou_data: Dict[str, Any]):
        ou_id = ou_data.get("orgUnitId")
        async with self.session.delete(
            f"{self.ADMIN_BASE_URL}/customer/my_customer/orgunits/{ou_id}",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def test_connection(self) -> bool:
        try:
            async with self.session.get(
                f"{self.ADMIN_BASE_URL}/users?customer=my_customer&maxResults=1",
                headers=await self._get_headers(),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Google Workspace connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(GoogleWorkspaceConnector, GoogleWorkspaceConnector.CONFIG)