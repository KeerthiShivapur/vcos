"""Gate 24 — Linear Connector.

Implements Linear integration for issues, projects, teams, and users.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, AsyncIterator

from app.intelligence.connectors.base import BaseConnector, connector_registry
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.connectors.linear")


class LinearConnector(BaseConnector):
    """Linear connector implementation."""

    @property
    def provider(self) -> str:
        return "linear"

    @property
    def kind(self) -> str:
        return "productivity"

    async def authenticate(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials

        if not credentials:
            return False, "No credentials configured"

        api_key = credentials.get("api_key")
        if not api_key:
            return False, "No API key configured"

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.linear.app/graphql",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"query": "{ viewer { id name email } }"},
                )

            if response.status_code == 200:
                data = response.json()
                if "data" in data and "viewer" in data["data"]:
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
        api_key = credentials.get("api_key")

        # Sync users
        if "read_users" in instance.connector.inbound_capabilities:
            async for user in self._sync_users(api_key):
                yield user

        # Sync teams
        if "read_teams" in instance.connector.inbound_capabilities:
            async for team in self._sync_teams(api_key):
                yield team

        # Sync issues
        if "read_issues" in instance.connector.inbound_capabilities:
            async for issue in self._sync_issues(api_key, since, until):
                yield issue

        # Sync projects
        if "read_projects" in instance.connector.inbound_capabilities:
            async for project in self._sync_projects(api_key, since, until):
                yield project

        # Sync cycles
        if "read_cycles" in instance.connector.inbound_capabilities:
            async for cycle in self._sync_cycles(api_key, since, until):
                yield cycle

    async def _sync_users(self, api_key: str) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = """
        query {
            users(first: 100) {
                nodes {
                    id
                    name
                    email
                    displayName
                    avatarUrl
                    active
                    admin
                    createdAt
                    updatedAt
                }
            }
        }
        """

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.linear.app/graphql",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"query": query},
            )

            if response.status_code != 200:
                return

            data = response.json()
            for user in data.get("data", {}).get("users", {}).get("nodes", []):
                yield {
                    "entity_type": "person",
                    "external_id": user["id"],
                    "operation": "upsert",
                    "data": {
                        "external_id": user["id"],
                        "external_email": user.get("email"),
                        "external_display_name": user.get("displayName") or user.get("name"),
                        "external_avatar_url": user.get("avatarUrl"),
                        "external_metadata": {
                            "active": user.get("active"),
                            "admin": user.get("admin"),
                            "created_at": user.get("createdAt"),
                            "updated_at": user.get("updatedAt"),
                        },
                    },
                }

    async def _sync_teams(self, api_key: str) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = """
        query {
            teams(first: 100) {
                nodes {
                    id
                    name
                    key
                    description
                    private
                    createdAt
                    updatedAt
                }
            }
        }
        """

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.linear.app/graphql",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"query": query},
            )

            if response.status_code != 200:
                return

            data = response.json()
            for team in data.get("data", {}).get("teams", {}).get("nodes", []):
                yield {
                    "entity_type": "team",
                    "external_id": team["id"],
                    "operation": "upsert",
                    "data": {
                        "external_id": team["id"],
                        "external_display_name": team.get("name"),
                        "external_metadata": {
                            "key": team.get("key"),
                            "description": team.get("description"),
                            "private": team.get("private"),
                            "created_at": team.get("createdAt"),
                            "updated_at": team.get("updatedAt"),
                        },
                    },
                }

    async def _sync_issues(self, api_key: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        filter_args = "first: 100"
        if since:
            filter_args += f', filter: {{ updatedAt: {{ gte: "{since.isoformat()}" }} }}'

        query = f"""
        query {{
            issues({filter_args}) {{
                nodes {{
                    id
                    identifier
                    title
                    description
                    state {{ id name type color }}
                    priority
                    assignee {{ id name email }}
                    team {{ id name }}
                    project {{ id name }}
                    labels {{ nodes {{ id name color }} }}
                    priorityLabel
                    estimate
                    startedAt
                    completedAt
                    createdAt
                    updatedAt
                }}
                pageInfo {{
                    hasNextPage
                    endCursor
                }}
            }}
        }}
        """

        variables = {}
        if since:
            variables["filter"] = {"updatedAt": {"gte": since.isoformat()}}
        if until:
            if "filter" not in variables:
                variables["filter"] = {}
            variables["filter"]["updatedAt"] = {"lte": until.isoformat()}

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                response = await client.post(
                    "https://api.linear.app/graphql",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"query": query, "variables": variables},
                )

                if response.status_code != 200:
                    break

                data = response.json()
                for issue in data.get("data", {}).get("issues", {}).get("nodes", []):
                    if since and issue.get("updatedAt"):
                        modified = datetime.fromisoformat(issue["updatedAt"].replace("Z", "+00:00"))
                        if modified < since:
                            continue
                    if until and issue.get("updatedAt"):
                        modified = datetime.fromisoformat(issue["updatedAt"].replace("Z", "+00:00"))
                        if modified > until:
                            continue

                    assignee = issue.get("assignee")
                    team = issue.get("team")
                    project = issue.get("project")
                    labels = [label.get("name") for label in issue.get("labels", {}).get("nodes", [])]

                    yield {
                        "entity_type": "task",
                        "external_id": issue["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": issue["id"],
                            "external_display_name": issue.get("title"),
                            "external_metadata": {
                                "identifier": issue.get("identifier"),
                                "description": issue.get("description"),
                                "state_id": issue.get("state", {}).get("id"),
                                "state_name": issue.get("state", {}).get("name"),
                                "state_type": issue.get("state", {}).get("type"),
                                "priority": issue.get("priority"),
                                "assignee_id": assignee.get("id") if assignee else None,
                                "assignee_name": assignee.get("name") if assignee else None,
                                "team_id": team.get("id") if team else None,
                                "team_name": team.get("name") if team else None,
                                "project_id": project.get("id") if project else None,
                                "project_name": project.get("name") if project else None,
                                "labels": labels,
                                "priority_label": issue.get("priorityLabel"),
                                "estimate": issue.get("estimate"),
                                "started_at": issue.get("startedAt"),
                                "completed_at": issue.get("completedAt"),
                                "created_at": issue.get("createdAt"),
                                "updated_at": issue.get("updatedAt"),
                            },
                        },
                    }

                page_info = data.get("data", {}).get("issues", {}).get("pageInfo", {})
                if not page_info.get("hasNextPage"):
                    break
                variables["after"] = page_info.get("endCursor")

    async def _sync_projects(self, api_key: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        filter_args = "first: 100"
        if since:
            filter_args += f', filter: {{ updatedAt: {{ gte: "{since.isoformat()}" }} }}'

        query = f"""
        query {{
            projects({filter_args}) {{
                nodes {{
                    id
                    name
                    description
                    icon
                    color
                    startDate
                    targetDate
                    createdAt
                    updatedAt
                    teams {{ nodes {{ id name }} }}
                    members {{ nodes {{ id name }} }}
                }}
                pageInfo {{
                    hasNextPage
                    endCursor
                }}
            }}
        }}
        """

        variables = {}
        if since:
            variables["filter"] = {"updatedAt": {"gte": since.isoformat()}}
        if until:
            if "filter" not in variables:
                variables["filter"] = {}
            variables["filter"]["updatedAt"] = {"lte": until.isoformat()}

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                response = await client.post(
                    "https://api.linear.app/graphql",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"query": query, "variables": variables},
                )

                if response.status_code != 200:
                    break

                data = response.json()
                for project in data.get("data", {}).get("projects", {}).get("nodes", []):
                    if since and project.get("updatedAt"):
                        modified = datetime.fromisoformat(project["updatedAt"].replace("Z", "+00:00"))
                        if modified < since:
                            continue
                    if until and project.get("updatedAt"):
                        modified = datetime.fromisoformat(project["updatedAt"].replace("Z", "+00:00"))
                        if modified > until:
                            continue

                    teams = [t.get("id") for t in project.get("teams", {}).get("nodes", [])]
                    members = [m.get("id") for m in project.get("members", {}).get("nodes", [])]

                    yield {
                        "entity_type": "project",
                        "external_id": project["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": project["id"],
                            "external_display_name": project.get("name"),
                            "external_metadata": {
                                "description": project.get("description"),
                                "icon": project.get("icon"),
                                "color": project.get("color"),
                                "start_date": project.get("startDate"),
                                "target_date": project.get("targetDate"),
                                "teams": teams,
                                "members": members,
                                "created_at": project.get("createdAt"),
                                "updated_at": project.get("updatedAt"),
                            },
                        },
                    }

                page_info = data.get("data", {}).get("projects", {}).get("pageInfo", {})
                if not page_info.get("hasNextPage"):
                    break
                variables["after"] = page_info.get("endCursor")

    async def _sync_cycles(self, api_key: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = """
        query {
            cycles(first: 100) {
                nodes {
                    id
                    name
                    number
                    startsAt
                    endsAt
                    createdAt
                    updatedAt
                }
            }
        }
        """

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.linear.app/graphql",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"query": query},
            )

            if response.status_code != 200:
                return

            data = response.json()
            for cycle in data.get("data", {}).get("cycles", {}).get("nodes", []):
                yield {
                    "entity_type": "cycle",
                    "external_id": cycle["id"],
                    "operation": "upsert",
                    "data": {
                        "external_id": cycle["id"],
                        "external_display_name": cycle.get("name"),
                        "external_metadata": {
                            "number": cycle.get("number"),
                            "starts_at": cycle.get("startsAt"),
                            "ends_at": cycle.get("endsAt"),
                            "created_at": cycle.get("createdAt"),
                            "updated_at": cycle.get("updatedAt"),
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
        # Linear doesn't have a public events API
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
        api_key = credentials.get("api_key")

        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

            if operation_type == "create_issue" and target_entity_type == "issue":
                query = """
                mutation ($input: IssueCreateInput!) {
                    issueCreate(input: $input) {
                        issue { id identifier }
                        success
                    }
                }
                """

                variables = {"input": payload}

                response = await client.post(
                    "https://api.linear.app/graphql",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"query": query, "variables": variables},
                )

                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and "issueCreate" in data["data"]:
                        return {
                            "success": True,
                            "external_operation_id": data["data"]["issueCreate"]["issue"]["id"],
                            "data": data,
                        }

                return {"success": False, "error": response.text}

            elif operation_type == "update_issue" and target_entity_type == "issue":
                issue_id = target_external_id
                query = """
                mutation ($id: String!, $input: IssueUpdateInput!) {
                    issueUpdate(id: $id, input: $input) {
                        issue { id }
                        success
                    }
                }
                """

                variables = {"id": issue_id, "input": payload}

                response = await client.post(
                    "https://api.linear.app/graphql",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
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

        # Linear webhook events (if configured)
        for event in payload.get("data", []):
            event_type = event.get("type", "")
            action = event.get("action", "")
            object_type = event.get("type", "")

            events.append({
                "external_event_id": event.get("id", ""),
                "event_type": f"linear.{object_type}.{action}",
                "source_id": event.get("data", {}).get("id", ""),
                "source_type": object_type.lower(),
                "payload": event,
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
        api_key = credentials.get("api_key")

        import httpx
        query = """
        query ($userId: String!) {
            user(id: $userId) {
                id
                name
                email
                displayName
                avatarUrl
                active
                admin
            }
        }
        """

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.linear.app/graphql",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"query": query, "variables": {"userId": external_id}},
            )

            if response.status_code == 200:
                data = response.json()
                user = data.get("data", {}).get("user")
                if user:
                    return {
                        "external_id": user["id"],
                        "external_email": user.get("email"),
                        "external_display_name": user.get("displayName") or user.get("name"),
                        "external_avatar_url": user.get("avatarUrl"),
                        "external_metadata": {
                            "active": user.get("active"),
                            "admin": user.get("admin"),
                        },
                    }

        return None

    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return {
            "inbound_capabilities": ["read_users", "read_teams", "read_issues", "read_projects", "read_cycles", "read_labels", "read_comments"],
            "outbound_capabilities": ["create_issue", "update_issue", "create_project", "update_project", "create_comment", "create_cycle", "update_cycle"],
            "supported_entities": ["user", "team", "issue", "project", "cycle", "label", "comment", "attachment", "milestone"],
            "supported_events": ["issue.created", "issue.updated", "issue.deleted", "comment.created", "comment.updated", "issue.moved", "cycle.created", "cycle.updated"],
            "sync_modes": ["full", "incremental", "webhook"],
            "auth_types": ["api_key"],
            "oauth_scopes": [],
            "required_config_fields": ["api_key"],
            "optional_config_fields": [],
            "rate_limits": {
                "api": {"requests_per_minute": 300, "burst": 100},
                "complexity": {"points_per_minute": 1000},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("api_key"):
            return False, "No api_key configured"
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
connector_registry.register(LinearConnector())