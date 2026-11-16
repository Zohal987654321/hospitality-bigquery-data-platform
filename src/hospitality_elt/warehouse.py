"""BigQuery raw layer, ingestion state and run log.

Raw tables (``raw_<source>.<entity>``) are append-only and schema-on-read: each row
holds load metadata plus the protected source record as a JSON ``payload``. Vendor
schema changes therefore never fail a load; dbt staging models pick the fields
they need and dedupe to the latest version of each record.

Idempotency: a load first deletes any rows with the same ``_run_id``, so retrying
a failed or partial run never duplicates data.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

_IDENT = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def safe_ident(value: str) -> str:
    if not _IDENT.match(value):
        raise ValueError(f"Unsafe identifier: {value!r}")
    return value


RAW_SCHEMA = [
    ("_run_id", "STRING", "REQUIRED"),
    ("_ingested_at", "TIMESTAMP", "REQUIRED"),
    ("_source", "STRING", "REQUIRED"),
    ("_entity", "STRING", "REQUIRED"),
    ("_record_key", "STRING", "REQUIRED"),
    ("_record_hash", "STRING", "REQUIRED"),
    ("_source_updated_at", "TIMESTAMP", "NULLABLE"),
    ("_landing_uri", "STRING", "NULLABLE"),
    ("payload", "STRING", "REQUIRED"),  # JSON text; read with JSON_VALUE in dbt
]


@dataclass
class RunRecord:
    run_id: str
    source: str
    entity: str
    status: str  # "success" | "failed" | "skipped"
    started_at: str
    finished_at: str | None = None
    extracted: int = 0
    loaded: int = 0
    rejected: int = 0
    duplicates_removed: int = 0
    pii_fields_removed: str = ""
    watermark_from: str | None = None
    watermark_to: str | None = None
    landing_uri: str | None = None
    error: str | None = None


def build_raw_rows(
    records: list[dict[str, Any]],
    *,
    run_id: str,
    source: str,
    entity: str,
    key_fields: tuple[str, ...],
    updated_field: str,
    landing_uri: str | None,
    ingested_at: datetime | None = None,
) -> list[dict[str, Any]]:
    ingested = (ingested_at or datetime.now(UTC)).isoformat()
    rows = []
    for r in records:
        payload = json.dumps(r, default=str, sort_keys=True)
        rows.append(
            {
                "_run_id": run_id,
                "_ingested_at": ingested,
                "_source": source,
                "_entity": entity,
                "_record_key": "|".join(str(r[k]) for k in key_fields),
                "_record_hash": hashlib.sha256(payload.encode()).hexdigest(),
                "_source_updated_at": str(r.get(updated_field)) if r.get(updated_field) else None,
                "_landing_uri": landing_uri,
                "payload": payload,
            }
        )
    return rows


class Warehouse(Protocol):
    def get_watermark(self, source: str, entity: str) -> str | None: ...
    def set_watermark(self, source: str, entity: str, value: str, run_id: str) -> None: ...
    def load_raw(
        self, source: str, entity: str, rows: list[dict[str, Any]], run_id: str
    ) -> int: ...
    def record_run(self, run: RunRecord) -> None: ...


class BigQueryWarehouse:
    def __init__(self, project_id: str, location: str, ops_dataset: str = "ops") -> None:
        from google.cloud import bigquery

        self._bq = bigquery
        self._client = bigquery.Client(project=project_id, location=location)
        self._project = project_id
        self._ops = safe_ident(ops_dataset)

    # ---- state ----
    def get_watermark(self, source: str, entity: str) -> str | None:
        sql = f"""
            select watermark_value
            from `{self._project}.{self._ops}.ingestion_watermarks`
            where source = @source and entity = @entity
        """
        job = self._client.query(sql, job_config=self._params(source=source, entity=entity))
        rows = list(job.result())
        return rows[0].watermark_value if rows else None

    def set_watermark(self, source: str, entity: str, value: str, run_id: str) -> None:
        sql = f"""
            merge `{self._project}.{self._ops}.ingestion_watermarks` t
            using (select @source as source, @entity as entity) s
            on t.source = s.source and t.entity = s.entity
            when matched then update set
                watermark_value = @value, run_id = @run_id, updated_at = current_timestamp()
            when not matched then insert (source, entity, watermark_value, run_id, updated_at)
                values (@source, @entity, @value, @run_id, current_timestamp())
        """
        cfg = self._params(source=source, entity=entity, value=value, run_id=run_id)
        self._client.query(sql, job_config=cfg).result()

    # ---- raw load ----
    def load_raw(self, source: str, entity: str, rows: list[dict[str, Any]], run_id: str) -> int:
        bq = self._bq
        table_id = f"{self._project}.raw_{safe_ident(source)}.{safe_ident(entity)}"
        schema = [bq.SchemaField(n, t, mode=m) for n, t, m in RAW_SCHEMA]
        table = bq.Table(table_id, schema=schema)
        table.time_partitioning = bq.TimePartitioning(field="_ingested_at")
        table.clustering_fields = ["_record_key"]
        self._client.create_table(table, exists_ok=True)

        # Idempotent re-run: remove anything a previous attempt of this run loaded.
        self._client.query(
            f"delete from `{table_id}` where _run_id = @run_id "
            f"and _ingested_at >= timestamp_sub(current_timestamp(), interval 7 day)",
            job_config=self._params(run_id=run_id),
        ).result()

        job_config = bq.LoadJobConfig(
            schema=schema,
            source_format=bq.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bq.WriteDisposition.WRITE_APPEND,
        )
        job = self._client.load_table_from_json(rows, table_id, job_config=job_config)
        job.result()
        return int(job.output_rows or 0)

    def record_run(self, run: RunRecord) -> None:
        errors = self._client.insert_rows_json(
            f"{self._project}.{self._ops}.ingestion_runs", [asdict(run)]
        )
        if errors:
            raise RuntimeError(f"Failed to write run log: {errors}")

    def insert_ops_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        errors = self._client.insert_rows_json(
            f"{self._project}.{self._ops}.{safe_ident(table)}", rows
        )
        if errors:
            raise RuntimeError(f"Failed to write {table}: {errors}")

    def query(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        job = self._client.query(sql, job_config=self._params(**params))
        return [dict(r) for r in job.result()]

    def _params(self, **params: Any):
        bq = self._bq
        return bq.QueryJobConfig(
            query_parameters=[bq.ScalarQueryParameter(k, "STRING", v) for k, v in params.items()]
        )


class LocalWarehouse:
    """File-backed stand-in for BigQuery: lets the whole pipeline run on a laptop."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._state = self._root / "ops_ingestion_watermarks.json"

    def _read_state(self) -> dict[str, Any]:
        return json.loads(self._state.read_text()) if self._state.exists() else {}

    def get_watermark(self, source: str, entity: str) -> str | None:
        entry = self._read_state().get(f"{source}.{entity}")
        return entry["watermark_value"] if entry else None

    def set_watermark(self, source: str, entity: str, value: str, run_id: str) -> None:
        state = self._read_state()
        state[f"{source}.{entity}"] = {"watermark_value": value, "run_id": run_id}
        self._state.write_text(json.dumps(state, indent=2))

    def raw_path(self, source: str, entity: str) -> Path:
        return self._root / f"raw_{source}" / f"{entity}.jsonl"

    def load_raw(self, source: str, entity: str, rows: list[dict[str, Any]], run_id: str) -> int:
        path = self.raw_path(source, entity)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if path.exists():
            existing = [
                line
                for line in path.read_text().splitlines()
                if json.loads(line)["_run_id"] != run_id
            ]
        new = [json.dumps(r, default=str) for r in rows]
        path.write_text("\n".join(existing + new) + "\n")
        return len(rows)

    def record_run(self, run: RunRecord) -> None:
        with (self._root / "ops_ingestion_runs.jsonl").open("a") as fh:
            fh.write(json.dumps(asdict(run)) + "\n")
