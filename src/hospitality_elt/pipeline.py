"""The ingestion run for one source entity.

extract (since watermark - lookback)
  -> protect PII
  -> validate + dedupe            (reject file to GCS; fail if reject ratio too high)
  -> land batch in Cloud Storage
  -> load into BigQuery raw       (idempotent per run_id)
  -> advance watermark            (only after a successful load)
  -> write run log                (success or failure, always)
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from hospitality_elt.pii import apply_policy
from hospitality_elt.sources.base import Source
from hospitality_elt.storage import Landing
from hospitality_elt.validation import enforce_reject_threshold, validate_batch
from hospitality_elt.warehouse import RunRecord, Warehouse, build_raw_rows

log = logging.getLogger(__name__)


def new_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"{now:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"


def _parse_ts(value: str) -> datetime:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _minus_lookback(watermark: str, hours: int) -> str:
    return (_parse_ts(watermark) - timedelta(hours=hours)).isoformat()


def run_entity(
    source: Source,
    entity: str,
    *,
    warehouse: Warehouse,
    landing: Landing,
    pii_key: str,
    run_id: str,
    lookback_hours: int,
    max_reject_ratio: float,
    since_override: str | None = None,
) -> RunRecord:
    spec = source.entities[entity]
    now = datetime.now(UTC)
    run = RunRecord(
        run_id=run_id,
        source=source.name,
        entity=entity,
        status="failed",
        started_at=now.isoformat(),
    )
    ctx = {"run_id": run_id, "source": source.name, "entity": entity}

    try:
        previous = warehouse.get_watermark(source.name, entity)
        run.watermark_from = previous
        since = since_override or (_minus_lookback(previous, lookback_hours) if previous else None)
        log.info("extract started", extra={**ctx, "event": "extract_started", "since": since})

        extracted = list(source.extract(entity, since))
        run.extracted = len(extracted)

        protected, removed_fields = [], set()
        for record in extracted:
            clean, removed = apply_policy(record, spec.pii, pii_key)
            protected.append(clean)
            removed_fields |= removed
        run.pii_fields_removed = ",".join(sorted(removed_fields))

        outcome = validate_batch(protected, spec.contract, spec.key_fields, spec.updated_field)
        run.rejected = len(outcome.rejected)
        run.duplicates_removed = outcome.duplicates_removed

        date_part = f"ingest_date={now:%Y-%m-%d}"
        if outcome.rejected:
            landing.write(
                f"rejected/{source.name}/{entity}/{date_part}/{run_id}.jsonl.gz", outcome.rejected
            )
            log.warning(
                "records rejected",
                extra={**ctx, "event": "records_rejected", "count": len(outcome.rejected)},
            )
        enforce_reject_threshold(outcome, max_reject_ratio, f"{source.name}.{entity}")

        if not outcome.valid:
            run.status = "skipped"
            log.info("no new records", extra={**ctx, "event": "no_new_records"})
            return run

        run.landing_uri = landing.write(
            f"{source.name}/{entity}/{date_part}/{run_id}.jsonl.gz", outcome.valid
        )
        rows = build_raw_rows(
            outcome.valid,
            run_id=run_id,
            source=source.name,
            entity=entity,
            key_fields=spec.key_fields,
            updated_field=spec.updated_field,
            landing_uri=run.landing_uri,
            ingested_at=now,
        )
        run.loaded = warehouse.load_raw(source.name, entity, rows, run_id)

        new_watermark = max((str(r[spec.updated_field]) for r in outcome.valid), key=_parse_ts)
        if previous is None or _parse_ts(new_watermark) > _parse_ts(previous):
            warehouse.set_watermark(source.name, entity, new_watermark, run_id)
            run.watermark_to = new_watermark
        else:
            run.watermark_to = previous

        run.status = "success"
        log.info(
            "load complete",
            extra={
                **ctx,
                "event": "load_complete",
                "loaded": run.loaded,
                "rejected": run.rejected,
                "duplicates": run.duplicates_removed,
            },
        )
        return run
    except Exception as exc:  # noqa: BLE001 - recorded, reported, and surfaced by caller
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
        log.error("ingestion failed", extra={**ctx, "event": "ingestion_failed"}, exc_info=True)
        return run
    finally:
        run.finished_at = datetime.now(UTC).isoformat()
        try:
            warehouse.record_run(run)
        except Exception:  # noqa: BLE001
            log.exception("could not write run log", extra={**ctx, "event": "run_log_failed"})
