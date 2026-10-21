
from datetime import date
from decimal import Decimal

from backend.app.repositories import vendor_store


def compare_vendor_quotes(event_id: str) -> dict:
    comparisons = []
    today = date.today()

    for vendor in vendor_store.list_vendors(event_id):
        for quote in vendor_store.list_quotes(vendor["id"]):
            warnings = []
            valid_until = quote.get("valid_until")

            if valid_until:
                expiry = (
                    valid_until
                    if isinstance(valid_until, date)
                    else date.fromisoformat(str(valid_until))
                )
                if expiry < today:
                    warnings.append("Quote has expired")

            if not quote.get("includes"):
                warnings.append("Included services are not specified")

            if not quote.get("excludes"):
                warnings.append("Excluded services are not specified")

            comparisons.append({
                "vendor_id": vendor["id"],
                "vendor_name": vendor["name"],
                "category": vendor["category"],
                "quote_id": quote["id"],
                "amount": str(Decimal(str(quote["amount"]))),
                "currency": quote["currency"],
                "valid_until": str(valid_until) if valid_until else None,
                "status": quote["status"],
                "includes": quote.get("includes", []),
                "excludes": quote.get("excludes", []),
                "warnings": warnings,
            })

    comparisons.sort(
        key=lambda item: (
            item["category"],
            item["currency"],
            Decimal(item["amount"]),
            item["vendor_name"].casefold(),
        )
    )

    for item in comparisons:
        comparable = [
            quote for quote in comparisons
            if quote["category"] == item["category"]
            and quote["currency"] == item["currency"]
        ]
        item["comparable_quote_count"] = len(comparable)
        item["lowest_price_in_group"] = (
            Decimal(item["amount"])
            == min(Decimal(q["amount"]) for q in comparable)
        )

    return {
        "event_id": event_id,
        "quote_count": len(comparisons),
        "comparisons": comparisons,
        "note": (
            "Prices are compared only within matching categories and currencies. "
            "The lowest price does not necessarily represent the best value."
        ),
    }
