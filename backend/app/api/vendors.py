
from fastapi import APIRouter, HTTPException, status

from backend.app.services.vendor_comparison import compare_vendor_quotes
from backend.app.repositories import vendor_store
from backend.app.schemas.vendors import (
    VendorCreate,
    VendorResponse,
    QuoteCreate,
    QuoteResponse,
)

router = APIRouter(prefix="/api/v1/vendors", tags=["vendors"])


@router.post("", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
def create_vendor(data: VendorCreate):
    try:
        return vendor_store.create_vendor(data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/events/{event_id}", response_model=list[VendorResponse])
def get_event_vendors(event_id: str):
    from backend.app.repositories.dashboard_store import event_exists

    if not event_exists(event_id):
        raise HTTPException(status_code=404, detail="Event not found")

    return vendor_store.list_vendors(event_id)


@router.post(
    "/{vendor_id}/quotes",
    response_model=QuoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_vendor_quote(vendor_id: str, data: QuoteCreate):
    try:
        return vendor_store.create_quote(vendor_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{vendor_id}/quotes", response_model=list[QuoteResponse])
def get_vendor_quotes(vendor_id: str):
    from backend.app.repositories.vendor_store import list_vendors

    # Confirm the vendor exists before returning its quotes.
    with vendor_store._connect() as connection:
        vendor = connection.execute(
            "SELECT id FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()

    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")

    return vendor_store.list_quotes(vendor_id)


@router.get("/events/{event_id}/quote-comparison")
def get_event_quote_comparison(event_id: str):
    from backend.app.repositories.dashboard_store import event_exists

    if not event_exists(event_id):
        raise HTTPException(status_code=404, detail="Event not found")

    return compare_vendor_quotes(event_id)

