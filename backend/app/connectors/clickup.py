"""
ClickUp Connector for VCOS.

Provides integration with ClickUp for project management, tasks, docs, and goals.
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


class ClickUpConnector(BaseConnector):
    """ClickUp Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="clickup",
        display_name="ClickUp",
        description="Project management and productivity platform",
        category="project_management",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "access_token": {"type": "string", "description": "Personal API Token or OAuth Access Token"},
                "refresh_token": {"type": "string"},
                "team_id": {"type": "string", "description": "ClickUp Team (Workspace) ID"},
            },
            "required": ["client_id", "client_secret", "redirect_uri"],
        },
        required_scopes=[
            "task_read",
            "task_write",
            "list_read",
            "list_write",
            "folder_read",
            "folder_write",
            "space_read",
            "space_write",
            "goal_read",
            "goal_write",
            "doc_read",
            "doc_write",
            "comment_read",
            "comment_write",
            "webhook_read",
            "webhook_write",
        ],
        supported_operations=[
            "list_teams",
            "get_team",
            "list_spaces",
            "get_space",
            "list_folders",
            "get_folder",
            "list_lists",
            "get_list",
            "list_tasks",
            "get_task",
            "create_task",
            "update_task",
            "delete_task",
            "list_subtasks",
            "create_subtask",
            "list_comments",
            "create_comment",
            "update_comment",
            "delete_comment",
            "list_checklists",
            "create_checklist",
            "update_checklist",
            "list_goals",
            "get_goal",
            "create_goal",
            "update_goal",
            "list_docs",
            "get_doc",
            "create_doc",
            "update_doc",
            "list_views",
            "get_view",
            "list_webhooks",
            "create_webhook",
            "delete_webhook",
            "list_members",
            "get_member",
            "list_roles",
            "list_tags",
            "create_tag",
            "list_custom_fields",
            "create_custom_field",
        ],
        webhook_events=[
            "taskCreated",
            "taskUpdated",
            "taskDeleted",
            "taskPriorityUpdated",
            "taskStatusUpdated",
            "taskAssigneeUpdated",
            "taskTagUpdated",
            "taskDueDateUpdated",
            "taskTimeEstimateUpdated",
            "taskTimeTrackedUpdated",
            "taskChecklistUpdated",
            "taskAttachmentAdded",
            "taskAttachmentRemoved",
            "taskCommentPosted",
            "taskCommentUpdated",
            "taskCommentDeleted",
            "listCreated",
            "listUpdated",
            "listDeleted",
            "folderCreated",
            "folderUpdated",
            "folderDeleted",
            "spaceCreated",
            "spaceUpdated",
            "spaceDeleted",
            "goalCreated",
            "goalUpdated",
            "goalDeleted",
            "docCreated",
            "docUpdated",
            "docDeleted",
            "webhookCreated",
            "webhookDeleted",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=100,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/clickup.svg",
        documentation_url="https://clickup.com/api",
    )

    BASE_URL = "https://api.clickup.com/api/v2"
    TOKEN_URL = "https://app.clickup.com/api/v2/oauth/token"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.access_token = connection_config.get("access_token")
        self.refresh_token = connection_config.get("refresh_token")
        self.team_id = connection_config.get("team_id")
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with ClickUp using Personal API Token or OAuth2."""
        if self.access_token:
            self._authenticated = True
            logger.info("ClickUp authenticated with personal API token")
            return True

        client_id = self.connection_config.get("client_id")
        client_secret = self.connection_config.get("client_secret")
        
        if client_id and client_secret:
            from app.connectors.base import TokenManager
            self._token_manager = TokenManager(client_id, client_secret, self.TOKEN_URL)
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info("ClickUp authenticated with OAuth2")
            return True

        raise ValueError("ClickUp requires access_token or OAuth2 credentials (client_id, client_secret)")

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
        """Make ClickUp API request with error handling."""
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
                    raise Exception(f"ClickUp API error: {resp.status} - {error_text}")
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
            "list_spaces": self._list_spaces,
            "list_folders": self._list_folders,
            "list_lists": self._list_lists,
            "list_tasks": self._list_tasks,
            "list_subtasks": self._list_subtasks,
            "list_comments": self._list_comments,
            "list_checklists": self._list_checklists,
            "list_goals": self._list_goals,
            "list_docs": self._list_docs,
            "list_views": self._list_views,
            "list_webhooks": self._list_webhooks,
            "list_members": self._list_members,
            "list_roles": self._list_roles,
            "list_tags": self._list_tags,
            "list_custom_fields": self._list_custom_fields,
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
        data = await self._make_request("GET", "/team")
        for team in data.get("teams", []):
            yield {
                "type": "team",
                "id": team["id"],
                "data": team,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_spaces(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        team_id = filters.get("team_id") or self.team_id
        if not team_id:
            raise ValueError("team_id filter required")

        params = {"archived": "false"}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/team/{team_id}/space", params=params)
            for space in data.get("spaces", []):
                yield {
                    "type": "space",
                    "id": space["id"],
                    "data": space,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("page", 0) < data.get("total_pages", 1) - 1:
                params["page"] = (params.get("page", 0) + 1)
            else:
                break

    async def _list_folders(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        space_id = filters.get("space_id")
        if not space_id:
            raise ValueError("space_id filter required")

        params = {"archived": "false"}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/space/{space_id}/folder", params=params)
            for folder in data.get("folders", []):
                yield {
                    "type": "folder",
                    "id": folder["id"],
                    "data": folder,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("page", 0) < data.get("total_pages", 1) - 1:
                params["page"] = (params.get("page", 0) + 1)
            else:
                break

    async def _list_lists(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        folder_id = filters.get("folder_id")
        space_id = filters.get("space_id")
        
        if not folder_id and not space_id:
            raise ValueError("folder_id or space_id filter required")

        if folder_id:
            endpoint = f"/folder/{folder_id}/list"
        else:
            endpoint = f"/space/{space_id}/list"

        params = {"archived": "false"}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", endpoint, params=params)
            for lst in data.get("lists", []):
                yield {
                    "type": "list",
                    "id": lst["id"],
                    "data": lst,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("page", 0) < data.get("total_pages", 1) - 1:
                params["page"] = (params.get("page", 0) + 1)
            else:
                break

    async def _list_tasks(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        list_id = filters.get("list_id")
        if not list_id:
            raise ValueError("list_id filter required")

        params = {"page": 0, "order_by": "created", "reverse": "true", "subtasks": "true"}
        if filters:
            for key in ["statuses", "assignees", "tags", "due_date_gt", "due_date_lt", "date_created_gt", "date_created_lt", "date_updated_gt", "date_updated_lt"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/list/{list_id}/task", params=params)
            for task in data.get("tasks", []):
                yield {
                    "type": "task",
                    "id": task["id"],
                    "data": task,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("page", 0) < data.get("total_pages", 1) - 1:
                params["page"] = (params.get("page", 0) + 1)
            else:
                break

    async def _list_subtasks(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        task_id = filters.get("task_id")
        if not task_id:
            raise ValueError("task_id filter required")

        data = await self._make_request("GET", f"/task/{task_id}/subtask")
        for subtask in data.get("subtasks", []):
            yield {
                "type": "subtask",
                "id": subtask["id"],
                "data": subtask,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_comments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        task_id = filters.get("task_id")
        if not task_id:
            raise ValueError("task_id filter required")

        params = {"page": 0}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/task/{task_id}/comment", params=params)
            for comment in data.get("comments", []):
                yield {
                    "type": "comment",
                    "id": comment["id"],
                    "data": comment,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("page", 0) < data.get("total_pages", 1) - 1:
                params["page"] = (params.get("page", 0) + 1)
            else:
                break

    async def _list_checklists(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        task_id = filters.get("task_id")
        if not task_id:
            raise ValueError("task_id filter required")

        data = await self._make_request("GET", f"/task/{task_id}/checklist")
        for checklist in data.get("checklists", []):
            yield {
                "type": "checklist",
                "id": checklist["id"],
                "data": checklist,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_goals(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        team_id = filters.get("team_id") or self.team_id
        if not team_id:
            raise ValueError("team_id filter required")

        params = {"page": 0}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/team/{team_id}/goal", params=params)
            for goal in data.get("goals", []):
                yield {
                    "type": "goal",
                    "id": goal["id"],
                    "data": goal,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("page", 0) < data.get("total_pages", 1) - 1:
                params["page"] = (params.get("page", 0) + 1)
            else:
                break

    async def _list_docs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        team_id = filters.get("team_id") or self.team_id
        if not team_id:
            raise ValueError("team_id filter required")

        params = {"page": 0}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/team/{team_id}/doc", params=params)
            for doc in data.get("docs", []):
                yield {
                    "type": "doc",
                    "id": doc["id"],
                    "data": doc,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("page", 0) < data.get("total_pages", 1) - 1:
                params["page"] = (params.get("page", 0) + 1)
            else:
                break

    async def _list_views(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        list_id = filters.get("list_id")
        if not list_id:
            raise ValueError("list_id filter required")

        data = await self._make_request("GET", f"/list/{list_id}/view")
        for view in data.get("views", []):
            yield {
                "type": "view",
                "id": view["id"],
                "data": view,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_webhooks(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        team_id = filters.get("team_id") or self.team_id
        if not team_id:
            raise ValueError("team_id filter required")

        data = await self._make_request("GET", f"/team/{team_id}/webhook")
        for webhook in data.get("webhooks", []):
            yield {
                "type": "webhook",
                "id": webhook["id"],
                "data": webhook,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_members(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        team_id = filters.get("team_id") or self.team_id
        if not team_id:
            raise ValueError("team_id filter required")

        data = await self._make_request("GET", f"/team/{team_id}/member")
        for member in data.get("members", []):
            yield {
                "type": "member",
                "id": member["user"]["id"],
                "data": member,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_roles(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        team_id = filters.get("team_id") or self.team_id
        if not team_id:
            raise ValueError("team_id filter required")

        data = await self._make_request("GET", f"/team/{team_id}/role")
        for role in data.get("roles", []):
            yield {
                "type": "role",
                "id": role["id"],
                "data": role,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_tags(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        space_id = filters.get("space_id")
        if not space_id:
            raise ValueError("space_id filter required")

        data = await self._make_request("GET", f"/space/{space_id}/tag")
        for tag in data.get("tags", []):
            yield {
                "type": "tag",
                "id": tag["name"],
                "data": tag,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_custom_fields(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        space_id = filters.get("space_id")
        if not space_id:
            raise ValueError("space_id filter required")

        data = await self._make_request("GET", f"/space/{space_id}/field")
        for field in data.get("fields", []):
            yield {
                "type": "custom_field",
                "id": field["id"],
                "data": field,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_task": self._create_task,
            "update_task": self._update_task,
            "delete_task": self._delete_task,
            "create_subtask": self._create_subtask,
            "create_comment": self._create_comment,
            "update_comment": self._update_comment,
            "delete_comment": self._delete_comment,
            "create_checklist": self._create_checklist,
            "update_checklist": self._update_checklist,
            "create_goal": self._create_goal,
            "update_goal": self._update_goal,
            "create_doc": self._create_doc,
            "update_doc": self._update_doc,
            "create_webhook": self._create_webhook,
            "delete_webhook": self._delete_webhook,
            "create_tag": self._create_tag,
            "create_custom_field": self._create_custom_field,
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

    async def _create_task(self, task_data: Dict[str, Any]):
        list_id = task_data.get("list_id")
        if not list_id:
            raise ValueError("list_id required")
        payload = task_data.get("task", {})
        await self._make_request("POST", f"/list/{list_id}/task", json=payload)

    async def _update_task(self, task_data: Dict[str, Any]):
        task_id = task_data.get("task_id")
        if not task_id:
            raise ValueError("task_id required")
        payload = task_data.get("task", {})
        await self._make_request("PUT", f"/task/{task_id}", json=payload)

    async def _delete_task(self, task_data: Dict[str, Any]):
        task_id = task_data.get("task_id")
        if not task_id:
            raise ValueError("task_id required")
        await self._make_request("DELETE", f"/task/{task_id}")

    async def _create_subtask(self, subtask_data: Dict[str, Any]):
        task_id = subtask_data.get("task_id")
        if not task_id:
            raise ValueError("task_id required")
        payload = subtask_data.get("subtask", {})
        await self._make_request("POST", f"/task/{task_id}/subtask", json=payload)

    async def _create_comment(self, comment_data: Dict[str, Any]):
        task_id = comment_data.get("task_id")
        if not task_id:
            raise ValueError("task_id required")
        payload = {
            "comment_text": comment_data.get("comment_text"),
            "assignee": comment_data.get("assignee"),
            "notify_all": comment_data.get("notify_all", False),
        }
        await self._make_request("POST", f"/task/{task_id}/comment", json=payload)

    async def _update_comment(self, comment_data: Dict[str, Any]):
        comment_id = comment_data.get("comment_id")
        if not comment_id:
            raise ValueError("comment_id required")
        payload = {"comment_text": comment_data.get("comment_text")}
        await self._make_request("PUT", f"/comment/{comment_id}", json=payload)

    async def _delete_comment(self, comment_data: Dict[str, Any]):
        comment_id = comment_data.get("comment_id")
        if not comment_id:
            raise ValueError("comment_id required")
        await self._make_request("DELETE", f"/comment/{comment_id}")

    async def _create_checklist(self, checklist_data: Dict[str, Any]):
        task_id = checklist_data.get("task_id")
        if not task_id:
            raise ValueError("task_id required")
        payload = checklist_data.get("checklist", {})
        await self._make_request("POST", f"/task/{task_id}/checklist", json=payload)

    async def _update_checklist(self, checklist_data: Dict[str, Any]):
        checklist_id = checklist_data.get("checklist_id")
        if not checklist_id:
            raise ValueError("checklist_id required")
        payload = checklist_data.get("checklist", {})
        await self._make_request("PUT", f"/checklist/{checklist_id}", json=payload)

    async def _create_goal(self, goal_data: Dict[str, Any]):
        team_id = goal_data.get("team_id") or self.team_id
        if not team_id:
            raise ValueError("team_id required")
        payload = goal_data.get("goal", {})
        await self._make_request("POST", f"/team/{team_id}/goal", json=payload)

    async def _update_goal(self, goal_data: Dict[str, Any]):
        goal_id = goal_data.get("goal_id")
        if not goal_id:
            raise ValueError("goal_id required")
        payload = goal_data.get("goal", {})
        await self._make_request("PUT", f"/goal/{goal_id}", json=payload)

    async def _create_doc(self, doc_data: Dict[str, Any]):
        team_id = doc_data.get("team_id") or self.team_id
        if not team_id:
            raise ValueError("team_id required")
        payload = doc_data.get("doc", {})
        await self._make_request("POST", f"/team/{team_id}/doc", json=payload)

    async def _update_doc(self, doc_data: Dict[str, Any]):
        doc_id = doc_data.get("doc_id")
        if not doc_id:
            raise ValueError("doc_id required")
        payload = doc_data.get("doc", {})
        await self._make_request("PUT", f"/doc/{doc_id}", json=payload)

    async def _create_webhook(self, webhook_data: Dict[str, Any]):
        team_id = webhook_data.get("team_id") or self.team_id
        if not team_id:
            raise ValueError("team_id required")
        payload = {
            "endpoint": webhook_data.get("endpoint"),
            "events": webhook_data.get("events", ["*"]),
            "space_id": webhook_data.get("space_id"),
            "folder_id": webhook_data.get("folder_id"),
            "list_id": webhook_data.get("list_id"),
            "task_id": webhook_data.get("task_id"),
        }
        await self._make_request("POST", f"/team/{team_id}/webhook", json=payload)

    async def _delete_webhook(self, webhook_data: Dict[str, Any]):
        webhook_id = webhook_data.get("webhook_id")
        if not webhook_id:
            raise ValueError("webhook_id required")
        await self._make_request("DELETE", f"/webhook/{webhook_id}")

    async def _create_tag(self, tag_data: Dict[str, Any]):
        space_id = tag_data.get("space_id")
        if not space_id:
            raise ValueError("space_id required")
        payload = {
            "name": tag_data.get("name"),
            "tag_fg": tag_data.get("tag_fg", "#000000"),
            "tag_bg": tag_data.get("tag_bg", "#ffffff"),
        }
        await self._make_request("POST", f"/space/{space_id}/tag", json=payload)

    async def _create_custom_field(self, field_data: Dict[str, Any]):
        space_id = field_data.get("space_id")
        if not space_id:
            raise ValueError("space_id required")
        payload = field_data.get("custom_field", {})
        await self._make_request("POST", f"/space/{space_id}/field", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/user")
            return "user" in data
        except Exception as e:
            logger.error(f"ClickUp connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(ClickUpConnector, ClickUpConnector.CONFIG)