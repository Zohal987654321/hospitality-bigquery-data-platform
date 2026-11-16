"""Inventory system scheduled exports, delivered as CSV files over SFTP.

File names carry the export timestamp (``stock_counts_20261116T0300.csv``), which
is used as the watermark: each run processes files newer than the last one loaded
(minus the lookback window — reprocessing is safe because staging dedupes).
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from hospitality_elt.schemas import InventoryStockCount
from hospitality_elt.sources.base import EntitySpec, Source

FILE_PATTERN = re.compile(r"^stock_counts_(\d{8}T\d{4})\.csv$")


class FileStore(Protocol):
    def list_files(self) -> list[str]: ...
    def read_text(self, name: str) -> str: ...


class LocalFileStore:
    """Used for local demos and tests (a folder standing in for the SFTP drop)."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)

    def list_files(self) -> list[str]:
        return sorted(p.name for p in self._dir.glob("*.csv"))

    def read_text(self, name: str) -> str:
        return (self._dir / name).read_text(encoding="utf-8-sig")


class SftpFileStore:
    """Key-based SFTP. Host key is pinned (no auto-accept)."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        private_key: str,
        known_host_key: str,
        directory: str,
    ) -> None:
        import paramiko

        key = paramiko.Ed25519Key.from_private_key(io.StringIO(private_key))
        self._transport = paramiko.Transport((host, port))
        host_key_type, host_key_b64 = known_host_key.split()[:2]
        expected = paramiko.PKey.from_type_string(host_key_type, _b64(host_key_b64))
        self._transport.connect(username=username, pkey=key, hostkey=expected)
        self._sftp = paramiko.SFTPClient.from_transport(self._transport)
        self._dir = directory.rstrip("/")

    def list_files(self) -> list[str]:
        return sorted(self._sftp.listdir(self._dir))

    def read_text(self, name: str) -> str:
        with self._sftp.open(f"{self._dir}/{name}", "r") as fh:
            return fh.read().decode("utf-8-sig")

    def close(self) -> None:
        self._sftp.close()
        self._transport.close()


def _b64(value: str) -> bytes:
    import base64

    return base64.b64decode(value)


def export_time(file_name: str) -> datetime | None:
    match = FILE_PATTERN.match(file_name)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%dT%H%M").replace(tzinfo=UTC)


class SftpInventorySource(Source):
    name = "inventory"
    entities = {
        "stock_counts": EntitySpec(
            name="stock_counts",
            contract=InventoryStockCount,
            key_fields=("location_code", "sku", "counted_on"),
            updated_field="exported_at",
        )
    }

    def __init__(self, store: FileStore) -> None:
        self._store = store

    def extract(self, entity: str, since: str | None) -> Iterator[dict[str, Any]]:
        since_dt = datetime.fromisoformat(since) if since else None
        for name in self._store.list_files():
            exported = export_time(name)
            if exported is None or (since_dt and exported < since_dt):
                continue
            reader = csv.DictReader(io.StringIO(self._store.read_text(name)))
            for row in reader:
                record = {k.strip().lower(): (v.strip() if v else v) for k, v in row.items()}
                record["exported_at"] = exported.isoformat()
                record["source_file"] = name
                yield record

    def close(self) -> None:
        if hasattr(self._store, "close"):
            self._store.close()
