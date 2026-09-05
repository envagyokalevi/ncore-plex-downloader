"""Parancssori segédeszközök.

    python -m app.cli hash-password        # bcrypt hash generálása (interaktív)
    python -m app.cli check-qbittorrent    # kapcsolat ellenőrzése a .env alapján
    python -m app.cli check-ncore          # nCore bejelentkezés ellenőrzése

A jelszót szándékosan nem parancssori argumentumként kérjük be, hogy ne
kerüljön be a shell history-ba.
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from app.config import get_settings
from app.errors import AppError
from app.integrations import ncore as ncore_integration
from app.integrations import qbittorrent as qbit_integration
from app.security import hash_password


def _hash_password() -> int:
    password = getpass.getpass("Jelszó: ")
    if not password:
        print("Üres jelszó nem használható.", file=sys.stderr)
        return 1
    if password != getpass.getpass("Jelszó újra: "):
        print("A két jelszó nem egyezik.", file=sys.stderr)
        return 1
    print()
    print("Másold be a .env fájlba:")
    print(f"ADMIN_PASSWORD_HASH={hash_password(password)}")
    return 0


async def _check_qbittorrent() -> int:
    settings = get_settings()
    print(f"qBittorrent: {settings.qbittorrent_url}")
    client = qbit_integration.build_client(
        base_url=settings.qbittorrent_url,
        username=settings.qbittorrent_username,
        password=settings.qbittorrent_password,
        category=settings.qbittorrent_category,
        timeout=settings.qbittorrent_timeout,
    )
    try:
        await client.login()
        print(f"  verzió:                {await client.get_version()}")
        print(f"  alapért. letöltési út: {await client.get_default_save_path()}")
        print(f"  aktív torrentek:       {len(await client.get_torrents())}")
        print("OK - a qBittorrent elérhető.")
        return 0
    except AppError as exc:
        print(f"HIBA: {exc.message}", file=sys.stderr)
        return 1
    finally:
        await client.aclose()


async def _check_ncore() -> int:
    settings = get_settings()
    print(f"nCore: {settings.ncore_url} (kategóriák: {', '.join(settings.category_list)})")
    client = ncore_integration.build_client(
        base_url=settings.ncore_url,
        username=settings.ncore_username,
        password=settings.ncore_password,
        categories=settings.category_list,
        timeout=settings.ncore_timeout,
        max_results=settings.ncore_max_results,
    )
    try:
        await client.login()
        print("OK - az nCore bejelentkezés sikeres.")
        return 0
    except AppError as exc:
        print(f"HIBA: {exc.message}", file=sys.stderr)
        return 1
    finally:
        await client.aclose()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else ""

    if command == "hash-password":
        return _hash_password()
    if command == "check-qbittorrent":
        return asyncio.run(_check_qbittorrent())
    if command == "check-ncore":
        return asyncio.run(_check_ncore())

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
