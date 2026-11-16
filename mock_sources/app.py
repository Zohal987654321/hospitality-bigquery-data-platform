"""Mock POS and workforce APIs, serving the synthetic dataset.

    uvicorn mock_sources.app:app --port 8080

POS:        OAuth2 client credentials, cursor pagination, ``updated_since`` filter
Workforce:  bearer API key, page-number pagination, ``updated_after`` filter
Set MOCK_FAILURE_RATE=0.2 to make 20% of data requests return 503 (to watch the
retry/backoff logic work).
"""

from __future__ import annotations

import base64
import os
import random
from datetime import date, datetime

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query

from mock_sources.generator import daily_sales_report, generate

DATA = generate()
CLIENT_ID, CLIENT_SECRET = "demo-client", "demo-secret"
WORKFORCE_KEY = "demo-workforce-key"
ISSUED_TOKENS: set[str] = set()
FAILURE_RATE = float(os.environ.get("MOCK_FAILURE_RATE", "0"))

app = FastAPI(title="Mock hospitality source systems")


def _maybe_fail() -> None:
    if FAILURE_RATE and random.random() < FAILURE_RATE:
        raise HTTPException(status_code=503, detail="temporarily unavailable")


def _since(rows: list[dict], since: str | None, field: str = "updated_at") -> list[dict]:
    if not since:
        return rows
    cutoff = datetime.fromisoformat(since.replace(" ", "+").replace("Z", "+00:00"))
    return [r for r in rows if datetime.fromisoformat(r[field]) >= cutoff]


# ---------------- POS ----------------
@app.post("/pos/oauth/token")
def token(grant_type: str = Form(...), authorization: str = Header(...)) -> dict:
    expected = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    if grant_type != "client_credentials" or authorization != f"Basic {expected}":
        raise HTTPException(status_code=401, detail="invalid_client")
    tok = f"tok_{random.getrandbits(64):x}"
    ISSUED_TOKENS.add(tok)
    return {"access_token": tok, "token_type": "bearer", "expires_in": 3600}


def pos_auth(authorization: str = Header(...)) -> None:
    if authorization.removeprefix("Bearer ") not in ISSUED_TOKENS:
        raise HTTPException(status_code=401, detail="invalid token")


def _cursor_page(rows: list[dict], cursor: str | None, limit: int) -> dict:
    start = int(cursor or 0)
    end = start + limit
    return {"data": rows[start:end], "next_cursor": str(end) if end < len(rows) else None}


@app.get("/pos/v1/transactions", dependencies=[Depends(pos_auth)])
def transactions(
    updated_since: str | None = None, cursor: str | None = None, limit: int = Query(200, le=500)
) -> dict:
    _maybe_fail()
    return _cursor_page(_since(DATA.transactions, updated_since), cursor, limit)


@app.get("/pos/v1/products", dependencies=[Depends(pos_auth)])
def products(updated_since: str | None = None, cursor: str | None = None, limit: int = 200) -> dict:
    return _cursor_page(_since(DATA.products, updated_since), cursor, limit)


@app.get("/pos/v1/locations", dependencies=[Depends(pos_auth)])
def locations(
    updated_since: str | None = None, cursor: str | None = None, limit: int = 200
) -> dict:
    return _cursor_page(_since(DATA.locations, updated_since), cursor, limit)


@app.get("/pos/v1/reports/daily-sales", dependencies=[Depends(pos_auth)])
def daily_sales(date_: str = Query(..., alias="date")) -> dict:
    return {"data": daily_sales_report(DATA, date.fromisoformat(date_))}


# ---------------- Workforce ----------------
def workforce_auth(authorization: str = Header(...)) -> None:
    if authorization != f"Bearer {WORKFORCE_KEY}":
        raise HTTPException(status_code=401, detail="invalid api key")


def _numbered_page(rows: list[dict], page: int, per_page: int) -> dict:
    total_pages = max(1, -(-len(rows) // per_page))
    start = (page - 1) * per_page
    return {"results": rows[start : start + per_page], "page": page, "total_pages": total_pages}


@app.get("/workforce/api/v2/employees", dependencies=[Depends(workforce_auth)])
def employees(updated_after: str | None = None, page: int = 1, per_page: int = 100) -> dict:
    return _numbered_page(_since(DATA.employees, updated_after), page, per_page)


@app.get("/workforce/api/v2/timesheets", dependencies=[Depends(workforce_auth)])
def timesheets(updated_after: str | None = None, page: int = 1, per_page: int = 100) -> dict:
    _maybe_fail()
    return _numbered_page(_since(DATA.shifts, updated_after), page, per_page)
