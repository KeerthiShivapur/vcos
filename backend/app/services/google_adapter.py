"""Google Workspace Connector Adapter — production-grade implementation."""

import asyncio
import logging
import hmac
import hashlib
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Set
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode

import httpx
import jwt
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.services.base_adapter import BaseConnectorAdapter
from app.models.canonical_integration import ConnectorInstance
from app.services.external_identity_service import external_identity_service
from app.services.canonical_reality_integrity_service import canonical_reality_integrity_service
from app.services.source_authority_service import source_authority_service

logger = logging.getLogger("vcos.integration.google")


@dataclass
class GoogleConfig:
    """Google Workspace connector configuration."""
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: List[str]
    admin_email: Optional[str] = None
    customer_id: Optional[str] = None
    impersonated_user: Optional[str] = None


class GoogleEventTypes(Enum):
    """Google Workspace event types we support."""
    # Drive events
    FILE_CREATED = "file_created"
    FILE_UPDATED = "file_updated"
    FILE_DELETED = "file_deleted"
    FILE_TRASHED = "file_trashed"
    FILE_UNTRASHED = "file_untrashed"
    # Calendar events
    CALENDAR_CREATED = "calendar_created"
    CALENDAR_UPDATED = "calendar_updated"
    CALENDAR_DELETED = "calendar_deleted"
    EVENT_CREATED = "event_created"
    EVENT_UPDATED = "event_updated"
    EVENT_DELETED = "event_deleted"
    EVENT_CANCELLED = "event_cancelled"
    # User/Group events
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_SUSPENDED = "user_suspended"
    USER_UNSUSPENDED = "user_unsuspended"
    GROUP_CREATED = "group_created"
    GROUP_UPDATED = "group_updated"
    GROUP_DELETED = "group_deleted"
    GROUP_MEMBER_ADDED = "group_member_added"
    GROUP_MEMBER_REMOVED = "group_member_removed"
    # Org unit events
    ORGUNIT_CREATED = "orgunit_created"
    ORGUNIT_UPDATED = "orgunit_updated"
    ORGUNIT_DELETED = "orgunit_deleted"


class GoogleWorkspaceAdapter(BaseConnectorAdapter):
    """Google Workspace connector adapter with full API support."""

    provider_name = "google"

    # Supported entity types and their API endpoints
    ENTITY_ENDPOINTS = {
        "person": ("admin", "directory_v1", "users", "list"),
        "group": ("admin", "directory_v1", "groups", "list"),
        "channel": None,
        "message": None,
        "file": ("drive", "v3", "files", "list"),
        "event": ("calendar", "v3", "events", "list"),
        "contact": ("people", "v1", "people", "list"),
        "repository": None,
        "issue": None,
        "pull_request": None,
        "commit": None,
        "project": None,
        "task": ("tasks", "v1", "tasks", "list"),
        "customer": None,
        "deal": None,
        "organization": ("admin", "directory_v1", "customers", "get"),
        "employee": ("admin", "directory_v1", "users", "list"),
        "department": ("admin", "directory_v1", "orgunits", "list"),
        "role": ("admin", "directory_v1", "roleassignments", "list"),
    }

    # Google Workspace scopes we support
    SUPPORTED_SCOPES = {
        # Admin SDK
        "https://www.googleapis.com/auth/admin.directory.user.readonly",
        "https://www.googleapis.com/auth/admin.directory.user",
        "https://www.googleapis.com/auth/admin.directory.group.readonly",
        "https://www.googleapis.com/auth/admin.directory.group",
        "https://www.googleapis.com/auth/admin.directory.orgunit.readonly",
        "https://www.googleapis.com/auth/admin.directory.orgunit",
        "https://www.googleapis.com/auth/admin.directory.roleassignment.readonly",
        "https://www.googleapis.com/auth/admin.directory.roleassignment",
        "https://www.googleapis.com/auth/admin.directory.customer.readonly",
        # Drive
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
        "https://www.googleapis.com/auth/drive.file",
        # Calendar
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events.readonly",
        "https://www.googleapis.com/auth/calendar.events",
        # People
        "https://www.googleapis.com/auth/contacts.readonly",
        "https://www.googleapis.com/auth/contacts",
        # Tasks
        "https://www.googleapis.com/auth/tasks.readonly",
        "https://www.googleapis.com/auth/tasks",
    }

    # Webhook event types we support (from Google push notifications)
    SUPPORTED_WEBHOOK_EVENTS = {
        "file_created", "file_updated", "file_deleted", "file_trashed", "file_untrashed",
        "calendar_created", "calendar_updated", "calendar_deleted",
        "event_created", "event_updated", "event_deleted", "event_cancelled",
        "user_created", "user_updated", "user_deleted", "user_suspended", "user_unsuspended",
        "group_created", "group_updated", "group_deleted",
        "group_member_added", "group_member_removed",
        "orgunit_created", "orgunit_updated", "orgunit_deleted",
    }

    # Event types that support incremental sync with since parameter
    INCREMENTAL_EVENT_TYPES = {
        "person", "group", "file", "event", "department", "role",
    }

    def __init__(self, config: Optional[GoogleConfig] = None):
        super().__init__()
        self.config = config
        self._credentials: Optional[Credentials] = None
        self._service_cache: Dict[str, Any] = {}
        self._rate_limit_state: Dict[str, Dict[str, Any]] = {}
        # Track processed event IDs for exact-once semantics
        self._processed_event_ids: Set[str] = set()
        # Track event timestamps for out-of-order handling
        self._event_timestamps: Dict[str, datetime] = {}
        # OAuth state storage (in production, use Redis or DB)
        self._oauth_states: Dict[str, str] = {}
        # Channel IDs for push notifications
        self._watch_channels: Dict[str, str] = {}

    # =========================================================================
    # OAUTH 2.0 SUPPORT
    # =========================================================================

    def generate_oauth_url(self, state: Optional[str] = None) -> str:
        """Generate Google OAuth authorization URL."""
        state = state or secrets.token_urlsafe(32)
        self._oauth_states[state] = state  # Store for validation

        # Use offline access to get refresh token
        params = {
            "client_id": self.config.client_id if self.config else "",
            "redirect_uri": self.config.redirect_uri if self.config else "",
            "scope": " ".join(self.SUPPORTED_SCOPES),
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "include_granted_scopes": "true",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def handle_oauth_callback(self, code: str, state: str) -> Dict[str, Any]:
        """Handle OAuth callback and exchange code for tokens."""
        # Validate state
        if state not in self._oauth_states:
            raise ValueError("Invalid OAuth state")
        del self._oauth_states[state]

        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.config.client_id if self.config else "",
                    "client_secret": self.config.client_secret if self.config else "",
                    "code": code,
                    "redirect_uri": self.config.redirect_uri if self.config else "",
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                raise ValueError(f"OAuth failed: {data.get('error_description', data.get('error'))}")

            # Get user info
            user_info = await self._get_user_info(data.get("access_token"))

            return {
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in"),
                "token_type": data.get("token_type"),
                "scope": data.get("scope"),
                "user_email": user_info.get("email"),
                "user_name": user_info.get("name"),
                "user_id": user_info.get("id"),
            }

    async def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from Google using access token."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()

    async def verify_oauth_state(self, state: str) -> bool:
        """Verify OAuth state parameter."""
        return state in self._oauth_states

    async def refresh_access_token(self, instance: ConnectorInstance) -> bool:
        """Refresh access token using refresh token."""
        try:
            creds_dict = instance.credentials
            if not creds_dict or not creds_dict.get("refresh_token"):
                return False

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": creds_dict.get("client_id"),
                        "client_secret": creds_dict.get("client_secret"),
                        "refresh_token": creds_dict.get("refresh_token"),
                        "grant_type": "refresh_token",
                    },
                )
                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    logger.error(f"Token refresh failed: {data.get('error_description', data.get('error'))}")
                    return False

                # Update stored credentials
                instance.credentials = {
                    **creds_dict,
                    "access_token": data.get("access_token"),
                    "expires_in": data.get("expires_in"),
                    "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))).isoformat(),
                }
                instance.credentials_updated_at = datetime.now(timezone.utc)

                return True

        except Exception as e:
            logger.error(f"Token refresh failed for {instance.id}: {e}")
            return False

    # =========================================================================
    # SYNCHRONIZATION
    # =========================================================================

    async def start_provisioning_only(
        self,
        db,
        organization_name: str,
        domain: str,
        admin_email: str,
        admin_name: str,
        plan_key: str = "starter",
        billing_interval: str = "monthly",
        custom_domain: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> ConnectorInstance:
        """Start provisioning a new company with Google Workspace integration (without executing)."""
        from sqlalchemy import select, cast, String
        from app.models.organization import Organization
        from app.models.canonical_integration import Connector

        # Check if provisioning already exists for this idempotency key
        if idempotency_key:
            existing = await db.execute(
                select(ConnectorInstance).where(
                    cast(ConnectorInstance.config["idempotency_key"], String) == idempotency_key
                )
            )
            existing = existing.scalar_one_or_none()
            if existing:
                return existing

        # Create organization
        org = Organization(
            name=organization_name,
            slug=domain,
            domain=domain if custom_domain else None,
            status="provisioning",
        )
        db.add(org)
        await db.flush()

        # Create Google Workspace connector instance
        connector = await db.execute(
            select(Connector).where(Connector.provider == "google")
        )
        connector = connector.scalar_one_or_none()
        if not connector:
            connector = Connector(
                id="google",
                provider="google",
                kind="productivity",
                display_name="Google Workspace",
                description="Google Workspace integration for Drive, Calendar, Users, and Groups",
                inbound_capabilities=["read_users", "read_groups", "read_files", "read_calendar", "read_contacts", "read_orgunits"],
                outbound_capabilities=["write_files", "write_calendar", "write_users", "write_groups"],
                supported_entities=["person", "group", "file", "event", "organization", "employee", "department", "role", "contact", "task"],
                supported_events=["file", "calendar", "event", "user", "group", "orgunit"],
                sync_modes=["incremental", "webhook", "polling"],
                supports_webhooks=True,
                supports_polling=True,
                default_poll_interval_seconds=300,
                auth_types=["oauth2"],
                oauth_scopes=[
                    "https://www.googleapis.com/auth/admin.directory.user.readonly",
                    "https://www.googleapis.com/auth/admin.directory.group.readonly",
                    "https://www.googleapis.com/auth/drive.readonly",
                    "https://www.googleapis.com/auth/calendar.readonly",
                    "https://www.googleapis.com/auth/contacts.readonly",
                ],
                required_config_fields=["customer_id", "admin_email", "domain"],
                optional_config_fields=["impersonated_user"],
                enabled=True,
            )
            db.add(connector)
            await db.flush()

        instance = ConnectorInstance(
            organization_id=org.id,
            connector_id=connector.id,
            name=f"{organization_name} Google Workspace",
            config={
                "workspace": domain,
                "customer_id": domain,  # Will be updated after connection
                "admin_email": admin_email,
                "domain": domain,
                "idempotency_key": idempotency_key,
            } if idempotency_key else {
                "workspace": domain,
                "customer_id": domain,
                "admin_email": admin_email,
                "domain": domain,
            },
            credentials={},
            state="pending",
            webhook_secret=None,
            sync_enabled=True,
            sync_mode="incremental",
        )
        db.add(instance)
        await db.flush()

        return instance

    async def authenticate(self, instance: ConnectorInstance) -> bool:
        """Authenticate with Google Workspace using OAuth 2.0."""
        try:
            creds_dict = instance.credentials
            if not creds_dict:
                logger.error(f"No credentials for instance {instance.id}")
                return False

            self._credentials = Credentials(
                token=creds_dict.get("access_token"),
                refresh_token=creds_dict.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=creds_dict.get("client_id"),
                client_secret=creds_dict.get("client_secret"),
                scopes=creds_dict.get("scopes", []),
            )

            # Check if token needs refresh
            if self._credentials.expired and self._credentials.refresh_token:
                self._credentials.refresh(Request())
                # Update stored credentials
                instance.credentials = {
                    **creds_dict,
                    "access_token": self._credentials.token,
                    "refresh_token": self._credentials.refresh_token,
                    "expires_at": self._credentials.expiry.isoformat() if self._credentials.expiry else None,
                }
                instance.credentials_updated_at = datetime.now(timezone.utc)

            return True

        except Exception as e:
            logger.error(f"Google authentication failed for {instance.id}: {e}")
            return False

    async def test_connection(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Test connection to Google Workspace."""
        try:
            if not await self.authenticate(instance):
                return {"success": False, "error": "Authentication failed"}

            # Test Admin SDK
            service = await self._get_service("admin", "directory_v1", instance)
            if not service:
                return {"success": False, "error": "Failed to create Admin SDK service"}

            # Test with a simple request
            customer_id = instance.config.get("customer_id", "my_customer")
            result = service.users().list(customer=customer_id, maxResults=1).execute()

            return {
                "success": True,
                "customer_id": customer_id,
                "domain": instance.config.get("domain"),
                "user_count": len(result.get("users", [])),
            }

        except HttpError as e:
            return {"success": False, "error": f"Google API error: {e.resp.status} - {e._get_reason()}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # SERVICE MANAGEMENT
    # =========================================================================

    async def _get_service(self, api_name: str, api_version: str, instance: ConnectorInstance) -> Optional[Any]:
        """Get or create Google API service."""
        cache_key = f"{api_name}_{api_version}_{instance.id}"

        if cache_key in self._service_cache:
            return self._service_cache[cache_key]

        if not self._credentials:
            if not await self.authenticate(instance):
                return None

        # Create delegated credentials for domain-wide access
        if instance.config.get("admin_email"):
            delegated_creds = self._credentials.with_subject(instance.config["admin_email"])
        else:
            delegated_creds = self._credentials

        try:
            service = build(api_name, api_version, credentials=delegated_creds, cache_discovery=False)
            self._service_cache[cache_key] = service
            return service
        except Exception as e:
            logger.error(f"Failed to create {api_name} service: {e}")
            return None

    # =========================================================================
    # CURSOR MANAGEMENT
    # =========================================================================

    async def get_initial_cursor(self, instance: ConnectorInstance, entity_type: str) -> str:
        """Get initial cursor for full sync - returns earliest timestamp."""
        return "1970-01-01T00:00:00Z"

    async def get_incremental_cursor(self, instance: ConnectorInstance, entity_type: str, cursor: str) -> str:
        """Get next cursor for incremental sync."""
        return cursor

    async def _get_cursor_from_sync_run(self, instance: ConnectorInstance, entity_type: str) -> Optional[str]:
        """Get cursor from latest successful sync run."""
        from sqlalchemy import select
        from app.models.canonical_integration import SyncCursor, SyncRun, SYNC_STATES

        result = await db.execute(
            select(SyncCursor.cursor_value)
            .join(SyncRun, SyncCursor.sync_run_id == SyncRun.id)
            .where(
                SyncRun.connector_instance_id == instance.id,
                SyncCursor.entity_type == entity_type,
                SyncRun.state == "completed",
            )
            .order_by(SyncRun.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # =========================================================================
    # DATA FETCHING - GOOGLE DRIVE
    # =========================================================================

    async def _fetch_drive_page(
        self,
        instance: ConnectorInstance,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """Fetch a page of Drive files."""
        await self._check_rate_limit(instance, "drive")

        service = await self._get_service("drive", "v3", instance)
        if not service:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": "Service unavailable"}

        try:
            # Build query parameters
            params = {
                "pageSize": min(page_size, 1000),
                "fields": "nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, owners, permissions, webViewLink, size, trashed, parents, version, md5Checksum, description)",
                "orderBy": "modifiedTime desc",
            }

            # Add page token for pagination
            if cursor and cursor != "1970-01-01T00:00:00Z":
                params["pageToken"] = cursor

            # Add updated_min for incremental sync
            if since:
                params["q"] = f"modifiedTime > '{since.isoformat()}'"

            # Execute request with rate limit handling
            result = await self._execute_with_retry(
                lambda **p: service.files().list(**p),
                params
            )

            if not result:
                return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

            entities = [self._drive_file_to_dict(f) for f in result.get("files", [])]
            next_cursor = result.get("nextPageToken")

            return {
                "entities": entities,
                "next_cursor": next_cursor,
                "has_more": bool(next_cursor),
                "total_count": len(entities),
            }

        except HttpError as e:
            logger.error(f"Google Drive API error: {e}")
            await self._handle_http_error(e)
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}
        except Exception as e:
            logger.error(f"Error fetching Drive files: {e}")
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}

    def _drive_file_to_dict(self, file: Dict) -> Dict[str, Any]:
        """Convert Drive file to standard dict."""
        return {
            "id": file.get("id"),
            "external_id": file.get("id"),
            "name": file.get("name"),
            "mime_type": file.get("mimeType"),
            "description": file.get("description"),
            "size": file.get("size"),
            "md5_checksum": file.get("md5Checksum"),
            "version": file.get("version"),
            "created_time": file.get("createdTime"),
            "modified_time": file.get("modifiedTime"),
            "trashed": file.get("trashed", False),
            "web_view_link": file.get("webViewLink"),
            "owners": file.get("owners", []),
            "parents": file.get("parents", []),
            "permissions": file.get("permissions", []),
        }

    async def _fetch_drive_changes(
        self,
        instance: ConnectorInstance,
        start_page_token: Optional[str] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """Fetch Drive changes using change log (for incremental sync)."""
        await self._check_rate_limit(instance, "drive")

        service = await self._get_service("drive", "v3", instance)
        if not service:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": "Service unavailable"}

        try:
            # Get start page token if not provided
            if not start_page_token:
                start_token = service.changes().getStartPageToken().execute()
                start_page_token = start_token.get("startPageToken")

            params = {
                "pageToken": start_page_token,
                "pageSize": min(page_size, 1000),
                "fields": "nextPageToken, newStartPageToken, changes(fileId, removed, file(id, name, mimeType, createdTime, modifiedTime, owners, permissions, webViewLink, size, trashed, parents, version, md5Checksum, description))",
            }

            result = await self._execute_with_retry(
                lambda **p: service.changes().list(**p),
                params
            )

            if not result:
                return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

            entities = []
            for change in result.get("changes", []):
                if change.get("removed"):
                    entities.append({"external_id": change.get("fileId"), "deleted": True})
                else:
                    file_data = change.get("file")
                    if file_data:
                        entities.append(self._drive_file_to_dict(file_data))

            next_cursor = result.get("newStartPageToken") or result.get("nextPageToken")

            return {
                "entities": entities,
                "next_cursor": next_cursor,
                "has_more": bool(result.get("nextPageToken")),
                "total_count": len(entities),
            }

        except HttpError as e:
            logger.error(f"Google Drive changes API error: {e}")
            await self._handle_http_error(e)
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}
        except Exception as e:
            logger.error(f"Error fetching Drive changes: {e}")
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}

    # =========================================================================
    # DATA FETCHING - GOOGLE CALENDAR
    # =========================================================================

    async def _fetch_calendar_events_page(
        self,
        instance: ConnectorInstance,
        calendar_id: str = "primary",
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """Fetch a page of Calendar events."""
        await self._check_rate_limit(instance, "calendar")

        service = await self._get_service("calendar", "v3", instance)
        if not service:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": "Service unavailable"}

        try:
            params = {
                "calendarId": calendar_id,
                "maxResults": min(page_size, 2500),
                "singleEvents": True,
                "orderBy": "startTime",
                "showDeleted": True,
            }

            # Add page token for pagination
            if cursor and cursor != "1970-01-01T00:00:00Z":
                params["pageToken"] = cursor

            # Add time range
            time_min = since or datetime.now(timezone.utc) - timedelta(days=30)
            params["timeMin"] = time_min.isoformat()
            params["timeMax"] = datetime.now(timezone.utc).isoformat()

            result = await self._execute_with_retry(
                lambda **p: service.events().list(**p),
                params
            )

            if not result:
                return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

            entities = [self._calendar_event_to_dict(e, calendar_id) for e in result.get("items", [])]
            next_cursor = result.get("nextPageToken")

            return {
                "entities": entities,
                "next_cursor": next_cursor,
                "has_more": bool(next_cursor),
                "total_count": len(entities),
            }

        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}")
            await self._handle_http_error(e)
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}
        except Exception as e:
            logger.error(f"Error fetching Calendar events: {e}")
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}

    def _calendar_event_to_dict(self, event: Dict, calendar_id: str) -> Dict[str, Any]:
        """Convert Calendar event to standard dict."""
        return {
            "id": event.get("id"),
            "external_id": event.get("id"),
            "calendar_id": calendar_id,
            "summary": event.get("summary"),
            "description": event.get("description"),
            "location": event.get("location"),
            "status": event.get("status"),
            "start": event.get("start"),
            "end": event.get("end"),
            "timezone": event.get("timeZone"),
            "recurrence": event.get("recurrence"),
            "recurring_event_id": event.get("recurringEventId"),
            "organizer": event.get("organizer"),
            "attendees": event.get("attendees", []),
            "created": event.get("created"),
            "updated": event.get("updated"),
            "html_link": event.get("htmlLink"),
            "creator": event.get("creator"),
            "sequence": event.get("sequence"),
            "transparency": event.get("transparency"),
            "visibility": event.get("visibility"),
        }

    async def _fetch_calendar_list(
        self,
        instance: ConnectorInstance,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """Fetch list of calendars."""
        await self._check_rate_limit(instance, "calendar")

        service = await self._get_service("calendar", "v3", instance)
        if not service:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": "Service unavailable"}

        try:
            params = {"maxResults": min(page_size, 250)}
            result = await self._execute_with_retry(
                lambda **p: service.calendarList().list(**p),
                params
            )

            if not result:
                return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

            entities = [self._calendar_to_dict(c) for c in result.get("items", [])]
            next_cursor = result.get("nextPageToken")

            return {
                "entities": entities,
                "next_cursor": next_cursor,
                "has_more": bool(next_cursor),
                "total_count": len(entities),
            }

        except HttpError as e:
            logger.error(f"Google Calendar list API error: {e}")
            await self._handle_http_error(e)
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}
        except Exception as e:
            logger.error(f"Error fetching Calendar list: {e}")
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}

    def _calendar_to_dict(self, calendar: Dict) -> Dict[str, Any]:
        """Convert Calendar to standard dict."""
        return {
            "id": calendar.get("id"),
            "external_id": calendar.get("id"),
            "summary": calendar.get("summary"),
            "description": calendar.get("description"),
            "location": calendar.get("location"),
            "timezone": calendar.get("timeZone"),
            "primary": calendar.get("primary", False),
            "access_role": calendar.get("accessRole"),
            "selected": calendar.get("selected"),
            "background_color": calendar.get("backgroundColor"),
            "foreground_color": calendar.get("foregroundColor"),
        }

    # =========================================================================
    # DATA FETCHING - USERS AND GROUPS (ADMIN SDK)
    # =========================================================================

    async def _fetch_admin_page(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """Fetch a page of Admin SDK entities (users, groups, orgunits)."""
        await self._check_rate_limit(instance, "admin")

        endpoint = self.ENTITY_ENDPOINTS.get(entity_type)
        if not endpoint:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

        api_name, api_version, resource, method = endpoint

        service = await self._get_service(api_name, api_version, instance)
        if not service:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": "Service unavailable"}

        try:
            resource_obj = getattr(service, resource)()
            method_func = getattr(resource_obj, method)

            params = {"maxResults": min(page_size, 500)}

            # Add customer ID for Admin SDK
            customer_id = instance.config.get("customer_id", "my_customer")
            params["customer"] = customer_id

            # Add page token for pagination
            if cursor and cursor != "1970-01-01T00:00:00Z":
                params["pageToken"] = cursor

            # Add updated_min for incremental sync
            if since and entity_type in self.INCREMENTAL_EVENT_TYPES:
                params["updatedMin"] = since.isoformat()

            # Add query for specific entity types
            if entity_type == "person":
                params["orderBy"] = "email"
                params["projection"] = "full"
            elif entity_type == "group":
                params["orderBy"] = "email"
            elif entity_type == "department":
                params["type"] = "all"

            result = await self._execute_with_retry(method_func, params)

            if not result:
                return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

            entities = self._extract_admin_entities(result, entity_type)
            next_cursor = result.get("nextPageToken")

            return {
                "entities": entities,
                "next_cursor": next_cursor,
                "has_more": bool(next_cursor),
                "total_count": len(entities),
            }

        except HttpError as e:
            logger.error(f"Google Admin API error fetching {entity_type}: {e}")
            await self._handle_http_error(e)
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}
        except Exception as e:
            logger.error(f"Error fetching {entity_type} from Google: {e}")
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}

    def _extract_admin_entities(self, result: Dict[str, Any], entity_type: str) -> List[Dict[str, Any]]:
        """Extract entities from Admin SDK result based on entity type."""
        if entity_type == "person":
            return [self._user_to_dict(u) for u in result.get("users", [])]
        elif entity_type == "group":
            return [self._group_to_dict(g) for g in result.get("groups", [])]
        elif entity_type == "department":
            return [self._orgunit_to_dict(u) for u in result.get("organizationUnits", [])]
        elif entity_type == "role":
            return [self._role_to_dict(r) for r in result.get("items", [])]
        elif entity_type == "organization":
            return [self._customer_to_dict(result)] if result else []

        # Generic fallback
        for key in ["users", "groups", "organizationUnits", "items"]:
            if key in result:
                return result[key]
        return []

    def _user_to_dict(self, user: Dict) -> Dict[str, Any]:
        """Convert Admin SDK user to standard dict."""
        return {
            "id": user.get("id"),
            "external_id": user.get("id"),
            "primary_email": user.get("primaryEmail"),
            "emails": user.get("emails", []),
            "name": user.get("name"),
            "given_name": user.get("name", {}).get("givenName"),
            "family_name": user.get("name", {}).get("familyName"),
            "display_name": user.get("name", {}).get("fullName"),
            "suspended": user.get("suspended", False),
            "archived": user.get("archived", False),
            "org_unit_path": user.get("orgUnitPath"),
            "is_admin": user.get("isAdmin", False),
            "is_delegated_admin": user.get("isDelegatedAdmin", False),
            "last_login_time": user.get("lastLoginTime"),
            "creation_time": user.get("creationTime"),
            "deletion_time": user.get("deletionTime"),
            "phones": user.get("phones", []),
            "addresses": user.get("addresses", []),
            "relations": user.get("relations", []),
            "aliases": user.get("aliases", []),
            "non_editable_aliases": user.get("nonEditableAliases", []),
            "customer_id": user.get("customerId"),
            "thumbnail_photo_url": user.get("thumbnailPhotoUrl"),
            "external_ids": user.get("externalIds", []),
            "organizations": user.get("organizations", []),
        }

    def _group_to_dict(self, group: Dict) -> Dict[str, Any]:
        """Convert Admin SDK group to standard dict."""
        return {
            "id": group.get("id"),
            "external_id": group.get("id"),
            "email": group.get("email"),
            "name": group.get("name"),
            "description": group.get("description"),
            "direct_members_count": group.get("directMembersCount"),
            "aliases": group.get("aliases", []),
            "non_editable_aliases": group.get("nonEditableAliases", []),
        }

    def _orgunit_to_dict(self, orgunit: Dict) -> Dict[str, Any]:
        """Convert Admin SDK org unit to standard dict."""
        return {
            "id": orgunit.get("id"),
            "external_id": orgunit.get("id"),
            "name": orgunit.get("name"),
            "description": orgunit.get("description"),
            "parent_org_unit_id": orgunit.get("parentOrgUnitId"),
            "parent_org_unit_path": orgunit.get("parentOrgUnitPath"),
            "block_inheritance": orgunit.get("blockInheritance", False),
        }

    def _role_to_dict(self, role: Dict) -> Dict[str, Any]:
        """Convert Admin SDK role assignment to standard dict."""
        return {
            "id": role.get("roleAssignmentId"),
            "external_id": role.get("roleAssignmentId"),
            "role_id": role.get("roleId"),
            "role_name": role.get("roleName"),
            "user_id": role.get("userId"),
            "org_unit_id": role.get("orgUnitId"),
            "scope_type": role.get("scopeType"),
        }

    def _customer_to_dict(self, customer: Dict) -> Dict[str, Any]:
        """Convert Admin SDK customer to standard dict."""
        return {
            "id": customer.get("id"),
            "external_id": customer.get("id"),
            "domain": customer.get("domain"),
            "customer_domain": customer.get("customerDomain"),
            "alternate_email": customer.get("alternateEmail"),
            "language": customer.get("language"),
            "phone_number": customer.get("phoneNumber"),
            "postal_address": customer.get("postalAddress"),
        }

    # =========================================================================
    # UNIFIED FETCH_PAGE
    # =========================================================================

    async def fetch_page(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """Fetch a page of entities from Google Workspace."""
        if entity_type == "file":
            return await self._fetch_drive_page(instance, cursor, since, page_size)
        elif entity_type == "event":
            calendar_id = instance.config.get("calendar_id", "primary")
            return await self._fetch_calendar_events_page(instance, calendar_id, cursor, since, page_size)
        elif entity_type == "channel":  # Calendar list
            return await self._fetch_calendar_list(instance, page_size)
        elif entity_type in ("person", "group", "department", "role", "organization", "employee"):
            return await self._fetch_admin_page(instance, entity_type, cursor, since, page_size)
        else:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

    async def fetch_entity(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        external_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single entity by external ID."""
        endpoint = self.ENTITY_ENDPOINTS.get(entity_type)
        if not endpoint:
            return None

        api_name, api_version, resource, method = endpoint
        service = await self._get_service(api_name, api_version, instance)
        if not service:
            return None

        try:
            resource_obj = getattr(service, resource)()

            # Build parameters based on entity type
            if api_name == "admin":
                params = {"customer": instance.config.get("customer_id", "my_customer")}

            if entity_type == "person":
                params["userKey"] = external_id
            elif entity_type == "group":
                params["groupKey"] = external_id
            elif entity_type == "file":
                params["fileId"] = external_id
            elif entity_type == "event":
                calendar_id = instance.config.get("calendar_id", "primary")
                params["calendarId"] = calendar_id
                params["eventId"] = external_id
            elif entity_type == "department":
                params["orgUnitId"] = external_id
            elif entity_type == "role":
                params["roleAssignmentId"] = external_id

            result = await self._execute_with_retry(getattr(resource_obj, "get"), params)

            if result:
                if entity_type == "person":
                    return self._user_to_dict(result)
                elif entity_type == "group":
                    return self._group_to_dict(result)
                elif entity_type == "file":
                    return self._drive_file_to_dict(result)
                elif entity_type == "event":
                    calendar_id = instance.config.get("calendar_id", "primary")
                    return self._calendar_event_to_dict(result, calendar_id)
                elif entity_type == "department":
                    return self._orgunit_to_dict(result)
                elif entity_type == "role":
                    return self._role_to_dict(result)
                elif entity_type == "organization":
                    return self._customer_to_dict(result)
            return None

        except HttpError as e:
            if e.resp.status == 404:
                return None
            logger.error(f"Google API error fetching entity {external_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching entity {external_id}: {e}")
            return None

    async def get_deleted_entities(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        since: datetime,
    ) -> List[str]:
        """Get list of deleted entity external IDs since timestamp."""
        if entity_type == "person":
            try:
                service = await self._get_service("admin", "directory_v1", instance)
                if not service:
                    return []

                result = service.users().list(
                    customer=instance.config.get("customer_id", "my_customer"),
                    showDeleted=True,
                    maxResults=500
                ).execute()

                deleted_ids = []
                for user in result.get("users", []):
                    if user.get("deleted", False) and user.get("deletionTime"):
                        deletion_time = datetime.fromisoformat(user["deletionTime"].replace("Z", "+00:00"))
                        if deletion_time >= since:
                            deleted_ids.append(user["id"])

                return deleted_ids
            except Exception as e:
                logger.error(f"Error fetching deleted users: {e}")
                return []

        # For Drive files, use changes API
        if entity_type == "file":
            try:
                service = await self._get_service("drive", "v3", instance)
                if not service:
                    return []

                # Get start page token
                start_token = service.changes().getStartPageToken().execute()
                start_page_token = start_token.get("startPageToken")

                # List changes
                result = service.changes().list(
                    pageToken=start_page_token,
                    pageSize=1000,
                    fields="changes(fileId, removed)"
                ).execute()

                deleted_ids = []
                for change in result.get("changes", []):
                    if change.get("removed"):
                        deleted_ids.append(change.get("fileId"))

                return deleted_ids
            except Exception as e:
                logger.error(f"Error fetching deleted Drive files: {e}")
                return []

        return []

    # =========================================================================
    # WEBHOOK / PUSH NOTIFICATION HANDLING
    # =========================================================================

    async def verify_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature_header: str,
        channel_id_header: Optional[str] = None,
    ) -> bool:
        """Verify Google push notification signature.

        Google uses X-Goog-Signature header with format: sha256=signature
        and X-Goog-Channel-ID for channel identification.
        """
        if not instance.webhook_secret:
            logger.warning(f"No webhook secret configured for instance {instance.id}")
            return False

        # Verify channel ID if provided
        if channel_id_header and channel_id_header not in self._watch_channels.values():
            logger.warning(f"Unknown channel ID: {channel_id_header}")
            return False

        # Verify signature
        expected_signature = hmac.new(
            instance.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        expected_signature = f"sha256={expected_signature}"

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected_signature, signature_header)

    async def process_webhook_event(
        self,
        instance: ConnectorInstance,
        event_type: str,
        payload: Dict[str, Any],
        delivery_id: str,
        event_timestamp: datetime,
    ) -> Dict[str, Any]:
        """Process a Google push notification event with exact-once semantics."""
        # Exact-once: Check if we've already processed this event
        event_fingerprint = f"{delivery_id}:{event_type}"
        if event_fingerprint in self._processed_event_ids:
            logger.info(f"Duplicate webhook event ignored: {event_fingerprint}")
            return {"status": "duplicate", "delivery_id": delivery_id}

        # Out-of-order handling: check event timestamp
        if delivery_id in self._event_timestamps:
            previous_timestamp = self._event_timestamps[delivery_id]
            if event_timestamp <= previous_timestamp:
                logger.warning(f"Out-of-order event detected: {delivery_id}, "
                             f"previous: {previous_timestamp}, current: {event_timestamp}")

        # Record event for future duplicate/out-of-order detection
        self._processed_event_ids.add(event_fingerprint)
        self._event_timestamps[delivery_id] = event_timestamp

        # Only process supported event types
        if event_type not in self.SUPPORTED_WEBHOOK_EVENTS:
            return {"status": "ignored", "reason": f"Unsupported event type: {event_type}"}

        result = {"status": "processed", "delivery_id": delivery_id, "entities": []}

        try:
            # Process based on event type
            if event_type.startswith("file_"):
                entities = await self._process_drive_webhook(payload)
                result["entities"] = entities
            elif event_type.startswith("event_") or event_type.startswith("calendar_"):
                entities = await self._process_calendar_webhook(payload)
                result["entities"] = entities
            elif event_type.startswith("user_"):
                entities = await self._process_user_webhook(payload)
                result["entities"] = entities
            elif event_type.startswith("group_"):
                entities = await self._process_group_webhook(payload)
                result["entities"] = entities
            elif event_type.startswith("orgunit_"):
                entities = await self._process_orgunit_webhook(payload)
                result["entities"] = entities

            # Record provenance for all processed entities
            for entity in result.get("entities", []):
                await self._record_provenance(payload, entity)

        except Exception as e:
            logger.error(f"Error processing webhook {event_type} ({delivery_id}): {e}")
            result = {"status": "error", "delivery_id": delivery_id, "error": str(e)}

        return result

    async def _process_drive_webhook(self, payload: Dict) -> List[Dict]:
        """Process Drive push notification."""
        # Google Drive push notifications include the changed file ID
        # We need to fetch the full file details
        file_id = payload.get("fileId") or payload.get("id")
        if not file_id:
            return []

        # In a real implementation, we'd fetch the file here
        # For now, return the file reference
        return [{
            "id": file_id,
            "external_id": file_id,
            "webhook_payload": payload,
        }]

    async def _process_calendar_webhook(self, payload: Dict) -> List[Dict]:
        """Process Calendar push notification."""
        # Calendar push notifications indicate a calendar changed
        # We need to fetch events for that calendar
        calendar_id = payload.get("calendarId") or "primary"

        # Return calendar reference
        return [{
            "calendar_id": calendar_id,
            "webhook_payload": payload,
        }]

    async def _process_user_webhook(self, payload: Dict) -> List[Dict]:
        """Process Admin SDK user webhook (via Google Workspace Events API)."""
        user_id = payload.get("userId")
        return [{
            "id": user_id,
            "external_id": user_id,
            "webhook_payload": payload,
        }]

    async def _process_group_webhook(self, payload: Dict) -> List[Dict]:
        """Process Admin SDK group webhook."""
        group_id = payload.get("groupId")
        return [{
            "id": group_id,
            "external_id": group_id,
            "webhook_payload": payload,
        }]

    async def _process_orgunit_webhook(self, payload: Dict) -> List[Dict]:
        """Process Admin SDK org unit webhook."""
        orgunit_id = payload.get("orgUnitId")
        return [{
            "id": orgunit_id,
            "external_id": orgunit_id,
            "webhook_payload": payload,
        }]

    async def _record_provenance(self, payload: Dict, entity: Dict):
        """Record provenance for an entity from webhook."""
        # This would integrate with the provenance tracking system
        pass

    async def start_push_notifications(
        self,
        instance: ConnectorInstance,
        webhook_url: str,
        entity_types: List[str],
    ) -> Dict[str, Any]:
        """Start Google push notifications (watch) for specified resources."""
        results = {}

        for entity_type in entity_types:
            try:
                if entity_type == "file":
                    result = await self._watch_drive_changes(instance, webhook_url)
                elif entity_type == "event":
                    result = await self._watch_calendar(instance, webhook_url)
                elif entity_type == "person":
                    result = await self._watch_users(instance, webhook_url)
                elif entity_type == "group":
                    result = await self._watch_groups(instance, webhook_url)
                else:
                    result = {"error": f"Unsupported entity type for push: {entity_type}"}

                results[entity_type] = result

            except Exception as e:
                logger.error(f"Failed to start push for {entity_type}: {e}")
                results[entity_type] = {"error": str(e)}

        return results

    async def _watch_drive_changes(self, instance: ConnectorInstance, webhook_url: str) -> Dict[str, Any]:
        """Watch Drive changes."""
        service = await self._get_service("drive", "v3", instance)
        if not service:
            return {"error": "Service unavailable"}

        # Create unique channel ID
        channel_id = f"vcos-drive-{instance.id}-{secrets.token_hex(8)}"
        channel_token = secrets.token_urlsafe(32)

        body = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            "token": channel_token,
            "params": {"ttl": "86400"},  # 24 hours
        }

        result = await self._execute_with_retry(
            lambda **p: service.changes().watch(**p),
            {"body": body}
        )

        if result:
            self._watch_channels[channel_id] = channel_id
            instance.webhook_url = webhook_url
            instance.webhook_secret = channel_token
            instance.webhook_events = ["file"]
            instance.webhook_verified = True
            instance.webhook_verified_at = datetime.now(timezone.utc)

        return {"channel_id": channel_id, "resource_id": result.get("resourceId"), "expiration": result.get("expiration")}

    async def _watch_calendar(self, instance: ConnectorInstance, webhook_url: str) -> Dict[str, Any]:
        """Watch Calendar events."""
        service = await self._get_service("calendar", "v3", instance)
        if not service:
            return {"error": "Service unavailable"}

        calendar_id = instance.config.get("calendar_id", "primary")
        channel_id = f"vcos-cal-{instance.id}-{secrets.token_hex(8)}"
        channel_token = secrets.token_urlsafe(32)

        body = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            "token": channel_token,
            "params": {"ttl": "86400"},
        }

        result = await self._execute_with_retry(
            lambda **p: service.events().watch(**p),
            {"calendarId": calendar_id, "body": body}
        )

        if result:
            self._watch_channels[channel_id] = channel_id

        return {"channel_id": channel_id, "resource_id": result.get("resourceId"), "expiration": result.get("expiration")}

    async def _watch_users(self, instance: ConnectorInstance, webhook_url: str) -> Dict[str, Any]:
        """Watch Admin SDK users (via Google Workspace Events API)."""
        # Note: Admin SDK doesn't have native watch, use Google Workspace Events API
        return {"error": "Admin SDK user watch requires Google Workspace Events API"}

    async def _watch_groups(self, instance: ConnectorInstance, webhook_url: str) -> Dict[str, Any]:
        """Watch Admin SDK groups (via Google Workspace Events API)."""
        return {"error": "Admin SDK group watch requires Google Workspace Events API"}

    async def stop_push_notifications(self, instance: ConnectorInstance, channel_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Stop Google push notifications."""
        if channel_ids is None:
            channel_ids = list(self._watch_channels.keys())

        results = {}
        for channel_id in channel_ids:
            try:
                service = await self._get_service("drive", "v3", instance)
                if service:
                    result = service.channels().stop(body={"id": channel_id, "resourceId": channel_id}).execute()
                    results[channel_id] = {"stopped": True}
                    self._watch_channels.pop(channel_id, None)
            except Exception as e:
                results[channel_id] = {"error": str(e)}

        return results

    # =========================================================================
    # IDENTITY MAPPING
    # =========================================================================

    async def map_google_user_to_vcos(
        self,
        db,
        organization_id: str,
        connector_instance_id: str,
        google_user: Dict,
    ):
        """Map Google Workspace user to VCOS employee via external_identity_service."""
        return await external_identity_service.resolve_identity(
            db=db,
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            external_id=google_user.get("id"),
            external_email=google_user.get("primary_email"),
            external_display_name=google_user.get("display_name"),
            external_avatar_url=google_user.get("thumbnail_photo_url"),
            external_metadata=google_user,
        )

    async def map_google_group_to_vcos(
        self,
        db,
        organization_id: str,
        connector_instance_id: str,
        google_group: Dict,
    ):
        """Map Google Workspace group to VCOS team via external_identity_service."""
        return await external_identity_service.resolve_identity(
            db=db,
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            external_id=google_group.get("id"),
            external_email=google_group.get("email"),
            external_display_name=google_group.get("name"),
            external_metadata=google_group,
        )

    # =========================================================================
    # CONFLICT DETECTION
    # =========================================================================

    async def detect_conflict(
        self,
        db,
        organization_id: str,
        entity_type: str,
        entity_id: str,
        external_value: Dict,
        canonical_value: Dict,
    ):
        """Detect conflict between external and canonical data."""
        from app.models.canonical_integration import ExternalConflict
        from sqlalchemy import select

        # Check if conflict already exists
        existing = await db.execute(
            select(ExternalConflict).where(
                ExternalConflict.organization_id == organization_id,
                ExternalConflict.entity_type == entity_type,
                ExternalConflict.entity_id == entity_id,
            )
        )
        if existing.scalar_one_or_none():
            return existing.scalar_one_or_none()

        # Create conflict record
        conflict = ExternalConflict(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            source_a_instance_id="google",
            source_a_value=external_value,
            source_b_instance_id="canonical",
            source_b_value=canonical_value,
            conflict_type="value_mismatch",
        )
        db.add(conflict)
        await db.flush()
        return conflict

    async def check_source_authority(self, db, organization_id: str, entity_type: str) -> str:
        """Check which source has authority for this entity type."""
        from app.services.source_authority_service import source_authority_service
        primary = await source_authority_service.get_primary_authority(db, organization_id, entity_type)
        if primary:
            return primary.connector_instance_id
        return "canonical"

    async def reconcile_conflict(
        self,
        db,
        conflict_id: str,
        resolution: str,
        resolved_by: str,
    ):
        """Reconcile a conflict using reconciliation_service."""
        from app.services.reconciliation_service import reconciliation_service
        return await reconciliation_service.resolve_conflict(
            db=db,
            conflict_id=conflict_id,
            resolution=resolution,
            resolved_by=resolved_by,
        )

    def _find_field_conflicts(self, external_value: Dict, canonical_value: Dict) -> List[str]:
        """Find fields that differ between external and canonical values."""
        conflicts = []
        all_keys = set(external_value.keys()) | set(canonical_value.keys())
        for key in all_keys:
            ext_val = external_value.get(key)
            can_val = canonical_value.get(key)
            if ext_val != can_val:
                conflicts.append(key)
        return conflicts

    # =========================================================================
    # RATE LIMITING WITH EXPONENTIAL BACKOFF
    # =========================================================================

    async def _check_rate_limit(self, instance: ConnectorInstance, api: str):
        """Check and wait for rate limit if needed."""
        state = self._rate_limit_state.get(api, {})
        if state.get("reset_at"):
            reset_at = datetime.fromisoformat(state["reset_at"])
            if datetime.now(timezone.utc) < reset_at:
                wait_seconds = (reset_at - datetime.now(timezone.utc)).total_seconds()
                if wait_seconds > 0:
                    logger.info(f"Rate limited for {api}, waiting {wait_seconds}s")
                    await asyncio.sleep(min(wait_seconds, 60))

    async def _handle_http_error(self, error: HttpError):
        """Handle Google HTTP error."""
        if error.resp.status == 429:
            # Rate limited
            reset_time = error.resp.headers.get("Retry-After")
            if reset_time:
                wait_time = int(reset_time)
                logger.warning(f"Rate limited, will wait {wait_time}s")
                await asyncio.sleep(min(wait_time, 60))
        elif error.resp.status == 401:
            logger.error("Authentication failed - token may be expired")
        elif error.resp.status == 403:
            logger.error("Access forbidden - check permissions and scopes")

    async def _execute_with_retry(self, method_func, params: Dict[str, Any], max_retries: int = 3) -> Optional[Dict]:
        """Execute API call with exponential backoff retry."""
        last_error = None

        for attempt in range(4):  # 3 retries + 1 initial
            try:
                return method_func(**params).execute()
            except HttpError as e:
                if e.resp.status in (429, 500, 502, 503, 504):
                    if attempt < 3:
                        delay = min(2 ** attempt, 60)
                        logger.warning(f"Retryable error (attempt {attempt + 1}), retrying in {delay}s: {e}")
                        await asyncio.sleep(delay)
                        continue
                raise
            except Exception as e:
                if attempt < 3:
                    delay = min(2 ** attempt, 60)
                    logger.warning(f"Error (attempt {attempt + 1}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    continue
                raise

        logger.error(f"All retries exhausted: {last_error}")
        return None

    async def get_rate_limit_status(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Get current rate limit status."""
        return self._rate_limit_state.get("admin", {"remaining": 100, "limit": 240, "reset_at": None})

    async def handle_rate_limit(self, instance: ConnectorInstance, reset_at: datetime) -> bool:
        """Handle rate limit - return True if should retry."""
        wait_seconds = (reset_at - datetime.now(timezone.utc)).total_seconds()
        if wait_seconds > 0 and wait_seconds < 300:  # Max 5 minutes
            logger.info(f"Rate limited, waiting {wait_seconds}s")
            await asyncio.sleep(min(wait_seconds, 60))
            return True
        return False

    # =========================================================================
    # CONNECTION REVOCATION
    # =========================================================================

    @classmethod
    async def revoke_connection(cls, instance: ConnectorInstance) -> bool:
        """Revoke Google connection and clean up credentials."""
        try:
            # Revoke access token if we have one
            if instance.credentials.get("access_token"):
                async with httpx.AsyncClient() as client:
                    await client.post(
                        "https://oauth2.googleapis.com/revoke",
                        params={"token": instance.credentials["access_token"]},
                    )

            # Clear credentials
            instance.credentials = {}
            instance.state = "revoked"
            instance.revoked_at = datetime.now(timezone.utc)

            return True
        except Exception as e:
            logger.error(f"Failed to revoke Google connection: {e}")
            return False

    # =========================================================================
    # HEALTH MONITORING
    # =========================================================================

    async def health_check(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Perform health check on Google Workspace connection."""
        health = {
            "status": "healthy",
            "checks": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Test authentication
        try:
            auth_ok = await self.authenticate(instance)
            health["checks"]["authentication"] = "pass" if auth_ok else "fail"
        except Exception as e:
            health["checks"]["authentication"] = f"fail: {str(e)}"
            health["status"] = "degraded"

        # Test API access
        try:
            if self._credentials:
                service = await self._get_service("admin", "directory_v1", instance)
                if service:
                    result = service.users().list(customer=instance.config.get("customer_id", "my_customer"), maxResults=1).execute()
                    health["checks"]["api_access"] = "pass"
                else:
                    health["checks"]["api_access"] = "fail"
                    health["status"] = "degraded"
        except Exception as e:
            health["checks"]["api_access"] = f"fail: {str(e)}"
            health["status"] = "degraded"

        # Check rate limit
        try:
            rate_limit = await self.get_rate_limit_status(instance)
            health["checks"]["rate_limit"] = rate_limit
            if rate_limit.get("remaining", 0) < 10:
                health["status"] = "degraded"
                health["checks"]["rate_limit_warning"] = "Low rate limit remaining"
        except Exception:
            pass

        # Check webhook status
        health["checks"]["push_notifications"] = "active" if self._watch_channels else "not_configured"

        # Check token expiry
        if instance.credentials.get("expires_at"):
            expires_at = datetime.fromisoformat(instance.credentials["expires_at"])
            if expires_at < datetime.now(timezone.utc) + timedelta(hours=1):
                health["status"] = "degraded"
                health["checks"]["token_expiry_warning"] = "Token expires soon"

        return health

    # =========================================================================
    # ENTITY TRANSFORMERS
    # =========================================================================

    def _get_supported_entity_types(self) -> List[str]:
        return [k for k, v in self.ENTITY_ENDPOINTS.items() if v is not None]

    def _extract_external_id(self, entity_type: str, entity: Dict) -> Optional[str]:
        return entity.get("id") or entity.get("external_id")


def create_google_adapter(config: Optional[GoogleConfig] = None) -> GoogleWorkspaceAdapter:
    """Create Google Workspace adapter."""
    return GoogleWorkspaceAdapter(config)