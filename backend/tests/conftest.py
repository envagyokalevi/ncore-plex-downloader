"""Közös teszt-fixture-ök.

Az API teszteket a valódi FastAPI alkalmazás ellen futtatjuk, de az nCore és
a qBittorrent integrációt mockra cseréljük - így hálózat nélkül tesztelhető a
teljes útvonal a HTTP kéréstől a szolgáltatásrétegig.
"""

from __future__ import annotations

import os
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app.models.schemas import SearchResult, TorrentDetails, TorrentFile
from app.security import CSRF_HEADER, hash_password

TEST_PASSWORD = "teszt-jelszo-123"
#: A bcrypt hash szándékosan egyszer készül el - tesztfutásonként lassú művelet.
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)
DEFAULT_SAVE_PATH = "/media/downloads"
HASH_A = "a" * 40
HASH_B = "b" * 40


# --- mock integrációk -----------------------------------------------------


class FakeNcore:
    """Az NcoreClient felülete, hálózat nélkül."""

    def __init__(self) -> None:
        self.results = [
            SearchResult(
                id="1234567",
                title="Interstellar.2014.HUNGARIAN.1080p.BluRay.x264",
                size_bytes=13_336_691_507,
                size_text="12.42 GiB",
                category="Film HD",
                language="magyar",
                seeders=42,
                leechers=3,
            )
        ]
        self.details = TorrentDetails(
            id="1234567",
            title="Interstellar.2014.HUNGARIAN.1080p.BluRay.x264",
            size_bytes=13_336_691_507,
            size_text="12.42 GiB",
            category="Film HD",
            language="magyar",
            seeders=42,
            leechers=3,
            files=[
                TorrentFile(
                    name="Interstellar.mkv",
                    size_bytes=13_000_000_000,
                    size_text="12.10 GiB",
                    kind="videó",
                )
            ],
        )
        self.torrent_bytes = b"d8:announce20:http://tracker/annou4:infod4:name5:filmee"
        self.raise_on_search: Exception | None = None
        self.raise_on_details: Exception | None = None
        self.raise_on_get: Exception | None = None
        self.searched: list[str] = []

    async def login(self, force: bool = False) -> None:
        return None

    async def search_movies(self, query: str) -> list[SearchResult]:
        if self.raise_on_search:
            raise self.raise_on_search
        self.searched.append(query)
        return self.results

    async def get_torrent_details(self, torrent_id: str) -> TorrentDetails:
        from app.integrations.ncore import validate_torrent_id

        validate_torrent_id(torrent_id)
        if self.raise_on_details:
            raise self.raise_on_details
        return self.details

    async def get_torrent(self, torrent_id: str) -> bytes:
        from app.integrations.ncore import validate_torrent_id

        validate_torrent_id(torrent_id)
        if self.raise_on_get:
            raise self.raise_on_get
        return self.torrent_bytes

    async def aclose(self) -> None:
        return None


class FakeQbit:
    """A QBittorrentClient felülete, hálózat nélkül."""

    def __init__(self) -> None:
        self.torrents: list[dict[str, Any]] = []
        self.added: list[tuple[bytes, str | None]] = []
        self.paused: list[str] = []
        self.resumed: list[str] = []
        self.deleted: list[tuple[str, bool]] = []
        self.raise_on_add: Exception | None = None
        self.raise_on_save_path: Exception | None = None
        self.next_hash = HASH_A

    async def login(self, force: bool = False) -> None:
        return None

    async def get_version(self) -> str:
        return "v5.0.3"

    async def get_preferences(self) -> dict[str, Any]:
        return {"save_path": DEFAULT_SAVE_PATH}

    async def get_default_save_path(self) -> str:
        if self.raise_on_save_path:
            raise self.raise_on_save_path
        return DEFAULT_SAVE_PATH

    async def add_torrent(self, torrent_data: bytes, save_path: str | None = None) -> None:
        if self.raise_on_add:
            raise self.raise_on_add
        self.added.append((torrent_data, save_path))
        self.torrents.append(
            {
                "hash": self.next_hash,
                "name": "Interstellar.2014.HUNGARIAN.1080p.BluRay.x264",
                "progress": 0.0,
                "state": "downloading",
                "size": 13_336_691_507,
                "completed": 0,
                "dlspeed": 12_582_912,
                "upspeed": 0,
                "eta": 640,
                "save_path": DEFAULT_SAVE_PATH,
            }
        )

    async def get_torrents(self, hashes: list[str] | None = None) -> list[dict[str, Any]]:
        if hashes:
            return [t for t in self.torrents if t["hash"] in set(hashes)]
        return list(self.torrents)

    async def get_torrent(self, torrent_hash: str) -> dict[str, Any] | None:
        from app.integrations.qbittorrent import validate_torrent_hash

        torrent_hash = validate_torrent_hash(torrent_hash)
        return next((t for t in self.torrents if t["hash"] == torrent_hash), None)

    async def pause(self, torrent_hash: str) -> None:
        self.paused.append(torrent_hash)

    async def resume(self, torrent_hash: str) -> None:
        self.resumed.append(torrent_hash)

    async def delete(self, torrent_hash: str, delete_files: bool = False) -> None:
        self.deleted.append((torrent_hash, delete_files))
        self.torrents = [t for t in self.torrents if t["hash"] != torrent_hash]

    async def aclose(self) -> None:
        return None


# --- alkalmazás -----------------------------------------------------------


@pytest.fixture
def env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "teszt-titkos-kulcs-legalabb-32-karakter-hosszu")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "nincs-static"))
    monkeypatch.setenv("ADMIN_USERNAME", "apa")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", TEST_PASSWORD_HASH)
    monkeypatch.setenv("EXTRA_USERS", f"anya:{TEST_PASSWORD_HASH}")
    monkeypatch.setenv("NCORE_USERNAME", "ncore-user")
    monkeypatch.setenv("NCORE_PASSWORD", "ncore-titok")
    monkeypatch.setenv("QBITTORRENT_PASSWORD", "qbit-titok")
    # A .env fájlt ne olvassa be a teszt futtatásakor
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def fake_ncore() -> FakeNcore:
    return FakeNcore()


@pytest.fixture
def fake_qbit() -> FakeQbit:
    return FakeQbit()


@pytest.fixture
def client(env, fake_ncore: FakeNcore, fake_qbit: FakeQbit) -> Iterator[TestClient]:
    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        # A valódi integrációkat mockra cseréljük az indulás után.
        app.state.app_state.ncore = fake_ncore
        app.state.app_state.qbit = fake_qbit
        yield test_client
    get_settings.cache_clear()


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    """Bejelentkezett kliens, beállított CSRF fejléccel."""
    response = client.post(
        "/api/auth/login", json={"username": "apa", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    client.headers[CSRF_HEADER] = client.cookies["cs_csrf"]
    return client
