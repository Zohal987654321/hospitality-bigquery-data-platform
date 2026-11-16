"""Point-of-sale REST API (OAuth 2.0 client credentials, cursor pagination).

The endpoint shapes follow the common pattern used by cloud POS vendors:
``GET /v1/transactions?updated_since=...&cursor=...&limit=...`` returning
``{"data": [...], "next_cursor": "..."}``. Mapping to a specific vendor is a matter
of adjusting paths and field names here — nothing downstream changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from hospitality_elt.http import ApiClient
from hospitality_elt.pii import PiiPolicy
from hospitality_elt.schemas import PosLocation, PosProduct, PosTransaction
from hospitality_elt.sources.base import EntitySpec, Source

_ENDPOINTS = {
    "transactions": "/v1/transactions",
    "products": "/v1/products",
    "locations": "/v1/locations",
}


class PosApiSource(Source):
    name = "pos"
    entities = {
        "transactions": EntitySpec(
            name="transactions",
            contract=PosTransaction,
            key_fields=("transaction_id",),
            updated_field="updated_at",
            pii=PiiPolicy(
                # Customer and card details are never needed for analytics.
                drop=frozenset({"customer", "customer_email", "customer_name", "card"}),
                pseudonymise=frozenset({"staff_id"}),
            ),
        ),
        "products": EntitySpec(
            name="products",
            contract=PosProduct,
            key_fields=("product_id",),
            updated_field="updated_at",
        ),
        "locations": EntitySpec(
            name="locations",
            contract=PosLocation,
            key_fields=("location_id",),
            updated_field="updated_at",
            # Store address is business data, not personal data.
            pii=PiiPolicy(allow=frozenset({"address"})),
        ),
    }

    def __init__(self, client: ApiClient, page_size: int = 200) -> None:
        self._client = client
        self._page_size = page_size

    def extract(self, entity: str, since: str | None) -> Iterator[dict[str, Any]]:
        params: dict[str, Any] = {"limit": self._page_size}
        if since:
            params["updated_since"] = since
        cursor: str | None = None
        while True:
            if cursor:
                params["cursor"] = cursor
            page = self._client.get_json(_ENDPOINTS[entity], params=params)
            yield from page.get("data", [])
            cursor = page.get("next_cursor")
            if not cursor:
                break

    def daily_sales_report(self, business_date: str) -> list[dict[str, Any]]:
        """Vendor-calculated totals per location, used for reconciliation."""
        page = self._client.get_json("/v1/reports/daily-sales", params={"date": business_date})
        return page.get("data", [])

    def close(self) -> None:
        self._client.close()
