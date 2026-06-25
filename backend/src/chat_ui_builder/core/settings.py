from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8010"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    max_log_chars: int = int(os.getenv("MAX_LOG_CHARS", "1200"))


settings = Settings()
