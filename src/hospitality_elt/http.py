"""HTTP client for third-party REST APIs.

* OAuth 2.0 client-credentials tokens, cached and refreshed before expiry
  (and once more on a 401).
* Retries with exponential backoff + jitter on 429, 5xx and network errors.
* Pluggable ``httpx`` transport so tests run without a network.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class RetryableHTTPError(Exception):
    pass


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, RetryableHTTPError | httpx.TransportError)


class OAuth2ClientCredentials:
    """Fetches and caches a bearer token using the client-credentials grant."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._transport = transport
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0

    def invalidate(self) -> None:
        self._token = None

    def token(self) -> str:
        if self._token and self._clock() < self._expires_at - 60:
            return self._token
        data = {"grant_type": "client_credentials"}
        if self._scope:
            data["scope"] = self._scope
        with httpx.Client(transport=self._transport, timeout=30) as client:
            resp = client.post(
                self._token_url, data=data, auth=(self._client_id, self._client_secret)
            )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._expires_at = self._clock() + int(payload.get("expires_in", 3600))
        log.info("oauth token refreshed", extra={"event": "oauth_token_refreshed"})
        return self._token


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        oauth: OAuth2ClientCredentials | None = None,
        api_key: str | None = None,
        api_key_header: str = "Authorization",
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        max_attempts: int = 5,
    ) -> None:
        self._oauth = oauth
        self._static_headers = {"Accept": "application/json"}
        if api_key:
            value = f"Bearer {api_key}" if api_key_header == "Authorization" else api_key
            self._static_headers[api_key_header] = value
        self._client = httpx.Client(base_url=base_url, transport=transport, timeout=timeout)
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = dict(self._static_headers)
        if self._oauth:
            headers["Authorization"] = f"Bearer {self._oauth.token()}"
        return headers

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        @retry(
            retry=retry_if_exception(_is_retryable),
            wait=wait_exponential_jitter(initial=1, max=30),
            stop=stop_after_attempt(self._max_attempts),
            reraise=True,
        )
        def _do() -> Any:
            resp = self._client.get(path, params=params, headers=self._headers())
            if resp.status_code == 401 and self._oauth:
                self._oauth.invalidate()
                raise RetryableHTTPError(f"401 from {path}; token refreshed")
            if resp.status_code in RETRYABLE_STATUS:
                log.warning(
                    "retryable http status",
                    extra={"event": "http_retry", "status": resp.status_code, "path": path},
                )
                raise RetryableHTTPError(f"{resp.status_code} from {path}")
            resp.raise_for_status()
            return resp.json()

        return _do()
