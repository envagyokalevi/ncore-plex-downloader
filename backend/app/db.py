"""Nagyon egyszerű SQLite tároló (aiosqlite).

Két tábla:
  users            – családtagok (bcrypt hash), az .env-ből seedelve
  download_history – audit: ki, mikor, melyik torrentet indította el
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS download_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL,
    torrent_id   TEXT NOT NULL,
    title        TEXT NOT NULL,
    size_bytes   INTEGER,
    torrent_hash TEXT,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_created ON download_history (created_at DESC);
"""


class Database:
    def __init__(self, path: str) -> None:
        self._path = path

    async def init(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        async with aiosqlite.connect(self._path) as conn:
            await conn.executescript(_SCHEMA)
            await conn.commit()

    async def sync_users(self, users: dict[str, str]) -> None:
        """Az .env-ben megadott felhasználók beírása/frissítése.

        Nyilvános regisztráció nincs; a felhasználók forrása kizárólag a konfiguráció.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as conn:
            for username, password_hash in users.items():
                await conn.execute(
                    """
                    INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash
                    """,
                    (username, password_hash, now),
                )
            await conn.commit()

    async def get_user_hash(self, username: str) -> str | None:
        async with aiosqlite.connect(self._path) as conn:
            async with conn.execute(
                "SELECT password_hash FROM users WHERE username = ?", (username,)
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else None

    async def log_download(
        self,
        *,
        username: str,
        torrent_id: str,
        title: str,
        size_bytes: int | None,
        torrent_hash: str | None,
    ) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                """
                INSERT INTO download_history
                    (username, torrent_id, title, size_bytes, torrent_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    torrent_id,
                    title,
                    size_bytes,
                    torrent_hash,
                    datetime.now(tz=timezone.utc).isoformat(),
                ),
            )
            await conn.commit()

    async def recent_downloads(self, limit: int = 50) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT username, torrent_id, title, size_bytes, torrent_hash, created_at
                FROM download_history ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]
