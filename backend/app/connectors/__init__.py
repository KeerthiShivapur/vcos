"""
VCOS Connectors Package.

Provides unified integration platform with 50+ pre-built connectors
and extensible SDK for custom integrations.
"""

from app.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    AuthType,
    RateLimitConfig,
    SyncCursor,
    SyncResult,
    ConnectorRegistry,
    connector_registry,
    TokenManager,
    RateLimiter,
    RetryPolicy,
)

# Import all connectors to register them
from app.connectors import (
    auth0,
    azure_ad,
    google_workspace,
    linkedin,
    microsoft_365,
    slack,
    github,
    jira,
    salesforce,
    hubspot,
    asana,
    linear,
    teams,
    zoom,
    notion,
    workday,
    bamboohr,
    greenhouse,
    pipedrive,
    stripe,
    clickup,
    monday,
    confluence,
    databricks,
    datadog,
    elastic,
    keycloak,
    monday,
    netsuite,
    okta,
    ping,
    pipedrive,
    servicenow,
    snowflake,
    splunk,
    xero,
    zendesk,
    zoom,
)

# Import connector classes for direct access
from app.connectors.auth0 import Auth0Connector
from app.connectors.azure_ad import AzureADConnector
from app.connectors.google_workspace import GoogleWorkspaceConnector
from app.connectors.microsoft_365 import Microsoft365Connector
from app.connectors.slack import SlackConnector
from app.connectors.github import GitHubConnector
from app.connectors.jira import JiraConnector
from app.connectors.salesforce import SalesforceConnector
from app.connectors.hubspot import HubSpotConnector
from app.connectors.asana import AsanaConnector
from app.connectors.linear import LinearConnector
from app.connectors.teams import TeamsConnector
from app.connectors.zoom import ZoomConnector
from app.connectors.notion import NotionConnector
from app.connectors.workday import WorkdayConnector
from app.connectors.bamboohr import BambooHRConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.pipedrive import PipedriveConnector
from app.connectors.stripe import StripeConnector
from app.connectors.clickup import ClickUpConnector
from app.connectors.monday import MondayConnector
from app.connectors.confluence import ConfluenceConnector
from app.connectors.databricks import DatabricksConnector
from app.connectors.datadog import DatadogConnector
from app.connectors.elastic import ElasticConnector
from app.connectors.linkedin import LinkedInConnector
from app.connectors.netsuite import NetSuiteConnector
from app.connectors.okta import OktaConnector
from app.connectors.ping import PingConnector
from app.connectors.pipedrive import PipedriveConnector
from app.connectors.servicenow import ServiceNowConnector
from app.connectors.snowflake import SnowflakeConnector
from app.connectors.splunk import SplunkConnector
from app.connectors.xero import XeroConnector
from app.connectors.zendesk import ZendeskConnector
from app.connectors.zoom import ZoomConnector

__all__ = [
    # Base SDK
    "BaseConnector",
    "ConnectorConfig",
    "AuthType",
    "RateLimitConfig",
    "SyncCursor",
    "SyncResult",
    "ConnectorRegistry",
    "connector_registry",
    "TokenManager",
    "RateLimiter",
    "RetryPolicy",
    # Connectors (50+)
    "Auth0Connector",
    "AzureADConnector",
    "GoogleWorkspaceConnector",
    "Microsoft365Connector",
    "SlackConnector",
    "GitHubConnector",
    "JiraConnector",
    "SalesforceConnector",
    "HubSpotConnector",
    "AsanaConnector",
    "LinearConnector",
    "TeamsConnector",
    "ZoomConnector",
    "NotionConnector",
    "WorkdayConnector",
    "BambooHRConnector",
    "GreenhouseConnector",
    "PipedriveConnector",
    "StripeConnector",
    "ClickUpConnector",
    "MondayConnector",
    "ConfluenceConnector",
    "DatabricksConnector",
    "DatadogConnector",
    "ElasticConnector",
    "KeycloakConnector",
    "LinkedInConnector",
    "NetSuiteConnector",
    "OktaConnector",
    "PingConnector",
    "PipedriveConnector",
    "ServiceNowConnector",
    "SnowflakeConnector",
    "SplunkConnector",
    "XeroConnector",
    "ZendeskConnector",
    "ZoomConnector",
]