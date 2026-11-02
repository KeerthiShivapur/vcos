"""
Linear Connector for VCOS.

Provides integration with Linear for issue tracking and project management
using GraphQL API.
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


class LinearConnector(BaseConnector):
    """Linear Connector Implementation using GraphQL API."""

    CONFIG = ConnectorConfig(
        name="linear",
        display_name="Linear",
        description="Issue tracking and project management for software teams",
        category="project_mgmt",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "Linear API key"},
            },
            "required": ["api_key"],
        },
        required_scopes=[],
        supported_operations=[
            "list_users",
            "get_user",
            "list_teams",
            "get_team",
            "list_issues",
            "get_issue",
            "create_issue",
            "update_issue",
            "delete_issue",
            "list_projects",
            "get_project",
            "create_project",
            "update_project",
            "list_cycles",
            "get_cycle",
            "create_cycle",
            "list_labels",
            "create_label",
            "list_comments",
            "create_comment",
            "list_issue_relations",
            "create_issue_relation",
            "list_webhooks",
            "create_webhook",
        ],
        webhook_events=[
            "IssueCreated",
            "IssueUpdated",
            "IssueDeleted",
            "IssueArchived",
            "IssueUnarchived",
            "CommentCreated",
            "CommentUpdated",
            "CommentDeleted",
            "IssueRelationCreated",
            "IssueRelationDeleted",
            "LabelCreated",
            "LabelUpdated",
            "LabelDeleted",
            "CycleCreated",
            "CycleUpdated",
            "CycleDeleted",
            "ProjectCreated",
            "ProjectUpdated",
            "ProjectDeleted",
            "TeamCreated",
            "TeamUpdated",
            "UserCreated",
            "UserUpdated",
        ],
        rate_limits=RateLimitConfig(
            requests_per_minute=300,
            complexity={"points_per_minute": 1000},
        ),
    )

    BASE_URL = "https://api.linear.app/graphql"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.api_key = connection_config.get("api_key")

    async def authenticate(self) -> bool:
        """Authenticate with Linear using API key."""
        if not self.api_key:
            raise ValueError("Linear requires api_key")

        # Test the API key
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }
        query = "{ viewer { id name email } }"
        async with self.session.post(
            self.BASE_URL,
            headers=headers,
            json={"query": query},
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if "errors" not in data:
                    self._authenticated = True
                    logger.info("Linear authenticated with API key")
                    return True
            return False

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

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
            "list_teams": self._list_teams,
            "list_issues": self._list_issues,
            "list_projects": self._list_projects,
            "list_cycles": self._list_cycles,
            "list_labels": self._list_labels,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _graphql_query(self, query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        headers = {"Authorization": self.api_key, "Content-Type": "application/json"}
        payload = {"query": query, "variables": variables or {}}
        async with self.session.post(self.BASE_URL, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            if "errors" in data:
                raise Exception(f"GraphQL errors: {data['errors']}")
            return data.get("data", {})

    async def _paginated_query(self, query: str, variables: Dict[str, Any] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle Linear's cursor-based pagination."""
        vars_ = variables or {}
        vars_.setdefault("first", 100)

        while True:
            data = await self._graphql_query(query, vars_)
            # Extract nodes from the connection
            for key, value in data.items():
                if isinstance(value, dict) and "nodes" in value:
                    for node in value["nodes"]:
                        yield node
                    page_info = value.get("pageInfo", {})
                    if page_info.get("hasNextPage"):
                        vars_["after"] = page_info["endCursor"]
                        break
                    else:
                        return

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query Users($first: Int!, $after: String) {
            users(first: $first, after: $after) {
                nodes {
                    id
                    name
                    email
                    displayName
                    active
                    createdAt
                    updatedAt
                    avatarUrl
                    timezone
                    role
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        vars_ = {"first": 100}
        if cursor and cursor.cursor:
            vars_["after"] = cursor.cursor

        async for user in self._paginated_query(query, vars_):
            yield {
                "type": "user",
                "id": user["id"],
                "data": user,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_teams(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query Teams($first: Int!, $after: String) {
            teams(first: $first, after: $after) {
                nodes {
                    id
                    name
                    key
                    description
                    private
                    createdAt
                    updatedAt
                    memberCount
                    defaultIssueState {
                        id
                        name
                        type
                    }
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        vars_ = {"first": 100}
        if cursor and cursor.cursor:
            vars_["after"] = cursor.cursor

        async for team in self._paginated_query(query, vars_):
            yield {
                "type": "team",
                "id": team["id"],
                "data": team,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_issues(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query Issues($first: Int!, $after: String, $filter: IssueFilter) {
            issues(first: $first, after: $after, filter: $filter) {
                nodes {
                    id
                    identifier
                    title
                    description
                    priority
                    estimate
                    state {
                        id
                        name
                        type
                        color
                    }
                    assignee {
                        id
                        name
                        email
                    }
                    creator {
                        id
                        name
                        email
                    }
                    project {
                        id
                        name
                    }
                    team {
                        id
                        name
                        key
                    }
                    labels {
                        nodes {
                            id
                            name
                            color
                        }
                    }
                    cycle {
                        id
                        name
                        number
                    }
                    createdAt
                    updatedAt
                    completedAt
                    dueDate
                    startedAt
                    snoozedUntilAt
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        vars_ = {"first": 100}
        if cursor and cursor.cursor:
            vars_["after"] = cursor.cursor

        filter_dict = {}
        if filters:
            if filters.get("team_id"):
                filter_dict["team"] = {"id": {"eq": filters["team_id"]}}
            if filters.get("project_id"):
                filter_dict["project"] = {"id": {"eq": filters["project_id"]}}
            if filters.get("assignee_id"):
                filter_dict["assignee"] = {"id": {"eq": filters["assignee_id"]}}
            if filters.get("state_id"):
                filter_dict["state"] = {"id": {"eq": filters["state_id"]}}
            if filters.get("label_ids"):
                filter_dict["labels"] = {"some": {"id": {"in": filters["label_ids"]}}}
            if filters.get("since"):
                filter_dict["updatedAt"] = {"gte": filters["since"]}

        if filter_dict:
            vars_["filter"] = filter_dict

        async for issue in self._paginated_query(query, vars_):
            yield {
                "type": "issue",
                "id": issue["id"],
                "data": issue,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_projects(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query Projects($first: Int!, $after: String, $filter: ProjectFilter) {
            projects(first: $first, after: $after, filter: $filter) {
                nodes {
                    id
                    name
                    description
                    icon
                    color
                    state
                    startDate
                    targetDate
                    completedAt
                    createdAt
                    updatedAt
                    progress
                    lead {
                        id
                        name
                    }
                    teams {
                        nodes {
                            id
                            name
                            key
                        }
                    }
                    issueCount
                    completedIssueCount
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        vars_ = {"first": 100}
        if cursor and cursor.cursor:
            vars_["after"] = cursor.cursor
        if filters and filters.get("team_id"):
            vars_["filter"] = {"team": {"id": {"eq": filters["team_id"]}}}

        async for project in self._paginated_query(query, vars_):
            yield {
                "type": "project",
                "id": project["id"],
                "data": project,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_cycles(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query Cycles($first: Int!, $after: String, $filter: CycleFilter) {
            cycles(first: $first, after: $after, filter: $filter) {
                nodes {
                    id
                    name
                    number
                    startsAt
                    endsAt
                    completedAt
                    createdAt
                    completedIssueCount
                    inProgressIssueCount
                    scopeIssueCount
                    team {
                        id
                        name
                        key
                    }
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        vars_ = {"first": 50}
        if cursor and cursor.cursor:
            vars_["after"] = cursor.cursor
        if filters and filters.get("team_id"):
            vars_["filter"] = {"team": {"id": {"eq": filters["team_id"]}}}

        async for cycle in self._paginated_query(query, vars_):
            yield {
                "type": "cycle",
                "id": cycle["id"],
                "data": cycle,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_labels(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = """
        query IssueLabels($first: Int!, $after: String) {
            issueLabels(first: $first, after: $after) {
                nodes {
                    id
                    name
                    color
                    description
                    createdAt
                    updatedAt
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        vars_ = {"first": 100}
        if cursor and cursor.cursor:
            vars_["after"] = cursor.cursor

        async for label in self._paginated_query(query, vars_):
            yield {
                "type": "label",
                "id": label["id"],
                "data": label,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_issue": self._create_issue,
            "update_issue": self._update_issue,
            "delete_issue": self._delete_issue,
            "create_project": self._create_project,
            "update_project": self._update_project,
            "create_cycle": self._create_cycle,
            "create_label": self._create_label,
            "create_comment": self._create_comment,
            "create_issue_relation": self._create_issue_relation,
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

    async def _execute_mutation(self, mutation: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        data = await self._graphql_query(mutation, variables)
        return data

    async def _create_issue(self, issue_data: Dict[str, Any]):
        mutation = """
        mutation IssueCreate($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                }
            }
        }
        """
        variables = {
            "input": {
                "title": issue_data.get("title"),
                "description": issue_data.get("description"),
                "teamId": issue_data.get("team_id"),
                "projectId": issue_data.get("project_id"),
                "labelIds": issue_data.get("label_ids", []),
                "priority": issue_data.get("priority", 0),
                "estimate": issue_data.get("estimate"),
                "dueDate": issue_data.get("due_date"),
                "stateId": issue_data.get("state_id"),
            }
        }
        await self._execute_mutation(mutation, variables)

    async def _update_issue(self, issue_data: Dict[str, Any]):
        mutation = """
        mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    title
                }
            }
        }
        """
        variables = {
            "id": issue_data.get("id"),
            "input": {k: v for k, v in issue_data.items() if k != "id"},
        }
        await self._execute_mutation(mutation, variables)

    async def _delete_issue(self, issue_data: Dict[str, Any]):
        mutation = """
        mutation IssueDelete($id: String!) {
            issueDelete(id: $id) {
                success
            }
        }
        """
        variables = {"id": issue_data.get("id")}
        await self._execute_mutation(mutation, variables)

    async def _create_project(self, project_data: Dict[str, Any]):
        mutation = """
        mutation ProjectCreate($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project {
                    id
                    name
                }
            }
        }
        """
        variables = {
            "input": {
                "name": project_data.get("name"),
                "description": project_data.get("description"),
                "icon": project_data.get("icon"),
                "color": project_data.get("color"),
                "teams": project_data.get("team_ids", []),
            }
        }
        await self._execute_mutation(mutation, variables)

    async def _update_project(self, project_data: Dict[str, Any]):
        mutation = """
        mutation ProjectUpdate($id: String!, $input: ProjectUpdateInput!) {
            projectUpdate(id: $id, input: $input) {
                success
                project {
                    id
                    name
                }
            }
        }
        """
        variables = {
            "id": project_data.get("id"),
            "input": {k: v for k, v in project_data.items() if k != "id"},
        }
        await self._execute_mutation(mutation, variables)

    async def _create_cycle(self, cycle_data: Dict[str, Any]):
        mutation = """
        mutation CycleCreate($input: CycleCreateInput!) {
            cycleCreate(input: $input) {
                success
                cycle {
                    id
                    name
                }
            }
        }
        """
        variables = {
            "input": {
                "name": cycle_data.get("name"),
                "teamId": cycle_data.get("team_id"),
                "startsAt": cycle_data.get("starts_at"),
                "endsAt": cycle_data.get("ends_at"),
            }
        }
        await self._execute_mutation(mutation, variables)

    async def _create_label(self, label_data: Dict[str, Any]):
        mutation = """
        mutation IssueLabelCreate($input: IssueLabelCreateInput!) {
            issueLabelCreate(input: $input) {
                success
                issueLabel {
                    id
                    name
                }
            }
        }
        """
        variables = {
            "input": {
                "name": label_data.get("name"),
                "color": label_data.get("color", "#6366f1"),
                "description": label_data.get("description"),
            }
        }
        await self._execute_mutation(mutation, variables)

    async def _create_comment(self, comment_data: Dict[str, Any]):
        mutation = """
        mutation CommentCreate($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                success
                comment {
                    id
                    body
                }
            }
        }
        """
        variables = {
            "input": {
                "issueId": comment_data.get("issue_id"),
                "body": comment_data.get("body"),
            }
        }
        await self._execute_mutation(mutation, variables)

    async def _create_issue_relation(self, relation_data: Dict[str, Any]):
        mutation = """
        mutation IssueRelationCreate($input: IssueRelationCreateInput!) {
            issueRelationCreate(input: $input) {
                success
                issueRelation {
                    id
                    relationType
                }
            }
        }
        """
        variables = {
            "input": {
                "sourceId": relation_data.get("source_id"),
                "targetId": relation_data.get("target_id"),
                "relationType": relation_data.get("relation_type", "relates"),
            }
        }
        await self._execute_mutation(mutation, variables)

    async def _graphql_query(self, query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        headers = {"Authorization": self.api_key, "Content-Type": "application/json"}
        payload = {"query": query, "variables": variables or {}}
        async with self.session.post(self.BASE_URL, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            if "errors" in data:
                raise Exception(f"GraphQL errors: {data['errors']}")
            return data.get("data", {})

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> bool:
        try:
            query = "{ viewer { id } }"
            await self._graphql_query(query)
            return True
        except Exception as e:
            logger.error(f"Linear connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(LinearConnector, LinearConnector.CONFIG)