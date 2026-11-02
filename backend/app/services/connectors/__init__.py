"""
Connector Package - Universal Integration Platform Connectors.

This package contains all connector implementations organized by category.
"""

from app.services.connectors.base import (
    BaseConnector,
    ConnectorAuth,
    ConnectorConfig,
    ConnectorType,
    SyncMode,
    OAuth2Connector,
    APIKeyConnector,
    HttpConnector,
    RateLimiter,
    RetryPolicy,
    ConnectorRegistry,
)

from app.services.connectors.calendar import (
    GoogleCalendarConnector,
    OutlookCalendarConnector,
    CalendlyConnector,
    DoodleConnector,
)

from app.services.connectors.ats import (
    GreenhouseConnector,
    LeverConnector,
    AshbyConnector,
    WorkableConnector,
    SmartRecruitersConnector,
)

from app.services.connectors.devops import (
    GitHubConnector,
    GitLabConnector,
    BitbucketConnector,
    VercelConnector,
    AWSConnector,
    GCPConnector,
    AzureConnector,
    KubernetesConnector,
    TerraformCloudConnector,
    DatadogConnector,
)

__all__ = [
    # Base
    "BaseConnector",
    "ConnectorAuth",
    "ConnectorConfig",
    "ConnectorType",
    "SyncMode",
    "OAuth2Connector",
    "APIKeyConnector",
    "HttpConnector",
    "RateLimiter",
    "RetryPolicy",
    "ConnectorRegistry",
    # Calendar
    "GoogleCalendarConnector",
    "OutlookCalendarConnector",
    "CalendlyConnector",
    "DoodleConnector",
    # ATS
    "GreenhouseConnector",
    "LeverConnector",
    "AshbyConnector",
    "WorkableConnector",
    "SmartRecruitersConnector",
    # DevOps
    "GitHubConnector",
    "GitLabConnector",
    "BitbucketConnector",
    "VercelConnector",
    "AWSConnector",
    "GCPConnector",
    "AzureConnector",
    "KubernetesConnector",
    "TerraformCloudConnector",
    "DatadogConnector",
]