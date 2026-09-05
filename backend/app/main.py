"""Családi Plex - FastAPI alkalmazás belépési pont.

Egyetlen konténer szolgálja ki az API-t és a beépített React frontendet, így
nincs CORS és a session cookie azonos originből érkezik.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth as auth_api
from app.api import downloads as downloads_api
from app.api import search as search_api
from app.config import get_settings
from app.db import Database
from app.deps import AppState
from app.errors import AppError
from app.integrations import ncore as ncore_integration
from app.integrations import qbittorrent as qbit_integration
from app.logging_setup import setup_logging
from app.models.schemas import ErrorResponse

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level, settings.secrets)

    if settings.app_env == "production":
        if settings.app_secret_key == "change-me":
            logger.error(
                "APP_SECRET_KEY nincs beallitva! Generalj egyet: openssl rand -hex 32"
            )
        elif len(settings.app_secret_key) < 32:
            logger.warning(
                "Az APP_SECRET_KEY rovidebb 32 karakternel - hasznalj erosebb kulcsot "
                "(openssl rand -hex 32)."
            )

    db = Database(settings.database_path)
    await db.init()
    await db.sync_users(settings.users)
    if not settings.users:
        logger.error(
            "Nincs beallitva felhasznalo, igy semmilyen belepes nem fog mukodni. "
            "Allitsd be az ADMIN_USERNAME es ADMIN_PASSWORD_HASH ertekeket a .env "
            "fajlban, majd inditsd ujra: docker compose up -d"
        )
    else:
        # A leggyakoribb telepitesi hiba a serult jelszo-hash - erre azonnal
        # szoljunk, ne csak a sikertelen belepesnel derüljön ki.
        from app.cli import describe_hash_problem

        for username, password_hash in settings.users.items():
            problem = describe_hash_problem(password_hash)
            if problem:
                logger.error(
                    "A(z) '%s' felhasznalo jelszo-hash-e hibas: %s "
                    "(ellenorzes: python -m app.cli check-login)",
                    username,
                    problem,
                )

    ncore_client = ncore_integration.build_client(
        base_url=settings.ncore_url,
        username=settings.ncore_username,
        password=settings.ncore_password,
        categories=settings.category_list,
        timeout=settings.ncore_timeout,
        max_results=settings.ncore_max_results,
    )
    qbit_client = qbit_integration.build_client(
        base_url=settings.qbittorrent_url,
        username=settings.qbittorrent_username,
        password=settings.qbittorrent_password,
        category=settings.qbittorrent_category,
        timeout=settings.qbittorrent_timeout,
    )

    app.state.app_state = AppState(
        settings=settings, db=db, ncore=ncore_client, qbit=qbit_client
    )
    logger.info("Alkalmazas elindult (env=%s)", settings.app_env)
    try:
        yield
    finally:
        await ncore_client.aclose()
        await qbit_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Családi Plex",
        description="Egyszerű felület filmek kereséséhez és letöltéséhez.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        # A technikai részlet csak a szerveroldali logba kerül.
        if exc.detail:
            logger.warning("%s (%s): %s", exc.code, request.url.path, exc.detail)
        else:
            logger.info("%s (%s)", exc.code, request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Kezeletlen hiba: %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                code="internal_error", message="Váratlan hiba történt. Próbáld újra."
            ).model_dump(),
        )

    app.include_router(auth_api.router)
    app.include_router(search_api.router)
    app.include_router(downloads_api.router)

    @app.get("/api/health", tags=["rendszer"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status", tags=["rendszer"])
    async def status(request: Request) -> dict[str, object]:
        """Diagnosztika: elérhető-e a qBittorrent és az nCore.

        Titkos adatot nem ad vissza, csak állapotot.
        """
        state: AppState = request.app.state.app_state
        result: dict[str, object] = {"qbittorrent": {}, "ncore": {}}
        try:
            version = await state.qbit.get_version()
            save_path = await state.qbit.get_default_save_path()
            result["qbittorrent"] = {
                "ok": True,
                "version": version,
                "default_save_path": save_path,
            }
        except AppError as exc:
            result["qbittorrent"] = {"ok": False, "message": exc.message}
        try:
            await state.ncore.login()
            result["ncore"] = {"ok": True}
        except AppError as exc:
            result["ncore"] = {"ok": False, "message": exc.message}
        return result

    _mount_frontend(app, settings.static_dir)
    return app


def _mount_frontend(app: FastAPI, static_dir: str) -> None:
    """A Vite build kiszolgálása; ismeretlen útvonalon SPA fallback."""
    index_file = os.path.join(static_dir, "index.html")
    if not os.path.isdir(static_dir) or not os.path.isfile(index_file):
        logger.warning("A frontend build nem talalhato (%s) - csak az API elerheto.", static_dir)
        return

    assets_dir = os.path.join(static_dir, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = os.path.normpath(os.path.join(static_dir, full_path))
        # Path traversal ellen: a fájl csak a static könyvtárból szolgálható ki.
        if (
            full_path
            and candidate.startswith(os.path.abspath(static_dir))
            and os.path.isfile(candidate)
        ):
            return FileResponse(candidate)
        return FileResponse(index_file)


app = create_app()
