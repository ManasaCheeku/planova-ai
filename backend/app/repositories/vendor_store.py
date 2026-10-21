
import json
import sqlite3
import uuid
from contextlib import closing
from decimal import Decimal

from backend.app.repositories import dashboard_store
from backend.app.schemas.vendors import VendorCreate, QuoteCreate


def _connect():
    # Reuse Planova's existing database and schema initialization.
    return dashboard_store._connect()


def _vendor_dict(row):
    return dict(row)


def _quote_dict(row):
    result = dict(row)
    result["includes"] = json.loads(result["includes"])
    result["excludes"] = json.loads(result["excludes"])
    return result


def create_vendor(data: VendorCreate) -> dict:
    if not dashboard_store.event_exists(data.event_id):
        raise ValueError("Event not found")

    vendor_id = str(uuid.uuid4())

    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT INTO vendors (
                id, event_id, name, category, contact_name,
                contact_email, contact_phone, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vendor_id, data.event_id, data.name, data.category,
                data.contact_name, data.contact_email,
                data.contact_phone, data.notes,
            ),
        )
        row = connection.execute(
            "SELECT * FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()

    return _vendor_dict(row)


def list_vendors(event_id: str) -> list[dict]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM vendors WHERE event_id = ? ORDER BY name",
            (event_id,),
        ).fetchall()

    return [_vendor_dict(row) for row in rows]


def create_quote(vendor_id: str, data: QuoteCreate) -> dict:
    quote_id = str(uuid.uuid4())

    with closing(_connect()) as connection, connection:
        vendor = connection.execute(
            "SELECT id FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()

        if vendor is None:
            raise ValueError("Vendor not found")

        connection.execute(
            """
            INSERT INTO vendor_quotes (
                id, vendor_id, amount, currency, valid_until,
                includes, excludes, notes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'quoted')
            """,
            (
                quote_id, vendor_id, str(data.amount), data.currency,
                data.valid_until.isoformat() if data.valid_until else None,
                json.dumps(data.includes), json.dumps(data.excludes),
                data.notes,
            ),
        )

        row = connection.execute(
            "SELECT * FROM vendor_quotes WHERE id = ?", (quote_id,)
        ).fetchone()

    return _quote_dict(row)


def list_quotes(vendor_id: str) -> list[dict]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            """
            SELECT * FROM vendor_quotes
            WHERE vendor_id = ?
            ORDER BY CAST(amount AS REAL), id
            """,
            (vendor_id,),
        ).fetchall()

    return [_quote_dict(row) for row in rows]
