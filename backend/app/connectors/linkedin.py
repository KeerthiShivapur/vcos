"""
LinkedIn Connector for VCOS.

Provides integration with LinkedIn APIs for:
- Professional profile research
- Recruitment and candidate management
- Business development and company research
- Professional network insights

Note: LinkedIn API access requires partnership approval and specific permissions.
"""

import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlencode

from app.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    AuthType,
    RateLimitConfig,
    SyncCursor,
    SyncResult,
)

logger = logging.getLogger(__name__)


class LinkedInConnector(BaseConnector):
    """LinkedIn Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="linkedin",
        display_name="LinkedIn",
        description="Professional network for recruitment, business development, and professional research",
        category="identity",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "scopes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["client_id", "client_secret", "redirect_uri"],
        },
        required_scopes=[
            "r_liteprofile",
            "r_emailaddress",
            "w_member_social",
            "rw_organization_admin",
            "r_organization_social",
            "r_1st_connections_size",
        ],
        supported_operations=[
            # Profile operations
            "get_own_profile",
            "get_profile",
            "search_profiles",
            # Company operations
            "get_company",
            "search_companies",
            "get_company_updates",
            # Network operations
            "get_connections",
            "get_connection_count",
            # Organization admin (requires partnership)
            "list_organization_members",
            "get_organization_brand",
            # Job/Recruitment (requires partnership)
            "post_job",
            "get_job_applicants",
            # Learning (requires partnership)
            "list_learning_courses",
        ],
        webhook_events=[
            "profile.updated",
            "connection.added",
            "connection.removed",
            "company.updated",
            "job.posted",
            "job.application_received",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=5,
            requests_per_minute=100,
            burst=10,
        ),
    )

    BASE_URL = "https://api.linkedin.com/v2"
    AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
    TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.client_id = connection_config.get("client_id")
        self.client_secret = connection_config.get("client_secret")
        self.redirect_uri = connection_config.get("redirect_uri")
        self.scopes = connection_config.get("scopes", [
            "r_liteprofile",
            "r_emailaddress",
            "w_member_social",
            "rw_organization_admin",
            "r_organization_social",
        ])
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with LinkedIn using OAuth2."""
        from app.connectors.base import TokenManager

        self._token_manager = TokenManager(
            self.client_id,
            self.client_secret,
            self.TOKEN_URL,
        )
        await self._token_manager.get_access_token()
        self._authenticated = True
        logger.info("LinkedIn authenticated")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        if self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    # =========================================================================
    # PROFILE OPERATIONS
    # =========================================================================

    async def get_own_profile(self, projection: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Get the authenticated user's profile."""
        params = {}
        if projection:
            params["projection"] = f"({','.join(projection)})"
        
        response = await self._request("GET", "/me", params=params)
        return response.json()

    async def get_profile(self, person_id: str, projection: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Get a specific person's profile by URN."""
        params = {}
        if projection:
            params["projection"] = f"({','.join(projection)})"
        
        response = await self._request("GET", f"/people/{person_id}", params=params)
        return response.json()

    async def search_profiles(
        self,
        keywords: str,
        cursor: Optional[str] = None,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> SyncResult:
        """Search for profiles by keywords."""
        params = {
            "q": "keywords",
            "keywords": keywords,
            "count": min(limit, 10),
        }
        if filters:
            if filters.get("current_company"):
                params["company"] = filters["current_company"]
            if filters.get("location"):
                params["location"] = filters["location"]
            if filters.get("industry"):
                params["industry"] = filters["industry"]

        response = await self._request("GET", "/peopleSearch", params=params)
        data = response.json()
        
        entities = data.get("elements", [])
        next_cursor = data.get("paging", {}).get("next")

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    # =========================================================================
    # COMPANY OPERATIONS
    # =========================================================================

    async def get_company(self, company_id: str) -> Optional[Dict[str, Any]]:
        """Get company details by URN."""
        response = await self._request("GET", f"/organizations/{company_id}")
        return response.json()

    async def search_companies(
        self,
        keywords: str,
        cursor: Optional[str] = None,
        limit: int = 10,
    ) -> SyncResult:
        """Search for companies."""
        params = {
            "q": "keywords",
            "keywords": keywords,
            "count": min(limit, 10),
        }

        response = await self._request("GET", "/organizationSearch", params=params)
        data = response.json()
        
        entities = data.get("elements", [])
        next_cursor = data.get("paging", {}).get("next")

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def get_company_updates(
        self,
        company_id: str,
        cursor: Optional[str] = None,
        limit: int = 20,
    ) -> SyncResult:
        """Get company page updates/posts."""
        params = {
            "q": "organization",
            "organization": company_id,
            "count": min(limit, 50),
        }
        if cursor:
            params["start"] = cursor

        response = await self._request("GET", "/organizationalEntityShareStatistics", params=params)
        data = response.json()
        
        entities = data.get("elements", [])
        next_cursor = data.get("paging", {}).get("next")

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    # =========================================================================
    # NETWORK OPERATIONS
    # =========================================================================

    async def get_connections(
        self,
        person_id: str = "~",
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> SyncResult:
        """Get 1st-degree connections."""
        params = {"count": min(limit, 100)}
        if cursor:
            params["start"] = cursor

        response = await self._request("GET", f"/people/{person_id}/connections", params=params)
        data = response.json()
        
        entities = data.get("elements", [])
        next_cursor = data.get("paging", {}).get("next")

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def get_connection_count(self, person_id: str = "~") -> int:
        """Get total number of 1st-degree connections."""
        response = await self._request("GET", f"/people/{person_id}/num-connections")
        return response.json().get("count", 0)

    # =========================================================================
    # ORGANIZATION ADMIN (Requires Partnership)
    # =========================================================================

    async def list_organization_members(
        self,
        organization_urn: str,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> SyncResult:
        """List members of an organization (requires partnership)."""
        params = {"count": min(limit, 100)}
        if cursor:
            params["start"] = cursor

        response = await self._request("GET", f"/organizations/{organization_urn}/members", params=params)
        data = response.json()
        
        entities = data.get("elements", [])
        next_cursor = data.get("paging", {}).get("next")

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    async def get_organization_brand(self, organization_urn: str) -> Optional[Dict[str, Any]]:
        """Get organization brand details."""
        response = await self._request("GET", f"/organizations/{organization_urn}/brand")
        return response.json()

    # =========================================================================
    # JOB/RECRUITMENT (Requires Partnership)
    # =========================================================================

    async def post_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Post a job listing (requires partnership)."""
        required_fields = ["title", "description", "location", "employmentType"]
        for field in required_fields:
            if field not in job_data:
                raise ValueError(f"Required field missing: {field}")
        
        response = await self._request("POST", "/jobs", json=job_data)
        return response.json()

    async def get_job_applicants(
        self,
        job_id: str,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> SyncResult:
        """Get applicants for a job (requires partnership)."""
        params = {"count": min(limit, 50)}
        if cursor:
            params["start"] = cursor

        response = await self._request("GET", f"/jobs/{job_id}/applicants", params=params)
        data = response.json()
        
        entities = data.get("elements", [])
        next_cursor = data.get("paging", {}).get("next")

        return SyncResult(
            entities=entities,
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    # =========================================================================
    # OAUTH 2.0 SUPPORT
    # =========================================================================

    def generate_oauth_url(self, state: Optional[str] = None, scopes: Optional[List[str]] = None) -> str:
        """Generate LinkedIn OAuth authorization URL."""
        state = state or secrets.token_urlsafe(32)
        scope_list = scopes or self.scopes

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scope_list),
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def handle_oauth_callback(self, code: str, state: str) -> Dict[str, Any]:
        """Handle OAuth callback and exchange code for tokens."""
        if state not in self._oauth_states:
            raise ValueError("Invalid OAuth state")
        del self._oauth_states[state]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                raise ValueError(f"OAuth failed: {data.get('error_description', data.get('error'))}")

            return {
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in"),
                "token_type": data.get("token_type"),
                "scope": data.get("scope"),
            }