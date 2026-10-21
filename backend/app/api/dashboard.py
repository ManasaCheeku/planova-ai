from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from backend.app.schemas.ai import (
    RecoveryAIGuidanceResponse,
    WorkflowAIGuidanceResponse,
)
from backend.app.schemas.budget import (
    BudgetGuidanceResponse,
    BudgetProposalCreate,
    BudgetProposalResponse,
    BudgetSummaryResponse,
    ExpenseCreate,
    ExpenseResponse,
    ExpenseUpdate,
)
from backend.app.repositories.dashboard_store import (
    RecoveryProposalConflict,
    create_task,
    decide_recovery_proposal,
    event_exists,
    update_event_status,
    update_task_record,
)
from backend.app.schemas.dashboard import (
    DashboardCommandRequest,
    DashboardCommandResponse,
    DashboardEventUpdate,
    DashboardResponse,
    DashboardTaskCreate,
    DashboardTaskResponse,
    DashboardTaskUpdate,
)
from backend.app.schemas.autopilot import (
    RecoveryCaseCreate,
    RecoveryCaseResolution,
    RecoveryCaseResponse,
    RecoveryProposalCreate,
    RecoveryProposalResponse,
    WorkflowResponse,
)
from backend.app.services.event_autopilot import (
    build_workflow,
    create_recovery,
    generate_workflow,
    get_event_recovery_cases,
    get_recovery_case,
    propose_recovery_option,
)
from backend.app.repositories.dashboard_store import resolve_recovery_case
from backend.app.services.ai_assistant import propose_event_plan
from backend.app.services.ai_guidance import (
    recovery_guidance,
    workflow_guidance,
)
from backend.app.services.ai_provider import AIProviderError
from backend.app.services.budget_guardian import (
    add_expense,
    ai_budget_guidance,
    budget_summary,
    decide_budget_change,
    edit_expense,
    propose_budget_plan_change,
)
from backend.app.services.dashboard_service import build_dashboard_snapshot


router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard() -> dict:
    return build_dashboard_snapshot()


@router.get("/tasks", response_model=list[DashboardTaskResponse])
def list_dashboard_tasks(
    event_id: UUID | None = None,
    assigned_to: str | None = Query(default=None, max_length=120),
    status_filter: Literal["pending", "in_progress", "completed", "overdue", "blocked"]
    | None = Query(default=None, alias="status"),
    priority: Literal["low", "medium", "high"] | None = None,
) -> list[dict]:
    tasks = build_dashboard_snapshot()["tasks"]
    if event_id is not None:
        tasks = [task for task in tasks if task["event_id"] == str(event_id)]
    if assigned_to is not None:
        normalized_assignee = assigned_to.strip().casefold()
        tasks = [
            task
            for task in tasks
            if (task["assigned_to"] or "").casefold() == normalized_assignee
        ]
    if priority is not None:
        tasks = [task for task in tasks if task["priority"] == priority]
    if status_filter == "overdue":
        tasks = [task for task in tasks if task["overdue"]]
    elif status_filter == "blocked":
        tasks = [task for task in tasks if task["blocked"]]
    elif status_filter is not None:
        tasks = [task for task in tasks if task["status"] == status_filter]
    return tasks


@router.get(
    "/events/{event_id}/budget",
    response_model=BudgetSummaryResponse,
)
def event_budget(event_id: UUID) -> dict:
    summary = budget_summary(str(event_id))
    if summary is None:
        raise HTTPException(status_code=404, detail="The event was not found.")
    return summary


@router.post(
    "/events/{event_id}/expenses",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_event_expense(
    event_id: UUID, request: ExpenseCreate, response: Response
) -> dict:
    try:
        result = add_expense(str(event_id), request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="The event was not found.")
    expense, created = result
    if not created:
        response.status_code = status.HTTP_200_OK
    return expense


@router.patch(
    "/events/{event_id}/expenses/{expense_id}",
    response_model=ExpenseResponse,
)
def update_event_expense_record(
    event_id: UUID, expense_id: UUID, request: ExpenseUpdate
) -> dict:
    try:
        expense = edit_expense(str(event_id), str(expense_id), request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if expense is None:
        raise HTTPException(status_code=404, detail="The event or expense was not found.")
    return expense


@router.post(
    "/events/{event_id}/budget/proposals",
    response_model=BudgetProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event_budget_proposal(
    event_id: UUID, request: BudgetProposalCreate, response: Response
) -> dict:
    try:
        result = propose_budget_plan_change(str(event_id), request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="The event was not found.")
    proposal, created = result
    if not created:
        response.status_code = status.HTTP_200_OK
    return proposal


@router.post(
    "/budget-proposals/{proposal_id}/approve",
    response_model=BudgetProposalResponse,
)
def approve_event_budget_proposal(proposal_id: UUID) -> dict:
    try:
        proposal = decide_budget_change(str(proposal_id), "approve")
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if proposal is None:
        raise HTTPException(status_code=404, detail="The budget proposal was not found.")
    return proposal


@router.post(
    "/budget-proposals/{proposal_id}/reject",
    response_model=BudgetProposalResponse,
)
def reject_event_budget_proposal(proposal_id: UUID) -> dict:
    try:
        proposal = decide_budget_change(str(proposal_id), "reject")
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if proposal is None:
        raise HTTPException(status_code=404, detail="The budget proposal was not found.")
    return proposal


@router.post(
    "/events/{event_id}/budget/ai-guidance",
    response_model=BudgetGuidanceResponse,
)
def event_budget_ai_guidance(event_id: UUID) -> dict:
    try:
        guidance = ai_budget_guidance(str(event_id))
    except AIProviderError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    if guidance is None:
        raise HTTPException(status_code=404, detail="The event was not found.")
    return guidance


@router.post("/command", response_model=DashboardCommandResponse)
def dashboard_command(request: DashboardCommandRequest) -> dict:
    try:
        return propose_event_plan(
            request.message,
            str(request.conversation_id) if request.conversation_id else None,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except AIProviderError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.post("/tasks", response_model=DashboardTaskResponse, status_code=status.HTTP_201_CREATED)
def add_dashboard_task(task: DashboardTaskCreate) -> dict:
    if task.event_id and not event_exists(str(task.event_id)):
        raise HTTPException(status_code=404, detail="The linked event was not found.")
    try:
        created = create_task(
            task.title,
            task.due_date,
            str(task.event_id) if task.event_id else None,
            description=task.description,
            priority=task.priority,
            assigned_to=task.assigned_to,
            estimated_cost=task.estimated_cost,
            completion_criteria=task.completion_criteria,
            dependencies=[str(dependency) for dependency in task.dependencies],
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    snapshot_task = next(
        (
            saved
            for saved in build_dashboard_snapshot()["tasks"]
            if saved["id"] == created["id"]
        ),
        None,
    )
    if snapshot_task is None:
        raise HTTPException(status_code=500, detail="The saved task could not be reloaded.")
    return snapshot_task


@router.patch("/tasks/{task_id}", response_model=DashboardTaskResponse)
def change_task_status(task_id: UUID, update: DashboardTaskUpdate) -> dict:
    try:
        changes = update.model_dump(exclude_unset=True)
        if "dependencies" in changes and changes["dependencies"] is not None:
            changes["dependencies"] = [str(dependency) for dependency in changes["dependencies"]]
        updated = update_task_record(str(task_id), changes)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not updated:
        raise HTTPException(status_code=404, detail="The task was not found.")
    dashboard = build_dashboard_snapshot()
    return next(task for task in dashboard["tasks"] if task["id"] == str(task_id))


@router.patch("/events/{event_id}", response_model=DashboardResponse)
def change_event_status(event_id: str, update: DashboardEventUpdate) -> dict:
    if not update_event_status(event_id, update.status):
        raise HTTPException(status_code=404, detail="The event was not found.")
    return build_dashboard_snapshot()


@router.get("/events/{event_id}/workflow", response_model=WorkflowResponse)
def event_workflow(event_id: UUID) -> dict:
    workflow = build_workflow(str(event_id))
    if workflow is None:
        raise HTTPException(status_code=404, detail="The event was not found.")
    return workflow


@router.post(
    "/events/{event_id}/workflow/generate",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event_workflow(event_id: UUID) -> dict:
    workflow = generate_workflow(str(event_id))
    if workflow is None:
        raise HTTPException(status_code=404, detail="The event was not found.")
    return workflow


@router.post(
    "/events/{event_id}/workflow/ai-guidance",
    response_model=WorkflowAIGuidanceResponse,
)
def event_workflow_ai_guidance(event_id: UUID) -> dict:
    try:
        guidance = workflow_guidance(str(event_id))
    except AIProviderError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    if guidance is None:
        raise HTTPException(status_code=404, detail="The event was not found.")
    return guidance


@router.get(
    "/events/{event_id}/recovery-cases",
    response_model=list[RecoveryCaseResponse],
)
def event_recovery_cases(event_id: UUID) -> list[dict]:
    if not event_exists(str(event_id)):
        raise HTTPException(status_code=404, detail="The event was not found.")
    return get_event_recovery_cases(str(event_id))


@router.post(
    "/recovery-cases/{case_id}/ai-guidance",
    response_model=RecoveryAIGuidanceResponse,
)
def recovery_case_ai_guidance(case_id: UUID) -> dict:
    try:
        guidance = recovery_guidance(str(case_id))
    except AIProviderError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    if guidance is None:
        raise HTTPException(status_code=404, detail="The recovery case was not found.")
    return guidance


@router.post(
    "/recovery-cases/{case_id}/resolve",
    response_model=RecoveryCaseResponse,
)
def resolve_case(case_id: UUID, request: RecoveryCaseResolution) -> dict:
    try:
        case = resolve_recovery_case(str(case_id), request.summary)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if case is None:
        raise HTTPException(status_code=404, detail="The recovery case was not found.")
    return case


@router.post(
    "/events/{event_id}/recovery-cases",
    response_model=RecoveryCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def report_recovery_case(event_id: UUID, request: RecoveryCaseCreate) -> dict:
    try:
        case = create_recovery(str(event_id), request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if case is None:
        raise HTTPException(status_code=404, detail="The event was not found.")
    saved_case = get_recovery_case(case["id"])
    if saved_case is None:
        raise RuntimeError("The recovery case could not be reloaded after creation.")
    return saved_case


@router.post(
    "/recovery-cases/{case_id}/proposals",
    response_model=RecoveryCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def propose_recovery(case_id: UUID, request: RecoveryProposalCreate) -> dict:
    try:
        proposal = propose_recovery_option(str(case_id), request.option_id)
    except RecoveryProposalConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if proposal is None:
        raise HTTPException(status_code=404, detail="The recovery case was not found.")
    saved_case = get_recovery_case(str(case_id))
    if saved_case is None:
        raise RuntimeError("The recovery proposal was saved but its case could not be reloaded.")
    return saved_case


@router.post(
    "/recovery-proposals/{proposal_id}/approve",
    response_model=RecoveryProposalResponse,
)
def approve_recovery_proposal(proposal_id: UUID) -> dict:
    try:
        proposal = decide_recovery_proposal(str(proposal_id), "approve")
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if proposal is None:
        raise HTTPException(status_code=404, detail="The proposal was not found.")
    return proposal


@router.post(
    "/recovery-proposals/{proposal_id}/reject",
    response_model=RecoveryProposalResponse,
)
def reject_recovery_proposal(proposal_id: UUID) -> dict:
    try:
        proposal = decide_recovery_proposal(str(proposal_id), "reject")
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if proposal is None:
        raise HTTPException(status_code=404, detail="The proposal was not found.")
    return proposal
