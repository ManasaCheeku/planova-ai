import re
from datetime import date, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from backend.app.schemas.events import EventCreate
from backend.app.services.event_planner import build_event_plan


NUMBER_PATTERN = r"(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?"
UNSUPPORTED_ACTIONS = (
    ("booking", re.compile(r"\b(book|reserve)\b", re.IGNORECASE)),
    ("sending messages", re.compile(r"\b(send|email|sms|text|invite)\b", re.IGNORECASE)),
    ("payment", re.compile(r"\b(pay|purchase|charge)\b", re.IGNORECASE)),
    ("cancellation", re.compile(r"\bcancel\b", re.IGNORECASE)),
)


def _extract_name(message: str) -> str | None:
    quoted = re.search(
        r"\b(?:called|named)\s+['\"]([^'\"]{1,120})['\"]",
        message,
        re.IGNORECASE,
    )
    if quoted:
        return quoted.group(1).strip()
    unquoted = re.search(
        r"\b(?:called|named)\s+(.+?)(?=\s+(?:for\s+\d|on\s+\d{4}-\d{2}-\d{2}|at\s+\d|with\s+(?:a\s+)?(?:budget|₹)|budget\b)|$)",
        message,
        re.IGNORECASE,
    )
    return unquoted.group(1).strip(" .,'\"") if unquoted else None


def _extract_budget(message: str) -> Decimal | None:
    patterns = (
        rf"\bbudget\b\s*(?:(?:of|is|around|about)\s*)?(?:₹|INR\b|Rs\.?\s*|rupees?\s*)?({NUMBER_PATTERN})",
        rf"(?:₹|INR\b|Rs\.?\s*)\s*({NUMBER_PATTERN})",
        rf"\b({NUMBER_PATTERN})\s*(?:INR|rupees?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            try:
                return Decimal(match.group(1).replace(",", ""))
            except InvalidOperation:
                return None
    return None


def _extract_event_date(message: str) -> date | None:
    if re.search(r"\btoday\b", message, re.IGNORECASE):
        return date.today()
    if re.search(r"\btomorrow\b", message, re.IGNORECASE):
        return date.today() + timedelta(days=1)
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", message)
    if not match:
        return None
    try:
        parsed = date.fromisoformat(match.group(1))
    except ValueError:
        return None
    return parsed if parsed >= date.today() else None


def _extract_event_time(message: str) -> time | None:
    match = re.search(
        r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = (match.group(3) or "").lower()
    if minute > 59 or (meridiem and not 1 <= hour <= 12) or (not meridiem and hour > 23):
        return None
    if meridiem == "am" and hour == 12:
        hour = 0
    elif meridiem == "pm" and hour != 12:
        hour += 12
    return time(hour, minute)


def _extract_guest_count(message: str) -> int | None:
    match = re.search(
        rf"\b({NUMBER_PATTERN})\s*(?:guests?|attendees|people|persons)\b",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_event_type(message: str) -> str | None:
    for keyword, event_type in (
        ("birthday", "birthday"),
        ("wedding", "wedding"),
        ("corporate", "corporate"),
        ("conference", "conference"),
        ("community", "community gathering"),
    ):
        if re.search(rf"\b{keyword}\b", message, re.IGNORECASE):
            return event_type
    return None


def _extract_location(message: str) -> str | None:
    explicit = re.search(
        r"\blocation(?:\s+is)?\s*[:=]\s*([^,;\n]{2,100})",
        message,
        re.IGNORECASE,
    )
    if explicit:
        return explicit.group(1).strip(" .")
    in_location = re.search(
        r"\bin\s+([A-Z][A-Za-z]+(?:[ -][A-Z][A-Za-z]+){0,3})(?=\s+(?:on|at|for|with|budget|named|called)\b|[,;.]|$)",
        message,
    )
    return in_location.group(1).strip() if in_location else None


def propose_event_plan(message: str) -> dict[str, Any]:
    name = _extract_name(message)
    budget = _extract_budget(message)
    event_date = _extract_event_date(message)
    guest_count = _extract_guest_count(message)
    event_time = _extract_event_time(message)
    event_type = _extract_event_type(message)
    location = _extract_location(message)

    extracted: dict[str, Any] = {
        "event_name": name,
        "event_type": event_type,
        "event_date": event_date.isoformat() if event_date else None,
        "event_time": event_time.isoformat(timespec="minutes") if event_time else None,
        "guest_count": guest_count,
        "location": location,
        "budget_inr": float(budget) if budget is not None else None,
    }
    missing_information: list[str] = []
    questions: list[str] = []
    if not name:
        missing_information.append("event_name")
        questions.append("What should this event be called?")
    if not event_type:
        missing_information.append("event_type")
        questions.append("What type of event are you planning?")
    if not event_date:
        missing_information.append("event_date")
        questions.append("What future date should I use?")
    if guest_count is None or guest_count <= 0:
        missing_information.append("guest_count")
        questions.append("How many guests or attendees do you expect?")
    if not location:
        missing_information.append("location")
        questions.append("Where will the event take place?")
    if budget is None or budget <= 0:
        missing_information.append("budget")
        questions.append("What is the total budget in INR? It must be greater than ₹0.")
    if event_date is None and re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", message):
        questions.append("The date provided is invalid or in the past. What future event date should I use?")
    unsupported_actions = [
        label for label, pattern in UNSUPPORTED_ACTIONS if pattern.search(message)
    ]

    if (
        missing_information
        or name is None
        or event_type is None
        or event_date is None
        or guest_count is None
        or guest_count <= 0
        or location is None
        or budget is None
        or budget <= 0
    ):
        return {
            "mode": "deterministic_fallback",
            "ai_model_configured": False,
            "status": "needs_input",
            "extracted": extracted,
            "missing_information": missing_information,
            "questions": questions,
            "unsupported_actions": unsupported_actions,
            "notice": (
                "No AI model is configured. This deterministic fallback only extracts "
                "explicitly recognized details; no event was saved and no external action was attempted."
            ),
            "draft": None,
            "plan": None,
        }

    try:
        event = EventCreate(
            event_name=name,
            event_type=event_type,
            event_date=event_date,
            event_time=event_time,
            guest_count=guest_count,
            location=location,
            budget=budget,
            currency="INR",
        )
    except ValidationError as error:
        validation_fields = sorted(
            {
                str(item["loc"][0])
                for item in error.errors()
                if item.get("loc")
            }
        )
        return {
            "mode": "deterministic_fallback",
            "ai_model_configured": False,
            "status": "needs_input",
            "extracted": extracted,
            "missing_information": validation_fields,
            "questions": [
                "Some extracted details exceed the event schema limits. Please revise: "
                + ", ".join(validation_fields)
            ],
            "unsupported_actions": unsupported_actions,
            "notice": (
                "No AI model is configured. This deterministic fallback did not save "
                "an event or attempt an external action."
            ),
            "draft": None,
            "plan": None,
        }
    return {
        "mode": "deterministic_fallback",
        "ai_model_configured": False,
        "status": "draft_ready",
        "extracted": extracted,
        "missing_information": [],
        "questions": [],
        "unsupported_actions": unsupported_actions,
        "notice": (
            "No AI model is configured. This is a deterministic draft based only on "
            "recognized input. Review it before saving; no event was saved and no external action was attempted."
        ),
        "draft": event,
        "plan": build_event_plan(event),
    }
