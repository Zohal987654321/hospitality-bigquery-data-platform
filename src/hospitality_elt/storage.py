"""Landing zone: every batch is written to Cloud Storage before it is loaded.

Keeping the exact extracted file means any load can be replayed or audited, and
BigQuery loads come from a durable copy rather than from memory.

Layout: ``gs://<bucket>/<source>/<entity>/ingest_date=YYYY-MM-DD/<run_id>.jsonl.gz``
Rejected records go to ``rejected/<source>/<entity>/...`` with their errors.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Protocol


def to_ndjson_gz(records: list[dict[str, Any]]) -> bytes:
    body = "\n".join(json.dumps(r, default=str, sort_keys=True) for r in records)
    return gzip.compress(body.encode("utf-8"))


class Landing(Protocol):
    def write(self, path: str, records: list[dict[str, Any]]) -> str: ...


class GcsLanding:
    def __init__(self, bucket: str) -> None:
        from google.cloud import storage

        self._bucket = storage.Client().bucket(bucket)
        self._name = bucket

    def write(self, path: str, records: list[dict[str, Any]]) -> str:
        blob = self._bucket.blob(path)
        blob.content_encoding = "gzip"
        blob.upload_from_string(to_ndjson_gz(records), content_type="application/x-ndjson")
        return f"gs://{self._name}/{path}"


class LocalLanding:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def write(self, path: str, records: list[dict[str, Any]]) -> str:
        target = self._root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(to_ndjson_gz(records))
        return str(target)
