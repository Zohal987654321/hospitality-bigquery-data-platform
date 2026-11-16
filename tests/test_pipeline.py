"""End-to-end: mock APIs -> PII -> validation -> landing -> raw warehouse -> state."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from hospitality_elt.http import ApiClient, OAuth2ClientCredentials
from hospitality_elt.pipeline import run_entity
from hospitality_elt.reconcile import compare_daily_sales
from hospitality_elt.sources.pos import PosApiSource
from hospitality_elt.sources.workforce import WorkforceApiSource
from hospitality_elt.storage import LocalLanding
from hospitality_elt.warehouse import LocalWarehouse
from mock_sources.generator import CUTOFF_HOURS, LOCATIONS, generate

KEY = "test-pii-key"


@pytest.fixture
def pos(mock_transport):
    oauth = OAuth2ClientCredentials(
        "http://mock/pos/oauth/token", "demo-client", "demo-secret", transport=mock_transport
    )
    return PosApiSource(
        ApiClient("http://mock/pos", oauth=oauth, transport=mock_transport), page_size=500
    )


@pytest.fixture
def workforce(mock_transport):
    return WorkforceApiSource(
        ApiClient("http://mock/workforce", api_key="demo-workforce-key", transport=mock_transport)
    )


@pytest.fixture
def targets(tmp_path):
    return LocalWarehouse(tmp_path / "wh"), LocalLanding(tmp_path / "landing")


def _run(source, entity, targets, run_id="run-1", **kw):
    wh, landing = targets
    return run_entity(
        source,
        entity,
        warehouse=wh,
        landing=landing,
        pii_key=KEY,
        run_id=run_id,
        lookback_hours=48,
        max_reject_ratio=0.05,
        **kw,
    )


def _raw(wh: LocalWarehouse, source: str, entity: str) -> list[dict]:
    lines = wh.raw_path(source, entity).read_text().splitlines()
    return [json.loads(line) for line in lines if line]


def test_transactions_load_with_dedupe_and_rejects(pos, targets):
    run = _run(pos, "transactions", targets)
    expected_unique = len({t["transaction_id"] for t in generate().transactions})

    assert run.status == "success"
    assert run.duplicates_removed == 2  # injected re-sends
    assert run.rejected == 1  # injected broken transaction
    assert run.loaded == expected_unique - 1
    rows = _raw(targets[0], "pos", "transactions")
    payload = json.loads(rows[0]["payload"])
    assert "card" not in payload and "customer" not in payload
    assert payload["staff_id"].startswith("EMP") is False  # pseudonymised
    assert targets[0].get_watermark("pos", "transactions") == run.watermark_to


def test_rerunning_the_same_run_is_idempotent(pos, targets):
    _run(pos, "transactions", targets, run_id="run-1")
    first = len(_raw(targets[0], "pos", "transactions"))
    targets[0].set_watermark("pos", "transactions", "2000-01-01T00:00:00+00:00", "reset")
    _run(pos, "transactions", targets, run_id="run-1")  # retry of the same run
    assert len(_raw(targets[0], "pos", "transactions")) == first


def test_incremental_run_only_pulls_lookback_window(pos, targets):
    full = _run(pos, "transactions", targets, run_id="run-1")
    incr = _run(pos, "transactions", targets, run_id="run-2")
    assert incr.status == "success"
    assert 0 < incr.extracted < full.extracted / 5


def test_failure_does_not_advance_watermark(targets):
    class Broken(PosApiSource):
        def __init__(self):
            pass

        def extract(self, entity, since):
            raise ConnectionError("vendor down")

    wh, _ = targets
    wh.set_watermark("pos", "transactions", "2026-11-01T00:00:00+00:00", "prev")
    run = _run(Broken(), "transactions", targets)
    assert run.status == "failed" and "vendor down" in run.error
    assert wh.get_watermark("pos", "transactions") == "2026-11-01T00:00:00+00:00"
    log = (wh._root / "ops_ingestion_runs.jsonl").read_text()  # failure is still logged
    assert '"status": "failed"' in log


def test_workforce_employees_and_shifts_join_on_pseudonymised_key(workforce, targets):
    _run(workforce, "employees", targets)
    shifts_run = _run(workforce, "shifts", targets)
    assert shifts_run.rejected == 1  # injected shift ending before it starts
    employees = {
        json.loads(r["payload"])["employee_id"] for r in _raw(targets[0], "workforce", "employees")
    }
    shift_emps = {
        json.loads(r["payload"])["employee_id"] for r in _raw(targets[0], "workforce", "shifts")
    }
    assert shift_emps <= employees
    raw_text = targets[0].raw_path("workforce", "employees").read_text()
    assert "tax_file_number" not in raw_text and "@example.com" not in raw_text


def test_warehouse_totals_reconcile_with_vendor_report(pos, targets, mock_client):
    """Re-implements the dbt staging/mart logic in Python over the raw layer and checks
    it agrees with the POS vendor's own daily report — the same comparison the
    production reconciliation step makes against BigQuery."""
    _run(pos, "transactions", targets)
    tz = {pos_id: zone for pos_id, _w, _i, _n, zone, *_ in LOCATIONS}
    day = datetime(2026, 11, 14).date()

    totals: dict[str, dict] = {}
    for row in _raw(targets[0], "pos", "transactions"):
        t = json.loads(row["payload"])
        if t["status"] == "voided":
            continue
        local = datetime.fromisoformat(t["opened_at"]).astimezone(ZoneInfo(tz[t["location_id"]]))
        if (local - timedelta(hours=CUTOFF_HOURS)).date() != day:
            continue
        agg = totals.setdefault(
            t["location_id"],
            {"pos_location_id": t["location_id"], "net_sales": Decimal(0), "transaction_count": 0},
        )
        agg["net_sales"] += sum(Decimal(li["net_amount"]) for li in t["line_items"])
        agg["transaction_count"] += t["status"] == "completed"

    token = mock_client.post(
        "/pos/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=("demo-client", "demo-secret"),
    ).json()["access_token"]
    report = mock_client.get(
        "/pos/v1/reports/daily-sales",
        params={"date": day.isoformat()},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    results = compare_daily_sales(day.isoformat(), report, list(totals.values()))
    assert results and all(r.within_tolerance for r in results)
