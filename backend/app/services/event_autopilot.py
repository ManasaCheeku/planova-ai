from datetime import date, datetime, timezone
from typing import Any
import uuid

from backend.app.repositories.dashboard_store import (
    RecoveryProposalConflict,
    create_recovery_case,
    create_recovery_proposal,
    ensure_workflow_tasks,
    list_recovery_cases,
    load_dashboard_records,
    load_event,
    list_event_guests,
    load_recovery_case,
    load_task,
)
from backend.app.schemas.autopilot import RecoveryCaseCreate
from backend.app.schemas.events import EventCreate
from backend.app.services.ai_provider import provider_configured
from backend.app.services.event_planner import analyze_scenario


def _ai_notice() -> str:
    if provider_configured():
        return (
            "Workflow dates, dependencies, budget calculations, and approval transitions are "
            "deterministic. Optional GenAI explanations are available on request; no external "
            "calendar, messaging, booking, vendor, or payment integration is configured."
        )
    return (
        "Workflow and recovery calculations are deterministic. No GenAI provider or external "
        "calendar, messaging, booking, vendor, or payment integration is configured."
    )

_TASK_TEMPLATES = (
    {
        "key": "confirm_event_date",
        "title": "Confirm event date and schedule",
        "description": "Validate the event date and time with the event owner.",
        "priority": "high",
        "offset": -30,
        "criteria": "The event owner confirms the date and any supplied start time.",
        "dependencies": (),
        "cost_category": None,
    },
    {
        "key": "confirm_guest_count",
        "title": "Confirm attendee estimate",
        "description": "Confirm the expected guest count before venue and catering commitments.",
        "priority": "high",
        "offset": -21,
        "criteria": "A current attendee estimate is recorded in the event plan.",
        "dependencies": ("confirm_event_date",),
        "cost_category": None,
    },
    {
        "key": "verify_venue",
        "title": "Verify venue and capacity",
        "description": "Confirm the named venue, its usable capacity, and the planned layout.",
        "priority": "high",
        "offset": -28,
        "criteria": "Venue identity and capacity are confirmed against the attendee estimate.",
        "dependencies": ("confirm_event_date",),
        "cost_category": "venue",
    },
    {
        "key": "finalize_requirements",
        "title": "Review event requirements",
        "description": "Check event requirements and constraints with the event owner.",
        "priority": "medium",
        "offset": -21,
        "criteria": "Each supplied requirement and constraint has a verified status.",
        "dependencies": ("confirm_event_date",),
        "cost_category": None,
    },
    {
        "key": "collect_estimates",
        "title": "Review known costs and missing estimates",
        "description": "Collect user-provided estimates for relevant unpriced expenses.",
        "priority": "high",
        "offset": -14,
        "criteria": "Relevant expense categories are estimated or explicitly left unknown.",
        "dependencies": ("confirm_guest_count", "verify_venue"),
        "cost_category": None,
    },
    {
        "key": "confirm_catering",
        "title": "Confirm catering plan",
        "description": "Confirm catering requirements and obtain an estimate from the event owner or vendor.",
        "priority": "high",
        "offset": -7,
        "criteria": "Catering scope is confirmed and its estimate is recorded when available.",
        "dependencies": ("confirm_guest_count", "collect_estimates"),
        "cost_category": "catering",
    },
    {
        "key": "send_invitations",
        "title": "Prepare and send invitations",
        "description": "Prepare invitation details after the date and attendee assumptions are reviewed.",
        "priority": "medium",
        "offset": -14,
        "criteria": "The invitation content and recipient list are approved by the user.",
        "dependencies": ("confirm_event_date", "confirm_guest_count"),
        "cost_category": None,
    },
    {
        "key": "final_readiness_review",
        "title": "Complete final readiness review",
        "description": "Review open requirements, risks, costs, and dependencies before the event.",
        "priority": "high",
        "offset": -2,
        "criteria": "The event owner reviews remaining risks and records the final decision.",
        "dependencies": (
            "verify_venue",
            "finalize_requirements",
            "collect_estimates",
            "confirm_catering",
            "send_invitations",
        ),
        "cost_category": None,
    },
)


def generate_workflow(event_id: str) -> dict[str, Any] | None:
    record = load_event(event_id)
    if record is None:
        return None
    event_data = record["plan"]["event"]
    event_date = date.fromisoformat(event_data["event_date"]) if event_data["event_date"] else None
    templates = tuple(
        {
            **template,
            "estimated_cost": (
                event_data.get("estimated_costs", {}).get(template["cost_category"])
                if template["cost_category"]
                else None
            ),
        }
        for template in _TASK_TEMPLATES
    )
    ensure_workflow_tasks(event_id, event_date, templates)

    workflow = build_workflow(event_id)
    if workflow is not None:
        workflow["generated"] = True
    return workflow


def _missing_information(
    task_key: str,
    event_data: dict[str, Any],
    budget_analysis: dict[str, Any],
) -> list[str]:
    if task_key == "confirm_event_date" and not event_data.get("event_date"):
        return ["The event date is not set."]
    if task_key == "confirm_guest_count" and not event_data.get("guest_count"):
        return ["The attendee count is not set."]
    if task_key == "verify_venue":
        missing = []
        if not event_data.get("venue_name"):
            missing.append("A venue name is not supplied.")
        if not event_data.get("venue_capacity"):
            missing.append("Venue capacity is not supplied.")
        return missing
    if task_key == "finalize_requirements":
        if not event_data.get("requirements") and not event_data.get("constraints"):
            return ["No requirements or constraints were supplied."]
        statuses = [
            event_data.get("requirement_status", {}).get(item, "unverified")
            for item in event_data.get("requirements", [])
        ] + [
            event_data.get("constraint_status", {}).get(item, "unverified")
            for item in event_data.get("constraints", [])
        ]
        if any(value != "satisfied" for value in statuses):
            return ["One or more requirements or constraints are not verified as satisfied."]
    if task_key in {"collect_estimates", "confirm_catering"}:
        missing_costs = budget_analysis["missing_cost_categories"]
        if task_key == "confirm_catering" and "catering" in missing_costs:
            return ["A catering estimate has not been supplied."]
        if task_key == "collect_estimates" and missing_costs:
            return [
                "No estimate supplied for: "
                + ", ".join(category.replace("_", " ") for category in missing_costs)
                + "."
            ]
    return []


def _rsvp_coordination_information(event_id: str, task_key: str) -> list[str]:
    """Surface persisted RSVP evidence in existing workflow tasks without mutating a plan."""

    if task_key not in {"confirm_guest_count", "confirm_catering", "send_invitations"}:
        return []
    guests = [guest for guest in list_event_guests(event_id) if not guest["duplicate_of_id"]]
    if not guests:
        return []
    pending = sum(guest["rsvp_status"] == "awaiting_response" for guest in guests)
    attending = sum(
        (guest["rsvp_party_size"] or guest["party_size"])
        for guest in guests
        if guest["rsvp_status"] == "attending"
    )
    information: list[str] = []
    if pending:
        information.append(
            f"{pending} tracked guest RSVP(s) are still awaiting a response; review before commitments."
        )
    if task_key in {"confirm_guest_count", "confirm_catering"} and attending:
        information.append(
            f"{attending} attendee place(s) are confirmed in RSVP records; this has not changed the event plan or catering estimate."
        )
    return information


def build_workflow(event_id: str) -> dict[str, Any] | None:
    record = load_event(event_id)
    if record is None:
        return None
    records = load_dashboard_records()
    tasks = [task for task in records["tasks"] if task["event_id"] == event_id]
    task_by_id = {task["id"]: task for task in tasks}
    plan = record["plan"]
    event_data = plan["event"]
    today = date.today()
    dependents: dict[str, list[str]] = {task["id"]: [] for task in tasks}
    blockers_by_id: dict[str, list[str]] = {}
    information_by_id: dict[str, list[str]] = {}
    missing_information: list[str] = []

    for task in tasks:
        blockers = []
        for dependency_id in task["dependencies"]:
            dependency = task_by_id.get(dependency_id)
            if dependency is None:
                blockers.append("A required dependency record is missing.")
            elif dependency["status"] != "completed":
                blockers.append(f"Waiting for: {dependency['title']}.")
            dependents.setdefault(dependency_id, []).append(task["title"])
        key = next(
            (
                template["key"]
                for template in _TASK_TEMPLATES
                if template["title"] == task["title"] and task["generated"]
            ),
            "",
        )
        information_needed = _missing_information(
            key, event_data, plan["budget_analysis"]
        )
        information_needed.extend(_rsvp_coordination_information(event_id, key))
        if task["status"] == "completed":
            blockers = []
        blockers_by_id[task["id"]] = blockers
        information_by_id[task["id"]] = information_needed
        missing_information.extend(information_needed)

    result_tasks = []
    for task in tasks:
        due = date.fromisoformat(task["due_date"]) if task["due_date"] else None
        result_tasks.append(
            {
                **task,
                "blockers": blockers_by_id[task["id"]],
                "information_needed": information_by_id[task["id"]],
                "blocks": sorted(set(dependents.get(task["id"], []))),
                "overdue": (
                    task["status"] != "completed" and due is not None and due < today
                ),
            }
        )
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    actionable = [
        task
        for task in result_tasks
        if task["status"] == "pending" and not task["blockers"]
    ]
    actionable.sort(
        key=lambda task: (
            not task["overdue"],
            priority_rank[task["priority"]],
            task["due_date"] or "9999-12-31",
        )
    )
    risks = [
        f"{risk['title']}: {risk['reason']}" for risk in plan.get("risks", [])
    ]
    return {
        "event_id": event_id,
        "event_name": event_data["event_name"],
        "generated": any(task["generated"] for task in tasks),
        "tasks": result_tasks,
        "overdue_count": sum(task["overdue"] for task in result_tasks),
        "blocked_count": sum(bool(task["blockers"]) for task in result_tasks),
        "missing_information": sorted(set(missing_information)),
        "next_action": actionable[0]["title"] if actionable else None,
        "unresolved_event_risks": risks,
        "ai_model_configured": provider_configured(),
        "notice": _ai_notice(),
    }


def _affected_tasks(
    event_id: str, disruption_type: str, task_id: str | None = None
) -> list[str]:
    tasks = [
        task
        for task in load_dashboard_records()["tasks"]
        if task["event_id"] == event_id and task["status"] == "pending"
    ]
    keywords = {
        "venue_cancellation": ("venue", "readiness"),
        "vendor_cancellation": ("vendor", "catering", "readiness"),
        "budget_change": ("cost", "estimate", "catering", "readiness"),
        "guest_count_change": ("attendee", "catering", "venue", "invitation"),
        "date_change": ("date", "invitation", "readiness"),
        "delayed_task": (),
        "equipment_availability": ("equipment", "readiness"),
        "catering_availability": ("catering", "readiness"),
        "other": (),
    }[disruption_type]
    if disruption_type == "delayed_task":
        if task_id:
            task = load_task(task_id)
            if task is None or task["event_id"] != event_id:
                raise ValueError("The delayed task does not belong to this event.")
            if task["status"] != "pending":
                raise ValueError("Only a pending task can be reported as delayed.")
            selected = {task_id}
        else:
            today = date.today().isoformat()
            selected = {
                task["id"]
                for task in tasks
                if task["due_date"] is not None and task["due_date"] < today
            }
    else:
        selected = {
            task["id"]
            for task in tasks
            if any(word in task["title"].casefold() for word in keywords)
        }
    changed = True
    while changed:
        changed = False
        for task in tasks:
            if task["id"] not in selected and set(task["dependencies"]) & selected:
                selected.add(task["id"])
                changed = True
    return [task["title"] for task in tasks if task["id"] in selected]


def create_recovery(
    event_id: str, request: RecoveryCaseCreate
) -> dict[str, Any] | None:
    record = load_event(event_id)
    if record is None:
        return None
    event = EventCreate.model_validate(record["plan"]["event"])
    changes = (
        request.changes.model_dump(exclude_unset=True, exclude_none=True)
        if request.changes
        else {}
    )
    serializable_changes = (
        request.changes.model_dump(
            mode="json", exclude_unset=True, exclude_none=True
        )
        if request.changes
        else {}
    )
    affected = _affected_tasks(
        event_id,
        request.disruption_type,
        str(request.task_id) if request.task_id else None,
    )
    uncertainties = [
        "The user-reported disruption has not been independently verified.",
        "No trusted external availability source is configured.",
        "No vendor quotations or revised market prices are available.",
        "A human must verify venue/vendor availability and any operational commitments.",
    ]
    options: list[dict[str, Any]] = []
    scenario_result = analyze_scenario(event, changes) if changes else None
    base_budget = record["plan"]["budget_analysis"]
    if scenario_result:
        budget_impact = scenario_result["budget_impact"]
        projected_budget = budget_impact["scenario_budget"]
        projected_known_cost = budget_impact["scenario_known_expenses_total"]
        projected_overrun = budget_impact["scenario_overrun_amount"]
        date_delta = None
        if event.event_date and "event_date" in changes:
            date_delta = (changes["event_date"] - event.event_date).days
        options.append(
            {
                "id": "apply_supplied_changes",
                "title": "Review the supplied plan adjustment",
                "description": (
                    "This option applies only the changes you supplied to the saved Planova plan "
                    "after approval. It does not confirm external availability or commitments."
                ),
                "readiness": "ready_for_review",
                "cost_change": budget_impact["known_expenses_change"],
                "cost_basis": (
                    "Difference in known user-supplied expense estimates; vendor, booking, "
                    "and other unknown costs are excluded."
                ),
                "projected_known_cost_inr": projected_known_cost,
                "projected_overrun_inr": projected_overrun,
                "approved_budget_inr": projected_budget,
                "timing_change_days": date_delta,
                "affected_tasks": affected,
                "unresolved_risks": [
                    item["title"]
                    for item in scenario_result["scenario_plan"]["risks"]
                ],
                "uncertainties": uncertainties,
                "proposed_changes": serializable_changes,
            }
        )
    options.extend(
        [
            {
                "id": "verify_current_commitments",
                "title": "Verify current commitments before changing the plan",
                "description": (
                    "Contact the event owner or supplier through your existing channels, "
                    "record confirmed facts, and keep this recovery case open meanwhile."
                ),
                "readiness": "requires_verification",
                "cost_change": None,
                "cost_basis": "Unknown until actual supplier information is provided.",
                "projected_known_cost_inr": base_budget["known_expenses_total"],
                "projected_overrun_inr": base_budget["overrun_amount"],
                "approved_budget_inr": base_budget["budget"],
                "timing_change_days": None,
                "affected_tasks": affected,
                "unresolved_risks": [
                    risk["title"] for risk in record["plan"].get("risks", [])
                ],
                "uncertainties": uncertainties,
                "proposed_changes": {},
            },
            {
                "id": "source_verified_alternatives",
                "title": "Gather verified alternatives and re-sequence dependent tasks",
                "description": (
                    "Collect user-sourced options, quotes, and availability; then update the "
                    "event plan with verified information. This is a suggestion, not a booking."
                ),
                "readiness": "requires_verification",
                "cost_change": None,
                "cost_basis": "Unknown; no replacement prices or availability were supplied.",
                "projected_known_cost_inr": base_budget["known_expenses_total"],
                "projected_overrun_inr": base_budget["overrun_amount"],
                "approved_budget_inr": base_budget["budget"],
                "timing_change_days": None,
                "affected_tasks": affected,
                "unresolved_risks": [
                    risk["title"] for risk in record["plan"].get("risks", [])
                ],
                "uncertainties": uncertainties,
                "proposed_changes": {},
            },
        ]
    )
    budget_analysis = record["plan"]["budget_analysis"]
    impact = {
        "known_budget_inr": record["plan"]["budget_analysis"]["budget"],
        "known_expenses_inr": record["plan"]["budget_analysis"]["known_expenses_total"],
        "known_remaining_budget_inr": record["plan"]["budget_analysis"]["remaining_budget"],
        "estimated_overrun_inr": budget_analysis["overrun_amount"],
        "estimated_overrun_percent": (
            round(
                budget_analysis["overrun_amount"] / budget_analysis["budget"] * 100,
                2,
            )
            if budget_analysis["budget"] > 0
            else None
        ),
        "overrun_categories": budget_analysis["overrun_categories"],
        "overrun_breakdown_inr": budget_analysis["overrun_breakdown"],
        "scenario_estimated_overrun_inr": (
            scenario_result["budget_impact"]["scenario_overrun_amount"]
            if scenario_result
            else None
        ),
        "scenario_budget_inr": (
            scenario_result["budget_impact"]["scenario_budget"]
            if scenario_result
            else None
        ),
        "budget_assessment": (
            "partial"
            if budget_analysis["missing_cost_categories"]
            else "based_on_supplied_estimates"
        ),
        "missing_cost_categories": budget_analysis["missing_cost_categories"],
        "affected_tasks": affected,
        "user_reported_facts": [request.description],
        "confirmed_facts": [],
        "uncertain_facts": uncertainties,
        "scenario_comparison": scenario_result,
    }
    now = datetime.now(timezone.utc).isoformat()
    case = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "created_at": now,
        "source": request.source,
        "disruption_type": request.disruption_type,
        "description": request.description,
        "status": "open",
        "impact": impact,
        "options": options,
    }
    return create_recovery_case(case)


def propose_recovery_option(
    case_id: str, option_id: str
) -> dict[str, Any] | None:
    case = load_recovery_case(case_id)
    if case is None:
        return None
    if case["status"] != "open":
        raise RecoveryProposalConflict("A resolved recovery case cannot accept proposals.")
    option = next((item for item in case["options"] if item["id"] == option_id), None)
    if option is None:
        raise ValueError("The selected recovery option does not exist.")
    return create_recovery_proposal(
        {
            "id": str(uuid.uuid4()),
            "case_id": case_id,
            "event_id": case["event_id"],
            "option_id": option_id,
            "proposed_change": option["proposed_changes"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def get_recovery_case(case_id: str) -> dict[str, Any] | None:
    return load_recovery_case(case_id)


def get_event_recovery_cases(event_id: str) -> list[dict[str, Any]]:
    return list_recovery_cases(event_id)
