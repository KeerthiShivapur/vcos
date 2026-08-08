"""Workflow Automation & Business Process OS models (Phase 14).

The workflow engine is a graph of typed nodes (trigger, condition, approval,
task, meeting, notification, delay, ai_decision, integration, parallel,
webhook, end) connected by edges. Executions walk the graph, approvals gate
the flow, schedules fire on cron, business rules react to events, and
templates let the AI generate whole workflows from a prompt.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Workflow(Base, TimestampMixin):
    __tablename__ = "workflows"
    __table_args__ = (
        Index("ix_workflows_org_status", "organization_id", "status"),
        UniqueConstraint("organization_id", "name", name="uq_workflows_org_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # operations|hr|projects|crm|finance|knowledge|community|learning|meetings|general
    category: Mapped[str] = mapped_column(String(30), default="general")
    # draft|active|paused|archived
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    # manual|event|schedule|webhook
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual")
    trigger_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    icon: Mapped[Optional[str]] = mapped_column(String(50))
    color: Mapped[Optional[str]] = mapped_column(String(20))
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class WorkflowVersion(Base, TimestampMixin):
    __tablename__ = "workflow_versions"
    __table_args__ = (Index("ix_workflow_versions_workflow", "workflow_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # snapshot of the graph: {"nodes": [...], "edges": [...]}
    definition: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))


class WorkflowNode(Base, TimestampMixin):
    __tablename__ = "workflow_nodes"
    __table_args__ = (
        Index("ix_workflow_nodes_workflow", "workflow_id"),
        UniqueConstraint("workflow_id", "node_key", name="uq_workflow_nodes_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # trigger|start|condition|approval|task|meeting|notification|delay|
    # ai_decision|integration|webhook|parallel_split|parallel_join|script|end
    node_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    position: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class WorkflowEdge(Base, TimestampMixin):
    __tablename__ = "workflow_edges"
    __table_args__ = (
        Index("ix_workflow_edges_workflow", "workflow_id"),
        UniqueConstraint(
            "workflow_id", "source_key", "target_key", name="uq_workflow_edges_route"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    target_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # optional guard evaluated before traversing (e.g. branch label or condition)
    condition: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class WorkflowExecution(Base, TimestampMixin):
    __tablename__ = "workflow_executions"
    __table_args__ = (
        Index("ix_workflow_executions_org_status", "organization_id", "status"),
        Index("ix_workflow_executions_workflow", "workflow_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL")
    )
    workflow_name: Mapped[str] = mapped_column(String(255), default="")
    # queued|running|waiting|completed|failed|cancelled|timed_out
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # manual|event|schedule|webhook|retry
    trigger_source: Mapped[str] = mapped_column(String(20), default="manual")
    trigger_event: Mapped[Optional[str]] = mapped_column(String(120))
    triggered_by: Mapped[Optional[str]] = mapped_column(String(32))
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    current_node_key: Mapped[Optional[str]] = mapped_column(String(64))
    resume_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error: Mapped[Optional[str]] = mapped_column(Text)


class WorkflowExecutionStep(Base, TimestampMixin):
    __tablename__ = "workflow_execution_steps"
    __table_args__ = (
        Index("ix_workflow_steps_execution", "execution_id"),
        Index("ix_workflow_steps_exec_node", "execution_id", "node_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False
    )
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(30), nullable=False)
    node_name: Mapped[str] = mapped_column(String(255), default="")
    # pending|running|succeeded|failed|skipped|waiting_approval|waiting_delay|blocked
    status: Mapped[str] = mapped_column(String(30), default="pending")
    input_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    output_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class WorkflowTrigger(Base, TimestampMixin):
    __tablename__ = "workflow_triggers"
    __table_args__ = (
        Index("ix_workflow_triggers_org", "organization_id"),
        UniqueConstraint("workflow_id", "trigger_type", name="uq_workflow_triggers_one"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    # manual|event|schedule|webhook
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    event_name: Mapped[Optional[str]] = mapped_column(String(120))
    # filters / schedule cron / webhook token & payload template
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fire_count: Mapped[int] = mapped_column(Integer, default=0)


class WorkflowAction(Base, TimestampMixin):
    __tablename__ = "workflow_actions"
    __table_args__ = (
        Index("ix_workflow_actions_org", "organization_id"),
        UniqueConstraint("workflow_id", "node_key", name="uq_workflow_actions_node"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # create_task|create_meeting|create_project|send_notification|
    # create_approval|create_onboarding|send_message|webhook|ai_summarize|update_entity
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkflowTemplate(Base, TimestampMixin):
    __tablename__ = "workflow_templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default="general")
    icon: Mapped[Optional[str]] = mapped_column(String(50))
    # {"nodes": [...], "edges": [...], "trigger_type": "..."}
    definition: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    popularity: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))


class WorkflowSchedule(Base, TimestampMixin):
    __tablename__ = "workflow_schedules"
    __table_args__ = (
        Index("ix_workflow_schedules_org", "organization_id"),
        Index("ix_workflow_schedules_due", "enabled", "next_run_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # cron expression: minute hour dom month dow
    cron: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_template: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class WorkflowApproval(Base, TimestampMixin):
    __tablename__ = "workflow_approvals"
    __table_args__ = (
        Index("ix_workflow_approvals_org_status", "organization_id", "status"),
        Index("ix_workflow_approvals_execution", "execution_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL")
    )
    execution_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE")
    )
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # pending|approved|rejected|escalated|cancelled|skipped
    status: Mapped[str] = mapped_column(String(20), default="pending")
    approver_type: Mapped[str] = mapped_column(String(20), default="user")  # user|role|manager
    approver_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approver_role: Mapped[Optional[str]] = mapped_column(String(30))
    requested_by: Mapped[Optional[str]] = mapped_column(String(32))
    decided_by: Mapped[Optional[str]] = mapped_column(String(32))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    comment: Mapped[Optional[str]] = mapped_column(Text)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))


class WorkflowLog(Base, TimestampMixin):
    __tablename__ = "workflow_logs"
    __table_args__ = (
        Index("ix_workflow_logs_org_created", "organization_id", "created_at"),
        Index("ix_workflow_logs_workflow", "workflow_id"),
        Index("ix_workflow_logs_execution", "execution_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[Optional[str]] = mapped_column(String(32))
    workflow_id: Mapped[Optional[str]] = mapped_column(String(32))
    execution_id: Mapped[Optional[str]] = mapped_column(String(32))
    level: Mapped[str] = mapped_column(String(10), default="info")  # info|warning|error
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class BusinessRule(Base, TimestampMixin):
    __tablename__ = "business_rules"
    __table_args__ = (
        Index("ix_business_rules_org", "organization_id"),
        UniqueConstraint("organization_id", "name", name="uq_business_rules_org_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    event_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # list of {"field": "path", "operator": "eq|neq|gt|gte|lt|lte|contains|in|is_null", "value": ...}
    conditions: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    # list of {"action": "...", "config": {...}}
    actions: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[str]] = mapped_column(String(32))


class AutomationIntegration(Base, TimestampMixin):
    __tablename__ = "automation_integrations"
    __table_args__ = (
        Index("ix_automation_integrations_org", "organization_id"),
        UniqueConstraint("organization_id", "name", name="uq_automation_integrations_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # slack|teams|webhook|zapier|gsheet|notion|email|custom
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # connected|disconnected|error
    status: Mapped[str] = mapped_column(String(20), default="connected")
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))


class WorkflowMetric(Base, TimestampMixin):
    __tablename__ = "workflow_metrics"
    __table_args__ = (
        Index("ix_workflow_metrics_org_type", "organization_id", "metric_type", "period"),
        Index("ix_workflow_metrics_workflow", "workflow_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[Optional[str]] = mapped_column(String(32))
    # executions|completions|failures|avg_duration_ms|completion_rate|approval_time_hours
    metric_type: Mapped[str] = mapped_column(String(40), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2026-08" | "2026-W32"
    value: Mapped[float] = mapped_column(Float, default=0.0)
    count: Mapped[int] = mapped_column(Integer, default=0)
