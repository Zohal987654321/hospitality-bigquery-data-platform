import json

from fastapi.testclient import TestClient

from hospitality_elt.storage import LocalLanding
from hospitality_elt.webhooks import create_app, sign

SECRET = "whsec"
NOW = 1_800_000_000


def _client(tmp_path):
    app = create_app({"pos": SECRET}, LocalLanding(tmp_path), clock=lambda: NOW)
    return TestClient(app)


def _post(client, body: bytes, ts: int, signature: str | None = None):
    sig = signature or sign(SECRET, str(ts), body)
    return client.post(
        "/webhooks/pos", content=body, headers={"X-Signature": sig, "X-Timestamp": str(ts)}
    )


def test_valid_event_is_landed(tmp_path):
    body = json.dumps({"event_id": "evt_1", "type": "transaction.updated"}).encode()
    resp = _post(_client(tmp_path), body, NOW)
    assert resp.status_code == 202
    assert list(tmp_path.rglob("evt_1.jsonl.gz"))


def test_bad_signature_is_rejected(tmp_path):
    resp = _post(_client(tmp_path), b"{}", NOW, signature="sha256=deadbeef")
    assert resp.status_code == 401


def test_replayed_old_event_is_rejected(tmp_path):
    body = b'{"event_id": "evt_2"}'
    resp = _post(_client(tmp_path), body, NOW - 3600)
    assert resp.status_code == 401
    assert not list(tmp_path.rglob("*.gz"))


def test_unknown_source_404(tmp_path):
    resp = _client(tmp_path).post(
        "/webhooks/other", content=b"{}", headers={"X-Signature": "x", "X-Timestamp": str(NOW)}
    )
    assert resp.status_code == 404
