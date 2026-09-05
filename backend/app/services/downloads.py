"""Letöltéskezelés: nCore torrent -> qBittorrent, és a folyamat lekérdezése."""

from __future__ import annotations

import logging
from typing import Any

from app.db import Database
from app.errors import DownloadNotFoundError, TorrentAlreadyExistsError
from app.integrations.ncore import NcoreClient, validate_torrent_id
from app.integrations.qbittorrent import QBittorrentClient, validate_torrent_hash
from app.models.schemas import DownloadItem, TorrentDetails

logger = logging.getLogger(__name__)

#: qBittorrent állapot -> magyar felirat
STATE_LABELS: dict[str, str] = {
    "error": "Hiba",
    "missingFiles": "Hiányzó fájlok",
    "uploading": "Feltöltés",
    "pausedUP": "Kész (szüneteltetve)",
    "stoppedUP": "Kész",
    "queuedUP": "Sorban (feltöltés)",
    "stalledUP": "Feltöltés (várakozik)",
    "checkingUP": "Ellenőrzés",
    "forcedUP": "Feltöltés (kényszerített)",
    "allocating": "Helyfoglalás",
    "downloading": "Letöltés",
    "metaDL": "Metaadatok letöltése",
    "pausedDL": "Szüneteltetve",
    "stoppedDL": "Szüneteltetve",
    "queuedDL": "Sorban áll",
    "stalledDL": "Várakozás seederre",
    "checkingDL": "Ellenőrzés",
    "forcedDL": "Letöltés (kényszerített)",
    "checkingResumeData": "Ellenőrzés",
    "moving": "Áthelyezés",
    "unknown": "Ismeretlen",
}

_PAUSED_STATES = {"pausedDL", "pausedUP", "stoppedDL", "stoppedUP"}


def map_torrent(raw: dict[str, Any]) -> DownloadItem:
    """qBittorrent torrent objektum -> belső, frontendnek szánt struktúra."""
    state = str(raw.get("state") or "unknown")
    eta = raw.get("eta")
    # A qBittorrent 8640000 (100 nap) értékkel jelzi, hogy nincs érdemi becslés.
    eta_seconds = int(eta) if isinstance(eta, (int, float)) and 0 < int(eta) < 8640000 else None
    return DownloadItem(
        hash=str(raw.get("hash") or ""),
        name=str(raw.get("name") or "?"),
        progress=float(raw.get("progress") or 0.0),
        state=state,
        state_label=STATE_LABELS.get(state, state),
        size_bytes=_optional_int(raw.get("size")),
        downloaded_bytes=_optional_int(raw.get("completed") or raw.get("downloaded")),
        dlspeed=_optional_int(raw.get("dlspeed")),
        upspeed=_optional_int(raw.get("upspeed")),
        eta_seconds=eta_seconds,
        save_path=raw.get("save_path") if isinstance(raw.get("save_path"), str) else None,
        is_paused=state in _PAUSED_STATES,
    )


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class DownloadService:
    """A keresés és a letöltésindítás üzleti logikája.

    A szolgáltatás mindkét integrációt injektálva kapja, így teljesen
    mockolható a tesztekben.
    """

    def __init__(self, ncore: NcoreClient, qbit: QBittorrentClient, db: Database) -> None:
        self._ncore = ncore
        self._qbit = qbit
        self._db = db

    # --- keresés / részletek ---

    async def search(self, query: str) -> list:
        return await self._ncore.search_movies(query)

    async def get_details(self, torrent_id: str) -> tuple[TorrentDetails, str]:
        """Torrent adatai + a qBittorrent alapértelmezett letöltési könyvtára."""
        torrent_id = validate_torrent_id(torrent_id)
        details = await self._ncore.get_torrent_details(torrent_id)
        save_path = await self._qbit.get_default_save_path()
        return details, save_path

    async def get_default_save_path(self) -> str:
        return await self._qbit.get_default_save_path()

    # --- letöltés indítása ---

    async def start_download(self, torrent_id: str, username: str) -> str | None:
        """A teljes folyamat: validálás -> torrent letöltés -> qBittorrent.

        A save_path-ot szándékosan NEM adjuk át: a qBittorrent a saját
        alapértelmezett könyvtárába tölt. Így a kliens semmilyen módon nem
        befolyásolhatja a fájlrendszer útvonalát.
        """
        torrent_id = validate_torrent_id(torrent_id)

        details = await self._ncore.get_torrent_details(torrent_id)
        torrent_data = await self._ncore.get_torrent(torrent_id)

        before = {t.get("hash") for t in await self._qbit.get_torrents()}
        await self._qbit.add_torrent(torrent_data, save_path=None)

        after = await self._qbit.get_torrents()
        new_hashes = [t for t in after if t.get("hash") not in before]
        torrent_hash = str(new_hashes[0]["hash"]) if new_hashes else None

        if torrent_hash is None and len(after) == len(before):
            # A qBittorrent OK-t adott, de nem jött létre új torrent: már megvolt.
            logger.info("A torrent (id=%s) mar szerepelt a qBittorrentben", torrent_id)
            raise TorrentAlreadyExistsError()

        await self._db.log_download(
            username=username,
            torrent_id=torrent_id,
            title=details.title,
            size_bytes=details.size_bytes,
            torrent_hash=torrent_hash,
        )
        logger.info("Letoltes elinditva: torrent_id=%s felhasznalo=%s", torrent_id, username)
        return torrent_hash

    # --- letöltések kezelése ---

    async def list_downloads(self) -> list[DownloadItem]:
        raw_list = await self._qbit.get_torrents()
        items = [map_torrent(raw) for raw in raw_list]
        items.sort(key=lambda item: (item.progress >= 1.0, item.name.lower()))
        return items

    async def pause(self, torrent_hash: str) -> None:
        torrent_hash = validate_torrent_hash(torrent_hash)
        await self._ensure_exists(torrent_hash)
        await self._qbit.pause(torrent_hash)

    async def resume(self, torrent_hash: str) -> None:
        torrent_hash = validate_torrent_hash(torrent_hash)
        await self._ensure_exists(torrent_hash)
        await self._qbit.resume(torrent_hash)

    async def delete(self, torrent_hash: str, delete_files: bool = False) -> None:
        torrent_hash = validate_torrent_hash(torrent_hash)
        await self._ensure_exists(torrent_hash)
        await self._qbit.delete(torrent_hash, delete_files=delete_files)
        logger.info("Torrent torolve (fajlokkal: %s)", delete_files)

    async def _ensure_exists(self, torrent_hash: str) -> None:
        if await self._qbit.get_torrent(torrent_hash) is None:
            raise DownloadNotFoundError()
