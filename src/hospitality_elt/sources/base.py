"""Source abstraction.

A source knows how to pull records for each of its entities changed since a
watermark. Everything else (PII protection, validation, landing, loading, state)
is shared in ``pipeline.py`` so adding a new system is one small class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from hospitality_elt.pii import PiiPolicy


@dataclass(frozen=True)
class EntitySpec:
    name: str
    contract: type[BaseModel]
    key_fields: tuple[str, ...]
    updated_field: str
    pii: PiiPolicy = PiiPolicy()


class Source(ABC):
    name: str
    entities: dict[str, EntitySpec]

    @abstractmethod
    def extract(self, entity: str, since: str | None) -> Iterator[dict[str, Any]]:
        """Yield records for ``entity`` modified at or after ``since`` (ISO-8601)."""

    def close(self) -> None:  # pragma: no cover - optional hook
        return None
