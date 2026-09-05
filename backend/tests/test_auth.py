"""Bejelentkezés, session és CSRF tesztek."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.security import (
    CSRF_HEADER,
    create_session_token,
    csrf_tokens_match,
    hash_password,
    read_session_token,
    verify_password,
)
from tests.conftest import TEST_PASSWORD

SECRET = "titkos-teszt-kulcs"


# --- jelszó -------------------------------------------------------------


def test_hash_password_is_not_plaintext() -> None:
    hashed = hash_password("jelszo123")
    assert hashed != "jelszo123"
    assert hashed.startswith("$2")


def test_hash_password_is_salted() -> None:
    assert hash_password("jelszo123") != hash_password("jelszo123")


def test_verify_password() -> None:
    hashed = hash_password("jelszo123")
    assert verify_password("jelszo123", hashed)
    assert not verify_password("rossz", hashed)


@pytest.mark.parametrize("bad_hash", ["", "nem-hash", "$2b$rontott"])
def test_verify_password_with_broken_hash(bad_hash: str) -> None:
    assert verify_password("barmi", bad_hash) is False


# --- session token ------------------------------------------------------


def test_session_token_roundtrip() -> None:
    token = create_session_token("apa", SECRET, 24)
    assert read_session_token(token, SECRET) == "apa"


def test_session_token_rejects_wrong_secret() -> None:
    token = create_session_token("apa", SECRET, 24)
    assert read_session_token(token, "masik-kulcs") is None


def test_session_token_rejects_expired() -> None:
    token = create_session_token("apa", SECRET, -1)
    assert read_session_token(token, SECRET) is None


@pytest.mark.parametrize("token", ["", "abc", "a.b.c"])
def test_session_token_rejects_garbage(token: str) -> None:
    assert read_session_token(token, SECRET) is None


def test_csrf_tokens_match() -> None:
    assert csrf_tokens_match("abc", "abc")
    assert not csrf_tokens_match("abc", "abd")
    assert not csrf_tokens_match(None, "abc")
    assert not csrf_tokens_match("abc", None)


# --- login végpont ------------------------------------------------------


def test_login_success_sets_cookies(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": "apa", "password": TEST_PASSWORD})
    assert response.status_code == 200
    assert response.json() == {"username": "apa"}
    assert "cs_session" in response.cookies
    assert "cs_csrf" in response.cookies


def test_session_cookie_is_httponly(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": "apa", "password": TEST_PASSWORD})
    session_cookie = next(
        value for key, value in response.headers.items()
        if key.lower() == "set-cookie" and value.startswith("cs_session=")
    )
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie.replace("samesite=lax", "SameSite=lax")


def test_extra_user_can_log_in(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": "anya", "password": TEST_PASSWORD})
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("username", "password"),
    [("apa", "rossz-jelszo"), ("nincs-ilyen", TEST_PASSWORD), ("APA", TEST_PASSWORD)],
)
def test_login_failure(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "bad_credentials"
    assert body["message"] == "Hibás felhasználónév vagy jelszó."


def test_login_response_never_contains_password(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": "apa", "password": TEST_PASSWORD})
    assert TEST_PASSWORD not in response.text


def test_me_requires_login(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_username(auth_client: TestClient) -> None:
    assert auth_client.get("/api/auth/me").json() == {"username": "apa"}


def test_logout_clears_session(auth_client: TestClient) -> None:
    assert auth_client.post("/api/auth/logout").status_code == 200
    assert auth_client.get("/api/auth/me").status_code == 401


# --- védett végpontok ---------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/search?q=teszt"),
        ("get", "/api/torrents/1234567"),
        ("post", "/api/torrents/1234567/download"),
        ("get", "/api/downloads"),
        ("post", f"/api/downloads/{'a' * 40}/pause"),
        ("post", f"/api/downloads/{'a' * 40}/resume"),
        ("delete", f"/api/downloads/{'a' * 40}"),
    ],
)
def test_endpoints_require_authentication(client: TestClient, method: str, path: str) -> None:
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.json()["message"] == "Nincs bejelentkezve."


# --- CSRF ---------------------------------------------------------------


def test_write_without_csrf_header_is_rejected(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "apa", "password": TEST_PASSWORD})
    # A CSRF fejléc szándékosan hiányzik
    response = client.post("/api/torrents/1234567/download")
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_write_with_wrong_csrf_header_is_rejected(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "apa", "password": TEST_PASSWORD})
    response = client.post(
        "/api/torrents/1234567/download", headers={CSRF_HEADER: "hamis-token"}
    )
    assert response.status_code == 403


def test_read_endpoints_do_not_need_csrf(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "apa", "password": TEST_PASSWORD})
    assert client.get("/api/downloads").status_code == 200
