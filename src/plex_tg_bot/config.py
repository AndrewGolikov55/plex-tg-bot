from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False, extra="ignore")

    # Required
    telegram_bot_token: str
    admin_chat_id: int
    plex_token: str

    # Plex
    plex_server_name: str | None = None
    plex_machine_identifier: str | None = None

    # Overseerr (optional pair)
    overseerr_public_url: str | None = None
    overseerr_api_key: str | None = None

    # UX
    watch_url: str = "https://app.plex.tv/desktop/"
    apps_markdown_path: str = "/data/apps.md"

    # Storage
    db_path: str = "/data/db.sqlite"

    # Locale
    bot_lang: Literal["en", "ru"] = "en"

    # Networking
    proxy_url: str | None = None
    no_proxy: str = "localhost,127.0.0.1"

    # HTTP server
    health_port: int = 9095

    # Logging
    log_level: str = "INFO"

    # Scheduler
    daily_sync_cron: str = "0 4 * * *"

    # Plex share policy
    shared_library_ids: list[int] = Field(default_factory=list)
    allow_sync: str = "1"
    allow_camera_upload: str = "0"
    allow_channels: str = "0"

    @field_validator("shared_library_ids", mode="before")
    @classmethod
    def _parse_lib_ids(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if not v or v == "[]":
                return []
            return [int(x) for x in v.strip("[]").split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def _overseerr_pair(self) -> Settings:
        if self.overseerr_public_url and not self.overseerr_api_key:
            raise ValueError("OVERSEERR_API_KEY is required when OVERSEERR_PUBLIC_URL is set")
        return self

    @property
    def overseerr_enabled(self) -> bool:
        return bool(self.overseerr_public_url and self.overseerr_api_key)
