from datetime import date, timedelta
import sqlite3

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.repositories.dashboard_store import load_dashboard_records


client = TestClient(app)


def _event_payload(days_from_now: int = 45):
    return {
        "event_name": "Recovery Planning Forum",
        "event_type": "corporate",
        "event_date": (date.today() + timedelta(days=days_from_now)).isoformat(),
        "event_time": "09:30",
        "location": "Bengaluru",
        "guest_count": 80,
        "budget": "250000.00",
        "venue_name": "Cedar Hall",
        "venue_capacity": 100,
        "estimated_costs": {"venue": "50000.00", "catering": "75000.00"},
        "planned_expenses": ["venue", "catering", "equipment"],
        "requirements": ["Step-free access"],
        "requirement_status": {"Step-free access": "unverified"},
    }


def _create_event(days_from_now: int = 45) -> str:
    response = client.post("/api/v1/events", json=_event_payload(days_from_now))
    assert response.status_code == 200
    return response.json()["event_id"]


def test_autopilot_generates_persisted_dependency_graph_and_next_action():
    event_id = _create_event()
    url = f"/api/v1/dashboard/events/{event_id}/workflow"

    before = client.get(url)
    assert before.status_code == 200
    assert before.json()["tasks"] == []
    assert before.json()["ai_model_configured"] is False
    assert "No GenAI provider" in before.json()["notice"]

    generated = client.post(f"{url}/generate")
    assert generated.status_code == 201
    workflow = generated.json()
    assert len(workflow["tasks"]) == 8
    assert workflow["generated"] is True
    tasks = {task["title"]: task for task in workflow["tasks"]}
    date_task = tasks["Confirm event date and schedule"]
    guest_task = tasks["Confirm attendee estimate"]
    venue_task = tasks["Verify venue and capacity"]
    estimates_task = tasks["Review known costs and missing estimates"]
    assert guest_task["dependencies"] == [date_task["id"]]
    assert date_task["id"] in venue_task["dependencies"]
    assert estimates_task["id"] in tasks["Confirm catering plan"]["dependencies"]
    assert date_task["status"] == "pending"
    assert date_task["assigned_to"] is None
    assert tasks["Confirm catering plan"]["estimated_cost"] == 75000
    assert workflow["next_action"] == date_task["title"]
    assert workflow["blocked_count"] > 0
    assert any("equipment" in value for value in workflow["missing_information"])

    regenerated = client.post(f"{url}/generate")
    assert regenerated.status_code == 201
    assert len(regenerated.json()["tasks"]) == 8
    persisted = client.get(url).json()
    assert len(persisted["tasks"]) == 8
    assert set(task["id"] for task in persisted["tasks"]) == {
        task["id"] for task in workflow["tasks"]
    }


def test_workflow_detects_overdue_tasks_and_unblocks_dependents_on_completion():
    event_id = _create_event(days_from_now=10)
    url = f"/api/v1/dashboard/events/{event_id}/workflow"
    workflow = client.post(f"{url}/generate").json()
    date_task = next(
        task for task in workflow["tasks"]
        if task["title"] == "Confirm event date and schedule"
    )
    assert workflow["overdue_count"] >= 1
    assert date_task["overdue"] is True
    assert date_task["blocks"]
    dependent_attempt = client.patch(
        f"/api/v1/dashboard/tasks/{next(task for task in workflow['tasks'] if task['title'] == 'Confirm attendee estimate')['id']}",
        json={"status": "completed"},
    )
    assert dependent_attempt.status_code == 409

    completed = client.patch(
        f"/api/v1/dashboard/tasks/{date_task['id']}",
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    updated = client.get(url).json()
    guest_task = next(
        task for task in updated["tasks"]
        if task["title"] == "Confirm attendee estimate"
    )
    assert guest_task["blockers"] == []
    assert client.patch(
        f"/api/v1/dashboard/tasks/{guest_task['id']}",
        json={"status": "completed"},
    ).status_code == 200
    assert client.patch(
        f"/api/v1/dashboard/tasks/{date_task['id']}",
        json={"status": "pending"},
    ).status_code == 409


def test_recovery_case_compares_known_budget_change_and_requires_approval():
    event_id = _create_event()
    response = client.post(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases",
        json={
            "disruption_type": "budget_change",
            "description": "The approved budget was reduced by the organizer.",
            "changes": {"budget": 100000},
        },
    )
    assert response.status_code == 201
    case = response.json()
    assert case["source"] == "user_report"
    assert case["impact"]["known_budget_inr"] == 250000
    assert case["impact"]["scenario_comparison"]["budget_impact"]["scenario_budget"] == 100000
    adjusted = next(
        option for option in case["options"]
        if option["id"] == "apply_supplied_changes"
    )
    assert adjusted["cost_change"] == 0
    assert "unknown costs are excluded" in adjusted["cost_basis"]
    assert adjusted["readiness"] == "ready_for_review"

    proposal_response = client.post(
        f"/api/v1/dashboard/recovery-cases/{case['id']}/proposals",
        json={"option_id": adjusted["id"]},
    )
    assert proposal_response.status_code == 201
    case = proposal_response.json()
    proposal = case["proposals"][0]
    assert proposal["status"] == "proposed"
    assert client.post(
        f"/api/v1/dashboard/recovery-cases/{case['id']}/proposals",
        json={"option_id": adjusted["id"]},
    ).status_code == 409
    assert client.post(
        f"/api/v1/dashboard/recovery-proposals/{proposal['id']}/approve"
    ).status_code == 200

    applied = client.get(f"/api/v1/dashboard").json()
    saved_plan = next(item["plan"] for item in applied["events"] if item["id"] == event_id)
    assert float(saved_plan["event"]["budget"]) == 100000
    assert saved_plan["budget_analysis"]["over_budget"] is True
    assert saved_plan["budget_analysis"]["overrun_amount"] == 25000
    assert saved_plan["budget_analysis"]["remaining_budget"] == -25000
    repeated = client.post(
        f"/api/v1/dashboard/recovery-proposals/{proposal['id']}/approve"
    )
    assert repeated.status_code == 409
    assert "already applied" in repeated.json()["detail"]
    assert client.post(
        f"/api/v1/dashboard/recovery-cases/{case['id']}/proposals",
        json={"option_id": adjusted["id"]},
    ).status_code == 409


def test_approved_date_change_recalculates_autopilot_deadlines():
    event_id = _create_event()
    workflow_url = f"/api/v1/dashboard/events/{event_id}/workflow"
    initial = client.post(f"{workflow_url}/generate").json()
    case = client.post(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases",
        json={
            "disruption_type": "date_change",
            "description": "The event owner supplied a revised event date.",
            "changes": {
                "event_date": (date.today() + timedelta(days=60)).isoformat(),
                "estimated_costs": {"catering": 80000},
            },
        },
    ).json()
    proposal_case = client.post(
        f"/api/v1/dashboard/recovery-cases/{case['id']}/proposals",
        json={"option_id": "apply_supplied_changes"},
    ).json()
    proposal = proposal_case["proposals"][0]
    approved = client.post(
        f"/api/v1/dashboard/recovery-proposals/{proposal['id']}/approve"
    )
    assert approved.status_code == 200
    updated = client.get(workflow_url).json()
    new_date = date.today() + timedelta(days=60)
    generated_task = next(
        task for task in updated["tasks"]
        if task["title"] == "Confirm event date and schedule"
    )
    assert generated_task["due_date"] == (new_date - timedelta(days=30)).isoformat()
    original_task = next(
        task for task in initial["tasks"]
        if task["title"] == "Confirm event date and schedule"
    )
    assert generated_task["due_date"] != original_task["due_date"]
    catering_task = next(
        task for task in updated["tasks"]
        if task["title"] == "Confirm catering plan"
    )
    assert catering_task["estimated_cost"] == 80000


def test_venue_cancellation_options_are_unverified_and_costs_stay_unknown():
    event_id = _create_event()
    client.post(f"/api/v1/dashboard/events/{event_id}/workflow/generate")
    response = client.post(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases",
        json={
            "disruption_type": "venue_cancellation",
            "description": "The venue operator reported a cancellation by phone.",
        },
    )
    assert response.status_code == 201
    case = response.json()
    assert case["impact"]["user_reported_facts"] == [
        "The venue operator reported a cancellation by phone."
    ]
    assert case["impact"]["confirmed_facts"] == []
    assert len(case["options"]) == 2
    for option in case["options"]:
        assert option["readiness"] == "requires_verification"
        assert option["cost_change"] is None
        assert any("availability" in item for item in option["uncertainties"])
    assert "Verify venue and capacity" in case["impact"]["affected_tasks"]

    persisted = client.get(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases"
    )
    assert persisted.status_code == 200
    assert persisted.json()[0]["id"] == case["id"]


def test_recovery_validation_rejection_and_duplicate_execution_are_safe():
    event_id = _create_event()
    assert client.post(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases",
        json={
            "disruption_type": "budget_change",
            "description": "Invalid negative budget",
            "changes": {"budget": -1},
        },
    ).status_code == 422
    case = client.post(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases",
        json={
            "disruption_type": "vendor_cancellation",
            "description": "A supplier reported cancellation.",
        },
    ).json()
    assert client.post(
        f"/api/v1/dashboard/recovery-cases/{case['id']}/proposals",
        json={"option_id": "not-an-option"},
    ).status_code == 422
    proposal_case = client.post(
        f"/api/v1/dashboard/recovery-cases/{case['id']}/proposals",
        json={"option_id": "verify_current_commitments"},
    ).json()
    proposal = proposal_case["proposals"][0]
    rejected = client.post(
        f"/api/v1/dashboard/recovery-proposals/{proposal['id']}/reject"
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["result"] is None
    assert client.post(
        f"/api/v1/dashboard/recovery-proposals/{proposal['id']}/approve"
    ).status_code == 409
    re_proposed = client.post(
        f"/api/v1/dashboard/recovery-cases/{case['id']}/proposals",
        json={"option_id": "verify_current_commitments"},
    )
    assert re_proposed.status_code == 201
    assert re_proposed.json()["proposals"][-1]["status"] == "proposed"
    dashboard = client.get("/api/v1/dashboard").json()
    event = next(item for item in dashboard["events"] if item["id"] == event_id)
    assert float(event["plan"]["event"]["budget"]) == 250000


def test_guest_count_recovery_uses_capacity_risk_without_applying_unapproved_change():
    event_id = _create_event()
    case = client.post(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases",
        json={
            "disruption_type": "guest_count_change",
            "description": "The organizer increased the expected attendance.",
            "changes": {"guest_count": 110},
        },
    ).json()
    comparison = case["impact"]["scenario_comparison"]
    assert comparison["capacity_impact"]["scenario_status"] == "exceeds_capacity"
    assert any(
        risk["type"] == "venue_capacity"
        for risk in comparison["risk_changes"]["newly_introduced"]
    )
    dashboard = client.get("/api/v1/dashboard").json()
    event = next(item for item in dashboard["events"] if item["id"] == event_id)
    assert event["plan"]["event"]["guest_count"] == 80


def test_recovery_budget_overrun_reports_partial_basis_and_scenario_percent():
    payload = _event_payload()
    payload["budget"] = "100000"
    created = client.post("/api/v1/events", json=payload)
    assert created.status_code == 200
    event_id = created.json()["event_id"]

    response = client.post(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases",
        json={
            "disruption_type": "budget_change",
            "description": "The coordinator confirmed a lower spending limit.",
            "changes": {
                "budget": 100000,
                "estimated_costs": {"catering": 80000},
            },
        },
    )

    assert response.status_code == 201
    impact = response.json()["impact"]
    assert impact["estimated_overrun_inr"] == 25000
    assert impact["estimated_overrun_percent"] == 25
    assert impact["overrun_categories"] == ["catering", "venue"]
    assert impact["overrun_breakdown_inr"] == {"catering": 75000, "venue": 50000}
    assert impact["budget_assessment"] == "partial"
    assert "equipment" in impact["missing_cost_categories"]
    assert impact["scenario_estimated_overrun_inr"] == 30000
    assert impact["scenario_budget_inr"] == 100000
    option = response.json()["options"][0]
    assert option["projected_known_cost_inr"] == 130000
    assert option["projected_overrun_inr"] == 30000


def test_recovery_case_resolution_requires_decisions_and_records_remaining_blockers():
    event_id = _create_event()
    case = client.post(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases",
        json={
            "disruption_type": "venue_cancellation",
            "description": "The organizer reported venue cancellation.",
        },
    ).json()
    pending = client.post(
        f"/api/v1/dashboard/recovery-cases/{case['id']}/proposals",
        json={"option_id": "verify_current_commitments"},
    ).json()["proposals"][0]
    resolve_url = f"/api/v1/dashboard/recovery-cases/{case['id']}/resolve"
    assert client.post(resolve_url, json={"summary": "Reviewed"}).status_code == 409

    rejected = client.post(
        f"/api/v1/dashboard/recovery-proposals/{pending['id']}/reject"
    )
    assert rejected.status_code == 200
    resolved = client.post(
        resolve_url,
        json={"summary": "Venue cancellation verified; replacement is still being sourced."},
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None
    assert "replacement is still being sourced" in body["resolution"]
    assert body["activity"][-1]["action"] == "case_resolved"
    persisted = client.get(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases"
    ).json()[0]
    assert persisted["status"] == "resolved"
    assert client.post(resolve_url, json={"summary": "Resolve again"}).status_code == 409
    assert client.post(
        f"/api/v1/dashboard/recovery-cases/{case['id']}/proposals",
        json={"option_id": "verify_current_commitments"},
    ).status_code == 409


def test_recovery_endpoints_validate_missing_event_and_case_records():
    missing = "00000000-0000-0000-0000-000000000001"
    assert client.get(
        f"/api/v1/dashboard/events/{missing}/workflow"
    ).status_code == 404
    assert client.post(
        f"/api/v1/dashboard/events/{missing}/recovery-cases",
        json={
            "disruption_type": "other",
            "description": "No associated saved event.",
        },
    ).status_code == 404
    assert client.get(
        f"/api/v1/dashboard/events/{missing}/recovery-cases"
    ).status_code == 404
    assert client.post(
        f"/api/v1/dashboard/recovery-cases/{missing}/proposals",
        json={"option_id": "verify_current_commitments"},
    ).status_code == 404
    assert client.get(
        "/api/v1/dashboard/events/not-a-uuid/workflow"
    ).status_code == 422


def test_delayed_task_recovery_rejects_tasks_from_another_event():
    event_id = _create_event()
    other_event_id = _create_event()
    task = client.post(
        "/api/v1/dashboard/tasks",
        json={"title": "Confirm another event", "event_id": other_event_id},
    ).json()
    response = client.post(
        f"/api/v1/dashboard/events/{event_id}/recovery-cases",
        json={
            "disruption_type": "delayed_task",
            "description": "A task has slipped.",
            "task_id": task["id"],
        },
    )
    assert response.status_code == 422


def test_existing_task_database_is_migrated_without_losing_records(tmp_path, monkeypatch):
    database = tmp_path / "legacy-planova.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE events (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                plan_json TEXT NOT NULL
            );
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT,
                status TEXT NOT NULL CHECK (status IN ('pending', 'completed')),
                event_id TEXT REFERENCES events(id)
            );
            """
        )
        connection.execute(
            "INSERT INTO tasks (id, created_at, title, due_date, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "legacy-task-id",
                "2026-01-01T00:00:00+00:00",
                "Preserve existing task",
                None,
                "pending",
            ),
        )
    monkeypatch.setenv("PLANOVA_DB_PATH", str(database))

    loaded = load_dashboard_records()

    assert loaded["tasks"][0]["title"] == "Preserve existing task"
    assert loaded["tasks"][0]["description"] == ""
    assert loaded["tasks"][0]["dependencies"] == []
    assert loaded["tasks"][0]["generated"] is False
    created = client.post(
        "/api/v1/dashboard/tasks", json={"title": "Use migrated task status"}
    )
    assert created.status_code == 201
    progress = client.patch(
        f"/api/v1/dashboard/tasks/{created.json()['id']}",
        json={"status": "in_progress"},
    )
    assert progress.status_code == 200
    assert progress.json()["status"] == "in_progress"
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
    assert {"priority", "dependencies_json", "autopilot_key"} <= columns
