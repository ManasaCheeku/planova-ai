from fastapi import APIRouter

from backend.app.schemas.events import (
    EventCreate,
    EventPlanResponse,
    ScenarioAnalysisRequest,
    ScenarioAnalysisResponse,
)
from backend.app.repositories.dashboard_store import save_event
from backend.app.services.event_planner import analyze_scenario, build_event_plan


router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.post("", response_model=EventPlanResponse)
def create_event(event: EventCreate) -> dict:
    return save_event(build_event_plan(event))


@router.post("/scenario-analysis", response_model=ScenarioAnalysisResponse)
def scenario_analysis(request: ScenarioAnalysisRequest) -> dict:
    return analyze_scenario(
        request.event,
        request.changes.model_dump(exclude_unset=True, exclude_none=True),
    )
