"""Jelszó-hash, session token és CSRF token kezelés.

- A jelszavak bcrypt hash-ként tárolódnak, plaintext jelszót sehol nem tárolunk.
- A session egy HttpOnly cookie-ban tárolt, aláírt JWT.
- Cookie alapú auth mellett dupla-submit CSRF védelmet használunk.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

SESSION_COOKIE = "cs_session"
CSRF_COOKIE = "cs_csrf"
CSRF_HEADER = "X-CSRF-Token"
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Konstans idejű ellenőrzés; hibás/hiányzó hash esetén False."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_session_token(username: str, secret: str, ttl_hours: int) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def read_session_token(token: str, secret: str) -> str | None:
    """A tokenből visszaadja a felhasználónevet, vagy None, ha érvénytelen/lejárt."""
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) and sub else None


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_tokens_match(cookie_value: str | None, header_value: str | None) -> bool:
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)
