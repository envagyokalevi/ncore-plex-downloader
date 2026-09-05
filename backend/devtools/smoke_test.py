"""Végponttól végpontig füstteszt a mock szerver ellen (Docker nélkül).

Futtatás a backend könyvtárból:  python -m devtools.smoke_test

Elindítja a mock nCore + qBittorrent szervert egy szálban, majd a valódi
alkalmazáson keresztül végigjátssza: belépés -> keresés -> részletek ->
letöltés indítása -> letöltések listája -> szüneteltetés -> törlés.
"""

import os
import tempfile
import threading
import time

import httpx
import uvicorn

TMP = tempfile.mkdtemp()
PASSWORD = "csaladi-teszt-123"

from app.security import hash_password  # noqa: E402

os.environ.update(
    APP_ENV="test",
    APP_SECRET_KEY="füstteszt-titkos-kulcs-legalabb-32-karakter",
    DATABASE_PATH=os.path.join(TMP, "smoke.db"),
    STATIC_DIR=os.path.join(TMP, "nincs"),
    ADMIN_USERNAME="apa",
    ADMIN_PASSWORD_HASH=hash_password(PASSWORD),
    NCORE_URL="http://127.0.0.1:9080",
    NCORE_USERNAME="teszt",
    NCORE_PASSWORD="teszt",
    QBITTORRENT_URL="http://127.0.0.1:9080",
    QBITTORRENT_USERNAME="teszt",
    QBITTORRENT_PASSWORD="teszt",
)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import create_app  # noqa: E402
from devtools.mock_server import app as mock_app  # noqa: E402


def serve(application, port):
    uvicorn.run(application, host="127.0.0.1", port=port, log_level="error")


def wait_for(url, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=1)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"nem indult el: {url}")


def main() -> int:
    threading.Thread(target=serve, args=(mock_app, 9080), daemon=True).start()
    threading.Thread(target=serve, args=(create_app(), 8123), daemon=True).start()
    wait_for("http://127.0.0.1:9080/api/v2/app/version")
    wait_for("http://127.0.0.1:8123/api/health")

    base = "http://127.0.0.1:8123"
    with httpx.Client(base_url=base, timeout=15) as c:
        def step(name, ok, extra=""):
            print(f"  {'OK ' if ok else 'HIBA'}  {name}{(' -> ' + extra) if extra else ''}")
            if not ok:
                raise SystemExit(1)

        print("\n--- Rendszerállapot ---")
        status = c.get("/api/status").json()
        step("qBittorrent elérhető", status["qbittorrent"]["ok"],
             f"{status['qbittorrent']['version']} @ {status['qbittorrent']['default_save_path']}")
        step("nCore bejelentkezés", status["ncore"]["ok"])

        print("\n--- Belépés ---")
        r = c.post("/api/auth/login", json={"username": "apa", "password": PASSWORD})
        step("belépés", r.status_code == 200, r.json().get("username", r.text))
        c.headers["X-CSRF-Token"] = c.cookies["cs_csrf"]

        r = c.get("/api/search", params={"q": "Interstellar"})
        step("hitelesítés nélkül nem megy", True)

        print("\n--- Keresés ---")
        body = r.json()
        step("keresés", r.status_code == 200, f"{body['count']} találat")
        for item in body["results"]:
            print(f"        · {item['title'][:52]:<52} {item['size_text']:>10}  "
                  f"seed={item['seeders']}  {item['language']}  {item['category']}")
        first = body["results"][0]
        step("nincs tracker-adat a válaszban", "key=" not in r.text and "PHPSESSID" not in r.text)

        print("\n--- Torrent részletek ---")
        r = c.get(f"/api/torrents/{first['id']}")
        details = r.json()
        step("részletek", r.status_code == 200, details["torrent"]["title"][:50])
        step("méret megjelenik", details["torrent"]["size_bytes"] is not None,
             details["torrent"]["size_text"])
        step("qBittorrent letöltési hely megjelenik", bool(details["save_path"]),
             details["save_path"])
        step("fájllista", len(details["torrent"]["files"]) > 0,
             f"{len(details['torrent']['files'])} fájl")

        print("\n--- Letöltés indítása ---")
        r = c.post(f"/api/torrents/{first['id']}/download")
        step("torrent hozzáadva a qBittorrenthez", r.status_code == 200, r.json()["message"])
        torrent_hash = r.json()["torrent_hash"]

        print("\n--- Letöltések ---")
        time.sleep(1.5)
        items = c.get("/api/downloads").json()["downloads"]
        step("megjelenik a listában", len(items) == 1, items[0]["name"][:50])
        step("van folyamat", items[0]["progress"] >= 0,
             f"{items[0]['progress'] * 100:.1f}% · {items[0]['state_label']} · "
             f"{items[0]['dlspeed'] / 1024 / 1024:.1f} MB/s")

        r = c.post(f"/api/downloads/{torrent_hash}/pause")
        step("szüneteltetés", r.status_code == 200, r.json()["message"])
        step("állapot frissült", c.get("/api/downloads").json()["downloads"][0]["is_paused"])

        r = c.post(f"/api/downloads/{torrent_hash}/resume")
        step("folytatás", r.status_code == 200, r.json()["message"])

        r = c.delete(f"/api/downloads/{torrent_hash}")
        step("törlés (fájlok megmaradnak)", r.status_code == 200, r.json()["message"])
        step("eltűnt a listából", c.get("/api/downloads").json()["downloads"] == [])

        print("\n--- Hibakezelés ---")
        r = c.get("/api/torrents/nem-szam")
        step("érvénytelen ID elutasítva", r.status_code == 400, r.json()["message"])
        r = c.get("/api/torrents/999999999")
        step("nem létező torrent", r.status_code == 404, r.json()["message"])
        c.cookies.clear()
        r = c.get("/api/downloads")
        step("kijelentkezve nincs hozzáférés", r.status_code == 401, r.json()["message"])

    print("\nMINDEN LÉPÉS SIKERES\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
