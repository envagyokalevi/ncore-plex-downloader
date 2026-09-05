"""Az NcoreClient tesztjei mockolt HTTP réteggel (httpx MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from app.errors import (
    NcoreConfigError,
    NcoreLoginError,
    NcoreUnavailableError,
    TorrentDownloadError,
    TorrentNotFoundError,
)
from app.integrations.ncore import NcoreClient, NcoreConfig
from tests.fixtures import ncore_pages as pages

TORRENT_BYTES = b"d8:announce20:http://tracker/annou4:infod4:name5:filmee"


def make_client(handler, **overrides) -> NcoreClient:
    defaults = {
        "base_url": "https://ncore.test",
        "username": "teszt",
        "password": "titok",
        "categories": ("hd_hun",),
    }
    config = NcoreConfig(**{**defaults, **overrides})
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, follow_redirects=True)
    return NcoreClient(config, client=http_client)


def default_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    params = request.url.params

    if path == "/login.php":
        return httpx.Response(200, html=pages.LOGIN_SUCCESS, request=request)
    if path == "/index.php":
        return httpx.Response(200, html=pages.LOGIN_SUCCESS, request=request)
    if path == "/torrents.php":
        if params.get("action") == "download":
            return httpx.Response(200, content=TORRENT_BYTES, request=request)
        if params.get("action") == "details":
            return httpx.Response(200, html=pages.TORRENT_DETAILS, request=request)
        return httpx.Response(200, html=pages.SEARCH_RESULTS, request=request)
    return httpx.Response(404, request=request)


# --- login ----------------------------------------------------------------


async def test_login_sends_expected_form_fields() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login.php":
            body = request.content.decode()
            for pair in body.split("&"):
                key, _, value = pair.partition("=")
                captured[key] = value
            return httpx.Response(200, html=pages.LOGIN_SUCCESS, request=request)
        return httpx.Response(404, request=request)

    client = make_client(handler)
    await client.login()

    assert captured["nev"] == "teszt"
    assert captured["pass"] == "titok"
    assert captured["submitted"] == "1"


async def test_login_failure_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Az nCore sikertelen belépéskor a login.php-n hagy
        return httpx.Response(
            200, html=pages.LOGIN_PAGE, request=httpx.Request("POST", "https://ncore.test/login.php")
        )

    client = make_client(handler)
    with pytest.raises(NcoreLoginError):
        await client.login()


async def test_login_without_credentials_raises_config_error() -> None:
    client = make_client(default_handler)
    client._config.username = ""
    with pytest.raises(NcoreConfigError):
        await client.login()


async def test_network_error_maps_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nincs kapcsolat", request=request)

    client = make_client(handler)
    with pytest.raises(NcoreUnavailableError):
        await client.login()


# --- keresés --------------------------------------------------------------


async def test_search_uses_configured_category_and_params() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return default_handler(request)

    client = make_client(handler)
    await client.search_movies("Interstellar")

    search_url = next(u for u in seen if u.path == "/torrents.php")
    assert search_url.params["tipus"] == "hd_hun"
    assert search_url.params["mire"] == "Interstellar"
    assert search_url.params["miben"] == "name"


async def test_search_returns_normalized_results() -> None:
    client = make_client(default_handler)
    results = await client.search_movies("Interstellar")
    assert len(results) == 3
    # seeders szerint csökkenő sorrend
    assert [r.seeders for r in results] == [42, 7, 0]


async def test_search_merges_categories_without_duplicates() -> None:
    client = make_client(default_handler, categories=("hd_hun", "hd"))
    results = await client.search_movies("Interstellar")
    assert len({r.id for r in results}) == len(results) == 3


async def test_search_respects_max_results() -> None:
    client = make_client(default_handler, max_results=2)
    assert len(await client.search_movies("Interstellar")) == 2


async def test_empty_query_returns_empty_list() -> None:
    client = make_client(default_handler)
    assert await client.search_movies("   ") == []


async def test_expired_session_triggers_relogin() -> None:
    state = {"logged_in": False, "logins": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login.php":
            if request.method == "POST":
                state["logged_in"] = True
                state["logins"] += 1
                return httpx.Response(200, html=pages.LOGIN_SUCCESS)
            return httpx.Response(200, html=pages.LOGIN_PAGE)
        if not state["logged_in"]:
            # Az nCore a lejárt session miatt a login oldalra irányít
            return httpx.Response(302, headers={"Location": "https://ncore.test/login.php"})
        return default_handler(request)

    client = make_client(handler)
    await client.login()
    state["logged_in"] = False  # session lejár
    results = await client.search_movies("Interstellar")

    assert state["logins"] == 2
    assert len(results) == 3


# --- részletek / letöltés -------------------------------------------------


async def test_get_torrent_details() -> None:
    client = make_client(default_handler)
    details = await client.get_torrent_details("1234567")
    assert details.title.startswith("Interstellar")
    assert details.size_bytes == int(12.42 * 1024**3)
    assert len(details.files) == 3


async def test_get_torrent_details_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login.php":
            return httpx.Response(200, html=pages.LOGIN_SUCCESS, request=request)
        return httpx.Response(200, html=pages.DETAILS_MISSING, request=request)

    client = make_client(handler)
    with pytest.raises(TorrentNotFoundError):
        await client.get_torrent_details("1234567")


async def test_get_torrent_returns_bytes_and_uses_key() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return default_handler(request)

    client = make_client(handler)
    data = await client.get_torrent("1234567")

    assert data == TORRENT_BYTES
    download_url = next(u for u in seen if u.params.get("action") == "download")
    assert download_url.params["id"] == "1234567"
    assert download_url.params["key"] == "loginkey42"


async def test_get_torrent_rejects_non_torrent_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login.php":
            return httpx.Response(200, html=pages.LOGIN_SUCCESS, request=request)
        return httpx.Response(200, html="<html>hibauzenet</html>", request=request)

    client = make_client(handler)
    with pytest.raises(TorrentDownloadError):
        await client.get_torrent("1234567")


async def test_get_torrent_404_maps_to_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login.php":
            return httpx.Response(200, html=pages.LOGIN_SUCCESS, request=request)
        return httpx.Response(404, request=request)

    client = make_client(handler)
    with pytest.raises(TorrentNotFoundError):
        await client.get_torrent("1234567")


# --- SSRF védelem ---------------------------------------------------------


async def test_urls_stay_on_configured_host() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return default_handler(request)

    client = make_client(handler)
    await client.search_movies("Interstellar")
    await client.get_torrent_details("42")

    assert seen, "nem történt kérés"
    assert all(url.host == "ncore.test" for url in seen)
