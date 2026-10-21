from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from backend.app.schemas.events import EventCreate, ExpenseCategory


CENT = Decimal("0.01")
CONTINGENCY_RATE = Decimal("0.10")
EXPECTED_EXPENSE_CATEGORIES = (
    "venue",
    "catering",
    "production",
    "staffing",
    "contingency",
)
ALLOCATION_SHARES = {
    "venue": Decimal("0.30"),
    "catering": Decimal("0.22"),
    "equipment": Decimal("0.06"),
    "activities": Decimal("0.06"),
    "production": Decimal("0.06"),
    "staffing": Decimal("0.05"),
    "decoration": Decimal("0.07"),
    "photography": Decimal("0.05"),
    "entertainment": Decimal("0.05"),
    "transport": Decimal("0.02"),
    "accommodation": Decimal("0.01"),
    "invitations": Decimal("0.01"),
    "contingency": Decimal("0.04"),
    "miscellaneous": Decimal("0"),
    "other": Decimal("0"),
}
SEVERITY_WEIGHT = {"low": 5, "medium": 15, "high": 30}
RISK_TITLES = {
    "budget_overrun": "Known expenses exceed the budget",
    "insufficient_budget": "Known expenses exceed the budget",
    "venue_capacity_exceeded": "Attendee count exceeds venue capacity",
    "venue_capacity": "Attendee count exceeds venue capacity",
    "venue_capacity_unverified": "Venue capacity is unverified",
    "venue_capacity_unknown": "Venue capacity is unverified",
    "attendee_count_missing": "Attendee count is missing",
    "event_date_missing": "Event date is missing",
    "event_type_missing": "Event type is missing",
    "location_missing": "Event location is missing",
    "expense_estimate_missing": "Expense estimate is missing",
    "requirements_missing": "Event requirements are missing",
    "missing_requirements": "Event requirements are missing",
    "requirement_unverified": "Requirement has not been verified",
    "requirement_unsatisfied": "Requirement is marked unsatisfied",
    "constraint_unverified": "Constraint has not been verified",
    "constraint_unsatisfied": "Constraint is marked unsatisfied",
    "vendor_confirmation_unknown": "Vendor confirmation is unknown",
    "unconfirmed_vendors": "Vendor confirmation is unknown",
    "vendor_unconfirmed": "Vendor is not confirmed",
    "timeline_tight": "Event timeline is tight",
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _format_money(amount: Decimal | float, currency: str) -> str:
    value = Decimal(str(amount))
    if currency == "INR":
        return f"₹{value:,.2f}"
    return f"{currency} {value:,.2f}"


def _serialize_event(event: EventCreate) -> dict[str, Any]:
    result = event.model_dump(mode="json")
    result["budget"] = float(event.budget)
    result["estimated_costs"] = {
        category: float(amount)
        for category, amount in event.estimated_costs.items()
    }
    return result


def _risk(
    risk_id: str,
    risk_type: str,
    severity: str,
    reason: str,
    evidence: dict[str, Any],
    mitigation: str,
) -> dict[str, Any]:
    return {
        "id": risk_id,
        "type": risk_type,
        "title": RISK_TITLES[risk_type],
        "severity": severity,
        "reason": reason,
        "evidence": evidence,
        "mitigation": mitigation,
    }


def _build_risks(event: EventCreate, budget: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []

    if budget["over_budget"]:
        risks.append(
            _risk(
                "budget_overrun",
                "insufficient_budget",
                "high",
                (
                    f"Known expenses total {_format_money(budget['known_expenses_total'], event.currency)}, "
                    f"which is {_format_money(budget['overrun_amount'], event.currency)} above the "
                    f"{_format_money(budget['budget'], event.currency)} budget."
                ),
                {
                    "budget_inr": budget["budget"],
                    "known_expenses_inr": budget["known_expenses_total"],
                    "overrun_inr": budget["overrun_amount"],
                    "expense_categories": budget["overrun_categories"],
                    "expense_estimates_inr": budget["overrun_breakdown"],
                },
                "Reduce event scope or obtain revised estimates before committing.",
            )
        )

    if event.guest_count is None:
        risks.append(
            _risk(
                "attendee_count_missing",
                "attendee_count_missing",
                "medium",
                "An attendee count was not supplied, so capacity and per-attendee planning cannot be assessed.",
                {"guest_count": "not supplied"},
                "Add the expected attendee count to assess capacity and planning needs.",
            )
        )
    if event.venue_capacity is None:
        risks.append(
            _risk(
                "venue_capacity_unknown",
                "venue_capacity_unverified",
                "medium",
                "Venue capacity was not supplied, so attendee capacity cannot be verified.",
                {
                    "venue_name": event.venue_name or "not supplied",
                    "venue_capacity": "not supplied",
                    "guest_count": event.guest_count,
                },
                "Confirm the venue's approved capacity for the planned layout.",
            )
        )
    elif event.guest_count is not None and event.guest_count > event.venue_capacity:
        risks.append(
            _risk(
                "venue_capacity_exceeded",
                "venue_capacity",
                "high",
                (
                    f"The attendee count ({event.guest_count}) exceeds the "
                    f"provided venue capacity ({event.venue_capacity})."
                ),
                {
                    "guest_count": event.guest_count,
                    "venue_capacity": event.venue_capacity,
                    "venue_name": event.venue_name or "not supplied",
                },
                "Choose a venue with adequate capacity or reduce the attendee count.",
            )
        )

    for field_name, value in (
        ("event_type", event.event_type),
        ("event_date", event.event_date),
        ("location", event.location),
    ):
        if value is None:
            risk_type = f"{field_name}_missing"
            risks.append(
                _risk(
                    risk_type,
                    risk_type,
                    "medium",
                    f"{field_name.replace('_', ' ').capitalize()} was not supplied.",
                    {field_name: "not supplied"},
                    f"Add the {field_name.replace('_', ' ')} to complete the plan.",
                )
            )

    for category in budget["missing_cost_categories"]:
        risks.append(
            _risk(
                f"expense_estimate_missing:{category}",
                "expense_estimate_missing",
                "medium",
                f"No estimate was supplied for {category.replace('_', ' ')} expenses.",
                {"expense_category": category, "estimate": "not supplied"},
                f"Gather a user-provided estimate for {category.replace('_', ' ')}.",
            )
        )

    if not event.requirements:
        risks.append(
            _risk(
                "missing_requirements",
                "missing_requirements",
                "medium",
                "No event requirements were supplied, so priority needs cannot be checked.",
                {"requirements": "empty list"},
                "Document accessibility needs, priorities, and must-have services.",
            )
        )
    else:
        for requirement in event.requirements:
            status = event.requirement_status.get(requirement, "unverified")
            if status == "satisfied":
                continue
            risk_type = (
                "requirement_unsatisfied"
                if status == "unsatisfied"
                else "requirement_unverified"
            )
            risks.append(
                _risk(
                    f"{risk_type}:{requirement}",
                    risk_type,
                    "high" if status == "unsatisfied" else "medium",
                    (
                        f"Requirement '{requirement}' is marked unsatisfied."
                        if status == "unsatisfied"
                        else f"No status was supplied to confirm requirement '{requirement}'."
                    ),
                    {"requirement": requirement, "status": status},
                    (
                        "Resolve this requirement and update its status before proceeding."
                        if status == "unsatisfied"
                        else "Verify this requirement and record whether it is satisfied."
                    ),
                )
            )

    for constraint in event.constraints:
        status = event.constraint_status.get(constraint, "unverified")
        if status == "satisfied":
            continue
        risk_type = "constraint_unsatisfied" if status == "unsatisfied" else "constraint_unverified"
        risks.append(
            _risk(
                f"{risk_type}:{constraint}",
                risk_type,
                "high" if status == "unsatisfied" else "medium",
                (
                    f"Constraint '{constraint}' is marked unsatisfied."
                    if status == "unsatisfied"
                    else f"No status was supplied to confirm constraint '{constraint}'."
                ),
                {"constraint": constraint, "status": status},
                (
                    "Resolve this constraint or revise the plan before proceeding."
                    if status == "unsatisfied"
                    else "Verify this constraint and record whether the plan satisfies it."
                ),
            )
        )

    for vendor in event.unconfirmed_vendors:
        risks.append(
            _risk(
                f"vendor_unconfirmed:{vendor}",
                "vendor_unconfirmed",
                "medium",
                f"Vendor '{vendor}' was listed as not confirmed.",
                {"vendor": vendor, "status": "unconfirmed"},
                "Confirm the vendor's scope and terms before relying on their service.",
            )
        )
    if not event.confirmed_vendors and not event.unconfirmed_vendors:
        risks.append(
            _risk(
                "unconfirmed_vendors",
                "unconfirmed_vendors",
                "medium",
                "No confirmed or unconfirmed vendor information was supplied.",
                {"confirmed_vendors": "empty list", "unconfirmed_vendors": "empty list"},
                "Record vendors that are confirmed and identify vendors still to be confirmed.",
            )
        )

    if event.event_date is not None:
        days_until_event = (event.event_date - date.today()).days
        if days_until_event <= 14:
            risks.append(
                _risk(
                    "timeline_tight",
                    "timeline_tight",
                    "high" if days_until_event <= 7 else "medium",
                    f"The event date is {days_until_event} day(s) away.",
                    {"event_date": event.event_date.isoformat(), "days_until_event": days_until_event},
                    "Prioritize critical decisions and confirm outstanding details promptly.",
                )
            )
    return risks


def _build_budget_analysis(event: EventCreate) -> dict[str, Any]:
    if event.category_allocations:
        allocations = {
            category: _money(amount)
            for category, amount in event.category_allocations.items()
        }
        residual = event.budget - sum(allocations.values(), Decimal("0"))
        allocations["miscellaneous"] = (
            allocations.get("miscellaneous", Decimal("0")) + residual
        )
        for category in ALLOCATION_SHARES:
            allocations.setdefault(category, Decimal("0"))
    else:
        allocations = {}
        allocated_so_far = Decimal("0")
        categories = list(ALLOCATION_SHARES.items())
        for category, share in categories[:-1]:
            allocation = _money(event.budget * share)
            allocations[category] = allocation
            allocated_so_far += allocation
        last_category = categories[-1][0]
        allocations[last_category] = event.budget - allocated_so_far

    known_total = _money(sum(event.estimated_costs.values(), Decimal("0")))
    missing_categories = sorted(
        (
            set(EXPECTED_EXPENSE_CATEGORIES)
            | set(event.planned_expenses)
        )
        - event.estimated_costs.keys()
    )
    overrun = max(Decimal("0"), _money(known_total - event.budget))
    overrun_categories: list[ExpenseCategory] = [
        category
        for category, amount in event.estimated_costs.items()
        if overrun > 0 and amount > 0
    ]
    overrun_categories.sort()
    overrun_breakdown: dict[ExpenseCategory, float] = {
        category: float(event.estimated_costs[category])
        for category in overrun_categories
    }
    direct_expenses = sum(
        (
            amount
            for category, amount in event.estimated_costs.items()
            if category != "contingency"
        ),
        Decimal("0"),
    )
    recommended_contingency = (
        _money(direct_expenses * CONTINGENCY_RATE)
        if direct_expenses > 0
        else None
    )
    over_budget = overrun > 0
    status = (
        "over_budget"
        if over_budget
        else "incomplete"
        if missing_categories
        else "within_budget"
    )

    return {
        "currency": event.currency,
        "budget": float(event.budget),
        "allocations": {category: float(amount) for category, amount in allocations.items()},
        "allocation_total": float(sum(allocations.values(), Decimal("0"))),
        "estimated_costs": {
            category: float(amount)
            for category, amount in event.estimated_costs.items()
        },
        "estimated_total": float(known_total) if event.estimated_costs else None,
        "known_expenses_total": float(known_total),
        "remaining_budget": float(_money(event.budget - known_total)),
        "remaining_budget_basis": (
            "Budget minus supplied known expense estimates; unestimated categories are excluded."
        ),
        "status": status,
        "over_budget": over_budget,
        "overrun_amount": float(overrun),
        "overrun_categories": overrun_categories,
        "overrun_breakdown": overrun_breakdown,
        "missing_cost_categories": missing_categories,
        "contingency_recommendation": {
            "amount": float(recommended_contingency) if recommended_contingency is not None else None,
            "rate": float(CONTINGENCY_RATE) if recommended_contingency is not None else None,
            "basis": (
                "10% of supplied non-contingency estimates; informational only, "
                "and not included in known costs or remaining budget."
                if recommended_contingency is not None
                else "No positive non-contingency estimates were supplied, so no recommendation is calculated."
            ),
            "included_in_known_costs": False,
        },
        "assumptions": [
            f"All monetary amounts are {event.currency}; no currency conversion is performed.",
            "Known expenses are the sum of only user-supplied expense estimates; omitted categories are unknown, not zero.",
            "Equipment, activities, and other optional categories are checked for missing estimates only when listed as planned expenses.",
            "Remaining budget is budget minus known expenses and excludes unestimated categories.",
            "Budget allocations are planning targets, not estimates, quotes, or vendor prices.",
            "A suggested contingency is informational and is not added to known costs or counted twice.",
        ],
    }


def _readiness(risks: list[dict[str, Any]]) -> dict[str, Any]:
    score = max(
        0,
        100 - sum(SEVERITY_WEIGHT[risk["severity"]] for risk in risks),
    )
    status = (
        "at_risk"
        if any(risk["severity"] == "high" for risk in risks)
        else "needs_attention"
        if risks
        else "ready"
    )
    return {
        "status": status,
        "score": score,
        "basis": (
            "Score starts at 100 and subtracts 30 per high, 15 per medium, and "
            "5 per low risk, floored at 0. Any high risk is at_risk; otherwise "
            "any risk is needs_attention; no risks is ready."
        ),
    }


def build_event_plan(event: EventCreate) -> dict[str, Any]:
    budget = _build_budget_analysis(event)
    risks = _build_risks(event, budget)
    return {
        "event": _serialize_event(event),
        "budget_analysis": budget,
        "risks": risks,
        "readiness": _readiness(risks),
    }


def _capacity_status(event: EventCreate) -> str:
    if event.venue_capacity is None or event.guest_count is None:
        return "unknown"
    return (
        "exceeds_capacity"
        if event.guest_count > event.venue_capacity
        else "within_capacity"
    )


def _risk_changes(
    original_risks: list[dict[str, Any]], scenario_risks: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    original = {risk["id"]: risk for risk in original_risks}
    proposed = {risk["id"]: risk for risk in scenario_risks}
    return {
        "newly_introduced": [risk for key, risk in proposed.items() if key not in original],
        "resolved": [risk for key, risk in original.items() if key not in proposed],
        "remaining": [risk for key, risk in proposed.items() if key in original],
    }


def analyze_scenario(event: EventCreate, changes: dict[str, Any]) -> dict[str, Any]:
    original_plan = build_event_plan(event)
    merged_changes = dict(changes)
    if "estimated_costs" in merged_changes:
        merged_costs = dict(event.estimated_costs)
        merged_costs.update(merged_changes["estimated_costs"])
        merged_changes["estimated_costs"] = merged_costs
    scenario_event = EventCreate.model_validate(
        {**event.model_dump(), **merged_changes}
    )
    scenario_plan = build_event_plan(scenario_event)

    original_budget = original_plan["budget_analysis"]
    scenario_budget = scenario_plan["budget_analysis"]
    original_score = original_plan["readiness"]["score"]
    scenario_score = scenario_plan["readiness"]["score"]
    score_change = scenario_score - original_score
    risk_changes = _risk_changes(original_plan["risks"], scenario_plan["risks"])

    recommendations: list[str] = []
    budget_change = _money(scenario_event.budget - event.budget)
    known_expenses_change = _money(
        Decimal(str(scenario_budget["known_expenses_total"]))
        - Decimal(str(original_budget["known_expenses_total"]))
    )
    if scenario_budget["over_budget"]:
        recommendations.append(
            f"Known scenario expenses exceed the proposed budget by {_format_money(scenario_budget['overrun_amount'], scenario_event.currency)}."
        )
    if budget_change != 0:
        direction = "increases" if budget_change > 0 else "decreases"
        recommendations.append(
            f"The proposed budget {direction} by {_format_money(abs(budget_change), scenario_event.currency)}."
        )
    if known_expenses_change != 0:
        direction = "increase" if known_expenses_change > 0 else "decrease"
        recommendations.append(
            f"Known expense estimates {direction} by {_format_money(abs(known_expenses_change), scenario_event.currency)}; unknown costs remain excluded."
        )
    if _capacity_status(event) != "exceeds_capacity" and _capacity_status(scenario_event) == "exceeds_capacity":
        recommendations.append(
            "The attendee change exceeds the known venue capacity; reduce attendance or confirm a suitable venue."
        )
    if score_change > 0:
        recommendations.append(
            f"Readiness improved by {score_change} points because the proposed inputs removed one or more identified risks."
        )
    elif score_change < 0:
        recommendations.append(
            f"Readiness declined by {abs(score_change)} points because the proposed inputs introduced or increased planning risks."
        )
    if not recommendations:
        recommendations.append(
            "No material change was detected by the available budget, capacity, date, and requirement checks."
        )

    original_guest_count = event.guest_count
    scenario_guest_count = scenario_event.guest_count
    return {
        "original_plan": original_plan,
        "scenario_event": _serialize_event(scenario_event),
        "scenario_plan": scenario_plan,
        "budget_impact": {
            "original_budget": original_budget["budget"],
            "scenario_budget": scenario_budget["budget"],
            "budget_change": float(_money(scenario_event.budget - event.budget)),
            "original_estimated_total": original_budget["estimated_total"],
            "scenario_estimated_total": scenario_budget["estimated_total"],
            "original_known_expenses_total": original_budget["known_expenses_total"],
            "scenario_known_expenses_total": scenario_budget["known_expenses_total"],
            "known_expenses_change": float(
                known_expenses_change
            ),
            "original_remaining_budget": original_budget["remaining_budget"],
            "scenario_remaining_budget": scenario_budget["remaining_budget"],
            "original_overrun_amount": original_budget["overrun_amount"],
            "scenario_overrun_amount": scenario_budget["overrun_amount"],
            "original_status": original_budget["status"],
            "scenario_status": scenario_budget["status"],
        },
        "capacity_impact": {
            "original_status": _capacity_status(event),
            "scenario_status": _capacity_status(scenario_event),
            "original_guest_count": original_guest_count,
            "scenario_guest_count": scenario_guest_count,
            "venue_capacity": scenario_event.venue_capacity,
        },
        "readiness_impact": {
            "original_status": original_plan["readiness"]["status"],
            "scenario_status": scenario_plan["readiness"]["status"],
            "original_score": original_score,
            "scenario_score": scenario_score,
            "score_change": score_change,
        },
        "risk_changes": risk_changes,
        "recommendations": recommendations,
        "assumptions": [
            "Both plans are calculated with the same deterministic budget and risk calculations.",
            "Scenario expense estimates update the supplied categories and retain unchanged original estimates.",
            "Only user-supplied estimates are included; unestimated expenses remain unknown.",
            "A risk is resolved only when its triggering condition is absent from the proposed plan.",
            "No vendor quotations, market rates, or external availability data are retrieved.",
        ],
    }
