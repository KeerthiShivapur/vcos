"""Jira Connector Adapter — production-grade implementation."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict
from dataclasses import dataclass

import httpx
from jira import JIRA
from jira.exceptions import JIRAError

from app.services.base_adapter import BaseConnectorAdapter
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.integration.jira")


@dataclass
class JiraConfig:
    """Jira connector configuration."""
    server_url: str
    email: Optional[str] = None
    api_token: Optional[str] = None
    oauth_token: Optional[str] = None
    personal_access_token: Optional[str] = None


class JiraAdapter(BaseConnectorAdapter):
    """Jira connector adapter with full REST API support."""
    
    provider_name = "jira"
    
    ENTITY_ENDPOINTS = {
        "person": "users",
        "group": "groups",
        "channel": None,
        "message": None,
        "file": "attachments",
        "event": None,
        "contact": None,
        "repository": None,
        "issue": "issues",
        "pull_request": None,
        "commit": None,
        "project": "projects",
        "task": "issues",
        "customer": None,
        "deal": None,
        "organization": None,
        "employee": "users",
        "department": None,
        "role": None,
    }
    
    def __init__(self, config: Optional[JiraConfig] = None):
        super().__init__()
        self.config = config
        self._jira: Optional[JIRA] = None
        self._rate_limit_state: Dict[str, Dict[str, Any]] = {}
    
    async def authenticate(self, instance: ConnectorInstance) -> bool:
        """Authenticate with Jira using API token or OAuth."""
        try:
            creds_dict = instance.credentials
            if not creds_dict:
                return False
            
            server_url = creds_dict.get("server_url") or self.config.server_url
            if not server_url:
                return False
            
            # Try API token + email
            email = creds_dict.get("email")
            api_token = creds_dict.get("api_token")
            if email and api_token:
                self._jira = JIRA(
                    server=server_url,
                    basic_auth=(email, api_token),
                )
                # Test authentication
                _ = self._jira.myself()
                return True
            
            # Try OAuth token
            oauth_token = creds_dict.get("oauth_token")
            if oauth_token:
                self._jira = JIRA(
                    server=server_url,
                    oauth={"access_token": oauth_token},
                )
                _ = self._jira.myself()
                return True
            
            # Try personal access token
            pat = creds_dict.get("personal_access_token")
            if pat:
                self._jira = JIRA(
                    server=server_url,
                    token_auth=pat,
                )
                _ = self._jira.myself()
                return True
            
            return False
            
        except JIRAError as e:
            logger.error(f"Jira authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Jira authentication failed: {e}")
            return False
    
    async def test_connection(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Test connection to Jira."""
        try:
            if not await self.authenticate(instance):
                return {"success": False, "error": "Authentication failed"}
            
            myself = self._jira.myself()
            return {
                "success": True,
                "user": myself.get("displayName"),
                "account_id": myself.get("accountId"),
                "email": myself.get("emailAddress"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def authenticate(self, instance: ConnectorInstance) -> bool:
        """Authenticate with Jira."""
        try:
            creds_dict = instance.credentials
            if not creds_dict:
                return False
            
            server_url = creds_dict.get("server_url") or self.config.server_url
            if not server_url:
                return False
            
            email = creds_dict.get("email")
            api_token = creds_dict.get("api_token")
            if email and api_token:
                self._jira = JIRA(
                    server=server_url,
                    basic_auth=(email, api_token),
                )
                _ = self._jira.myself()
                return True
            
            oauth_token = creds_dict.get("oauth_token")
            if oauth_token:
                self._jira = JIRA(
                    server=server_url,
                    oauth={"access_token": oauth_token},
                )
                _ = self._jira.myself()
                return True
            
            pat = creds_dict.get("personal_access_token")
            if pat:
                self._jira = JIRA(
                    server=server_url,
                    token_auth=pat,
                )
                _ = self._jira.myself()
                return True
            
            return False
            
        except JIRAError as e:
            logger.error(f"Jira authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Jira authentication failed: {e}")
            return False
    
    async def test_connection(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Test connection to Jira."""
        try:
            if not await self.authenticate(instance):
                return {"success": False, "error": "Authentication failed"}
            
            myself = self._jira.myself()
            return {
                "success": True,
                "user": myself.get("displayName"),
                "account_id": myself.get("accountId"),
                "email": myself.get("emailAddress"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    ENTITY_ENDPOINTS = {
        "person": "users",
        "group": "groups",
        "channel": None,
        "message": None,
        "file": "attachments",
        "event": None,
        "contact": None,
        "repository": None,
        "issue": "issues",
        "pull_request": None,
        "commit": None,
        "project": "projects",
        "task": "issues",
        "customer": None,
        "deal": None,
        "organization": None,
        "employee": "users",
        "department": None,
        "role": None,
    }
    
    async def fetch_page(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """Fetch a page of entities from Jira."""
        if not self._jira:
            if not await self.authenticate(instance):
                return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        try:
            entities = []
            next_cursor = None
            
            if entity_type == "issue" or entity_type == "task":
                # JQL query for issues
                jql_parts = []
                
                if since:
                    jql_parts.append(f"updated >= '{since.strftime('%Y-%m-%d %H:%M')}'")
                
                project_key = instance.config.get("project_key")
                if project_key:
                    jql_parts.append(f"project = {project_key}")
                
                jql = " AND ".join(jql_parts) if jql_parts else "ORDER BY updated DESC"
                
                # Handle pagination
                start_at = int(cursor) if cursor and cursor.isdigit() else 0
                
                issues = self._jira.search_issues(
                    jql_str=jql,
                    startAt=start_at,
                    maxResults=min(page_size, 1000),
                    fields="*all",
                    expand="changelog",
                )
                
                entities = [self._issue_to_dict(issue) for issue in issues]
                next_cursor = str(start_at + len(issues)) if len(issues) == page_size else None
                
            elif entity_type == "project":
                projects = self._jira.projects()
                entities = [self._project_to_dict(p) for p in projects]
                next_cursor = None
            
            elif entity_type == "person" or entity_type == "employee":
                # Jira users
                users = self._jira.search_users(query="", maxResults=page_size)
                entities = [self._user_to_dict(u) for u in users]
                next_cursor = None
            
            elif entity_type == "group":
                # Jira groups
                groups = self._jira.groups()
                entities = [{"id": g, "name": g, "external_id": g} for g in groups]
                next_cursor = None
            
            else:
                entities = []
                next_cursor = None
            
            return {
                "entities": entities,
                "next_cursor": next_cursor,
                "has_more": bool(next_cursor),
                "total_count": len(entities),
            }
            
        except JIRAError as e:
            logger.error(f"Jira API error fetching {entity_type}: {e}")
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}
        except Exception as e:
            logger.error(f"Error fetching {entity_type} from Jira: {e}")
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0, "error": str(e)}
    
    async def fetch_entity(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        external_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single entity by external ID."""
        if not self._jira:
            if not await self.authenticate(instance):
                return None
        
        try:
            if entity_type == "issue" or entity_type == "task":
                issue = self._jira.issue(external_id, expand="changelog,transitions")
                return self._issue_to_dict(issue)
            
            elif entity_type == "project":
                project = self._jira.project(external_id)
                return self._project_to_dict(project)
            
            elif entity_type == "person" or entity_type == "employee":
                # Get user by account ID
                user = self._jira.user(external_id)
                return self._user_to_dict(user)
            
            return None
            
        except JIRAError as e:
            if e.status_code == 404:
                return None
            logger.error(f"Jira API error fetching entity {external_id}: {e}")
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
        return []
    
    async def authenticate(self, instance: ConnectorInstance) -> bool:
        """Authenticate with Jira."""
        try:
            creds_dict = instance.credentials
            if not creds_dict:
                return False
            
            server_url = creds_dict.get("server_url") or self.config.server_url
            if not server_url:
                return False
            
            email = creds_dict.get("email")
            api_token = creds_dict.get("api_token")
            if email and api_token:
                self._jira = JIRA(
                    server=server_url,
                    basic_auth=(email, api_token),
                )
                _ = self._jira.myself()
                return True
            
            oauth_token = creds_dict.get("oauth_token")
            if oauth_token:
                self._jira = JIRA(
                    server=server_url,
                    oauth={"access_token": oauth_token},
                )
                _ = self._jira.myself()
                return True
            
            pat = creds_dict.get("personal_access_token")
            if pat:
                self._jira = JIRA(
                    server=server_url,
                    token_auth=pat,
                )
                _ = self._jira.myself()
                return True
            
            return False
            
        except JIRAError as e:
            logger.error(f"Jira authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Jira authentication failed: {e}")
            return False
    
    async def test_connection(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Test connection to Jira."""
        try:
            if not await self.authenticate(instance):
                return {"success": False, "error": "Authentication failed"}
            
            myself = self._jira.myself()
            return {
                "success": True,
                "user": myself.get("displayName"),
                "account_id": myself.get("accountId"),
                "email": myself.get("emailAddress"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def fetch_entity(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        external_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single entity by external ID."""
        if not self._jira:
            if not await self.authenticate(instance):
                return None
        
        try:
            if entity_type == "issue" or entity_type == "task":
                issue = self._jira.issue(external_id, expand="changelog,transitions")
                return self._issue_to_dict(issue)
            
            elif entity_type == "project":
                project = self._jira.project(external_id)
                return self._project_to_dict(project)
            
            elif entity_type == "person" or entity_type == "employee":
                user = self._jira.user(external_id)
                return self._user_to_dict(user)
            
            return None
            
        except JIRAError as e:
            if e.status_code == 404:
                return None
            logger.error(f"Jira API error fetching entity {external_id}: {e}")
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
        return []
    
    async def get_rate_limit_status(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Get current rate limit status."""
        return self._rate_limit_state.get("default", {"remaining": 100, "reset_at": None})
    
    async def handle_rate_limit(self, instance: ConnectorInstance, reset_at: datetime) -> bool:
        """Handle rate limit - return True if should retry."""
        wait_seconds = (reset_at - datetime.now(timezone.utc)).total_seconds()
        if wait_seconds > 0 and wait_seconds < 300:
            await asyncio.sleep(min(wait_seconds, 60))
            return True
        return False
    
    ENTITY_ENDPOINTS = {
        "person": "users",
        "group": "groups",
        "channel": None,
        "message": None,
        "file": "attachments",
        "event": None,
        "contact": None,
        "repository": None,
        "issue": "issues",
        "pull_request": None,
        "commit": None,
        "project": "projects",
        "task": "issues",
        "customer": None,
        "deal": None,
        "organization": None,
        "employee": "users",
        "department": None,
        "role": None,
    }
    
    async def authenticate(self, instance: ConnectorInstance) -> bool:
        """Authenticate with Jira."""
        try:
            creds_dict = instance.credentials
            if not creds_dict:
                return False
            
            server_url = creds_dict.get("server_url") or self.config.server_url
            if not server_url:
                return False
            
            email = creds_dict.get("email")
            api_token = creds_dict.get("api_token")
            if email and api_token:
                self._jira = JIRA(
                    server=server_url,
                    basic_auth=(email, api_token),
                )
                _ = self._jira.myself()
                return True
            
            oauth_token = creds_dict.get("oauth_token")
            if oauth_token:
                self._jira = JIRA(
                    server=server_url,
                    oauth={"access_token": oauth_token},
                )
                _ = self._jira.myself()
                return True
            
            pat = creds_dict.get("personal_access_token")
            if pat:
                self._jira = JIRA(
                    server=server_url,
                    token_auth=pat,
                )
                _ = self._jira.myself()
                return True
            
            return False
            
        except JIRAError as e:
            logger.error(f"Jira authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Jira authentication failed: {e}")
            return False
    
    async def test_connection(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Test connection to Jira."""
        try:
            if not await self.authenticate(instance):
                return {"success": False, "error": "Authentication failed"}
            
            myself = self._jira.myself()
            return {
                "success": True,
                "user": myself.get("displayName"),
                "account_id": myself.get("accountId"),
                "email": myself.get("emailAddress"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def fetch_entity(
        self,
        instance: ConnectorInstance,
        entity_type: str,
        external_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single entity by external ID."""
        if not self._jira:
            if not await self.authenticate(instance):
                return None
        
        try:
            if entity_type == "issue" or entity_type == "task":
                issue = self._jira.issue(external_id, expand="changelog,transitions")
                return self._issue_to_dict(issue)
            
            elif entity_type == "project":
                project = self._jira.project(external_id)
                return self._project_to_dict(project)
            
            elif entity_type == "person" or entity_type == "employee":
                user = self._jira.user(external_id)
                return self._user_to_dict(user)
            
            return None
            
        except JIRAError as e:
            if e.status_code == 404:
                return None
            logger.error(f"Jira API error fetching entity {external_id}: {e}")
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
        return []
    
    async def get_rate_limit_status(self, instance: ConnectorInstance) -> Dict[str, Any]:
        """Get current rate limit status."""
        return self._rate_limit_state.get("default", {"remaining": 100, "reset_at": None})
    
    async def handle_rate_limit(self, instance: ConnectorInstance, reset_at: datetime) -> bool:
        """Handle rate limit - return True if should retry."""
        wait_seconds = (reset_at - datetime.now(timezone.utc)).total_seconds()
        if wait_seconds > 0 and wait_seconds < 300:
            await asyncio.sleep(min(wait_seconds, 60))
            return True
        return False
    
    def _get_supported_entity_types(self) -> List[str]:
        return [k for k, v in self.ENTITY_ENDPOINTS.items() if v is not None]
    
    # Entity transformers
    def _issue_to_dict(self, issue) -> Dict[str, Any]:
        """Convert Jira Issue to dict."""
        fields = issue.fields
        return {
            "id": issue.key,
            "external_id": issue.key,
            "id_numeric": issue.id,
            "summary": fields.summary,
            "description": getattr(fields, 'description', None),
            "status": fields.status.name if fields.status else None,
            "status_category": fields.status.statusCategory.name if fields.status and fields.status.statusCategory else None,
            "priority": fields.priority.name if fields.priority else None,
            "issuetype": fields.issuetype.name if fields.issuetype else None,
            "assignee": {
                "accountId": fields.assignee.accountId,
                "displayName": fields.assignee.displayName,
                "email": fields.assignee.emailAddress,
            } if fields.assignee else None,
            "reporter": {
                "accountId": fields.reporter.accountId,
                "displayName": fields.reporter.displayName,
                "email": fields.reporter.emailAddress,
            } if fields.reporter else None,
            "project": {
                "key": fields.project.key,
                "name": fields.project.name,
            } if fields.project else None,
            "labels": fields.labels,
            "components": [c.name for c in fields.components] if fields.components else [],
            "fixVersions": [v.name for v in fields.fixVersions] if fields.fixVersions else [],
            "affectsVersions": [v.name for v in fields.versions] if fields.versions else [],
            "created": fields.created,
            "updated": fields.updated,
            "resolution": fields.resolution.name if fields.resolution else None,
            "resolution_date": fields.resolutiondate,
            "duedate": fields.duedate,
            "timeestimate": fields.timeestimate,
            "timespent": fields.timespent,
            "timeoriginalestimate": fields.timeoriginalestimate,
            "votes": fields.votes.votes if fields.votes else 0,
            "watches": fields.watches.watchCount if fields.watches else 0,
        }
    
    def _project_to_dict(self, project) -> Dict[str, Any]:
        return {
            "id": project.key,
            "external_id": project.key,
            "key": project.key,
            "name": project.name,
            "description": getattr(project, 'description', None),
            "lead": {
                "accountId": project.lead.accountId,
                "displayName": project.lead.displayName,
            } if hasattr(project, 'lead') and project.lead else None,
            "url": project.self,
            "projectTypeKey": project.projectTypeKey,
        }
    
    def _user_to_dict(self, user) -> Dict[str, Any]:
        return {
            "id": user.accountId,
            "external_id": user.accountId,
            "account_id": user.accountId,
            "display_name": user.displayName,
            "email": getattr(user, 'emailAddress', None),
            "active": user.active,
            "time_zone": getattr(user, 'timeZone', None),
            "locale": getattr(user, 'locale', None),
        }
    
    def _get_supported_entity_types(self) -> List[str]:
        return [k for k, v in self.ENTITY_ENDPOINTS.items() if v is not None]
    
    def _extract_external_id(self, entity_type: str, entity: Dict) -> Optional[str]:
        return entity.get("id") or entity.get("external_id") or entity.get("key")


def create_jira_adapter(config: Optional[JiraConfig] = None) -> JiraAdapter:
    """Create Jira adapter."""
    return JiraAdapter(config)