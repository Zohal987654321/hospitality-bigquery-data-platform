"""Protection of sensitive employee, customer and financial fields.

Runs *before* anything is written to Cloud Storage or BigQuery, so raw layers never
hold direct identifiers.

Two layers:
1. Per-entity policy: fields to drop and fields to pseudonymise (HMAC-SHA256 with
   a secret key from Secret Manager — stable, so joins across systems still work,
   but not reversible without the key).
2. A deny-list scan of every key, at any nesting depth, that drops anything that
   looks like contact, identity or banking data — defence in depth when a vendor
   adds a field without notice.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Any

DENYLIST_PATTERN = re.compile(
    r"(e_?mail|phone|mobile|address|street|postcode|post_code|date_of_birth|\bdob\b|birth"
    r"|tax_file|\btfn\b|abn|bank|bsb|account_number|iban|card_number|pan\b|cvv|card_last"
    r"|medicare|passport|licen[cs]e_number|emergency_contact|password|first_name|last_name"
    r"|full_name|given_name|surname|super_fund|member_number)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PiiPolicy:
    drop: frozenset[str] = field(default_factory=frozenset)
    pseudonymise: frozenset[str] = field(default_factory=frozenset)
    # Explicitly allowed keys that would otherwise match the deny-list.
    allow: frozenset[str] = field(default_factory=frozenset)


def pseudonymise(value: Any, key: str) -> str | None:
    if value is None or value == "":
        return None
    digest = hmac.new(key.encode(), str(value).encode(), hashlib.sha256).hexdigest()
    return digest[:32]


def _scrub(obj: Any, allow: frozenset[str], removed: set[str], path: str = "") -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            full = f"{path}.{k}" if path else k
            if k not in allow and DENYLIST_PATTERN.search(k):
                removed.add(full)
                continue
            out[k] = _scrub(v, allow, removed, full)
        return out
    if isinstance(obj, list):
        return [_scrub(v, allow, removed, path) for v in obj]
    return obj


def apply_policy(
    record: dict[str, Any], policy: PiiPolicy, key: str
) -> tuple[dict[str, Any], set[str]]:
    """Return a protected copy of ``record`` and the set of removed field paths."""
    removed: set[str] = set()
    clean = {k: v for k, v in record.items() if k not in policy.drop}
    removed.update(k for k in record if k in policy.drop)
    for name in policy.pseudonymise:
        if name in clean:
            clean[name] = pseudonymise(clean[name], key)
    clean = _scrub(clean, policy.allow | policy.pseudonymise, removed)
    return clean, removed
