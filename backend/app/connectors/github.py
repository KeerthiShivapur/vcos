"""
GitHub Connector for VCOS.

Provides integration with GitHub for repositories, issues, pull requests,
workflows, and organization management.
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


class GitHubConnector(BaseConnector):
    """GitHub Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="github",
        display_name="GitHub",
        description="Code hosting and version control platform",
        category="devops",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "personal_access_token": {"type": "string", "description": "Classic PAT or fine-grained PAT"},
                "app_id": {"type": "string", "description": "GitHub App ID"},
                "private_key": {"type": "string", "description": "GitHub App private key"},
                "installation_id": {"type": "string", "description": "GitHub App installation ID"},
            },
            "required": [],
            "oneOf": [
                {"required": ["personal_access_token"]},
                {"required": ["client_id", "client_secret", "redirect_uri"]},
                {"required": ["app_id", "private_key", "installation_id"]},
            ],
        },
        required_scopes=[
            "repo",
            "user",
            "read:org",
            "read:user",
            "workflow",
            "admin:repo_hook",
            "admin:org_hook",
        ],
        supported_operations=[
            "list_repos",
            "get_repo",
            "create_repo",
            "update_repo",
            "delete_repo",
            "list_issues",
            "get_issue",
            "create_issue",
            "update_issue",
            "list_pull_requests",
            "get_pull_request",
            "create_pull_request",
            "update_pull_request",
            "merge_pull_request",
            "list_commits",
            "get_commit",
            "list_workflows",
            "get_workflow",
            "trigger_workflow",
            "list_workflow_runs",
            "list_releases",
            "create_release",
            "list_webhooks",
            "create_webhook",
            "delete_webhook",
            "list_organization_members",
            "list_teams",
            "list_team_members",
        ],
        webhook_events=[
            "push",
            "pull_request",
            "pull_request_review",
            "issues",
            "issue_comment",
            "release",
            "workflow_run",
            "workflow_job",
            "check_run",
            "check_suite",
            "create",
            "delete",
            "deployment",
            "deployment_status",
            "fork",
            "gollum",
            "label",
            "member",
            "membership",
            "milestone",
            "organization",
            "package",
            "page_build",
            "project",
            "project_card",
            "project_column",
            "public",
            "pull_request_review_comment",
            "push",
            "repository",
            "repository_dispatch",
            "secret_scanning_alert",
            "security_advisory",
            "star",
            "status",
            "team",
            "team_add",
            "watch",
            "workflow_dispatch",
            "workflow_run",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_hour=5000,
            burst=20,
        ),
    )

    BASE_URL = "https://api.github.com"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    GRAPHQL_URL = "https://api.github.com/graphql"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.pat = connection_config.get("personal_access_token")
        self.client_id = connection_config.get("client_id")
        self.client_secret = connection_config.get("client_secret")
        self.app_id = connection_config.get("app_id")
        self.private_key = connection_config.get("private_key")
        self.installation_id = connection_config.get("installation_id")
        self._token_manager = None
        self._installation_token = None
        self._installation_token_expires = None

    async def authenticate(self) -> bool:
        """Authenticate with GitHub using PAT, OAuth2, or GitHub App."""
        if self.pat:
            self._authenticated = True
            logger.info("GitHub authenticated with Personal Access Token")
            return True

        if self.app_id and self.private_key and self.installation_id:
            await self._authenticate_app()
            return True

        if self.client_id and self.client_secret:
            from app.connectors.base import TokenManager
            self._token_manager = TokenManager(
                self.client_id,
                self.client_secret,
                self.TOKEN_URL,
            )
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info("GitHub authenticated with OAuth2")
            return True

        raise ValueError("GitHub requires PAT, GitHub App, or OAuth2 credentials")

    async def _authenticate_app(self):
        """Authenticate as GitHub App installation."""
        import jwt
        import time

        # Create JWT for GitHub App
        now = int(time.time())
        payload = {
            "iat": now,
            "exp": now + (10 * 60),
            "iss": self.app_id,
        }
        jwt_token = jwt.encode(payload, self.private_key, algorithm="RS256")

        # Get installation token
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        url = f"{self.BASE_URL}/app/installations/{self.installation_id}/access_tokens"
        async with self.session.post(url, headers={"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github.v3+json"}) as resp:
            resp.raise_for_status()
            data = await resp.json()
            self._installation_token = data["token"]
            self._installation_token_expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            self._authenticated = True
            logger.info("GitHub authenticated as App installation")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if self.pat:
            headers["Authorization"] = f"Bearer {self.pat}"
        elif self._installation_token and datetime.utcnow() < self._installation_token_expires - timedelta(minutes=5):
            headers["Authorization"] = f"Bearer {self._installation_token}"
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
            "list_repos": self._list_repos,
            "list_issues": self._list_issues,
            "list_pull_requests": self._list_pull_requests,
            "list_commits": self._list_commits,
            "list_workflows": self._list_workflows,
            "list_workflow_runs": self._list_workflow_runs,
            "list_releases": self._list_releases,
            "list_organization_members": self._list_org_members,
            "list_teams": self._list_teams,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _paginated_get(self, endpoint: str, params: Dict[str, Any] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle GitHub pagination."""
        url = urljoin(self.BASE_URL, endpoint)
        params = params or {}
        params.setdefault("per_page", 100)

        while url:
            headers = await self._get_headers()
            async with self.session.get(url, headers=headers, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for item in data if isinstance(data, list) else [data]:
                    yield item

                # Handle pagination
                link_header = resp.headers.get("Link", "")
                url = self._parse_next_link(link_header)
                params = {}  # URL already has params

    async def _list_repos(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        org = filters.get("org") if filters else None
        if org:
            url = f"orgs/{org}/repos"
        else:
            url = "user/repos"

        params = {"per_page": 100, "sort": "updated", "direction": "desc"}
        if filters and filters.get("type"):
            params["type"] = filters["type"]

        async for repo in self._paginated_get(url, params):
            yield {
                "type": "repository",
                "id": str(repo["id"]),
                "data": repo,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_issues(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        repo = filters.get("repo")
        org = filters.get("org")
        if not repo:
            raise ValueError("repo filter required for list_issues")

        owner = org or filters.get("owner", "user")
        url = f"repos/{owner}/{repo}/issues"
        params = {
            "state": filters.get("state", "all"),
            "per_page": 100,
            "sort": "updated",
            "direction": "desc",
        }
        if filters and filters.get("since"):
            params["since"] = filters["since"]
        if filters and filters.get("labels"):
            params["labels"] = ",".join(filters["labels"])

        async for issue in self._paginated_get(url, params):
            # Skip pull requests (they appear as issues too)
            if "pull_request" not in issue:
                yield {
                    "type": "issue",
                    "id": str(issue["id"]),
                    "data": issue,
                    "synced_at": datetime.utcnow().isoformat(),
                }

    async def _list_pull_requests(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        repo = filters.get("repo")
        org = filters.get("org")
        if not repo:
            raise ValueError("repo filter required")

        owner = org or filters.get("owner", "user")
        url = f"repos/{owner}/{repo}/pulls"
        params = {
            "state": filters.get("state", "all"),
            "per_page": 100,
            "sort": "updated",
            "direction": "desc",
        }

        async for pr in self._paginated_get(url, params):
            yield {
                "type": "pull_request",
                "id": str(pr["id"]),
                "data": pr,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_commits(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        repo = filters.get("repo")
        org = filters.get("org")
        if not repo:
            raise ValueError("repo filter required")

        owner = org or filters.get("owner", "user")
        url = f"repos/{owner}/{repo}/commits"
        params = {"per_page": 100}
        if filters and filters.get("since"):
            params["since"] = filters["since"]
        if filters and filters.get("until"):
            params["until"] = filters["until"]

        async for commit in self._paginated_get(url, params):
            yield {
                "type": "commit",
                "id": commit["sha"],
                "data": commit,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_workflows(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        repo = filters.get("repo")
        org = filters.get("org")
        if not repo:
            raise ValueError("repo filter required")

        owner = org or filters.get("owner", "user")
        url = f"repos/{owner}/{repo}/actions/workflows"

        async for workflow in self._paginated_get(url, {"per_page": 100}):
            yield {
                "type": "workflow",
                "id": str(workflow["id"]),
                "data": workflow,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_workflow_runs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        repo = filters.get("repo")
        org = filters.get("org")
        if not repo:
            raise ValueError("repo filter required")

        owner = org or filters.get("owner", "user")
        url = f"repos/{owner}/{repo}/actions/runs"
        params = {"per_page": 100}
        if filters and filters.get("workflow_id"):
            params["workflow_id"] = filters["workflow_id"]
        if filters and filters.get("status"):
            params["status"] = filters["status"]

        async for run in self._paginated_get(url, params):
            yield {
                "type": "workflow_run",
                "id": str(run["id"]),
                "data": run,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_releases(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        repo = filters.get("repo")
        org = filters.get("org")
        if not repo:
            raise ValueError("repo filter required")

        owner = org or filters.get("owner", "user")
        url = f"repos/{owner}/{repo}/releases"

        async for release in self._paginated_get(url, {"per_page": 100}):
            yield {
                "type": "release",
                "id": str(release["id"]),
                "data": release,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_org_members(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        org = filters.get("org")
        if not org:
            raise ValueError("org filter required")

        url = f"orgs/{org}/members"
        params = {"per_page": 100}

        async for member in self._paginated_get(url, params):
            yield {
                "type": "member",
                "id": str(member["id"]),
                "data": member,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_teams(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        org = filters.get("org")
        if not org:
            raise ValueError("org filter required")

        url = f"orgs/{org}/teams"
        params = {"per_page": 100}

        async for team in self._paginated_get(url, params):
            yield {
                "type": "team",
                "id": str(team["id"]),
                "data": team,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.pat:
            headers["Authorization"] = f"Bearer {self.pat}"
        elif self._installation_token:
            headers["Authorization"] = f"Bearer {self._installation_token}"
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
            "create_repo": self._create_repo,
            "update_repo": self._update_repo,
            "delete_repo": self._delete_repo,
            "create_issue": self._create_issue,
            "update_issue": self._update_issue,
            "create_pull_request": self._create_pull_request,
            "update_pull_request": self._update_pull_request,
            "merge_pull_request": self._merge_pull_request,
            "create_release": self._create_release,
            "create_webhook": self._create_webhook,
            "delete_webhook": self._delete_webhook,
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

    async def _create_repo(self, repo_data: Dict[str, Any]):
        org = repo_data.get("org")
        payload = {
            "name": repo_data.get("name"),
            "description": repo_data.get("description", ""),
            "private": repo_data.get("private", False),
            "auto_init": repo_data.get("auto_init", False),
            "gitignore_template": repo_data.get("gitignore_template"),
            "license_template": repo_data.get("license_template"),
        }
        if org:
            url = f"orgs/{org}/repos"
        else:
            url = "user/repos"
        await self._make_request("POST", url, json=payload)

    async def _update_repo(self, repo_data: Dict[str, Any]):
        owner = repo_data.get("owner") or "user"
        repo = repo_data.get("repo")
        payload = {k: v for k, v in repo_data.items() if k not in ["owner", "repo"]}
        await self._make_request("PATCH", f"repos/{owner}/{repo}", json=payload)

    async def _delete_repo(self, repo_data: Dict[str, Any]):
        owner = repo_data.get("owner")
        repo = repo_data.get("repo")
        await self._make_request("DELETE", f"repos/{owner}/{repo}")

    async def _create_issue(self, issue_data: Dict[str, Any]):
        owner = issue_data.get("owner")
        repo = issue_data.get("repo")
        payload = {
            "title": issue_data.get("title"),
            "body": issue_data.get("body", ""),
            "assignees": issue_data.get("assignees", []),
            "labels": issue_data.get("labels", []),
            "milestone": issue_data.get("milestone"),
        }
        await self._make_request("POST", f"repos/{owner}/{repo}/issues", json=payload)

    async def _update_issue(self, issue_data: Dict[str, Any]):
        owner = issue_data.get("owner")
        repo = issue_data.get("repo")
        issue_number = issue_data.get("number")
        payload = {k: v for k, v in issue_data.items() if k not in ["owner", "repo", "number"]}
        await self._make_request("PATCH", f"repos/{owner}/{repo}/issues/{issue_number}", json=payload)

    async def _create_pull_request(self, pr_data: Dict[str, Any]):
        owner = pr_data.get("owner")
        repo = pr_data.get("repo")
        payload = {
            "title": pr_data.get("title"),
            "head": pr_data.get("head"),
            "base": pr_data.get("base"),
            "body": pr_data.get("body", ""),
            "draft": pr_data.get("draft", False),
        }
        await self._make_request("POST", f"repos/{owner}/{repo}/pulls", json=payload)

    async def _update_pull_request(self, pr_data: Dict[str, Any]):
        owner = pr_data.get("owner")
        repo = pr_data.get("repo")
        number = pr_data.get("number")
        payload = {k: v for k, v in pr_data.items() if k not in ["owner", "repo", "number"]}
        await self._make_request("PATCH", f"repos/{owner}/{repo}/pulls/{number}", json=payload)

    async def _merge_pull_request(self, pr_data: Dict[str, Any]):
        owner = pr_data.get("owner")
        repo = pr_data.get("repo")
        number = pr_data.get("number")
        payload = {
            "commit_title": pr_data.get("commit_title"),
            "commit_message": pr_data.get("commit_message"),
            "merge_method": pr_data.get("merge_method", "merge"),
        }
        await self._make_request("PUT", f"repos/{owner}/{repo}/pulls/{number}/merge", json=payload)

    async def _create_release(self, release_data: Dict[str, Any]):
        owner = release_data.get("owner")
        repo = release_data.get("repo")
        payload = {
            "tag_name": release_data.get("tag_name"),
            "target_commitish": release_data.get("target_commitish", "main"),
            "name": release_data.get("name"),
            "body": release_data.get("body", ""),
            "draft": release_data.get("draft", False),
            "prerelease": release_data.get("prerelease", False),
        }
        await self._make_request("POST", f"repos/{owner}/{repo}/releases", json=payload)

    async def _create_webhook(self, webhook_data: Dict[str, Any]):
        owner = webhook_data.get("owner")
        repo = webhook_data.get("repo")
        payload = {
            "name": "web",
            "active": True,
            "events": webhook_data.get("events", ["push", "pull_request"]),
            "config": {
                "url": webhook_data.get("url"),
                "content_type": "json",
                "secret": webhook_data.get("secret"),
                "insecure_ssl": "0",
            },
        }
        await self._make_request("POST", f"repos/{owner}/{repo}/hooks", json=payload)

    async def _delete_webhook(self, webhook_data: Dict[str, Any]):
        owner = webhook_data.get("owner")
        repo = webhook_data.get("repo")
        hook_id = webhook_data.get("hook_id")
        await self._make_request("DELETE", f"repos/{owner}/{repo}/hooks/{hook_id}")

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.BASE_URL, endpoint)
        headers = await self._get_headers()

        await self.rate_limiter.acquire()

        async def _request():
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
                    reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
                    wait = max(reset - int(time.time()), 0) + 1
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=403,
                        message=f"Rate limited, reset in {wait}s"
                    )
                resp.raise_for_status()
                return await resp.json() if resp.content_type == "application/json" else {}

        return await self.retry_policy.execute(_request)

    async def test_connection(self) -> bool:
        try:
            async with self.session.get(
                f"{self.BASE_URL}/user",
                headers=await self._get_headers(),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"GitHub connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(GitHubConnector, GitHubConnector.CONFIG)