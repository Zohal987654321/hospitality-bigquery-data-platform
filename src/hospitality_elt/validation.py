"""Batch validation and duplicate detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError


class DataQualityError(Exception):
    """Raised when a batch is too broken to load. The watermark is not advanced."""


@dataclass
class ValidationOutcome:
    valid: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    duplicates_removed: int = 0

    @property
    def reject_ratio(self) -> float:
        total = len(self.valid) + len(self.rejected) + self.duplicates_removed
        return len(self.rejected) / total if total else 0.0


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def validate_batch(
    records: list[dict[str, Any]],
    contract: type[BaseModel],
    key_fields: tuple[str, ...],
    updated_field: str,
) -> ValidationOutcome:
    """Validate each record against its contract and keep the latest version per key.

    Records are kept in their *original* (already PII-protected) shape so the raw
    layer is a faithful copy of the source; the contract only gates what gets in.
    """
    outcome = ValidationOutcome()
    latest: dict[tuple[str, ...], dict[str, Any]] = {}

    for record in records:
        try:
            contract.model_validate(record)
        except ValidationError as exc:
            errors = [
                {"loc": ".".join(map(str, e["loc"])), "msg": e["msg"]}
                for e in exc.errors(include_url=False, include_input=False)
            ]
            outcome.rejected.append({"record": record, "errors": errors})
            continue

        key = tuple(str(record[k]) for k in key_fields)
        current = latest.get(key)
        if current is None:
            latest[key] = record
            continue
        outcome.duplicates_removed += 1
        if _as_datetime(record[updated_field]) >= _as_datetime(current[updated_field]):
            latest[key] = record

    outcome.valid = list(latest.values())
    return outcome


def enforce_reject_threshold(outcome: ValidationOutcome, max_ratio: float, label: str) -> None:
    if outcome.reject_ratio > max_ratio:
        raise DataQualityError(
            f"{label}: {len(outcome.rejected)} rejected records "
            f"({outcome.reject_ratio:.1%}) exceeds limit {max_ratio:.1%}"
        )
