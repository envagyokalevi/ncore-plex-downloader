"""Bejelentkezés / kijelentkezés.

Nyilvános regisztráció nincs: a felhasználók kizárólag a .env fájlból jönnek.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response

from app.deps import AppSettings, CurrentUser, Db
from app.errors import BadCredentialsError
from app.models.schemas import LoginRequest, SimpleMessage, UserInfo
from app.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    create_csrf_token,
    create_session_token,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserInfo)
async def login(
    payload: LoginRequest,
    response: Response,
    db: Db,
    settings: AppSettings,
) -> UserInfo:
    username = payload.username.strip()
    password_hash = await db.get_user_hash(username)

    if not password_hash or not verify_password(payload.password, password_hash):
        # Szándékosan nem áruljuk el, hogy a név vagy a jelszó volt hibás.
        logger.warning("Sikertelen bejelentkezesi kiserlet")
        raise BadCredentialsError()

    session_token = create_session_token(
        username, settings.app_secret_key, settings.session_ttl_hours
    )
    csrf_token = create_csrf_token()
    max_age = settings.session_ttl_hours * 3600

    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=max_age,
        httponly=True,  # a JS soha nem fér hozzá
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,  # a frontend olvassa és fejlécben visszaküldi
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    logger.info("Sikeres bejelentkezes: %s", username)
    return UserInfo(username=username)


@router.post("/logout", response_model=SimpleMessage)
async def logout(response: Response, user: CurrentUser) -> SimpleMessage:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return SimpleMessage(message="Kijelentkeztél.")


@router.get("/me", response_model=UserInfo)
async def me(user: CurrentUser) -> UserInfo:
    return UserInfo(username=user)
