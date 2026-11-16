"""Failure notifications.

Two independent paths, so a broken chat webhook can't hide a failure:
1. Every failure is logged at ERROR with ``event=ingestion_failed`` — a log-based
   metric + Cloud Monitoring alert policy emails the on-call address.
2. A run summary is posted to a Google Chat / Slack / Teams incoming webhook
   (all accept ``{"text": ...}``), URL stored in Secret Manager.
"""

from __future__ import annotations

import logging

import httpx

from hospitality_elt.warehouse import RunRecord

log = logging.getLogger(__name__)


def summarise(runs: list[RunRecord], extra_lines: list[str] | None = None) -> str:
    failed = [r for r in runs if r.status == "failed"]
    header = "❌ Daily data load FAILED" if failed else "✅ Daily data load succeeded"
    lines = [header]
    for r in runs:
        lines.append(
            f"• {r.source}.{r.entity}: {r.status} — loaded {r.loaded}, "
            f"rejected {r.rejected}, dupes {r.duplicates_removed}"
            + (f" — {r.error}" if r.error else "")
        )
    lines.extend(extra_lines or [])
    return "\n".join(lines)


class WebhookNotifier:
    def __init__(self, url: str | None) -> None:
        self._url = url

    def send(self, text: str) -> None:
        if not self._url:
            log.info(
                "notification (no webhook configured)", extra={"event": "notify", "text": text}
            )
            return
        try:
            httpx.post(self._url, json={"text": text}, timeout=10).raise_for_status()
        except httpx.HTTPError:
            log.exception("notification webhook failed", extra={"event": "notify_failed"})
