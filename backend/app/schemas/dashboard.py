from datetime import date, datetime
from math import isfinite
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.schemas.events import EventCreate, EventPlanResponse


EventStatus = Literal["scheduled", "completed", "cancelled"]
TaskStatus = Literal["pending", "in_progress", "completed"]


class DashboardEventResponse(BaseModel):
    id: str
    created_at: datetime
    status: EventStatus
    plan: EventPlanResponse


class DashboardTaskResponse(BaseModel):
    id: str
    created_at: datetime
    title: str
    due_date: date | None
    status: TaskStatus
    overdue: bool = False
    blocked: bool = False
    blockers: list[str] = Field(default_factory=list)
    event_id: str | None
    description: str = ""
    priority: Literal["low", "medium", "high"] = "medium"
    assigned_to: str | None = None
    estimated_cost: float | None = None
    completion_criteria: str = ""
    dependencies: list[str] = Field(default_factory=list)
    generated: bool = False


class DashboardSummaryResponse(BaseModel):
    total_events: int
    upcoming_events: int
    completed_events: int
    cancelled_events: int
    planned_budget_total: float | None
    known_estimated_costs: float | None
    remaining_known_estimate_budget: float | None
    estimated_costs_by_category: dict[str, float]
    budget_totals_by_currency: list[dict[str, str | float]]
    estimated_costs_by_currency: list[dict[str, Any]]
    expenditure_tracking_available: Literal[True]
    task_counts: dict[TaskStatus | Literal["overdue", "blocked"], int]
    risk_counts: dict[Literal["low", "medium", "high"], int]


class DashboardResponse(BaseModel):
    updated_at: datetime
    events: list[DashboardEventResponse]
    tasks: list[DashboardTaskResponse]
    risk_alerts: list[dict[str, Any]]
    summary: DashboardSummaryResponse
    capabilities: dict[str, bool]


class DashboardTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    due_date: date | None = None
    event_id: UUID | None = None
    description: str = Field(default="", max_length=1000)
    priority: Literal["low", "medium", "high"] = "medium"
    assigned_to: str | None = Field(default=None, max_length=120)
    estimated_cost: float | None = Field(default=None, ge=0)
    completion_criteria: str = Field(default="", max_length=500)
    dependencies: list[UUID] = Field(default_factory=list, max_length=50)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must not be blank")
        return cleaned

    @field_validator("description", "completion_criteria", "assigned_to")
    @classmethod
    def strip_task_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned and value:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("assigned_to")
    @classmethod
    def blank_assignee_is_unassigned(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("dependencies")
    @classmethod
    def dependencies_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("dependencies must not contain duplicates")
        return value

    @field_validator("estimated_cost")
    @classmethod
    def estimated_cost_must_be_finite(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("estimated_cost must be a finite number")
        return value


class DashboardTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=160)
    due_date: date | None = None
    status: TaskStatus | None = None
    description: str | None = Field(default=None, max_length=1000)
    priority: Literal["low", "medium", "high"] | None = None
    assigned_to: str | None = Field(default=None, max_length=120)
    estimated_cost: float | None = Field(default=None, ge=0)
    completion_criteria: str | None = Field(default=None, max_length=500)
    dependencies: list[UUID] | None = Field(default=None, max_length=50)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must not be blank")
        return cleaned

    @field_validator("description", "completion_criteria")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("assigned_to")
    @classmethod
    def clean_assignee(cls, value: str | None) -> str | None:
        cleaned = value.strip() if value is not None else ""
        return cleaned or None

    @field_validator("estimated_cost")
    @classmethod
    def estimated_cost_must_be_finite(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("estimated_cost must be a finite number")
        return value

    @field_validator("dependencies")
    @classmethod
    def dependencies_must_be_unique(
        cls, value: list[UUID] | None
    ) -> list[UUID] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("dependencies must not contain duplicates")
        return value

    @model_validator(mode="after")
    def require_update_fields(self) -> "DashboardTaskUpdate":
        if not self.model_fields_set:
            raise ValueError("provide at least one task field to update")
        for field in ("status", "title", "description", "priority", "completion_criteria", "dependencies"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class DashboardEventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EventStatus


class DashboardCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1000)
    conversation_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class DashboardCommandResponse(BaseModel):
    mode: Literal["deterministic_fallback", "genai"]
    ai_model_configured: bool
    conversation_id: str | None = None
    status: Literal["needs_input", "draft_ready"]
    extracted: dict[str, Any]
    missing_information: list[str]
    questions: list[str]
    unsupported_actions: list[str]
    notice: str
    planning: dict[str, Any] | None = None
    draft: EventCreate | None
    plan: EventPlanResponse | None
