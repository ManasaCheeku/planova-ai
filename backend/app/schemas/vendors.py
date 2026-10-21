
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.events import ExpenseCategory, Money, SUPPORTED_CURRENCIES


VendorType = Literal[
    "venue",
    "catering",
    "photography",
    "decoration",
    "entertainment",
    "transport",
    "other",
]


class VendorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=150)
    category: VendorType
    contact_name: str | None = Field(default=None, max_length=120)
    contact_email: str | None = Field(default=None, max_length=254)
    contact_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("name", "event_id")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value


class QuoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = "INR"
    valid_until: date | None = None
    includes: list[str] = Field(default_factory=list, max_length=30)
    excludes: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in SUPPORTED_CURRENCIES:
            raise ValueError("Unsupported currency")
        return value

    @field_validator("includes", "excludes")
    @classmethod
    def clean_items(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values]
        if any(not item for item in cleaned):
            raise ValueError("Items cannot be blank")
        return cleaned


class VendorResponse(BaseModel):
    id: str
    event_id: str
    name: str
    category: VendorType
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None


class QuoteResponse(BaseModel):
    id: str
    vendor_id: str
    amount: Decimal
    currency: str
    valid_until: date | None = None
    includes: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    notes: str | None = None
    status: Literal["quoted", "accepted", "rejected"] = "quoted"
