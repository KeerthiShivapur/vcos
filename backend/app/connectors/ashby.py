"""
Ashby Connector for VCOS.

Provides integration with Ashby for ATS (Applicant Tracking System) data.
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


class AshbyConnector(BaseConnector):
    """Ashby Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="ashby",
        display_name="Ashby",
        description="Modern Applicant Tracking System and recruiting platform",
        category="ats",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "Ashby API Key"},
                "base_url": {"type": "string", "default": "https://api.ashbyhq.com/v1", "description": "Ashby API base URL"},
            },
            "required": ["api_key"],
        },
        required_scopes=[],
        supported_operations=[
            "list_candidates",
            "get_candidate",
            "create_candidate",
            "update_candidate",
            "list_applications",
            "get_application",
            "list_jobs",
            "get_job",
            "create_job",
            "update_job",
            "list_job_postings",
            "get_job_posting",
            "list_interviews",
            "get_interview",
            "list_interview_events",
            "list_users",
            "get_user",
            "list_departments",
            "get_department",
            "list_locations",
            "get_location",
            "list_offer_processes",
            "get_offer_process",
            "list_offers",
            "get_offer",
            "create_offer",
            "list_sources",
            "get_source",
            "list_tags",
            "get_tag",
            "list_custom_fields",
            "get_custom_field",
            "list_webhooks",
            "create_webhook",
            "delete_webhook",
        ],
        webhook_events=[
            "candidate.created",
            "candidate.updated",
            "candidate.merged",
            "candidate.deleted",
            "application.created",
            "application.updated",
            "application.status_changed",
            "application.withdrawn",
            "job.created",
            "job.updated",
            "job.published",
            "job.unpublished",
            "job.deleted",
            "interview.scheduled",
            "interview.updated",
            "interview.cancelled",
            "interview.completed",
            "interview.scorecard_submitted",
            "offer.created",
            "offer.updated",
            "offer.accepted",
            "offer.declined",
            "offer.withdrawn",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=100,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/ashby.svg",
        documentation_url="https://docs.ashbyhq.com/reference/introduction",
    )

    BASE_URL = "https://api.ashbyhq.com/v1"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.api_key = connection_config.get("api_key")
        self.base_url = connection_config.get("base_url", "https://api.ashbyhq.com/v1")

    async def authenticate(self) -> bool:
        """Authenticate with Ashby using API Key."""
        if not self.api_key:
            raise ValueError("Ashby requires api_key")

        import base64
        credentials = base64.b64encode(f"{self.api_key}:".encode()).decode()
        self._auth_header = f"Basic {credentials}"
        self._authenticated = True
        logger.info("Ashby authenticated with API Key")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._auth_header,
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.BASE_URL, endpoint)
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
                    raise Exception(f"Ashby API error: {resp.status} - {error_text}")
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
            "list_applications": self._list_applications,
            "list_jobs": self._list_jobs,
            "list_job_postings": self._list_job_postings,
            "list_interviews": self._list_interviews,
            "list_interview_events": self._list_interview_events,
            "list_users": self._list_users,
            "list_departments": self._list_departments,
            "list_locations": self._list_locations,
            "list_offer_processes": self._list_offer_processes,
            "list_offers": self._list_offers,
            "list_sources": self._list_sources,
            "list_tags": self._list_tags,
            "list_custom_fields": self._list_custom_fields,
            "list_webhooks": self._list_webhooks,
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
        params = {"limit": 100}
        if filters:
            for key in ["email", "name", "status", "source_id", "tag_ids", "created_after", "created_before"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/candidates.list", json=params)
            for candidate in data.get("results", []):
                yield {
                    "type": "candidate",
                    "id": candidate["id"],
                    "data": candidate,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_data_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_applications(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["candidate_id", "job_id", "status", "stage", "created_after", "created_before"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/applications.list", json=params)
            for app in data.get("results", []):
                yield {
                    "type": "application",
                    "id": app["id"],
                    "data": app,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_jobs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["status", "department_id", "location_id", "employment_type", "created_after", "created_before"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/jobs.list", json=params)
            for job in data.get("results", []):
                yield {
                    "type": "job",
                    "id": job["id"],
                    "data": job,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_job_postings(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["job_id", "status", "posted_after", "posted_before"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/jobPostings.list", json=params)
            for posting in data.get("results", []):
                yield {
                    "type": "job_posting",
                    "id": posting["id"],
                    "data": posting,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_interviews(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["application_id", "interview_plan_id", "status", "start_time_after", "start_time_before"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/interviews.list", json=params)
            for interview in data.get("results", []):
                yield {
                    "type": "interview",
                    "id": interview["id"],
                    "data": interview,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["email", "name", "is_active"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/users.list", json=params)
            for user in data.get("results", []):
                yield {
                    "type": "user",
                    "id": user["id"],
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_departments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/departments.list", json=params)
            for dept in data.get("results", []):
                yield {
                    "type": "department",
                    "id": dept["id"],
                    "data": dept,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_locations(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/locations.list", json=params)
            for location in data.get("results", []):
                yield {
                    "type": "location",
                    "id": location["id"],
                    "data": location,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_offers(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["application_id", "status", "created_after", "created_before"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/offers.list", json=params)
            for offer in data.get("results", []):
                yield {
                    "type": "offer",
                    "id": offer["id"],
                    "data": offer,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_sources(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/sources.list", json=params)
            for source in data.get("results", []):
                yield {
                    "type": "source",
                    "id": source["id"],
                    "data": source,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_tags(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/tags.list", json=params)
            for tag in data.get("results", []):
                yield {
                    "type": "tag",
                    "id": tag["id"],
                    "data": tag,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_custom_fields(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/customFields.list", json=params)
            for field in data.get("results", []):
                yield {
                    "type": "custom_field",
                    "id": field["id"],
                    "data": field,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
            else:
                break

    async def _list_webhooks(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/webhooks.list", json=params)
            for webhook in data.get("results", []):
                yield {
                    "type": "webhook",
                    "id": webhook["id"],
                    "data": webhook,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("more_results_available") and data.get("next_cursor"):
                params["cursor"] = data["next_cursor"]
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
        payload = candidate_data.get("candidate", {})
        await self._make_request("POST", "/candidates.create", json=payload)

    async def _update_candidate(self, candidate_data: Dict[str, Any]):
        candidate_id = candidate_data.get("candidate_id")
        if not candidate_id:
            raise ValueError("candidate_id required")
        payload = candidate_data.get("candidate", {})
        await self._make_request("POST", "/candidates.update", json={"candidate_id": candidate_id, "candidate": payload})

    async def _create_job(self, job_data: Dict[str, Any]):
        payload = job_data.get("job", {})
        await self._make_request("POST", "/jobs.create", json=payload)

    async def _update_job(self, job_data: Dict[str, Any]):
        job_id = job_data.get("job_id")
        if not job_id:
            raise ValueError("job_id required")
        payload = job_data.get("job", {})
        await self._make_request("POST", "/jobs.update", json={"job_id": job_id, "job": payload})

    async def _create_webhook(self, webhook_data: Dict[str, Any]):
        payload = {
            "url": webhook_data.get("url"),
            "events": webhook_data.get("events", ["*"]),
            "secret": webhook_data.get("secret"),
        }
        await self._make_request("POST", "/webhooks.create", json=payload)

    async def _delete_webhook(self, webhook_data: Dict[str, Any]):
        webhook_id = webhook_data.get("webhook_id")
        if not webhook_id:
            raise ValueError("webhook_id required")
        await self._make_request("POST", "/webhooks.delete", json={"webhook_id": webhook_id})

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("POST", "/users.list", json={"limit": 1})
            return "results" in data
        except Exception as e:
            logger.error(f"Ashby connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(AshbyConnector, AshbyConnector.CONFIG)