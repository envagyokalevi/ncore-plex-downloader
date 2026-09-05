"""Az API végpontok tesztjei mockolt integrációkkal."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.errors import (
    NcoreLoginError,
    NcoreSearchError,
    NcoreUnavailableError,
    NotEnoughSpaceError,
    QbitAddError,
    QbitAuthError,
    QbitUnavailableError,
    TorrentDownloadError,
    TorrentNotFoundError,
)
from tests.conftest import DEFAULT_SAVE_PATH, HASH_A, HASH_B, FakeNcore, FakeQbit


# --- keresés --------------------------------------------------------------


def test_search_returns_normalized_results(auth_client: TestClient) -> None:
    response = auth_client.get("/api/search", params={"q": "Interstellar"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "Interstellar"
    assert body["count"] == 1
    result = body["results"][0]
    assert result["title"].startswith("Interstellar")
    assert result["size_text"] == "12.42 GiB"
    assert result["seeders"] == 42
    assert result["language"] == "magyar"


def test_search_response_has_no_tracker_internals(auth_client: TestClient) -> None:
    """A frontend soha nem kaphat nCore kulcsot vagy cookie-t."""
    text = auth_client.get("/api/search", params={"q": "Interstellar"}).text
    for leak in ("key=", "PHPSESSID", "ncore.pro", "ncore-titok", "passkey"):
        assert leak not in text


@pytest.mark.parametrize("query", ["", "a"])
def test_search_rejects_too_short_query(auth_client: TestClient, query: str) -> None:
    assert auth_client.get("/api/search", params={"q": query}).status_code == 422


def test_search_missing_query(auth_client: TestClient) -> None:
    assert auth_client.get("/api/search").status_code == 422


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (NcoreLoginError(), 502, "ncore_login_failed"),
        (NcoreUnavailableError(), 502, "ncore_unavailable"),
        (NcoreSearchError(), 502, "ncore_search_failed"),
    ],
)
def test_search_errors_are_translated(
    auth_client: TestClient, fake_ncore: FakeNcore, error: Exception, status: int, code: str
) -> None:
    fake_ncore.raise_on_search = error
    response = auth_client.get("/api/search", params={"q": "Interstellar"})
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    # Magyar, emberi nyelvű üzenet
    assert body["message"].endswith(".")
    assert "Traceback" not in body["message"]


# --- torrent részletek ----------------------------------------------------


def test_torrent_details_include_save_path(auth_client: TestClient) -> None:
    response = auth_client.get("/api/torrents/1234567")
    assert response.status_code == 200
    body = response.json()
    assert body["save_path"] == DEFAULT_SAVE_PATH
    assert body["torrent"]["size_text"] == "12.42 GiB"
    assert body["torrent"]["files"][0]["kind"] == "videó"


@pytest.mark.parametrize("torrent_id", ["abc", "../etc/passwd", "1;drop", "-5"])
def test_torrent_details_rejects_invalid_id(auth_client: TestClient, torrent_id: str) -> None:
    response = auth_client.get(f"/api/torrents/{torrent_id}")
    assert response.status_code in (400, 404)
    if response.status_code == 400:
        assert response.json()["code"] == "invalid_torrent_id"


def test_torrent_details_not_found(auth_client: TestClient, fake_ncore: FakeNcore) -> None:
    fake_ncore.raise_on_details = TorrentNotFoundError()
    response = auth_client.get("/api/torrents/1234567")
    assert response.status_code == 404
    assert response.json()["message"] == "Ez a torrent már nem érhető el az nCore-on."


def test_torrent_details_when_qbittorrent_down(
    auth_client: TestClient, fake_qbit: FakeQbit
) -> None:
    fake_qbit.raise_on_save_path = QbitUnavailableError()
    response = auth_client.get("/api/torrents/1234567")
    assert response.status_code == 502
    assert response.json()["code"] == "qbittorrent_unavailable"


# --- letöltés indítása ----------------------------------------------------


def test_start_download_adds_torrent(
    auth_client: TestClient, fake_qbit: FakeQbit, fake_ncore: FakeNcore
) -> None:
    response = auth_client.post("/api/torrents/1234567/download")
    assert response.status_code == 200
    assert response.json()["message"] == "Letöltés elindítva."
    assert response.json()["torrent_hash"] == HASH_A
    assert len(fake_qbit.added) == 1
    assert fake_qbit.added[0][0] == fake_ncore.torrent_bytes


def test_start_download_never_sends_save_path(
    auth_client: TestClient, fake_qbit: FakeQbit
) -> None:
    """A letöltési helyet kizárólag a qBittorrent határozza meg."""
    auth_client.post("/api/torrents/1234567/download")
    assert fake_qbit.added[0][1] is None


def test_client_cannot_choose_save_path(auth_client: TestClient, fake_qbit: FakeQbit) -> None:
    """Kliens által küldött save_path értéket figyelmen kívül hagyunk."""
    auth_client.post(
        "/api/torrents/1234567/download",
        params={"save_path": "/etc"},
        json={"save_path": "/etc", "savepath": "/root"},
    )
    assert fake_qbit.added[0][1] is None


def test_start_download_is_logged_to_history(auth_client: TestClient, client: TestClient) -> None:
    auth_client.post("/api/torrents/1234567/download")
    state = client.app.state.app_state
    import asyncio

    history = asyncio.run(state.db.recent_downloads())
    assert history[0]["torrent_id"] == "1234567"
    assert history[0]["username"] == "apa"


@pytest.mark.parametrize(
    ("error", "status", "message"),
    [
        (TorrentNotFoundError(), 404, "Ez a torrent már nem érhető el az nCore-on."),
        (TorrentDownloadError(), 502, "Nem sikerült letölteni a torrent fájlt az nCore-ról."),
    ],
)
def test_start_download_ncore_errors(
    auth_client: TestClient, fake_ncore: FakeNcore, error: Exception, status: int, message: str
) -> None:
    fake_ncore.raise_on_get = error
    response = auth_client.post("/api/torrents/1234567/download")
    assert response.status_code == status
    assert response.json()["message"] == message


@pytest.mark.parametrize(
    ("error", "status", "message"),
    [
        (QbitAddError(), 502, "Nem sikerült hozzáadni a torrentet a qBittorrenthez."),
        (QbitAuthError(), 502, "A qBittorrent bejelentkezés sikertelen. Ellenőrizd a felhasználónevet és a jelszót."),
        (QbitUnavailableError(), 502, "A qBittorrent nem érhető el. Ellenőrizd, hogy fut-e."),
        (NotEnoughSpaceError(), 507, "Nincs elég szabad tárhely a letöltéshez."),
    ],
)
def test_start_download_qbittorrent_errors(
    auth_client: TestClient, fake_qbit: FakeQbit, error: Exception, status: int, message: str
) -> None:
    fake_qbit.raise_on_add = error
    response = auth_client.post("/api/torrents/1234567/download")
    assert response.status_code == status
    assert response.json()["message"] == message


def test_start_download_twice_reports_duplicate(
    auth_client: TestClient, fake_qbit: FakeQbit
) -> None:
    auth_client.post("/api/torrents/1234567/download")
    # A qBittorrent OK-t ad, de nem jön létre új torrent
    fake_qbit.add_torrent = _noop_add(fake_qbit)  # type: ignore[method-assign]
    response = auth_client.post("/api/torrents/1234567/download")
    assert response.status_code == 409
    assert response.json()["message"] == "Ez a torrent már szerepel a letöltések között."


def _noop_add(fake_qbit: FakeQbit):
    async def _add(torrent_data: bytes, save_path: str | None = None) -> None:
        return None

    return _add


# --- letöltések oldal -----------------------------------------------------


def test_downloads_empty(auth_client: TestClient) -> None:
    assert auth_client.get("/api/downloads").json() == {"downloads": []}


def test_downloads_list(auth_client: TestClient) -> None:
    auth_client.post("/api/torrents/1234567/download")
    item = auth_client.get("/api/downloads").json()["downloads"][0]
    assert item["hash"] == HASH_A
    assert item["state_label"] == "Letöltés"
    assert item["progress"] == 0.0
    assert item["size_bytes"] == 13_336_691_507
    assert item["eta_seconds"] == 640
    assert item["is_paused"] is False


def test_downloads_pause_and_resume(auth_client: TestClient, fake_qbit: FakeQbit) -> None:
    auth_client.post("/api/torrents/1234567/download")

    response = auth_client.post(f"/api/downloads/{HASH_A}/pause")
    assert response.status_code == 200
    assert response.json()["message"] == "Letöltés szüneteltetve."
    assert fake_qbit.paused == [HASH_A]

    response = auth_client.post(f"/api/downloads/{HASH_A}/resume")
    assert response.json()["message"] == "Letöltés folytatva."
    assert fake_qbit.resumed == [HASH_A]


def test_downloads_delete_keeps_files_by_default(
    auth_client: TestClient, fake_qbit: FakeQbit
) -> None:
    auth_client.post("/api/torrents/1234567/download")
    response = auth_client.delete(f"/api/downloads/{HASH_A}")
    assert response.status_code == 200
    assert response.json()["message"] == "Torrent törölve, a fájlok megmaradtak."
    assert fake_qbit.deleted == [(HASH_A, False)]


def test_downloads_delete_with_files(auth_client: TestClient, fake_qbit: FakeQbit) -> None:
    auth_client.post("/api/torrents/1234567/download")
    response = auth_client.delete(f"/api/downloads/{HASH_A}", params={"delete_files": "true"})
    assert response.json()["message"] == "Torrent és a fájlok törölve."
    assert fake_qbit.deleted == [(HASH_A, True)]


def test_downloads_action_on_unknown_hash(auth_client: TestClient) -> None:
    response = auth_client.post(f"/api/downloads/{HASH_B}/pause")
    assert response.status_code == 404
    assert response.json()["message"] == "Ez a letöltés nem található."


@pytest.mark.parametrize("bad_hash", ["abc", "../../etc", "z" * 40, "all"])
def test_downloads_action_rejects_invalid_hash(auth_client: TestClient, bad_hash: str) -> None:
    assert auth_client.post(f"/api/downloads/{bad_hash}/pause").status_code == 404


def test_downloads_when_qbittorrent_unavailable(
    auth_client: TestClient, fake_qbit: FakeQbit
) -> None:
    async def boom(hashes=None):
        raise QbitUnavailableError()

    fake_qbit.get_torrents = boom  # type: ignore[method-assign]
    response = auth_client.get("/api/downloads")
    assert response.status_code == 502
    assert response.json()["message"] == "A qBittorrent nem érhető el. Ellenőrizd, hogy fut-e."


# --- rendszer -------------------------------------------------------------


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_status_reports_both_services(client: TestClient) -> None:
    body = client.get("/api/status").json()
    assert body["qbittorrent"]["ok"] is True
    assert body["qbittorrent"]["default_save_path"] == DEFAULT_SAVE_PATH
    assert body["ncore"]["ok"] is True


def test_status_reports_failure_without_secrets(
    client: TestClient, fake_qbit: FakeQbit
) -> None:
    fake_qbit.raise_on_save_path = QbitUnavailableError()
    body = client.get("/api/status").json()
    assert body["qbittorrent"]["ok"] is False
    assert "qbit-titok" not in str(body)
