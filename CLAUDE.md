# CLAUDE.md

Útmutató a projekt folytatásához. A felhasználói dokumentáció a
[README.md](README.md) — ez a fájl a fejlesztéshez szükséges kontextust rögzíti.

## Mi ez

Családi, self-hosted webalkalmazás: a családtagok filmre keresnek az nCore-on,
és egy megerősítés után elindítják a letöltést a **már futó** qBittorrenten.
A cél az egyszerűség — a családtagoknak soha nem kell qBittorrentet vagy
nCore-t használniuk.

## Architektúra

```
Böngésző ──► FastAPI backend ──┬──► nCore (HTML scraping)
   (React)                     └──► qBittorrent Web API v2
                                          └──► letöltési mappa ──► Plex
```

- **Egyetlen Docker image**: a Vite build a FastAPI `static/` könyvtárába kerül,
  a FastAPI szolgálja ki. Nincs CORS, a session cookie azonos originből jön.
- **Egyetlen `docker-compose.yml`**: csak az `app` szolgáltatás. A qBittorrent
  NEM része a stacknek.
- **Dev és prod között kizárólag a `.env` tér el.** Nincs külön dev image, dev
  branch vagy dev architektúra — a felhasználó ezt kifejezetten kérte.

## Fontos döntések (és miért)

| Döntés | Indok |
|---|---|
| Az app **nem** nyúl a fájlrendszerhez | A qBittorrent másik konténerben más path-okat lát. A `.torrent`-et fájlfeltöltésként adjuk át a Web API-nak, így a path-eltérés irreleváns. Ne vezess be média-mountot. |
| A `save_path`-ot **soha nem küldjük** | A qBittorrent a saját alapértelmezettjébe tölt. Az app csak lekérdezi és megmutatja. A kliens semmilyen útvonalat nem adhat meg. |
| A qBittorrent nincs a compose-ban | A felhasználónál már fut, külön Compose projektben. Nem módosítjuk. |
| Nincs Plex API integráció, nincs fájlmozgatás | MVP-döntés. Megbízható megoldás nélkül több kárt okozna. |
| nCore parsing regexekkel, egy helyen | Az nCore HTML-t ad, nem API-t. A minták a `NcorePatterns` osztályban felülírhatók, ha az oldal változik. |
| Session: HttpOnly JWT cookie + dupla-submit CSRF | Cookie alapú auth belső hálózaton, egyszerű és biztonságos. |
| SQLite `aiosqlite`-tal, nyers SQL-lel | Két tábla összesen; ORM felesleges lenne. |

## Ellenőrzött külső API-tudás — NE találgasd újra

**nCore** (forrás: a karbantartott `radaron/ncoreparser` könyvtár olvasása, nem
kitalálás):

- login: `POST /login.php`, mezők: `nev`, `pass`, `set_lang`, `submitted`,
  `ne_leptessen_ki`
- keresés: `GET /torrents.php?oldal=&tipus=&miszerint=&hogyan=&mire=&miben=`
- Film HD/HU kategória: `tipus=hd_hun` (idegen nyelvű HD: `hd`)
- részletek: `/torrents.php?action=details&id=<id>`
- letöltés: `/torrents.php?action=download&id=<id>&key=<rss-kulcs>`
- a `key` az oldal RSS linkjéből jön: `rss.php?key=...`
- találati sor: `onclick="torrent(ID)"` + `title=`, `box_meret2`, `box_s2`
  (seed), `box_l2` (leech), kategória a `categ_link` képre mutató linkből

**qBittorrent Web API v2** (forrás: hivatalos WebUI API wiki):

- `POST /api/v2/auth/login` (`username`, `password`) → SID cookie. A válasz
  verziófüggő: régebbi qBittorrentek `200` + `Ok.` szöveggel, az 5.x sorozat
  (élőben ellenőrizve 5.2.3-mal) `204 No Content`-tel, üres törzzsel. A
  kliens mindkettőt sikerként kezeli. Hibás jelszó → `401`; IP-tiltás túl sok
  próbálkozás után → `403`.
- `GET /api/v2/app/defaultSavePath`, `/app/preferences`, `/app/version`
- `POST /api/v2/torrents/add` — multipart, `torrents` mező a fájl. Sikeres
  válasz szintén verziófüggő: régebbi verziók `Ok.` szöveget adnak, az 5.x
  sorozat (élőben ellenőrizve 5.2.3-mal) JSON objektumot
  (`{"added_torrent_ids": [...], "failure_count": 0, ...}`). Már hozzáadott
  torrentnél az 5.x `409 Conflict`-ot ad (régebbi verziók `200`-at
  "already" szöveggel).
- `GET /api/v2/torrents/info?hashes=<pipe-al elválasztva>`
- **5.x: `/torrents/stop` és `/torrents/start`**; 4.x: `/pause`, `/resume`.
  A kliens az újat próbálja, 404/405/501 esetén visszaesik a régire.
- a qBittorrent `Referer`/`Origin` fejlécet vár (CSRF védelem)

## Állapot

Kész és működik. **186 teszt zöld**, a Docker image épül, a teljes folyamat
valódi böngészőben végigpróbálva (belépés → keresés → megerősítés → indítás →
folyamat → szüneteltetés → folytatás → törlés).

```
backend/app/
  integrations/ncore.py       nCore kliens + parser (minden nCore-tudás ITT)
  integrations/qbittorrent.py qBittorrent Web API kliens
  services/downloads.py       üzleti logika, állapot-fordítás magyarra
  api/{auth,search,downloads}.py
  models/schemas.py           pydantic modellek (API szerződés)
  config.py errors.py security.py db.py deps.py logging_setup.py cli.py main.py
backend/devtools/
  mock_server.py              nCore + qBittorrent utánzat (offline fejlesztés)
  smoke_test.py               végponttól végpontig füstteszt
backend/tests/                186 teszt, fixtures/ncore_pages.py a HTML minták
frontend/src/                 React + TS, magyar UI, dark mode
```

## Fejlesztés másik gépen

```bash
cp .env.example .env
```

Töltsd ki: `APP_SECRET_KEY` (`openssl rand -hex 32`), `ADMIN_USERNAME`,
`ADMIN_PASSWORD_HASH` (`docker compose run --rm app python -m app.cli
hash-password`).

**Valódi nCore/qBittorrent nélkül** (ez a szokásos fejlesztői mód) a `.env`-ben:

```
NCORE_URL=http://mock:9080
QBITTORRENT_URL=http://mock:9080
```

majd:

```bash
docker compose --profile mock up -d --build
```

A `mock` szolgáltatás **ugyanazt az image-et** futtatja, csak más paranccsal —
nem külön architektúra.

Tesztek:

```bash
cd backend && pip install -r requirements-dev.txt && pytest
```

Végponttól végpontig füstteszt Docker nélkül:

```bash
cd backend && python -m devtools.smoke_test
```

Diagnosztika élő rendszeren: `python -m app.cli check-login` /
`check-qbittorrent` / `check-ncore`, illetve `GET /api/status`.

## Konvenciók

- **A felület és minden felhasználói hibaüzenet magyar.** A kód kommentjei és
  docstringjei szintén magyarul vannak.
- A logüzenetek ékezet nélküliek (konzol-kódlap problémák miatt).
- Minden felhasználónak szánt hiba az `app/errors.py`-ban él, magyar
  szöveggel; a technikai részlet a `detail=` mezőbe megy, ami **csak logba**
  kerül, válaszba soha.
- Új nCore-mező kell? Előbb vedd fel a `tests/fixtures/ncore_pages.py`-ba egy
  reális HTML mintát, és úgy írd a parsert.

## Biztonsági szabályok — ezeket ne lazítsd

- nCore és qBittorrent jelszó **soha** nem kerülhet API-válaszba.
- A `.env` nem kerülhet Gitbe (`.gitignore`) és image-be (`.dockerignore`).
- A kliens **nem adhat meg** `save_path`-ot és URL-t. A qBittorrent csak a
  backend által letöltött `.torrent` bájtokat kapja meg (SSRF ellen).
- Torrent ID: csak számjegy. Info-hash: csak hex, 40 vagy 64 karakter.
- Az nCore URL-eket a backend állítja össze, és ellenőrzi, hogy a konfigurált
  hoston maradnak.
- A `SecretFilter` maszkolja a titkokat a logban — string argumentumokat igen,
  számokat **nem** (különben eltörik a `%d` formázás).
- Nincs nyilvános regisztráció; a felhasználók forrása kizárólag a `.env`.

## Ismert korlátozások / nyitott pontok

- **A valódi nCore-ral és a valódi qBittorrenttel még nem futott.** A parser a
  fenti, ellenőrzött szerkezetre épül, de éles adaton nem volt tesztelve. Első
  éles indításnál a `check-ncore` és `check-qbittorrent` parancsokkal kell
  verifikálni.
- Az nCore bármikor változtathat HTML-t → a keresés eltörhet. A javítás helye:
  `NcorePatterns` a `ncore.py`-ban.
- nCore 2FA nincs támogatva.
- Nincs lapozás: az első oldal, seed szerint csökkenő, `NCORE_MAX_RESULTS`-ig.
- Alapból film HD/HU és sorozat HD/HU (`hd_hun,hdser_hun`) van bekapcsolva;
  más kategóriák (`hd`, `hdser`, SD/DVD változatok) a `NCORE_CATEGORIES`-ban
  konfigurálhatók, kódjuk az `ncore.py` `CATEGORY_LABELS`-jában.
- A Letöltések oldal 3 mp-es pollingot használ, nem WebSocketet.
- Egyetlen nCore fiókon osztozik minden családtag.
- A `docker-compose.yml` `env_file: .env` miatt egy friss klón `.env` nélkül
  hibát ad — ezért az első lépés mindig a `cp .env.example .env`.

## Amit ne csinálj

- Ne tegyél qBittorrent szolgáltatást a compose-ba.
- Ne vezess be külön dev/prod kódot, image-et vagy branchet.
- Ne mountolj média- vagy letöltési könyvtárat az app konténerbe.
- Ne írj `localhost`/`127.0.0.1` alapértelmezést a qBittorrent címéhez.
- Ne találj ki nCore endpointot vagy CSS selectort bizonyíték nélkül —
  vizsgáld meg az aktuális működést, vagy tedd konfigurálhatóvá.
- Ne kérj be jelszót parancssori argumentumként (shell history).

## Következő lehetséges lépések

Plex library scan indítása torrent elkészültekor · Plex-struktúrába rendezés
hardlinkkel (hogy a seedelés megmaradjon) · lapozás a
találatokban · több nCore fiók.
