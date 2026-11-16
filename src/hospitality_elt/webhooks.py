"""Webhook receiver (deployed as a Cloud Run service).

Vendors push near-real-time events (e.g. "transaction updated"). Each request is
authenticated with an HMAC-SHA256 signature over ``timestamp.body`` and rejected if
older than five minutes (replay protection). Accepted events are written as-is to
the landing bucket; a BigQuery external table over that prefix exposes them and
the next scheduled pull picks up the full records.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable

from fastapi import FastAPI, Header, HTTPException, Request

from hospitality_elt.storage import Landing

MAX_SKEW_SECONDS = 300


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def verify(secret: str, timestamp: str, body: bytes, signature: str, now: float) -> bool:
    try:
        if abs(now - int(timestamp)) > MAX_SKEW_SECONDS:
            return False
    except ValueError:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature)


def create_app(
    secrets_by_source: dict[str, str],
    landing: Landing,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    app = FastAPI(title="Hospitality webhook receiver", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/{source}", status_code=202)
    async def receive(
        source: str,
        request: Request,
        x_signature: str = Header(...),
        x_timestamp: str = Header(...),
    ) -> dict[str, str]:
        secret = secrets_by_source.get(source)
        if secret is None:
            raise HTTPException(status_code=404, detail="unknown source")
        body = await request.body()
        if not verify(secret, x_timestamp, body, x_signature, clock()):
            raise HTTPException(status_code=401, detail="invalid signature")
        try:
            event = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid json") from exc

        event_id = str(event.get("event_id") or uuid.uuid4())
        day = time.strftime("%Y-%m-%d", time.gmtime(clock()))
        landing.write(
            f"webhooks/{source}/event_date={day}/{event_id}.jsonl.gz",
            [{"event_id": event_id, "received_at": clock(), "event": event}],
        )
        return {"status": "accepted", "event_id": event_id}

    return app
