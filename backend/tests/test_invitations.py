from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import invitations


client = TestClient(app)


def _event_payload(**overrides):
    payload = {
        "event_name": "RSVP Coordination Day",
        "event_type": "community",
        "event_date": (date.today() + timedelta(days=45)).isoformat(),
        "location": "Pune",
        "guest_count": 40,
        "budget": "50000.00",
        "currency": "INR",
        "estimated_costs": {"venue": "15000", "catering": "18000"},
        "requirements": [],
        "confirmed_vendors": [],
    }
    payload.update(overrides)
    return payload


def _event_id(**overrides) -> str:
    response = client.post("/api/v1/events", json=_event_payload(**overrides))
    assert response.status_code == 200, response.text
    return response.json()["event_id"]


def _guest(event_id: str, **overrides) -> dict:
    payload = {
        "name": "Asha Patel",
        "email": "asha@example.com",
        "group_name": "Friends",
        "party_size": 2,
    }
    payload.update(overrides)
    response = client.post(f"/api/v1/invitations/events/{event_id}/guests", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _draft(event_id: str, **overrides) -> dict:
    payload = {"tone": "friendly", "rsvp_deadline": (date.today() + timedelta(days=20)).isoformat()}
    payload.update(overrides)
    response = client.post(f"/api/v1/invitations/events/{event_id}/drafts/generate", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_guest_crud_persistence_validation_and_duplicate_resolution():
    event_id = _event_id()
    invalid = client.post(
        f"/api/v1/invitations/events/{event_id}/guests",
        json={"name": "No Contact", "email": "not-an-email"},
    )
    assert invalid.status_code == 422

    first = _guest(event_id, dietary_requirements=["Vegetarian"])
    second = _guest(event_id, name="Asha Duplicate", email="asha@example.com")
    duplicates = client.get(f"/api/v1/invitations/events/{event_id}/duplicates")
    assert duplicates.status_code == 200
    assert duplicates.json()[0]["match_reasons"] == ["email"]

    resolved = client.patch(
        f"/api/v1/invitations/events/{event_id}/guests/{second['id']}",
        json={"duplicate_of_id": first["id"]},
    )
    assert resolved.status_code == 200
    assert resolved.json()["duplicate_of_id"] == first["id"]

    edited = client.patch(
        f"/api/v1/invitations/events/{event_id}/guests/{first['id']}",
        json={"party_size": 3, "notes": "Use the accessible entrance"},
    )
    assert edited.status_code == 200
    assert edited.json()["party_size"] == 3

    overview = client.get(f"/api/v1/invitations/events/{event_id}")
    assert overview.status_code == 200
    assert overview.json()["summary"]["total_guests"] == 1
    assert len(overview.json()["rsvp_activity"]) >= 3

    removed = client.delete(f"/api/v1/invitations/events/{event_id}/guests/{second['id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/v1/invitations/events/{event_id}").json()["summary"]["total_guests"] == 1


def test_manual_rsvp_summary_history_and_autopilot_coordination_do_not_change_plan():
    event_id = _event_id(guest_count=50)
    guest = _guest(event_id, party_size=3)
    too_large = client.post(
        f"/api/v1/invitations/events/{event_id}/guests/{guest['id']}/rsvp",
        json={"rsvp_status": "attending", "party_size": 4, "source": "manual"},
    )
    assert too_large.status_code == 422

    rsvp = client.post(
        f"/api/v1/invitations/events/{event_id}/guests/{guest['id']}/rsvp",
        json={
            "rsvp_status": "attending",
            "party_size": 2,
            "dietary_requirements": ["Vegetarian"],
            "source": "manual",
        },
    )
    assert rsvp.status_code == 200
    assert rsvp.json()["rsvp_party_size"] == 2

    workflow = client.post(f"/api/v1/dashboard/events/{event_id}/workflow/generate")
    assert workflow.status_code == 201
    refreshed_workflow = client.get(f"/api/v1/dashboard/events/{event_id}/workflow")
    assert any(
        "confirmed in RSVP records" in item
        for task in refreshed_workflow.json()["tasks"]
        for item in task["information_needed"]
    )

    overview = client.get(f"/api/v1/invitations/events/{event_id}").json()
    assert overview["summary"]["rsvp_counts"]["attending"] == 1
    assert overview["summary"]["confirmed_party_size"] == 2
    assert overview["coordination"]["planned_guest_count"] == 50
    assert overview["coordination"]["automatic_changes"] == []
    dashboard = client.get("/api/v1/dashboard").json()
    saved = next(event for event in dashboard["events"] if event["id"] == event_id)
    assert saved["plan"]["event"]["guest_count"] == 50


def test_draft_generation_preview_and_draft_only_never_claim_external_delivery():
    event_id = _event_id()
    guest = _guest(event_id)
    draft = _draft(event_id)
    assert draft["generated_by"] == "deterministic"
    assert "An RSVP deadline is not supplied." not in draft["missing_information"]
    assert "event time" in " ".join(draft["missing_information"]).casefold()

    preview = client.post(
        f"/api/v1/invitations/events/{event_id}/delivery/preview",
        json={"draft_id": draft["id"], "guest_ids": [guest["id"]]},
    )
    assert preview.status_code == 200
    assert preview.json()["approved"] is False
    assert preview.json()["recipients"][0]["body"].startswith("Hi Asha Patel")

    needs_approval = client.post(
        f"/api/v1/invitations/events/{event_id}/delivery/send",
        json={"draft_id": draft["id"], "guest_ids": [guest["id"]]},
    )
    assert needs_approval.status_code == 422

    send = client.post(
        f"/api/v1/invitations/events/{event_id}/delivery/send",
        json={
            "draft_id": draft["id"],
            "guest_ids": [guest["id"]],
            "approved": True,
            "idempotency_key": str(uuid4()),
        },
    )
    assert send.status_code == 200, send.text
    assert send.json()["delivery_mode"] == "draft_only"
    assert send.json()["status"] == "draft_only"
    assert send.json()["attempts"] == []
    assert client.get(f"/api/v1/invitations/events/{event_id}").json()["delivery_attempts"] == []


def test_smtp_success_failure_retry_and_idempotency_are_recorded_with_mocked_provider(monkeypatch):
    event_id = _event_id()
    guest = _guest(event_id)
    draft = _draft(event_id)
    for key, value in {
        "PLANOVA_SMTP_HOST": "smtp.example.test",
        "PLANOVA_SMTP_USERNAME": "planova",
        "PLANOVA_SMTP_PASSWORD": "secret",
        "PLANOVA_SMTP_FROM": "host@example.test",
    }.items():
        monkeypatch.setenv(key, value)

    class SuccessProvider:
        def send(self, recipient, subject, body):
            assert recipient in {"asha@example.com", "ravi@example.com"}
            assert any(name in body for name in {"Asha Patel", "Ravi Rao"})
            return {"provider_message_id": "provider-1", "transport_message_id": "transport-1"}

    monkeypatch.setattr(invitations, "SMTPDeliveryProvider", SuccessProvider)
    idempotency_key = str(uuid4())
    payload = {
        "draft_id": draft["id"],
        "guest_ids": [guest["id"]],
        "approved": True,
        "idempotency_key": idempotency_key,
    }
    sent = client.post(f"/api/v1/invitations/events/{event_id}/delivery/send", json=payload)
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "completed"
    assert sent.json()["attempts"][0]["status"] == "sent"
    assert sent.json()["attempts"][0]["delivered_at"] is None
    duplicate = client.post(f"/api/v1/invitations/events/{event_id}/delivery/send", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == sent.json()["id"]

    second_guest = _guest(event_id, name="Ravi Rao", email="ravi@example.com")

    class FailingProvider:
        def send(self, recipient, subject, body):
            raise invitations.DeliveryProviderError("Mocked provider failure")

    monkeypatch.setattr(invitations, "SMTPDeliveryProvider", FailingProvider)
    failed = client.post(
        f"/api/v1/invitations/events/{event_id}/delivery/send",
        json={
            "draft_id": draft["id"],
            "guest_ids": [second_guest["id"]],
            "approved": True,
            "idempotency_key": str(uuid4()),
        },
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    failed_attempt = failed.json()["attempts"][0]

    monkeypatch.setattr(invitations, "SMTPDeliveryProvider", SuccessProvider)
    retried = client.post(
        f"/api/v1/invitations/events/{event_id}/delivery-attempts/{failed_attempt['id']}/retry",
        json={"approved": True, "idempotency_key": str(uuid4())},
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "completed"
    assert retried.json()["attempts"][0]["retry_of_id"] == failed_attempt["id"]


def test_reminders_only_target_pending_and_can_be_cancelled():
    event_id = _event_id()
    pending = _guest(event_id)
    replied = _guest(event_id, name="Ravi", email="ravi@example.com")
    assert client.post(
        f"/api/v1/invitations/events/{event_id}/guests/{replied['id']}/rsvp",
        json={"rsvp_status": "not_attending", "source": "manual"},
    ).status_code == 200

    invalid = client.post(
        f"/api/v1/invitations/events/{event_id}/reminders/prepare",
        json={"guest_ids": [replied["id"]]},
    )
    assert invalid.status_code == 409
    prepared = client.post(
        f"/api/v1/invitations/events/{event_id}/reminders/prepare",
        json={"guest_ids": [pending["id"]]},
    )
    assert prepared.status_code == 201, prepared.text
    assert prepared.json()["guest_ids"] == [pending["id"]]
    assert prepared.json()["draft"]["kind"] == "reminder"

    duplicate = client.post(
        f"/api/v1/invitations/events/{event_id}/reminders/prepare",
        json={"guest_ids": [pending["id"]]},
    )
    assert duplicate.status_code == 409
    cancelled = client.post(
        f"/api/v1/invitations/events/{event_id}/reminders/{prepared.json()['id']}/cancel"
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
