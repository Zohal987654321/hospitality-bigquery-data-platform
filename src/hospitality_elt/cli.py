"""Command-line entry point (also the container entrypoint for Cloud Run jobs).

    hospitality-elt ingest --source pos            # one source, incremental
    hospitality-elt ingest --source all --since 2026-07-01T00:00:00+00:00   # backfill
    hospitality-elt transform                       # dbt build
    hospitality-elt reconcile --date 2026-11-15
    hospitality-elt daily                           # ingest all -> dbt build -> reconcile -> notify
    hospitality-elt serve-webhooks                  # Cloud Run service

Exit code is non-zero when anything failed, so Cloud Run marks the execution as
failed and applies its retry policy.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hospitality_elt.config import Settings
from hospitality_elt.http import ApiClient, OAuth2ClientCredentials
from hospitality_elt.logging_setup import configure_logging
from hospitality_elt.notify import WebhookNotifier, summarise
from hospitality_elt.pipeline import new_run_id, run_entity
from hospitality_elt.reconcile import WAREHOUSE_DAILY_SALES_SQL, compare_daily_sales
from hospitality_elt.secrets import SecretProvider, build_secret_provider
from hospitality_elt.sources.base import Source
from hospitality_elt.sources.inventory_sftp import (
    LocalFileStore,
    SftpFileStore,
    SftpInventorySource,
)
from hospitality_elt.sources.pos import PosApiSource
from hospitality_elt.sources.workforce import WorkforceApiSource
from hospitality_elt.storage import GcsLanding, LocalLanding
from hospitality_elt.warehouse import BigQueryWarehouse, LocalWarehouse, RunRecord

log = logging.getLogger("hospitality_elt")

SOURCES = ("pos", "workforce", "inventory")
TRANSFORM_DIR = Path(os.environ.get("DBT_PROJECT_DIR", Path(__file__).parents[2] / "transform"))


def build_source(name: str, settings: Settings, secrets: SecretProvider) -> Source:
    if name == "pos":
        oauth = OAuth2ClientCredentials(
            token_url=f"{settings.pos_base_url}/oauth/token",
            client_id=secrets.get("pos-client-id"),
            client_secret=secrets.get("pos-client-secret"),
        )
        return PosApiSource(ApiClient(settings.pos_base_url, oauth=oauth))
    if name == "workforce":
        client = ApiClient(settings.workforce_base_url, api_key=secrets.get("workforce-api-key"))
        return WorkforceApiSource(client)
    if name == "inventory":
        if settings.is_local:
            store = LocalFileStore(os.environ.get("LOCAL_SFTP_DIR", "mock_sources/sftp_drop"))
        else:
            store = SftpFileStore(
                host=settings.sftp_host,
                port=settings.sftp_port,
                username=settings.sftp_username,
                private_key=secrets.get("sftp-private-key"),
                known_host_key=secrets.get("sftp-host-key"),
                directory=settings.sftp_inventory_dir,
            )
        return SftpInventorySource(store)
    raise ValueError(f"Unknown source {name}")


def _targets(settings: Settings):
    """Local runs write to files unless WAREHOUSE=bigquery, which loads the mock data
    into a real BigQuery project (landing files stay on disk). Cloud runs use GCS + BigQuery."""
    if settings.is_local:
        root = Path(settings.local_data_dir)
        landing = LocalLanding(root / "landing")
        if os.environ.get("WAREHOUSE", "local") == "bigquery":
            wh = BigQueryWarehouse(settings.project_id, settings.region, settings.ops_dataset)
            return wh, landing
        return LocalWarehouse(root / "warehouse"), landing
    return (
        BigQueryWarehouse(settings.project_id, settings.region, settings.ops_dataset),
        GcsLanding(settings.landing_bucket),
    )


def cmd_ingest(
    settings: Settings,
    secrets: SecretProvider,
    sources: list[str],
    since: str | None,
    entity: str | None = None,
) -> list[RunRecord]:
    warehouse, landing = _targets(settings)
    pii_key = secrets.get("pii-hmac-key")
    run_id = new_run_id()
    runs: list[RunRecord] = []
    for name in sources:
        try:
            source = build_source(name, settings, secrets)
        except Exception as exc:  # noqa: BLE001 - one broken source must not stop the others
            log.error(
                "source setup failed",
                extra={"event": "ingestion_failed", "source": name},
                exc_info=True,
            )
            runs.append(
                RunRecord(
                    run_id=run_id,
                    source=name,
                    entity="*",
                    status="failed",
                    started_at=datetime.now(UTC).isoformat(),
                    error=str(exc),
                )
            )
            continue
        try:
            for ent in source.entities:
                if entity and ent != entity:
                    continue
                runs.append(
                    run_entity(
                        source,
                        ent,
                        warehouse=warehouse,
                        landing=landing,
                        pii_key=pii_key,
                        run_id=run_id,
                        lookback_hours=settings.lookback_hours,
                        max_reject_ratio=settings.max_reject_ratio,
                        since_override=since,
                    )
                )
        finally:
            source.close()
    return runs


def cmd_transform(target: str) -> bool:
    cmd = [
        "dbt",
        "build",
        "--target",
        target,
        "--project-dir",
        str(TRANSFORM_DIR),
        "--profiles-dir",
        str(TRANSFORM_DIR),
    ]
    log.info("dbt build started", extra={"event": "dbt_started", "cmd": " ".join(cmd)})
    ok = subprocess.run(cmd, check=False).returncode == 0  # noqa: S603
    if not ok:
        log.error("dbt build failed", extra={"event": "dbt_failed"})
    return ok


def cmd_reconcile(settings: Settings, secrets: SecretProvider, business_date: str) -> list[str]:
    """Returns human-readable lines describing any mismatches."""
    if settings.is_local:
        log.info("reconciliation needs BigQuery marts; skipped locally")
        return []
    pos = build_source("pos", settings, secrets)
    if not isinstance(pos, PosApiSource):
        raise TypeError("reconciliation requires the POS source")
    source_rows = pos.daily_sales_report(business_date)
    pos.close()
    wh = BigQueryWarehouse(settings.project_id, settings.region, settings.ops_dataset)
    sql = WAREHOUSE_DAILY_SALES_SQL.format(project=settings.project_id)
    warehouse_rows = wh.query(sql, business_date=business_date)
    results = compare_daily_sales(business_date, source_rows, warehouse_rows)
    wh.insert_ops_rows(
        "reconciliation_results",
        [
            {**{k: str(v) for k, v in asdict(r).items()}, "within_tolerance": r.within_tolerance}
            for r in results
        ],
    )
    bad = [r for r in results if not r.within_tolerance]
    for r in bad:
        log.error(
            "reconciliation mismatch",
            extra={"event": "reconciliation_mismatch", **{k: str(v) for k, v in asdict(r).items()}},
        )
    return [
        f"⚠️ {r.pos_location_id} {r.metric}: source {r.source_value} vs "
        f"warehouse {r.warehouse_value}"
        for r in bad
    ]


def cmd_serve_webhooks(settings: Settings, secrets: SecretProvider) -> None:
    import uvicorn

    from hospitality_elt.webhooks import create_app

    _, landing = _targets(settings)
    app = create_app({"pos": secrets.get("webhook-secret-pos")}, landing)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))  # noqa: S104


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hospitality-elt")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--source", choices=[*SOURCES, "all"], default="all")
    p_ing.add_argument("--entity", help="limit to one entity, e.g. transactions")
    p_ing.add_argument("--since", help="ISO-8601 timestamp; overrides the watermark (backfill)")

    p_tr = sub.add_parser("transform")
    p_tr.add_argument("--target", default=os.environ.get("DBT_TARGET", "dev"))

    p_rec = sub.add_parser("reconcile")
    p_rec.add_argument("--date", required=True)

    p_daily = sub.add_parser("daily")
    p_daily.add_argument("--skip-transform", action="store_true")
    p_daily.add_argument("--target", default=os.environ.get("DBT_TARGET", "prod"))

    sub.add_parser("serve-webhooks")

    args = parser.parse_args(argv)
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    settings = Settings.from_env()
    secrets = build_secret_provider(settings.environment, settings.project_id)

    if args.command == "ingest":
        sources = list(SOURCES) if args.source == "all" else [args.source]
        runs = cmd_ingest(settings, secrets, sources, args.since, args.entity)
        print(summarise(runs))
        return 1 if any(r.status == "failed" for r in runs) else 0

    if args.command == "transform":
        return 0 if cmd_transform(args.target) else 1

    if args.command == "reconcile":
        issues = cmd_reconcile(settings, secrets, args.date)
        print("\n".join(issues) or "Reconciliation passed")
        return 1 if issues else 0

    if args.command == "serve-webhooks":
        cmd_serve_webhooks(settings, secrets)
        return 0

    # daily
    runs = cmd_ingest(settings, secrets, list(SOURCES), None)
    extra: list[str] = []
    transform_ok = True
    if not args.skip_transform:
        transform_ok = cmd_transform(args.target)
        extra.append(
            "✅ dbt build passed" if transform_ok else "❌ dbt build failed (tests or models)"
        )
    if transform_ok and not settings.is_local:
        yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        extra.extend(cmd_reconcile(settings, secrets, yesterday) or ["✅ Reconciliation passed"])

    try:
        webhook_url = secrets.get("alert-webhook-url")
    except Exception:  # noqa: BLE001 - optional secret
        webhook_url = None
    WebhookNotifier(webhook_url).send(summarise(runs, extra))
    failed = any(r.status == "failed" for r in runs) or not transform_ok
    failed = failed or any(line.startswith("⚠️") for line in extra)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
