# Családi Plex

Nagyon egyszerű, magyar nyelvű webes felület, amellyel a családtagok filmre
kereshetnek az nCore-on, és egyetlen megerősítés után elindíthatják a letöltést
a **már futó** qBittorrent példányon. A letöltött film a qBittorrent
alapértelmezett könyvtárába kerül, ahonnan a Plex felszedi.

```
Megnyitom → Beírom: "Interstellar" → Keresés → Kiválasztom → Látom: 12,4 GB → Letöltés
```

A családtagoknak soha nem kell qBittorrentet vagy nCore-t használniuk.

---

## Tartalom

1. [Hogyan működik](#1-hogyan-működik)
2. [Előfeltételek](#2-előfeltételek)
3. [Quick Start](#3-quick-start)
4. [Konfiguráció (`.env`)](#4-konfiguráció-env)
5. [qBittorrent beállítása](#5-qbittorrent-beállítása)
6. [Docker network: hogyan lássa egymást a két konténer](#6-docker-network-hogyan-lássa-egymást-a-két-konténer)
7. [Plex beállítása](#7-plex-beállítása)
8. [Első belépés](#8-első-belépés)
9. [Használat](#9-használat)
10. [Fejlesztés](#10-fejlesztés)
11. [Tesztek](#11-tesztek)
12. [Hibaelhárítás](#12-hibaelhárítás)
13. [Biztonság](#13-biztonság)
14. [Ismert korlátozások](#14-ismert-korlátozások)

---

## 1. Hogyan működik

```
Böngésző (családtag)
      │  csak a saját backendjét hívja
      ▼
Családi Plex webapp  ──►  nCore     (keresés, .torrent fájl letöltése)
      │
      └──────────────►  qBittorrent Web API  (torrent hozzáadása, vezérlés)
                              │
                              ▼
                      letöltési könyvtár
                              │
                              ▼
                            Plex
```

Fontos tulajdonságok:

- **A böngésző soha nem kommunikál az nCore-ral vagy a qBittorrenttel.** Minden
  hívás a backenden megy keresztül, így tracker- és qBittorrent-jelszó nem kerül
  a frontendbe.
- **Az alkalmazásnak nincs szüksége a fájlrendszerre.** A `.torrent` fájlt
  fájlfeltöltésként adja át a qBittorrentnek. Nem kell mountolni a média- vagy
  letöltési könyvtárat, és nem számít, hogy a qBittorrent konténer más
  útvonalakat lát.
- **A letöltési helyet mindig a qBittorrent határozza meg.** Az alkalmazás
  lekérdezi (`/api/v2/app/defaultSavePath`) és megmutatja, de saját útvonalat
  soha nem küld – a kliens pedig végképp nem adhat meg ilyet.
- **Egyetlen kód, egyetlen image.** A fejlesztői gép és a production szerver
  között kizárólag a `.env` tartalma tér el.

---

## 2. Előfeltételek

| Kell | Megjegyzés |
|---|---|
| Docker + Docker Compose | Docker Desktop (macOS/Windows) vagy Docker Engine (Linux) |
| Futó qBittorrent, bekapcsolt Web UI-jal | Ezt az alkalmazás **nem** telepíti és nem módosítja |
| nCore fiók | Csak olyan tartalomhoz használd, amelyre jogosultságod van |
| Plex (opcionális) | Az MVP nem hív Plex API-t |

Az image `linux/amd64` és `linux/arm64` alatt is épül (Apple Silicon M1 is jó),
mert minden alaprétege multi-arch, és nincs benne architektúrafüggő beállítás.

---

## 3. Quick Start

```bash
git clone <a-repo-url> csaladi-plex
cd csaladi-plex
cp .env.example .env
```

Ezután **három dolgot kell kitölteni** a `.env` fájlban:

**a) Titkos kulcs**

```bash
openssl rand -hex 32
```

Az eredményt írd az `APP_SECRET_KEY=` sor mögé.

**b) Belépési jelszó (bcrypt hash)**

```bash
docker compose run --rm app python -m app.cli hash-password
```

A parancs bekéri a jelszót (nem jelenik meg és nem kerül a shell
előzményekbe), és kiírja a beillesztendő `ADMIN_PASSWORD_HASH=...` sort.

**c) nCore és qBittorrent adatok**

```env
NCORE_USERNAME=...
NCORE_PASSWORD=...
QBITTORRENT_URL=http://qbittorrent:8080
QBITTORRENT_USERNAME=...
QBITTORRENT_PASSWORD=...
```

Végül:

```bash
docker compose up -d --build
```

Ellenőrzés:

```bash
docker compose run --rm app python -m app.cli check-login
docker compose run --rm app python -m app.cli check-qbittorrent
docker compose run --rm app python -m app.cli check-ncore
```

Ha mindkettő `OK`, nyisd meg: **http://\<szerver-ip\>:8000**

---

## 4. Konfiguráció (`.env`)

Minden környezetfüggő érték itt van; a kód sehol nem tartalmaz gépspecifikus
beállítást. A teljes, kommentezett listát lásd a [`.env.example`](.env.example)
fájlban. A leggyakrabban állított értékek:

| Változó | Jelentés |
|---|---|
| `APP_SECRET_KEY` | A munkamenet-sütik aláírására. Legalább 32 karakter. |
| `APP_PORT` | A hoston kiajánlott port (alap: 8000). |
| `COOKIE_SECURE` | `true`, ha HTTPS mögött fut. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` | Az első családtag. |
| `EXTRA_USERS` | További családtagok: `anya:$2b$...,gyerek:$2b$...` |
| `NCORE_USERNAME` / `NCORE_PASSWORD` | nCore belépés (csak a backend látja). |
| `NCORE_CATEGORIES` | `hd_hun` = Film HD/HU, `hdser_hun` = Sorozat HD/HU. Bővíthető: `hd_hun,hdser_hun,hd,hdser`. |
| `QBITTORRENT_URL` | A futó qBittorrent Web UI címe. |
| `QBITTORRENT_USERNAME` / `QBITTORRENT_PASSWORD` | qBittorrent Web UI belépés. |
| `QBITTORRENT_CATEGORY` | Opcionális címke az innen indított torrenteknek. |

> **Ne használj `localhost`-ot a `QBITTORRENT_URL`-ben.** A konténeren belül az
> saját magát jelentené. Használd a qBittorrent konténer nevét (közös hálózaton)
> vagy a szerver LAN IP-címét.

---

## 5. qBittorrent beállítása

A meglévő qBittorrentet **nem kell átalakítani**, csak ennyi kell:

1. **Web UI bekapcsolva** – *Tools → Options → Web UI*, és jegyezd fel a portot
   (alap: 8080), a felhasználónevet és a jelszót.
2. **Alapértelmezett letöltési könyvtár beállítva** – *Options → Downloads →
   Default Save Path*. Ezt fogja mutatni az alkalmazás a megerősítő ablakban,
   és ide kerülnek a filmek.
3. **A CSRF/host-fejléc ellenőrzés ne blokkolja a kérést.** Ha a qBittorrent
   nem a `localhost`-ról érhető el, a *Web UI → Enable Host header validation*
   opciónál vedd fel a használt hostnevet (pl. `qbittorrent`), vagy kapcsold ki
   ezt az ellenőrzést a belső hálózaton. A tünete: minden hívás 401-et ad.

Az alkalmazás **soha nem ír a qBittorrent beállításaiba**; csak olvassa a
verziót, az alapértelmezett letöltési útvonalat és a torrentlistát, illetve
hozzáad / szüneteltet / folytat / töröl torrenteket.

---

## 6. Docker network: hogyan lássa egymást a két konténer

### a) A qBittorrent ugyanabban a Compose projektben fut

Ilyenkor a szolgáltatásnév a hostnév:

```env
QBITTORRENT_URL=http://qbittorrent:8080
```

### b) A qBittorrent külön Compose projektben / külön hálózaton fut (jellemző eset)

Hozz létre egy közös, külső hálózatot, és tedd rá mindkét konténert.

```bash
docker network create media
```

A **meglévő** qBittorrent compose fájljában (ezt neked kell egyszer
kiegészítened – az alkalmazás nem nyúl hozzá):

```yaml
services:
  qbittorrent:
    networks:
      - default
      - media

networks:
  media:
    external: true
```

Majd a `docker-compose.yml` fájlunkban vedd ki a kommentet a két helyről:

```yaml
services:
  app:
    networks:
      - default
      - media

networks:
  media:
    external: true
```

Indítsd újra mindkettőt (`docker compose up -d`), és utána a
`QBITTORRENT_URL=http://qbittorrent:8080` működni fog. Ha a qBittorrent
konténer neve más, azt írd be.

### c) A qBittorrent nincs Dockerben, vagy nem akarsz közös hálózatot

Használd a szerver LAN IP-jét és a kiajánlott portot:

```env
QBITTORRENT_URL=http://192.168.1.10:8080
```

Linux hoston a `host.docker.internal` nem működik alapból; ha mégis kell:

```yaml
services:
  app:
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

---

## 7. Plex beállítása

Az MVP **nem** hív Plex API-t, és **nem mozgat vagy nevez át fájlokat**. Ehhez
a qBittorrent és a Plex konténernek ugyanazt a host-könyvtárat kell látnia,
lehetőleg **azonos konténerbeli útvonalon**:

```
host:        /srv/media
konténerek:  /media
             ├── /media/downloads   ← qBittorrent ide tölt
             └── /media/movies      ← Plex Movie library
```

Példa (a **te meglévő** qBittorrent és Plex compose fájljaidban):

```yaml
services:
  qbittorrent:
    volumes:
      - /srv/media:/media

  plex:
    volumes:
      - /srv/media:/media
```

Ezután a Plexben a Movie library forrása `/media/movies` legyen.

**Fontos:** a qBittorrent a `/media/downloads` könyvtárba tölt, tehát a fájlok
alapból nem a Plex library-ben landolnak. Két lehetőség:

1. **Legegyszerűbb:** vedd fel a `/media/downloads` mappát is a Plex Movie
   library forrásai közé. A Plex a legtöbb szokásos torrentnevet felismeri.
2. **Rendezettebb:** a letöltés végeztével kézzel (vagy később egy erre
   szánt modullal) mozgasd át a filmet a Plex által ajánlott szerkezetbe:
   `/media/movies/Interstellar (2014)/Interstellar (2014).mkv`.

Az MVP szándékosan nem automatizálja a mozgatást/átnevezést – ez a rész
megbízható megoldás nélkül több kárt okozna, mint hasznot.

---

## 8. Első belépés

1. Nyisd meg a `http://<szerver-ip>:8000` címet.
2. Írd be az `ADMIN_USERNAME` értékét és a hozzá tartozó jelszót (amiből a
   hash készült).
3. Nyilvános regisztráció nincs. További családtag felvétele:

```bash
docker compose run --rm app python -m app.cli hash-password
```

majd a `.env`-ben:

```env
EXTRA_USERS=anya:$2b$12$...,gyerek:$2b$12$...
```

és `docker compose up -d` az újraindításhoz.

---

## 9. Használat

**Keresés fül**

1. Írd be a film címét, nyomj a *Keresés* gombra.
2. A találatoknál látod a nevet, méretet, seed/leech számot, nyelvet és
   kategóriát.
3. Nyomj a *Letöltés* gombra.
4. A megerősítő ablakban látod a torrent pontos nevét, méretét és a
   letöltési helyet (a qBittorrent alapértelmezett könyvtárát), valamint –
   ha elérhető – a fájllistát.
5. *Letöltés indítása* → „Letöltés elindítva.”

**Letöltések fül**

Néhány másodpercenként automatikusan frissül. Látod a folyamatot, a le- és
feltöltési sebességet, az állapotot, a méretet és a hátralévő időt.
Szüneteltethető, folytatható és törölhető.

A *Törlés* alapértelmezés szerint **megtartja a letöltött fájlokat** – csak a
torrentet veszi ki a listából. A fájlok törléséhez külön megerősítés kell.

---

## 10. Fejlesztés

Ugyanaz a kód, ugyanaz az image, csak más `.env`. Nincs külön dev build.

### Kipróbálás valódi nCore / qBittorrent nélkül

A repóban van egy mock szerver, amely az nCore és a qBittorrent Web API
válaszait utánozza. **Ugyanabban az image-ben fut, csak más paranccsal**, így
a teljes felület végigpróbálható a production rendszerekhez való hozzáférés
nélkül.

```bash
cp .env.example .env
```

A `.env`-ben:

```env
APP_SECRET_KEY=<openssl rand -hex 32 eredménye>
ADMIN_USERNAME=teszt
ADMIN_PASSWORD_HASH=<a hash-password parancs kimenete>

NCORE_URL=http://mock:9080
NCORE_USERNAME=teszt
NCORE_PASSWORD=teszt

QBITTORRENT_URL=http://mock:9080
QBITTORRENT_USERNAME=teszt
QBITTORRENT_PASSWORD=teszt
```

Indítás:

```bash
docker compose --profile mock up -d --build
```

Nyisd meg a http://localhost:8000 címet, keress rá például az
`Interstellar` szóra, és indíts el egy „letöltést” – a Letöltések oldalon
látni fogod a (szimulált) haladást.

Leállítás:

```bash
docker compose --profile mock down
```

### Frontend hot reload (opcionális)

Ha a felületen dolgozol, a Vite dev szerver kényelmesebb:

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, az /api hívásokat a :8000-re proxyzza
```

A backend közben fusson Dockerben (`docker compose up -d`).

### Backend lokálisan, Docker nélkül

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

---

## 11. Tesztek

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

A tesztek hálózat nélkül futnak. Amit lefednek:

- az nCore HTML parser többféle találati oldalon (több találat, egy találat,
  „nincs találat”, hiányzó mezők, HTML entitások, ismeretlen szerkezet),
- a részletes oldal és a fájllista feldolgozása,
- méret-parsing (GiB/MiB, vesszős tizedes, ezres elválasztó, SI egységek),
- torrent ID és info-hash validáció (path traversal, injekció),
- az nCore kliens: login mezők, hibás belépés, lejárt munkamenet és újralogin,
- a qBittorrent wrapper: login, Referer fejléc, `stop`/`start` és a 4.x-es
  `pause`/`resume` fallback, hibakódok fordítása,
- jelszó-hash és munkamenet-token,
- CSRF védelem,
- az API végpontok és a magyar hibaüzenetek.

Van egy végponttól végpontig futó füstteszt is, amely elindítja a mock
szervert és végigjátssza a teljes folyamatot (belépés → keresés → részletek →
letöltés indítása → szüneteltetés → folytatás → törlés):

```bash
cd backend
python -m devtools.smoke_test
```

---

## 12. Hibaelhárítás

| Tünet | Ok / megoldás |
|---|---|
| „A qBittorrent nem érhető el.” | Rossz `QBITTORRENT_URL`, vagy a két konténer nem látja egymást. Ellenőrizd: `docker compose run --rm app python -m app.cli check-qbittorrent`, illetve a [6. pontot](#6-docker-network-hogyan-lássa-egymást-a-két-konténer). |
| „A qBittorrent bejelentkezés sikertelen.” | Rossz felhasználónév/jelszó, **vagy** a qBittorrent host-fejléc ellenőrzése blokkol (lásd [5. pont](#5-qbittorrent-beállítása)). Túl sok hibás próbálkozás után a qBittorrent IP-t is bannolhat – ilyenkor várni kell. |
| „Nem sikerült bejelentkezni az nCore-ra.” | Rossz `NCORE_USERNAME`/`NCORE_PASSWORD`. Ha a fiókon kétlépcsős azonosítás van, az jelenleg nem támogatott. |
| „Az nCore jelenleg nem érhető el.” | Hálózati hiba vagy karbantartás. |
| Keresés fut, de 0 találat mindenre | Elképzelhető, hogy az nCore megváltoztatta a találati oldal HTML szerkezetét. Lásd lentebb. |
| „Ez a torrent már szerepel a letöltések között.” | A qBittorrentben már megvan ugyanez a torrent. |
| „Nincs elég szabad tárhely a letöltéshez.” | A qBittorrent gépén nincs hely. |
| „Hibás felhasználónév vagy jelszó", pedig jó a jelszó | Fusson le: `docker compose run --rm app python -m app.cli check-login`. Ez megmondja, hogy a hash sérült-e, vagy csak a konténer újraindítása hiányzik. A leggyakoribb ok: a `.env` szerkesztése után nem futott `docker compose up -d`. |
| A bejelentkezés után azonnal kidob | Változott az `APP_SECRET_KEY` (a régi sütik érvénytelenek) – jelentkezz be újra. HTTPS mögött állítsd `COOKIE_SECURE=true`. |
| `env file .env not found` | Nem futott le a `cp .env.example .env`. |

### Ha az nCore megváltoztatja a HTML-t

A találati sorok feldolgozása reguláris kifejezésekkel történik, amelyek egy
helyen, a `backend/app/integrations/ncore.py` fájl `NcorePatterns` osztályában
vannak. Ha az oldal szerkezete változik, elég ezeket módosítani – a többi
réteghez nem kell hozzányúlni. A mintákat a `tests/fixtures/ncore_pages.py`
tesztadatokkal együtt érdemes frissíteni.

### Naplók

```bash
docker compose logs -f app
```

A naplóból a jelszavak automatikusan ki vannak maszkolva.

---

## 13. Biztonság

- Az nCore és a qBittorrent jelszava **kizárólag a backendben** él; a
  frontend API-válaszai nem tartalmaznak hitelesítési adatot.
- A `.env` a `.gitignore`-ban van, nem kerül a Git repóba és a Docker
  image-be sem (`.dockerignore`).
- A naplózás kimaszkolja a beállított titkokat.
- A jelszavak bcrypt hash-ként tárolódnak; plaintext jelszót sehol nem tárol
  az alkalmazás.
- A munkamenet HttpOnly + SameSite=Lax sütiben van; az írási műveletek
  dupla-submit CSRF tokent igényelnek.
- **A kliens nem adhat meg letöltési útvonalat.** A `save_path` mindig a
  qBittorrenttől jön; az alkalmazás nem is küld ilyen paramétert.
- **A kliens nem adhat meg URL-t.** A qBittorrent csak a backend által
  letöltött `.torrent` fájlt kapja meg, soha nem egy kliens által megadott
  címet (SSRF ellen).
- A torrent azonosító csak számjegy lehet, az info-hash csak hexadecimális –
  így path traversal és injekció kizárt.
- Az nCore felé menő kérések URL-jét a backend állítja össze, és ellenőrzi,
  hogy a beállított hoston maradnak.
- Nincs nyilvános regisztráció; a felhasználók forrása kizárólag a `.env`.

---

## 14. Ismert korlátozások

- **Az nCore HTML-t ad vissza, nem hivatalos API-t.** Ha az oldal szerkezete
  változik, a keresés eltörhet. Emiatt van külön, konfigurálható minta-réteg és
  parser-tesztkészlet.
- **Kétlépcsős azonosítás (2FA) az nCore-on nem támogatott.**
- Nincs automatikus fájlrendezés a Plex struktúrába (szándékosan – lásd a
  7. pontot).
- Nincs Plex API integráció (nincs library scan indítás).
- Nincs lapozás a találatokban: az első oldal jelenik meg, seed szerint
  csökkenő sorrendben, `NCORE_MAX_RESULTS` darabig.
- Csak film-kategóriákban keres (alapból HD/HU); sorozat nincs bekapcsolva.
- A letöltések oldal pollingot használ (3 mp), nem WebSocketet.
- Egyetlen nCore fiókkal dolgozik – az összes családtag ezen keresztül tölt.
