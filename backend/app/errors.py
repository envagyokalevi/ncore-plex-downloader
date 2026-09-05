"""Alkalmazás-specifikus hibák, magyar nyelvű felhasználói üzenetekkel.

Minden kifelé menő hibaüzenet magyar és emberi nyelvű; a technikai részlet
csak a szerveroldali logba kerül.
"""

from __future__ import annotations


class AppError(Exception):
    """Minden kezelt alkalmazáshiba őse."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "Váratlan hiba történt."

    def __init__(self, message: str | None = None, *, detail: str | None = None) -> None:
        self.message = message or self.message
        # `detail` csak logba kerül, a válaszba soha.
        self.detail = detail
        super().__init__(self.message)


# --- nCore ---------------------------------------------------------------


class NcoreConfigError(AppError):
    status_code = 503
    code = "ncore_not_configured"
    message = "Az nCore hozzáférés nincs beállítva. Kérlek töltsd ki a .env fájlt."


class NcoreLoginError(AppError):
    status_code = 502
    code = "ncore_login_failed"
    message = "Nem sikerült bejelentkezni az nCore-ra. Ellenőrizd a felhasználónevet és a jelszót."


class NcoreUnavailableError(AppError):
    status_code = 502
    code = "ncore_unavailable"
    message = "Az nCore jelenleg nem érhető el. Próbáld újra később."


class NcoreSearchError(AppError):
    status_code = 502
    code = "ncore_search_failed"
    message = "A keresés nem sikerült. Próbáld újra később."


class TorrentNotFoundError(AppError):
    status_code = 404
    code = "torrent_not_found"
    message = "Ez a torrent már nem érhető el az nCore-on."


class TorrentDownloadError(AppError):
    status_code = 502
    code = "torrent_download_failed"
    message = "Nem sikerült letölteni a torrent fájlt az nCore-ról."


class InvalidTorrentIdError(AppError):
    status_code = 400
    code = "invalid_torrent_id"
    message = "Érvénytelen torrent azonosító."


# --- qBittorrent ---------------------------------------------------------


class QbitUnavailableError(AppError):
    status_code = 502
    code = "qbittorrent_unavailable"
    message = "A qBittorrent nem érhető el. Ellenőrizd, hogy fut-e."


class QbitAuthError(AppError):
    status_code = 502
    code = "qbittorrent_auth_failed"
    message = "A qBittorrent bejelentkezés sikertelen. Ellenőrizd a felhasználónevet és a jelszót."


class QbitAddError(AppError):
    status_code = 502
    code = "qbittorrent_add_failed"
    message = "Nem sikerült hozzáadni a torrentet a qBittorrenthez."


class TorrentAlreadyExistsError(AppError):
    status_code = 409
    code = "torrent_already_exists"
    message = "Ez a torrent már szerepel a letöltések között."


class NotEnoughSpaceError(AppError):
    status_code = 507
    code = "not_enough_space"
    message = "Nincs elég szabad tárhely a letöltéshez."


class DownloadNotFoundError(AppError):
    status_code = 404
    code = "download_not_found"
    message = "Ez a letöltés nem található."


# --- Auth ----------------------------------------------------------------


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Nincs bejelentkezve."


class BadCredentialsError(AppError):
    status_code = 401
    code = "bad_credentials"
    message = "Hibás felhasználónév vagy jelszó."


class CsrfError(AppError):
    status_code = 403
    code = "csrf_failed"
    message = "Lejárt vagy érvénytelen munkamenet. Frissítsd az oldalt és jelentkezz be újra."
