"""Industry configuration, workflow and AI models (Phase 17.1 / 17.11 / 17.12).

Per-organization pack state (enabled modules/workflows/templates/settings),
activated industry workflow instances (which integrate with the core Phase 14
Workflow table), and the industry AI model profiles that make the shared AI
gateway industry-aware.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
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


class IndustryConfiguration(Base, TimestampMixin):
    """Per-organization state for one installed industry pack."""

    __tablename__ = "industry_configurations"
    __table_args__ = (
        Index("ix_industry_configs_org", "organization_id"),
        UniqueConstraint(
            "organization_id", "industry_key", name="uq_industry_configs_org_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    industry_key: Mapped[str] = mapped_column(String(50), nullable=False)
    pack_version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    # installed|enabled|disabled|uninstalled
    status: Mapped[str] = mapped_column(String(20), default="installed")
    modules_enabled: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    workflows_enabled: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    templates_enabled: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # org-level overrides: {"country": "IN", "regulations": [...],
    # "compliance_overrides": {"policy_key": {"enabled": false}}}
    settings: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    installed_by: Mapped[Optional[str]] = mapped_column(String(32))
    installed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class IndustryWorkflow(Base, TimestampMixin):
    """An activated industry workflow instance for an organization.

    Steps come from the pack's workflow template (configurable data). The
    workflow links back to a core Phase 14 Workflow row so it participates in
    the universal workflow engine, approvals and automation.
    """

    __tablename__ = "industry_workflows"
    __table_args__ = (
        Index("ix_industry_workflows_org_status", "organization_id", "status"),
        Index("ix_industry_workflows_org_key", "organization_id", "industry_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    industry_key: Mapped[str] = mapped_column(String(50), nullable=False)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # draft|active|paused|completed|cancelled
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # list of {"key", "name", "status" (pending|in_progress|completed), "assignee_id"}
    steps: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    current_step: Mapped[Optional[str]] = mapped_column(String(80))
    progress: Mapped[float] = mapped_column(default=0.0)
    # link into the core workflow engine (Phase 14)
    source_workflow_id: Mapped[Optional[str]] = mapped_column(String(32))
    assignee_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class IndustryAIModel(Base, TimestampMixin):
    """Industry AI profile — makes the shared AI gateway industry-aware.

    Each profile carries a system prompt, glossary/terminology, knowledge
    scope and guardrails (e.g. healthcare AI never makes diagnoses without
    safeguards). Profiles are data; the routing logic lives in the AI router.
    """

    __tablename__ = "industry_ai_models"
    __table_args__ = (
        Index("ix_industry_ai_models_key", "industry_key"),
        UniqueConstraint("industry_key", "model_key", name="uq_industry_ai_models_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    industry_key: Mapped[str] = mapped_column(String(50), nullable=False)
    model_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="vcos")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    terminology: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    knowledge_scope: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    guardrails: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # e.g. {"summarize": "...", "forecast": "...", "assist": "..."}
    skill_prompts: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(String(60), default="industry-default")
    temperature: Mapped[float] = mapped_column(default=0.4)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(32))
