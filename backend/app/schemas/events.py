from datetime import date, datetime, time
from decimal import Decimal
import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
ExpenseCategory = Literal[
    "venue",
    "catering",
    "production",
    "staffing",
    "equipment",
    "activities",
    "decoration",
    "photography",
    "entertainment",
    "transport",
    "accommodation",
    "invitations",
    "contingency",
    "miscellaneous",
    "other",
]
SUPPORTED_CURRENCIES = {"INR", "USD", "EUR", "GBP", "CAD", "AUD", "SGD", "AED", "JPY"}
RequirementStatus = Literal["satisfied", "unsatisfied", "unverified"]
RiskSeverity = Literal["low", "medium", "high"]
ReadinessStatus = Literal["ready", "needs_attention", "at_risk"]
BudgetStatus = Literal["incomplete", "within_budget", "over_budget"]
CapacityStatus = Literal["unknown", "within_capacity", "exceeds_capacity"]


class AgendaSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    time: str | None = Field(default=None, max_length=40)
    duration_minutes: int | None = Field(default=None, gt=0, le=1440)
    basis: str = Field(max_length=300)


class PlanningSuggestions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objectives: list[str] = Field(default_factory=list, max_length=8)
    agenda: list[AgendaSuggestion] = Field(default_factory=list, max_length=20)
    checklist: list[str] = Field(default_factory=list, max_length=20)
    personalized_ideas: list[str] = Field(default_factory=list, max_length=12)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    uncertainties: list[str] = Field(default_factory=list, max_length=12)


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_name: str = Field(min_length=1, max_length=120)
    event_type: str | None = Field(default=None, min_length=1, max_length=80)
    purpose: str | None = Field(default=None, max_length=500)
    event_date: date | None = None
    event_time: time | None = None
    location: str | None = Field(default=None, min_length=1, max_length=200)
    guest_count: int | None = Field(default=None, gt=0, le=1_000_000)
    budget: PositiveMoney
    currency: str = "INR"
    venue_name: str | None = Field(default=None, min_length=1, max_length=200)
    venue_capacity: int | None = Field(default=None, gt=0, le=1_000_000)
    estimated_costs: dict[ExpenseCategory, Money] = Field(default_factory=dict)
    category_allocations: dict[ExpenseCategory, Money] = Field(default_factory=dict)
    planned_expenses: list[ExpenseCategory] = Field(default_factory=list, max_length=8)
    activities: list[str] = Field(default_factory=list, max_length=20)
    preferences: list[str] = Field(default_factory=list, max_length=30)
    planning_suggestions: PlanningSuggestions = Field(default_factory=PlanningSuggestions)
    requirements: list[str] = Field(default_factory=list, max_length=50)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    requirement_status: dict[str, RequirementStatus] = Field(default_factory=dict)
    constraint_status: dict[str, RequirementStatus] = Field(default_factory=dict)
    confirmed_vendors: list[str] = Field(default_factory=list, max_length=50)
    unconfirmed_vendors: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("event_name", "event_type", "purpose", "location", "venue_name")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", cleaned):
            raise ValueError("currency must be a 3-letter ISO currency code")
        if cleaned not in SUPPORTED_CURRENCIES:
            raise ValueError("currency is not currently supported")
        return cleaned

    @field_validator("event_date")
    @classmethod
    def event_date_must_not_be_in_past(cls, value: date | None) -> date | None:
        if value is not None and value < date.today():
            raise ValueError("event_date must be today or a future date")
        return value

    @field_validator(
        "activities",
        "preferences",
        "requirements",
        "constraints",
        "confirmed_vendors",
        "unconfirmed_vendors",
    )
    @classmethod
    def strip_list_items(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("items must not be blank")
        return cleaned

    @model_validator(mode="after")
    def statuses_must_match_items(self) -> "EventCreate":
        if self.category_allocations and sum(
            self.category_allocations.values(), Decimal("0")
        ) > self.budget:
            raise ValueError("category allocations must not exceed the event budget")
        unknown_requirements = self.requirement_status.keys() - set(self.requirements)
        if unknown_requirements:
            raise ValueError(
                "requirement_status keys must match requirements: "
                + ", ".join(sorted(unknown_requirements))
            )
        unknown_constraints = self.constraint_status.keys() - set(self.constraints)
        if unknown_constraints:
            raise ValueError(
                "constraint_status keys must match constraints: "
                + ", ".join(sorted(unknown_constraints))
            )
        return self


class ScenarioChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guest_count: int | None = Field(default=None, gt=0, le=1_000_000)
    budget: PositiveMoney | None = None
    event_date: date | None = None
    estimated_costs: dict[ExpenseCategory, Money] = Field(default_factory=dict)

    @field_validator("event_date")
    @classmethod
    def scenario_date_must_not_be_in_past(cls, value: date | None) -> date | None:
        if value is not None and value < date.today():
            raise ValueError("event_date must be today or a future date")
        return value

    @model_validator(mode="after")
    def require_at_least_one_change(self) -> "ScenarioChanges":
        if (
            self.guest_count is None
            and self.budget is None
            and self.event_date is None
            and not self.estimated_costs
        ):
            raise ValueError("provide at least one scenario change")
        return self


class ScenarioAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: EventCreate
    changes: ScenarioChanges


class RiskResponse(BaseModel):
    id: str
    type: str
    title: str
    severity: RiskSeverity
    reason: str
    evidence: dict[str, Any]
    mitigation: str


class ContingencyRecommendation(BaseModel):
    amount: float | None
    rate: float | None
    basis: str
    included_in_known_costs: bool


class BudgetAnalysisResponse(BaseModel):
    currency: str
    budget: float
    allocations: dict[ExpenseCategory, float]
    allocation_total: float
    estimated_costs: dict[ExpenseCategory, float]
    estimated_total: float | None
    known_expenses_total: float
    remaining_budget: float
    remaining_budget_basis: str
    status: BudgetStatus
    over_budget: bool
    overrun_amount: float
    overrun_categories: list[ExpenseCategory]
    overrun_breakdown: dict[ExpenseCategory, float]
    missing_cost_categories: list[ExpenseCategory]
    contingency_recommendation: ContingencyRecommendation
    assumptions: list[str]


class ReadinessResponse(BaseModel):
    status: ReadinessStatus
    score: int = Field(ge=0, le=100)
    basis: str


class EventPlanResponse(BaseModel):
    event_id: str | None = None
    created_at: datetime | None = None
    event: EventCreate
    budget_analysis: BudgetAnalysisResponse
    risks: list[RiskResponse]
    readiness: ReadinessResponse


class BudgetImpactResponse(BaseModel):
    original_budget: float
    scenario_budget: float
    budget_change: float
    original_estimated_total: float | None
    scenario_estimated_total: float | None
    original_known_expenses_total: float
    scenario_known_expenses_total: float
    known_expenses_change: float
    original_remaining_budget: float
    scenario_remaining_budget: float
    original_overrun_amount: float
    scenario_overrun_amount: float
    original_status: BudgetStatus
    scenario_status: BudgetStatus


class CapacityImpactResponse(BaseModel):
    original_status: CapacityStatus
    scenario_status: CapacityStatus
    original_guest_count: int | None
    scenario_guest_count: int | None
    venue_capacity: int | None


class ReadinessImpactResponse(BaseModel):
    original_status: ReadinessStatus
    scenario_status: ReadinessStatus
    original_score: int
    scenario_score: int
    score_change: int


class RiskChangesResponse(BaseModel):
    newly_introduced: list[RiskResponse]
    resolved: list[RiskResponse]
    remaining: list[RiskResponse]


class ScenarioAnalysisResponse(BaseModel):
    original_plan: EventPlanResponse
    scenario_event: EventCreate
    scenario_plan: EventPlanResponse
    budget_impact: BudgetImpactResponse
    capacity_impact: CapacityImpactResponse
    readiness_impact: ReadinessImpactResponse
    risk_changes: RiskChangesResponse
    recommendations: list[str]
    assumptions: list[str]
