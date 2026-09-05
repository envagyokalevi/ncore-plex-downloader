"""FastAPI függőségek: alkalmazás-állapot, bejelentkezés, CSRF."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.db import Database
from app.errors import AuthError, CsrfError
from app.integrations.ncore import NcoreClient
from app.integrations.qbittorrent import QBittorrentClient
from app.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, csrf_tokens_match, read_session_token
from app.services.downloads import DownloadService

#: Írási műveletekhez CSRF token szükséges (cookie alapú auth miatt).
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class AppState:
    settings: Settings
    db: Database
    ncore: NcoreClient
    qbit: QBittorrentClient

    @property
    def service(self) -> DownloadService:
        return DownloadService(self.ncore, self.qbit, self.db)


def get_state(request: Request) -> AppState:
    return request.app.state.app_state  # type: ignore[no-any-return]


def get_settings_dep(state: Annotated[AppState, Depends(get_state)]) -> Settings:
    return state.settings


def get_service(state: Annotated[AppState, Depends(get_state)]) -> DownloadService:
    return state.service


def get_db(state: Annotated[AppState, Depends(get_state)]) -> Database:
    return state.db


def current_user(
    request: Request,
    state: Annotated[AppState, Depends(get_state)],
) -> str:
    """Bejelentkezett felhasználó neve; CSRF ellenőrzés írási műveleteknél."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthError()
    username = read_session_token(token, state.settings.app_secret_key)
    if not username:
        raise AuthError()

    if request.method in _UNSAFE_METHODS:
        cookie_token = request.cookies.get(CSRF_COOKIE)
        header_token = request.headers.get(CSRF_HEADER)
        if not csrf_tokens_match(cookie_token, header_token):
            raise CsrfError()

    return username


CurrentUser = Annotated[str, Depends(current_user)]
Service = Annotated[DownloadService, Depends(get_service)]
Db = Annotated[Database, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
