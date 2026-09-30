"""Configurazione applicativa (env-driven)."""
from __future__ import annotations

import os


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL", "postgresql+psycopg://vcm:vcm@localhost:5432/vcm")
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.storage_dir = os.getenv("STORAGE_DIR", "/var/lib/vcm/uploads")
        self.reports_dir = os.getenv("REPORTS_DIR", "/var/lib/vcm/reports")
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "2048"))
        self.ingest_batch_size = int(os.getenv("INGEST_BATCH_SIZE", "500"))
        self.default_match_key = os.getenv("DEFAULT_MATCH_KEY", "ip")


settings = Settings()
