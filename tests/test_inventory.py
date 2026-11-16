from hospitality_elt.pipeline import run_entity
from hospitality_elt.sources.inventory_sftp import LocalFileStore, SftpInventorySource, export_time
from hospitality_elt.storage import LocalLanding
from hospitality_elt.warehouse import LocalWarehouse

HEADER = "Location_Code,SKU,Counted_On,Quantity_On_Hand,Unit_Cost\n"


def _write(d, name, rows):
    (d / name).write_text(HEADER + "".join(rows))


def test_only_new_files_are_processed(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    _write(drop, "stock_counts_20261102T0300.csv", ["BONDI,SKU-0001,2026-11-02,10,1.50\n"])
    _write(drop, "stock_counts_20261109T0300.csv", ["BONDI,SKU-0001,2026-11-09,7,1.50\n"])
    (drop / "readme.csv").write_text("ignored")

    source = SftpInventorySource(LocalFileStore(drop))
    rows = list(source.extract("stock_counts", since="2026-11-05T00:00:00+00:00"))
    assert [r["counted_on"] for r in rows] == ["2026-11-09"]
    assert rows[0]["location_code"] == "BONDI"  # headers normalised to snake case
    assert rows[0]["source_file"] == "stock_counts_20261109T0300.csv"


def test_bad_rows_are_rejected_not_loaded(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    good = [f"BONDI,SKU-{i:04d},2026-11-09,5,2.00\n" for i in range(40)]
    _write(drop, "stock_counts_20261109T0300.csv", [*good, "BONDI,SKU-9999,not-a-date,5,2.00\n"])
    wh = LocalWarehouse(tmp_path / "wh")
    run = run_entity(
        SftpInventorySource(LocalFileStore(drop)),
        "stock_counts",
        warehouse=wh,
        landing=LocalLanding(tmp_path / "l"),
        pii_key="k",
        run_id="r1",
        lookback_hours=48,
        max_reject_ratio=0.05,
    )
    assert (run.status, run.loaded, run.rejected) == ("success", 40, 1)
    assert wh.get_watermark("inventory", "stock_counts").startswith("2026-11-09T03:00")


def test_export_time_parsing():
    assert export_time("stock_counts_20261109T0300.csv").hour == 3
    assert export_time("other.csv") is None
