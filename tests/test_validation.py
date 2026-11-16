import pytest

from hospitality_elt.schemas import PosTransaction
from hospitality_elt.validation import DataQualityError, enforce_reject_threshold, validate_batch


def tx(tid: str, updated: str, total: str = "10.00", line_net: str = "10.00") -> dict:
    return {
        "transaction_id": tid,
        "location_id": "L1",
        "status": "completed",
        "opened_at": "2026-11-01T01:00:00+00:00",
        "updated_at": updated,
        "total_net": total,
        "total_tax": "1.00",
        "line_items": [
            {
                "line_id": "1",
                "product_id": "p",
                "sku": "S",
                "quantity": 1,
                "unit_price": line_net,
                "net_amount": line_net,
            }
        ],
    }


def test_keeps_latest_version_of_duplicates():
    records = [
        tx("t1", "2026-11-01T02:00:00+00:00", "10.00", "10.00"),
        tx("t1", "2026-11-01T03:00:00+00:00", "12.00", "12.00"),
        tx("t2", "2026-11-01T02:00:00+00:00"),
    ]
    out = validate_batch(records, PosTransaction, ("transaction_id",), "updated_at")
    assert out.duplicates_removed == 1
    assert {r["transaction_id"]: r["total_net"] for r in out.valid} == {
        "t1": "12.00",
        "t2": "10.00",
    }


def test_rejects_when_lines_do_not_sum_to_header():
    out = validate_batch(
        [tx("bad", "2026-11-01T02:00:00+00:00", total="99.00")],
        PosTransaction,
        ("transaction_id",),
        "updated_at",
    )
    assert not out.valid
    assert "line net" in out.rejected[0]["errors"][0]["msg"]


def test_rejects_unknown_status():
    record = tx("t3", "2026-11-01T02:00:00+00:00")
    record["status"] = "mystery"
    out = validate_batch([record], PosTransaction, ("transaction_id",), "updated_at")
    assert out.rejected and out.rejected[0]["errors"][0]["loc"] == "status"


def test_reject_threshold_stops_the_load():
    records = [tx(f"b{i}", "2026-11-01T02:00:00+00:00", total="5") for i in range(3)]
    records.append(tx("ok", "2026-11-01T02:00:00+00:00"))
    out = validate_batch(records, PosTransaction, ("transaction_id",), "updated_at")
    with pytest.raises(DataQualityError):
        enforce_reject_threshold(out, 0.05, "pos.transactions")
