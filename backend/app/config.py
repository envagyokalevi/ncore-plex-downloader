"""Alkalmazás-konfiguráció – kizárólag környezeti változókból / .env fájlból.

Titkos adat (nCore / qBittorrent jelszó) soha nem kerül a frontendbe és
soha nem kerül logba – lásd `app.logging_setup.SecretFilter`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Alkalmazás ---
    app_env: Literal["production", "development", "test"] = "production"
    app_secret_key: str = "change-me"
    session_ttl_hours: int = 168
    cookie_secure: bool = False
    log_level: str = "INFO"

    # --- Belépés ---
    admin_username: str = "admin"
    admin_password_hash: str = ""
    extra_users: str = ""

    # --- nCore ---
    ncore_url: str = "https://ncore.pro"
    ncore_username: str = ""
    ncore_password: str = ""
    ncore_categories: str = "hd_hun"
    ncore_timeout: float = 20.0
    ncore_max_results: int = 50

    # --- qBittorrent ---
    qbittorrent_url: str = "http://qbittorrent:8080"
    qbittorrent_username: str = "admin"
    qbittorrent_password: str = ""
    qbittorrent_category: str = ""
    qbittorrent_timeout: float = 20.0

    # --- Média (csak tájékoztató jellegű, a compose mountokkal egyezik) ---
    plex_download_path: str = "/media/downloads"
    plex_movies_path: str = "/media/movies"

    # --- Tárolás ---
    database_path: str = "/data/app.db"

    # --- Statikus frontend (a Docker image-ben ide kerül a Vite build) ---
    static_dir: str = "/app/static"

    @field_validator("ncore_url", "qbittorrent_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def category_list(self) -> list[str]:
        """nCore kategóriák (`tipus` paraméter értékei) listaként."""
        return [c.strip() for c in self.ncore_categories.split(",") if c.strip()]

    @property
    def users(self) -> dict[str, str]:
        """felhasználónév -> bcrypt hash leképezés a környezeti változókból."""
        result: dict[str, str] = {}
        if self.admin_username and self.admin_password_hash:
            result[self.admin_username] = self.admin_password_hash
        for entry in self.extra_users.split(","):
            entry = entry.strip()
            if not entry or ":" not in entry:
                continue
            name, _, hashed = entry.partition(":")
            name, hashed = name.strip(), hashed.strip()
            if name and hashed:
                result[name] = hashed
        return result

    @property
    def secrets(self) -> list[str]:
        """Log-szűréshez: minden érték, ami soha nem jelenhet meg logban."""
        return [
            s
            for s in (
                self.ncore_password,
                self.qbittorrent_password,
                self.app_secret_key,
                self.admin_password_hash,
            )
            if s and len(s) > 3
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
