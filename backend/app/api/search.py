"""Keresés és torrent részletek."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.deps import CurrentUser, Service
from app.models.schemas import (
    DownloadStartedResponse,
    SearchResponse,
    TorrentDetailsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["kereses"])


@router.get("/search", response_model=SearchResponse)
async def search(
    service: Service,
    user: CurrentUser,
    q: str = Query(min_length=2, max_length=100, description="Keresett film neve"),
) -> SearchResponse:
    results = await service.search(q)
    logger.info("Kereses: '%s' -> %d talalat", q, len(results))
    return SearchResponse(query=q, count=len(results), results=results)


@router.get("/torrents/{torrent_id}", response_model=TorrentDetailsResponse)
async def torrent_details(
    torrent_id: str,
    service: Service,
    user: CurrentUser,
) -> TorrentDetailsResponse:
    """A megerősítő ablak adatai: torrent neve, mérete, letöltési hely."""
    details, save_path = await service.get_details(torrent_id)
    return TorrentDetailsResponse(torrent=details, save_path=save_path)


@router.post("/torrents/{torrent_id}/download", response_model=DownloadStartedResponse)
async def start_download(
    torrent_id: str,
    service: Service,
    user: CurrentUser,
) -> DownloadStartedResponse:
    """Torrent hozzáadása a qBittorrenthez.

    A letöltési könyvtárat kizárólag a qBittorrent határozza meg; a kliens
    semmilyen útvonalat nem adhat meg.
    """
    torrent_hash = await service.start_download(torrent_id, user)
    return DownloadStartedResponse(torrent_hash=torrent_hash)
