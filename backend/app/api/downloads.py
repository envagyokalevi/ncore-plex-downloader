"""Letöltések listázása és vezérlése (szüneteltetés / folytatás / törlés)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.deps import CurrentUser, Service
from app.models.schemas import DownloadsResponse, SimpleMessage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/downloads", tags=["letoltesek"])


@router.get("", response_model=DownloadsResponse)
async def list_downloads(service: Service, user: CurrentUser) -> DownloadsResponse:
    return DownloadsResponse(downloads=await service.list_downloads())


@router.post("/{torrent_hash}/pause", response_model=SimpleMessage)
async def pause(torrent_hash: str, service: Service, user: CurrentUser) -> SimpleMessage:
    await service.pause(torrent_hash)
    return SimpleMessage(message="Letöltés szüneteltetve.")


@router.post("/{torrent_hash}/resume", response_model=SimpleMessage)
async def resume(torrent_hash: str, service: Service, user: CurrentUser) -> SimpleMessage:
    await service.resume(torrent_hash)
    return SimpleMessage(message="Letöltés folytatva.")


@router.delete("/{torrent_hash}", response_model=SimpleMessage)
async def delete(
    torrent_hash: str,
    service: Service,
    user: CurrentUser,
    delete_files: bool = Query(
        default=False,
        alias="delete_files",
        description="Ha true, a már letöltött fájlokat is törli.",
    ),
) -> SimpleMessage:
    """Torrent eltávolítása. Alapértelmezés szerint a fájlok megmaradnak."""
    await service.delete(torrent_hash, delete_files=delete_files)
    message = (
        "Torrent és a fájlok törölve." if delete_files else "Torrent törölve, a fájlok megmaradtak."
    )
    return SimpleMessage(message=message)
