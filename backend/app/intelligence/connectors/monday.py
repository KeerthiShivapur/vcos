"""Gate 24 — Monday.com Connector.

Implements Monday.com integration for boards, items, users, and columns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, AsyncIterator

from app.intelligence.connectors.base import BaseConnector, connector_registry
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.connectors.monday")


class MondayConnector(BaseConnector):
    """Monday.com connector implementation."""

    @property
    def provider(self) -> str:
        return "monday"

    @property
    def kind(self) -> str:
        return "productivity"

    async def authenticate(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials

        if not credentials:
            return False, "No credentials configured"

        api_token = credentials.get("api_token")
        if not api_token:
            return False, "No API token configured"

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.monday.com/v2",
                    headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                    json={"query": "{ me { id name email } }"},
                )

            if response.status_code == 200:
                data = response.json()
                if "data" in data and "me" in data["data"]:
                    return True, None
                return False, data.get("errors", [{}])[0].get("message", "Authentication failed")
        except Exception as e:
            return False, f"Authentication test failed: {str(e)}"

        return False, "Authentication failed"

    async def test_connection(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        return await self.authenticate(instance)

    async def full_sync(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        ok, error = await self.authenticate(instance)
        if not ok:
            raise RuntimeError(f"Authentication failed: {error}")

        credentials = instance.credentials
        api_token = credentials.get("api_token")

        # Sync users
        if "read_users" in instance.connector.inbound_capabilities:
            async for user in self._sync_users(api_token):
                yield user

        # Sync boards
        if "read_boards" in instance.connector.inbound_capabilities:
            async for board in self._sync_boards(api_token, since, until):
                yield board

        # Sync items (pulses)
        if "read_items" in instance.connector.inbound_capabilities:
            async for item in self._sync_items(api_token, since, until):
                yield item

        # Sync groups
        if "read_groups" in instance.connector.inbound_capabilities:
            async for group in self._sync_groups(api_token):
                yield group

    async def _sync_users(self, api_token: str) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = """
        query {
            users(limit: 100) {
                id
                name
                email
                photo_original
                title
                phone
                mobile_phone
                is_admin
                is_guest
                is_pending
                created_at
            }
        }
        """

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.monday.com/v2",
                headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                json={"query": query},
            )

            if response.status_code != 200:
                return

            data = response.json()
            for user in data.get("data", {}).get("users", []):
                yield {
                    "entity_type": "person",
                    "external_id": str(user["id"]),
                    "operation": "upsert",
                    "data": {
                        "external_id": str(user["id"]),
                        "external_email": user.get("email"),
                        "external_display_name": user.get("name"),
                        "external_avatar_url": user.get("photo_original"),
                        "external_metadata": {
                            "title": user.get("title"),
                            "phone": user.get("phone"),
                            "mobile_phone": user.get("mobile_phone"),
                            "is_admin": user.get("is_admin"),
                            "is_guest": user.get("is_guest"),
                            "is_pending": user.get("is_pending"),
                            "created_at": user.get("created_at"),
                        },
                    },
                }

    async def _sync_boards(self, api_token: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = """
        query ($limit: Int!, $cursor: String) {
            boards(limit: $limit, cursor: $cursor) {
                data {
                    id
                    name
                    description
                    state
                    board_kind
                    workspace_id
                    owner { id }
                    columns { id title type }
                    groups { id title }
                    created_at
                    updated_at
                }
                cursor
            }
        }
        """

        variables = {"limit": 100}
        cursor = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                if cursor:
                    variables["cursor"] = cursor

                response = await httpx.AsyncClient(timeout=30.0).post(
                    "https://api.monday.com/v2",
                    headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                    json={"query": query, "variables": variables},
                )

                if response.status_code != 200:
                    break

                data = response.json()
                boards_data = data.get("data", {}).get("boards", {})
                for board in boards_data.get("data", []):
                    if since and board.get("updated_at"):
                        modified = datetime.fromisoformat(board["updated_at"].replace("Z", "+00:00"))
                        if modified < since:
                            continue
                    if until and board.get("updated_at"):
                        modified = datetime.fromisoformat(board["updated_at"].replace("Z", "+00:00"))
                        if modified > until:
                            continue

                    yield {
                        "entity_type": "project",
                        "external_id": str(board["id"]),
                        "operation": "upsert",
                        "data": {
                            "external_id": str(board["id"]),
                            "external_display_name": board.get("name"),
                            "external_metadata": {
                                "description": board.get("description"),
                                "state": board.get("state"),
                                "board_kind": board.get("board_kind"),
                                "workspace_id": board.get("workspace_id"),
                                "owner_id": board.get("owner", {}).get("id") if board.get("owner") else None,
                                "columns": board.get("columns"),
                                "groups": board.get("groups"),
                                "created_at": board.get("created_at"),
                                "updated_at": board.get("updated_at"),
                            },
                        },
                    }

                cursor = boards_data.get("cursor")
                if not cursor:
                    break

    async def _sync_items(self, api_token: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = """
        query ($boardIds: [ID!]!, $limit: Int!, $cursor: String) {
            items_by_multiple_columns_values(board_ids: $boardIds, column_values: [], limit: $limit, cursor: $cursor) {
                data {
                    id
                    name
                    column_values { id text value type }
                    column_values { id text value type }
                    group { id title }
                    creator_id
                    created_at
                    updated_at
                    state
                }
                cursor
            }
        }
        """

        variables = {"limit": 100}
        cursor = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                if cursor:
                    variables["cursor"] = cursor

                response = await client.post(
                    "https://api.monday.com/v2",
                    headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                    json={"query": query, "variables": variables},
                )

                if response.status_code != 200:
                    break

                data = response.json()
                items_data = data.get("data", {}).get("items_by_multiple_columns_values", {})
                for item in items_data.get("data", []):
                    if since and item.get("updated_at"):
                        modified = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                        if modified < since:
                            continue
                    if until and item.get("updated_at"):
                        modified = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                        if modified > until:
                            continue

                    column_values = {}
                    for col in item.get("column_values", []):
                        column_values[col["id"]] = col["text"]

                    yield {
                        "entity_type": "task",
                        "external_id": str(item["id"]),
                        "operation": "upsert",
                        "data": {
                            "external_id": str(item["id"]),
                            "external_display_name": item.get("name"),
                            "external_metadata": {
                                "column_values": column_values,
                                "group_id": item.get("group", {}).get("id") if item.get("group") else None,
                                "creator_id": item.get("creator_id"),
                                "state": item.get("state"),
                                "created_at": item.get("created_at"),
                                "updated_at": item.get("updated_at"),
                            },
                        },
                    }

                cursor = items_data.get("cursor")
                if not cursor:
                    break

    async def _sync_groups(self, api_token: str) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = """
        query {
            groups {
                id
                title
                color
                deleted
                items_count
            }
        }
        """

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.monday.com/v2",
                headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                json={"query": query},
            )

            if response.status_code != 200:
                return

            data = response.json()
            for group in data.get("data", {}).get("groups", []):
                yield {
                    "entity_type": "group",
                    "external_id": str(group["id"]),
                    "operation": "upsert",
                    "data": {
                        "external_id": str(group["id"]),
                        "external_display_name": group.get("title"),
                        "external_metadata": {
                            "color": group.get("color"),
                            "deleted": group.get("deleted"),
                            "items_count": group.get("items_count"),
                        },
                    },
                }

    async def incremental_sync(
        self,
        instance: ConnectorInstance,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        async for entity in self.full_sync(instance, since=since):
            yield entity

    async def poll_events(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
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
        ok, error = await self.authenticate(instance)
        if not ok:
            return {"success": False, "error": error}

        credentials = instance.credentials
        api_token = credentials.get("api_token")

        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}

            if operation_type == "create_item" and target_entity_type == "item":
                board_id = payload.get("board_id")
                group_id = payload.get("group_id")
                item_name = payload.get("item_name")
                column_values = payload.get("column_values", {})

                query = """
                mutation ($boardId: ID!, $groupId: ID, $itemName: String!, $columnValues: JSON!) {
                    create_item(board_id: $boardId, group_id: $groupId, item_name: $itemName, column_values: $columnValues) {
                        id
                    }
                }
                """

                variables = {
                    "boardId": int(board_id),
                    "groupId": int(group_id) if group_id else None,
                    "itemName": item_name,
                    "columnValues": column_values,
                }

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://api.monday.com/v2",
                        headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                        json={"query": query, "variables": variables},
                    )

                    if response.status_code == 200:
                        data = response.json()
                        if "data" in data and "create_item" in data["data"]:
                            return {
                                "success": True,
                                "external_operation_id": str(data["data"]["create_item"]["id"]),
                                "data": data,
                            }

                return {"success": False, "error": response.text}

            elif operation_type == "update_item" and target_entity_type == "item":
                item_id = target_external_id
                query = """
                mutation ($itemId: ID!, $columnValues: JSON!) {
                    change_multiple_column_values(item_id: $itemId, column_values: $columnValues) {
                        id
                    }
                }
                """

                variables = {
                    "itemId": int(item_id),
                    "columnValues": payload.get("column_values", {}),
                }

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://api.monday.com/v2",
                        headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                        json={"query": query, "variables": variables},
                    )

                    if response.status_code == 200:
                        return {"success": True, "data": response.json()}

                return {"success": False, "error": response.text}

        return {"success": False, "error": f"Operation {operation_type} not implemented"}

    async def get_webhook_events(
        self,
        instance: ConnectorInstance,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        events = []

        if payload.get("challenge"):
            return []

        event_type = payload.get("type", "")
        event_data = payload.get("event", {})

        events.append({
            "external_event_id": payload.get("eventId", ""),
            "event_type": f"monday.{event_type}",
            "source_id": event_data.get("boardId") or event_data.get("pulseId") or event_data.get("userId"),
            "source_type": "board" if "board" in event_type else "item" if "pulse" in event_type else "user",
            "payload": event_data,
            "external_timestamp": datetime.now(timezone.utc),
        })

        return events

    async def refresh_credentials(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str], Optional[dict]]:
        return True, None, instance.credentials

    async def get_rate_limit_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        return {"remaining": "unknown", "reset_at": None}

    async def resolve_identity(
        self,
        instance: ConnectorInstance,
        external_id: str,
    ) -> Optional[dict[str, Any]]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return None

        credentials = instance.credentials
        api_token = credentials.get("api_token")

        import httpx
        query = """
        query ($userId: ID!) {
            users(ids: [$userId]) {
                id
                name
                email
                photo_original
                title
            }
        }
        """

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.monday.com/v2",
                headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                json={"query": query, "variables": {"userId": int(external_id)}},
            )

        if response.status_code == 200:
            data = response.json()
            users = data.get("data", {}).get("users", [])
            if users:
                user = users[0]
                return {
                    "external_id": str(user["id"]),
                    "external_email": user.get("email"),
                    "external_display_name": user.get("name"),
                    "external_avatar_url": user.get("photo_original"),
                    "external_metadata": {
                        "title": user.get("title"),
                    },
                }

        return None

    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return {
            "inbound_capabilities": ["read_users", "read_boards", "read_items", "read_groups", "read_columns"],
            "outbound_capabilities": ["create_item", "update_item", "create_board", "update_board", "create_update", "add_column"],
            "supported_entities": ["user", "board", "item", "group", "column", "update", "team"],
            "supported_events": ["item.created", "item.updated", "item.deleted", "column.value.changed", "item.moved", "board.created", "column.created"],
            "sync_modes": ["full", "incremental", "webhook"],
            "auth_types": ["api_token"],
            "oauth_scopes": [],
            "required_config_fields": ["api_token"],
            "optional_config_fields": [],
            "rate_limits": {
                "api": {"requests_per_minute": 60, "burst": 10},
                "complexity": {"points_per_minute": 5000000},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("api_token"):
            return False, "No api_token configured"
        return True, None

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return {
                "status": "unhealthy",
                "last_check": datetime.now(timezone.utc).isoformat(),
                "details": {"error": error},
                "latency_ms": 0,
            }
        return {
            "status": "healthy",
            "last_check": datetime.now(timezone.utc).isoformat(),
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
        import hmac
        import hashlib
        credentials = instance.credentials
        webhook_secret = credentials.get("signing_secret")
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

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        return await self.validate_webhook_signature(instance, payload, signature, timestamp)


# Register the connector
connector_registry.register(MondayConnector())