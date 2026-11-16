"""Runtime settings, read from environment variables.

Nothing secret lives here. Credentials are resolved at runtime through
``secrets.SecretProvider`` (Google Secret Manager in the cloud, env vars locally).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    environment: str  # "local" | "dev" | "prod"
    project_id: str
    region: str
    landing_bucket: str
    ops_dataset: str
    lookback_hours: int
    max_reject_ratio: float

    pos_base_url: str
    workforce_base_url: str

    sftp_host: str
    sftp_port: int
    sftp_username: str
    sftp_inventory_dir: str

    local_data_dir: str

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @classmethod
    def from_env(cls) -> Settings:
        environment = _env("HOSPITALITY_ENV", "local")
        return cls(
            environment=environment,
            project_id=_env("GCP_PROJECT_ID", "local-project"),
            region=_env("GCP_REGION", "australia-southeast1"),
            landing_bucket=_env("LANDING_BUCKET", "local-landing"),
            ops_dataset=_env("OPS_DATASET", "ops"),
            lookback_hours=int(_env("INCREMENTAL_LOOKBACK_HOURS", "48")),
            max_reject_ratio=float(_env("MAX_REJECT_RATIO", "0.05")),
            pos_base_url=_env("POS_BASE_URL", "http://127.0.0.1:8080/pos"),
            workforce_base_url=_env("WORKFORCE_BASE_URL", "http://127.0.0.1:8080/workforce"),
            sftp_host=_env("SFTP_HOST", ""),
            sftp_port=int(_env("SFTP_PORT", "22")),
            sftp_username=_env("SFTP_USERNAME", ""),
            sftp_inventory_dir=_env("SFTP_INVENTORY_DIR", "/exports/inventory"),
            local_data_dir=_env("LOCAL_DATA_DIR", ".local"),
        )
