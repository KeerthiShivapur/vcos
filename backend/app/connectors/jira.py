"""
Jira Connector for VCOS.

Provides integration with Jira Cloud for issue tracking, project management,
and agile workflows.
"""

import logging
import base64
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


class JiraConnector(BaseConnector):
    """Jira Cloud Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="jira",
        display_name="Jira",
        description="Project and issue tracking for software teams",
        category="project_mgmt",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": "Jira instance URL (e.g., https://company.atlassian.net)"},
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "api_token": {"type": "string", "description": "API token for basic auth"},
                "email": {"type": "string", "description": "Email for basic auth"},
            },
            "required": ["base_url"],
            "oneOf": [
                {"required": ["client_id", "client_secret", "redirect_uri"]},
                {"required": ["api_token", "email"]},
            ],
        },
        required_scopes=[
            "read:jira-work",
            "write:jira-work",
            "manage:jira-project",
            "read:jira-user",
        ],
        supported_operations=[
            "list_issues",
            "get_issue",
            "create_issue",
            "update_issue",
            "transition_issue",
            "delete_issue",
            "search_issues",
            "list_projects",
            "get_project",
            "create_project",
            "update_project",
            "list_boards",
            "get_board",
            "list_sprints",
            "get_sprint",
            "create_sprint",
            "update_sprint",
            "list_versions",
            "create_version",
            "list_components",
            "create_component",
            "list_users",
            "get_user",
            "add_comment",
            "add_worklog",
        ],
        webhook_events=[
            "jira:issue_created",
            "jira:issue_updated",
            "jira:issue_deleted",
            "jira:issue_transitioned",
            "jira:issue_assigned",
            "jira:issue_commented",
            "jira:issue_worklogged",
            "jira:issue_link_created",
            "jira:issue_link_deleted",
            "jira:sprint_created",
            "jira:sprint_updated",
            "jira:sprint_deleted",
            "jira:sprint_started",
            "jira:sprint_closed",
            "jira:project_created",
            "jira:project_updated",
            "jira:project_deleted",
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
        self.base_url = connection_config.get("base_url").rstrip("/")
        self.api_token = connection_config.get("api_token")
        self.email = connection_config.get("email")
        self.client_id = connection_config.get("client_id")
        self.client_secret = connection_config.get("client_secret")
        self._token_manager = None
        self._auth_header = None

    async def authenticate(self) -> bool:
        """Authenticate with Jira using API token or OAuth2."""
        if self.api_token and self.email:
            credentials = f"{self.email}:{self.api_token}"
            encoded = base64.b64encode(credentials.encode()).decode()
            self._auth_header = f"Basic {encoded}"
            self._authenticated = True
            logger.info("Jira authenticated with API token")
            return True

        if self.client_id and self.client_secret:
            from app.connectors.base import TokenManager
            token_url = urljoin(self.base_url, "/oauth/token")
            self._token_manager = TokenManager(
                self.client_id,
                self.client_secret,
                token_url,
            )
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info("Jira authenticated with OAuth2")
            return True

        raise ValueError("Jira requires either API token + email or OAuth2 credentials")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._auth_header:
            headers["Authorization"] = self._auth_header
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
        if not self._authenticated:
            await self.authenticate()

        handlers = {
            "list_issues": self._list_issues,
            "search_issues": self._search_issues,
            "list_projects": self._list_projects,
            "list_boards": self._list_boards,
            "list_sprints": self._list_sprints,
            "list_versions": self._list_versions,
            "list_components": self._list_components,
            "list_users": self._list_users,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _paginated_get(self, endpoint: str, params: Dict[str, Any] = None) -> AsyncGenerator[Dict[str, Any], None]:
        url = urljoin(self.base_url, f"/rest/api/3/{endpoint}")
        params = params or {}
        params.setdefault("startAt", 0)
        params.setdefault("maxResults", 100)

        while True:
            headers = await self._get_headers()
            async with self.session.get(url, headers=headers, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()

                if isinstance(data, dict) and "values" in data:
                    items = data["values"]
                    total = data.get("total", len(items))
                    is_last = data.get("isLast", True)
                    start_at = data.get("startAt", 0)
                else:
                    items = [data] if not isinstance(data, list) else data
                    total = len(items)
                    is_last = True

                for item in items:
                    yield item

                if is_last or len(items) < params.get("maxResults", 100):
                    break

                params["startAt"] = params.get("startAt", 0) + params.get("maxResults", 100)

    async def _list_issues(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        jql = filters.get("jql") if filters else "ORDER BY updated DESC"
        if filters and filters.get("project"):
            jql = f"project = {filters['project']} AND {jql}"
        if filters and filters.get("since"):
            jql = f"{jql} AND updated >= {filters['since']}"

        params = {
            "jql": jql,
            "maxResults": 100,
            "fields": "*all",
            "expand": "changelog,transitions,names,schema,operations,editmeta,versionedRepresentations",
        }
        if cursor and cursor.cursor:
            params["startAt"] = cursor.cursor

        while True:
            headers = await self._get_headers()
            url = urljoin(self.base_url, "/rest/api/3/search")
            async with self.session.get(url, headers=headers, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for issue in data.get("issues", []):
                    yield {
                        "type": "issue",
                        "id": issue["id"],
                        "data": issue,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                if data.get("isLast", True):
                    break
                params["startAt"] = params.get("startAt", 0) + params.get("maxResults", 100)

    async def _search_issues(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        async for item in self._list_issues(cursor, filters):
            yield item

    async def _list_projects(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"expand": "description,lead,issueTypes,url,projectKeys,permissions,insight"}
        if cursor and cursor.cursor:
            params["startAt"] = cursor.cursor

        async for project in self._paginated_get("project/search", params):
            yield {
                "type": "project",
                "id": project["id"],
                "data": project,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_boards(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"maxResults": 50}
        if filters and filters.get("project_key"):
            params["projectKeyOrId"] = filters["project_key"]
        if cursor and cursor.cursor:
            params["startAt"] = cursor.cursor

        async for board in self._paginated_get("board", params):
            yield {
                "type": "board",
                "id": str(board["id"]),
                "data": board,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_sprints(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        board_id = filters.get("board_id") if filters else None
        if not board_id:
            raise ValueError("board_id filter required")

        params = {"maxResults": 50}
        if filters and filters.get("state"):
            params["state"] = filters["state"]
        if cursor and cursor.cursor:
            params["startAt"] = cursor.cursor

        async for sprint in self._paginated_get(f"board/{board_id}/sprint", params):
            yield {
                "type": "sprint",
                "id": str(sprint["id"]),
                "data": sprint,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_versions(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        project_id = filters.get("project_id") if filters else None
        if not project_id:
            raise ValueError("project_id filter required")

        params = {"maxResults": 50}
        if cursor and cursor.cursor:
            params["startAt"] = cursor.cursor

        async for version in self._paginated_get(f"project/{project_id}/versions", params):
            yield {
                "type": "version",
                "id": str(version["id"]),
                "data": version,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_components(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        project_id = filters.get("project_id") if filters else None
        if not project_id:
            raise ValueError("project_id filter required")

        async for component in self._paginated_get(f"project/{project_id}/components", {}):
            yield {
                "type": "component",
                "id": str(component["id"]),
                "data": component,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"maxResults": 100}
        if filters and filters.get("query"):
            params["query"] = filters["query"]
        if cursor and cursor.cursor:
            params["startAt"] = cursor.cursor

        async for user in self._paginated_get("user/search", params):
            yield {
                "type": "user",
                "id": user["accountId"],
                "data": user,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._auth_header:
            headers["Authorization"] = self._auth_header
        elif self._token_manager:
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
            "create_issue": self._create_issue,
            "update_issue": self._update_issue,
            "transition_issue": self._transition_issue,
            "delete_issue": self._delete_issue,
            "add_comment": self._add_comment,
            "add_worklog": self._add_worklog,
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

    async def _create_issue(self, issue_data: Dict[str, Any]):
        payload = {
            "fields": {
                "project": {"key": issue_data.get("project_key")},
                "summary": issue_data.get("summary"),
                "description": issue_data.get("description", {"type": "doc", "version": 1, "content": []}),
                "issuetype": {"name": issue_data.get("issue_type", "Task")},
            }
            if issue_data.get("priority"):
                payload["fields"]["priority"] = {"name": issue_data["priority"]}
            if issue_data.get("assignee"):
                payload["fields"]["assignee"] = {"accountId": issue_data["assignee"]}
            if issue_data.get("labels"):
                payload["fields"]["labels"] = issue_data["labels"]
            if issue_data.get("components"):
                payload["fields"]["components"] = [{"name": c} for c in issue_data["components"]]
            if issue_data.get("fixVersions"):
                payload["fields"]["fixVersions"] = [{"name": v} for v in issue_data["fixVersions"]]

        url = urljoin(self.base_url, "/rest/api/3/issue")
        headers = await self._get_headers()
        async with self.session.post(url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_issue(self, issue_data: Dict[str, Any]):
        issue_id = issue_data.get("issue_id") or issue_data.get("key")
        payload = {"fields": {}}
        if issue_data.get("summary"):
            payload["fields"]["summary"] = issue_data["summary"]
        if issue_data.get("description"):
            payload["fields"]["description"] = issue_data["description"]
        if issue_data.get("priority"):
            payload["fields"]["priority"] = {"name": issue_data["priority"]}
        if issue_data.get("assignee"):
            payload["fields"]["assignee"] = {"accountId": issue_data["assignee"]}
        if issue_data.get("labels"):
            payload["fields"]["labels"] = issue_data["labels"]

        url = urljoin(self.base_url, f"/rest/api/3/issue/{issue_id}")
        headers = await self._get_headers()
        async with self.session.put(url, headers=headers, json=payload) as resp:
            resp.raise_for_status()

    async def _transition_issue(self, issue_data: Dict[str, Any]):
        issue_id = issue_data.get("issue_id") or issue_data.get("key")
        transition_id = issue_data.get("transition_id")
        payload = {"transition": {"id": transition_id}}
        if issue_data.get("comment"):
            payload["update"] = {"comment": [{"add": {"body": issue_data["comment"]}}]}

        url = urljoin(self.base_url, f"/rest/api/3/issue/{issue_id}/transitions")
        headers = await self._get_headers()
        async with self.session.post(url, headers=headers, json=payload) as resp:
            resp.raise_for_status()

    async def _delete_issue(self, issue_data: Dict[str, Any]):
        issue_id = issue_data.get("issue_id") or issue_data.get("key")
        url = urljoin(self.base_url, f"/rest/api/3/issue/{issue_id}")
        headers = await self._get_headers()
        async with self.session.delete(url, headers=headers) as resp:
            resp.raise_for_status()

    async def _add_comment(self, comment_data: Dict[str, Any]):
        issue_id = comment_data.get("issue_id") or comment_data.get("key")
        payload = {"body": {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": comment_data.get("body", "")}]}
        ]}}
        url = urljoin(self.base_url, f"/rest/api/3/issue/{issue_id}/comment")
        headers = await self._get_headers()
        async with self.session.post(url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _add_worklog(self, worklog_data: Dict[str, Any]):
        issue_id = worklog_data.get("issue_id") or worklog_data.get("key")
        payload = {
            "timeSpent": worklog_data.get("time_spent", "1h"),
            "started": worklog_data.get("started", datetime.utcnow().isoformat()),
            "comment": {"type": "doc", "version": 1, "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": worklog_data.get("comment", "")}]}
            ]},
        }
        url = urljoin(self.base_url, f"/rest/api/3/issue/{issue_id}/worklog")
        headers = await self._get_headers()
        async with self.session.post(url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._auth_header:
            headers["Authorization"] = self._auth_header
        elif self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def test_connection(self) -> bool:
        try:
            async with self.session.get(
                urljoin(self.base_url, "/rest/api/3/myself"),
                headers=await self._get_headers(),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Jira connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(JiraConnector, JiraConnector.CONFIG)