"""
Canonical Schemas - Universal Data Normalization Layer (Part 2: Remaining Models)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.services.canonical_schemas import (
    CanonicalBaseModel,
    EntityType,
    Priority,
    DealStage,
    InvoiceStatus,
)


class DealStage(str, Enum):
    PROSPECTING = "prospecting"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"
    PARTIAL = "partial"


class CanonicalChannel(CanonicalBaseModel):
    name: str = Field(..., description="Channel name")
    name_normalized: Optional[str] = Field(None, description="Normalized name")
    channel_type: str = Field("channel", description="Channel type (channel, group, im, mpim)")
    is_private: bool = Field(False, description="Whether channel is private")
    is_archived: bool = Field(False, description="Whether channel is archived")
    is_general: bool = Field(False, description="Whether this is #general channel")
    team_id: Optional[str] = Field(None, description="Team/workspace external ID")
    creator_id: Optional[str] = Field(None, description="Creator external ID")
    topic: Optional[str] = Field(None, description="Channel topic")
    purpose: Optional[str] = Field(None, description="Channel purpose")
    member_ids: List[str] = Field(default_factory=list, description="Member external IDs")
    member_count: int = Field(0, description="Member count")
    is_shared: bool = Field(False, description="Whether channel is shared externally")
    is_org_shared: bool = Field(False, description="Whether channel is org-wide shared")


class CanonicalMessage(CanonicalBaseModel):
    text: str = Field(..., description="Message text")
    text_format: str = Field("plain", description="Text format (plain, markdown, html)")
    channel_id: str = Field(..., description="Channel external ID")
    thread_ts: Optional[str] = Field(None, description="Thread timestamp (parent message)")
    thread_id: Optional[str] = Field(None, description="Thread ID")
    reply_count: int = Field(0, description="Reply count in thread")
    author_id: str = Field(..., description="Author external ID")
    author_name: Optional[str] = Field(None, description="Author name")
    is_bot: bool = Field(False, description="Whether message is from bot")
    is_app: bool = Field(False, description="Whether message is from app")
    blocks: List[Dict[str, Any]] = Field(default_factory=list, description="Block kit blocks")
    attachments: List[Dict[str, Any]] = Field(default_factory=list, description="Attachments")
    files: List[Dict[str, Any]] = Field(default_factory=list, description="File attachments")
    reactions: List[Dict[str, Any]] = Field(default_factory=list, description="Reactions")
    reaction_counts: Dict[str, int] = Field(default_factory=dict, description="Reaction counts")
    edited_at: Optional[datetime] = Field(None, description="Edit timestamp")
    deleted: bool = Field(False, description="Whether message was deleted")
    pinned: bool = Field(False, description="Whether message is pinned")


class CanonicalFile(CanonicalBaseModel):
    name: str = Field(..., description="File name")
    title: Optional[str] = Field(None, description="File title")
    description: Optional[str] = Field(None, description="File description")
    mime_type: Optional[str] = Field(None, description="MIME type")
    file_type: Optional[str] = Field(None, description="File type/category")
    extension: Optional[str] = Field(None, description="File extension")
    size: int = Field(0, description="File size in bytes")
    size_pretty: Optional[str] = Field(None, description="Human-readable size")
    owner_id: Optional[str] = Field(None, description="Owner external ID")
    creator_id: Optional[str] = Field(None, description="Creator external ID")
    folder_id: Optional[str] = Field(None, description="Parent folder external ID")
    folder_path: Optional[str] = Field(None, description="Folder path")
    is_public: bool = Field(False, description="Whether file is public")
    shared: bool = Field(False, description="Whether file is shared")
    permissions: List[Dict[str, Any]] = Field(default_factory=list, description="Permissions")
    version: Optional[str] = Field(None, description="Version identifier")
    version_count: int = Field(1, description="Number of versions")
    latest_version: bool = Field(True, description="Whether this is latest version")
    previous_version_id: Optional[str] = Field(None, description="Previous version external ID")
    content_hash: Optional[str] = Field(None, description="Content hash (MD5/SHA256)")
    preview_url: Optional[str] = Field(None, description="Preview URL")
    download_url: Optional[str] = Field(None, description="Download URL")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail URL")
    width: Optional[int] = Field(None, description="Image width")
    height: Optional[int] = Field(None, description="Image height")
    duration: Optional[float] = Field(None, description="Media duration (seconds)")
    pages: Optional[int] = Field(None, description="Number of pages")


class CanonicalContact(CanonicalBaseModel):
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    full_name: Optional[str] = Field(None, description="Full name")
    display_name: Optional[str] = Field(None, description="Display name")
    prefix: Optional[str] = Field(None, description="Name prefix (Mr., Dr., etc.)")
    suffix: Optional[str] = Field(None, description="Name suffix (Jr., PhD, etc.)")
    middle_name: Optional[str] = Field(None, description="Middle name")
    nickname: Optional[str] = Field(None, description="Nickname")
    company_name: Optional[str] = Field(None, description="Company name")
    company_id: Optional[str] = Field(None, description="Company external ID")
    job_title: Optional[str] = Field(None, description="Job title")
    department: Optional[str] = Field(None, description="Department")
    manager_name: Optional[str] = Field(None, description="Manager name")
    emails: List[Dict[str, Any]] = Field(default_factory=list, description="Email addresses")
    phone_numbers: List[Dict[str, Any]] = Field(default_factory=list, description="Phone numbers")
    addresses: List[Dict[str, Any]] = Field(default_factory=list, description="Addresses")
    urls: List[Dict[str, Any]] = Field(default_factory=list, description="URLs (website, LinkedIn, etc.)")
    im_handles: List[Dict[str, Any]] = Field(default_factory=list, description="IM handles")
    birthday: Optional[str] = Field(None, description="Birthday (MM-DD)")
    anniversary: Optional[str] = Field(None, description="Anniversary (MM-DD)")
    notes: Optional[str] = Field(None, description="Notes")
    tags: List[str] = Field(default_factory=list, description="Tags/categories")
    group_names: List[str] = Field(default_factory=list, description="Group memberships")


class CanonicalEvent(CanonicalBaseModel):
    summary: str = Field(..., description="Event title")
    description: Optional[str] = Field(None, description="Event description")
    calendar_id: Optional[str] = Field(None, description="Calendar external ID")
    organizer_id: Optional[str] = Field(None, description="Organizer external ID")
    organizer_email: Optional[str] = Field(None, description="Organizer email")
    start_time: datetime = Field(..., description="Start time")
    end_time: datetime = Field(..., description="End time")
    all_day: bool = Field(False, description="All-day event")
    timezone: str = Field("UTC", description="Event timezone")
    recurring: bool = Field(False, description="Whether event recurs")
    recurrence_rule: Optional[str] = Field(None, description="RRULE string")
    recurrence_id: Optional[str] = Field(None, description="Instance ID for recurring event")
    original_start_time: Optional[datetime] = Field(None, description="Original start for moved instance")
    attendees: List[Dict[str, Any]] = Field(default_factory=list, description="Attendees")
    required_attendees: List[str] = Field(default_factory=list, description="Required attendee IDs")
    optional_attendees: List[str] = Field(default_factory=list, description="Optional attendee IDs")
    attendees_count: int = Field(0, description="Total attendees")
    accepted_count: int = Field(0, description="Accepted count")
    declined_count: int = Field(0, description="Declined count")
    tentative_count: int = Field(0, description="Tentative count")
    location: Optional[str] = Field(None, description="Physical location")
    location_details: Optional[Dict[str, Any]] = Field(None, description="Location details")
    conference_data: Optional[Dict[str, Any]] = Field(None, description="Video conference info")
    status: str = Field("confirmed", description="Event status (confirmed, tentative, cancelled)")
    transparency: str = Field("opaque", description="Transparency (opaque, transparent)")
    visibility: str = Field("default", description="Visibility (default, public, private, confidential)")
    reminders: List[Dict[str, Any]] = Field(default_factory=list, description="Reminders")
    default_reminders: bool = Field(True, description="Use default reminders")
    recurring_event_id: Optional[str] = Field(None, description="Master event ID for recurring")
    source: Optional[str] = Field(None, description="Source (email, manual, etc.)")


class CanonicalDeal(CanonicalBaseModel):
    name: str = Field(..., description="Deal name")
    description: Optional[str] = Field(None, description="Deal description")
    pipeline_id: Optional[str] = Field(None, description="Pipeline external ID")
    stage_id: Optional[str] = Field(None, description="Stage external ID")
    stage: str = Field("prospecting", description="Deal stage")
    stage_order: int = Field(0, description="Stage order in pipeline")
    probability: int = Field(0, ge=0, le=100, description="Close probability %")
    amount: float = Field(0, description="Deal amount")
    currency: str = Field("USD", description="Currency code")
    amount_usd: Optional[float] = Field(None, description="Amount in USD")
    expected_close_date: Optional[datetime] = Field(None, description="Expected close date")
    actual_close_date: Optional[datetime] = Field(None, description="Actual close date")
    owner_id: Optional[str] = Field(None, description="Owner external ID")
    contact_ids: List[str] = Field(default_factory=list, description="Contact external IDs")
    account_id: Optional[str] = Field(None, description="Account external ID")
    source: Optional[str] = Field(None, description="Lead source")
    source_detail: Optional[str] = Field(None, description="Source detail")
    campaign_id: Optional[str] = Field(None, description="Campaign external ID")
    forecast_category: Optional[str] = Field(None, description="Forecast category")
    forecast_amount: Optional[float] = Field(None, description="Forecast amount")
    competitor: Optional[str] = Field(None, description="Competitor name")
    loss_reason: Optional[str] = Field(None, description="Loss reason")


class CanonicalAccount(CanonicalBaseModel):
    name: str = Field(..., description="Account name")
    domain: Optional[str] = Field(None, description="Primary domain")
    domains: List[str] = Field(default_factory=list, description="All domains")
    display_name: Optional[str] = Field(None, description="Display name")
    description: Optional[str] = Field(None, description="Description")
    industry: Optional[str] = Field(None, description="Industry")
    sub_industry: Optional[str] = Field(None, description="Sub-industry")
    employee_count: Optional[int] = Field(None, description="Employee count")
    annual_revenue: Optional[float] = Field(None, description="Annual revenue")
    revenue_range: Optional[str] = Field(None, description="Revenue range")
    account_type: Optional[str] = Field(None, description="Account type (customer, prospect, partner, etc.)")
    status: str = Field("active", description="Account status")
    lifecycle_stage: Optional[str] = Field(None, description="Lifecycle stage")
    owner_id: Optional[str] = Field(None, description="Owner external ID")
    account_manager_id: Optional[str] = Field(None, description="Account manager external ID")
    csm_id: Optional[str] = Field(None, description="Customer success manager external ID")
    parent_account_id: Optional[str] = Field(None, description="Parent account external ID")
    child_account_ids: List[str] = Field(default_factory=list, description="Child account external IDs")
    ultimate_parent_id: Optional[str] = Field(None, description="Ultimate parent external ID")
    billing_address: Optional[Dict[str, Any]] = Field(None, description="Billing address")
    shipping_address: Optional[Dict[str, Any]] = Field(None, description="Shipping address")
    linkedin_url: Optional[str] = Field(None, description="LinkedIn URL")
    twitter_url: Optional[str] = Field(None, description="Twitter URL")
    facebook_url: Optional[str] = Field(None, description="Facebook URL")


class CanonicalInvoice(CanonicalBaseModel):
    number: str = Field(..., description="Invoice number")
    po_number: Optional[str] = Field(None, description="Purchase order number")
    account_id: Optional[str] = Field(None, description="Account external ID")
    contact_id: Optional[str] = Field(None, description="Contact external ID")
    customer_name: Optional[str] = Field(None, description="Customer name")
    customer_email: Optional[str] = Field(None, description="Customer email")
    issue_date: datetime = Field(..., description="Invoice date")
    due_date: Optional[datetime] = Field(None, description="Due date")
    paid_date: Optional[datetime] = Field(None, description="Paid date")
    subtotal: float = Field(0, description="Subtotal")
    tax_amount: float = Field(0, description="Tax amount")
    discount_amount: float = Field(0, description="Discount amount")
    total: float = Field(0, description="Total amount")
    currency: str = Field("USD", description="Currency code")
    amount_paid: float = Field(0, description="Amount paid")
    amount_due: float = Field(0, description="Amount due")
    exchange_rate: float = Field(1.0, description="Exchange rate to base currency")
    status: str = Field("draft", description="Invoice status")
    payment_terms: Optional[str] = Field(None, description="Payment terms (e.g., Net 30)")
    line_items: List[Dict[str, Any]] = Field(default_factory=list, description="Line items")
    quote_id: Optional[str] = Field(None, description="Quote external ID")
    order_id: Optional[str] = Field(None, description="Order external ID")
    contract_id: Optional[str] = Field(None, description="Contract external ID")


class CanonicalMetric(CanonicalBaseModel):
    name: str = Field(..., description="Metric name")
    value: Union[int, float] = Field(..., description="Metric value")
    unit: str = Field(..., description="Unit of measurement")
    dimensions: Dict[str, str] = Field(default_factory=dict, description="Dimension key-value pairs")
    timestamp: datetime = Field(..., description="Metric timestamp")
    interval: Optional[str] = Field(None, description="Interval (e.g., 1m, 5m, 1h)")
    source: Optional[str] = Field(None, description="Source system")
    resource_id: Optional[str] = Field(None, description="Monitored resource ID")
    resource_type: Optional[str] = Field(None, description="Resource type")
    tags: Dict[str, str] = Field(default_factory=dict, description="Tags")
    metric_type: str = Field("gauge", description="Metric type (gauge, counter, histogram, summary)")


class CanonicalAlert(CanonicalBaseModel):
    title: str = Field(..., description="Alert title")
    description: Optional[str] = Field(None, description="Alert description")
    severity: str = Field("high", description="Alert severity")
    status: str = Field("firing", description="Alert status (firing, resolved, acknowledged)")
    acknowledged: bool = Field(False, description="Whether acknowledged")
    acknowledged_by: Optional[str] = Field(None, description="Acknowledger external ID")
    acknowledged_at: Optional[datetime] = Field(None, description="Acknowledgment timestamp")
    source: str = Field(..., description="Alert source/monitoring system")
    rule_name: Optional[str] = Field(None, description="Alert rule name")
    rule_id: Optional[str] = Field(None, description="Alert rule ID")
    resource_id: Optional[str] = Field(None, description="Affected resource ID")
    resource_type: Optional[str] = Field(None, description="Affected resource type")
    service: Optional[str] = Field(None, description="Affected service")
    environment: Optional[str] = Field(None, description="Environment (prod, staging, etc.)")
    started_at: datetime = Field(..., description="Alert start time")
    ended_at: Optional[datetime] = Field(None, description="Alert end time")
    acknowledged_at: Optional[datetime] = Field(None, description="Acknowledgment time")
    value: Optional[Union[int, float]] = Field(None, description="Trigger value")
    threshold: Optional[Union[int, float]] = Field(None, description="Threshold value")
    condition: Optional[str] = Field(None, description="Trigger condition")
    runbook_url: Optional[str] = Field(None, description="Runbook URL")
    dashboard_url: Optional[str] = Field(None, description="Dashboard URL")
    labels: Dict[str, str] = Field(default_factory=dict, description="Alert labels")
    annotations: Dict[str, str] = Field(default_factory=dict, description="Alert annotations")


class CanonicalIncident(CanonicalBaseModel):
    title: str = Field(..., description="Incident title")
    description: Optional[str] = Field(None, description="Incident description")
    severity: str = Field("high", description="Incident severity")
    status: str = Field("open", description="Incident status (open, investigating, resolved, closed)")
    state: str = Field("active", description="Incident state")
    detected_at: datetime = Field(..., description="Detection time")
    acknowledged_at: Optional[datetime] = Field(None, description="Acknowledgment time")
    resolved_at: Optional[datetime] = Field(None, description="Resolution time")
    closed_at: Optional[datetime] = Field(None, description="Closure time")
    commander_id: Optional[str] = Field(None, description="Incident commander external ID")
    responder_ids: List[str] = Field(default_factory=list, description="Responder external IDs")
    stakeholder_ids: List[str] = Field(default_factory=list, description="Stakeholder external IDs")
    impact: str = Field("", description="Business impact description")
    affected_services: List[str] = Field(default_factory=list, description="Affected services")
    affected_customers: int = Field(0, description="Number of affected customers")
    status_page_url: Optional[str] = Field(None, description="Status page URL")
    war_room_url: Optional[str] = Field(None, description="War room URL")
    timeline: List[Dict[str, Any]] = Field(default_factory=list, description="Incident timeline")
    postmortem_url: Optional[str] = Field(None, description="Postmortem URL")
    root_cause: Optional[str] = Field(None, description="Root cause")
    action_items: List[Dict[str, Any]] = Field(default_factory=list, description="Action items")


# Entity Registry
CANONICAL_ENTITY_TYPES = {
    EntityType.USER: "CanonicalUser",
    EntityType.TEAM: "CanonicalTeam",
    EntityType.ORGANIZATION: "CanonicalOrganization",
    EntityType.PROJECT: "CanonicalProject",
    EntityType.TASK: "CanonicalTask",
    EntityType.ISSUE: "CanonicalIssue",
    EntityType.REPOSITORY: "CanonicalRepository",
    EntityType.PR: "CanonicalPullRequest",
    EntityType.COMMIT: "CanonicalCommit",
    EntityType.CHANNEL: "CanonicalChannel",
    EntityType.MESSAGE: "CanonicalMessage",
    EntityType.FILE: "CanonicalFile",
    EntityType.CONTACT: "CanonicalContact",
    EntityType.EVENT: "CanonicalEvent",
    EntityType.DEAL: "CanonicalDeal",
    EntityType.ACCOUNT: "CanonicalAccount",
    EntityType.INVOICE: "CanonicalInvoice",
    EntityType.METRIC: "CanonicalMetric",
    EntityType.ALERT: "CanonicalAlert",
    EntityType.INCIDENT: "CanonicalIncident",
}


def get_canonical_model(entity_type: EntityType) -> Optional[type]:
    model_name = CANONICAL_ENTITY_TYPES.get(entity_type)
    if model_name:
        return globals().get(model_name)
    return None


def get_all_canonical_types() -> List[EntityType]:
    return list(CANONICAL_ENTITY_TYPES.keys())


def validate_canonical(entity_type: EntityType, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    model = get_canonical_model(entity_type)
    if not model:
        return True, []
    try:
        model(**data)
        return True, []
    except Exception as e:
        return False, [str(e)]


def transform_to_canonical(entity_type: EntityType, raw_data: Dict[str, Any], source_system: str) -> Dict[str, Any]:
    model = get_canonical_model(entity_type)
    if not model:
        return raw_data
    canonical = {
        "external_id": str(raw_data.get("id", raw_data.get("external_id", ""))),
        "source_system": source_system,
        "raw_data": raw_data,
    }
    for key, value in raw_data.items():
        if key in model.model_fields:
            canonical[key] = value
    return canonical


def get_json_schema(entity_type: EntityType) -> Dict[str, Any]:
    model = get_canonical_model(entity_type)
    if not model:
        return {}
    return model.model_json_schema()


def get_all_schemas() -> Dict[str, Dict[str, Any]]:
    return {entity_type.value: get_json_schema(entity_type) for entity_type in get_all_canonical_types()}


def get_all_canonical_types() -> List[EntityType]:
    return list(CANONICAL_ENTITY_TYPES.keys())


class CanonicalSchemaRegistry:
    def __init__(self):
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._initialize_schemas()
    
    def _initialize_schemas(self) -> None:
        for entity_type in get_all_canonical_types():
            self._schemas[entity_type.value] = get_json_schema(entity_type)
    
    def get_schema(self, entity_type: EntityType) -> Optional[Dict[str, Any]]:
        return self._schemas.get(entity_type.value)
    
    def validate(self, entity_type: EntityType, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        return validate_canonical(entity_type, data)
    
    def transform(self, entity_type: EntityType, raw_data: Dict[str, Any], source_system: str) -> Dict[str, Any]:
        return transform_to_canonical(entity_type, raw_data, source_system)
    
    def get_all_schemas(self) -> Dict[str, Dict[str, Any]]:
        return self._schemas.copy()
    
    def get_supported_types(self) -> List[str]:
        return [et.value for et in get_all_canonical_types()]


_canonical_schema_registry = None


def get_canonical_schema_registry() -> CanonicalSchemaRegistry:
    global _canonical_schema_registry
    if _canonical_schema_registry is None:
        _canonical_schema_registry = CanonicalSchemaRegistry()
    return _canonical_schema_registry


__all__ = [
    "EntityType",
    "UserStatus",
    "TaskStatus",
    "IssueStatus",
    "Priority",
    "DealStage",
    "InvoiceStatus",
    "CanonicalBaseModel",
    "CanonicalUser",
    "CanonicalTeam",
    "CanonicalOrganization",
    "CanonicalProject",
    "CanonicalTask",
    "CanonicalIssue",
    "CanonicalRepository",
    "CanonicalPullRequest",
    "CanonicalCommit",
    "CanonicalChannel",
    "CanonicalMessage",
    "CanonicalFile",
    "CanonicalContact",
    "CanonicalEvent",
    "CanonicalDeal",
    "CanonicalAccount",
    "CanonicalInvoice",
    "CanonicalMetric",
    "CanonicalAlert",
    "CanonicalIncident",
    "CANONICAL_ENTITY_TYPES",
    "get_canonical_model",
    "get_all_canonical_types",
    "validate_canonical",
    "transform_to_canonical",
    "get_json_schema",
    "get_all_schemas",
    "CanonicalSchemaRegistry",
    "get_canonical_schema_registry",
]