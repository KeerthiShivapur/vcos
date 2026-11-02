"""
Workday Connector for VCOS.

Provides integration with Workday for HR, payroll, and financial data.
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


class WorkdayConnector(BaseConnector):
    """Workday Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="workday",
        display_name="Workday",
        description="Enterprise cloud applications for finance and HR",
        category="hris",
        auth_type=AuthType.BASIC_AUTH,
        config_schema={
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": "Workday tenant URL (e.g., https://yourtenant.workday.com)"},
                "username": {"type": "string", "description": "Workday username (with @tenant)"},
                "password": {"type": "string", "description": "Workday password"},
                "tenant_name": {"type": "string", "description": "Workday tenant name"},
                "api_version": {"type": "string", "default": "v39.0"},
            },
            "required": ["base_url", "username", "password", "tenant_name"],
        },
        required_scopes=[],
        supported_operations=[
            "list_workers",
            "get_worker",
            "create_worker",
            "update_worker",
            "terminate_worker",
            "list_positions",
            "get_position",
            "create_position",
            "list_organizations",
            "get_organization",
            "list_job_profiles",
            "get_job_profile",
            "list_locations",
            "get_location",
            "list_compensation_plans",
            "get_compensation_plan",
            "list_benefits",
            "get_benefit",
            "list_time_off",
            "get_time_off",
            "create_time_off",
            "list_payroll",
            "get_payroll",
        ],
        webhook_events=[
            "worker.created",
            "worker.updated",
            "worker.terminated",
            "position.created",
            "position.updated",
            "position.filled",
            "organization.created",
            "organization.updated",
            "compensation.changed",
            "benefit.enrolled",
            "benefit.terminated",
            "time_off.requested",
            "time_off.approved",
            "time_off.denied",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=5,
            requests_per_minute=100,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/workday.svg",
        documentation_url="https://community.workday.com/sites/default/files/file-hosting/productionapi/index.html",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.base_url = connection_config.get("base_url", "").rstrip("/")
        self.username = connection_config.get("username")
        self.password = connection_config.get("password")
        self.tenant_name = connection_config.get("tenant_name")
        self.api_version = connection_config.get("api_version", "v39.0")
        self._auth_header = None

    async def authenticate(self) -> bool:
        """Authenticate with Workday using Basic Auth."""
        if not self.username or not self.password:
            raise ValueError("Workday requires username and password")

        import base64
        credentials = f"{self.username}:{self.password}"
        self._auth_header = "Basic " + base64.b64encode(credentials.encode()).decode()
        self._authenticated = True
        logger.info("Workday authenticated with Basic Auth")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._auth_header,
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make Workday API request with error handling."""
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.base_url, endpoint)
        headers = await self._get_headers()

        await self.rate_limiter.acquire()

        # Add Workday-specific headers
        if "json" in kwargs:
            # Workday uses SOAP/JSON hybrid
            pass

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
                    raise Exception(f"Workday API error: {resp.status} - {error_text}")
                
                content_type = resp.headers.get("Content-Type", "")
                if "xml" in content_type:
                    # Parse XML response
                    import xmltodict
                    text = await resp.text()
                    return xmltodict.parse(text)
                return await resp.json()

        return await self.retry_policy.execute(_request)

    def _build_soap_envelope(self, operation: str, payload: Dict[str, Any]) -> str:
        """Build SOAP envelope for Workday API."""
        # Workday uses SOAP for most operations
        # This is a simplified version - real implementation would be more complex
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <env:Body>
        <{operation} xmlns="urn:com.workday/bsvc">
            {self._dict_to_xml(payload)}
        </{operation}>
    </env:Body>
</env:Envelope>"""

    def _dict_to_xml(self, data: Dict[str, Any], indent: int = 0) -> str:
        """Convert dict to XML string."""
        xml = ""
        for key, value in data.items():
            if isinstance(value, dict):
                xml += " " * indent + f"<{key}>"
                xml += self._dict_to_xml(value, indent + 2)
                xml += " " * indent + f"</{key}>"
            elif isinstance(value, list):
                for item in value:
                    xml += " " * indent + f"<{key}>"
                    if isinstance(item, dict):
                        xml += self._dict_to_xml(item, indent + 2)
                    else:
                        xml += str(item)
                    xml += f"</{key}>"
            else:
                xml += " " * indent + f"<{key}>{value}</{key}>"
        return xml

    async def pull_data(
        self,
        operation: str,
        cursor: Optional[SyncCursor] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not self._authenticated:
            await self.authenticate()

        handlers = {
            "list_workers": self._list_workers,
            "list_positions": self._list_positions,
            "list_organizations": self._list_organizations,
            "list_job_profiles": self._list_job_profiles,
            "list_locations": self._list_locations,
            "list_compensation_plans": self._list_compensation_plans,
            "list_benefits": self._list_benefits,
            "list_time_off": self._list_time_off,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_workers(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List workers using Get_Workers operation."""
        # Workday uses SOAP - this is a simplified REST-like wrapper
        payload = {
            "Request_Criteria": {
                "Include_Inactive": filters.get("include_inactive", False) if filters else False,
            },
            "Response_Filter": {
                "Page": cursor.cursor if cursor and cursor.cursor else 1,
                "Count": 100,
            },
        }

        # For demo, using a hypothetical REST endpoint
        # Real Workday uses SOAP with specific WSDL
        data = await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Human_Resources/{self.api_version}", 
                                        json={"operation": "Get_Workers", **payload})

        workers = data.get("Get_Workers_Response", {}).get("Response_Data", {}).get("Worker", [])
        for worker in workers:
            yield {
                "type": "worker",
                "id": worker.get("Worker_ID", {}).get("#text", ""),
                "data": worker,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_positions(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List positions."""
        payload = {
            "Request_Criteria": {},
            "Response_Filter": {
                "Page": cursor.cursor if cursor and cursor.cursor else 1,
                "Count": 100,
            },
        }

        data = await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Human_Resources/{self.api_version}",
                                        json={"operation": "Get_Positions", **payload})

        positions = data.get("Get_Positions_Response", {}).get("Response_Data", {}).get("Position", [])
        for position in positions:
            yield {
                "type": "position",
                "id": position.get("Position_ID", {}).get("#text", ""),
                "data": position,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_organizations(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List organizations."""
        payload = {
            "Request_Criteria": {},
            "Response_Filter": {
                "Page": cursor.cursor if cursor and cursor.cursor else 1,
                "Count": 100,
            },
        }

        data = await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Human_Resources/{self.api_version}",
                                        json={"operation": "Get_Organizations", **payload})

        orgs = data.get("Get_Organizations_Response", {}).get("Response_Data", {}).get("Organization", [])
        for org in orgs:
            yield {
                "type": "organization",
                "id": org.get("Organization_ID", {}).get("#text", ""),
                "data": org,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_job_profiles(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List job profiles."""
        payload = {
            "Request_Criteria": {},
            "Response_Filter": {
                "Page": cursor.cursor if cursor and cursor.cursor else 1,
                "Count": 100,
            },
        }

        data = await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Human_Resources/{self.api_version}",
                                        json={"operation": "Get_Job_Profiles", **payload})

        jobs = data.get("Get_Job_Profiles_Response", {}).get("Response_Data", {}).get("Job_Profile", [])
        for job in jobs:
            yield {
                "type": "job_profile",
                "id": job.get("Job_Profile_ID", {}).get("#text", ""),
                "data": job,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_locations(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List locations."""
        payload = {
            "Request_Criteria": {},
            "Response_Filter": {
                "Page": cursor.cursor if cursor and cursor.cursor else 1,
                "Count": 100,
            },
        }

        data = await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Human_Resources/{self.api_version}",
                                        json={"operation": "Get_Locations", **payload})

        locations = data.get("Get_Locations_Response", {}).get("Response_Data", {}).get("Location", [])
        for location in locations:
            yield {
                "type": "location",
                "id": location.get("Location_ID", {}).get("#text", ""),
                "data": location,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_compensation_plans(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List compensation plans."""
        payload = {
            "Request_Criteria": {},
            "Response_Filter": {
                "Page": cursor.cursor if cursor and cursor.cursor else 1,
                "Count": 100,
            },
        }

        data = await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Compensation/{self.api_version}",
                                        json={"operation": "Get_Compensation_Plans", **payload})

        plans = data.get("Get_Compensation_Plans_Response", {}).get("Response_Data", {}).get("Compensation_Plan", [])
        for plan in plans:
            yield {
                "type": "compensation_plan",
                "id": plan.get("Compensation_Plan_ID", {}).get("#text", ""),
                "data": plan,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_benefits(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List benefits."""
        payload = {
            "Request_Criteria": {},
            "Response_Filter": {
                "Page": cursor.cursor if cursor and cursor.cursor else 1,
                "Count": 100,
            },
        }

        data = await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Benefits/{self.api_version}",
                                        json={"operation": "Get_Benefits", **payload})

        benefits = data.get("Get_Benefits_Response", {}).get("Response_Data", {}).get("Benefit", [])
        for benefit in benefits:
            yield {
                "type": "benefit",
                "id": benefit.get("Benefit_ID", {}).get("#text", ""),
                "data": benefit,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_time_off(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List time off requests."""
        payload = {
            "Request_Criteria": {
                "From_Date": filters.get("from_date") if filters else None,
                "To_Date": filters.get("to_date") if filters else None,
            },
            "Response_Filter": {
                "Page": cursor.cursor if cursor and cursor.cursor else 1,
                "Count": 100,
            },
        }

        data = await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Time_Tracking/{self.api_version}",
                                        json={"operation": "Get_Time_Off", **payload})

        timeoffs = data.get("Get_Time_Off_Response", {}).get("Response_Data", {}).get("Time_Off", [])
        for timeoff in timeoffs:
            yield {
                "type": "time_off",
                "id": timeoff.get("Time_Off_ID", {}).get("#text", ""),
                "data": timeoff,
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
            "create_worker": self._create_worker,
            "update_worker": self._update_worker,
            "terminate_worker": self._terminate_worker,
            "create_position": self._create_position,
            "create_time_off": self._create_time_off,
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
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_worker(self, worker_data: Dict[str, Any]):
        """Create a new worker (hire)."""
        payload = {
            "Worker_Data": worker_data.get("worker_data", {}),
        }
        await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Human_Resources/{self.api_version}",
                                 json={"operation": "Hire_Employee", **payload})

    async def _update_worker(self, worker_data: Dict[str, Any]):
        """Update worker information."""
        worker_id = worker_data.get("worker_id")
        if not worker_id:
            raise ValueError("worker_id required")

        payload = {
            "Worker_Reference": {"ID": [{"type": "Worker_ID", "#text": worker_id}]},
            "Worker_Data": worker_data.get("worker_data", {}),
        }
        await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Human_Resources/{self.api_version}",
                                 json={"operation": "Update_Worker", **payload})

    async def _terminate_worker(self, worker_data: Dict[str, Any]):
        """Terminate a worker."""
        worker_id = worker_data.get("worker_id")
        if not worker_id:
            raise ValueError("worker_id required")

        payload = {
            "Worker_Reference": {"ID": [{"type": "Worker_ID", "#text": worker_id}]},
            "Termination_Date": worker_data.get("termination_date"),
            "Termination_Reason": worker_data.get("termination_reason"),
        }
        await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Human_Resources/{self.api_version}",
                                 json={"operation": "Terminate_Employee", **payload})

    async def _create_position(self, position_data: Dict[str, Any]):
        """Create a new position."""
        payload = {
            "Position_Data": position_data.get("position_data", {}),
        }
        await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Human_Resources/{self.api_version}",
                                 json={"operation": "Create_Position", **payload})

    async def _create_time_off(self, timeoff_data: Dict[str, Any]):
        """Create a time off request."""
        payload = {
            "Time_Off_Data": timeoff_data.get("time_off_data", {}),
        }
        await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Time_Tracking/{self.api_version}",
                                 json={"operation": "Create_Time_Off", **payload})

    async def test_connection(self) -> bool:
        try:
            # Test with a simple Get_Workers call
            data = await self._make_request("POST", f"/ccx/service/{self.tenant_name}/Human_Resources/{self.api_version}",
                                            json={"operation": "Get_Workers", "Request_Criteria": {}, "Response_Filter": {"Count": 1}})
            return "Get_Workers_Response" in data
        except Exception as e:
            logger.error(f"Workday connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(WorkdayConnector, WorkdayConnector.CONFIG)