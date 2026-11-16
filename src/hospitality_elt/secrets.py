"""Credential lookup.

Cloud runs read from Google Secret Manager using the job's service account
(granted ``roles/secretmanager.secretAccessor`` on named secrets only — see
``infra/terraform/secrets.tf``). Local runs read env vars so no cloud access is
needed for development. Secret values are never logged.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Protocol


class SecretProvider(Protocol):
    def get(self, name: str) -> str: ...


class EnvSecretProvider:
    """``pos-client-secret`` -> env var ``POS_CLIENT_SECRET``."""

    def get(self, name: str) -> str:
        key = name.upper().replace("-", "_")
        try:
            return os.environ[key]
        except KeyError as exc:
            raise RuntimeError(f"Secret {name!r} not set (expected env var {key})") from exc


class GcpSecretProvider:
    def __init__(self, project_id: str) -> None:
        from google.cloud import secretmanager

        self._client = secretmanager.SecretManagerServiceClient()
        self._project_id = project_id

    @lru_cache(maxsize=64)  # noqa: B019 - provider lives for one job execution
    def get(self, name: str) -> str:
        path = f"projects/{self._project_id}/secrets/{name}/versions/latest"
        response = self._client.access_secret_version(request={"name": path})
        return response.payload.data.decode("utf-8")


def build_secret_provider(environment: str, project_id: str) -> SecretProvider:
    if environment == "local":
        return EnvSecretProvider()
    return GcpSecretProvider(project_id)
