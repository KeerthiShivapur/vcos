"""Gate 24 — GitHub Connector.

Implements GitHub integration for repositories, issues, pull requests, commits.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, AsyncIterator

from app.intelligence.connectors.base import BaseConnector, connector_registry
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.connectors.github")


class GitHubConnector(BaseConnector):
    """GitHub connector implementation."""
    
    @property
    def provider(self) -> str:
        return "github"
    
    @property
    def kind(self) -> str:
        return "code"
    
    async def authenticate(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """Authenticate with GitHub using OAuth2 or Personal Access Token."""
        credentials = instance.credentials
        
        if not credentials:
            return False, "No credentials configured"
        
        # Support both OAuth token and PAT
        token = credentials.get("access_token") or credentials.get("pat")
        if not token:
            return False, "No access token or PAT configured"
        
        # Test the token
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                )
            
            if response.status_code == 200:
                return True, None
            elif response.status_code == 401:
                return False, "Invalid or expired token"
            else:
                return False, f"GitHub API error: {response.status_code}"
        except Exception as e:
            return False, f"Authentication test failed: {str(e)}"
    
    async def test_connection(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """Test GitHub connection."""
        return await self.authenticate(instance)
    
    async def full_sync(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Full sync of GitHub data."""
        ok, error = await self.authenticate(instance)
        if not ok:
            raise RuntimeError(f"Authentication failed: {error}")
        
        credentials = instance.credentials
        token = credentials.get("access_token") or credentials.get("pat")
        org = instance.config.get("organization")
        
        if not org:
            raise RuntimeError("Organization not configured")
        
        # Sync repositories
        if "read_repositories" in instance.connector.inbound_capabilities:
            async for repo in self._sync_repositories(token, org):
                yield repo
        
        # Sync issues
        if "read_issues" in instance.connector.inbound_capabilities:
            async for issue in self._sync_issues(token, org, since, until):
                yield issue
        
        # Sync pull requests
        if "read_pull_requests" in instance.connector.inbound_capabilities:
            async for pr in self._sync_pull_requests(token, org, since, until):
                yield pr
        
        # Sync commits
        if "read_commits" in instance.connector.inbound_capabilities:
            async for commit in self._sync_commits(token, org, since, until):
                yield commit
    
    async def _sync_repositories(self, token: str, org: str) -> AsyncIterator[dict[str, Any]]:
        """Sync GitHub repositories."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            while True:
                response = await client.get(
                    f"https://api.github.com/orgs/{org}/repos",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                    params={"per_page": 100, "page": page, "type": "all"},
                )
                
                if response.status_code != 200:
                    break
                
                repos = response.json()
                if not repos:
                    break
                
                for repo in repos:
                    yield {
                        "entity_type": "repository",
                        "external_id": str(repo["id"]),
                        "operation": "upsert",
                        "data": {
                            "external_id": str(repo["id"]),
                            "external_display_name": repo.get("full_name"),
                            "external_metadata": {
                                "name": repo.get("name"),
                                "description": repo.get("description"),
                                "private": repo.get("private"),
                                "fork": repo.get("fork"),
                                "default_branch": repo.get("default_branch"),
                                "language": repo.get("language"),
                                "stargazers_count": repo.get("stargazers_count"),
                                "forks_count": repo.get("forks_count"),
                                "created_at": repo.get("created_at"),
                                "updated_at": repo.get("updated_at"),
                                "pushed_at": repo.get("pushed_at"),
                                "topics": repo.get("topics"),
                            },
                        },
                    }
                
                page += 1
    
    async def _sync_issues(
        self, token: str, org: str, since: Optional[datetime], until: Optional[datetime]
    ) -> AsyncIterator[dict[str, Any]]:
        """Sync GitHub issues across all repos."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            while True:
                params = {
                    "state": "all",
                    "per_page": 100,
                    "page": page,
                    "direction": "asc",
                }
                if since:
                    params["since"] = since.isoformat()
                
                response = await client.get(
                    f"https://api.github.com/orgs/{org}/issues",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                    params=params,
                )
                
                if response.status_code != 200:
                    break
                
                issues = response.json()
                if not issues:
                    break
                
                for issue in issues:
                    # Skip pull requests (they appear in issues API)
                    if "pull_request" in issue:
                        continue
                    
                    yield {
                        "entity_type": "issue",
                        "external_id": str(issue["id"]),
                        "operation": "upsert",
                        "data": {
                            "external_id": str(issue["id"]),
                            "external_display_name": issue.get("title"),
                            "external_metadata": {
                                "number": issue.get("number"),
                                "state": issue.get("state"),
                                "title": issue.get("title"),
                                "body": issue.get("body"),
                                "user": issue.get("user", {}).get("login"),
                                "assignees": [a.get("login") for a in issue.get("assignees", [])],
                                "labels": [l.get("name") for l in issue.get("labels", [])],
                                "repository": issue.get("repository_url", "").split("/")[-1],
                                "created_at": issue.get("created_at"),
                                "updated_at": issue.get("updated_at"),
                                "closed_at": issue.get("closed_at"),
                            },
                        },
                    }
                
                page += 1
    
    async def _sync_pull_requests(
        self, token: str, org: str, since: Optional[datetime], until: Optional[datetime]
    ) -> AsyncIterator[dict[str, Any]]:
        """Sync GitHub pull requests."""
        import httpx
        
        # First get all repos
        repos = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            while True:
                response = await client.get(
                    f"https://api.github.com/orgs/{org}/repos",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                    params={"per_page": 100, "page": page, "type": "all"},
                )
                
                if response.status_code != 200:
                    break
                
                repo_list = response.json()
                if not repo_list:
                    break
                
                repos.extend(repo_list)
                page += 1
        
        # Sync PRs for each repo
        for repo in repos:
            repo_name = repo["name"]
            async with httpx.AsyncClient(timeout=30.0) as client:
                page = 1
                while True:
                    params = {"state": "all", "per_page": 100, "page": page, "direction": "asc"}
                    if since:
                        params["since"] = since.isoformat()
                    
                    response = await client.get(
                        f"https://api.github.com/repos/{org}/{repo_name}/pulls",
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                        params=params,
                    )
                    
                    if response.status_code != 200:
                        break
                    
                    prs = response.json()
                    if not prs:
                        break
                    
                    for pr in prs:
                        yield {
                            "entity_type": "pull_request",
                            "external_id": str(pr["id"]),
                            "operation": "upsert",
                            "data": {
                                "external_id": str(pr["id"]),
                                "external_display_name": pr.get("title"),
                                "external_metadata": {
                                    "number": pr.get("number"),
                                    "state": pr.get("state"),
                                    "title": pr.get("title"),
                                    "body": pr.get("body"),
                                    "user": pr.get("user", {}).get("login"),
                                    "assignees": [a.get("login") for a in pr.get("assignees", [])],
                                    "labels": [l.get("name") for l in pr.get("labels", [])],
                                    "head_branch": pr.get("head", {}).get("ref"),
                                    "base_branch": pr.get("base", {}).get("ref"),
                                    "repository": repo_name,
                                    "draft": pr.get("draft"),
                                    "merged": pr.get("merged"),
                                    "merged_at": pr.get("merged_at"),
                                    "created_at": pr.get("created_at"),
                                    "updated_at": pr.get("updated_at"),
                                    "closed_at": pr.get("closed_at"),
                                },
                            },
                        }
                    
                    page += 1
    
    async def _sync_commits(
        self, token: str, org: str, since: Optional[datetime], until: Optional[datetime]
    ) -> AsyncIterator[dict[str, Any]]:
        """Sync GitHub commits (limited - requires repo enumeration)."""
        # This would be very expensive for large orgs
        # For now, we don't sync commits in full sync
        return
        yield
    
    async def incremental_sync(
        self,
        instance: ConnectorInstance,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Incremental sync using since parameter."""
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
        """Poll for GitHub events (using Events API or webhooks)."""
        # GitHub provides Events API for polling
        ok, error = await self.authenticate(instance)
        if not ok:
            raise RuntimeError(f"Authentication failed: {error}")
        
        credentials = instance.credentials
        token = credentials.get("access_token") or credentials.get("pat")
        org = instance.config.get("organization")
        
        if not org:
            return
            yield
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {"per_page": 100}
            if since:
                # GitHub Events API doesn't support since directly
                pass
            
            response = await client.get(
                f"https://api.github.com/orgs/{org}/events",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                params=params,
            )
            
            if response.status_code != 200:
                return
                yield
            
            events = response.json()
            for event in events:
                yield {
                    "external_event_id": event["id"],
                    "event_type": f"github.{event['type'].lower()}",
                    "source_id": event.get("repo", {}).get("id"),
                    "source_type": "repository",
                    "payload": event,
                    "external_timestamp": datetime.fromisoformat(event["created_at"].replace("Z", "+00:00")),
                }
    
    async def execute_operation(
        self,
        instance: ConnectorInstance,
        operation_type: str,
        target_entity_type: str,
        target_external_id: Optional[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an operation on GitHub."""
        ok, error = await self.authenticate(instance)
        if not ok:
            return {"success": False, "error": error}
        
        credentials = instance.credentials
        token = credentials.get("access_token") or credentials.get("pat")
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            if operation_type == "write_issue" and target_entity_type == "issue":
                # Create or update issue
                repo = payload.get("repository")
                title = payload.get("title")
                body = payload.get("body")
                
                if not repo or not title:
                    return {"success": False, "error": "Missing repository or title"}
                
                if target_external_id:
                    # Update issue
                    response = await client.patch(
                        f"https://api.github.com/repos/{repo}/issues/{target_external_id}",
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                        json={"title": title, "body": body},
                    )
                else:
                    # Create issue
                    response = await client.post(
                        f"https://api.github.com/repos/{repo}/issues",
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                        json={"title": title, "body": body},
                    )
                
                if response.status_code in (200, 201):
                    data = response.json()
                    return {
                        "success": True,
                        "external_operation_id": str(data["id"]),
                        "data": data,
                    }
                
                return {"success": False, "error": response.text}
            
            elif operation_type == "write_pull_request" and target_entity_type == "pull_request":
                # Similar for PRs
                return {"success": False, "error": "Not implemented"}
        
        return {"success": False, "error": f"Operation {operation_type} not implemented"}
    
    async def get_webhook_events(
        self,
        instance: ConnectorInstance,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Parse GitHub webhook payload."""
        events = []
        
        event_type = payload.get("action", "unknown")
        event_name = payload.get("zen") and "ping" or "event"
        
        if "repository" in payload:
            events.append({
                "external_event_id": payload.get("delivery_id", "") or f"github_{event_type}_{datetime.now(timezone.utc).timestamp()}",
                "event_type": f"github.{payload.get('repository', {}).get('name', 'unknown')}.{event_type}",
                "source_id": str(payload.get("repository", {}).get("id", "")),
                "source_type": "repository",
                "payload": payload,
                "external_timestamp": datetime.now(timezone.utc),
            })
        
        return events
    
    async def refresh_credentials(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str], Optional[dict]]:
        """GitHub PATs don't expire, OAuth tokens do."""
        credentials = instance.credentials
        if credentials.get("pat"):
            return True, None, credentials
        
        # OAuth refresh would go here
        return True, None, credentials
    
    async def get_rate_limit_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Get GitHub API rate limit status."""
        credentials = instance.credentials
        token = credentials.get("access_token") or credentials.get("pat")
        
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.github.com/rate_limit",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                )
            
            if response.status_code == 200:
                data = response.json()
                core = data.get("resources", {}).get("core", {})
                return {
                    "remaining": core.get("remaining"),
                    "reset_at": datetime.fromtimestamp(core.get("reset", 0), timezone.utc).isoformat() if core.get("reset") else None,
                    "limit": core.get("limit"),
                }
        except Exception:
            pass
        
        return {"remaining": "unknown", "reset_at": None}
    
    async def resolve_identity(
        self,
        instance: ConnectorInstance,
        external_id: str,
    ) -> Optional[dict[str, Any]]:
        """Resolve a GitHub user ID to identity attributes."""
        ok, error = await self.authenticate(instance)
        if not ok:
            return None
        
        credentials = instance.credentials
        token = credentials.get("access_token") or credentials.get("pat")
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://api.github.com/user/{external_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
            )
        
        if response.status_code == 200:
            user = response.json()
            return {
                "external_id": str(user["id"]),
                "external_email": user.get("email"),
                "external_display_name": user.get("name") or user.get("login"),
                "external_avatar_url": user.get("avatar_url"),
                "external_metadata": {
                    "login": user.get("login"),
                    "company": user.get("company"),
                    "blog": user.get("blog"),
                    "location": user.get("location"),
                    "bio": user.get("bio"),
                },
            }
        
        return None


    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Discover and return the connector's capabilities."""
        return {
            "inbound_capabilities": ["read_repositories", "read_issues", "read_pull_requests", "read_commits", "read_actions", "read_releases"],
            "outbound_capabilities": ["create_issue", "update_issue", "create_pull_request", "merge_pull_request", "create_release", "create_deployment", "create_comment", "create_webhook"],
            "supported_entities": ["repository", "issue", "pull_request", "commit", "release", "workflow", "deployment", "environment"],
            "supported_events": ["repository.created", "repository.updated", "repository.deleted", "issue.created", "issue.updated", "issue.closed", "pull_request.created", "pull_request.updated", "pull_request.merged", "release.published", "workflow_run.completed"],
            "sync_modes": ["full", "incremental", "webhook", "polling"],
            "auth_types": ["oauth2", "pat"],
            "oauth_scopes": [
                "repo", "repo:status", "repo:public_repo", "admin:repo_hook", "read:org", "read:user", "admin:repo_hook", "admin:org_hook",
                "workflow", "admin:public_key", "admin:org", "delete_repo"
            ],
            "required_config_fields": ["organization"],
            "optional_config_fields": [],
            "rate_limits": {
                "core": {"requests_per_hour": 5000, "burst": 100},
                "search": {"requests_per_minute": 30},
                "graphql": {"points_per_hour": 5000},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("access_token") and not credentials.get("pat"):
            return False, "No access token or PAT configured"
        if not instance.config.get("organization"):
            return False, "Missing organization in config"
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
        # GitHub uses HMAC-SHA256 with webhook secret
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


# Register the connector
connector_registry.register(GitHubConnector())