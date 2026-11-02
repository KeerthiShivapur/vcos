"""Gate 24 — Jira Connector.

Implements Jira integration for projects, issues, sprints, boards.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, AsyncIterator

from app.intelligence.connectors.base import BaseConnector, connector_registry
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.connectors.jira")

class JiraConnector(BaseConnector):
    """Jira connector implementation (Cloud and Server/DC)."""
    
    @property
    def provider(self) -> str:
        return "jira"
    
    @property
    def kind(self) -> str:
        return "work_management"
    
    async def authenticate(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """Authenticate with Jira using OAuth2, API token, or Basic auth."""
        credentials = instance.credentials
        
        if not credentials:
            return False, "No credentials configured"
        
        base_url = instance.config.get("base_url") or instance.config.get("cloud_id")
        if not base_url:
            return False, "No base URL or cloud ID configured"
        
        # Support multiple auth methods
        auth_method = credentials.get("auth_method", "api_token")
        
        if auth_method == "api_token":
            email = credentials.get("email")
            api_token = credentials.get("api_token")
            if not email or not api_token:
                return False, "Email and API token required for API token auth"
            
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://api.atlassian.com/ex/jira/{base_url}/rest/api/3/myself",
                    headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json"},
                ) if "atlassian.net" in base_url else client.get(
                    f"{base_url}/rest/api/3/myself",
                    auth=(email, api_token),
                    headers={"Accept": "application/json"},
                )
            
            if response.status_code == 200:
                return True, None
            elif response.status_code == 401:
                return False, "Invalid credentials"
            else:
                return False, f"Jira API error: {response.status_code}"
        
        elif auth_method == "oauth2":
            access_token = credentials.get("access_token")
            if not access_token:
                return False, "No access token"
            
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://api.atlassian.com/ex/jira/{base_url}/rest/api/3/myself",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
            
            if response.status_code == 200:
                return True, None
            elif response.status_code == 401:
                return False, "Access token expired"
            else:
                return False, f"Jira API error: {response.status_code}"
        
        return False, f"Unsupported auth method: {auth_method}"
    
    async def test_connection(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """Test Jira connection."""
        return await self.authenticate(instance)
    
    def _get_auth_headers(self, credentials: dict, base_url: str) -> dict:
        """Get authentication headers for Jira API."""
        auth_method = credentials.get("auth_method", "api_token")
        
        if auth_method == "api_token":
            email = credentials.get("email")
            api_token = credentials.get("api_token")
            import base64
            auth_string = base64.b64encode(f"{email}:{api_token}".encode()).decode()
            return {"Authorization": f"Basic {auth_string}", "Accept": "application/json"}
        
        elif auth_method == "oauth2":
            access_token = credentials.get("access_token")
            return {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        
        return {"Accept": "application/json"}
    
    def _get_base_url(self, instance: ConnectorInstance) -> str:
        """Get the base URL for API calls."""
        base_url = instance.config.get("base_url")
        cloud_id = instance.config.get("cloud_id")
        
        if cloud_id:
            return f"https://api.atlassian.com/ex/jira/{cloud_id}"
        return base_url.rstrip("/")
    
    async def full_sync(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Full sync of Jira data."""
        ok, error = await self.authenticate(instance)
        if not ok:
            raise RuntimeError(f"Authentication failed: {error}")
        
        credentials = instance.credentials
        base_url = self._get_base_url(instance)
        headers = self._get_auth_headers(credentials, base_url)
        
        # Sync projects
        if "read_projects" in instance.connector.inbound_capabilities:
            async for project in self._sync_projects(base_url, headers):
                yield project
        
        # Sync issues
        if "read_issues" in instance.connector.inbound_capabilities:
            async for issue in self._sync_issues(base_url, headers, since, until):
                yield issue
        
        # Sync boards
        if "read_projects" in instance.connector.inbound_capabilities:
            async for board in self._sync_boards(base_url, headers):
                yield board
        
        # Sync sprints
        if "read_tasks" in instance.connector.inbound_capabilities:
            async for sprint in self._sync_sprints(base_url, headers):
                yield sprint
    
    async def _sync_projects(self, base_url: str, headers: dict) -> AsyncIterator[dict[str, Any]]:
        """Sync Jira projects."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            start_at = 0
            while True:
                response = await client.get(
                    f"{base_url}/rest/api/3/project/search",
                    headers=headers,
                    params={"startAt": start_at, "maxResults": 100},
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                projects = data.get("values", [])
                if not projects:
                    break
                
                for project in projects:
                    yield {
                        "entity_type": "project",
                        "external_id": project["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": project["id"],
                            "external_display_name": project.get("name"),
                            "external_metadata": {
                                "key": project.get("key"),
                                "description": project.get("description"),
                                "project_type_key": project.get("projectTypeKey"),
                                "lead": project.get("lead", {}).get("displayName"),
                                "url": project.get("self"),
                            },
                        },
                    }
                
                start_at += len(projects)
                if start_at >= data.get("total", 0):
                    break
    
    async def _sync_issues(
        self, base_url: str, headers: dict, since: Optional[datetime], until: Optional[datetime]
    ) -> AsyncIterator[dict[str, Any]]:
        """Sync Jira issues using JQL."""
        import httpx
        
        jql_parts = ["ORDER BY updated ASC"]
        if since:
            jql_parts.append(f"updated >= '{since.strftime('%Y-%m-%d %H:%M')}'")
        if until:
            jql_parts.append(f"updated <= '{until.strftime('%Y-%m-%d %H:%M')}'")
        
        jql = " AND ".join(jql_parts)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            start_at = 0
            while True:
                response = await client.post(
                    f"{base_url}/rest/api/3/search/jql",
                    headers=headers,
                    json={
                        "jql": jql,
                        "startAt": start_at,
                        "maxResults": 100,
                        "fields": ["summary", "description", "status", "assignee", "reporter", "priority", "issuetype", "project", "created", "updated", "resolutiondate", "labels", "components", "fixVersions", "sprint"],
                    },
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                issues = data.get("issues", [])
                if not issues:
                    break
                
                for issue in issues:
                    fields = issue.get("fields", {})
                    yield {
                        "entity_type": "issue",
                        "external_id": issue["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": issue["id"],
                            "external_display_name": fields.get("summary"),
                            "external_metadata": {
                                "key": issue.get("key"),
                                "summary": fields.get("summary"),
                                "description": fields.get("description"),
                                "status": fields.get("status", {}).get("name"),
                                "status_category": fields.get("status", {}).get("statusCategory", {}).get("name"),
                                "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
                                "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
                                "priority": fields.get("priority", {}).get("name"),
                                "issue_type": fields.get("issuetype", {}).get("name"),
                                "project": fields.get("project", {}).get("key"),
                                "labels": fields.get("labels", []),
                                "components": [c.get("name") for c in fields.get("components", [])],
                                "fix_versions": [v.get("name") for v in fields.get("fixVersions", [])],
                                "sprint": fields.get("customfield_10020"),  # Sprint field (varies)
                                "created": fields.get("created"),
                                "updated": fields.get("updated"),
                                "resolution_date": fields.get("resolutiondate"),
                            },
                        },
                    }
                
                start_at += len(issues)
                if start_at >= data.get("total", 0):
                    break
    
    async def _sync_boards(self, base_url: str, headers: dict) -> AsyncIterator[dict[str, Any]]:
        """Sync Jira boards (Agile)."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            start_at = 0
            while True:
                response = await client.get(
                    f"{base_url}/rest/agile/1.0/board",
                    headers=headers,
                    params={"startAt": start_at, "maxResults": 50},
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                boards = data.get("values", [])
                if not boards:
                    break
                
                for board in boards:
                    yield {
                        "entity_type": "project",
                        "external_id": f"board_{board['id']}",
                        "operation": "upsert",
                        "data": {
                            "external_id": f"board_{board['id']}",
                            "external_display_name": board.get("name"),
                            "external_metadata": {
                                "board_type": board.get("type"),
                                "project_key": board.get("location", {}).get("projectKey"),
                                "project_name": board.get("location", {}).get("displayName"),
                            },
                        },
                    }
                
                start_at += len(boards)
                if start_at >= data.get("total", 0):
                    break
    
    async def _sync_sprints(self, base_url: str, headers: dict) -> AsyncIterator[dict[str, Any]]:
        """Sync Jira sprints."""
        import httpx
        
        # First get boards, then sprints for each board
        async with httpx.AsyncClient(timeout=30.0) as client:
            start_at = 0
            while True:
                response = await client.get(
                    f"{base_url}/rest/agile/1.0/board",
                    headers=headers,
                    params={"startAt": start_at, "maxResults": 50},
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                boards = data.get("values", [])
                if not boards:
                    break
                
                for board in boards:
                    sprint_start = 0
                    while True:
                        sprint_response = await client.get(
                            f"{base_url}/rest/agile/1.0/board/{board['id']}/sprint",
                            headers=headers,
                            params={"startAt": sprint_start, "maxResults": 50, "state": "active,future,closed"},
                        )
                        
                        if sprint_response.status_code != 200:
                            break
                        
                        sprint_data = sprint_response.json()
                        sprints = sprint_data.get("values", [])
                        if not sprints:
                            break
                        
                        for sprint in sprints:
                            yield {
                                "entity_type": "task",
                                "external_id": f"sprint_{sprint['id']}",
                                "operation": "upsert",
                                "data": {
                                    "external_id": f"sprint_{sprint['id']}",
                                    "external_display_name": sprint.get("name"),
                                    "external_metadata": {
                                        "state": sprint.get("state"),
                                        "start_date": sprint.get("startDate"),
                                        "end_date": sprint.get("endDate"),
                                        "complete_date": sprint.get("completeDate"),
                                        "board_id": board["id"],
                                        "goal": sprint.get("goal"),
                                    },
                                },
                            }
                        
                        sprint_start += len(sprints)
                        if sprint_start >= sprint_data.get("total", 0):
                            break
                
                start_at += len(boards)
                if start_at >= data.get("total", 0):
                    break
    
    async def incremental_sync(
        self,
        instance: ConnectorInstance,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Incremental sync using updated timestamp."""
        if not since and cursor:
            try:
                since = datetime.fromisoformat(cursor)
            except ValueError:
                since = None
        
        async for entity in self.full_sync(instance, since=since):
            yield entity
    
    async def poll_events(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Poll for Jira events (using webhook is preferred)."""
        # Jira webhooks are the primary mechanism
        # Polling would use the changelog or search
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
        """Execute an operation on Jira."""
        ok, error = await self.authenticate(instance)
        if not ok:
            return {"success": False, "error": error}
        
        credentials = instance.credentials
        base_url = self._get_base_url(instance)
        headers = self._get_auth_headers(credentials, base_url)
        headers["Content-Type"] = "application/json"
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            if operation_type == "write_issue" and target_entity_type == "issue":
                if target_external_id:
                    # Update issue
                    response = await client.put(
                        f"{base_url}/rest/api/3/issue/{target_external_id}",
                        headers=headers,
                        json={"fields": payload.get("fields", {})},
                    )
                else:
                    # Create issue
                    response = await client.post(
                        f"{base_url}/rest/api/3/issue",
                        headers=headers,
                        json=payload,
                    )
                
                if response.status_code in (200, 201):
                    data = response.json()
                    return {
                        "success": True,
                        "external_operation_id": data.get("id") or data.get("key"),
                        "data": data,
                    }
                
                return {"success": False, "error": response.text}
        
        return {"success": False, "error": f"Operation {operation_type} not implemented"}
    
    async def get_webhook_events(
        self,
        instance: ConnectorInstance,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Parse Jira webhook payload."""
        events = []
        
        webhook_event = payload.get("webhookEvent", "")
        issue = payload.get("issue", {})
        
        if issue:
            events.append({
                "external_event_id": f"jira_{webhook_event}_{issue.get('id')}_{datetime.now(timezone.utc).timestamp()}",
                "event_type": f"jira.{webhook_event.lower()}",
                "source_id": issue.get("id"),
                "source_type": "issue",
                "payload": payload,
                "external_timestamp": datetime.now(timezone.utc),
            })
        
        return events
    
    async def refresh_credentials(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str], Optional[dict]]:
        """Refresh Jira credentials."""
        credentials = instance.credentials
        auth_method = credentials.get("auth_method", "api_token")
        
        if auth_method == "api_token":
            return True, None, credentials
        
        if auth_method == "oauth2":
            refresh_token = credentials.get("refresh_token")
            client_id = credentials.get("client_id")
            client_secret = credentials.get("client_secret")
            
            if not refresh_token:
                return False, "No refresh token", None
            
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://auth.atlassian.com/oauth/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            
            if response.status_code == 200:
                data = response.json()
                new_creds = credentials.copy()
                new_creds["access_token"] = data["access_token"]
                if "refresh_token" in data:
                    new_creds["refresh_token"] = data["refresh_token"]
                new_creds["expires_at"] = (datetime.now(timezone.utc) + 
                    timedelta(seconds=data.get("expires_in", 3600))).isoformat()
                return True, None, new_creds
            
            return False, f"Token refresh failed: {response.text}", None
        
        return True, None, credentials
    
    async def get_rate_limit_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Get Jira rate limit status."""
        return {"remaining": "unknown", "reset_at": None}
    
    async def resolve_identity(
        self,
        instance: ConnectorInstance,
        external_id: str,
    ) -> Optional[dict[str, Any]]:
        """Resolve a Jira user account ID to identity attributes."""
        ok, error = await self.authenticate(instance)
        if not ok:
            return None
        
        credentials = instance.credentials
        base_url = self._get_base_url(instance)
        headers = self._get_auth_headers(credentials, base_url)
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/rest/api/3/user",
                headers=headers,
                params={"accountId": external_id},
            )
        
        if response.status_code == 200:
            user = response.json()
            return {
                "external_id": user.get("accountId"),
                "external_email": user.get("emailAddress"),
                "external_display_name": user.get("displayName"),
                "external_avatar_url": user.get("avatarUrls", {}).get("48x48"),
                "external_metadata": {
                    "active": user.get("active"),
                    "time_zone": user.get("timeZone"),
                    "locale": user.get("locale"),
                },
            }
        
        return None

    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Discover and return the connector's capabilities."""
        return {
            "inbound_capabilities": ["read_issues", "read_projects", "read_users", "read_boards", "read_sprints", "read_workflows"],
            "outbound_capabilities": ["create_issue", "update_issue", "transition_issue", "create_comment", "create_sprint", "create_board", "assign_issue", "add_comment"],
            "supported_entities": ["issue", "project", "user", "board", "sprint", "workflow", "epic", "component", "version"],
            "supported_events": ["issue.created", "issue.updated", "issue.deleted", "comment.created", "sprint.started", "sprint.closed", "worklog.logged"],
            "sync_modes": ["full", "incremental", "webhook", "polling"],
            "auth_types": ["oauth2", "basic", "pat"],
            "oauth_scopes": ["read:jira-user", "read:jira-work", "write:jira-work", "manage:jira-project", "read:jira-user"],
            "required_config_fields": ["base_url", "client_id", "client_secret"],
            "optional_config_fields": [],
            "rate_limits": {
                "rest_api": {"requests_per_second": 50, "burst": 100},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("access_token") and not credentials.get("basic_auth"):
            return False, "No access token or basic auth configured"
        if not instance.config.get("base_url"):
            return False, "Missing base_url in config"
        return True, None

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return {
                "status": "unhealthy",
                "last_check": utcnow().isoformat(),
                "details": {"error": error},
                "latency_ms": 0,
            }
        return {
            "status": "healthy",
            "last_check": utcnow().isoformat(),
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
        # Jira uses a simple secret-based verification for webhooks
        # The signature is typically an HMAC-SHA256 of the payload
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

# Register the connector
connector_registry.register(JiraConnector())