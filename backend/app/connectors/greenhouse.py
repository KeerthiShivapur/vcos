"""
Greenhouse Connector for VCOS.

Provides integration with Greenhouse for ATS (Applicant Tracking System) data.
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


class GreenhouseConnector(BaseConnector):
    """Greenhouse Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="greenhouse",
        display_name="Greenhouse",
        description="Applicant Tracking System and recruiting software",
        category="ats",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "Greenhouse API Key"},
                "base_url": {"type": "string", "default": "https://harvest.greenhouse.io/v1", "description": "Greenhouse Harvest API base URL"},
            },
            "required": ["api_key"],
        },
        required_scopes=[],
        supported_operations=[
            "list_candidates",
            "get_candidate",
            "create_candidate",
            "update_candidate",
            "list_jobs",
            "get_job",
            "create_job",
            "update_job",
            "list_applications",
            "get_application",
            "create_application",
            "update_application",
            "list_offers",
            "get_offer",
            "create_offer",
            "list_departments",
            "get_department",
            "list_offices",
            "get_office",
            "list_users",
            "get_user",
            "list_stages",
            "get_stage",
            "list_sources",
            "get_source",
            "list_scorecards",
            "get_scorecard",
            "list_activities",
            "get_activity",
            "list_custom_fields",
            "get_custom_field",
        ],
        webhook_events=[
            "candidate_created",
            "candidate_updated",
            "candidate_hired",
            "candidate_rejected",
            "application_created",
            "application_updated",
            "job_created",
            "job_updated",
            "job_opened",
            "job_closed",
            "offer_created",
            "offer_updated",
            "offer_accepted",
            "offer_declined",
            "scorecard_submitted",
            "interview_scheduled",
            "interview_updated",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=200,
            burst=50,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/greenhouse.svg",
        documentation_url="https://developers.greenhouse.io/harvest.html",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.api_key = connection_config.get("api_key")
        self.base_url = connection_config.get("base_url", "https://harvest.greenhouse.io/v1")

    async def authenticate(self) -> bool:
        """Authenticate with Greenhouse using API Key."""
        if not self.api_key:
            raise ValueError("Greenhouse requires api_key")

        # Greenhouse uses API key as username with empty password
        credentials = base64.b64encode(f"{self.api_key}:".encode()).decode()
        self._auth_header = f"Basic {credentials}"
        self._authenticated = True
        logger.info("Greenhouse authenticated with API Key")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._auth_header,
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make Greenhouse API request with error handling."""
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
                    raise Exception(f"Greenhouse API error: {resp.status} - {error_text}")
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
            "list_candidates": self._list_candidates,
            "list_jobs": self._list_jobs,
            "list_applications": self._list_applications,
            "list_offers": self._list_offers,
            "list_departments": self._list_departments,
            "list_offices": self._list_offices,
            "list_users": self._list_users,
            "list_stages": self._list_stages,
            "list_sources": self._list_sources,
            "list_scorecards": self._list_scorecards,
            "list_activities": self._list_activities,
            "list_custom_fields": self._list_custom_fields,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_candidates(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List candidates."""
        params = {"per_page": 100}
        if filters and filters.get("created_after"):
            params["created_after"] = filters["created_after"]
        if filters and filters.get("updated_after"):
            params["updated_after"] = filters["updated_after"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/candidates", params=params)
            for candidate in data:
                yield {
                    "type": "candidate",
                    "id": str(candidate["id"]),
                    "data": candidate,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            # Greenhouse uses Link header for pagination
            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_jobs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List jobs."""
        params = {"per_page": 100}
        if filters and filters.get("status"):
            params["status"] = filters["status"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/jobs", params=params)
            for job in data:
                yield {
                    "type": "job",
                    "id": str(job["id"]),
                    "data": job,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_applications(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List applications."""
        params = {"per_page": 100}
        if filters and filters.get("job_id"):
            params["job_id"] = filters["job_id"]
        if filters and filters.get("candidate_id"):
            params["candidate_id"] = filters["candidate_id"]
        if filters and filters.get("status"):
            params["status"] = filters["status"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/applications", params=params)
            for app in data:
                yield {
                    "type": "application",
                    "id": str(app["id"]),
                    "data": app,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_offers(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List offers."""
        params = {"per_page": 100}
        if filters and filters.get("application_id"):
            params["application_id"] = filters["application_id"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/offers", params=params)
            for offer in data:
                yield {
                    "type": "offer",
                    "id": str(offer["id"]),
                    "data": offer,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_departments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List departments."""
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/departments", params=params)
            for dept in data:
                yield {
                    "type": "department",
                    "id": str(dept["id"]),
                    "data": dept,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_offices(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List offices."""
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/offices", params=params)
            for office in data:
                yield {
                    "type": "office",
                    "id": str(office["id"]),
                    "data": office,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List users."""
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/users", params=params)
            for user in data:
                yield {
                    "type": "user",
                    "id": str(user["id"]),
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_stages(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List job stages."""
        params = {"per_page": 100}
        if filters and filters.get("job_id"):
            params["job_id"] = filters["job_id"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/stages", params=params)
            for stage in data:
                yield {
                    "type": "stage",
                    "id": str(stage["id"]),
                    "data": stage,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_sources(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List sources."""
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/sources", params=params)
            for source in data:
                yield {
                    "type": "source",
                    "id": str(source["id"]),
                    "data": source,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_scorecards(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List scorecards."""
        params = {"per_page": 100}
        if filters and filters.get("application_id"):
            params["application_id"] = filters["application_id"]
        if filters and filters.get("interview_id"):
            params["interview_id"] = filters["interview_id"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/scorecards", params=params)
            for scorecard in data:
                yield {
                    "type": "scorecard",
                    "id": str(scorecard["id"]),
                    "data": scorecard,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_activities(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List activities/notes."""
        params = {"per_page": 100}
        if filters and filters.get("candidate_id"):
            params["candidate_id"] = filters["candidate_id"]
        if filters and filters.get("application_id"):
            params["application_id"] = filters["application_id"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/activities", params=params)
            for activity in data:
                yield {
                    "type": "activity",
                    "id": str(activity["id"]),
                    "data": activity,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def _list_custom_fields(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List custom fields."""
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/custom_fields", params=params)
            for field in data:
                yield {
                    "type": "custom_field",
                    "id": str(field["id"]),
                    "data": field,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            link_header = self.session._last_response_headers.get("Link", "") if hasattr(self.session, '_last_response_headers') else ""
            if 'rel="next"' in link_header:
                import re
                match = re.search(r'<[^>]*[?&]page=(\d+)>; rel="next"', link_header)
                if match:
                    params["page"] = int(match.group(1))
                else:
                    break
            else:
                break

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_candidate": self._create_candidate,
            "update_candidate": self._update_candidate,
            "create_job": self._create_job,
            "update_job": self._update_job,
            "create_application": self._create_application,
            "update_application": self._update_application,
            "create_offer": self._create_offer,
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

    async def _create_candidate(self, candidate_data: Dict[str, Any]):
        """Create a new candidate."""
        payload = candidate_data.get("candidate", {})
        await self._make_request("POST", "/candidates", json=payload)

    async def _update_candidate(self, candidate_data: Dict[str, Any]):
        """Update a candidate."""
        candidate_id = candidate_data.get("candidate_id")
        if not candidate_id:
            raise ValueError("candidate_id required")

        payload = candidate_data.get("candidate", {})
        await self._make_request("PATCH", f"/candidates/{candidate_id}", json=payload)

    async def _create_job(self, job_data: Dict[str, Any]):
        """Create a new job."""
        payload = job_data.get("job", {})
        await self._make_request("POST", "/jobs", json=payload)

    async def _update_job(self, job_data: Dict[str, Any]):
        """Update a job."""
        job_id = job_data.get("job_id")
        if not job_id:
            raise ValueError("job_id required")

        payload = job_data.get("job", {})
        await self._make_request("PATCH", f"/jobs/{job_id}", json=payload)

    async def _create_application(self, app_data: Dict[str, Any]):
        """Create a new application."""
        payload = {
            "candidate_id": app_data.get("candidate_id"),
            "job_id": app_data.get("job_id"),
            "prospect": app_data.get("prospect", False),
            "applied_at": app_data.get("applied_at", datetime.utcnow().isoformat()),
        }
        await self._make_request("POST", "/applications", json=payload)

    async def _update_application(self, app_data: Dict[str, Any]):
        """Update an application."""
        application_id = app_data.get("application_id")
        if not application_id:
            raise ValueError("application_id required")

        payload = app_data.get("application", {})
        await self._make_request("PATCH", f"/applications/{application_id}", json=payload)

    async def _create_offer(self, offer_data: Dict[str, Any]):
        """Create a new offer."""
        payload = {
            "application_id": offer_data.get("application_id"),
            "version": offer_data.get("version", 1),
            "opens_at": offer_data.get("opens_at"),
            "expires_at": offer_data.get("expires_at"),
            "offer_details": offer_data.get("offer_details", {}),
        }
        await self._make_request("POST", "/offers", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/users", params={"per_page": 1})
            return isinstance(data, list)
        except Exception as e:
            logger.error(f"Greenhouse connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(GreenhouseConnector, GreenhouseConnector.CONFIG)