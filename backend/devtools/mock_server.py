"""Fejlesztői mock szerver: nCore + qBittorrent Web API utánzat.

CSAK FEJLESZTÉSHEZ. Ezzel a teljes alkalmazás kipróbálható a fejlesztői
gépen anélkül, hogy a production qBittorrenthez vagy az nCore-hoz hozzá
kellene férni.

Indítás:
    uvicorn devtools.mock_server:app --host 0.0.0.0 --port 9080

A .env-ben ilyenkor:
    NCORE_URL=http://mock:9080
    QBITTORRENT_URL=http://mock:9080
"""

from __future__ import annotations

import hashlib
import random
import time
from typing import Any

from fastapi import FastAPI, Form, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

app = FastAPI(title="Mock nCore + qBittorrent", docs_url=None)

DEFAULT_SAVE_PATH = "/media/downloads"

_MOVIES: list[dict[str, Any]] = [
    {"id": "100001", "title": "Interstellar.2014.HUNGARIAN.1080p.BluRay.x264-DEMO", "size": "12.42 GiB", "seed": 42, "leech": 3},
    {"id": "100002", "title": "Interstellar.2014.HUN.2160p.UHD.BluRay.x265-DEMO", "size": "48.10 GiB", "seed": 12, "leech": 7},
    {"id": "100003", "title": "Interstellar.2014.HUN.720p.BluRay.x264-DEMO", "size": "6.85 GiB", "seed": 88, "leech": 1},
    {"id": "100004", "title": "A.Nagy.Film.2023.HUN.1080p.WEB-DL.DDP5.1-DEMO", "size": "9.20 GiB", "seed": 5, "leech": 0},
    {"id": "100005", "title": "Csaladi.Kaland.2021.HUN.1080p.BluRay.x264-DEMO", "size": "11.03 GiB", "seed": 23, "leech": 2},
]

#: hash -> qBittorrent-szerű torrent objektum
_TORRENTS: dict[str, dict[str, Any]] = {}
_SESSION_ID = "mock-sid"


# =====================================================================
#  nCore mock
# =====================================================================


def _is_logged_in(request: Request) -> bool:
    return request.cookies.get("mock_ncore") == "1"


def _login_page() -> HTMLResponse:
    return HTMLResponse('<html><head><title>nCore</title></head><body>login.php</body></html>')


@app.post("/login.php")
async def ncore_login(
    nev: str = Form(default=""),
    password: str = Form(default="", alias="pass"),
    set_lang: str = Form(default=""),
    submitted: str = Form(default=""),
    ne_leptessen_ki: str = Form(default=""),
) -> Response:
    if not nev or not password:
        return _login_page()
    body = (
        '<html><head><title>nCore - Index</title>'
        '<link rel="alternate" type="application/rss+xml" '
        'href="https://ncore.pro/rss.php?key=mockrsskey123" title="RSS"></head>'
        "<body>Bejelentkezve</body></html>"
    )
    response = HTMLResponse(body)
    response.set_cookie("mock_ncore", "1")
    return response


@app.get("/index.php")
async def ncore_index(request: Request) -> Response:
    if not _is_logged_in(request):
        return _login_page()
    return HTMLResponse(
        '<html><head><link rel="alternate" href="https://ncore.pro/rss.php?key=mockrsskey123" '
        'title="RSS"></head><body>index</body></html>'
    )


def _row(movie: dict[str, Any]) -> str:
    return f"""
    <div class="box_torrent">
      <div class="box_alap_img">
        <a href="/torrents.php?tipus=hd_hun"><img src="/pic/categ.gif" class="categ_link"
           alt="Film/HU" title="Film/HU"></a>
      </div>
      <div class="box_nev2">
        <a href="/torrents.php?action=details&amp;id={movie['id']}"
           onclick="torrent({movie['id']}); return false;" title="{movie['title']}">
           {movie['title'][:40]}</a>
      </div>
      <div class="box_feltoltve2">2024-01-15<br>10:22:31</div>
      <div class="box_meret2">{movie['size']}</div>
      <div class="box_d2"><a class="torrent" href="#">15</a></div>
      <div class="box_s2"><a class="torrent" href="/torrents.php?peers">{movie['seed']}</a></div>
      <div class="box_l2"><a class="torrent" href="/torrents.php?peers">{movie['leech']}</a></div>
    </div>
    """


@app.get("/torrents.php")
async def ncore_torrents(request: Request) -> Response:
    if not _is_logged_in(request):
        return _login_page()

    params = request.query_params
    action = params.get("action")

    if action == "download":
        torrent_id = params.get("id", "")
        movie = next((m for m in _MOVIES if m["id"] == torrent_id), None)
        if movie is None:
            return PlainTextResponse("nincs ilyen torrent", status_code=404)
        return Response(content=_fake_torrent_file(movie), media_type="application/x-bittorrent")

    if action == "details":
        torrent_id = params.get("id", "")
        movie = next((m for m in _MOVIES if m["id"] == torrent_id), None)
        if movie is None:
            return HTMLResponse("<html><body>Nincs ilyen torrent</body></html>", status_code=404)
        return HTMLResponse(_detail_page(movie))

    query = (params.get("mire") or "").lower()
    matches = [m for m in _MOVIES if query in m["title"].lower()] if query else _MOVIES
    header = (
        '<html><head><link rel="alternate" href="https://ncore.pro/rss.php?key=mockrsskey123" '
        'title="RSS"></head><body>'
    )
    if not matches:
        return HTMLResponse(header + '<div class="lista_mini_error">Nincs találat!</div></body></html>')
    return HTMLResponse(header + "".join(_row(m) for m in matches) + "</body></html>")


def _detail_page(movie: dict[str, Any]) -> str:
    return f"""<html><head>
    <link rel="alternate" href="https://ncore.pro/rss.php?key=mockrsskey123" title="RSS"></head><body>
    <div class="torrent_reszletek_cim">{movie['title']}</div>
    <div class="dt">Típus:</div>
    <div class="dd"><a title="Film" href="/torrents.php?csoport_listazas=osszes_film">Film</a>
      &raquo; <a title="HD/HU" href="/torrents.php?tipus=hd_hun">HD/HU</a></div>
    <div class="dt">Feltöltve:</div><div class="dd">2024-01-15 10:22:31</div>
    <div class="dt">Méret:</div><div class="dd">{movie['size']} (13 331 034 112 bájt)</div>
    <div class="dt">Seederek:</div><div class="dd"><a onclick="return false;">{movie['seed']}</a></div>
    <div class="dt">Leecherek:</div><div class="dd"><a onclick="return false;">{movie['leech']}</a></div>
    <div class="fl_konyvtar_fajl_nev">{movie['title']}.mkv</div>
    <div class="fl_konyvtar_fajl_meret">{movie['size']}</div>
    <div class="fl_konyvtar_fajl_nev">{movie['title']}.srt</div>
    <div class="fl_konyvtar_fajl_meret">64.20 KiB</div>
    </body></html>"""


def _fake_torrent_file(movie: dict[str, Any]) -> bytes:
    """Minimális, érvényes bencode szerkezetű .torrent tartalom."""
    name = movie["title"].encode()
    info = b"d6:lengthi1024e4:name" + str(len(name)).encode() + b":" + name
    info += b"12:piece lengthi262144e6:pieces20:" + b"\x00" * 20 + b"e"
    return b"d8:announce23:http://mock.tracker/ann4:info" + info + b"e"


# =====================================================================
#  qBittorrent Web API mock
# =====================================================================


@app.post("/api/v2/auth/login")
async def qbit_login(username: str = Form(default=""), password: str = Form(default="")) -> Response:
    if not username:
        return PlainTextResponse("Fails.", status_code=200)
    response = PlainTextResponse("Ok.")
    response.set_cookie("SID", _SESSION_ID)
    return response


@app.get("/api/v2/app/version")
async def qbit_version() -> Response:
    return PlainTextResponse("v5.0.3 (mock)")


@app.get("/api/v2/app/webapiVersion")
async def qbit_webapi_version() -> Response:
    return PlainTextResponse("2.11.2")


@app.get("/api/v2/app/defaultSavePath")
async def qbit_default_save_path() -> Response:
    return PlainTextResponse(DEFAULT_SAVE_PATH)


@app.get("/api/v2/app/preferences")
async def qbit_preferences() -> JSONResponse:
    return JSONResponse({"save_path": DEFAULT_SAVE_PATH, "dht": True})


@app.post("/api/v2/torrents/add")
async def qbit_add(torrents: UploadFile | None = None) -> Response:
    content = await torrents.read() if torrents is not None else b""
    if not content.startswith(b"d"):
        return PlainTextResponse("Fails.", status_code=415)

    torrent_hash = hashlib.sha1(content).hexdigest()
    if torrent_hash in _TORRENTS:
        return PlainTextResponse("Ok.")

    name = _extract_name(content) or f"mock-torrent-{torrent_hash[:8]}"
    _TORRENTS[torrent_hash] = {
        "hash": torrent_hash,
        "name": name,
        "size": random.randint(6, 48) * 1024**3,
        "progress": 0.0,
        "state": "downloading",
        "dlspeed": random.randint(4, 40) * 1024 * 1024,
        "upspeed": random.randint(0, 2) * 1024 * 1024,
        "save_path": DEFAULT_SAVE_PATH,
        "added_on": time.time(),
    }
    return PlainTextResponse("Ok.")


def _extract_name(content: bytes) -> str | None:
    marker = b"4:name"
    index = content.find(marker)
    if index < 0:
        return None
    rest = content[index + len(marker) :]
    colon = rest.find(b":")
    try:
        length = int(rest[:colon])
    except ValueError:
        return None
    return rest[colon + 1 : colon + 1 + length].decode(errors="replace")


def _advance(torrent: dict[str, Any]) -> dict[str, Any]:
    """A haladás szimulálása, hogy a Letöltések oldal élőnek látsszon."""
    if torrent["state"] in {"pausedDL", "stoppedDL"}:
        return torrent
    elapsed = time.time() - torrent["added_on"]
    torrent["progress"] = min(1.0, elapsed / 120.0)  # 2 perc alatt "kész"
    if torrent["progress"] >= 1.0:
        torrent["state"] = "uploading"
        torrent["dlspeed"] = 0
    return torrent


@app.get("/api/v2/torrents/info")
async def qbit_info(request: Request) -> JSONResponse:
    wanted = request.query_params.get("hashes")
    items = [_advance(t) for t in _TORRENTS.values()]
    if wanted and wanted != "all":
        allowed = set(wanted.split("|"))
        items = [t for t in items if t["hash"] in allowed]
    payload = []
    for torrent in items:
        eta = int((1 - torrent["progress"]) * 120) or 8640000
        payload.append(
            {
                **torrent,
                "completed": int(torrent["size"] * torrent["progress"]),
                "eta": eta,
            }
        )
    return JSONResponse(payload)


def _set_state(hashes: str, state: str) -> Response:
    for torrent_hash in hashes.split("|"):
        if torrent_hash in _TORRENTS:
            _TORRENTS[torrent_hash]["state"] = state
            if state == "downloading":
                # Az eltelt idő "visszaállítása", hogy folytatódjon a haladás.
                progress = _TORRENTS[torrent_hash]["progress"]
                _TORRENTS[torrent_hash]["added_on"] = time.time() - progress * 120
    return PlainTextResponse("")


@app.post("/api/v2/torrents/stop")
async def qbit_stop(hashes: str = Form(default="")) -> Response:
    return _set_state(hashes, "stoppedDL")


@app.post("/api/v2/torrents/start")
async def qbit_start(hashes: str = Form(default="")) -> Response:
    return _set_state(hashes, "downloading")


@app.post("/api/v2/torrents/delete")
async def qbit_delete(hashes: str = Form(default=""), deleteFiles: str = Form(default="false")) -> Response:
    for torrent_hash in hashes.split("|"):
        _TORRENTS.pop(torrent_hash, None)
    return PlainTextResponse("")
