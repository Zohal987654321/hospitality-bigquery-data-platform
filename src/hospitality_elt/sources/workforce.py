"""Workforce management / rostering API (API key, page-number pagination).

Employee records from these systems carry the most sensitive data in the business
(contact details, tax file numbers, bank and super details, pay rates). Only the
attributes needed for labour analytics are kept; the employee identifier is
pseudonymised with the same key used for POS ``staff_id`` so the two still join.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from hospitality_elt.http import ApiClient
from hospitality_elt.pii import PiiPolicy
from hospitality_elt.schemas import WorkforceEmployee, WorkforceShift
from hospitality_elt.sources.base import EntitySpec, Source

_ENDPOINTS = {"employees": "/api/v2/employees", "shifts": "/api/v2/timesheets"}

_EMPLOYEE_POLICY = PiiPolicy(
    drop=frozenset(
        {"display_name", "pay_rate", "hourly_rate", "salary", "award_classification", "notes"}
    ),
    pseudonymise=frozenset({"employee_id", "manager_id"}),
)
_SHIFT_POLICY = PiiPolicy(
    drop=frozenset({"pay_rate", "hourly_rate", "notes", "gps"}),
    pseudonymise=frozenset({"employee_id", "approved_by"}),
)


class WorkforceApiSource(Source):
    name = "workforce"
    entities = {
        "employees": EntitySpec(
            name="employees",
            contract=WorkforceEmployee,
            key_fields=("employee_id",),
            updated_field="updated_at",
            pii=_EMPLOYEE_POLICY,
        ),
        "shifts": EntitySpec(
            name="shifts",
            contract=WorkforceShift,
            key_fields=("shift_id",),
            updated_field="updated_at",
            pii=_SHIFT_POLICY,
        ),
    }

    def __init__(self, client: ApiClient, page_size: int = 100) -> None:
        self._client = client
        self._page_size = page_size

    def extract(self, entity: str, since: str | None) -> Iterator[dict[str, Any]]:
        page_number = 1
        while True:
            params: dict[str, Any] = {"page": page_number, "per_page": self._page_size}
            if since:
                params["updated_after"] = since
            body = self._client.get_json(_ENDPOINTS[entity], params=params)
            yield from body.get("results", [])
            if page_number >= int(body.get("total_pages", 1)):
                break
            page_number += 1

    def close(self) -> None:
        self._client.close()
