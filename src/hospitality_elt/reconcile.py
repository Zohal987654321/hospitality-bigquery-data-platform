"""Automated reconciliation: warehouse totals vs. the source system's own report.

After dbt builds the marts, yesterday's net sales and transaction counts per
location are compared with the POS vendor's daily sales report. Differences
beyond tolerance are written to ``ops.reconciliation_results`` and alerted.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class ReconciliationResult:
    business_date: str
    pos_location_id: str
    metric: str
    source_value: Decimal
    warehouse_value: Decimal
    difference: Decimal
    within_tolerance: bool


def compare_daily_sales(
    business_date: str,
    source_rows: list[dict[str, Any]],
    warehouse_rows: list[dict[str, Any]],
    *,
    amount_tolerance: Decimal = Decimal("1.00"),
) -> list[ReconciliationResult]:
    """Rows on both sides: ``pos_location_id``, ``net_sales``, ``transaction_count``."""
    wh = {r["pos_location_id"]: r for r in warehouse_rows}
    src = {r["pos_location_id"]: r for r in source_rows}
    results: list[ReconciliationResult] = []
    for loc in sorted(set(wh) | set(src)):
        s, w = src.get(loc, {}), wh.get(loc, {})
        for metric, tol in (("net_sales", amount_tolerance), ("transaction_count", Decimal(0))):
            sv = Decimal(str(s.get(metric, 0) or 0))
            wv = Decimal(str(w.get(metric, 0) or 0))
            diff = wv - sv
            results.append(
                ReconciliationResult(
                    business_date=business_date,
                    pos_location_id=loc,
                    metric=metric,
                    source_value=sv,
                    warehouse_value=wv,
                    difference=diff,
                    within_tolerance=abs(diff) <= tol,
                )
            )
    return results


WAREHOUSE_DAILY_SALES_SQL = """
select
    l.pos_location_id,
    coalesce(sum(p.net_sales), 0)            as net_sales,
    coalesce(sum(p.transaction_count), 0)    as transaction_count
from `{project}.marts.dim_location` l
left join `{project}.marts.mart_daily_location_performance` p
    on p.location_key = l.location_key
   and p.business_date = date(@business_date)
group by 1
"""
