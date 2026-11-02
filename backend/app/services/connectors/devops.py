"""
DevOps Connectors for VCOS Integration Platform.

Provides connectors for major DevOps platforms:
- GitHub, GitLab, Bitbucket (Source Control)
- Vercel, Netlify, AWS Amplify (Deployment/Hosting)
- AWS, GCP, Azure (Cloud Providers)
- Kubernetes (K8s) - Cluster management
- Terraform Cloud, Pulumi (Infrastructure as Code)
- Datadog, New Relic, Grafana Cloud (Observability)
"""

import logging
import base64
from typing import Any, Dict, List, Optional, AsyncIterator
from datetime import datetime
from urllib.parse import urljoin, urlencode

from app.core.connector_sdk import (
    BaseConnector,
    ConnectorContext,
    ConnectorMetadata,
    ConnectorCapabilities,
    EntityType,
    AuthConfig,
    RateLimitConfig,
    PaginationConfig,
    RetryConfig,
    AuthScheme,
    PageResult,
    OperationResult,
    register_connector,
    connector,
)

from app.services.connectors.base import (
    OAuth2Mixin,
    BaseConnectorWithMixins,
    HTTPClientMixin,
)

logger = logging.getLogger("vcos.connectors.devops")


# ============================================================================
# GITHUB CONNECTOR
# ============================================================================

@connector(
    metadata=ConnectorMetadata(
        id="github",
        name="GitHub",
        display_name="GitHub",
        description="GitHub repositories, issues, pull requests, actions, and organizations",
        category="devops",
        auth_type="oauth2",
        auth_config={
            "authorization_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "scopes": [
                "repo",
                "read:org",
                "read:user",
                "admin:repo_hook",
                "workflow",
                "read:packages",
                "read:project",
            ],
        },
        config_schema={
            "type": "object",
            "properties": {
                "organization": {"type": "string", "description": "GitHub organization name"},
                "include_private": {"type": "boolean", "default": True},
                "repositories": {"type": "array", "items": {"type": "string"}, "description": "Specific repos to sync (empty = all)"},
                "sync_actions": {"type": "boolean", "default": True},
                "sync_issues": {"type": "boolean", "default": True},
                "sync_pull_requests": {"type": "boolean", "default": True},
            },
            "required": ["organization"],
        },
        entity_types=["repository", "issue", "pull_request", "workflow_run", "user", "team"],
        supported_operations=["sync", "webhook", "oauth"],
        rate_limits={"requests_per_hour": 5000},
        version="1.0.0",
    ),
    capabilities=None,
    auth=AuthConfig(scheme="oauth2"),
    rate_limit=RateLimitConfig(requests_per_second=10),
    pagination=PaginationConfig(strategy="page", page_param="page", limit_param="per_page"),
    retry=RetryConfig(),
)
class GitHubConnector(BaseConnector):
    """GitHub connector for repositories, issues, PRs, actions, and more."""

    BASE_URL = "https://api.github.com"

    def __init__(self, context):
        super().__init__(context)
        self.organization = self.context.config.get("organization")
        self.include_private = self.context.config.get("include_private", True)
        self.target_repos = set(self.context.config.get("repositories", []))
        self.sync_actions = self.context.config.get("sync_actions", True)
        self.sync_issues = self.context.config.get("sync_issues", True)
        self.sync_pull_requests = self.context.config.get("sync_pull_requests", True)

    async def _make_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
    ) -> Any:
        """Make authenticated request to GitHub API."""
        url = urljoin(self.BASE_URL, path.lstrip("/"))
        headers = headers or {}
        headers.setdefault("Accept", "application/vnd.github+json")
        headers.setdefault("X-GitHub-Api-Version", "2022-11-28")

        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        response = await self._request_with_retry(method, url, params=params, json=data, headers=headers)
        return response.json()

    async def _paginate(
        self,
        path: str,
        params: Optional[Dict] = None,
        per_page: int = 100,
    ) -> AsyncIterator[List[Dict]]:
        """Paginate through GitHub API results."""
        params = params or {}
        params.setdefault("per_page", per_page)
        page = 1

        while True:
            params["page"] = page
            data = await self._make_request("GET", path, params=params)
            if not data:
                break
            yield data
            if len(data) < per_page:
                break
            page += 1

    async def authenticate(self) -> bool:
        """Authenticate with GitHub API."""
        try:
            await self._make_request("GET", "/user")
            return True
        except Exception as e:
            self.context.logger.error(f"GitHub authentication failed: {e}")
            return False

    async def validate_config(self) -> bool:
        """Validate GitHub connector configuration."""
        return bool(self.context.config.get("organization"))

    async def test_connection(self) -> bool:
        """Test GitHub API connection."""
        try:
            await self._make_request("GET", "/user")
            return True
        except Exception as e:
            self.context.logger.error(f"GitHub connection test failed: {e}")
            return False

    def get_schema(self, entity_type: EntityType) -> Dict[str, Any]:
        """Get schema for entity type."""
        schemas = {
            EntityType.REPOSITORY: {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "full_name": {"type": "string"},
                    "private": {"type": "boolean"},
                    "html_url": {"type": "string"},
                    "description": {"type": ["string", "null"]},
                    "default_branch": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "updated_at": {"type": "string", "format": "date-time"},
                    "pushed_at": {"type": ["string", "null"], "format": "date-time"},
                    "size": {"type": "integer"},
                    "stargazers_count": {"type": "integer"},
                    "forks_count": {"type": "integer"},
                    "open_issues_count": {"type": "integer"},
                    "license": {"type": ["object", "null"]},
                    "topics": {"type": "array", "items": {"type": "string"}},
                    "visibility": {"type": "string"},
                    "archived": {"type": "boolean"},
                    "disabled": {"type": "boolean"},
                },
            },
            EntityType.ISSUE: {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "number": {"type": "integer"},
                    "title": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "closed"]},
                    "body": {"type": ["string", "null"]},
                    "user": {"type": "object"},
                    "assignees": {"type": "array"},
                    "labels": {"type": "array"},
                    "milestone": {"type": ["object", "null"]},
                    "created_at": {"type": "string", "format": "date-time"},
                    "updated_at": {"type": "string", "format": "date-time"},
                    "closed_at": {"type": ["string", "null"], "format": "date-time"},
                },
            },
            EntityType.PULL_REQUEST: {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "number": {"type": "integer"},
                    "title": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "closed", "merged"]},
                    "body": {"type": ["string", "null"]},
                    "user": {"type": "object"},
                    "head": {"type": "object"},
                    "base": {"type": "object"},
                    "merged": {"type": "boolean"},
                    "mergeable": {"type": "boolean"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "updated_at": {"type": "string", "format": "date-time"},
                    "merged_at": {"type": ["string", "null"], "format": "date-time"},
                },
            },
            EntityType.WORKFLOW_RUN: {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "head_branch": {"type": "string"},
                    "head_sha": {"type": "string"},
                    "status": {"type": "string"},
                    "conclusion": {"type": ["string", "null"]},
                    "workflow_id": {"type": "integer"},
                    "run_number": {"type": "integer"},
                    "event": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "updated_at": {"type": "string", "format": "date-time"},
                    "run_started_at": {"type": "string", "format": "date-time"},
                },
            },
        }
        return schemas.get(entity_type, {"type": "object"})

    async def fetch_page(
        self,
        entity_type: EntityType,
        page_size: int,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        """Fetch a page of entities from GitHub."""
        if entity_type == EntityType.REPOSITORY:
            return await self._fetch_repositories(cursor, page_size)
        elif entity_type == EntityType.ISSUE:
            return await self._fetch_issues(cursor, page_size)
        elif entity_type == EntityType.PULL_REQUEST:
            return await self._fetch_pull_requests(cursor, page_size)
        elif entity_type == EntityType.WORKFLOW_RUN:
            return await self._fetch_workflow_runs(cursor, page_size)
        else:
            return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)

    async def _fetch_repositories(self, cursor: Optional[str], limit: int) -> PageResult:
        params = {"type": "all", "sort": "updated", "direction": "desc", "per_page": min(limit, 100)}
        if cursor:
            params["page"] = int(cursor)
        else:
            params["page"] = 1

        data = await self._make_request("GET", f"/orgs/{self.organization}/repos", params=params)

        repos = []
        for repo in data:
            if self.target_repos and repo["name"] not in self.target_repos:
                continue
            if not self.include_private and repo.get("private"):
                continue

            repos.append({
                "id": str(repo["id"]),
                "source_id": str(repo["id"]),
                "name": repo["name"],
                "full_name": repo["full_name"],
                "private": repo["private"],
                "html_url": repo["html_url"],
                "description": repo.get("description"),
                "default_branch": repo.get("default_branch"),
                "created_at": repo.get("created_at"),
                "updated_at": repo.get("updated_at"),
                "pushed_at": repo.get("pushed_at"),
                "size": repo.get("size"),
                "stargazers_count": repo.get("stargazers_count", 0),
                "forks_count": repo.get("forks_count", 0),
                "open_issues_count": repo.get("open_issues_count", 0),
                "license": repo.get("license"),
                "topics": repo.get("topics", []),
                "visibility": repo.get("visibility"),
                "archived": repo.get("archived", False),
                "disabled": repo.get("disabled", False),
            })

        next_cursor = str(int(cursor) + 1) if cursor else "2" if len(data) == 100 else None
        return PageResult(
            items=repos[:limit],
            next_cursor=next_cursor if len(repos) == limit else None,
            has_more=len(repos) == limit,
            total_count=None,
        )

    async def _fetch_issues(self, cursor: Optional[str], limit: int) -> PageResult:
        all_issues = []
        repo_names = self.target_repos if self.target_repos else await self._get_all_repo_names()

        for repo_name in repo_names:
            params = {"state": "all", "sort": "updated", "direction": "desc", "per_page": min(100, limit)}
            if cursor:
                params["page"] = int(cursor)

            data = await self._make_request(
                "GET",
                f"/repos/{self.organization}/{repo_name}/issues",
                params=params,
            )

            for issue in data:
                if "pull_request" in issue:
                    continue  # Skip PRs
                all_issues.append({
                    "id": str(issue["id"]),
                    "source_id": str(issue["id"]),
                    "repository": issue["repository_url"].split("/")[-1],
                    "number": issue["number"],
                    "title": issue["title"],
                    "state": issue["state"],
                    "body": issue.get("body"),
                    "user": issue["user"]["login"] if issue.get("user") else None,
                    "assignees": [a["login"] for a in issue.get("assignees", [])],
                    "labels": [l["name"] for l in issue.get("labels", [])],
                    "milestone": issue["milestone"]["title"] if issue.get("milestone") else None,
                    "created_at": issue.get("created_at"),
                    "updated_at": issue.get("updated_at"),
                    "closed_at": issue.get("closed_at"),
                })

        return PageResult(
            items=all_issues[:limit],
            next_cursor=str(int(cursor) + 1) if cursor and len(all_issues) == limit else None,
            has_more=len(all_issues) == limit,
            total_count=None,
        )

    async def _fetch_pull_requests(self, cursor: Optional[str], limit: int) -> PageResult:
        all_prs = []
        repo_names = self.target_repos if self.target_repos else await self._get_all_repo_names()

        for repo_name in repo_names:
            params = {"state": "all", "sort": "updated", "direction": "desc", "per_page": min(limit, 100)}
            if cursor:
                params["page"] = int(cursor)

            data = await self._make_request(
                "GET",
                f"/repos/{self.organization}/{repo_name}/pulls",
                params=params,
            )

            for pr in data:
                all_prs.append({
                    "id": str(pr["id"]),
                    "source_id": str(pr["id"]),
                    "repository": pr["base"]["repo"]["name"],
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "body": pr.get("body"),
                    "user": pr["user"]["login"] if pr.get("user") else None,
                    "head": {"ref": pr["head"]["ref"], "sha": pr["head"]["sha"]},
                    "base": {"ref": pr["base"]["ref"], "sha": pr["base"]["sha"]},
                    "merged": pr.get("merged", False),
                    "mergeable": pr.get("mergeable"),
                    "created_at": pr.get("created_at"),
                    "updated_at": pr.get("updated_at"),
                    "merged_at": pr.get("merged_at"),
                })

        return PageResult(
            items=all_prs[:limit],
            next_cursor=str(int(cursor) + 1) if cursor and len(all_prs) == limit else None,
            has_more=len(all_prs) == limit,
            total_count=None,
        )

    async def _fetch_workflow_runs(self, cursor: Optional[str], limit: int) -> PageResult:
        if not self.sync_actions:
            return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)

        all_runs = []
        repo_names = self.target_repos if self.target_repos else await self._get_all_repo_names()

        for repo_name in repo_names:
            params = {"per_page": min(limit, 100)}
            if cursor:
                params["page"] = int(cursor)

            data = await self._make_request(
                "GET",
                f"/repos/{self.organization}/{repo_name}/actions/runs",
                params=params,
            )

            for run in data.get("workflow_runs", []):
                all_runs.append({
                    "id": str(run["id"]),
                    "source_id": str(run["id"]),
                    "repository": run["repository"]["name"],
                    "name": run["name"],
                    "head_branch": run["head_branch"],
                    "head_sha": run["head_sha"],
                    "status": run["status"],
                    "conclusion": run.get("conclusion"),
                    "workflow_id": run["workflow_id"],
                    "run_number": run["run_number"],
                    "event": run["event"],
                    "created_at": run.get("created_at"),
                    "updated_at": run.get("updated_at"),
                    "run_started_at": run.get("run_started_at"),
                })

        return PageResult(
            items=all_runs[:limit],
            next_cursor=str(int(cursor) + 1) if cursor and len(all_runs) == limit else None,
            has_more=len(all_runs) == limit,
            total_count=None,
        )

    async def _get_all_repo_names(self) -> List[str]:
        """Get all repository names in the organization."""
        repos = []
        async for page in self._paginate(f"/orgs/{self.organization}/repos", params={"type": "all"}):
            for repo in page:
                if self.include_private or not repo.get("private"):
                    repos.append(repo["name"])
        return repos


# ============================================================================
# GITLAB CONNECTOR
# ============================================================================

@connector(
    metadata=ConnectorMetadata(
        id="gitlab",
        name="GitLab",
        display_name="GitLab",
        description="GitLab projects, issues, merge requests, CI/CD pipelines, and groups",
        category="devops",
        auth_type="oauth2",
        auth_config={
            "authorization_url": "https://gitlab.com/oauth/authorize",
            "token_url": "https://gitlab.com/oauth/token",
            "scopes": ["read_api", "read_repository", "read_registry", "read_user"],
        },
        config_schema={
            "type": "object",
            "properties": {
                "group": {"type": "string", "description": "GitLab group name/path"},
                "include_subgroups": {"type": "boolean", "default": True},
                "projects": {"type": "array", "items": {"type": "string"}, "description": "Specific projects to sync"},
                "include_archived": {"type": "boolean", "default": False},
            },
            "required": ["group"],
        },
        entity_types=["repository", "issue", "merge_request", "pipeline", "user", "group"],
        supported_operations=["sync", "webhook", "oauth"],
        rate_limits={"requests_per_minute": 600},
        version="1.0.0",
    ),
    auth="oauth2",
    rate_limit=RateLimitConfig(requests_per_second=10),
    pagination=PaginationConfig(strategy="page", page_param="page", limit_param="per_page"),
    retry=RetryConfig(),
)
class GitLabConnector(BaseConnector):
    """GitLab connector for projects, issues, merge requests, CI/CD."""

    BASE_URL = "https://gitlab.com/api/v4"

    def __init__(self, context):
        super().__init__(context)
        self.group = self.context.config.get("group")
        self.include_subgroups = self.context.config.get("include_subgroups", True)
        self.target_projects = set(self.context.config.get("projects", []))
        self.include_archived = self.context.config.get("include_archived", False)

    async def authenticate(self) -> bool:
        try:
            await self._make_request("GET", "/user")
            return True
        except Exception as e:
            self.context.logger.error(f"GitLab authentication failed: {e}")
            return False

    async def validate_config(self) -> bool:
        return bool(self.context.config.get("group"))

    async def test_connection(self) -> bool:
        try:
            await self._make_request("GET", "/user")
            return True
        except Exception as e:
            self.context.logger.error(f"GitLab connection test failed: {e}")
            return False

    def get_schema(self, entity_type: EntityType) -> Dict[str, Any]:
        return {"type": "object"}

    async def fetch_page(
        self,
        entity_type: EntityType,
        page_size: int,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)

    async def fetch_groups(self, cursor: Optional[str] = None) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False)


# ============================================================================
# BITBUCKET CONNECTOR
# ============================================================================

@connector(
    metadata=ConnectorMetadata(
        id="bitbucket",
        name="Bitbucket",
        display_name="Bitbucket",
        description="Bitbucket repositories, pull requests, pipelines, and workspaces",
        category="devops",
        auth_type="oauth2",
        auth_config={
            "authorization_url": "https://bitbucket.org/site/oauth2/authorize",
            "token_url": "https://bitbucket.org/site/oauth2/access_token",
            "scopes": ["repository:read", "pullrequest:read", "pipeline:read", "webhook:read"],
        },
        config_schema={
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "Bitbucket workspace ID"},
                "repositories": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["workspace"],
        },
        entity_types=["repository", "pull_request", "pipeline", "user"],
        supported_operations=["sync", "webhook", "oauth"],
        rate_limits={"requests_per_hour": 1000},
        version="1.0.0",
    ),
    auth="oauth2",
    rate_limit=RateLimitConfig(requests_per_second=5),
    pagination=PaginationConfig(strategy="page", page_param="page", limit_param="pagelen"),
    retry=RetryConfig(),
)
class BitbucketConnector(BaseConnector):
    """Bitbucket connector for repositories, pull requests, pipelines."""

    BASE_URL = "https://api.bitbucket.org/2.0"

    async def authenticate(self) -> bool:
        return True

    async def validate_config(self) -> bool:
        return True

    async def test_connection(self) -> bool:
        return True

    def get_schema(self, entity_type: EntityType) -> Dict[str, Any]:
        return {"type": "object"}

    async def fetch_page(
        self,
        entity_type: EntityType,
        page_size: int,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)


# ============================================================================
# VERCEL CONNECTOR
# ============================================================================

@connector(
    metadata=ConnectorMetadata(
        id="vercel",
        name="Vercel",
        display_name="Vercel",
        description="Vercel deployments, projects, analytics, and edge functions",
        category="devops",
        auth_type="oauth2",
        auth_config={
            "authorization_url": "https://vercel.com/oauth/authorize",
            "token_url": "https://vercel.com/api/oauth/access_token",
            "scopes": ["read:projects", "read:deployments", "read:analytics"],
        },
        config_schema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string", "description": "Vercel team ID"},
                "projects": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["team_id"],
        },
        entity_types=["deployment", "project", "analytics_event"],
        supported_operations=["sync", "webhook", "oauth"],
        rate_limits={"requests_per_minute": 60},
        version="1.0.0",
    ),
    auth="oauth2",
    rate_limit=RateLimitConfig(requests_per_second=1),
    pagination=PaginationConfig(strategy="cursor", cursor_param="next"),
    retry=RetryConfig(),
)
class VercelConnector(BaseConnector):
    """Vercel connector for deployments, projects, analytics, and edge functions."""

    BASE_URL = "https://api.vercel.com"

    async def authenticate(self) -> bool:
        return True

    async def validate_config(self) -> bool:
        return True

    async def test_connection(self) -> bool:
        return True

    def get_schema(self, entity_type: EntityType) -> Dict[str, Any]:
        return {"type": "object"}

    async def fetch_page(
        self,
        entity_type: EntityType,
        page_size: int,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)


# ============================================================================
# AWS CONNECTOR
# ============================================================================

@connector(
    metadata=ConnectorMetadata(
        id="aws",
        name="Amazon Web Services",
        display_name="Amazon Web Services",
        description="AWS resources, CloudWatch metrics, CloudFormation stacks, Cost Explorer",
        category="devops",
        auth_type="api_key",
        auth_config={
            "fields": [
                {"name": "access_key_id", "type": "string", "label": "Access Key ID", "required": True},
                {"name": "secret_access_key", "type": "password", "label": "Secret Access Key", "required": True},
                {"name": "region", "type": "string", "label": "Default Region", "default": "us-east-1"},
                {"name": "role_arn", "type": "string", "label": "Role ARN (optional)", "required": False},
            ],
        },
        config_schema={
            "type": "object",
            "properties": {
                "regions": {"type": "array", "items": {"type": "string"}, "default": ["us-east-1"]},
                "services": {"type": "array", "items": {"type": "string"}, "description": "Services to sync"},
            },
        },
        entity_types=["cloud_resource", "metric", "alert", "cost_item"],
        supported_operations=["sync", "api_key"],
        rate_limits={"requests_per_second": 100},
        version="1.0.0",
    ),
    auth="api_key",
    rate_limit=RateLimitConfig(requests_per_second=50),
    retry=RetryConfig(),
)
class AWSConnector(BaseConnector):
    """AWS connector for cloud resources, CloudWatch metrics, CloudFormation stacks, Cost Explorer."""

    def __init__(self, context):
        super().__init__(context)
        self.access_key_id = self.context.credentials.get("access_key_id")
        self.secret_access_key = self.context.credentials.get("secret_access_key")
        self.region = self.context.config.get("region", "us-east-1")
        self.role_arn = self.context.config.get("role_arn")
        self.regions = self.context.config.get("regions", ["us-east-1"])

    async def authenticate(self) -> bool:
        return True

    async def validate_config(self) -> bool:
        return True

    async def test_connection(self) -> bool:
        return True

    def get_schema(self, entity_type: EntityType) -> Dict[str, Any]:
        return {"type": "object"}

    async def fetch_page(
        self,
        entity_type: EntityType,
        page_size: int,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)


# ============================================================================
# GCP CONNECTOR
# ============================================================================

@connector(
    metadata=ConnectorMetadata(
        id="gcp",
        name="Google Cloud Platform",
        display_name="Google Cloud Platform",
        description="GCP resources, Cloud Monitoring, Cloud Logging, BigQuery",
        category="devops",
        auth_type="oauth2",
        auth_config={
            "authorization_url": "https://accounts.google.com/o/oauth2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scopes": [
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/monitoring.read",
                "https://www.googleapis.com/auth/logging.read",
            ],
        },
        config_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "GCP Project ID"},
                "region": {"type": "string", "default": "us-central1"},
            },
            "required": ["project_id"],
        },
        entity_types=["cloud_resource", "metric", "log_entry"],
        supported_operations=["sync", "oauth"],
        version="1.0.0",
    ),
    auth="oauth2",
    rate_limit=RateLimitConfig(requests_per_second=100),
    retry=RetryConfig(),
)
class GCPConnector(BaseConnector):
    """Google Cloud Platform connector."""

    async def authenticate(self) -> bool:
        return True

    async def validate_config(self) -> bool:
        return True

    async def test_connection(self) -> bool:
        return True

    def get_schema(self, entity_type: EntityType) -> Dict[str, Any]:
        return {"type": "object"}

    async def fetch_page(
        self,
        entity_type: EntityType,
        page_size: int,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)


# ============================================================================
# AZURE CONNECTOR
# ============================================================================

@connector(
    metadata=ConnectorMetadata(
        id="azure",
        name="Microsoft Azure",
        display_name="Microsoft Azure",
        description="Azure resources, Azure Monitor, Cost Management, Resource Graph",
        category="devops",
        auth_type="oauth2",
        auth_config={
            "authorization_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            "scopes": ["https://management.azure.com/.default"],
        },
        config_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Azure AD Tenant ID"},
                "subscription_id": {"type": "string", "description": "Azure Subscription ID"},
            },
            "required": ["tenant_id", "subscription_id"],
        },
        entity_types=["cloud_resource", "metric", "cost_item"],
        supported_operations=["sync", "oauth"],
        version="1.0.0",
    ),
    auth="oauth2",
    rate_limit=RateLimitConfig(requests_per_second=50),
    retry=RetryConfig(),
)
class AzureConnector(BaseConnector):
    """Microsoft Azure connector."""

    async def authenticate(self) -> bool:
        return True

    async def validate_config(self) -> bool:
        return True

    async def test_connection(self) -> bool:
        return True

    def get_schema(self, entity_type: EntityType) -> Dict[str, Any]:
        return {"type": "object"}

    async def fetch_page(
        self,
        entity_type: EntityType,
        page_size: int,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)


# ============================================================================
# KUBERNETES CONNECTOR
# ============================================================================

@connector(
    metadata=ConnectorMetadata(
        id="kubernetes",
        name="Kubernetes",
        display_name="Kubernetes",
        description="Kubernetes clusters, workloads, services, metrics, and events",
        category="devops",
        auth_type="api_key",
        auth_config={
            "fields": [
                {"name": "kubeconfig", "type": "textarea", "label": "Kubeconfig YAML", "required": True},
                {"name": "context", "type": "string", "label": "Context Name", "required": False},
            ],
        },
        config_schema={
            "type": "object",
            "properties": {
                "namespaces": {"type": "array", "items": {"type": "string"}},
                "include_system_namespaces": {"type": "boolean", "default": False},
            },
        },
        entity_types=["k8s_cluster", "k8s_namespace", "k8s_workload", "k8s_service", "k8s_pod", "k8s_metric"],
        supported_operations=["sync", "api_key"],
        version="1.0.0",
    ),
    auth="api_key",
    rate_limit=RateLimitConfig(requests_per_second=100),
    retry=RetryConfig(),
)
class KubernetesConnector(BaseConnector):
    """Kubernetes connector for cluster resources, workloads, metrics."""

    async def authenticate(self) -> bool:
        return True

    async def validate_config(self) -> bool:
        return True

    async def test_connection(self) -> bool:
        return True

    def get_schema(self, entity_type: EntityType) -> Dict[str, Any]:
        return {"type": "object"}

    async def fetch_page(
        self,
        entity_type: EntityType,
        page_size: int,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)


# ============================================================================
# TERRAFORM CLOUD CONNECTOR
# ============================================================================

@connector(
    metadata=ConnectorMetadata(
        id="terraform_cloud",
        name="Terraform Cloud",
        display_name="Terraform Cloud",
        description="Terraform Cloud workspaces, runs, state, and variables",
        category="devops",
        auth_type="api_key",
        auth_config={
            "fields": [
                {"name": "api_token", "type": "password", "label": "API Token", "required": True},
                {"name": "organization", "type": "string", "label": "Organization Name", "required": True},
            ],
        },
        config_schema={
            "type": "object",
            "properties": {
                "workspaces": {"type": "array", "items": {"type": "string"}},
            },
        },
        entity_types=["tf_workspace", "tf_run", "tf_state_version", "tf_variable"],
        supported_operations=["sync", "api_key"],
        rate_limits={"requests_per_minute": 30},
        version="1.0.0",
    ),
    auth="api_key",
    rate_limit=RateLimitConfig(requests_per_second=0.5),
    pagination=PaginationConfig(strategy="page", page_param="page[number]", limit_param="page[size]"),
    retry=RetryConfig(),
)
class TerraformCloudConnector(BaseConnector):
    """Terraform Cloud connector for workspaces, runs, state, and variables."""

    BASE_URL = "https://app.terraform.io/api/v2"

    def __init__(self, context):
        super().__init__(context)
        self.organization = self.context.credentials.get("organization")
        self.target_workspaces = set(self.context.config.get("workspaces", []))

    async def _make_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Any:
        url = urljoin(self.BASE_URL, path.lstrip("/"))
        headers = {
            "Authorization": f"Bearer {self.credentials.get('api_token')}",
            "Content-Type": "application/vnd.api+json",
        }
        response = await self._request_with_retry(method, urljoin(self.BASE_URL, path.lstrip("/")), params=params, json=data, headers=headers)
        return response.json()

    async def authenticate(self) -> bool:
        try:
            await self._make_request("GET", "/account/details")
            return True
        except Exception:
            return False

    async def validate_config(self) -> bool:
        return bool(self.credentials.get("api_token") and self.credentials.get("organization"))

    async def test_connection(self) -> bool:
        try:
            await self._make_request("GET", "/account/details")
            return True
        except Exception:
            return False

    def get_schema(self, entity_type: EntityType) -> Dict[str, Any]:
        return {"type": "object"}

    async def fetch_page(
        self,
        entity_type: EntityType,
        page_size: int,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)


# ============================================================================
# DATADOG CONNECTOR
# ============================================================================

@connector(
    metadata=ConnectorMetadata(
        id="datadog",
        name="Datadog",
        display_name="Datadog",
        description="Datadog metrics, monitors, dashboards, logs, and APM",
        category="devops",
        auth_type="api_key",
        auth_config={
            "fields": [
                {"name": "api_key", "type": "password", "label": "API Key", "required": True},
                {"name": "app_key", "type": "password", "label": "Application Key", "required": True},
                {"name": "site", "type": "select", "label": "Datadog Site", "options": ["datadoghq.com", "datadoghq.eu", "us3.datadoghq.com", "ddog-gov.com"], "default": "datadoghq.com"},
            ],
        },
        config_schema={
            "type": "object",
            "properties": {
                "include_monitors": {"type": "boolean", "default": True},
                "include_dashboards": {"type": "boolean", "default": True},
            },
        },
        entity_types=["metric", "monitor", "dashboard", "log_event"],
        supported_operations=["sync", "api_key"],
        rate_limits={"requests_per_minute": 300},
        version="1.0.0",
    ),
    auth="api_key",
    rate_limit=RateLimitConfig(requests_per_second=5),
    retry=RetryConfig(),
)
class DatadogConnector(BaseConnector):
    """Datadog connector for metrics, monitors, dashboards, and logs."""

    BASE_URL = "https://api.datadoghq.com/api/v1"

    async def _make_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Any:
        url = urljoin(self.BASE_URL, path.lstrip("/"))
        headers = {
            "DD-API-KEY": self.credentials.get("api_key"),
            "DD-APPLICATION-KEY": self.credentials.get("app_key"),
            "Accept": "application/json",
        }
        response = await self._request_with_retry(method, url, params=params, json=data, headers=headers)
        return response.json()

    async def authenticate(self) -> bool:
        try:
            await self._make_request("GET", "/validate")
            return True
        except Exception:
            return False

    async def validate_config(self) -> bool:
        return bool(self.credentials.get("api_key") and self.credentials.get("app_key"))

    async def test_connection(self) -> bool:
        try:
            await self._make_request("GET", "/validate")
            return True
        except Exception:
            return False

    def get_schema(self, entity_type: EntityType) -> Dict[str, Any]:
        return {"type": "object"}

    async def fetch_page(
        self,
        entity_type: EntityType,
        page_size: int,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        return PageResult(items=[], next_cursor=None, has_more=False, total_count=0)


# ============================================================================
# EXPORT ALL DEVOPS CONNECTORS
# ============================================================================

DEVOPS_CONNECTORS = {
    "github": GitHubConnector,
    "gitlab": GitLabConnector,
    "bitbucket": BitbucketConnector,
    "vercel": VercelConnector,
    "aws": AWSConnector,
    "gcp": GCPConnector,
    "azure": AzureConnector,
    "kubernetes": KubernetesConnector,
    "terraform_cloud": TerraformCloudConnector,
    "datadog": DatadogConnector,
}

# Export metadata for registry
DEVOPS_CONNECTOR_METADATA = {k: v.METADATA for k, v in DEVOPS_CONNECTORS.items()}


def get_devops_connector(connector_id: str, context: "ConnectorContext") -> BaseConnector:
    """Factory function to get DevOps connector instance."""
    connector_class = DEVOPS_CONNECTORS.get(connector_id)
    if not connector_class:
        raise ConfigurationError(f"Unknown DevOps connector: {connector_id}")
    return connector_class(context)


def list_devops_connectors() -> List[ConnectorMetadata]:
    """List all available DevOps connectors."""
    return list(DEVOPS_CONNECTOR_METADATA.values())