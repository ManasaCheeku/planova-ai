from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.schemas.events import ExpenseCategory, Money


ExpenseStatus = Literal["committed", "paid"]


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ExpenseCategory
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    expense_date: date
    description: str = Field(min_length=1, max_length=500)
    payment_status: ExpenseStatus
    vendor_name: str | None = Field(default=None, max_length=160)
    idempotency_key: UUID = Field(default_factory=uuid4)

    @field_validator("description", "vendor_name")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class ExpenseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ExpenseCategory | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    expense_date: date | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)
    payment_status: ExpenseStatus | None = None
    vendor_name: str | None = Field(default=None, max_length=160)

    @field_validator("description", "vendor_name")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @model_validator(mode="after")
    def require_changes(self) -> "ExpenseUpdate":
        if not self.model_fields_set:
            raise ValueError("provide at least one expense field to update")
        for field in ("category", "amount", "expense_date", "description", "payment_status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ExpenseResponse(BaseModel):
    id: str
    event_id: str
    created_at: datetime
    updated_at: datetime
    category: ExpenseCategory
    amount: float
    expense_date: date
    description: str
    payment_status: ExpenseStatus
    vendor_name: str | None


class BudgetCategorySummary(BaseModel):
    category: ExpenseCategory
    allocation: float
    estimated: float | None
    committed: float
    paid: float
    recorded_total: float
    projected: float | None
    utilization_percent: float | None
    missing_estimate: bool


class BudgetAlert(BaseModel):
    id: str
    severity: Literal["info", "warning", "high"]
    category: ExpenseCategory | None
    title: str
    explanation: str
    supporting_figures: dict[str, float | str | None]


class BudgetRecommendation(BaseModel):
    id: str
    issue: str
    supporting_figures: dict[str, float | str | None]
    proposed_change: str
    estimated_savings: float | None
    savings_basis: str
    tradeoffs: list[str]
    uncertainty: list[str]
    requires_approval: Literal[True] = True
    proposed_changes: dict[str, dict[str, float]] | None = None


class BudgetSummaryResponse(BaseModel):
    event_id: str
    event_name: str
    currency: str
    approved_budget: float
    planned_allocations: float
    estimated_total: float | None
    committed_total: float
    paid_total: float
    recorded_total: float
    remaining_available: float
    projected_total: float | None
    projected_overrun: float | None
    overrun_percent: float | None
    assessment: Literal["complete", "partial"]
    missing_cost_categories: list[ExpenseCategory]
    categories: list[BudgetCategorySummary]
    expenses: list[ExpenseResponse]
    proposals: list[dict[str, object]]
    alerts: list[BudgetAlert]
    recommendations: list[BudgetRecommendation]
    assumptions: list[str]


class BudgetChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    estimated_costs: dict[ExpenseCategory, Money] | None = None
    category_allocations: dict[ExpenseCategory, Money] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "BudgetChange":
        if not any(
            value is not None
            for value in (self.budget, self.estimated_costs, self.category_allocations)
        ):
            raise ValueError("provide a budget, estimate, or allocation change")
        if self.estimated_costs == {} or self.category_allocations == {}:
            raise ValueError("budget change dictionaries must not be empty")
        return self


class BudgetProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: BudgetChange
    rationale: str = Field(min_length=1, max_length=500)
    idempotency_key: UUID = Field(default_factory=uuid4)

    @field_validator("rationale")
    @classmethod
    def clean_rationale(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("rationale must not be blank")
        return cleaned


class BudgetProposalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]


class BudgetProposalResponse(BaseModel):
    id: str
    event_id: str
    status: Literal["proposed", "applied", "rejected"]
    rationale: str
    proposed_changes: dict[str, object]
    preview: dict[str, object]
    created_at: datetime
    updated_at: datetime
    result: dict[str, object] | None


class BudgetGuidanceResponse(BaseModel):
    ai_model_configured: bool
    guidance: dict[str, object] | None
    notice: str
