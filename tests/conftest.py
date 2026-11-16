from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from mock_sources import app as mock_app


@pytest.fixture(scope="session")
def mock_client() -> TestClient:
    return TestClient(mock_app.app)


@pytest.fixture
def mock_transport(mock_client: TestClient) -> httpx.MockTransport:
    """Routes httpx requests from the real ApiClient into the in-process mock APIs."""

    def handler(request: httpx.Request) -> httpx.Response:
        resp = mock_client.request(
            request.method,
            request.url.raw_path.decode(),
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            content=request.content,
        )
        return httpx.Response(resp.status_code, headers=resp.headers, content=resp.content)

    return httpx.MockTransport(handler)
