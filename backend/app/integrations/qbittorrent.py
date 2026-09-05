"""qBittorrent Web API (v2) kliens.

Az endpointok a hivatalos WebUI API dokumentációjából származnak:
  POST /api/v2/auth/login            username, password  -> SID cookie
  GET  /api/v2/app/version
  GET  /api/v2/app/webapiVersion
  GET  /api/v2/app/preferences       -> JSON (tartalmazza a save_path-ot)
  GET  /api/v2/app/defaultSavePath   -> alapértelmezett letöltési könyvtár
  POST /api/v2/torrents/add          multipart: torrents=<fájl>, savepath, category...
  GET  /api/v2/torrents/info         hashes=<pipe-al elválasztva>
  POST /api/v2/torrents/stop|pause   hashes
  POST /api/v2/torrents/start|resume hashes
  POST /api/v2/torrents/delete       hashes, deleteFiles

A qBittorrent 5.0 átnevezte a pause/resume végpontokat stop/start-ra, a régi
neveket alias-ként megtartva. A kliens megpróbálja az újat, és 404/405 esetén
visszaesik a régire, így 4.x és 5.x is működik.

Biztonság: a `save_path` értékét kizárólag a szerver adhatja meg, a kliens
soha; és soha nem adunk át kliens által megadott URL-t a qBittorrentnek
(csak feltöltött .torrent tartalmat).
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.errors import (
    NotEnoughSpaceError,
    QbitAddError,
    QbitAuthError,
    QbitUnavailableError,
    TorrentAlreadyExistsError,
)

logger = logging.getLogger(__name__)

HASH_RE = re.compile(r"^[a-fA-F0-9]{40}(?:[a-fA-F0-9]{24})?$")  # SHA-1 vagy SHA-256 (v2)


def validate_torrent_hash(value: str) -> str:
    """Csak valódi info-hash fogadható el (path traversal / injekció ellen)."""
    from app.errors import DownloadNotFoundError

    candidate = (value or "").strip().lower()
    if not HASH_RE.match(candidate):
        raise DownloadNotFoundError()
    return candidate


@dataclass
class QbitConfig:
    base_url: str = "http://qbittorrent:8080"
    username: str = "admin"
    password: str = ""
    category: str = ""
    timeout: float = 20.0


class QBittorrentClient:
    def __init__(self, config: QbitConfig, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            # A qBittorrent CSRF védelme miatt a Referer/Origin fejlécet elvárja.
            headers={"Referer": config.base_url, "Origin": config.base_url},
            follow_redirects=False,
        )
        self._logged_in = False
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    # --- alap kérések ---

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        files: Any = None,
        retry_auth: bool = True,
    ) -> httpx.Response:
        if not self._logged_in and not path.endswith("/auth/login"):
            await self.login()
        try:
            response = await self._client.request(
                method, path, data=data, params=params, files=files
            )
        except httpx.HTTPError as exc:
            logger.warning("qBittorrent halozati hiba: %s", type(exc).__name__)
            raise QbitUnavailableError(detail=str(exc)) from exc

        if response.status_code == 403 and retry_auth and not path.endswith("/auth/login"):
            # Lejárt SID – egyszer újra bejelentkezünk.
            logger.info("qBittorrent session lejart, ujra bejelentkezes")
            self._logged_in = False
            await self.login(force=True)
            return await self._request(
                method, path, data=data, params=params, files=files, retry_auth=False
            )
        return response

    # --- auth ---

    async def login(self, force: bool = False) -> None:
        async with self._lock:
            if self._logged_in and not force:
                return
            self._client.cookies.clear()
            try:
                response = await self._client.post(
                    "/api/v2/auth/login",
                    data={
                        "username": self._config.username,
                        "password": self._config.password,
                    },
                )
            except httpx.HTTPError as exc:
                logger.warning("qBittorrent login halozati hiba: %s", type(exc).__name__)
                raise QbitUnavailableError(detail=str(exc)) from exc

            if response.status_code == 403:
                logger.warning("qBittorrent login tiltva (IP ban vagy tul sok proba)")
                raise QbitAuthError()
            if response.status_code != 200 or "Ok." not in response.text:
                logger.warning("qBittorrent login sikertelen (HTTP %s)", response.status_code)
                raise QbitAuthError()

            self._logged_in = True
            logger.info("qBittorrent bejelentkezes sikeres")

    # --- alkalmazás ---

    async def get_version(self) -> str:
        response = await self._request("GET", "/api/v2/app/version")
        return response.text.strip()

    async def get_preferences(self) -> dict[str, Any]:
        response = await self._request("GET", "/api/v2/app/preferences")
        if response.status_code != 200:
            raise QbitUnavailableError(detail=f"preferences HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise QbitUnavailableError(detail="preferences: invalid JSON") from exc

    async def get_default_save_path(self) -> str:
        """A qBittorrentben beállított alapértelmezett letöltési könyvtár."""
        response = await self._request("GET", "/api/v2/app/defaultSavePath")
        if response.status_code == 200 and response.text.strip():
            return response.text.strip()
        # Régebbi verziók: a preferences save_path mezője.
        preferences = await self.get_preferences()
        save_path = preferences.get("save_path")
        if isinstance(save_path, str) and save_path:
            return save_path
        raise QbitUnavailableError(detail="nincs default save path")

    # --- torrentek ---

    async def add_torrent(
        self, torrent_data: bytes, save_path: str | None = None
    ) -> None:
        """.torrent fájl hozzáadása.

        `save_path` alapértelmezés szerint None: ilyenkor a qBittorrent a saját
        beállított alapértelmezett könyvtárát használja. Az érték kizárólag
        szerveroldalról származhat.
        """
        files = {"torrents": ("upload.torrent", torrent_data, "application/x-bittorrent")}
        data: dict[str, Any] = {}
        if save_path:
            data["savepath"] = save_path
        if self._config.category:
            data["category"] = self._config.category

        response = await self._request("POST", "/api/v2/torrents/add", data=data, files=files)

        if response.status_code == 415:
            logger.warning("qBittorrent elutasitotta a torrent fajlt (HTTP 415)")
            raise QbitAddError()
        if response.status_code != 200:
            logger.warning("qBittorrent torrent hozzaadas HTTP %s", response.status_code)
            self._raise_add_error(response.text)
        body = response.text.strip()
        if body and body.lower() not in {"ok.", "ok"}:
            self._raise_add_error(body)

    @staticmethod
    def _raise_add_error(body: str) -> None:
        lowered = (body or "").lower()
        if "space" in lowered or "no space" in lowered:
            raise NotEnoughSpaceError()
        if "already" in lowered:
            raise TorrentAlreadyExistsError()
        raise QbitAddError(detail=body[:200])

    async def get_torrents(self, hashes: list[str] | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if hashes:
            params["hashes"] = "|".join(validate_torrent_hash(h) for h in hashes)
        response = await self._request("GET", "/api/v2/torrents/info", params=params)
        if response.status_code != 200:
            raise QbitUnavailableError(detail=f"info HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise QbitUnavailableError(detail="info: invalid JSON") from exc
        return payload if isinstance(payload, list) else []

    async def get_torrent(self, torrent_hash: str) -> dict[str, Any] | None:
        torrent_hash = validate_torrent_hash(torrent_hash)
        torrents = await self.get_torrents([torrent_hash])
        return torrents[0] if torrents else None

    async def _action(self, primary: str, fallback: str, torrent_hash: str) -> None:
        """Művelet hívása, 5.x névvel, szükség esetén 4.x fallbackkel."""
        torrent_hash = validate_torrent_hash(torrent_hash)
        response = await self._request(
            "POST", f"/api/v2/torrents/{primary}", data={"hashes": torrent_hash}
        )
        if response.status_code in (404, 405, 501):
            response = await self._request(
                "POST", f"/api/v2/torrents/{fallback}", data={"hashes": torrent_hash}
            )
        if response.status_code != 200:
            logger.warning("qBittorrent %s HTTP %s", primary, response.status_code)
            raise QbitUnavailableError(detail=f"{primary} HTTP {response.status_code}")

    async def pause(self, torrent_hash: str) -> None:
        await self._action("stop", "pause", torrent_hash)

    async def resume(self, torrent_hash: str) -> None:
        await self._action("start", "resume", torrent_hash)

    async def delete(self, torrent_hash: str, delete_files: bool = False) -> None:
        torrent_hash = validate_torrent_hash(torrent_hash)
        response = await self._request(
            "POST",
            "/api/v2/torrents/delete",
            data={"hashes": torrent_hash, "deleteFiles": "true" if delete_files else "false"},
        )
        if response.status_code != 200:
            logger.warning("qBittorrent delete HTTP %s", response.status_code)
            raise QbitUnavailableError(detail=f"delete HTTP {response.status_code}")


def build_client(
    *,
    base_url: str,
    username: str,
    password: str,
    category: str,
    timeout: float,
) -> QBittorrentClient:
    return QBittorrentClient(
        QbitConfig(
            base_url=base_url,
            username=username,
            password=password,
            category=category,
            timeout=timeout,
        )
    )
