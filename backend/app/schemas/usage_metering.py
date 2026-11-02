"""Usage Metering Contracts — Stage 5.1 Pay-As-You-Go Billing.

Defines validated, versioned usage-event contracts for the metering pipeline.
All fields required by the existing architecture are included.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.config import ConfigDict


class UsageEventSchemaVersion(str, Enum):
    """Supported usage event schema versions."""
    V1 = "1.0.0"


class UsageMetricCode(str, Enum):
    """Supported billable metric codes matching ENTITLEMENT_KEYS."""
    # Core platform metrics
    EMPLOYEES = "employees.max"
    STORAGE_GB = "storage.gb"
    INTEGRATIONS = "integrations.max"
    API_CALLS_PER_MONTH = "api.calls.per_month"
    AI_USAGE_PER_MONTH = "ai.usage.per_month"
    
    # Advanced features
    ANALYTICS_ADVANCED = "analytics.advanced"
    GOVERNANCE_ADVANCED = "governance.advanced"
    SECURITY_ADVANCED = "security.advanced"
    AUTOMATION_WORKFLOWS = "automation.workflows"
    RETENTION_DAYS = "retention.days"
    SUPPORT_LEVEL = "support.level"
    WORKSPACE_ADVANCED = "workspace.advanced"
    VIRTUAL_OFFICE = "virtual_office.enabled"
    SSO_ENABLED = "sso.enabled"
    AUDIT_LOG_RETENTION = "audit_log.retention_days"
    DATA_EXPORT = "data_export.enabled"
    CUSTOM_BRANDING = "custom_branding.enabled"
    PRIORITY_SUPPORT = "priority_support.enabled"
    
    # Compute/Processing metrics
    DOCUMENT_PROCESSING_PAGES = "document.processing.pages"
    WORKFLOW_EXECUTIONS = "workflow.executions"
    INTEGRATION_SYNC_RECORDS = "integration.sync.records"
    AI_INFERENCE_TOKENS = "ai.inference.tokens"
    COMPUTE_SECONDS = "compute.seconds"


class UsageUnit(str, Enum):
    """Supported units for usage quantities."""
    UNITS = "units"
    GB = "GB"
    MB = "MB"
    PAGES = "pages"
    TOKENS = "tokens"
    RECORDS = "records"
    EXECUTIONS = "executions"
    SECONDS = "seconds"
    CALLS = "calls"
    USERS = "users"
    INTEGRATIONS = "integrations"
    WORKFLOWS = "workflows"
    DAYS = "days"


class UsageEventSource(str, Enum):
    """Source systems that emit usage events."""
    AI_INFERENCE = "ai_inference"
    WORKFLOW_ENGINE = "workflow_engine"
    INTEGRATION_SYNC = "integration_sync"
    DOCUMENT_PROCESSING = "document_processing"
    STORAGE = "storage"
    API_GATEWAY = "api_gateway"
    SYSTEM = "system"
    WORKER = "worker"
    WEBHOOK = "webhook"
    MANUAL = "manual"


class UsageEventState(str, Enum):
    """Processing state of a usage event."""
    RECEIVED = "received"
    VALIDATED = "validated"
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class BaseUsageEvent(BaseModel):
    """Base usage event with all required architecture fields."""
    
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )
    
    # Event identity (required for exact-once)
    event_id: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Globally unique event identifier for idempotency"
    )
    event_schema_version: UsageEventSchemaVersion = Field(
        default=UsageEventSchemaVersion.V1,
        description="Schema version for forward/backward compatibility"
    )
    
    # Tenant and account ownership (required for tenant isolation)
    organization_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="VCOS organization ID (tenant scope)"
    )
    commercial_account_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Commercial account ID for billing relationship"
    )
    subscription_id: Optional[str] = Field(
        default=None,
        max_length=32,
        description="Active subscription ID (validated at ingestion)"
    )
    
    # Metric and quantity (required for billing)
    metric_code: UsageMetricCode = Field(
        ...,
        description="Billable metric identifier matching entitlement keys"
    )
    quantity: Decimal = Field(
        ...,
        gt=0,
        max_digits=18,
        decimal_places=6,
        description="Usage quantity (decimal-safe, no binary floating-point)"
    )
    unit: UsageUnit = Field(
        ...,
        description="Unit of measure for the quantity"
    )
    
    # Temporal fields (required for temporal truth)
    occurred_at: datetime = Field(
        ...,
        description="When the usage actually occurred (source system time)"
    )
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When VCOS received the event"
    )
    
    # Source attribution (required for provenance)
    source_system: UsageEventSource = Field(
        ...,
        description="System that generated this usage"
    )
    source_entity_id: Optional[str] = Field(
        default=None,
        max_length=120,
        description="ID of the entity in the source system (e.g., workflow ID, document ID)"
    )
    source_operation_id: Optional[str] = Field(
        default=None,
        max_length=120,
        description="ID of the operation in the source system (e.g., execution ID, sync run ID)"
    )
    
    # Provenance and metadata
    provenance: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provenance chain linking to source evidence"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured metadata (constrained by schema)"
    )
    
    # Billing period (computed at ingestion)
    period: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}$",
        description="Billing period in YYYY-MM format"
    )
    
    @field_validator("quantity", mode="before")
    @classmethod
    def _validate_quantity(cls, v: Any) -> Decimal:
        """Ensure quantity uses exact decimal arithmetic."""
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v)
        if isinstance(v, Decimal):
            return v
        raise ValueError("Quantity must be a number or decimal string")
    
    @field_validator("occurred_at", "received_at", mode="before")
    @classmethod
    def _validate_timezone(cls, v: Any) -> datetime:
        """Ensure all timestamps are timezone-aware UTC."""
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        elif isinstance(v, datetime):
            dt = v
        else:
            raise ValueError("Timestamp must be ISO format string or datetime")
        
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    
    @field_validator("period", mode="before")
    @classmethod
    def _validate_period(cls, v: Any) -> str:
        """Validate billing period format."""
        if isinstance(v, str):
            if not v or not v.match(r"^\d{4}-\d{2}$"):
                raise ValueError("Period must be YYYY-MM format")
        return v
    
    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "BaseUsageEvent":
        """Cross-field validation."""
        # Ensure occurred_at is not in the future (with 5 min grace)
        now = datetime.now(timezone.utc)
        if self.occurred_at > now + timedelta(minutes=5):
            raise ValueError("occurred_at cannot be in the future")
        
        # Ensure received_at >= occurred_at (with clock skew tolerance)
        if self.received_at < self.occurred_at - timedelta(minutes=10):
            raise ValueError("received_at cannot be significantly before occurred_at")
        
        # Ensure period matches occurred_at
        expected_period = self.occurred_at.strftime("%Y-%m")
        if self.period != expected_period:
            raise ValueError(f"period must match occurred_at month: expected {expected_period}")
        
        return self


class UsageEventCreate(BaseUsageEvent):
    """Usage event for ingestion (client-facing)."""
    pass


class UsageEventInternal(BaseUsageEvent):
    """Usage event with internal processing fields."""
    
    # Internal processing state
    state: UsageEventState = Field(
        default=UsageEventState.RECEIVED,
        description="Current processing state"
    )
    
    # Validation results
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Validation errors if rejected"
    )
    
    # Processing timestamps
    validated_at: Optional[datetime] = Field(
        default=None,
        description="When event passed validation"
    )
    accepted_at: Optional[datetime] = Field(
        default=None,
        description="When event was accepted for recording"
    )
    
    # Deduplication
    is_duplicate: bool = Field(
        default=False,
        description="Whether this event was identified as duplicate"
    )
    original_event_id: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Original event ID if this is a duplicate"
    )


class UsageEventResponse(BaseModel):
    """Response for usage event ingestion."""
    event_id: str
    state: UsageEventState
    message: str
    accepted_at: Optional[datetime] = None
    duplicate_of: Optional[str] = None


class UsageValidationError(BaseModel):
    """Validation error detail."""
    field: str
    message: str
    code: str


class UsageBatchRequest(BaseModel):
    """Batch usage event ingestion request."""
    events: List[UsageEventCreate] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Usage events to ingest (max 1000 per batch)"
    )
    
    @field_validator("events")
    @classmethod
    def _check_duplicate_ids(cls, v: List[UsageEventCreate]) -> List[UsageEventCreate]:
        """Check for duplicate event_ids within the batch."""
        seen = set()
        for event in v:
            if event.event_id in seen:
                raise ValueError(f"Duplicate event_id in batch: {event.event_id}")
            seen.add(event.event_id)
        return v


class UsageBatchResponse(BaseModel):
    """Batch usage event ingestion response."""
    accepted: int
    duplicates: int
    rejected: int
    results: List[UsageEventResponse]


# Import timedelta for validators
from datetime import timedelta


# Metric metadata registry for validation and documentation
METRIC_REGISTRY: Dict[str, Dict[str, Any]] = {
    "employees.max": {
        "display_name": "Employees",
        "unit": UsageUnit.USERS,
        "description": "Active employee count",
        "aggregation": "max",
        "billing_type": "limit",
    },
    "storage.gb": {
        "display_name": "Storage",
        "unit": UsageUnit.GB,
        "description": "Object storage consumption",
        "aggregation": "max",
        "billing_type": "limit",
    },
    "integrations.max": {
        "display_name": "Integrations",
        "unit": UsageUnit.INTEGRATIONS,
        "description": "Active integration connections",
        "aggregation": "max",
        "billing_type": "limit",
    },
    "api.calls.per_month": {
        "display_name": "API Calls",
        "unit": UsageUnit.CALLS,
        "description": "API gateway requests per month",
        "aggregation": "sum",
        "billing_type": "metered",
    },
    "ai.usage.per_month": {
        "display_name": "AI Usage",
        "unit": UsageUnit.TOKENS,
        "description": "AI inference tokens per month",
        "aggregation": "sum",
        "billing_type": "metered",
    },
    "document.processing.pages": {
        "display_name": "Document Processing",
        "unit": UsageUnit.PAGES,
        "description": "Pages processed by document intelligence",
        "aggregation": "sum",
        "billing_type": "metered",
    },
    "workflow.executions": {
        "display_name": "Workflow Executions",
        "unit": UsageUnit.EXECUTIONS,
        "description": "Workflow/commitment executions",
        "aggregation": "sum",
        "billing_type": "metered",
    },
    "integration.sync.records": {
        "display_name": "Integration Sync Records",
        "unit": UsageUnit.RECORDS,
        "description": "Records synchronized from external systems",
        "aggregation": "sum",
        "billing_type": "metered",
    },
    "ai.inference.tokens": {
        "display_name": "AI Inference Tokens",
        "unit": UsageUnit.TOKENS,
        "description": "Tokens consumed by AI inference",
        "aggregation": "sum",
        "billing_type": "metered",
    },
    "compute.seconds": {
        "display_name": "Compute Time",
        "unit": UsageUnit.SECONDS,
        "description": "Compute seconds consumed",
        "aggregation": "sum",
        "billing_type": "metered",
    },
}


def get_metric_metadata(metric_code: str) -> Optional[Dict[str, Any]]:
    """Get metric metadata from registry."""
    return METRIC_REGISTRY.get(metric_code)


def validate_metric_unit(metric_code: str, unit: str) -> bool:
    """Validate that unit matches metric's expected unit."""
    metadata = get_metric_metadata(metric_code)
    if not metadata:
        return True  # Unknown metric, allow
    return metadata.get("unit") == unit


def get_metric_aggregation(metric_code: str) -> str:
    """Get aggregation type for metric (sum, max, avg)."""
    metadata = get_metric_metadata(metric_code)
    if not metadata:
        return "sum"
    return metadata.get("aggregation", "sum")


def get_metric_billing_type(metric_code: str) -> str:
    """Get billing type for metric (limit, metered, boolean)."""
    metadata = get_metric_registry(metric_code)
    if not metadata:
        return "metered"
    return metadata.get("billing_type", "metered")


def get_metric_registry(metric_code: str) -> Optional[Dict[str, Any]]:
    """Get metric metadata from registry (alias)."""
    return METRIC_REGISTRY.get(metric_code)