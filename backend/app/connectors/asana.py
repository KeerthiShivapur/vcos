"""
Asana Connector for VCOS.

Provides integration with Asana for work management including projects,
tasks, teams, and users.
"""

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


class AsanaConnector(BaseConnector):
    """Asana Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="asana",
        display_name="Asana",
        description="Work management platform for teams",
        category="project_mgmt",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "access_token": {"type": "string", "description": "Personal Access Token"},
                "workspace_gid": {"type": "string", "description": "Workspace GID (optional, will auto-detect)"},
            },
            "required": ["access_token"],
        },
        required_scopes=[],
        supported_operations=[
            "list_users",
            "get_user",
            "list_projects",
            "get_project",
            "create_project",
            "update_project",
            "delete_project",
            "list_tasks",
            "get_task",
            "create_task",
            "update_task",
            "delete_task",
            "list_teams",
            "get_team",
            "list_team_members",
            "list_sections",
            "create_section",
            "add_task_to_section",
            "list_custom_fields",
            "get_custom_field",
            "create_custom_field",
            "list_tags",
            "create_tag",
            "add_tag_to_task",
            "remove_tag_from_task",
            "list_stories",
            "create_story",
        ],
        webhook_events=[
            "task.created",
            "task.updated",
            "task.deleted",
            "task.completed",
            "task.uncompleted",
            "task.assignee_changed",
            "task.due_date_changed",
            "task.due_on_changed",
            "task.added_to_project",
            "task.removed_from_project",
            "task.tag_added",
            "task.tag_removed",
            "task.dependency_added",
            "task.dependency_removed",
            "subtask_added",
            "subtask_removed",
            "story.created",
            "story.deleted",
            "project.created",
            "project.updated",
            "project.deleted",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=1500,
            burst=100,
        ),
    )

    BASE_URL = "https://app.asana.com/api/1.0"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.access_token = connection_config.get("access_token")
        self.workspace_gid = connection_config.get("workspace_gid")
        self._authenticated = False

    async def authenticate(self) -> bool:
        """Authenticate with Asana using Personal Access Token."""
        if not self.access_token:
            raise ValueError("Asana requires access_token")

        # Test the token
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with self.session.get(f"{self.BASE_URL}/users/me", headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._authenticated = True
                # Auto-detect workspace if not provided
                if not self.workspace_gid:
                    workspaces = await self._get_workspaces()
                    if workspaces:
                        self.workspace_gid = workspaces[0]["gid"]
                logger.info("Asana authenticated with PAT")
                return True
            return False

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get_workspaces(self) -> List[Dict[str, Any]]:
        async with self.session.get(
            f"{self.BASE_URL}/workspaces",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", [])

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
            "list_projects": self._list_projects,
            "list_tasks": self._list_tasks,
            "list_teams": self._list_teams,
            "list_sections": self._list_sections,
            "list_custom_fields": self._list_custom_fields,
            "list_tags": self._list_tags,
            "list_stories": self._list_stories,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _paginated_get(
        self,
        endpoint: str,
        params: Dict[str, Any] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = urljoin(self.BASE_URL, endpoint)
        params = params or {}
        params.setdefault("limit", 100)

        while True:
            headers = await self._get_headers()
            async with self.session.get(url, headers=headers, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for item in data.get("data", []):
                    yield item

                next_page = data.get("next_page")
                if next_page and next_page.get("offset"):
                    params["offset"] = next_page["offset"]
                else:
                    break

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"workspace": self.workspace_gid, "limit": 100}
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        async for user in self._paginated_get("/users", params):
            yield {
                "type": "user",
                "id": user["gid"],
                "data": user,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_projects(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"workspace": self.workspace_gid, "limit": 100}
        if filters and filters.get("archived") is not None:
            params["archived"] = str(filters["archived"]).lower()
        if filters and filters.get("team"):
            params["team"] = filters["team"]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        async for project in self._paginated_get("/projects", params):
            yield {
                "type": "project",
                "id": project["gid"],
                "data": project,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_tasks(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters and filters.get("project"):
            params["project"] = filters["project"]
        if filters and filters.get("assignee"):
            params["assignee"] = filters["assignee"]
        if filters and filters.get("section"):
            params["section"] = filters["section"]
        if filters and filters.get("completed_since"):
            params["completed_since"] = filters["completed_since"]
        if filters and filters.get("modified_since"):
            params["modified_since"] = filters["modified_since"]
        if filters and filters.get("workspace"):
            params["workspace"] = filters["workspace"]
        else:
            params["workspace"] = self.workspace_gid
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        opt_fields = "gid,name,notes,completed,completed_at,created_at,modified_at,assignee,assignee_status,projects,sections,tags,custom_fields,dependencies,dependents,parent,hearted,hearts,liked,likes,num_hearts,num_likes,permalink_url,resource_subtype,start_on,due_on,due_at"
        params["opt_fields"] = opt_fields

        async for task in self._paginated_get("/tasks", params):
            yield {
                "type": "task",
                "id": task["gid"],
                "data": task,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_teams(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"organization": filters.get("organization")} if filters and filters.get("organization") else {}
        params["limit"] = 100

        async for team in self._paginated_get("/teams", params):
            yield {
                "type": "team",
                "id": team["gid"],
                "data": team,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_sections(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        project_gid = filters.get("project") if filters else None
        if not project_gid:
            raise ValueError("project filter required")

        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        async for section in self._paginated_get(f"/projects/{project_gid}/sections", params):
            yield {
                "type": "section",
                "id": section["gid"],
                "data": section,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_custom_fields(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        workspace_gid = filters.get("workspace", self.workspace_gid)
        params = {"workspace": workspace_gid, "limit": 100}

        async for field in self._paginated_get("/custom_fields", params):
            yield {
                "type": "custom_field",
                "id": field["gid"],
                "data": field,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_tags(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"workspace": self.workspace_gid, "limit": 100}

        async for tag in self._paginated_get("/tags", params):
            yield {
                "type": "tag",
                "id": tag["gid"],
                "data": tag,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_stories(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        task_gid = filters.get("task") if filters else None
        if not task_gid:
            raise ValueError("task filter required")

        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        async for story in self._paginated_get(f"/tasks/{task_gid}/stories", params):
            yield {
                "type": "story",
                "id": story["gid"],
                "data": story,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_task": self._create_task,
            "update_task": self._update_task,
            "delete_task": self._delete_task,
            "create_project": self._create_project,
            "update_project": self._update_project,
            "create_section": self._create_section,
            "add_task_to_section": self._add_task_to_section,
            "create_tag": self._create_tag,
            "add_tag_to_task": self._add_tag_to_task,
            "remove_tag_from_task": self._remove_tag_from_task,
            "create_story": self._create_story,
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

    async def _create_task(self, task_data: Dict[str, Any]):
        payload = {
            "data": {
                "name": task_data.get("name"),
                "notes": task_data.get("notes", ""),
                "projects": [task_data.get("project")] if task_data.get("project") else [],
                "assignee": task_data.get("assignee"),
                "due_on": task_data.get("due_on"),
                "due_at": task_data.get("due_at"),
                "start_on": task_data.get("start_on"),
                "tags": task_data.get("tags", []),
                "custom_fields": task_data.get("custom_fields", {}),
            }
        }
        async with self.session.post(
            f"{self.BASE_URL}/tasks",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_task(self, task_data: Dict[str, Any]):
        task_gid = task_data.get("gid") or task_data.get("id")
        payload = {
            "data": {k: v for k, v in task_data.items() if k not in ["gid", "id"]}
        }
        async with self.session.put(
            f"{self.BASE_URL}/tasks/{task_gid}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _delete_task(self, task_data: Dict[str, Any]):
        task_gid = task_data.get("gid") or task_data.get("id")
        async with self.session.delete(
            f"{self.BASE_URL}/tasks/{task_gid}",
            headers=await self._get_headers(),
        ) as resp:
            resp.raise_for_status()

    async def _create_project(self, project_data: Dict[str, Any]):
        payload = {
            "data": {
                "name": project_data.get("name"),
                "notes": project_data.get("notes", ""),
                "workspace": self.workspace_gid,
                "team": project_data.get("team"),
                "public": project_data.get("public", True),
                "color": project_data.get("color"),
                "notes": project_data.get("notes", ""),
            }
        }
        async with self.session.post(
            f"{self.BASE_URL}/projects",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_project(self, project_data: Dict[str, Any]):
        project_gid = project_data.get("gid") or project_data.get("id")
        payload = {"data": {k: v for k, v in project_data.items() if k not in ["gid", "id"]}}
        async with self.session.put(
            f"{self.BASE_URL}/projects/{project_gid}",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _create_section(self, section_data: Dict[str, Any]):
        project_gid = section_data.get("project")
        payload = {
            "data": {
                "name": section_data.get("name"),
                "project": project_gid,
            }
        }
        async with self.session.post(
            f"{self.BASE_URL}/sections",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _add_task_to_section(self, data: Dict[str, Any]):
        section_gid = data.get("section")
        task_gid = data.get("task")
        payload = {"data": {"task": task_gid}}
        async with self.session.post(
            f"{self.BASE_URL}/sections/{section_gid}/addTask",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _create_tag(self, tag_data: Dict[str, Any]):
        payload = {
            "data": {
                "name": tag_data.get("name"),
                "workspace": self.workspace_gid,
                "color": tag_data.get("color"),
                "notes": tag_data.get("notes", ""),
            }
        }
        async with self.session.post(
            f"{self.BASE_URL}/tags",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _add_tag_to_task(self, data: Dict[str, Any]):
        task_gid = data.get("task")
        tag_gid = data.get("tag")
        payload = {"data": {"tag": tag_gid}}
        async with self.session.post(
            f"{self.BASE_URL}/tasks/{task_gid}/addTag",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _remove_tag_from_task(self, data: Dict[str, Any]):
        task_gid = data.get("task")
        tag_gid = data.get("tag")
        async with self.session.post(
            f"{self.BASE_URL}/tasks/{task_gid}/removeTag",
            headers=await self._get_headers(),
            json={"data": {"tag": tag_gid}},
        ) as resp:
            resp.raise_for_status()

    async def _create_story(self, story_data: Dict[str, Any]):
        task_gid = story_data.get("task")
        payload = {
            "data": {
                "text": story_data.get("text"),
                "html_text": story_data.get("html_text"),
            }
        }
        async with self.session.post(
            f"{self.BASE_URL}/tasks/{task_gid}/stories",
            headers=await self._get_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> bool:
        try:
            async with self.session.get(
                f"{self.BASE_URL}/users/me",
                headers=await self._get_headers(),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Asana connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(AsanaConnector, AsanaConnector.CONFIG)