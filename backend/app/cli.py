"""Parancssori segédeszközök.

    python -m app.cli hash-password        # bcrypt hash generálása (interaktív)
    python -m app.cli check-login          # miért nem enged be? - diagnosztika
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
from app.security import hash_password, verify_password


def _prompt_password(prompt: str = "Jelszó: ") -> str | None:
    """Jelszó bekérése. None, ha nincs terminál (pl. -T kapcsolóval indítva)."""
    try:
        return getpass.getpass(prompt)
    except (EOFError, OSError):
        print()
        print(
            "Nincs interaktív terminál, ezért a jelszót nem tudom bekérni.",
            file=sys.stderr,
        )
        print(
            "Futtasd '-T' kapcsoló nélkül:  docker compose run --rm app "
            "python -m app.cli <parancs>",
            file=sys.stderr,
        )
        return None


def _escape_for_env_file(value: str) -> str:
    """A `$` jeleket megduplázza, hogy a docker compose .env-értelmezése ne nyelje el.

    A docker compose a `.env` fájlt is feldolgozza valtozo-behelyettesitesre
    (nem csak a konteneren belüli kornyezeti valtozokent adja tovabb), ezert
    egy nyers bcrypt hash `$`-jelei elvesznenek/csonkulnanak, ha nyersen
    masoljuk be. Lasd meg: describe_hash_problem.
    """
    return value.replace("$", "$$")


def _hash_password() -> int:
    password = _prompt_password()
    if password is None:
        return 2
    if not password:
        print("Üres jelszó nem használható.", file=sys.stderr)
        return 1
    again = _prompt_password("Jelszó újra: ")
    if again is None:
        return 2
    if password != again:
        print("A két jelszó nem egyezik.", file=sys.stderr)
        return 1
    print()
    print("A .env fájlban CSERÉLD LE erre a teljes sort (ne írd a régi mögé):")
    print()
    print(f"ADMIN_PASSWORD_HASH={_escape_for_env_file(hash_password(password))}")
    print()
    print(
        "(A '$' jeleket szándékosan dupláztuk - ezt várja el a docker compose "
        "a .env fájl feldolgozásakor, különben csonkul a hash.)"
    )
    print()
    print("Ezután indítsd újra:  docker compose up -d")
    return 0


def describe_hash_problem(password_hash: str) -> str | None:
    """Megmondja, mi a baj egy beállított jelszó-hash-sel. None = rendben van.

    A leggyakoribb hibák: hiányzó érték, véletlenül bemásolt `ADMIN_PASSWORD_HASH=`
    előtag, vagy a `$` jelek elvesztése (változó-behelyettesítés miatt).
    """
    if not password_hash:
        return "üres - nincs kitöltve a .env-ben"
    if password_hash == "change-me":
        return "még a példaérték szerepel benne"
    if "=" in password_hash:
        return (
            "tartalmaz '=' jelet - valószínűleg duplán került be az "
            "'ADMIN_PASSWORD_HASH=' előtag. A sorban csak egyszer szerepelhet."
        )
    if not password_hash.startswith("$2"):
        return (
            "nem bcrypt hash ($2-vel kellene kezdődnie). Ha a $ jelek eltűntek, "
            "a .env-ben írd őket duplán ($$2b$$12$$...), vagy tedd idézőjelbe."
        )
    if password_hash.count("$") < 3 or len(password_hash) < 55:
        return "csonka bcrypt hash - hiányzik a vége, másold be újra a teljes sort"
    return None


def _check_login() -> int:
    settings = get_settings()
    users = settings.users
    problems = 0

    print("Beállított felhasználók a konfigurációból:")
    if not settings.admin_username:
        print("  HIBA: ADMIN_USERNAME üres")
        problems += 1
    else:
        problem = describe_hash_problem(settings.admin_password_hash)
        status = "OK" if problem is None else f"HIBA: a hash {problem}"
        print(f"  {settings.admin_username!r}: {status}")
        if problem:
            problems += 1

    for name, password_hash in users.items():
        if name == settings.admin_username:
            continue
        problem = describe_hash_problem(password_hash)
        print(f"  {name!r} (EXTRA_USERS): {'OK' if problem is None else f'HIBA: a hash {problem}'}")
        if problem:
            problems += 1

    if not users:
        print("  HIBA: egyetlen használható felhasználó sincs - így semmilyen belépés nem megy")
        problems += 1

    if problems:
        print(f"\n{problems} hiba. Javítsd a .env fájlt, majd:  docker compose up -d")
        return 1

    print("\nA konfiguráció rendben. Próbáljuk ki a jelszót is.")
    print("(Hagyd üresen és nyomj Entert, ha kihagynád.)")
    password = _prompt_password()
    if not password:
        return 0

    matches = [name for name, h in users.items() if verify_password(password, h)]
    if matches:
        print(f"OK - ezzel a jelszóval be tudsz lépni: {', '.join(matches)}")
        print("\nHa a weboldal mégsem enged be, akkor a futó konténer még a régi")
        print("beállítással fut. Indítsd újra:  docker compose up -d")
        return 0

    print("HIBA: ez a jelszó egyik beállított felhasználóhoz sem illik.")
    print("Generálj újat:  python -m app.cli hash-password")
    return 1


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
    if command == "check-login":
        return _check_login()
    if command == "check-qbittorrent":
        return asyncio.run(_check_qbittorrent())
    if command == "check-ncore":
        return asyncio.run(_check_ncore())

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
