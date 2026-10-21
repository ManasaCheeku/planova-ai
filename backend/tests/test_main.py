from fastapi.testclient import TestClient
from datetime import date, timedelta

from backend.app.main import app


client = TestClient(app)


def _event_payload():
    return {
        "event_name": "Dashboard Summit",
        "event_type": "corporate",
        "event_date": (date.today() + timedelta(days=30)).isoformat(),
        "event_time": "09:30",
        "location": "Bengaluru",
        "guest_count": 80,
        "budget": "250000.00",
        "estimated_costs": {"venue": "50000.00", "catering": "75000.00"},
    }


def test_root_identifies_planova_ai():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "app": "Planova AI",
        "message": "Every detail aligned. Every moment extraordinary.",
        "status": "running",
    }


def test_health_reports_healthy_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_dashboard_persists_event_task_and_user_managed_statuses():
    created = client.post("/api/v1/events", json=_event_payload())
    assert created.status_code == 200
    event_id = created.json()["event_id"]
    assert event_id

    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["summary"]["total_events"] == 1
    assert dashboard["summary"]["upcoming_events"] == 1
    assert dashboard["summary"]["completed_events"] == 0
    assert dashboard["summary"]["cancelled_events"] == 0
    assert dashboard["summary"]["planned_budget_total"] == 250000
    assert dashboard["summary"]["known_estimated_costs"] == 125000
    assert dashboard["summary"]["remaining_known_estimate_budget"] == 125000
    assert dashboard["summary"]["expenditure_tracking_available"] is True
    event = dashboard["events"][0]
    assert event["plan"]["event"]["event_time"] == "09:30:00"
    assert event["status"] == "scheduled"

    overdue_task = client.post(
        "/api/v1/dashboard/tasks",
        json={
            "title": "Confirm venue access",
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "event_id": event_id,
        },
    )
    assert overdue_task.status_code == 201
    task_id = overdue_task.json()["id"]
    dashboard = client.get("/api/v1/dashboard").json()
    assert dashboard["summary"]["task_counts"] == {
        "pending": 1,
        "in_progress": 0,
        "overdue": 1,
        "blocked": 0,
        "completed": 0,
    }
    assert dashboard["tasks"][0]["title"] == "Confirm venue access"

    completed_task = client.patch(
        f"/api/v1/dashboard/tasks/{task_id}",
        json={"status": "completed"},
    )
    assert completed_task.status_code == 200
    assert completed_task.json()["status"] == "completed"

    updated_event = client.patch(
        f"/api/v1/dashboard/events/{event_id}",
        json={"status": "completed"},
    )
    assert updated_event.status_code == 200
    assert updated_event.json()["summary"]["completed_events"] == 1
    assert updated_event.json()["summary"]["upcoming_events"] == 0
    assert updated_event.json()["summary"]["planned_budget_total"] == 250000

    cancelled_event = client.patch(
        f"/api/v1/dashboard/events/{event_id}",
        json={"status": "cancelled"},
    )
    assert cancelled_event.status_code == 200
    assert cancelled_event.json()["summary"]["cancelled_events"] == 1
    assert cancelled_event.json()["summary"]["planned_budget_total"] == 0


def test_dashboard_exposes_unsupported_workflows_as_unavailable():
    response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    capabilities = response.json()["capabilities"]
    assert capabilities["approvals"] is False
    assert capabilities["notifications"] is False
    assert capabilities["calendar_integrations"] is False
    assert capabilities["ai_model_configured"] is False


def test_deterministic_command_asks_for_missing_essentials_without_saving():
    response = client.post(
        "/api/v1/dashboard/command",
        json={"message": "Plan a birthday party for 80 guests tomorrow at 6 pm"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "deterministic_fallback"
    assert result["ai_model_configured"] is False
    assert result["status"] == "needs_input"
    assert set(result["missing_information"]) == {"event_name", "location", "budget"}
    assert result["extracted"]["guest_count"] == 80
    assert result["extracted"]["event_time"] == "18:00"
    assert result["plan"] is None
    assert client.get("/api/v1/dashboard").json()["summary"]["total_events"] == 0


def test_deterministic_command_proposes_validated_plan_but_does_not_persist():
    response = client.post(
        "/api/v1/dashboard/command",
        json={
            "message": (
                f"Plan a corporate event named Product Launch for 120 guests "
                f"in Bengaluru on {(date.today() + timedelta(days=30)).isoformat()} "
                "at 09:30 with budget INR 250000"
            )
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "draft_ready"
    assert result["ai_model_configured"] is False
    assert result["draft"]["event_name"] == "Product Launch"
    assert result["draft"]["event_time"] == "09:30:00"
    assert result["draft"]["budget"] == "250000"
    assert result["plan"]["budget_analysis"]["currency"] == "INR"
    assert "no event was saved" in result["notice"]
    assert client.get("/api/v1/dashboard").json()["summary"]["total_events"] == 0


def test_deterministic_command_reports_external_actions_without_executing_them():
    response = client.post(
        "/api/v1/dashboard/command",
        json={
            "message": (
                f"Book a venue for a birthday named Private Dinner in Pune for 20 guests "
                f"on {(date.today() + timedelta(days=45)).isoformat()} with budget INR 50000"
            )
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "draft_ready"
    assert result["unsupported_actions"] == ["booking"]
    assert "no event was saved" in result["notice"]
    assert client.get("/api/v1/dashboard").json()["summary"]["total_events"] == 0


def test_dashboard_task_and_event_updates_validate_unknown_records():
    assert client.patch(
        "/api/v1/dashboard/tasks/00000000-0000-0000-0000-000000000000",
        json={"status": "completed"},
    ).status_code == 404
    assert client.patch(
        "/api/v1/dashboard/events/not-found", json={"status": "cancelled"}
    ).status_code == 404
    assert client.post(
        "/api/v1/dashboard/tasks",
        json={
            "title": "Link missing event",
            "event_id": "00000000-0000-0000-0000-000000000000",
        },
    ).status_code == 404


def test_team_task_assignment_status_dependencies_and_filters():
    event_id = client.post("/api/v1/events", json=_event_payload()).json()["event_id"]
    first = client.post(
        "/api/v1/dashboard/tasks",
        json={
            "title": "Confirm accessibility",
            "event_id": event_id,
            "assigned_to": "Asha",
            "priority": "high",
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "completion_criteria": "Venue confirms step-free access.",
        },
    )
    assert first.status_code == 201
    first_task = first.json()
    second = client.post(
        "/api/v1/dashboard/tasks",
        json={
            "title": "Publish venue plan",
            "event_id": event_id,
            "assigned_to": "Asha",
            "dependencies": [first_task["id"]],
        },
    )
    assert second.status_code == 201
    second_task = second.json()

    dashboard = client.get("/api/v1/dashboard").json()
    assert dashboard["summary"]["task_counts"] == {
        "pending": 2,
        "in_progress": 0,
        "overdue": 1,
        "blocked": 1,
        "completed": 0,
    }
    assert next(task for task in dashboard["tasks"] if task["id"] == second_task["id"])[
        "blockers"
    ] == ["Confirm accessibility"]
    filtered = client.get(
        f"/api/v1/dashboard/tasks?event_id={event_id}&assigned_to=asha&status=blocked&priority=medium"
    )
    assert filtered.status_code == 200
    assert [task["id"] for task in filtered.json()] == [second_task["id"]]

    started = client.patch(
        f"/api/v1/dashboard/tasks/{first_task['id']}",
        json={"status": "in_progress"},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"
    assert client.patch(
        f"/api/v1/dashboard/tasks/{second_task['id']}",
        json={"status": "in_progress"},
    ).status_code == 409

    changed = client.patch(
        f"/api/v1/dashboard/tasks/{first_task['id']}",
        json={"assigned_to": None, "due_date": None, "description": "Access confirmed."},
    )
    assert changed.status_code == 200
    assert changed.json()["assigned_to"] is None
    assert changed.json()["due_date"] is None
    assert changed.json()["description"] == "Access confirmed."
    assert client.patch(
        f"/api/v1/dashboard/tasks/{first_task['id']}",
        json={"status": "completed"},
    ).status_code == 200
    assert client.patch(
        f"/api/v1/dashboard/tasks/{second_task['id']}",
        json={"status": "completed"},
    ).status_code == 200
    assert client.patch(
        f"/api/v1/dashboard/tasks/{first_task['id']}",
        json={"status": "pending"},
    ).status_code == 409

    persisted = client.get("/api/v1/dashboard").json()["tasks"]
    assert {task["status"] for task in persisted} == {"completed"}


def test_task_dependencies_reject_cross_event_cycles_and_duplicate_ids():
    first_event = client.post("/api/v1/events", json=_event_payload()).json()["event_id"]
    second_event = client.post(
        "/api/v1/events",
        json={**_event_payload(), "event_name": "Second Coordination Event"},
    ).json()["event_id"]
    first = client.post(
        "/api/v1/dashboard/tasks", json={"title": "First", "event_id": first_event}
    ).json()
    second = client.post(
        "/api/v1/dashboard/tasks",
        json={
            "title": "Second",
            "event_id": first_event,
            "dependencies": [first["id"]],
        },
    ).json()
    cross_event = client.post(
        "/api/v1/dashboard/tasks",
        json={
            "title": "Cross-event dependency",
            "event_id": second_event,
            "dependencies": [first["id"]],
        },
    )
    assert cross_event.status_code == 422
    duplicate = client.post(
        "/api/v1/dashboard/tasks",
        json={
            "title": "Duplicate dependency",
            "event_id": first_event,
            "dependencies": [first["id"], first["id"]],
        },
    )
    assert duplicate.status_code == 422
    cycle = client.patch(
        f"/api/v1/dashboard/tasks/{first['id']}",
        json={"dependencies": [second["id"]]},
    )
    assert cycle.status_code == 409
    self_dependency = client.patch(
        f"/api/v1/dashboard/tasks/{first['id']}",
        json={"dependencies": [first["id"]]},
    )
    assert self_dependency.status_code == 409


def test_task_assignment_validation_and_persistence():
    event_id = client.post("/api/v1/events", json=_event_payload()).json()["event_id"]
    invalid = client.post(
        "/api/v1/dashboard/tasks",
        json={"title": "Invalid priority", "event_id": event_id, "priority": "urgent"},
    )
    assert invalid.status_code == 422
    created = client.post(
        "/api/v1/dashboard/tasks",
        json={
            "title": "Coordinate volunteers",
            "event_id": event_id,
            "assigned_to": "Meera",
            "priority": "medium",
        },
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert client.get(f"/api/v1/dashboard/tasks?assigned_to=MEERA").json()[0]["id"] == task_id
    assert client.patch(
        f"/api/v1/dashboard/tasks/{task_id}", json={"assigned_to": ""}
    ).status_code == 200
    assert client.get("/api/v1/dashboard").json()["tasks"][0]["assigned_to"] is None
