from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from backend.app.repositories.dashboard_store import load_dashboard_records
from backend.app.services.ai_provider import provider_configured
from backend.app.services.invitations import delivery_configuration


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_dashboard_snapshot() -> dict[str, Any]:
    delivery = delivery_configuration()
    records = load_dashboard_records()
    events = records["events"]
    tasks = records["tasks"]
    today = date.today()
    tasks_by_id = {task["id"]: task for task in tasks}
    for task in tasks:
        dependencies = [
            tasks_by_id[dependency_id]
            for dependency_id in task["dependencies"]
            if dependency_id in tasks_by_id
        ]
        task["blockers"] = [
            dependency["title"]
            for dependency in dependencies
            if dependency["status"] != "completed"
        ]
        missing_dependencies = [
            dependency_id
            for dependency_id in task["dependencies"]
            if dependency_id not in tasks_by_id
        ]
        task["blockers"].extend(
            f"Missing task ({dependency_id})" for dependency_id in missing_dependencies
        )
        task["blocked"] = task["status"] != "completed" and bool(task["blockers"])
        task["overdue"] = (
            task["status"] != "completed"
            and task["due_date"] is not None
            and date.fromisoformat(task["due_date"]) < today
        )
    active_events = [item for item in events if item["status"] == "scheduled"]
    non_cancelled_events = [item for item in events if item["status"] != "cancelled"]
    upcoming_events = [
        item
        for item in active_events
        if item["plan"]["event"].get("event_date")
        and date.fromisoformat(item["plan"]["event"]["event_date"]) >= today
    ]
    cancelled_count = sum(item["status"] == "cancelled" for item in events)
    completed_count = sum(item["status"] == "completed" for item in events)

    budget_totals: dict[str, dict[str, Decimal]] = {}
    estimates_by_currency: dict[str, dict[str, Decimal]] = {}
    for item in non_cancelled_events:
        plan = item["plan"]
        currency = plan["event"].get("currency", "INR")
        totals = budget_totals.setdefault(
            currency,
            {"planned_budget_total": Decimal("0"), "known_estimated_costs": Decimal("0")},
        )
        totals["planned_budget_total"] += Decimal(str(plan["budget_analysis"]["budget"]))
        totals["known_estimated_costs"] += Decimal(
            str(plan["budget_analysis"]["known_expenses_total"])
        )

    for item in active_events:
        plan = item["plan"]
        currency = plan["event"].get("currency", "INR")
        category_totals = estimates_by_currency.setdefault(currency, {})
        for category, amount in plan["budget_analysis"]["estimated_costs"].items():
            category_totals[category] = category_totals.get(category, Decimal("0")) + Decimal(str(amount))

    single_currency = (
        next(iter(budget_totals.values()))
        if len(budget_totals) == 1
        else (
            {"planned_budget_total": Decimal("0"), "known_estimated_costs": Decimal("0")}
            if not budget_totals
            else None
        )
    )
    single_currency_costs = (
        next(iter(estimates_by_currency.values())) if len(estimates_by_currency) == 1 else {}
    )
    risks: list[dict[str, Any]] = []
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    for item in active_events:
        for risk in item["plan"]["risks"]:
            risk_counts[risk["severity"]] += 1
            risks.append(
                {
                    "event_id": item["id"],
                    "event_name": item["plan"]["event"]["event_name"],
                    "risk": risk,
                }
            )
    risks.sort(
        key=lambda item: (
            SEVERITY_ORDER[item["risk"]["severity"]],
            item["event_name"].casefold(),
            item["risk"]["title"],
        )
    )

    pending_count = sum(item["status"] == "pending" for item in tasks)
    in_progress_count = sum(item["status"] == "in_progress" for item in tasks)
    completed_tasks = sum(item["status"] == "completed" for item in tasks)
    overdue_count = sum(item["overdue"] for item in tasks)
    blocked_count = sum(item["blocked"] for item in tasks)

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "events": events,
        "tasks": tasks,
        "risk_alerts": risks,
        "summary": {
            "total_events": len(events),
            "upcoming_events": len(upcoming_events),
            "completed_events": completed_count,
            "cancelled_events": cancelled_count,
            "planned_budget_total": (
                float(single_currency["planned_budget_total"]) if single_currency else None
            ),
            "known_estimated_costs": (
                float(single_currency["known_estimated_costs"]) if single_currency else None
            ),
            "remaining_known_estimate_budget": (
                float(
                    single_currency["planned_budget_total"]
                    - single_currency["known_estimated_costs"]
                )
                if single_currency
                else None
            ),
            "estimated_costs_by_category": {
                category: float(amount)
                for category, amount in sorted(single_currency_costs.items())
            },
            "budget_totals_by_currency": [
                {
                    "currency": currency,
                    **{key: float(value) for key, value in totals.items()},
                    "remaining_known_estimate_budget": float(
                        totals["planned_budget_total"] - totals["known_estimated_costs"]
                    ),
                }
                for currency, totals in sorted(budget_totals.items())
            ],
            "estimated_costs_by_currency": [
                {
                    "currency": currency,
                    "categories": {
                        category: float(amount)
                        for category, amount in sorted(category_totals.items())
                    },
                }
                for currency, category_totals in sorted(estimates_by_currency.items())
            ],
            "expenditure_tracking_available": True,
            "task_counts": {
                "pending": pending_count,
                "in_progress": in_progress_count,
                "overdue": overdue_count,
                "blocked": blocked_count,
                "completed": completed_tasks,
            },
            "risk_counts": risk_counts,
        },
        "capabilities": {
            "tasks": True,
            "event_status_updates": True,
            "approvals": False,
            "notifications": delivery["configured"],
            "calendar_integrations": False,
            "email_or_sms_delivery": delivery["configured"],
            "invitations_rsvp": True,
            "draft_only_invitation_mode": delivery["mode"] == "draft_only",
            "ai_model_configured": provider_configured(),
        },
    }
