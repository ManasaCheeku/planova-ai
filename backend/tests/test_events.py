from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def _event_payload(**overrides):
    payload = {
        "event_name": "Product Launch",
        "event_type": "corporate",
        "event_date": (date.today() + timedelta(days=90)).isoformat(),
        "location": "Bengaluru, India",
        "guest_count": 100,
        "budget": "10000.00",
        "currency": "INR",
        "requirements": ["Accessible venue", "Vegetarian catering"],
        "requirement_status": {
            "Accessible venue": "satisfied",
            "Vegetarian catering": "satisfied",
        },
        "constraints": ["Indoor venue"],
        "constraint_status": {"Indoor venue": "satisfied"},
        "venue_name": "Cedar Hall",
        "venue_capacity": 120,
        "estimated_costs": {
            "venue": "3000.00",
            "catering": "4000.00",
            "production": "1000.00",
            "staffing": "500.00",
            "contingency": "500.00",
        },
        "confirmed_vendors": ["Sample Catering Co."],
    }
    payload.update(overrides)
    return payload


def test_create_event_returns_structured_plan_and_budget_totals():
    response = client.post("/api/v1/events", json=_event_payload())

    assert response.status_code == 200
    plan = response.json()
    budget = plan["budget_analysis"]
    assert plan["event"]["event_name"] == "Product Launch"
    assert plan["event"]["currency"] == "INR"
    assert "Score starts at 100" in plan["readiness"]["basis"]
    assert budget["currency"] == "INR"
    assert budget["allocation_total"] == budget["budget"] == 10000
    assert budget["estimated_total"] == budget["known_expenses_total"] == 9000
    assert budget["remaining_budget"] == 1000
    assert budget["status"] == "within_budget"
    assert budget["over_budget"] is False
    assert budget["missing_cost_categories"] == []
    assert budget["contingency_recommendation"]["amount"] == 850
    assert budget["contingency_recommendation"]["included_in_known_costs"] is False


def test_missing_costs_are_explicit_and_budget_allocations_stay_in_budget():
    response = client.post(
        "/api/v1/events",
        json=_event_payload(
            estimated_costs={
                "venue": "0.00",
                "catering": "0.00",
                "production": "0.00",
                "staffing": "0.00",
                "equipment": "0.00",
                "activities": "0.00",
                "contingency": "0.00",
            }
        ),
    )

    assert response.status_code == 200
    budget = response.json()["budget_analysis"]
    assert budget["estimated_total"] == 0
    assert budget["known_expenses_total"] == 0
    assert budget["status"] == "within_budget"
    assert budget["missing_cost_categories"] == []

    legacy_missing_response = client.post(
        "/api/v1/events",
        json=_event_payload(estimated_costs={"venue": "0.00"}),
    )
    assert legacy_missing_response.status_code == 200
    legacy_budget = legacy_missing_response.json()["budget_analysis"]
    assert legacy_budget["allocation_total"] == legacy_budget["budget"]
    assert legacy_budget["missing_cost_categories"] == [
        "catering",
        "contingency",
        "production",
        "staffing",
    ]

    missing_response = client.post(
        "/api/v1/events",
        json=_event_payload(
            estimated_costs={"venue": "0.00"},
            planned_expenses=["equipment", "activities"],
        ),
    )
    missing_budget = missing_response.json()["budget_analysis"]
    assert missing_budget["estimated_total"] == 0
    assert missing_budget["status"] == "incomplete"
    assert "catering" in missing_budget["missing_cost_categories"]
    assert "equipment" in missing_budget["missing_cost_categories"]
    assert "activities" in missing_budget["missing_cost_categories"]
    assert any(
        risk["evidence"] == {"expense_category": "catering", "estimate": "not supplied"}
        for risk in missing_response.json()["risks"]
    )


def test_empty_estimates_are_unknown_not_zero_and_remaining_is_basis_labelled():
    response = client.post(
        "/api/v1/events",
        json=_event_payload(estimated_costs={}),
    )

    assert response.status_code == 200
    budget = response.json()["budget_analysis"]
    assert budget["estimated_total"] is None
    assert budget["known_expenses_total"] == 0
    assert budget["remaining_budget"] == 10000
    assert "unestimated categories are excluded" in budget["remaining_budget_basis"]
    assert budget["contingency_recommendation"]["amount"] is None


def test_equipment_activity_and_contingency_are_counted_once():
    response = client.post(
        "/api/v1/events",
        json=_event_payload(
            estimated_costs={
                "equipment": "1250.25",
                "activities": "750.25",
                "contingency": "200.00",
            }
        ),
    )

    budget = response.json()["budget_analysis"]
    assert budget["known_expenses_total"] == 2200.5
    assert budget["estimated_costs"]["equipment"] == 1250.25
    assert budget["estimated_costs"]["activities"] == 750.25
    assert budget["contingency_recommendation"]["amount"] == 200.05
    assert budget["contingency_recommendation"]["included_in_known_costs"] is False


def test_cost_overrun_is_flagged_and_creates_high_risk():
    response = client.post(
        "/api/v1/events",
        json=_event_payload(
            estimated_costs={"venue": "12000.00", "catering": "1000.00"}
        ),
    )

    assert response.status_code == 200
    plan = response.json()
    budget = plan["budget_analysis"]
    assert budget["status"] == "over_budget"
    assert budget["over_budget"] is True
    assert budget["known_expenses_total"] == 13000
    assert budget["remaining_budget"] == -3000
    assert budget["overrun_amount"] == 3000
    assert budget["overrun_categories"] == ["catering", "venue"]
    assert budget["overrun_breakdown"] == {"catering": 1000, "venue": 12000}
    risk = next(risk for risk in plan["risks"] if risk["type"] == "insufficient_budget")
    assert risk["severity"] == "high"
    assert risk["title"]
    assert risk["reason"]
    assert risk["evidence"]["overrun_inr"] == 3000
    assert risk["evidence"]["expense_estimates_inr"] == {
        "catering": 1000,
        "venue": 12000,
    }
    assert risk["mitigation"]


def test_venue_capacity_risk_is_reported():
    boundary = client.post(
        "/api/v1/events",
        json=_event_payload(guest_count=120, venue_capacity=120),
    ).json()
    assert not any(risk["type"] == "venue_capacity" for risk in boundary["risks"])

    over = client.post(
        "/api/v1/events",
        json=_event_payload(guest_count=121, venue_capacity=120),
    ).json()
    capacity_risk = next(
        risk for risk in over["risks"] if risk["type"] == "venue_capacity"
    )
    assert capacity_risk["severity"] == "high"
    assert capacity_risk["evidence"]["guest_count"] == 121
    assert capacity_risk["evidence"]["venue_capacity"] == 120
    assert capacity_risk["reason"]
    assert capacity_risk["mitigation"]


def test_unknown_capacity_and_missing_core_information_are_explicit():
    response = client.post(
        "/api/v1/events",
        json=_event_payload(
            event_type=None,
            event_date=None,
            location=None,
            guest_count=None,
            venue_capacity=None,
        ),
    )

    assert response.status_code == 200
    risks = response.json()["risks"]
    risk_types = {risk["type"] for risk in risks}
    assert "attendee_count_missing" in risk_types
    assert "venue_capacity_unverified" in risk_types
    assert "event_type_missing" in risk_types
    assert "event_date_missing" in risk_types
    assert "location_missing" in risk_types
    assert all(risk["evidence"] and risk["reason"] and risk["mitigation"] for risk in risks)


def test_unsatisfied_and_unverified_requirements_and_constraints_are_flagged():
    response = client.post(
        "/api/v1/events",
        json=_event_payload(
            requirement_status={
                "Accessible venue": "unsatisfied",
                "Vegetarian catering": "unverified",
            },
            constraint_status={"Indoor venue": "unsatisfied"},
        ),
    )

    assert response.status_code == 200
    risks = response.json()["risks"]
    assert any(
        risk["type"] == "requirement_unsatisfied"
        and risk["evidence"]["requirement"] == "Accessible venue"
        and risk["severity"] == "high"
        for risk in risks
    )
    assert any(
        risk["type"] == "requirement_unverified"
        and risk["evidence"]["requirement"] == "Vegetarian catering"
        for risk in risks
    )
    assert any(
        risk["type"] == "constraint_unsatisfied"
        and risk["evidence"]["constraint"] == "Indoor venue"
        for risk in risks
    )


def test_missing_requirements_and_unconfirmed_vendors_are_reported():
    response = client.post(
        "/api/v1/events",
        json=_event_payload(
            requirements=[],
            requirement_status={},
            constraints=[],
            constraint_status={},
            confirmed_vendors=[],
            unconfirmed_vendors=["Lighting vendor"],
        ),
    )

    assert response.status_code == 200
    risks = response.json()["risks"]
    risk_types = {risk["type"] for risk in risks}
    assert "missing_requirements" in risk_types
    assert "vendor_unconfirmed" in risk_types
    vendor_risk = next(risk for risk in risks if risk["type"] == "vendor_unconfirmed")
    assert vendor_risk["evidence"]["vendor"] == "Lighting vendor"


def test_scenario_analysis_reports_budget_capacity_and_readiness_impacts():
    response = client.post(
        "/api/v1/events/scenario-analysis",
        json={
            "event": _event_payload(estimated_costs={"venue": "3000.00"}),
            "changes": {
                "guest_count": 150,
                "budget": "8000.00",
                "event_date": (date.today() + timedelta(days=7)).isoformat(),
                "estimated_costs": {"catering": "4000.00", "equipment": "500.00"},
            },
        },
    )

    assert response.status_code == 200
    result = response.json()
    impact = result["budget_impact"]
    assert impact["original_budget"] == 10000
    assert impact["scenario_budget"] == 8000
    assert impact["budget_change"] == -2000
    assert impact["original_known_expenses_total"] == 3000
    assert impact["scenario_known_expenses_total"] == 7500
    assert impact["known_expenses_change"] == 4500
    assert impact["scenario_remaining_budget"] == 500
    assert result["capacity_impact"]["original_status"] == "within_capacity"
    assert result["capacity_impact"]["scenario_status"] == "exceeds_capacity"
    assert result["readiness_impact"]["scenario_status"] == "at_risk"
    assert any(
        risk["id"] == "venue_capacity_exceeded"
        for risk in result["risk_changes"]["newly_introduced"]
    )
    assert any(
        risk["id"] ==         "expense_estimate_missing:production"
        for risk in result["risk_changes"]["remaining"]
    )
    assert any("exceed" in item for item in result["recommendations"])
    assert any("budget decreases" in item for item in result["recommendations"])
    assert any("estimates increase" in item for item in result["recommendations"])


def test_scenario_filling_missing_expense_resolves_only_that_risk():
    response = client.post(
        "/api/v1/events/scenario-analysis",
        json={
            "event": _event_payload(estimated_costs={"venue": "1000.00"}),
            "changes": {"estimated_costs": {"catering": "0.00"}},
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["budget_impact"]["known_expenses_change"] == 0
    resolved_ids = {risk["id"] for risk in result["risk_changes"]["resolved"]}
    remaining_ids = {risk["id"] for risk in result["risk_changes"]["remaining"]}
    assert "expense_estimate_missing:catering" in resolved_ids
    assert "expense_estimate_missing:production" in remaining_ids
    assert result["scenario_plan"]["budget_analysis"]["estimated_costs"]["venue"] == 1000
    assert result["scenario_plan"]["budget_analysis"]["estimated_costs"]["catering"] == 0


def test_scenario_keeps_persistent_risks_and_reports_resolved_budget_overrun():
    response = client.post(
        "/api/v1/events/scenario-analysis",
        json={
            "event": _event_payload(
                estimated_costs={"venue": "12000.00"},
                guest_count=130,
            ),
            "changes": {
                "estimated_costs": {"venue": "9000.00"},
                "guest_count": 110,
            },
        },
    )

    assert response.status_code == 200
    result = response.json()
    introduced = {risk["id"] for risk in result["risk_changes"]["newly_introduced"]}
    resolved = {risk["id"] for risk in result["risk_changes"]["resolved"]}
    remaining = {risk["id"] for risk in result["risk_changes"]["remaining"]}
    assert "venue_capacity_exceeded" in resolved
    assert "budget_overrun" in resolved
    assert not introduced
    assert "expense_estimate_missing:catering" in remaining


def test_invalid_event_values_return_useful_validation_errors():
    invalid_payloads = [
        _event_payload(guest_count=0),
        _event_payload(budget="-1.00"),
        _event_payload(event_date="not-a-date"),
        _event_payload(event_date=(date.today() - timedelta(days=1)).isoformat()),
        _event_payload(estimated_costs={"venue": "-0.01"}),
        _event_payload(currency="XYZ"),
    ]
    for payload in invalid_payloads:
        response = client.post("/api/v1/events", json=payload)
        assert response.status_code == 422
        assert response.json()["detail"]


def test_scenario_rejects_empty_changes_and_invalid_values():
    response = client.post(
        "/api/v1/events/scenario-analysis",
        json={"event": _event_payload(), "changes": {}},
    )
    assert response.status_code == 422
    assert response.json()["detail"]

    response = client.post(
        "/api/v1/events/scenario-analysis",
        json={"event": _event_payload(), "changes": {"guest_count": 0}},
    )
    assert response.status_code == 422
    assert response.json()["detail"]

    invalid_scenarios = [
        {},
        {"guest_count": 0},
        {"budget": "0"},
        {"estimated_costs": {"venue": "-1"}},
        {"estimated_costs": {"unknown": "1"}},
    ]
    for changes in invalid_scenarios:
        response = client.post(
            "/api/v1/events/scenario-analysis",
            json={"event": _event_payload(), "changes": changes},
        )
        assert response.status_code == 422
        assert response.json()["detail"]


def test_malformed_requests_and_unknown_fields_are_rejected():
    malformed = client.post("/api/v1/events", content="{invalid json")
    assert malformed.status_code == 422
    assert malformed.json()["detail"]

    extra_field = client.post(
        "/api/v1/events",
        json=_event_payload(fake_vendor_quote="₹123"),
    )
    assert extra_field.status_code == 422


def test_tight_timeline_risk_uses_the_supplied_event_date():
    response = client.post(
        "/api/v1/events",
        json=_event_payload(event_date=(date.today() + timedelta(days=10)).isoformat()),
    )

    assert response.status_code == 200
    risk = next(
        risk for risk in response.json()["risks"] if risk["type"] == "timeline_tight"
    )
    assert risk["evidence"]["days_until_event"] == 10
    assert risk["severity"] == "medium"
