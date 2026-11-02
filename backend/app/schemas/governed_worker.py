"""Governed AI Worker schemas (Slice 4).

Request and output shapes for governed AI tasks: research briefs and
authorization-required recommendations. The model output shape is validated
strictly before anything derived from it is persisted.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class WorkerTaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    instruction: str = Field(min_length=5, max_length=4000)
    task_kind: Literal["research", "recommendation"] = "research"
    scope_type: Literal["company", "project"] = "company"
    scope_id: Optional[str] = Field(default=None, max_length=32)
    idempotency_key: Optional[str] = Field(default=None, max_length=64)


class WorkerEvidenceItem(BaseModel):
    claim: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=120)
    source_ref: Optional[str] = Field(default=None, max_length=255)


class WorkerProposedAction(BaseModel):
    action_type: str = Field(default="create_task", max_length=40)
    title: str = Field(min_length=1, max_length=240)
    description: Optional[str] = Field(default=None, max_length=2000)
    requires_approval: bool = True


class WorkerModelOutput(BaseModel):
    """The only shape accepted from the model. Anything else is a failure."""

    summary: str = Field(min_length=1, max_length=4000)
    observed_facts: list[str] = Field(default_factory=list)
    evidence: list[WorkerEvidenceItem] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    proposed_actions: list[WorkerProposedAction] = Field(default_factory=list)
