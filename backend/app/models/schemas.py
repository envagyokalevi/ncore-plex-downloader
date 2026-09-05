"""A backend belső / API felé menő adatstruktúrái.

Fontos: ezek a modellek szándékosan NEM tartalmaznak nCore-specifikus
mezőket (pl. RSS kulcs, cookie), így a frontend soha nem lát tracker-adatot.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Auth ----------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserInfo(BaseModel):
    username: str


# --- Keresés -------------------------------------------------------------


class SearchResult(BaseModel):
    id: str
    title: str
    size_bytes: int | None = None
    size_text: str | None = None
    category: str | None = None
    language: str | None = None
    seeders: int | None = None
    leechers: int | None = None


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchResult]


# --- Torrent részletek ---------------------------------------------------


class TorrentFile(BaseModel):
    name: str
    size_bytes: int | None = None
    size_text: str | None = None
    kind: str | None = None


class TorrentDetails(BaseModel):
    id: str
    title: str
    size_bytes: int | None = None
    size_text: str | None = None
    category: str | None = None
    language: str | None = None
    seeders: int | None = None
    leechers: int | None = None
    files: list[TorrentFile] = Field(default_factory=list)


class TorrentDetailsResponse(BaseModel):
    """A megerősítő ablak adatai – a letöltési hely a qBittorrenttől jön."""

    torrent: TorrentDetails
    save_path: str


class DownloadStartedResponse(BaseModel):
    message: str = "Letöltés elindítva."
    torrent_hash: str | None = None


# --- Letöltések ----------------------------------------------------------


class DownloadItem(BaseModel):
    hash: str
    name: str
    progress: float  # 0.0 – 1.0
    state: str  # nyers qBittorrent állapot
    state_label: str  # magyar felirat
    size_bytes: int | None = None
    downloaded_bytes: int | None = None
    dlspeed: int | None = None  # bájt/mp
    upspeed: int | None = None  # bájt/mp
    eta_seconds: int | None = None
    save_path: str | None = None
    is_paused: bool = False


class DownloadsResponse(BaseModel):
    downloads: list[DownloadItem]


class SimpleMessage(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    code: str
    message: str
