import httpx
import pytest

from hospitality_elt.http import ApiClient, OAuth2ClientCredentials, RetryableHTTPError
from hospitality_elt.sources.pos import PosApiSource


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # tenacity sleeps between attempts; tests shouldn't wait.
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _s: None)


def test_retries_transient_errors_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = ApiClient("https://api.test", transport=httpx.MockTransport(handler))
    assert client.get_json("/x") == {"ok": True}
    assert calls["n"] == 3


def test_gives_up_after_max_attempts():
    client = ApiClient(
        "https://api.test",
        max_attempts=2,
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),
    )
    with pytest.raises(RetryableHTTPError):
        client.get_json("/x")


def test_does_not_retry_client_errors():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404)

    client = ApiClient("https://api.test", transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        client.get_json("/x")
    assert calls["n"] == 1


def test_oauth_token_is_cached_and_refreshed_on_401():
    tokens = iter(["tok1", "tok2"])
    seen = []

    def handler(request):
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": next(tokens), "expires_in": 3600})
        seen.append(request.headers["Authorization"])
        if request.headers["Authorization"] == "Bearer tok1" and len(seen) == 2:
            return httpx.Response(401)  # token revoked mid-run
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    oauth = OAuth2ClientCredentials(
        "https://api.test/oauth/token", "id", "secret", transport=transport
    )
    client = ApiClient("https://api.test", oauth=oauth, transport=transport)
    client.get_json("/a")
    client.get_json("/b")
    assert seen == ["Bearer tok1", "Bearer tok1", "Bearer tok2"]


def test_pos_source_follows_cursor_pagination(mock_transport):
    oauth = OAuth2ClientCredentials(
        "http://mock/pos/oauth/token", "demo-client", "demo-secret", transport=mock_transport
    )
    source = PosApiSource(
        ApiClient("http://mock/pos", oauth=oauth, transport=mock_transport), page_size=7
    )
    products = list(source.extract("products", since=None))
    assert len(products) == 25  # spans 4 pages
    assert len({p["product_id"] for p in products}) == 25
