"""Gate 24 — Connectors Package."""

from app.intelligence.connectors.base import BaseConnector, ConnectorRegistry, connector_registry
from app.intelligence.connectors.google import GoogleWorkspaceConnector
from app.intelligence.connectors.microsoft import Microsoft365Connector
from app.intelligence.connectors.slack import SlackConnector
from app.intelligence.connectors.github import GitHubConnector
from app.intelligence.connectors.jira import JiraConnector
from app.intelligence.connectors.asana import AsanaConnector
from app.intelligence.connectors.monday import MondayConnector
from app.intelligence.connectors.salesforce import SalesforceConnector
from app.intelligence.connectors.hubspot import HubSpotConnector
from app.intelligence.connectors.linear import LinearConnector

__all__ = [
    "BaseConnector",
    "ConnectorRegistry",
    "connector_registry",
    "GoogleWorkspaceConnector",
    "Microsoft365Connector",
    "SlackConnector",
    "GitHubConnector",
    "JiraConnector",
    "AsanaConnector",
    "MondayConnector",
    "SalesforceConnector",
    "HubSpotConnector",
    "LinearConnector",
]