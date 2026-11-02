from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, Request
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import uuid
import json

router = APIRouter(prefix="/integrations", tags=["integrations"])


class ConnectorCategory(str, Enum):
    IDENTITY = "identity"
    HRIS = "hris"
    ATS = "ats"
    CRM = "crm"
    COMMUNICATION = "communication"
    CALENDAR = "calendar"
    STORAGE = "storage"
    PROJECT_MGMT = "project_mgmt"
    FINANCE = "finance"
    BI_ANALYTICS = "bi_analytics"
    DEVOPS = "devops"


class ConnectorStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    PENDING = "pending"
    DEPRECATED = "deprecated"


class AuthType(str, Enum):
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    SAML = "saml"
    API_KEY = "api_key"
    BASIC_AUTH = "basic_auth"
    JWT = "jwt"


class ConnectorBase(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    logo_url: Optional[str] = None
    documentation_url: Optional[str] = None
    auth_type: str
    config_schema: Dict[str, Any] = {}
    required_scopes: List[str] = []
    supported_operations: List[str] = []
    webhook_events: List[str] = []
    rate_limits: Dict[str, int] = {}
    is_active: bool = True
    version: str = "1.0.0"


class ConnectorCreate(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    logo_url: Optional[str] = None
    documentation_url: Optional[str] = None
    auth_type: str
    config_schema: Dict[str, Any] = {}
    required_scopes: List[str] = []
    supported_operations: List[str] = []
    webhook_events: List[str] = []
    rate_limits: Dict[str, int] = {}
    is_active: bool = True
    version: str = "1.0.0"


class ConnectorUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    documentation_url: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None
    required_scopes: Optional[List[str]] = None
    supported_operations: Optional[List[str]] = None
    webhook_events: Optional[List[str]] = None
    rate_limits: Optional[Dict[str, int]] = None
    is_active: Optional[bool] = None
    version: Optional[str] = None


class ConnectorResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    category: str
    logo_url: Optional[str] = None
    documentation_url: Optional[str] = None
    auth_type: str
    config_schema: Dict[str, Any] = {}
    required_scopes: List[str] = []
    supported_operations: List[str] = []
    webhook_events: List[str] = []
    rate_limits: Dict[str, int] = {}
    is_active: bool = True
    version: str = "1.0.0"
    id: str
    created_at: str
    updated_at: str
    created_by: str
    status: str = "active"
    last_sync: Optional[str] = None
    sync_status: Optional[str] = None
    error_message: Optional[str] = None


class ConnectionBase(BaseModel):
    connector_id: str
    name: str
    config: Dict[str, Any] = {}
    field_mappings: Dict[str, str] = {}
    sync_schedule: Optional[str] = None
    is_active: bool = True
    sync_direction: str = "bidirectional"


class ConnectionCreate(ConnectionBase):
    organization_id: str


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    field_mappings: Optional[Dict[str, str]] = None
    sync_schedule: Optional[str] = None
    is_active: Optional[bool] = None
    sync_direction: Optional[str] = None


class ConnectionResponse(BaseModel):
    id: str
    organization_id: str
    connector_id: str
    name: str
    config: Dict[str, Any] = {}
    field_mappings: Dict[str, str] = {}
    sync_schedule: Optional[str] = None
    is_active: bool = True
    sync_direction: str = "bidirectional"
    connector: Dict
    created_at: str
    updated_at: str
    created_by: str
    status: str = "pending"
    last_sync: Optional[str] = None
    last_error: Optional[str] = None
    sync_stats: Dict[str, int] = {}


class SyncJobBase(BaseModel):
    connection_id: str
    operation: str
    direction: str = "pull"
    filters: Dict[str, Any] = {}
    dry_run: bool = False


class SyncJobResponse(BaseModel):
    id: str
    connection_id: str
    operation: str
    direction: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_failed: int = 0
    error_message: Optional[str] = None
    logs: List[str] = []


# DEFAULT_CONNECTORS with 10 connectors
DEFAULT_CONNECTORS = {
    "slack": {
        "name": "slack",
        "display_name": "Slack",
        "description": "Team communication and collaboration platform",
        "category": "communication",
        "logo_url": "https://cdn.vcos.io/connectors/slack.png",
        "documentation_url": "https://docs.vcos.io/integrations/slack",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "scopes": {"type": "array", "items": {"type": "string"}}
            }
        },
        "required_scopes": ["channels:read", "chat:write", "users:read"],
        "supported_operations": ["send_message", "create_channel", "invite_user", "get_channels", "get_users"],
        "webhook_events": ["message", "reaction_added", "channel_created", "member_joined"],
        "rate_limits": {"requests_per_minute": 50},
    },
    "google_workspace": {
        "name": "google_workspace",
        "display_name": "Google Workspace",
        "description": "Google's productivity and collaboration suite",
        "category": "identity",
        "logo_url": "https://cdn.vcos.io/connectors/google.png",
        "documentation_url": "https://docs.vcos.io/integrations/google-workspace",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "scopes": {"type": "array", "items": {"type": "string"}}
            }
        },
        "required_scopes": ["https://www.googleapis.com/auth/admin.directory.user.readonly"],
        "supported_operations": ["list_users", "create_user", "update_user", "delete_user", "get_groups", "create_group"],
        "webhook_events": ["user_created", "user_updated", "user_deleted", "group_created"],
        "rate_limits": {"requests_per_minute": 100},
    },
    "github": {
        "name": "github",
        "display_name": "GitHub",
        "description": "Code hosting and version control platform",
        "category": "devops",
        "logo_url": "https://cdn.vcos.io/connectors/github.png",
        "documentation_url": "https://docs.vcos.io/integrations/github",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "scopes": {"type": "array", "items": {"type": "string"}}
            }
        },
        "required_scopes": ["repo", "user", "admin:org"],
        "supported_operations": ["list_repos", "create_repo", "create_issue", "create_pr", "get_commits", "get_workflows"],
        "webhook_events": ["push", "pull_request", "issues", "release", "workflow_run"],
        "rate_limits": {"requests_per_hour": 5000},
    },
    "jira": {
        "name": "jira",
        "display_name": "Jira",
        "description": "Project and issue tracking for software teams",
        "category": "project_mgmt",
        "logo_url": "https://cdn.vcos.io/connectors/jira.png",
        "documentation_url": "https://docs.vcos.io/integrations/jira",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "base_url": {"type": "string"},
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"}
            }
        },
        "required_scopes": ["read:jira-work", "write:jira-work", "manage:jira-project"],
        "supported_operations": ["list_issues", "create_issue", "update_issue", "transition_issue", "search_issues", "get_projects"],
        "webhook_events": ["issue_created", "issue_updated", "issue_deleted", "comment_added"],
        "rate_limits": {"requests_per_minute": 100},
    },
    "salesforce": {
        "name": "salesforce",
        "display_name": "Salesforce",
        "description": "Customer relationship management platform",
        "category": "crm",
        "logo_url": "https://cdn.vcos.io/connectors/salesforce.png",
        "documentation_url": "https://docs.vcos.io/integrations/salesforce",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "login_url": {"type": "string", "default": "https://login.salesforce.com"}
            }
        },
        "required_scopes": ["api", "refresh_token", "offline_access"],
        "supported_operations": ["query", "create", "update", "delete", "upsert", "describe"],
        "webhook_events": ["created", "updated", "deleted"],
        "rate_limits": {"requests_per_minute": 100},
    },
    "jira": {
        "name": "jira",
        "display_name": "Jira",
        "description": "Project and issue tracking for software teams",
        "category": "project_mgmt",
        "logo_url": "https://cdn.vcos.io/connectors/jira.png",
        "documentation_url": "https://docs.vcos.io/integrations/jira",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "base_url": {"type": "string"},
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"}
            }
        },
        "required_scopes": ["read:jira-work", "write:jira-work", "manage:jira-project"],
        "supported_operations": ["list_issues", "create_issue", "update_issue", "transition_issue", "search_issues", "get_projects"],
        "webhook_events": ["issue_created", "issue_updated", "issue_deleted", "comment_added"],
        "rate_limits": {"requests_per_minute": 100},
    },
    "slack": {
        "name": "slack",
        "display_name": "Slack",
        "description": "Team communication and collaboration platform",
        "category": "communication",
        "logo_url": "https://cdn.vcos.io/connectors/slack.png",
        "documentation_url": "https://docs.vcos.io/integrations/slack",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "scopes": {"type": "array", "items": {"type": "string"}}
            }
        },
        "required_scopes": ["channels:read", "chat:write", "users:read"],
        "supported_operations": ["send_message", "create_channel", "invite_user", "get_channels", "get_users"],
        "webhook_events": ["message", "reaction_added", "channel_created", "member_joined"],
        "rate_limits": {"requests_per_minute": 50},
    },
    "google_workspace": {
        "name": "google_workspace",
        "display_name": "Google Workspace",
        "description": "Google's productivity and collaboration suite",
        "category": "identity",
        "logo_url": "https://cdn.vcos.io/connectors/google.png",
        "documentation_url": "https://docs.vcos.io/integrations/google-workspace",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "scopes": {"type": "array", "items": {"type": "string"}}
            }
        },
        "required_scopes": ["https://www.googleapis.com/auth/admin.directory.user.readonly"],
        "supported_operations": ["list_users", "create_user", "update_user", "delete_user", "get_groups", "create_group"],
        "webhook_events": ["user_created", "user_updated", "user_deleted", "group_created"],
        "rate_limits": {"requests_per_minute": 100},
    },
    "asana": {
        "name": "asana",
        "display_name": "Asana",
        "description": "Work management platform for teams",
        "category": "project_mgmt",
        "logo_url": "https://cdn.vcos.io/connectors/asana.png",
        "documentation_url": "https://docs.vcos.io/integrations/asana",
        "auth_type": "api_key",
        "config_schema": {
            "type": "object",
            "properties": {
                "access_token": {"type": "string"},
                "workspace_gid": {"type": "string"}
            }
        },
        "required_scopes": [],
        "supported_operations": ["list_users", "list_projects", "list_tasks", "list_teams", "create_task", "update_task", "create_project", "create_comment"],
        "webhook_events": ["task.created", "task.updated", "task.deleted", "task.completed", "project.created", "project.updated", "story.created", "attachment.created"],
        "rate_limits": {"requests_per_minute": 1500, "burst": 100},
    },
    "monday": {
        "name": "monday",
        "display_name": "Monday.com",
        "description": "Work OS for project and team management",
        "category": "project_mgmt",
        "logo_url": "https://cdn.vcos.io/connectors/monday.png",
        "documentation_url": "https://docs.vcos.io/integrations/monday",
        "auth_type": "api_key",
        "config_schema": {
            "type": "object",
            "properties": {
                "api_token": {"type": "string"}
            }
        },
        "required_scopes": [],
        "supported_operations": ["list_users", "list_boards", "list_items", "list_groups", "create_item", "update_item", "create_board", "add_column"],
        "webhook_events": ["item.created", "item.updated", "item.deleted", "column.value.changed", "item.moved", "board.created", "column.created"],
        "rate_limits": {"requests_per_minute": 60, "complexity": {"points_per_minute": 5000000}},
    },
    "salesforce": {
        "name": "salesforce",
        "display_name": "Salesforce",
        "description": "Customer relationship management platform",
        "category": "crm",
        "logo_url": "https://cdn.vcos.io/connectors/salesforce.png",
        "documentation_url": "https://docs.vcos.io/integrations/salesforce",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "login_url": {"type": "string", "default": "https://login.salesforce.com"}
            }
        },
        "required_scopes": ["api", "refresh_token", "offline_access"],
        "supported_operations": ["query", "create", "update", "delete", "upsert", "describe"],
        "webhook_events": ["created", "updated", "deleted"],
        "rate_limits": {"requests_per_minute": 100},
    },
    "hubspot": {
        "name": "hubspot",
        "display_name": "HubSpot",
        "description": "Inbound marketing, sales, and service platform",
        "category": "crm",
        "logo_url": "https://cdn.vcos.io/connectors/hubspot.png",
        "documentation_url": "https://docs.vcos.io/integrations/hubspot",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "scopes": {"type": "array", "items": {"type": "string"}}
            }
        },
        "required_scopes": ["contacts", "companies", "deals", "tickets", "automation", "content", "oauth", "reports"],
        "supported_operations": ["list_contacts", "create_contact", "update_contact", "list_companies", "create_company", "list_deals", "create_deal", "list_tickets", "create_ticket"],
        "webhook_events": ["contact.creation", "contact.propertyChange", "contact.deletion", "company.creation", "company.propertyChange", "deal.creation", "deal.propertyChange", "ticket.creation", "ticket.propertyChange"],
        "rate_limits": {"requests_per_second": 100, "daily": {"limit": 4000000}},
    },
    "linear": {
        "name": "linear",
        "display_name": "Linear",
        "description": "Issue tracking and project management for software teams",
        "category": "project_mgmt",
        "logo_url": "https://cdn.vcos.io/connectors/linear.png",
        "documentation_url": "https://docs.vcos.io/integrations/linear",
        "auth_type": "api_key",
        "config_schema": {
            "type": "object",
            "properties": {
                "api_key": {"type": "string"}
            }
        },
        "required_scopes": [],
        "supported_operations": ["list_users", "list_teams", "list_issues", "list_projects", "list_cycles", "create_issue", "update_issue", "create_project", "create_comment", "create_cycle"],
        "webhook_events": ["issue.created", "issue.updated", "issue.deleted", "comment.created", "comment.updated", "issue.moved", "cycle.created", "cycle.updated"],
        "rate_limits": {"requests_per_minute": 300, "complexity": {"points_per_minute": 1000}},
    },
    "monday": {
        "name": "monday",
        "display_name": "Monday.com",
        "description": "Work OS for project and team management",
        "category": "project_mgmt",
        "logo_url": "https://cdn.vcos.io/connectors/monday.png",
        "documentation_url": "https://docs.vcos.io/integrations/monday",
        "auth_type": "api_key",
        "config_schema": {
            "type": "object",
            "properties": {
                "api_token": {"type": "string"}
            }
        },
        "required_scopes": [],
        "supported_operations": ["list_users", "list_boards", "list_items", "list_groups", "create_item", "update_item", "create_board", "add_column"],
        "webhook_events": ["item.created", "item.updated", "item.deleted", "column.value.changed", "item.moved", "board.created", "column.created"],
        "rate_limits": {"requests_per_minute": 60, "complexity": {"points_per_minute": 5000000}},
    },
}


# Build connector registry
connector_registry = {}
for key, config in DEFAULT_CONNECTORS.items():
    connector_registry[key] = {
        "id": key,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "created_by": "system",
        "status": "active",
        **config
    }


# Pydantic Models
class ConnectorCategory(str, Enum):
    IDENTITY = "identity"
    HRIS = "hris"
    ATS = "ats"
    CRM = "crm"
    COMMUNICATION = "communication"
    CALENDAR = "calendar"
    STORAGE = "storage"
    PROJECT_MGMT = "project_mgmt"
    FINANCE = "finance"
    BI_ANALYTICS = "bi_analytics"
    DEVOPS = "devops"


class ConnectorStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    PENDING = "pending"
    DEPRECATED = "deprecated"


class AuthType(str, Enum):
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    SAML = "saml"
    API_KEY = "api_key"
    BASIC_AUTH = "basic_auth"
    JWT = "jwt"


class ConnectorStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    PENDING = "pending"
    DEPRECATED = "deprecated"


class AuthType(str, Enum):
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    SAML = "saml"
    API_KEY = "api_key"
    BASIC_AUTH = "basic_auth"
    JWT = "jwt"


class ConnectorBase(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    logo_url: Optional[str] = None
    documentation_url: Optional[str] = None
    auth_type: str
    config_schema: Dict[str, Any] = {}
    required_scopes: List[str] = []
    supported_operations: List[str] = []
    webhook_events: List[str] = []
    rate_limits: Dict[str, int] = {}
    is_active: bool = True
    version: str = "1.0.0"


class ConnectorCreate(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    logo_url: Optional[str] = None
    documentation_url: Optional[str] = None
    auth_type: str
    config_schema: Dict[str, Any] = {}
    required_scopes: List[str] = []
    supported_operations: List[str] = []
    webhook_events: List[str] = []
    rate_limits: Dict[str, int] = {}
    is_active: bool = True
    version: str = "1.0.0"


class ConnectorUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    documentation_url: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None
    required_scopes: Optional[List[str]] = None
    supported_operations: Optional[List[str]] = None
    webhook_events: Optional[List[str]] = None
    rate_limits: Optional[Dict[str, int]] = None
    is_active: Optional[bool] = None
    version: Optional[str] = None


class ConnectorResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    category: str
    logo_url: Optional[str] = None
    documentation_url: Optional[str] = None
    auth_type: str
    config_schema: Dict[str, Any] = {}
    required_scopes: List[str] = []
    supported_operations: List[str] = []
    webhook_events: List[str] = []
    rate_limits: Dict[str, int] = {}
    is_active: bool = True
    version: str = "1.0.0"
    id: str
    created_at: str
    updated_at: str
    created_by: str
    status: str = "active"
    last_sync: Optional[str] = None
    sync_status: Optional[str] = None
    error_message: Optional[str] = None


class ConnectionBase(BaseModel):
    connector_id: str
    name: str
    config: Dict[str, Any] = {}
    field_mappings: Dict[str, str] = {}
    sync_schedule: Optional[str] = None
    is_active: bool = True
    sync_direction: str = "bidirectional"


class ConnectionCreate(ConnectionBase):
    organization_id: str


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    field_mappings: Optional[Dict[str, str]] = None
    sync_schedule: Optional[str] = None
    is_active: Optional[bool] = None
    sync_direction: Optional[str] = None


class ConnectionResponse(BaseModel):
    id: str
    organization_id: str
    connector_id: str
    name: str
    config: Dict[str, Any] = {}
    field_mappings: Dict[str, str] = {}
    sync_schedule: Optional[str] = None
    is_active: bool = True
    sync_direction: str = "bidirectional"
    connector: Dict
    created_at: str
    updated_at: str
    created_by: str
    status: str = "pending"
    last_sync: Optional[str] = None
    last_error: Optional[str] = None
    sync_stats: Dict[str, int] = {}


class SyncJobBase(BaseModel):
    connection_id: str
    operation: str
    direction: str = "pull"
    filters: Dict[str, Any] = {}
    dry_run: bool = False


class SyncJobResponse(BaseModel):
    id: str
    connection_id: str
    operation: str
    direction: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_failed: int = 0
    error_message: Optional[str] = None
    logs: List[str] = []


# WebhookManager class
class WebhookManager:
    def __init__(self):
        self.endpoints: Dict[str, List[Dict]] = {}

    def register(self, url: str, events: List[str], secret: str, connector_id: str) -> str:
        endpoint_id = str(uuid.uuid4())
        if url not in self.endpoints:
            self.endpoints[url] = []
        self.endpoints[url].append({
            "id": endpoint_id,
            "events": events,
            "secret": secret,
            "connector_id": connector_id,
            "created_at": datetime.utcnow().isoformat(),
            "active": True,
        })
        return endpoint_id

    def unregister(self, endpoint_id: str) -> bool:
        for url, endpoints in self.endpoints.items():
            for i, ep in enumerate(endpoints):
                if ep["id"] == endpoint_id:
                    endpoints.pop(i)
                    return True
        return False

    def get_endpoints(self, url: str) -> List[Dict]:
        return self.endpoints.get(url, [])

    async def deliver(self, url: str, event: str, payload: Dict) -> bool:
        if url not in self.endpoints:
            return False

        for endpoint in self.endpoints[url]:
            if not endpoint["active"] or event not in endpoint["events"]:
                continue

            import hmac
            import hashlib
            signature = hmac.new(
                endpoint["secret"].encode(),
                json.dumps(payload).encode(),
                hashlib.sha256
            ).hexdigest()

            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
                "X-Webhook-Event": event,
                "X-Webhook-Timestamp": datetime.utcnow().isoformat(),
            }

            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                        return resp.status < 400
            except:
                return False
        return True


webhook_manager = WebhookManager()

# Build connector registry
connector_registry = {}
for key, config in DEFAULT_CONNECTORS.items():
    connector_registry[key] = {
        "id": key,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "created_by": "system",
        "status": "active",
        **config
    }


# API Routes
router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/connectors")
async def list_connectors(category: Optional[str] = Query(None)):
    connectors = list(connector_registry.values())
    if category:
        connectors = [c for c in connectors if c.get("category") == category]
    return connectors


@router.get("/connectors/{connector_id}")
async def get_connector(connector_id: str):
    if connector_id not in connector_registry:
        raise HTTPException(status_code=404, detail="Connector not found")
    return connector_registry[connector_id]


@router.post("/connectors")
async def create_connector(connector: dict):
    connector_id = connector.get("name", "").lower().replace(" ", "_")
    connector_obj = {
        "id": connector_id,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "created_by": "system",
        **connector
    }
    connector_registry[connector_id] = connector_obj
    return connector_obj


@router.patch("/connectors/{connector_id}")
async def update_connector(connector_id: str, updates: dict):
    if connector_id not in connector_registry:
        raise HTTPException(status_code=404, detail="Connector not found")
    connector = connector_registry[connector_id]
    for key, value in updates.items():
        if value is not None:
            connector[key] = value
    connector["updated_at"] = datetime.utcnow().isoformat()
    return connector


@router.delete("/connectors/{connector_id}")
async def delete_connector(connector_id: str):
    if connector_id not in connector_registry:
        raise HTTPException(status_code=404, detail="Connector not found")
    del connector_registry[connector_id]
    return {"success": True}


# Webhook endpoints
@router.post("/webhooks/register")
async def register_webhook(url: str = Body(...), events: List[str] = Body(...), secret: str = Body(...), connector_id: str = Body(...)):
    endpoint_id = webhook_manager.register(url, events, secret, connector_id)
    return {"endpoint_id": endpoint_id}


@router.delete("/webhooks/{endpoint_id}")
async def unregister_webhook(endpoint_id: str):
    success = webhook_manager.unregister(endpoint_id)
    if not success:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    return {"success": True}


# TypeScript SDK endpoint
@router.get("/sdk/typescript")
async def get_typescript_sdk():
    sdk_code = '''
// VCOS Integration SDK for TypeScript
// Install: npm install @vcos/integrations-sdk

import { 
  ConnectorSDK, 
  SlackConnector, 
  GitHubConnector, 
  GoogleWorkspaceConnector, 
  JiraConnector, 
  SalesforceConnector,
  AsanaConnector,
  MondayConnector,
  HubSpotConnector,
  LinearConnector,
  MondayConnector as MondayDotComConnector
} from '@vcos/integrations-sdk';

// Initialize SDK
const sdk = new ConnectorSDK({
  baseUrl: 'https://api.vcos.io',
  apiKey: process.env.VCOS_API_KEY
});

// List available connectors
const connectors = await sdk.listConnectors({ category: 'communication' });
console.log('Available connectors:', connectors);

// Create a Slack connection
const slackConnection = await sdk.createConnection({
  connectorId: 'slack',
  name: 'Main Slack Workspace',
  config: {
    clientId: process.env.SLACK_CLIENT_ID,
    clientSecret: process.env.SLACK_CLIENT_SECRET,
    redirectUri: 'https://app.vcos.io/oauth/callback'
  }
});

// Sync data from Slack
const syncResult = await sdk.syncConnection(slackConnection.id, 'sync', 'pull');
console.log('Sync completed:', syncResult);

// Use specific connector - Slack
const slack = new SlackConnector({
  clientId: process.env.SLACK_CLIENT_ID,
  clientSecret: process.env.SLACK_CLIENT_SECRET,
  redirectUri: 'https://app.vcos.io/oauth/callback'
});

await slack.authenticate();
const channels = await slack.pullData('channels');
console.log('Channels:', channels);

// Send a message
await slack.pushData('messages', [{
  channel: 'C123456',
  text: 'Hello from VCOS!',
  blocks: [{ type: 'section', text: { type: 'mrkdwn', text: 'Hello from VCOS!' } }]
});

// Subscribe to webhook events
const webhookId = await slack.setupWebhook('https://api.vcos.io/webhooks/slack', [
  'message',
  'reaction_added',
  'channel_created'
]);

// GitHub connector
const github = new GitHubConnector({
  clientId: process.env.GITHUB_CLIENT_ID,
  clientSecret: process.env.GITHUB_CLIENT_SECRET,
  redirectUri: 'https://app.vcos.io/oauth/callback'
});

await github.authenticate();
const repos = await github.pullData('repositories');
console.log('Repositories:', repos);

// Create an issue
await github.pushData('issues', [{
  title: 'New feature request',
  body: 'Please add dark mode support',
  labels: ['enhancement', 'ui']
}]);

// Salesforce connector
const salesforce = new SalesforceConnector({
  clientId: process.env.SF_CLIENT_ID,
  clientSecret: process.env.SF_CLIENT_SECRET,
  redirectUri: 'https://app.vcos.io/oauth/callback'
});

await salesforce.authenticate();
const accounts = await salesforce.pullData('accounts');
console.log('Accounts:', accounts);

// Create an opportunity
await salesforce.pushData('opportunities', [{
  name: 'Enterprise Deal',
  amount: 50000,
  stageName: 'Proposal',
  closeDate: '2024-12-31'
}]);

// Asana connector
const asana = new AsanaConnector({
  accessToken: process.env.ASANA_ACCESS_TOKEN
});

await asana.authenticate();
const projects = await asana.pullData('projects');
console.log('Projects:', projects);

// Create a task
await asana.pushData('tasks', [{
  name: 'Design review',
  notes: 'Review new dashboard designs',
  projects: ['project-gid-123'],
  assignee: 'user-gid-456'
}]);

// HubSpot connector
const hubspot = new HubSpotConnector({
  accessToken: process.env.HUBSPOT_ACCESS_TOKEN
});

await hubspot.authenticate();
const contacts = await hubspot.pullData('contacts');
console.log('Contacts:', contacts);

// Create a deal
await hubspot.pushData('deals', [{
  dealname: 'New Enterprise Deal',
  amount: '75000',
  dealstage: 'appointmentscheduled',
  pipeline: 'default'
}]);

// Linear connector
const linear = new LinearConnector({
  apiKey: process.env.LINEAR_API_KEY
});

await linear.authenticate();
const issues = await linear.pullData('issues');
console.log('Issues:', issues);

// Create an issue
await linear.pushData('issues', [{
  title: 'Fix login bug',
  description: 'Users cannot login with SSO',
  teamId: 'team-id-123',
  priority: 1
}]);

// Monday.com connector
const monday = new MondayConnector({
  apiToken: process.env.MONDAY_API_TOKEN
});

await monday.authenticate();
const boards = await monday.pullData('boards');
console.log('Boards:', boards);

// Create an item
await monday.pushData('items', [{
  boardId: '123456',
  itemName: 'New Feature',
  columnValues: { status: { label: 'Working on it' } }
}]);

export { sdk };
    '''
    return {"sdk_code": sdk_code.strip(), "version": "1.0.0"}