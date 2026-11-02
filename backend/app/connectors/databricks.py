"""
Databricks Connector for VCOS.

Provides integration with Databricks for data engineering and analytics.
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


class DatabricksConnector(BaseConnector):
    """Databricks Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="databricks",
        display_name="Databricks",
        description="Unified analytics platform for data engineering and ML",
        category="data_platform",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Databricks workspace URL (e.g., https://dbc-xxxxx.cloud.databricks.com)"},
                "token": {"type": "string", "description": "Personal access token"},
                "cluster_id": {"type": "string", "description": "Default cluster ID for job execution"},
            },
            "required": ["host", "token"],
        },
        required_scopes=[],
        supported_operations=[
            "execute_sql",
            "list_clusters",
            "get_cluster",
            "create_cluster",
            "start_cluster",
            "stop_cluster",
            "list_jobs",
            "get_job",
            "create_job",
            "run_job",
            "list_job_runs",
            "get_job_run",
            "list_dbfs_files",
            "get_dbfs_file",
            "put_dbfs_file",
            "delete_dbfs_file",
            "list_libraries",
            "install_library",
            "uninstall_library",
            "list_clusters",
            "list_jobs",
            "list_notebooks",
            "get_notebook",
            "export_notebook",
            "import_notebook",
            "list_pools",
            "list_policies",
            "list_secrets",
            "create_secret",
            "delete_secret",
        ],
        webhook_events=[],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=60,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/databricks.svg",
        documentation_url="https://docs.databricks.com/dev-tools/api/latest/index.html",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.host = connection_config.get("host", "").rstrip("/")
        self.token = connection_config.get("token")
        self.cluster_id = connection_config.get("cluster_id")

    async def authenticate(self) -> bool:
        """Authenticate with Databricks using token."""
        if not self.token or not self.host:
            raise ValueError("Databricks requires host and token")

        self._authenticated = True
        logger.info("Databricks authenticated with token")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.host, endpoint)
        headers = await self._get_headers()

        await self.rate_limiter.acquire()

        async def _request():
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    await asyncio.sleep(retry_after)
                    return await _request()
                if resp.status >= 400:
                    error_text = await resp.text()
                    raise Exception(f"Databricks API error: {resp.status} - {error_text}")
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
            "list_clusters": self._list_clusters,
            "list_jobs": self._list_jobs,
            "list_job_runs": self._list_job_runs,
            "list_dbfs_files": self._list_dbfs_files,
            "list_libraries": self._list_libraries,
            "list_pools": self._list_pools,
            "list_policies": self._list_policies,
            "list_secrets": self._list_secrets,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_clusters(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        data = await self._make_request("GET", "/api/2.0/clusters/list")
        for cluster in data.get("clusters", []):
            yield {
                "type": "cluster",
                "id": cluster["cluster_id"],
                "data": cluster,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_jobs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/api/2.1/jobs/list", params=params)
            for job in data.get("jobs", []):
                yield {
                    "type": "job",
                    "id": job["job_id"],
                    "data": job,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("jobs", [])) < 100:
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_job_runs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["job_id", "run_type", "state", "start_time_from", "start_time_to"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/api/2.1/jobs/runs/list", params=params)
            for run in data.get("runs", []):
                yield {
                    "type": "job_run",
                    "id": run["run_id"],
                    "data": run,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("runs", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_dbfs_files(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        path = filters.get("path") if filters else "/"
        if cursor and cursor.cursor:
            # DBFS doesn't support cursor-based pagination, use recursion
            pass

        data = await self._make_request("GET", "/api/2.0/dbfs/list", params={"path": path})
        for file in data.get("files", []):
            yield {
                "type": "dbfs_file",
                "id": file["path"],
                "data": file,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_libraries(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        cluster_id = filters.get("cluster_id") if filters else None
        if not cluster_id:
            raise ValueError("cluster_id filter required for list_libraries")

        data = await self._make_request("GET", "/api/2.0/libraries/cluster-status", params={"cluster_id": cluster_id})
        for lib in data.get("library_statuses", []):
            yield {
                "type": "library",
                "id": lib.get("library", {}).get("id", ""),
                "data": lib,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_pools(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        data = await self._make_request("GET", "/api/2.0/instance-pools/list")
        for pool in data.get("instance_pools", []):
            yield {
                "type": "pool",
                "id": pool["instance_pool_id"],
                "data": pool,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_policies(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        data = await self._make_request("GET", "/api/2.0/policies/list")
        for policy in data.get("policies", []):
            yield {
                "type": "policy",
                "id": policy["policy_id"],
                "data": policy,
                "synced_at": datetime.utcnow().isoformat(),
            )

    async def _list_secrets(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        scope = filters.get("scope") if filters else None
        if not scope:
            raise ValueError("scope filter required for list_secrets")

        data = await self._make_request("GET", "/api/2.0/secrets/list", params={"scope": scope})
        for secret in data.get("secrets", []):
            yield {
                "type": "secret",
                "id": secret["key"],
                "data": secret,
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
            "create_cluster": self._create_cluster,
            "start_cluster": self._start_cluster,
            "stop_cluster": self._stop_cluster,
            "run_job": self._run_job,
            "put_dbfs_file": self._put_dbfs_file,
            "delete_dbfs_file": self._delete_dbfs_file,
            "install_library": self._install_library,
            "uninstall_library": self._uninstall_library,
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

    async def _create_cluster(self, cluster_data: Dict[str, Any]):
        payload = cluster_data.get("cluster", {})
        await self._make_request("POST", "/api/2.0/clusters/create", json=payload)

    async def _start_cluster(self, cluster_data: Dict[str, Any]):
        cluster_id = cluster_data.get("cluster_id")
        if not cluster_id:
            raise ValueError("cluster_id required")
        await self._make_request("POST", "/api/2.0/clusters/start", json={"cluster_id": cluster_id})

    async def _stop_cluster(self, cluster_data: Dict[str, Any]):
        cluster_id = cluster_data.get("cluster_id")
        if not cluster_id:
            raise ValueError("cluster_id required")
        await self._make_request("POST", "/api/2.0/clusters/delete", json={"cluster_id": cluster_id})

    async def _run_job(self, job_data: Dict[str, Any]):
        job_id = job_data.get("job_id")
        if not job_id:
            raise ValueError("job_id required")
        payload = {
            "job_id": job_id,
            "notebook_params": job_data.get("notebook_params", {}),
            "python_params": job_data.get("python_params", []),
            "jar_params": job_data.get("jar_params", []),
            "spark_submit_params": job_data.get("spark_submit_params", []),
        }
        await self._make_request("POST", "/api/2.1/jobs/run-now", json=payload)

    async def _put_dbfs_file(self, file_data: Dict[str, Any]):
        path = file_data.get("path")
        content = file_data.get("content")
        if not path or content is None:
            raise ValueError("path and content required")

        import base64
        content_b64 = base64.b64encode(content.encode() if isinstance(content, str) else content).decode()

        await self._make_request("POST", "/api/2.0/dbfs/put", json={
            "path": path,
            "contents": content_b64,
            "overwrite": file_data.get("overwrite", True),
        })

    async def _delete_dbfs_file(self, file_data: Dict[str, Any]):
        path = file_data.get("path")
        if not path:
            raise ValueError("path required")

        await self._make_request("POST", "/api/2.0/dbfs/delete", json={"path": path, "recursive": file_data.get("recursive", False)})

    async def _install_library(self, library_data: Dict[str, Any]):
        cluster_id = library_data.get("cluster_id")
        if not cluster_id:
            raise ValueError("cluster_id required")

        payload = {
            "cluster_id": cluster_id,
            "libraries": library_data.get("libraries", []),
        }
        await self._make_request("POST", "/api/2.0/libraries/install", json=payload)

    async def _uninstall_library(self, library_data: Dict[str, Any]):
        cluster_id = library_data.get("cluster_id")
        if not cluster_id:
            raise ValueError("cluster_id required")

        payload = {
            "cluster_id": cluster_id,
            "libraries": library_data.get("libraries", []),
        }
        await self._make_request("POST", "/api/2.0/libraries/uninstall", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/api/2.0/clusters/list")
            return "clusters" in data
        except Exception as e:
            logger.error(f"Databricks connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(DatabricksConnector, DatabricksConnector.CONFIG)