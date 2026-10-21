from datetime import date, time
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.events import PlanningSuggestions


class AIEventFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_name: str | None = Field(default=None, max_length=120)
    event_type: str | None = Field(default=None, max_length=80)
    purpose: str | None = Field(default=None, max_length=500)
    event_date: date | None = None
    event_time: time | None = None
    location: str | None = Field(default=None, max_length=200)
    guest_count: int | None = Field(default=None, gt=0, le=1_000_000)
    budget: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, max_length=8)
    venue_name: str | None = Field(default=None, max_length=200)
    venue_capacity: int | None = Field(default=None, gt=0, le=1_000_000)
    activities: list[str] = Field(default_factory=list, max_length=20)
    requirements: list[str] = Field(default_factory=list, max_length=50)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    preferences: list[str] = Field(default_factory=list, max_length=30)


class AIEventUnderstanding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: AIEventFields
    planning: PlanningSuggestions = Field(default_factory=PlanningSuggestions)
    questions: list[str] = Field(default_factory=list, max_length=12)


class DashboardAICommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = Field(default=None, min_length=36, max_length=36)


class WorkflowAIGuidance(BaseModel):
    explanation: str = Field(min_length=1, max_length=1200)
    next_action: str | None = Field(default=None, max_length=300)
    action_source: str
    reasons: list[str] = Field(default_factory=list, max_length=8)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=8)


class RecoveryAISuggestion(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    suggestion: str = Field(min_length=1, max_length=500)
    tradeoffs: list[str] = Field(default_factory=list, max_length=6)
    assumptions: list[str] = Field(default_factory=list, max_length=6)
    evidence_to_verify: list[str] = Field(default_factory=list, max_length=6)


class RecoveryAIGuidance(BaseModel):
    summary: str = Field(min_length=1, max_length=800)
    suggestions: list[RecoveryAISuggestion] = Field(default_factory=list, max_length=6)


class WorkflowAIOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(min_length=1, max_length=1200)
    recommended_action: str | None = Field(default=None, max_length=300)
    reasons: list[str] = Field(default_factory=list, max_length=8)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=8)


class WorkflowAIGuidanceResponse(BaseModel):
    notice: str
    ai_model_configured: bool
    guidance: WorkflowAIGuidance | None


class RecoveryAIGuidanceResponse(BaseModel):
    notice: str
    ai_model_configured: bool
    guidance: RecoveryAIGuidance | None
