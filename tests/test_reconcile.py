from decimal import Decimal

from hospitality_elt.notify import summarise
from hospitality_elt.reconcile import compare_daily_sales
from hospitality_elt.warehouse import RunRecord


def test_flags_mismatches_and_missing_locations():
    source = [
        {"pos_location_id": "A", "net_sales": "1000.00", "transaction_count": 10},
        {"pos_location_id": "B", "net_sales": "500.00", "transaction_count": 5},
    ]
    warehouse = [{"pos_location_id": "A", "net_sales": Decimal("1000.40"), "transaction_count": 10}]
    results = {
        (r.pos_location_id, r.metric): r
        for r in compare_daily_sales("2026-11-14", source, warehouse)
    }

    assert results[("A", "net_sales")].within_tolerance  # 40c rounding is fine
    assert results[("A", "transaction_count")].within_tolerance
    assert not results[("B", "net_sales")].within_tolerance  # missing in warehouse
    assert results[("B", "net_sales")].difference == Decimal("-500.00")


def test_summary_message_lists_failures():
    runs = [
        RunRecord("r", "pos", "transactions", "success", "t", loaded=10),
        RunRecord("r", "workforce", "shifts", "failed", "t", error="TimeoutError"),
    ]
    text = summarise(runs)
    assert text.startswith("❌") and "TimeoutError" in text
