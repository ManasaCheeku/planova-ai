"""REST endpoints for Smart Invitations & RSVP Management."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from backend.app.schemas.invitations import (
    DeliveryBatchResponse,
    DeliveryPreviewRequest,
    DeliveryPreviewResponse,
    DeliveryRetryRequest,
    DeliverySendRequest,
    DuplicateSuggestionResponse,
    GuestCreate,
    GuestResponse,
    GuestUpdate,
    InvitationDraftCreate,
    InvitationDraftGenerateRequest,
    InvitationDraftResponse,
    InvitationDraftUpdate,
    InvitationOverviewResponse,
    RSVPActivityResponse,
    RSVPUpdate,
    ReminderPreparationResponse,
    ReminderPrepareRequest,
    ReminderSendRequest,
)
from backend.app.services.ai_provider import AIProviderError
from backend.app.services.invitations import (
    cancel_reminder,
    create_guest,
    create_manual_invitation_draft,
    duplicate_suggestions,
    edit_guest,
    edit_invitation_draft,
    generate_invitation_draft,
    get_invitation_overview,
    list_rsvp_activity,
    prepare_reminders,
    preview_delivery,
    remove_guest,
    retry_delivery,
    send_delivery,
    send_reminder,
    update_rsvp,
)


router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])


def _missing_event() -> HTTPException:
    return HTTPException(status_code=404, detail="The event was not found.")


@router.get("/events/{event_id}", response_model=InvitationOverviewResponse)
def invitation_overview(event_id: UUID) -> dict:
    overview = get_invitation_overview(str(event_id))
    if overview is None:
        raise _missing_event()
    return overview


@router.get("/events/{event_id}/guests", response_model=list[GuestResponse])
def guests_for_event(event_id: UUID) -> list[dict]:
    overview = get_invitation_overview(str(event_id))
    if overview is None:
        raise _missing_event()
    return overview["guests"]


@router.post(
    "/events/{event_id}/guests",
    response_model=GuestResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_guest(event_id: UUID, request: GuestCreate) -> dict:
    guest = create_guest(str(event_id), request)
    if guest is None:
        raise _missing_event()
    return guest


@router.patch("/events/{event_id}/guests/{guest_id}", response_model=GuestResponse)
def update_guest(event_id: UUID, guest_id: UUID, request: GuestUpdate) -> dict:
    try:
        guest = edit_guest(str(event_id), str(guest_id), request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if guest is None:
        if get_invitation_overview(str(event_id)) is None:
            raise _missing_event()
        raise HTTPException(status_code=404, detail="The guest was not found for this event.")
    return guest


@router.delete("/events/{event_id}/guests/{guest_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_guest(event_id: UUID, guest_id: UUID) -> Response:
    deleted = remove_guest(str(event_id), str(guest_id))
    if deleted is None:
        raise _missing_event()
    if not deleted:
        raise HTTPException(status_code=404, detail="The guest was not found for this event.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/events/{event_id}/guests/{guest_id}/rsvp", response_model=GuestResponse)
def record_manual_rsvp(event_id: UUID, guest_id: UUID, request: RSVPUpdate) -> dict:
    try:
        guest = update_rsvp(str(event_id), str(guest_id), request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if guest is None:
        if get_invitation_overview(str(event_id)) is None:
            raise _missing_event()
        raise HTTPException(status_code=404, detail="The guest was not found for this event.")
    return guest


@router.get(
    "/events/{event_id}/guests/{guest_id}/activity",
    response_model=list[RSVPActivityResponse],
)
def guest_rsvp_activity(event_id: UUID, guest_id: UUID) -> list[dict]:
    overview = get_invitation_overview(str(event_id))
    if overview is None:
        raise _missing_event()
    if not any(guest["id"] == str(guest_id) for guest in overview["guests"]):
        raise HTTPException(status_code=404, detail="The guest was not found for this event.")
    return list_rsvp_activity(str(event_id), str(guest_id))


@router.get(
    "/events/{event_id}/duplicates", response_model=list[DuplicateSuggestionResponse]
)
def guest_duplicates(event_id: UUID) -> list[dict]:
    suggestions = duplicate_suggestions(str(event_id))
    if suggestions is None:
        raise _missing_event()
    return suggestions


@router.post(
    "/events/{event_id}/drafts/generate",
    response_model=InvitationDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_draft(event_id: UUID, request: InvitationDraftGenerateRequest) -> dict:
    try:
        draft = generate_invitation_draft(str(event_id), request)
    except AIProviderError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    if draft is None:
        raise _missing_event()
    return draft


@router.post(
    "/events/{event_id}/drafts",
    response_model=InvitationDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_draft(event_id: UUID, request: InvitationDraftCreate) -> dict:
    draft = create_manual_invitation_draft(str(event_id), request)
    if draft is None:
        raise _missing_event()
    return draft


@router.patch("/events/{event_id}/drafts/{draft_id}", response_model=InvitationDraftResponse)
def update_draft(event_id: UUID, draft_id: UUID, request: InvitationDraftUpdate) -> dict:
    try:
        draft = edit_invitation_draft(str(event_id), str(draft_id), request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if draft is None:
        if get_invitation_overview(str(event_id)) is None:
            raise _missing_event()
        raise HTTPException(status_code=404, detail="The invitation draft was not found for this event.")
    return draft


@router.post(
    "/events/{event_id}/delivery/preview", response_model=DeliveryPreviewResponse
)
def preview_invitation_delivery(event_id: UUID, request: DeliveryPreviewRequest) -> dict:
    try:
        preview = preview_delivery(str(event_id), request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if preview is None:
        raise _missing_event()
    return preview


@router.post("/events/{event_id}/delivery/send", response_model=DeliveryBatchResponse)
def approve_invitation_delivery(event_id: UUID, request: DeliverySendRequest) -> dict:
    try:
        batch = send_delivery(str(event_id), request)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if batch is None:
        raise _missing_event()
    return batch


@router.post(
    "/events/{event_id}/delivery-attempts/{attempt_id}/retry",
    response_model=DeliveryBatchResponse,
)
def approve_delivery_retry(
    event_id: UUID, attempt_id: UUID, request: DeliveryRetryRequest
) -> dict:
    try:
        batch = retry_delivery(str(event_id), str(attempt_id), request)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if batch is None:
        if get_invitation_overview(str(event_id)) is None:
            raise _missing_event()
        raise HTTPException(status_code=404, detail="The delivery attempt was not found for this event.")
    return batch


@router.post(
    "/events/{event_id}/reminders/prepare",
    response_model=ReminderPreparationResponse,
    status_code=status.HTTP_201_CREATED,
)
def prepare_rsvp_reminders(event_id: UUID, request: ReminderPrepareRequest) -> dict:
    try:
        preparation = prepare_reminders(str(event_id), request)
    except AIProviderError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if preparation is None:
        raise _missing_event()
    return preparation


@router.post(
    "/events/{event_id}/reminders/{preparation_id}/send",
    response_model=ReminderPreparationResponse,
)
def approve_rsvp_reminder(
    event_id: UUID, preparation_id: UUID, request: ReminderSendRequest
) -> dict:
    try:
        preparation = send_reminder(str(event_id), str(preparation_id), request)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if preparation is None:
        if get_invitation_overview(str(event_id)) is None:
            raise _missing_event()
        raise HTTPException(status_code=404, detail="The reminder preparation was not found for this event.")
    return preparation


@router.post(
    "/events/{event_id}/reminders/{preparation_id}/cancel",
    response_model=ReminderPreparationResponse,
)
def cancel_rsvp_reminder(event_id: UUID, preparation_id: UUID) -> dict:
    try:
        preparation = cancel_reminder(str(event_id), str(preparation_id))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if preparation is None:
        if get_invitation_overview(str(event_id)) is None:
            raise _missing_event()
        raise HTTPException(status_code=404, detail="The reminder preparation was not found for this event.")
    return preparation
