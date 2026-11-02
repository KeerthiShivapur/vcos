"""
Azure Active Directory (Entra ID) Connector for VCOS.

Provides integration with Microsoft Entra ID for user/group management,
conditional access, and identity governance.
"""

import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse urljoin

from app.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    AuthType,
    RateLimitConfig,
    SyncCursor,
    SyncResult,
)

logger = logging.getLogger(__name__)


class AzureADConnector(BaseConnector):
    """Microsoft Entra ID (Azure AD) Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="azure_ad",
        display_name="Microsoft Entra ID",
        description="Microsoft's cloud-based identity and access management service",
        category="identity",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Azure AD tenant ID"},
                "client_id": {"type": "string", "description": "Application (client) ID"},
                "client_secret": {"type": "string", "description": "Client secret"},
                "redirect_uri": {"type": "string"},
            },
            "required": ["tenant_id", "client_id", "client_secret", "redirect_uri"],
        },
        required_scopes=[
            "https://graph.microsoft.com/User.Read.All",
            "https://graph.microsoft.com/Group.Read.All",
            "https://graph.microsoft.com/Application.Read.All",
            "https://graph.microsoft.com/Directory.Read.All",
        ],
        supported_operations=[
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
            "add_group_member",
            "remove_group_member",
            "list_applications",
            "get_application",
            "list_service_principals",
            "list_conditional_access_policies",
            "list_named_locations",
            "list_identity_providers",
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
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=600,
            burst=20,
        ),
    )

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
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
        self.client_id = connection_config.get("client_id")
        self.client_secret = connection_config.get("client_secret")
        self.token_url = self.TOKEN_URL.format(tenant_id=self.tenant_id)
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with Azure AD using client credentials flow."""
        from app.connectors.base import TokenManager
        self._token_manager = TokenManager(
            self.client_id,
            self.client_secret,
            self.token_url,
        )
        # Add default scope for Microsoft Graph
        self._token_manager.token_url = self.token_url
        await self._token_manager.get_access_token()
        self._authenticated = True
        logger.info(f"Azure AD authenticated for tenant {self.tenant_id}")
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
        """Pull data from Microsoft Graph."""
        if not self._authenticated:
            await self.authenticate()

        handlers = {
            "list_users": self._list_users,
            "list_groups": self._list_groups,
            "list_applications": self._list_applications,
            "list_service_principals": self._list_service_principals,
            "list_conditional_access_policies": self._list_ca_policies,
            "list_named_locations": self._list_named_locations,
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
        """List users with delta query support for incremental sync."""
        url = f"{self.GRAPH_BASE_URL}/users"
        params = {
            "$top": 999,
            "$select": "id,displayName,userPrincipalName,mail,givenName,surname,jobTitle,department,officeLocation,accountEnabled,createdDateTime,lastPasswordChangeDateTime,onPremisesSyncEnabled,onPremisesLastSyncDateTime,userType,employeeId,employeeHireDate",
        }

        if cursor and cursor.cursor:
            url = cursor.cursor
        elif filters and filters.get("since"):
            params["$filter"] = f"lastModifiedDateTime ge {filters['since']}"

        while url:
            async with self.session.get(
                url,
                headers=await self._get_headers(),
                params=params if isinstance(url, str) and url == f"{self.GRAPH_BASE_URL}/users" else None,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for user in data.get("value", []):
                    yield {
                        "type": "user",
                        "id": user["id"],
                        "external_id": user.get("onPremisesImmutableId") or user.get("employeeId"),
                        "data": user,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                # Handle delta query nextLink or regular pagination
                url = data.get("@odata.nextLink") or data.get("@odata.deltaLink")

    async def _list_groups(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List groups with delta query."""
        url = f"{self.GRAPH_BASE_URL}/groups"
        params = {
            "$top": 999,
            "$select": "id,displayName,description,mail,mailEnabled,securityEnabled,groupTypes,createdDateTime,expirationDateTime,onPremisesSyncEnabled,onPremisesLastSyncDateTime",
        }

        if cursor and cursor.cursor:
            url = cursor.cursor

        while url:
            async with self.session.get(
                url,
                headers=await self._get_headers(),
                params=params if isinstance(url, str) and url == f"{self.GRAPH_BASE_URL}/groups" else None,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for group in data.get("value", []):
                    yield {
                        "type": "group",
                        "id": group["id"],
                        "data": group,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                url = data.get("@odata.nextLink") or data.get("@odata.deltaLink")

    async def _list_applications(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List application registrations."""
        url = f"{self.GRAPH_BASE_URL}/applications"
        params = {
            "$top": 999,
            "$select": "id,displayName,appId,identifierUris,signInAudience,web,spa,publicClient,requiredResourceAccess,createdDateTime",
        }

        if cursor and cursor.cursor:
            url = cursor.cursor

        while url:
            async with self.session.get(
                url,
                headers=await self._get_headers(),
                params=params if isinstance(url, str) and url == f"{self.GRAPH_BASE_URL}/applications" else None,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for app in data.get("value", []):
                    yield {
                        "type": "application",
                        "id": app["id"],
                        "data": app,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                url = data.get("@odata.nextLink") or data.get("@odata.deltaLink")

    async def _list_service_principals(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List service principals (enterprise applications)."""
        url = f"{self.GRAPH_BASE_URL}/servicePrincipals"
        params = {
            "$top": 999,
            "$select": "id,appId,displayName,servicePrincipalType,tags,appOwnerOrganizationId,createdDateTime",
        }

        if cursor and cursor.cursor:
            url = cursor.cursor

        while url:
            async with self.session.get(
                url,
                headers=await self._get_headers(),
                params=params if isinstance(url, str) and url == f"{self.GRAPH_BASE_URL}/servicePrincipals" else None,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for sp in data.get("value", []):
                    yield {
                        "type": "service_principal",
                        "id": sp["id"],
                        "data": sp,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                url = data.get("@odata.nextLink") or data.get("@odata.deltaLink")

    async def _list_ca_policies(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List conditional access policies."""
        url = f"{self.GRAPH_BASE_URL}/identity/conditionalAccess/policies"
        params = {"$top": 100}

        if cursor and cursor.cursor:
            url = cursor.cursor

        while url:
            async with self.session.get(
                url,
                headers=await self._get_headers(),
                params=params if isinstance(url, str) and url == f"{self.GRAPH_BASE_URL}/identity/conditionalAccess/policies" else None,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for policy in data.get("value", []):
                    yield {
                        "type": "conditional_access_policy",
                        "id": policy["id"],
                        "data": policy,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                url = data.get("@odata.nextLink")

    async def _list_named_locations(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List named locations."""
        url = f"{self.GRAPH_BASE_URL}/identity/conditionalAccess/namedLocations"
        params = {"$top": 100}

        if cursor and cursor.cursor:
            url = cursor.cursor

        while url:
            async with self.session.get(
                url,
                headers=await self._get_headers(),
                params=params if isinstance(url, str) and url == f"{self.GRAPH_BASE_URL}/identity/conditionalAccess/namedLocations" else None,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for location in data.get("value", []):
                    yield {
                        "type": "named_location",
                        "id": location["id"],
                        "data": location,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                url = data.get("@odata.nextLink")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "ConsistencyLevel": "eventual",
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
        """Push data to Azure AD."""
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_user": self._create_user,
            "update_user": self._update_user,
            "delete_user": self._delete_user,
            "create_group": self._create_group,
            "update_group": self._update_group,
            "delete_group": self._delete_group,
            "add_group_member": self._add_group_member,
            "remove_group_member": self._remove_group_member,
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

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_user(self, user_data: Dict[str, Any]):
        payload = {
            "accountEnabled": user_data.get("accountEnabled", True),
            "displayName": user_data.get("displayName"),
            "userPrincipalName": user_data.get("userPrincipalName"),
            "mailNickname": user_data.get("mailNickname"),
            "passwordProfile": user_data.get("passwordProfile", {
                "forceChangePasswordNextSignIn": True,
                "password": "TempPass123!",
            }),
            "givenName": user_data.get("givenName"),
            "surname": user_data.get("surname"),
            "jobTitle": user_data.get("jobTitle"),
            "department": user_data.get("department"),
            "officeLocation": user_data.get("officeLocation"),
        }
        async with self.session.post(
            f"{self.GRAPH_BASE_URL}/users",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_user(self, user_data: Dict[str, Any]):
        user_id = user_data.get("id")
        if not user_id:
            raise ValueError("User ID required")
        payload = {k: v for k, v in user_data.items() if k != "id"}
        async with self.session.patch(
            f"{self.GRAPH_BASE_URL}/users/{user_id}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _delete_user(self, user_data: Dict[str, Any]):
        user_id = user_data.get("id")
        async with self.session.delete(
            f"{self.GRAPH_BASE_URL}/users/{user_id}",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def _create_group(self, group_data: Dict[str, Any]):
        payload = {
            "displayName": group_data.get("displayName"),
            "description": group_data.get("description", ""),
            "mailEnabled": group_data.get("mailEnabled", False),
            "mailNickname": group_data.get("mailNickname"),
            "securityEnabled": group_data.get("securityEnabled", True),
            "groupTypes": group_data.get("groupTypes", ["Unified"]),
        }
        async with self.session.post(
            f"{self.GRAPH_BASE_URL}/groups",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_group(self, group_data: Dict[str, Any]):
        group_id = group_data.get("id")
        payload = {k: v for k, v in group_data.items() if k != "id"}
        async with self.session.patch(
            f"{self.GRAPH_BASE_URL}/groups/{group_id}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _delete_group(self, group_data: Dict[str, Any]):
        group_id = group_data.get("id")
        async with self.session.delete(
            f"{self.GRAPH_BASE_URL}/groups/{group_id}",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def _add_group_member(self, data: Dict[str, Any]):
        group_id = data.get("group_id")
        user_id = data.get("user_id")
        url = f"{self.GRAPH_BASE_URL}/groups/{group_id}/members/$ref"
        payload = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_id}"}
        async with self.session.post(
            url,
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _remove_group_member(self, data: Dict[str, Any]):
        group_id = data.get("group_id")
        user_id = data.get("user_id")
        async with self.session.delete(
            f"{self.GRAPH_BASE_URL}/groups/{group_id}/members/{user_id}/$ref",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def test_connection(self) -> bool:
        try:
            async with self.session.get(
                f"{self.GRAPH_BASE_URL}/organization",
                headers=await self._get_headers(),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Azure AD connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(AzureADConnector, AzureADConnector.CONFIG)