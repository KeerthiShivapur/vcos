"""
BambooHR Connector for VCOS.

Provides integration with BambooHR for HR data including employees, time off, and benefits.
"""

import base64
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


class BambooHRConnector(BaseConnector):
    """BambooHR Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="bamboohr",
        display_name="BambooHR",
        description="HR software for small and medium businesses",
        category="hris",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "subdomain": {"type": "string", "description": "BambooHR subdomain (e.g., 'mycompany' for mycompany.bamboohr.com)"},
                "api_key": {"type": "string", "description": "BambooHR API Key"},
            },
            "required": ["subdomain", "api_key"],
        },
        required_scopes=[],
        supported_operations=[
            "list_employees",
            "get_employee",
            "create_employee",
            "update_employee",
            "list_departments",
            "get_department",
            "list_locations",
            "get_location",
            "list_job_titles",
            "get_job_title",
            "list_time_off_types",
            "get_time_off_type",
            "list_time_off_requests",
            "get_time_off_request",
            "create_time_off_request",
            "approve_time_off_request",
            "deny_time_off_request",
            "list_benefits",
            "get_benefit",
            "list_payroll",
            "get_payroll",
            "list_tables",
            "get_table",
            "list_reports",
            "run_report",
        ],
        webhook_events=[
            "employee.created",
            "employee.updated",
            "employee.terminated",
            "time_off.created",
            "time_off.updated",
            "time_off.approved",
            "time_off.denied",
            "benefit.created",
            "benefit.updated",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=100,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/bamboohr.svg",
        documentation_url="https://documentation.bamboohr.com/reference",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.subdomain = connection_config.get("subdomain")
        self.api_key = connection_config.get("api_key")
        self.base_url = f"https://api.bamboohr.com/api/gateway.php/{self.subdomain}/v1"

    async def authenticate(self) -> bool:
        """Authenticate with BambooHR using API Key."""
        if not self.api_key:
            raise ValueError("BambooHR requires api_key")

        # BambooHR uses API key as username with empty password
        credentials = base64.b64encode(f"{self.api_key}:".encode()).decode()
        self._auth_header = f"Basic {credentials}"
        self._authenticated = True
        logger.info("BambooHR authenticated with API Key")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._auth_header,
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make BambooHR API request with error handling."""
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.base_url, endpoint)
        headers = await self._get_headers()

        await self.rate_limiter.acquire()

        async def _request():
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=429,
                        message=f"Rate limited, retry after {retry_after}s"
                    )
                if resp.status >= 400:
                    error_text = await resp.text()
                    raise Exception(f"BambooHR API error: {resp.status} - {error_text}")
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
            "list_employees": self._list_employees,
            "list_departments": self._list_departments,
            "list_locations": self._list_locations,
            "list_job_titles": self._list_job_titles,
            "list_time_off_types": self._list_time_off_types,
            "list_time_off_requests": self._list_time_off_requests,
            "list_benefits": self._list_benefits,
            "list_tables": self._list_tables,
            "get_table": self._get_table,
            "list_reports": self._list_reports,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_employees(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List employees."""
        params = {}
        if filters and filters.get("since"):
            params["since"] = filters["since"]

        data = await self._make_request("GET", "/employees/directory", params=params)
        
        for employee in data.get("employees", []):
            yield {
                "type": "employee",
                "id": str(employee["id"]),
                "data": employee,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_departments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List departments."""
        data = await self._make_request("GET", "/meta/departments")
        
        for dept in data:
            yield {
                "type": "department",
                "id": str(dept["id"]),
                "data": dept,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_locations(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List locations."""
        data = await self._make_request("GET", "/meta/locations")
        
        for location in data:
            yield {
                "type": "location",
                "id": str(location["id"]),
                "data": location,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_job_titles(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List job titles."""
        data = await self._make_request("GET", "/meta/jobTitles")
        
        for job in data:
            yield {
                "type": "job_title",
                "id": str(job["id"]),
                "data": job,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_time_off_types(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List time off types."""
        data = await self._make_request("GET", "/meta/time_off/types")
        
        for ttype in data:
            yield {
                "type": "time_off_type",
                "id": str(ttype["id"]),
                "data": ttype,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_time_off_requests(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List time off requests."""
        params = {}
        if filters and filters.get("start"):
            params["start"] = filters["start"]
        if filters and filters.get("end"):
            params["end"] = filters["end"]
        if filters and filters.get("employee_id"):
            params["employeeId"] = filters["employee_id"]
        if filters and filters.get("status"):
            params["status"] = filters["status"]

        data = await self._make_request("GET", "/time_off/requests", params=params)
        
        for request in data:
            yield {
                "type": "time_off_request",
                "id": str(request["id"]),
                "data": request,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_benefits(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List benefits."""
        data = await self._make_request("GET", "/benefits/employee")
        
        for benefit in data:
            yield {
                "type": "benefit",
                "id": str(benefit.get("id", benefit.get("benefitTypeId", ""))),
                "data": benefit,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_tables(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List custom tables."""
        data = await self._make_request("GET", "/meta/tables")
        
        for table in data:
            yield {
                "type": "table",
                "id": table["name"],
                "data": table,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _get_table(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Get table data."""
        table_name = filters.get("table_name")
        if not table_name:
            raise ValueError("table_name filter required")

        params = {"fields": filters.get("fields", "all")}
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        data = await self._make_request("GET", f"/tables/{table_name}", params=params)
        
        for row in data.get("rows", []):
            yield {
                "type": "table_row",
                "id": str(row.get("id", "")),
                "data": row,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_reports(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List reports."""
        data = await self._make_request("GET", "/reports")
        
        for report in data:
            yield {
                "type": "report",
                "id": str(report["id"]),
                "data": report,
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
            "create_employee": self._create_employee,
            "update_employee": self._update_employee,
            "create_time_off_request": self._create_time_off_request,
            "approve_time_off_request": self._approve_time_off_request,
            "deny_time_off_request": self._deny_time_off_request,
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
                result.records_updated += 1 if "update" in operation or "approve" in operation or "deny" in operation else 0
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_employee(self, employee_data: Dict[str, Any]):
        """Create a new employee."""
        payload = employee_data.get("employee", {})
        await self._make_request("POST", "/employees", json=payload)

    async def _update_employee(self, employee_data: Dict[str, Any]):
        """Update an employee."""
        employee_id = employee_data.get("employee_id")
        if not employee_id:
            raise ValueError("employee_id required")

        payload = employee_data.get("employee", {})
        await self._make_request("POST", f"/employees/{employee_id}", json=payload)

    async def _create_time_off_request(self, request_data: Dict[str, Any]):
        """Create a time off request."""
        payload = {
            "employeeId": request_data.get("employee_id"),
            "start": request_data.get("start"),
            "end": request_data.get("end"),
            "typeId": request_data.get("type_id"),
            "note": request_data.get("note"),
        }
        await self._make_request("POST", "/time_off/requests", json=payload)

    async def _approve_time_off_request(self, request_data: Dict[str, Any]):
        """Approve a time off request."""
        request_id = request_data.get("request_id")
        if not request_id:
            raise ValueError("request_id required")

        payload = {"status": "approved", "note": request_data.get("note", "")}
        await self._make_request("PUT", f"/time_off/requests/{request_id}/status", json=payload)

    async def _deny_time_off_request(self, request_data: Dict[str, Any]):
        """Deny a time off request."""
        request_id = request_data.get("request_id")
        if not request_id:
            raise ValueError("request_id required")

        payload = {"status": "denied", "note": request_data.get("note", "")}
        await self._make_request("PUT", f"/time_off/requests/{request_id}/status", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/employees/directory")
            return "employees" in data
        except Exception as e:
            logger.error(f"BambooHR connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(BambooHRConnector, BambooHRConnector.CONFIG)