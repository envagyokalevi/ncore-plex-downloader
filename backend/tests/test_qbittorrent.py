"""A qBittorrent Web API wrapper tesztjei mockolt HTTP réteggel."""

from __future__ import annotations

import httpx
import pytest

from app.errors import (
    DownloadNotFoundError,
    NotEnoughSpaceError,
    QbitAddError,
    QbitAuthError,
    QbitUnavailableError,
    TorrentAlreadyExistsError,
)
from app.integrations.qbittorrent import QbitConfig, QBittorrentClient, validate_torrent_hash

HASH_A = "a" * 40
HASH_B = "b" * 40
TORRENT_BYTES = b"d8:announce20:http://tracker/annou4:infod4:name5:filmee"


def make_client(handler, **overrides) -> QBittorrentClient:
    defaults = {
        "base_url": "http://qbit.test:8080",
        "username": "admin",
        "password": "titok",
        "category": "",
    }
    config = QbitConfig(**{**defaults, **overrides})
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=config.base_url,
        headers={"Referer": config.base_url, "Origin": config.base_url},
    )
    return QBittorrentClient(config, client=http_client)


def torrent_payload(torrent_hash: str = HASH_A, **overrides) -> dict:
    return {
        "hash": torrent_hash,
        "name": "Interstellar.2014.HUN.1080p",
        "progress": 0.42,
        "state": "downloading",
        "size": 13_336_691_507,
        "completed": 5_601_410_433,
        "dlspeed": 12_582_912,
        "upspeed": 1_048_576,
        "eta": 640,
        "save_path": "/media/downloads",
        **overrides,
    }


def default_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/v2/auth/login":
        return httpx.Response(200, text="Ok.")
    if path == "/api/v2/app/version":
        return httpx.Response(200, text="v5.0.3")
    if path == "/api/v2/app/defaultSavePath":
        return httpx.Response(200, text="/media/downloads")
    if path == "/api/v2/app/preferences":
        return httpx.Response(200, json={"save_path": "/media/downloads"})
    if path == "/api/v2/torrents/info":
        return httpx.Response(200, json=[torrent_payload()])
    if path == "/api/v2/torrents/add":
        return httpx.Response(200, text="Ok.")
    if path.startswith("/api/v2/torrents/"):
        return httpx.Response(200, text="")
    return httpx.Response(404)


# --- auth -----------------------------------------------------------------


async def test_login_posts_credentials() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            for pair in request.content.decode().split("&"):
                key, _, value = pair.partition("=")
                captured[key] = value
            return httpx.Response(200, text="Ok.")
        return httpx.Response(404)

    await make_client(handler).login()
    assert captured == {"username": "admin", "password": "titok"}


async def test_login_sets_referer_header() -> None:
    """A qBittorrent CSRF védelme miatt kötelező a Referer fejléc."""
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, text="Ok.")

    await make_client(handler).login()
    assert seen[0]["referer"] == "http://qbit.test:8080"


@pytest.mark.parametrize(
    ("status", "body"),
    [(403, "Forbidden"), (200, "Fails."), (401, "")],
)
async def test_login_failure_maps_to_auth_error(status: int, body: str) -> None:
    client = make_client(lambda request: httpx.Response(status, text=body))
    with pytest.raises(QbitAuthError):
        await client.login()


async def test_connection_error_maps_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nincs kapcsolat", request=request)

    with pytest.raises(QbitUnavailableError):
        await make_client(handler).login()


async def test_expired_session_relogins_once() -> None:
    state = {"authed": False, "logins": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            state["authed"] = True
            state["logins"] += 1
            return httpx.Response(200, text="Ok.")
        if not state["authed"]:
            return httpx.Response(403, text="Forbidden")
        return default_handler(request)

    client = make_client(handler)
    await client.login()
    state["authed"] = False  # a SID lejár
    assert await client.get_default_save_path() == "/media/downloads"
    assert state["logins"] == 2


# --- alkalmazás-adatok ----------------------------------------------------


async def test_get_version() -> None:
    assert await make_client(default_handler).get_version() == "v5.0.3"


async def test_get_default_save_path() -> None:
    assert await make_client(default_handler).get_default_save_path() == "/media/downloads"


async def test_default_save_path_falls_back_to_preferences() -> None:
    """Régebbi qBittorrent verziókon a defaultSavePath végpont hiányozhat."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/app/defaultSavePath":
            return httpx.Response(404)
        return default_handler(request)

    assert await make_client(handler).get_default_save_path() == "/media/downloads"


async def test_get_preferences() -> None:
    prefs = await make_client(default_handler).get_preferences()
    assert prefs["save_path"] == "/media/downloads"


# --- torrent hozzáadás ----------------------------------------------------


async def test_add_torrent_uploads_file_without_save_path() -> None:
    """Alapesetben nem adunk meg save_path-ot - a qBittorrent dönt."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/add":
            captured["body"] = request.content
            captured["content_type"] = request.headers.get("content-type", "")
        return default_handler(request)

    await make_client(handler).add_torrent(TORRENT_BYTES)

    assert "multipart/form-data" in captured["content_type"]  # type: ignore[operator]
    assert TORRENT_BYTES in captured["body"]  # type: ignore[operator]
    assert b'name="savepath"' not in captured["body"]  # type: ignore[operator]


async def test_add_torrent_sends_category_when_configured() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/add":
            captured["body"] = request.content
        return default_handler(request)

    await make_client(handler, category="csaladi-plex").add_torrent(TORRENT_BYTES)
    assert b"csaladi-plex" in captured["body"]


async def test_add_torrent_rejected_by_qbittorrent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/add":
            return httpx.Response(415, text="Fails.")
        return default_handler(request)

    with pytest.raises(QbitAddError):
        await make_client(handler).add_torrent(TORRENT_BYTES)


async def test_add_torrent_no_space_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/add":
            return httpx.Response(500, text="Not enough space on device")
        return default_handler(request)

    with pytest.raises(NotEnoughSpaceError):
        await make_client(handler).add_torrent(TORRENT_BYTES)


async def test_add_torrent_already_exists() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/add":
            return httpx.Response(200, text="Torrent already in session")
        return default_handler(request)

    with pytest.raises(TorrentAlreadyExistsError):
        await make_client(handler).add_torrent(TORRENT_BYTES)


# --- listázás / vezérlés --------------------------------------------------


async def test_get_torrents() -> None:
    torrents = await make_client(default_handler).get_torrents()
    assert torrents[0]["hash"] == HASH_A


async def test_get_torrent_filters_by_hash() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/info":
            seen.append(request.url.params.get("hashes", ""))
        return default_handler(request)

    await make_client(handler).get_torrent(HASH_A)
    assert seen == [HASH_A]


async def test_get_torrent_missing_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/info":
            return httpx.Response(200, json=[])
        return default_handler(request)

    assert await make_client(handler).get_torrent(HASH_B) is None


async def test_pause_uses_stop_endpoint_on_qbittorrent_5() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return default_handler(request)

    await make_client(handler).pause(HASH_A)
    assert "/api/v2/torrents/stop" in calls
    assert "/api/v2/torrents/pause" not in calls


async def test_pause_falls_back_to_legacy_endpoint() -> None:
    """qBittorrent 4.x-en még /pause és /resume a végpont neve."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path in ("/api/v2/torrents/stop", "/api/v2/torrents/start"):
            return httpx.Response(404)
        return default_handler(request)

    client = make_client(handler)
    await client.pause(HASH_A)
    await client.resume(HASH_A)

    assert "/api/v2/torrents/pause" in calls
    assert "/api/v2/torrents/resume" in calls


async def test_delete_defaults_to_keeping_files() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/delete":
            captured["body"] = request.content.decode()
        return default_handler(request)

    await make_client(handler).delete(HASH_A)
    assert "deleteFiles=false" in captured["body"]


async def test_delete_with_files() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/delete":
            captured["body"] = request.content.decode()
        return default_handler(request)

    await make_client(handler).delete(HASH_A, delete_files=True)
    assert "deleteFiles=true" in captured["body"]


# --- hash validáció -------------------------------------------------------


@pytest.mark.parametrize("value", [HASH_A, HASH_A.upper(), "c" * 64])
def test_validate_hash_accepts_valid(value: str) -> None:
    assert validate_torrent_hash(value) == value.lower()


@pytest.mark.parametrize(
    "value",
    ["", "abc", "z" * 40, "../../etc/passwd", HASH_A + "x", "all", f"{HASH_A}|{HASH_B}"],
)
def test_validate_hash_rejects_invalid(value: str) -> None:
    with pytest.raises(DownloadNotFoundError):
        validate_torrent_hash(value)
