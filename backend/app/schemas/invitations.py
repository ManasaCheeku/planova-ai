from datetime import date, datetime
import re
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


InvitationStatus = Literal[
    "not_prepared",
    "drafted",
    "queued",
    "sent",
    "delivered",
    "failed",
]
EditableInvitationStatus = Literal["not_prepared", "drafted"]
RSVPStatus = Literal["awaiting_response", "attending", "not_attending"]
DeliveryStatus = Literal[
    "draft_only",
    "queued",
    "sent",
    "delivered",
    "failed",
    "unknown",
    "cancelled",
]
DraftKind = Literal["invitation", "reminder"]
InvitationTone = Literal["formal", "friendly", "celebratory", "professional"]

_EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,63}$")
_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s().-]{5,24}$")


def _clean_optional_text(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must not be blank")
    return cleaned


def _clean_requirement_items(values: list[str]) -> list[str]:
    cleaned = [item.strip() for item in values]
    if any(not item for item in cleaned):
        raise ValueError("requirement items must not be blank")
    return cleaned


class GuestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=32)
    group_name: str | None = Field(default=None, max_length=80)
    party_size: int = Field(default=1, ge=1, le=100)
    notes: str | None = Field(default=None, max_length=2000)
    dietary_requirements: list[str] = Field(default_factory=list, max_length=20)
    accessibility_requirements: list[str] = Field(default_factory=list, max_length=20)
    accommodation_requirements: list[str] = Field(default_factory=list, max_length=20)
    invitation_status: EditableInvitationStatus = "not_prepared"
    rsvp_status: RSVPStatus = "awaiting_response"
    rsvp_party_size: int | None = Field(default=None, ge=1, le=100)

    @field_validator("name", "group_name", "notes")
    @classmethod
    def clean_text(cls, value: str | None, info) -> str | None:
        return _clean_optional_text(value, info.field_name)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        value = _clean_optional_text(value, "email")
        if value is not None and not _EMAIL_PATTERN.fullmatch(value):
            raise ValueError("email must be a valid email address")
        return value.casefold() if value else None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        value = _clean_optional_text(value, "phone")
        if value is not None and not _PHONE_PATTERN.fullmatch(value):
            raise ValueError("phone must be a valid phone number")
        return value

    @field_validator(
        "dietary_requirements",
        "accessibility_requirements",
        "accommodation_requirements",
    )
    @classmethod
    def clean_requirements(cls, values: list[str]) -> list[str]:
        return _clean_requirement_items(values)

    @model_validator(mode="after")
    def validate_rsvp_size(self) -> "GuestCreate":
        if self.rsvp_status == "attending" and self.rsvp_party_size is not None:
            if self.rsvp_party_size > self.party_size:
                raise ValueError("rsvp_party_size cannot exceed the invited party_size")
        if self.rsvp_status != "attending" and self.rsvp_party_size is not None:
            raise ValueError("rsvp_party_size is only valid when rsvp_status is attending")
        return self


class GuestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=32)
    group_name: str | None = Field(default=None, max_length=80)
    party_size: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = Field(default=None, max_length=2000)
    dietary_requirements: list[str] | None = Field(default=None, max_length=20)
    accessibility_requirements: list[str] | None = Field(default=None, max_length=20)
    accommodation_requirements: list[str] | None = Field(default=None, max_length=20)
    invitation_status: EditableInvitationStatus | None = None
    duplicate_of_id: UUID | None = None

    @field_validator("name", "group_name", "notes")
    @classmethod
    def clean_text(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _clean_optional_text(value, info.field_name)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _clean_optional_text(value, "email")
        if not _EMAIL_PATTERN.fullmatch(value):
            raise ValueError("email must be a valid email address")
        return value.casefold()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _clean_optional_text(value, "phone")
        if not _PHONE_PATTERN.fullmatch(value):
            raise ValueError("phone must be a valid phone number")
        return value

    @field_validator(
        "dietary_requirements",
        "accessibility_requirements",
        "accommodation_requirements",
    )
    @classmethod
    def clean_requirements(cls, values: list[str] | None) -> list[str] | None:
        return _clean_requirement_items(values) if values is not None else None

    @model_validator(mode="after")
    def require_changes(self) -> "GuestUpdate":
        if not self.model_fields_set:
            raise ValueError("provide at least one guest field to update")
        return self


class RSVPUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rsvp_status: RSVPStatus
    party_size: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = Field(default=None, max_length=2000)
    dietary_requirements: list[str] | None = Field(default=None, max_length=20)
    accessibility_requirements: list[str] | None = Field(default=None, max_length=20)
    accommodation_requirements: list[str] | None = Field(default=None, max_length=20)
    source: Literal["manual"] = "manual"

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, "notes") if value is not None else None

    @field_validator(
        "dietary_requirements",
        "accessibility_requirements",
        "accommodation_requirements",
    )
    @classmethod
    def clean_requirements(cls, values: list[str] | None) -> list[str] | None:
        return _clean_requirement_items(values) if values is not None else None

    @model_validator(mode="after")
    def size_requires_attendance(self) -> "RSVPUpdate":
        if self.rsvp_status != "attending" and self.party_size is not None:
            raise ValueError("party_size is only valid when rsvp_status is attending")
        return self


class GuestResponse(BaseModel):
    id: str
    event_id: str
    created_at: datetime
    updated_at: datetime
    name: str
    email: str | None
    phone: str | None
    group_name: str | None
    party_size: int
    notes: str | None
    dietary_requirements: list[str]
    accessibility_requirements: list[str]
    accommodation_requirements: list[str]
    invitation_status: InvitationStatus
    rsvp_status: RSVPStatus
    rsvp_party_size: int | None
    duplicate_of_id: str | None


class DuplicateSuggestionResponse(BaseModel):
    guest_id: str
    possible_duplicate_id: str
    match_reasons: list[Literal["email", "phone", "name_and_contact"]]


class RSVPActivityResponse(BaseModel):
    id: str
    guest_id: str
    action: str
    source: str
    details: dict[str, Any]
    created_at: datetime


class InvitationDraftGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tone: InvitationTone = "friendly"
    language: str = Field(default="English", min_length=1, max_length=64)
    group_name: str | None = Field(default=None, max_length=80)
    rsvp_deadline: date | None = None
    instructions: str | None = Field(default=None, max_length=1000)

    @field_validator("language", "group_name", "instructions")
    @classmethod
    def clean_text(cls, value: str | None, info) -> str | None:
        return _clean_optional_text(value, info.field_name)


class InvitationDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: DraftKind = "invitation"
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=6000)
    tone: InvitationTone = "friendly"
    language: str = Field(default="English", min_length=1, max_length=64)
    group_name: str | None = Field(default=None, max_length=80)
    rsvp_deadline: date | None = None

    @field_validator("subject", "body", "language", "group_name")
    @classmethod
    def clean_text(cls, value: str | None, info) -> str | None:
        return _clean_optional_text(value, info.field_name)


class InvitationDraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=6000)
    tone: InvitationTone | None = None
    language: str | None = Field(default=None, min_length=1, max_length=64)
    group_name: str | None = Field(default=None, max_length=80)
    rsvp_deadline: date | None = None

    @field_validator("subject", "body", "language", "group_name")
    @classmethod
    def clean_text(cls, value: str | None, info) -> str | None:
        return _clean_optional_text(value, info.field_name) if value is not None else None

    @model_validator(mode="after")
    def require_changes(self) -> "InvitationDraftUpdate":
        if not self.model_fields_set:
            raise ValueError("provide at least one draft field to update")
        return self


class InvitationDraftResponse(BaseModel):
    id: str
    event_id: str
    kind: DraftKind
    subject: str
    body: str
    tone: InvitationTone
    language: str
    group_name: str | None
    rsvp_deadline: date | None
    generated_by: Literal["manual", "genai", "deterministic"]
    missing_information: list[str]
    created_at: datetime
    updated_at: datetime


class DeliveryPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: UUID
    guest_ids: list[UUID] = Field(min_length=1, max_length=1000)

    @field_validator("guest_ids")
    @classmethod
    def guest_ids_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("guest_ids must not contain duplicates")
        return value


class DeliverySendRequest(DeliveryPreviewRequest):
    approved: Literal[True]
    idempotency_key: UUID = Field(default_factory=uuid4)


class DeliveryRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: Literal[True]
    idempotency_key: UUID = Field(default_factory=uuid4)


class DeliveryPreviewRecipient(BaseModel):
    guest_id: str
    guest_name: str
    email: str | None
    eligible: bool
    reason: str | None = None
    subject: str | None = None
    body: str | None = None


class DeliveryPreviewResponse(BaseModel):
    event_id: str
    draft_id: str
    delivery_mode: Literal["smtp", "draft_only"]
    recipients: list[DeliveryPreviewRecipient]
    approved: Literal[False] = False
    notice: str


class DeliveryAttemptResponse(BaseModel):
    id: str
    batch_id: str | None
    event_id: str
    guest_id: str
    draft_id: str
    channel: Literal["email"]
    status: DeliveryStatus
    recipient_address: str
    provider_message_id: str | None
    transport_message_id: str | None
    error_message: str | None
    retry_of_id: str | None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None


class DeliveryBatchResponse(BaseModel):
    id: str
    event_id: str
    draft_id: str
    kind: DraftKind
    idempotency_key: str
    status: Literal["draft_only", "completed", "partial_failed", "failed", "unknown", "cancelled"]
    delivery_mode: Literal["smtp", "draft_only"]
    approved_at: datetime
    created_at: datetime
    updated_at: datetime
    attempts: list[DeliveryAttemptResponse]
    notice: str


class ReminderPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guest_ids: list[UUID] | None = Field(default=None, max_length=1000)
    tone: InvitationTone = "friendly"
    language: str = Field(default="English", min_length=1, max_length=64)
    rsvp_deadline: date | None = None
    instructions: str | None = Field(default=None, max_length=1000)

    @field_validator("guest_ids")
    @classmethod
    def guest_ids_must_be_unique(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("guest_ids must not contain duplicates")
        return value

    @field_validator("language", "instructions")
    @classmethod
    def clean_text(cls, value: str | None, info) -> str | None:
        return _clean_optional_text(value, info.field_name) if value is not None else None


class ReminderSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: Literal[True]
    idempotency_key: UUID = Field(default_factory=uuid4)


class ReminderPreparationResponse(BaseModel):
    id: str
    event_id: str
    draft: InvitationDraftResponse
    guest_ids: list[str]
    status: Literal["prepared", "sent", "cancelled"]
    created_at: datetime
    updated_at: datetime
    delivery_batch_id: str | None
    notice: str


class InvitationSummaryResponse(BaseModel):
    total_guests: int
    invitation_counts: dict[str, int]
    rsvp_counts: dict[str, int]
    confirmed_party_size: int
    pending_guest_ids: list[str]
    pending_count: int
    declined_count: int
    response_rate_percent: float


class DeliveryConfigurationResponse(BaseModel):
    mode: Literal["smtp", "draft_only"]
    configured: bool
    sender: str | None
    notice: str


class InvitationOverviewResponse(BaseModel):
    event_id: str
    guests: list[GuestResponse]
    drafts: list[InvitationDraftResponse]
    summary: InvitationSummaryResponse
    rsvp_activity: list[RSVPActivityResponse]
    delivery_attempts: list[DeliveryAttemptResponse]
    reminder_preparations: list[ReminderPreparationResponse]
    delivery: DeliveryConfigurationResponse
    coordination: dict[str, Any]
