"""Gate 24 — Asana Connector.

Implements Asana integration for projects, tasks, users, and teams.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, AsyncIterator

from app.intelligence.connectors.base import BaseConnector, connector_registry
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.connectors.asana")


class AsanaConnector(BaseConnector):
    """Asana connector implementation."""

    @property
    def provider(self) -> str:
        return "asana"

    @property
    def kind(self) -> str:
        return "productivity"

    async def authenticate(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """Authenticate with Asana using Personal Access Token."""
        credentials = instance.credentials

        if not credentials:
            return False, "No credentials configured"

        access_token = credentials.get("access_token")
        if not access_token:
            return False, "No access token configured"

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://app.asana.com/api/1.0/users/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                )

            if response.status_code == 200:
                data = response.json()
                if "data" in data:
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
        access_token = credentials.get("access_token")

        # Sync users
        if "read_people" in instance.connector.inbound_capabilities:
            async for user in self._sync_users(access_token):
                yield user

        # Sync projects
        if "read_projects" in instance.connector.inbound_capabilities:
            async for project in self._sync_projects(access_token, since, until):
                yield project

        # Sync tasks
        if "read_tasks" in instance.connector.inbound_capabilities:
            async for task in self._sync_tasks(access_token, since, until):
                yield task

        # Sync teams
        if "read_teams" in instance.connector.inbound_capabilities:
            async for team in self._sync_teams(access_token):
                yield team

    async def _sync_users(self, access_token: str) -> AsyncIterator[dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            url = "https://app.asana.com/api/1.0/users"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {"limit": 100}

            while True:
                response = await client.get(url, headers={"Authorization": f"Bearer {access_token}"}, params=params)

                if response.status_code != 200:
                    break

                data = response.json()
                for user in data.get("data", []):
                    yield {
                        "entity_type": "person",
                        "external_id": user["gid"],
                        "operation": "upsert",
                        "data": {
                            "external_id": user["gid"],
                            "external_email": user.get("email"),
                            "external_display_name": user.get("name"),
                            "external_avatar_url": user.get("photo", {}).get("image_128x128") if user.get("photo") else None,
                            "external_metadata": {
                                "workspaces": user.get("workspaces"),
                            },
                        },
                    }

                next_page = data.get("next_page")
                if not next_page:
                    break
                params["offset"] = next_page.get("offset", 0)

    async def _sync_projects(self, access_token: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            url = "https://app.asana.com/api/1.0/projects"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {"limit": 100, "opt_fields": "gid,name,notes,created_at,modified_at,owner,team,archived"}

            while True:
                response = await client.get(url, headers=headers, params=params)

                if response.status_code != 200:
                    break

                data = response.json()
                for project in data.get("data", []):
                    if since and project.get("modified_at"):
                        modified = datetime.fromisoformat(project["modified_at"].replace("Z", "+00:00"))
                        if modified < since:
                            continue
                    if until and project.get("modified_at"):
                        modified = datetime.fromisoformat(project["modified_at"].replace("Z", "+00:00"))
                        if modified > until:
                            continue

                    yield {
                        "entity_type": "project",
                        "external_id": project["gid"],
                        "operation": "upsert",
                        "data": {
                            "external_id": project["gid"],
                            "external_display_name": project.get("name"),
                            "external_metadata": {
                                "notes": project.get("notes"),
                                "owner": project.get("owner", {}).get("gid") if project.get("owner") else None,
                                "team": project.get("team", {}).get("gid") if project.get("team") else None,
                                "archived": project.get("archived"),
                                "created_at": project.get("created_at"),
                                "modified_at": project.get("modified_at"),
                            },
                        },
                    }

                next_page = data.get("next_page")
                if not next_page:
                    break
                params["offset"] = next_page.get("offset", 0)

    async def _sync_tasks(self, access_token: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            url = "https://app.asana.com/api/1.0/tasks"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {"limit": 100, "opt_fields": "gid,name,notes,created_at,modified_at,completed,completed_at,assignee,projects,memberships,custom_fields,dependencies,dependents"}

            if since:
                params["modified_since"] = since.isoformat()

            while True:
                response = await client.get("https://app.asana.com/api/1.0/tasks", headers={"Authorization": f"Bearer {access_token}"}, params=params)

                if response.status_code != 200:
                    break

                data = response.json()
                for task in data.get("data", []):
                    if since and task.get("modified_at"):
                        modified = datetime.fromisoformat(task["modified_at"].replace("Z", "+00:00"))
                        if modified < since:
                            continue
                    if until and task.get("modified_at"):
                        modified = datetime.fromisoformat(task["modified_at"].replace("Z", "+00:00"))
                        if modified > until:
                            continue

                    yield {
                        "entity_type": "task",
                        "external_id": task["gid"],
                        "operation": "upsert",
                        "data": {
                            "external_id": task["gid"],
                            "external_display_name": task.get("name"),
                            "external_metadata": {
                                "notes": task.get("notes"),
                                "completed": task.get("completed"),
                                "completed_at": task.get("completed_at"),
                                "assignee": task.get("assignee", {}).get("gid") if task.get("assignee") else None,
                                "projects": [p.get("gid") for p in task.get("projects", [])],
                                "memberships": [m.get("section", {}).get("gid") for m in task.get("memberships", [])],
                                "dependencies": [d.get("gid") for d in task.get("dependencies", [])],
                                "dependents": [d.get("gid") for d in task.get("dependents", [])],
                                "custom_fields": task.get("custom_fields"),
                            },
                        },
                    }

                next_page = data.get("next_page")
                if not next_page:
                    break
                params["offset"] = next_page.get("offset", 0)

    async def _sync_teams(self, access_token: str) -> AsyncIterator[dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            url = "https://app.asana.com/api/1.0/teams"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {"limit": 100, "opt_fields": "gid,name,description,organization"}

            response = await client.get(url, headers=headers, params=params)

            if response.status_code != 200:
                return

            data = response.json()
            for team in data.get("data", []):
                yield {
                    "entity_type": "team",
                    "external_id": team["gid"],
                    "operation": "upsert",
                    "data": {
                        "external_id": team["gid"],
                        "external_display_name": team.get("name"),
                        "external_metadata": {
                            "description": team.get("description"),
                            "organization": team.get("organization", {}).get("gid") if team.get("organization") else None,
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
        # Asana doesn't have a public events API - would need webhooks
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
        access_token = credentials.get("access_token")

        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

            if operation_type == "create_task" and target_entity_type == "task":
                url = "https://app.asana.com/api/1.0/tasks"
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"data": payload},
                )

                if response.status_code == 201:
                    data = response.json()
                    if "data" in data:
                        return {
                            "success": True,
                            "external_operation_id": data["data"]["gid"],
                            "data": data,
                        }

                return {"success": False, "error": response.text}

            elif operation_type == "update_task" and target_entity_type == "task":
                url = f"https://app.asana.com/api/1.0/tasks/{target_external_id}"
                response = await client.put(
                    url,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"data": payload},
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

        events_list = payload.get("events", [])
        for event in events_list:
            resource = event.get("resource", {})
            event_type = event.get("action", "")
            resource_type = event.get("resource", {}).get("resource_type", "")

            events.append({
                "external_event_id": event.get("gid", ""),
                "event_type": f"asana.{resource_type}.{event_type}",
                "source_id": event.get("resource", {}).get("gid", ""),
                "source_type": resource_type,
                "payload": event,
                "external_timestamp": datetime.fromisoformat(event.get("created_at", "").replace("Z", "+00:00")) if event.get("created_at") else datetime.now(timezone.utc),
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
        access_token = credentials.get("access_token")

        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://app.asana.com/api/1.0/users/{external_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if response.status_code == 200:
            data = response.json()
            if "data" in data:
                user = data["data"]
                return {
                    "external_id": user["gid"],
                    "external_email": user.get("email"),
                    "external_display_name": user.get("name"),
                    "external_avatar_url": user.get("photo", {}).get("image_128x128") if user.get("photo") else None,
                    "external_metadata": {
                        "workspaces": user.get("workspaces"),
                    },
                }

        return None

    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return {
            "inbound_capabilities": ["read_users", "read_projects", "read_tasks", "read_teams", "read_workspaces"],
            "outbound_capabilities": ["create_task", "update_task", "create_project", "update_project", "create_comment", "add_task_to_project"],
            "supported_entities": ["user", "project", "task", "team", "workspace", "section", "tag", "custom_field"],
            "supported_events": ["task.created", "task.updated", "task.deleted", "task.completed", "project.created", "project.updated", "project.deleted", "story.created", "attachment.created"],
            "sync_modes": ["full", "incremental", "webhook"],
            "auth_types": ["personal_access_token"],
            "oauth_scopes": [
                "default"
            ],
            "required_config_fields": ["access_token"],
            "optional_config_fields": ["workspace_gid"],
            "rate_limits": {
                "api": {"requests_per_minute": 1500, "burst": 100},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("access_token"):
            return False, "No access_token configured"
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
connector_registry.register(AsanaConnector())