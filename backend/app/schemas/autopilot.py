from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.events import ScenarioChanges


TaskPriority = Literal["low", "medium", "high"]
DisruptionType = Literal[
    "venue_cancellation",
    "vendor_cancellation",
    "budget_change",
    "guest_count_change",
    "date_change",
    "delayed_task",
    "equipment_availability",
    "catering_availability",
    "other",
]


class WorkflowTaskResponse(BaseModel):
    id: str
    created_at: datetime
    event_id: str
    title: str
    description: str
    priority: TaskPriority
    status: Literal["pending", "in_progress", "completed"]
    due_date: date | None
    assigned_to: str | None
    estimated_cost: float | None
    completion_criteria: str
    dependencies: list[str]
    blockers: list[str]
    information_needed: list[str]
    blocks: list[str]
    overdue: bool
    generated: bool


class WorkflowResponse(BaseModel):
    event_id: str
    event_name: str
    generated: bool
    tasks: list[WorkflowTaskResponse]
    overdue_count: int
    blocked_count: int
    missing_information: list[str]
    next_action: str | None
    unresolved_event_risks: list[str]
    ai_model_configured: bool
    notice: str


class RecoveryOption(BaseModel):
    id: str
    title: str
    description: str
    readiness: Literal["requires_verification", "ready_for_review"]
    cost_change: float | None
    cost_basis: str
    projected_known_cost_inr: float
    projected_overrun_inr: float
    approved_budget_inr: float
    timing_change_days: int | None
    affected_tasks: list[str]
    unresolved_risks: list[str]
    uncertainties: list[str]
    proposed_changes: dict[str, Any]


class RecoveryActivityResponse(BaseModel):
    id: str
    proposal_id: str | None
    action: str
    status: str
    details: str
    created_at: datetime


class RecoveryProposalResult(BaseModel):
    event_id: str
    applied_changes: dict[str, Any]
    remaining_blockers: list[dict[str, Any]]
    external_actions_executed: list[str]
    message: str


class RecoveryProposalResponse(BaseModel):
    id: str
    case_id: str
    event_id: str
    option_id: str
    status: Literal["proposed", "approved", "rejected", "applied", "failed"]
    proposed_change: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    result: RecoveryProposalResult | None = None


class RecoveryCaseResponse(BaseModel):
    id: str
    event_id: str
    created_at: datetime
    resolved_at: datetime | None
    resolution: str | None
    source: Literal["user_report"]
    disruption_type: DisruptionType
    description: str
    status: Literal["open", "resolved"]
    impact: dict[str, Any]
    options: list[RecoveryOption]
    proposals: list[RecoveryProposalResponse]
    activity: list[RecoveryActivityResponse]


class RecoveryCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["user_report"] = "user_report"
    disruption_type: DisruptionType
    description: str = Field(min_length=1, max_length=1000)
    task_id: UUID | None = None
    changes: ScenarioChanges | None = None

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("description must not be blank")
        return value


class RecoveryProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str = Field(min_length=1, max_length=80)


class RecoveryProposalDecision(BaseModel):
    status: Literal["applied", "rejected"]


class RecoveryCaseResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1000)

    @field_validator("summary")
    @classmethod
    def summary_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("summary must not be blank")
        return value
