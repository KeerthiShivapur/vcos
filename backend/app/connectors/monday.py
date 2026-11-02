"""
Monday.com Connector for VCOS.

Provides integration with Monday.com for work management, boards, items, and automations.
"""

import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

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


class MondayConnector(BaseConnector):
    """Monday.com Connector Implementation using GraphQL API."""

    CONFIG = ConnectorConfig(
        name="monday",
        display_name="Monday.com",
        description="Work OS for project management and team collaboration",
        category="project_management",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "Monday.com API v2 Token"},
                "api_version": {"type": "string", "default": "2023-10", "description": "API Version"},
            },
            "required": ["api_key"],
        },
        required_scopes=[],
        supported_operations=[
            "list_boards",
            "get_board",
            "create_board",
            "update_board",
            "delete_board",
            "list_board_views",
            "list_groups",
            "get_group",
            "create_group",
            "update_group",
            "delete_group",
            "list_items",
            "get_item",
            "create_item",
            "update_item",
            "delete_item",
            "move_item_to_group",
            "list_subitems",
            "create_subitem",
            "update_subitem",
            "list_columns",
            "get_column",
            "create_column",
            "update_column",
            "delete_column",
            "list_column_values",
            "change_column_value",
            "change_multiple_column_values",
            "list_updates",
            "create_update",
            "update_update",
            "delete_update",
            "list_replies",
            "create_reply",
            "list_users",
            "get_user",
            "list_teams",
            "get_team",
            "create_team",
            "list_workspaces",
            "get_workspace",
            "list_webhooks",
            "create_webhook",
            "delete_webhook",
            "list_activity_logs",
            "execute_query",
        ],
        webhook_events=[
            "create_board",
            "delete_board",
            "update_board",
            "create_item",
            "delete_item",
            "update_item",
            "create_update",
            "delete_update",
            "create_column_value",
            "change_column_value",
            "change_multiple_column_values",
            "create_subitem",
            "delete_subitem",
            "update_subitem",
            "create_group",
            "delete_group",
            "update_group",
            "add_user_to_team",
            "remove_user_from_team",
            "create_team",
            "delete_team",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=60,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/mondaydotcom.svg",
        documentation_url="https://developer.monday.com/api-reference",
    )

    BASE_URL = "https://api.monday.com/v2"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.api_key = connection_config.get("api_key")
        self.api_version = connection_config.get("api_version", "2023-10")

    async def authenticate(self) -> bool:
        """Authenticate with Monday.com using API Key."""
        if not self.api_key:
            raise ValueError("Monday.com requires api_key")

        self._authenticated = True
        logger.info("Monday.com authenticated with API key")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "API-Version": self.api_version,
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make Monday.com GraphQL API request."""
        if not self._authenticated:
            await self.authenticate()

        # Monday.com uses GraphQL over POST
        url = self.BASE_URL
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
                response_data = await resp.json()
                if resp.status >= 400:
                    errors = response_data.get("errors", [{"message": "Unknown error"}])
                    raise Exception(f"Monday.com API error: {errors[0].get('message')}")
                if "errors" in response_data:
                    raise Exception(f"Monday.com GraphQL error: {response_data['errors'][0].get('message')}")
                return response_data.get("data", {})

        return await self.retry_policy.execute(_request)

    async def _graphql_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute GraphQL query."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        return await self._make_request("POST", "", json=payload)

    async def pull_data(
        self,
        operation: str,
        cursor: Optional[SyncCursor] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not self._authenticated:
            await self.authenticate()

        handlers = {
            "list_boards": self._list_boards,
            "list_groups": self._list_groups,
            "list_items": self._list_items,
            "list_subitems": self._list_subitems,
            "list_columns": self._list_columns,
            "list_column_values": self._list_column_values,
            "list_updates": self._list_updates,
            "list_replies": self._list_replies,
            "list_users": self._list_users,
            "list_teams": self._list_teams,
            "list_workspaces": self._list_workspaces,
            "list_webhooks": self._list_webhooks,
            "list_activity_logs": self._list_activity_logs,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_boards(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query ($limit: Int!, $page: Int!, $workspace_ids: [ID!]) {
            boards (limit: $limit, page: $page, workspace_ids: $workspace_ids) {
                id
                name
                description
                state
                board_kind
                board_folder_id
                workspace_id
                created_at
                updated_at
                owner { id name email }
                items_count
                groups { id title color }
                columns { id title type settings_str }
            }
        }
        """
        variables = {"limit": 100, "page": 1}
        if filters and filters.get("workspace_ids"):
            variables["workspace_ids"] = filters["workspace_ids"]
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            for board in data.get("boards", []):
                yield {
                    "type": "board",
                    "id": str(board["id"]),
                    "data": board,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("boards", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_groups(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        board_id = filters.get("board_id")
        if not board_id:
            raise ValueError("board_id filter required")

        query = """
        query ($board_id: [ID!]!, $limit: Int!, $page: Int!) {
            boards (ids: $board_id) {
                groups (limit: $limit, page: $page) {
                    id
                    title
                    color
                    position
                    items_count
                }
            }
        }
        """
        variables = {"board_id": [board_id], "limit": 100, "page": 1}
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            boards = data.get("boards", [])
            if not boards:
                break
            for group in boards[0].get("groups", []):
                yield {
                    "type": "group",
                    "id": str(group["id"]),
                    "data": group,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(boards[0].get("groups", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_items(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        board_id = filters.get("board_id")
        group_id = filters.get("group_id")
        if not board_id:
            raise ValueError("board_id filter required")

        query = """
        query ($board_id: [ID!]!, $group_ids: [String!], $limit: Int!, $page: Int!) {
            boards (ids: $board_id) {
                items_page (limit: $limit, page: $page, group_ids: $group_ids) {
                    cursor
                    items {
                        id
                        name
                        state
                        board { id }
                        group { id title }
                        column_values { id text value type }
                        subitems { id name column_values { id text value } }
                        created_at
                        updated_at
                        creator { id name email }
                        assignees { id name email }
                    }
                }
            }
        }
        """
        variables = {"board_id": [board_id], "limit": 100, "page": 1}
        if group_id:
            variables["group_ids"] = [group_id]
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            boards = data.get("boards", [])
            if not boards:
                break
            items_page = boards[0].get("items_page", {})
            for item in items_page.get("items", []):
                yield {
                    "type": "item",
                    "id": str(item["id"]),
                    "data": item,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not items_page.get("cursor") or len(items_page.get("items", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_subitems(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        item_id = filters.get("item_id")
        if not item_id:
            raise ValueError("item_id filter required")

        query = """
        query ($item_id: [ID!]!, $limit: Int!, $page: Int!) {
            items (ids: $item_id) {
                subitems (limit: $limit, page: $page) {
                    id
                    name
                    column_values { id text value type }
                    created_at
                    updated_at
                    creator { id name email }
                }
            }
        }
        """
        variables = {"item_id": [item_id], "limit": 100, "page": 1}
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            items = data.get("items", [])
            if not items:
                break
            for subitem in items[0].get("subitems", []):
                yield {
                    "type": "subitem",
                    "id": str(subitem["id"]),
                    "data": subitem,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(items[0].get("subitems", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_columns(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        board_id = filters.get("board_id")
        if not board_id:
            raise ValueError("board_id filter required")

        query = """
        query ($board_id: [ID!]!) {
            boards (ids: $board_id) {
                columns {
                    id
                    title
                    type
                    settings_str
                    description
                    default_value
                    width
                }
            }
        }
        """
        variables = {"board_id": [board_id]}
        data = await self._graphql_query(query, variables)
        boards = data.get("boards", [])
        if boards:
            for column in boards[0].get("columns", []):
                yield {
                    "type": "column",
                    "id": str(column["id"]),
                    "data": column,
                    "synced_at": datetime.utcnow().isoformat(),
                }

    async def _list_column_values(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        board_id = filters.get("board_id")
        item_ids = filters.get("item_ids", [])
        if not board_id:
            raise ValueError("board_id filter required")

        query = """
        query ($board_id: [ID!]!, $item_ids: [ID!]!, $limit: Int!, $page: Int!) {
            boards (ids: $board_id) {
                items_page (limit: $limit, page: $page, item_ids: $item_ids) {
                    items {
                        id
                        column_values { id text value type }
                    }
                }
            }
        }
        """
        variables = {"board_id": [board_id], "limit": 100, "page": 1}
        if item_ids:
            variables["item_ids"] = item_ids
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            boards = data.get("boards", [])
            if not boards:
                break
            items_page = boards[0].get("items_page", {})
            for item in items_page.get("items", []):
                for col_val in item.get("column_values", []):
                    yield {
                        "type": "column_value",
                        "id": f"{item['id']}_{col_val['id']}",
                        "data": {**col_val, "item_id": item["id"]},
                        "synced_at": datetime.utcnow().isoformat(),
                    }

            if len(items_page.get("items", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_updates(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        item_id = filters.get("item_id")
        if not item_id:
            raise ValueError("item_id filter required")

        query = """
        query ($item_id: [ID!]!, $limit: Int!, $page: Int!) {
            items (ids: $item_id) {
                updates (limit: $limit, page: $page) {
                    id
                    body
                    created_at
                    creator { id name email }
                    replies { id body created_at creator { id name email } }
                }
            }
        }
        """
        variables = {"item_id": [item_id], "limit": 100, "page": 1}
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            items = data.get("items", [])
            if not items:
                break
            for update in items[0].get("updates", []):
                yield {
                    "type": "update",
                    "id": str(update["id"]),
                    "data": update,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(items[0].get("updates", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_replies(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        update_id = filters.get("update_id")
        if not update_id:
            raise ValueError("update_id filter required")

        query = """
        query ($update_id: [ID!]!, $limit: Int!, $page: Int!) {
            updates (ids: $update_id) {
                replies (limit: $limit, page: $page) {
                    id
                    body
                    created_at
                    creator { id name email }
                }
            }
        }
        """
        variables = {"update_id": [update_id], "limit": 100, "page": 1}
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            updates = data.get("updates", [])
            if not updates:
                break
            for reply in updates[0].get("replies", []):
                yield {
                    "type": "reply",
                    "id": str(reply["id"]),
                    "data": reply,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(updates[0].get("replies", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query ($limit: Int!, $page: Int!) {
            users (limit: $limit, page: $page) {
                id
                name
                email
                title
                mobile_phone
                photo_original
                is_admin
                is_guest
                is_view_only
                enabled
                created_at
                teams { id name }
            }
        }
        """
        variables = {"limit": 100, "page": 1}
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            for user in data.get("users", []):
                yield {
                    "type": "user",
                    "id": str(user["id"]),
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("users", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_teams(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query ($limit: Int!, $page: Int!) {
            teams (limit: $limit, page: $page) {
                id
                name
                picture_url
                users { id name email }
            }
        }
        """
        variables = {"limit": 100, "page": 1}
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            for team in data.get("teams", []):
                yield {
                    "type": "team",
                    "id": str(team["id"]),
                    "data": team,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("teams", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_workspaces(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query ($limit: Int!, $page: Int!) {
            workspaces (limit: $limit, page: $page) {
                id
                name
                kind
                description
                picture_url
                teams { id name }
                users { id name email }
            }
        }
        """
        variables = {"limit": 100, "page": 1}
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            for workspace in data.get("workspaces", []):
                yield {
                    "type": "workspace",
                    "id": str(workspace["id"]),
                    "data": workspace,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("workspaces", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_webhooks(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query ($limit: Int!, $page: Int!) {
            webhooks (limit: $limit, page: $page) {
                id
                board_id
                event
                config_str
                url
                secret
            }
        }
        """
        variables = {"limit": 100, "page": 1}
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            for webhook in data.get("webhooks", []):
                yield {
                    "type": "webhook",
                    "id": str(webhook["id"]),
                    "data": webhook,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("webhooks", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def _list_activity_logs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query ($limit: Int!, $page: Int!, $from: ISO8601DateTime, $to: ISO8601DateTime, $board_ids: [ID!]) {
            activity_logs (limit: $limit, page: $page, from: $from, to: $to, board_ids: $board_ids) {
                id
                entity
                event
                data
                user_id
                created_at
                board_id
                group_id
                item_id
                column_id
            }
        }
        """
        variables = {"limit": 100, "page": 1}
        if filters:
            for key in ["from", "to", "board_ids"]:
                if key in filters:
                    variables[key] = filters[key]
        if cursor and cursor.cursor:
            variables["page"] = cursor.cursor

        while True:
            data = await self._graphql_query(query, variables)
            for log in data.get("activity_logs", []):
                yield {
                    "type": "activity_log",
                    "id": str(log["id"]),
                    "data": log,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("activity_logs", [])) < variables["limit"]:
                break
            variables["page"] += 1

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_board": self._create_board,
            "update_board": self._update_board,
            "delete_board": self._delete_board,
            "create_group": self._create_group,
            "update_group": self._update_group,
            "delete_group": self._delete_group,
            "create_item": self._create_item,
            "update_item": self._update_item,
            "delete_item": self._delete_item,
            "move_item_to_group": self._move_item_to_group,
            "create_subitem": self._create_subitem,
            "update_subitem": self._update_subitem,
            "create_column": self._create_column,
            "update_column": self._update_column,
            "delete_column": self._delete_column,
            "change_column_value": self._change_column_value,
            "change_multiple_column_values": self._change_multiple_column_values,
            "create_update": self._create_update,
            "update_update": self._update_update,
            "delete_update": self._delete_update,
            "create_reply": self._create_reply,
            "create_team": self._create_team,
            "create_webhook": self._create_webhook,
            "delete_webhook": self._delete_webhook,
            "execute_query": self._execute_query,
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
                result.records_deleted += 1 if "delete" in operation else 0
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_board(self, board_data: Dict[str, Any]):
        payload = board_data.get("board", {})
        query = """
        mutation ($name: String!, $workspace_id: ID!, $board_kind: BoardKind!, $description: String) {
            create_board (board_name: $name, workspace_id: $workspace_id, board_kind: $board_kind, description: $description) {
                id
            }
        }
        """
        variables = {
            "name": payload.get("name"),
            "workspace_id": payload.get("workspace_id"),
            "board_kind": payload.get("board_kind", "public"),
            "description": payload.get("description", ""),
        }
        await self._graphql_query(query, variables)

    async def _update_board(self, board_data: Dict[str, Any]):
        board_id = board_data.get("board_id")
        if not board_id:
            raise ValueError("board_id required")
        payload = board_data.get("board", {})
        query = """
        mutation ($board_id: ID!, $name: String, $description: String) {
            update_board (board_id: $board_id, board_name: $name, description: $description) {
                id
            }
        }
        """
        variables = {"board_id": board_id}
        if "name" in payload:
            variables["name"] = payload["name"]
        if "description" in payload:
            variables["description"] = payload["description"]
        await self._graphql_query(query, variables)

    async def _delete_board(self, board_data: Dict[str, Any]):
        board_id = board_data.get("board_id")
        if not board_id:
            raise ValueError("board_id required")
        query = """
        mutation ($board_id: ID!) {
            delete_board (board_id: $board_id) {
                id
            }
        }
        """
        await self._graphql_query(query, {"board_id": board_id})

    async def _create_group(self, group_data: Dict[str, Any]):
        board_id = group_data.get("board_id")
        if not board_id:
            raise ValueError("board_id required")
        payload = group_data.get("group", {})
        query = """
        mutation ($board_id: ID!, $group_name: String!, $color: String, $position: Int) {
            create_group (board_id: $board_id, group_name: $group_name, color: $color, position: $position) {
                id
            }
        }
        """
        variables = {
            "board_id": board_id,
            "group_name": payload.get("title"),
            "color": payload.get("color"),
            "position": payload.get("position"),
        }
        await self._graphql_query(query, variables)

    async def _update_group(self, group_data: Dict[str, Any]):
        board_id = group_data.get("board_id")
        group_id = group_data.get("group_id")
        if not board_id or not group_id:
            raise ValueError("board_id and group_id required")
        payload = group_data.get("group", {})
        query = """
        mutation ($board_id: ID!, $group_id: String!, $title: String, $color: String, $position: Int) {
            update_group (board_id: $board_id, group_id: $group_id, title: $title, color: $color, position: $position) {
                id
            }
        }
        """
        variables = {"board_id": board_id, "group_id": group_id}
        if "title" in payload:
            variables["title"] = payload["title"]
        if "color" in payload:
            variables["color"] = payload["color"]
        if "position" in payload:
            variables["position"] = payload["position"]
        await self._graphql_query(query, variables)

    async def _delete_group(self, group_data: Dict[str, Any]):
        board_id = group_data.get("board_id")
        group_id = group_data.get("group_id")
        if not board_id or not group_id:
            raise ValueError("board_id and group_id required")
        query = """
        mutation ($board_id: ID!, $group_id: String!) {
            delete_group (board_id: $board_id, group_id: $group_id) {
                id
            }
        }
        """
        await self._graphql_query(query, {"board_id": board_id, "group_id": group_id})

    async def _create_item(self, item_data: Dict[str, Any]):
        board_id = item_data.get("board_id")
        group_id = item_data.get("group_id")
        if not board_id:
            raise ValueError("board_id required")
        payload = item_data.get("item", {})
        query = """
        mutation ($board_id: ID!, $group_id: String, $item_name: String!, $column_values: JSON) {
            create_item (board_id: $board_id, group_id: $group_id, item_name: $item_name, column_values: $column_values) {
                id
            }
        }
        """
        import json
        variables = {
            "board_id": board_id,
            "group_id": group_id,
            "item_name": payload.get("name"),
            "column_values": json.dumps(payload.get("column_values", {})),
        }
        await self._graphql_query(query, variables)

    async def _update_item(self, item_data: Dict[str, Any]):
        item_id = item_data.get("item_id")
        if not item_id:
            raise ValueError("item_id required")
        payload = item_data.get("item", {})
        query = """
        mutation ($item_id: ID!, $item_name: String, $column_values: JSON) {
            update_item (item_id: $item_id, item_name: $item_name, column_values: $column_values) {
                id
            }
        }
        """
        import json
        variables = {"item_id": item_id}
        if "name" in payload:
            variables["item_name"] = payload["name"]
        if "column_values" in payload:
            variables["column_values"] = json.dumps(payload["column_values"])
        await self._graphql_query(query, variables)

    async def _delete_item(self, item_data: Dict[str, Any]):
        item_id = item_data.get("item_id")
        if not item_id:
            raise ValueError("item_id required")
        query = """
        mutation ($item_id: ID!) {
            delete_item (item_id: $item_id) {
                id
            }
        }
        """
        await self._graphql_query(query, {"item_id": item_id})

    async def _move_item_to_group(self, item_data: Dict[str, Any]):
        item_id = item_data.get("item_id")
        group_id = item_data.get("group_id")
        if not item_id or not group_id:
            raise ValueError("item_id and group_id required")
        query = """
        mutation ($item_id: ID!, $group_id: String!) {
            move_item_to_group (item_id: $item_id, group_id: $group_id) {
                id
            }
        }
        """
        await self._graphql_query(query, {"item_id": item_id, "group_id": group_id})

    async def _create_subitem(self, subitem_data: Dict[str, Any]):
        parent_item_id = subitem_data.get("parent_item_id")
        if not parent_item_id:
            raise ValueError("parent_item_id required")
        payload = subitem_data.get("subitem", {})
        query = """
        mutation ($parent_item_id: ID!, $item_name: String!, $column_values: JSON) {
            create_subitem (parent_item_id: $parent_item_id, item_name: $item_name, column_values: $column_values) {
                id
            }
        }
        """
        import json
        variables = {
            "parent_item_id": parent_item_id,
            "item_name": payload.get("name"),
            "column_values": json.dumps(payload.get("column_values", {})),
        }
        await self._graphql_query(query, variables)

    async def _update_subitem(self, subitem_data: Dict[str, Any]):
        item_id = subitem_data.get("item_id")
        if not item_id:
            raise ValueError("item_id required")
        payload = subitem_data.get("subitem", {})
        query = """
        mutation ($item_id: ID!, $item_name: String, $column_values: JSON) {
            update_item (item_id: $item_id, item_name: $item_name, column_values: $column_values) {
                id
            }
        }
        """
        import json
        variables = {"item_id": item_id}
        if "name" in payload:
            variables["item_name"] = payload["name"]
        if "column_values" in payload:
            variables["column_values"] = json.dumps(payload["column_values"])
        await self._graphql_query(query, variables)

    async def _create_column(self, column_data: Dict[str, Any]):
        board_id = column_data.get("board_id")
        if not board_id:
            raise ValueError("board_id required")
        payload = column_data.get("column", {})
        query = """
        mutation ($board_id: ID!, $title: String!, $column_type: ColumnType!, $description: String, $default_value: JSON, $width: Int) {
            create_column (board_id: $board_id, title: $title, column_type: $column_type, description: $description, default_value: $default_value, width: $width) {
                id
            }
        }
        """
        variables = {
            "board_id": board_id,
            "title": payload.get("title"),
            "column_type": payload.get("type"),
            "description": payload.get("description"),
            "default_value": payload.get("default_value"),
            "width": payload.get("width"),
        }
        await self._graphql_query(query, variables)

    async def _update_column(self, column_data: Dict[str, Any]):
        board_id = column_data.get("board_id")
        column_id = column_data.get("column_id")
        if not board_id or not column_id:
            raise ValueError("board_id and column_id required")
        payload = column_data.get("column", {})
        query = """
        mutation ($board_id: ID!, $column_id: String!, $title: String, $description: String, $width: Int) {
            update_column (board_id: $board_id, column_id: $column_id, title: $title, description: $description, width: $width) {
                id
            }
        }
        """
        variables = {"board_id": board_id, "column_id": column_id}
        if "title" in payload:
            variables["title"] = payload["title"]
        if "description" in payload:
            variables["description"] = payload["description"]
        if "width" in payload:
            variables["width"] = payload["width"]
        await self._graphql_query(query, variables)

    async def _delete_column(self, column_data: Dict[str, Any]):
        board_id = column_data.get("board_id")
        column_id = column_data.get("column_id")
        if not board_id or not column_id:
            raise ValueError("board_id and column_id required")
        query = """
        mutation ($board_id: ID!, $column_id: String!) {
            delete_column (board_id: $board_id, column_id: $column_id) {
                id
            }
        }
        """
        await self._graphql_query(query, {"board_id": board_id, "column_id": column_id})

    async def _change_column_value(self, column_data: Dict[str, Any]):
        board_id = column_data.get("board_id")
        item_id = column_data.get("item_id")
        column_id = column_data.get("column_id")
        if not board_id or not item_id or not column_id:
            raise ValueError("board_id, item_id, and column_id required")
        query = """
        mutation ($board_id: ID!, $item_id: ID!, $column_id: String!, $value: JSON!) {
            change_column_value (board_id: $board_id, item_id: $item_id, column_id: $column_id, value: $value) {
                id
            }
        }
        """
        import json
        variables = {
            "board_id": board_id,
            "item_id": item_id,
            "column_id": column_id,
            "value": json.dumps(column_data.get("value")),
        }
        await self._graphql_query(query, variables)

    async def _change_multiple_column_values(self, column_data: Dict[str, Any]):
        board_id = column_data.get("board_id")
        item_id = column_data.get("item_id")
        if not board_id or not item_id:
            raise ValueError("board_id and item_id required")
        query = """
        mutation ($board_id: ID!, $item_id: ID!, $column_values: JSON!) {
            change_multiple_column_values (board_id: $board_id, item_id: $item_id, column_values: $column_values) {
                id
            }
        }
        """
        import json
        variables = {
            "board_id": board_id,
            "item_id": item_id,
            "column_values": json.dumps(column_data.get("column_values", {})),
        }
        await self._graphql_query(query, variables)

    async def _create_update(self, update_data: Dict[str, Any]):
        item_id = update_data.get("item_id")
        if not item_id:
            raise ValueError("item_id required")
        query = """
        mutation ($item_id: ID!, $body: String!) {
            create_update (item_id: $item_id, body: $body) {
                id
            }
        }
        """
        variables = {"item_id": item_id, "body": update_data.get("body", "")}
        await self._graphql_query(query, variables)

    async def _update_update(self, update_data: Dict[str, Any]):
        update_id = update_data.get("update_id")
        if not update_id:
            raise ValueError("update_id required")
        query = """
        mutation ($update_id: ID!, $body: String!) {
            update_update (id: $update_id, body: $body) {
                id
            }
        }
        """
        variables = {"update_id": update_id, "body": update_data.get("body", "")}
        await self._graphql_query(query, variables)

    async def _delete_update(self, update_data: Dict[str, Any]):
        update_id = update_data.get("update_id")
        if not update_id:
            raise ValueError("update_id required")
        query = """
        mutation ($update_id: ID!) {
            delete_update (id: $update_id) {
                id
            }
        }
        """
        await self._graphql_query(query, {"update_id": update_id})

    async def _create_reply(self, reply_data: Dict[str, Any]):
        update_id = reply_data.get("update_id")
        if not update_id:
            raise ValueError("update_id required")
        query = """
        mutation ($update_id: ID!, $body: String!) {
            create_reply (update_id: $update_id, body: $body) {
                id
            }
        }
        """
        variables = {"update_id": update_id, "body": reply_data.get("body", "")}
        await self._graphql_query(query, variables)

    async def _create_team(self, team_data: Dict[str, Any]):
        query = """
        mutation ($name: String!, $users_ids: [ID!]) {
            create_team (team_name: $name, users_ids: $users_ids) {
                id
            }
        }
        """
        variables = {
            "name": team_data.get("name"),
            "users_ids": team_data.get("user_ids", []),
        }
        await self._graphql_query(query, variables)

    async def _create_webhook(self, webhook_data: Dict[str, Any]):
        query = """
        mutation ($board_id: ID!, $url: String!, $event: WebhookEventType!, $config: JSON, $secret: String) {
            create_webhook (board_id: $board_id, url: $url, event: $event, config: $config, secret: $secret) {
                id
            }
        }
        """
        variables = {
            "board_id": webhook_data.get("board_id"),
            "url": webhook_data.get("url"),
            "event": webhook_data.get("event"),
            "config": webhook_data.get("config", {}),
            "secret": webhook_data.get("secret"),
        }
        await self._graphql_query(query, variables)

    async def _delete_webhook(self, webhook_data: Dict[str, Any]):
        webhook_id = webhook_data.get("webhook_id")
        if not webhook_id:
            raise ValueError("webhook_id required")
        query = """
        mutation ($webhook_id: ID!) {
            delete_webhook (id: $webhook_id) {
                id
            }
        }
        """
        await self._graphql_query(query, {"webhook_id": webhook_id})

    async def _execute_query(self, query_data: Dict[str, Any]):
        query = query_data.get("query")
        variables = query_data.get("variables", {})
        if not query:
            raise ValueError("query required")
        await self._graphql_query(query, variables)

    async def test_connection(self) -> bool:
        try:
            query = "{ me { id name } }"
            data = await self._graphql_query(query)
            return "me" in data
        except Exception as e:
            logger.error(f"Monday.com connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(MondayConnector, MondayConnector.CONFIG)