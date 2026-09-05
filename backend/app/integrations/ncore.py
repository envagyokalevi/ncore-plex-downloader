"""nCore integráció.

MINDEN nCore-specifikus tudás (URL-ek, form mezők, HTML minták) kizárólag
ebben a modulban él. A modul kifelé csak normalizált adatot ad vissza
(`SearchResult`, `TorrentDetails`, illetve nyers .torrent bájtok).

A HTML szerkezet ismerete a jelenlegi nCore oldal felépítéséből származik
(találati sor: `box_meret2` / `box_s2` / `box_l2` div-ek, a torrent
azonosítója és neve a sor `onclick="torrent(ID)"` linkjéből, a kategória a
`categ_link` képre mutató `torrents.php?tipus=...` hivatkozásból, a letöltő
kulcs pedig az oldal RSS linkjéből). Ha az oldal változik, a lenti
`NcorePatterns` mezői konfigurációból felülírhatók anélkül, hogy a
szolgáltatásréteghez hozzá kellene nyúlni.

Biztonság:
  * A tracker cookie-k és a jelszó SOHA nem hagyják el a backendet.
  * Minden kimenő kérés a konfigurált nCore hosthoz megy - SSRF ellen a
    `_url()` ellenőrzi, hogy a végleges URL a beállított bázison marad-e.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence
from urllib.parse import urlencode, urlsplit

import httpx

from app.errors import (
    InvalidTorrentIdError,
    NcoreConfigError,
    NcoreLoginError,
    NcoreSearchError,
    NcoreUnavailableError,
    TorrentDownloadError,
    TorrentNotFoundError,
)
from app.models.schemas import SearchResult, TorrentDetails, TorrentFile

logger = logging.getLogger(__name__)

TORRENT_ID_RE = re.compile(r"^[0-9]{1,10}$")

#: nCore `tipus` érték -> (emberi kategórianév, nyelv)
CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "hd_hun": ("Film HD", "magyar"),
    "hd": ("Film HD", "angol"),
    "xvid_hun": ("Film SD", "magyar"),
    "xvid": ("Film SD", "angol"),
    "dvd_hun": ("Film DVD", "magyar"),
    "dvd": ("Film DVD", "angol"),
    "dvd9_hun": ("Film DVD9", "magyar"),
    "dvd9": ("Film DVD9", "angol"),
    "hdser_hun": ("Sorozat HD", "magyar"),
    "hdser": ("Sorozat HD", "angol"),
    "xvidser_hun": ("Sorozat SD", "magyar"),
    "xvidser": ("Sorozat SD", "angol"),
}

_UNIT_BYTES: dict[str, int] = {
    "B": 1,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
    "TIB": 1024**4,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
}

_SIZE_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*([KMGT]?i?B)", re.IGNORECASE)


def parse_size(text: str | None) -> int | None:
    """Méret szöveg (pl. "1.44 GiB") átváltása bájtra. Ismeretlen formátumnál None."""
    if not text:
        return None
    normalized = text.replace("\xa0", " ").strip()
    # Ezres elválasztó eltávolítása: "1 023.50 MiB" -> "1023.50 MiB"
    normalized = re.sub(r"(?<=\d) (?=\d)", "", normalized)
    match = _SIZE_RE.search(normalized)
    if not match:
        return None
    number = match.group(1).replace(",", ".")
    unit = match.group(2).upper()
    multiplier = _UNIT_BYTES.get(unit)
    if multiplier is None:
        return None
    try:
        return int(float(number) * multiplier)
    except ValueError:
        return None


def validate_torrent_id(torrent_id: str) -> str:
    """Csak számjegy lehet - így semmilyen útvonal vagy URL nem csempészhető be."""
    candidate = (torrent_id or "").strip()
    if not TORRENT_ID_RE.match(candidate):
        raise InvalidTorrentIdError()
    return candidate


@dataclass(frozen=True)
class NcorePatterns:
    """Az oldal HTML szerkezetéhez tartozó, felülírható reguláris kifejezések."""

    row_id_title: str = (
        r'onclick="torrent\((?P<id>[0-9]+)\);\s*return false;"\s*title="(?P<title>[^"]*)"'
    )
    row_size: str = r'<div class="box_meret2">(?P<size>.*?)</div>'
    row_seeders: str = r'<div class="box_s2">(?:<a[^>]*>)?(?P<seeders>[0-9]+)(?:</a>)?</div>'
    row_leechers: str = r'<div class="box_l2">(?:<a[^>]*>)?(?P<leechers>[0-9]+)(?:</a>)?</div>'
    row_category: str = r'torrents\.php\?tipus=(?P<category>[a-z0-9_]+)"><img[^>]*class="categ_link"'
    no_results: str = r'class="lista_mini_error"[^>]*>\s*Nincs\s+tal'
    rss_key: str = r"rss\.php\?key=(?P<key>[a-zA-Z0-9]+)"
    detail_title: str = r'<div class="torrent_reszletek_cim">(?P<title>.*?)</div>'
    detail_size: str = r'<div class="dd">(?P<size>[0-9][0-9.,]*\s*[KMGT]?i?B)\s*\('
    detail_seed_leech: str = (
        r'Seederek:</div>.*?<div class="dd">(?:<a[^>]*>)?(?P<seeders>[0-9]+)'
        r'.*?Leecherek:</div>.*?<div class="dd">(?:<a[^>]*>)?(?P<leechers>[0-9]+)'
    )
    detail_category: str = r'torrents\.php\?tipus=(?P<category>[a-z0-9_]+)"'
    detail_files: str = (
        r'<div class="fl_konyvtar_fajl_nev">(?P<name>.*?)</div>\s*'
        r'<div class="fl_konyvtar_fajl_meret">(?P<size>.*?)</div>'
    )
    login_failure: str = r"(hib[áa]s|sikertelen).{0,60}(jelsz[óo]|bel[ée]p)"

    def compiled(self, name: str) -> re.Pattern[str]:
        return re.compile(getattr(self, name), re.IGNORECASE | re.DOTALL)


@dataclass
class NcoreConfig:
    base_url: str = "https://ncore.pro"
    username: str = ""
    password: str = ""
    categories: Sequence[str] = ("hd_hun",)
    timeout: float = 20.0
    max_results: int = 50
    user_agent: str = "csaladi-plex/1.0"
    patterns: NcorePatterns = field(default_factory=NcorePatterns)


def _clean(text: str) -> str:
    """HTML entitások feloldása, tag-ek eltávolítása, whitespace normalizálás."""
    without_tags = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _file_kind(name: str) -> str:
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix in {"mkv", "mp4", "avi", "m2ts", "ts", "mov", "wmv", "mpg", "mpeg"}:
        return "videó"
    if suffix in {"srt", "sub", "idx", "ass", "ssa"}:
        return "felirat"
    if suffix in {"mp3", "flac", "ac3", "dts", "aac"}:
        return "hang"
    if suffix in {"nfo", "txt", "jpg", "png", "sfv"}:
        return "egyéb"
    return suffix or "fájl"


class NcoreParser:
    """Az nCore HTML válaszainak feldolgozása - hálózat nélkül tesztelhető."""

    def __init__(self, patterns: NcorePatterns | None = None) -> None:
        self.patterns = patterns or NcorePatterns()

    # --- találati lista ---

    def parse_search_page(self, html_text: str) -> list[SearchResult]:
        patterns = self.patterns
        if patterns.compiled("no_results").search(html_text):
            return []

        rows = list(patterns.compiled("row_id_title").finditer(html_text))
        if not rows:
            return []

        sizes = [m.group("size") for m in patterns.compiled("row_size").finditer(html_text)]
        seeders = [m.group("seeders") for m in patterns.compiled("row_seeders").finditer(html_text)]
        leechers = [
            m.group("leechers") for m in patterns.compiled("row_leechers").finditer(html_text)
        ]
        categories = [
            m.group("category") for m in patterns.compiled("row_category").finditer(html_text)
        ]

        results: list[SearchResult] = []
        for index, row in enumerate(rows):
            size_text = _clean(sizes[index]) if index < len(sizes) else None
            raw_category = categories[index] if index < len(categories) else None
            label, language = CATEGORY_LABELS.get(raw_category or "", (raw_category, None))
            results.append(
                SearchResult(
                    id=row.group("id"),
                    title=html.unescape(row.group("title")).strip(),
                    size_bytes=parse_size(size_text),
                    size_text=size_text or None,
                    category=label,
                    language=language,
                    seeders=_to_int(seeders[index] if index < len(seeders) else None),
                    leechers=_to_int(leechers[index] if index < len(leechers) else None),
                )
            )
        return results

    # --- részletes oldal ---

    def parse_detail_page(self, html_text: str, torrent_id: str) -> TorrentDetails:
        patterns = self.patterns
        title_match = patterns.compiled("detail_title").search(html_text)
        if not title_match:
            raise TorrentNotFoundError()

        size_match = patterns.compiled("detail_size").search(html_text)
        size_text = _clean(size_match.group("size")) if size_match else None

        peers = patterns.compiled("detail_seed_leech").search(html_text)
        category_match = patterns.compiled("detail_category").search(html_text)
        raw_category = category_match.group("category") if category_match else None
        label, language = CATEGORY_LABELS.get(raw_category or "", (raw_category, None))

        files: list[TorrentFile] = []
        for match in patterns.compiled("detail_files").finditer(html_text):
            name = _clean(match.group("name"))
            file_size_text = _clean(match.group("size"))
            if not name:
                continue
            files.append(
                TorrentFile(
                    name=name,
                    size_bytes=parse_size(file_size_text),
                    size_text=file_size_text or None,
                    kind=_file_kind(name),
                )
            )

        return TorrentDetails(
            id=torrent_id,
            title=_clean(title_match.group("title")),
            size_bytes=parse_size(size_text),
            size_text=size_text or None,
            category=label,
            language=language,
            seeders=_to_int(peers.group("seeders")) if peers else None,
            leechers=_to_int(peers.group("leechers")) if peers else None,
            files=files,
        )

    def parse_rss_key(self, html_text: str) -> str | None:
        match = self.patterns.compiled("rss_key").search(html_text)
        return match.group("key") if match else None


class NcoreClient:
    """Bejelentkezés-kezelő nCore kliens.

    A session (cookie-k) a backend memóriájában él, a böngésző soha nem
    kapja meg. Lejárt session esetén automatikusan újra bejelentkezik.
    """

    def __init__(self, config: NcoreConfig, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self.parser = NcoreParser(config.patterns)
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": config.user_agent},
            timeout=config.timeout,
            follow_redirects=True,
        )
        self._logged_in = False
        self._lock = asyncio.Lock()
        self._rss_key: str | None = None

    # --- alap ---

    @property
    def base_url(self) -> str:
        return self._config.base_url

    def _url(self, path: str, params: dict[str, str] | None = None) -> str:
        """URL összeállítása a konfigurált bázisról - SSRF ellen ellenőrizve."""
        url = f"{self._config.base_url}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params)}"
        base_host = urlsplit(self._config.base_url).netloc
        if urlsplit(url).netloc != base_host:
            raise NcoreSearchError(detail="URL host mismatch")
        return url

    def _require_credentials(self) -> None:
        if not self._config.username or not self._config.password:
            raise NcoreConfigError()

    async def aclose(self) -> None:
        await self._client.aclose()

    # --- login ---

    async def login(self, force: bool = False) -> None:
        self._require_credentials()
        async with self._lock:
            if self._logged_in and not force:
                return
            self._client.cookies.clear()
            data = {
                "set_lang": "hu",
                "submitted": "1",
                "nev": self._config.username,
                "pass": self._config.password,
                "ne_leptessen_ki": "1",
            }
            try:
                response = await self._client.post(self._url("login.php"), data=data)
            except httpx.HTTPError as exc:
                logger.warning("nCore login halozati hiba: %s", type(exc).__name__)
                raise NcoreUnavailableError(detail=str(exc)) from exc

            # Sikeres belépés jelei: az nCore átirányít a login.php-ről, és a
            # bejelentkezett oldalfejléc tartalmazza a személyes RSS linket.
            # Csak az egyiket nézni törékeny lenne, ezért mindkettőt vizsgáljuk.
            rss_key = self.parser.parse_rss_key(response.text)
            still_on_login = response.url.path.endswith("/login.php")
            explicit_error = self._config.patterns.compiled("login_failure").search(response.text)

            if explicit_error or (still_on_login and rss_key is None):
                logger.warning("nCore bejelentkezes elutasitva (HTTP %s)", response.status_code)
                raise NcoreLoginError()

            self._logged_in = True
            self._rss_key = rss_key
            logger.info("nCore bejelentkezes sikeres")

    async def _get(self, url: str, *, retry: bool = True) -> httpx.Response:
        """GET bejelentkezett sessionnel; lejárat esetén egyszer újrapróbál."""
        if not self._logged_in:
            await self.login()
        try:
            response = await self._client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("nCore keres halozati hiba: %s", type(exc).__name__)
            raise NcoreUnavailableError(detail=str(exc)) from exc

        if "login.php" in str(response.url):
            if not retry:
                raise NcoreLoginError()
            logger.info("nCore session lejart, ujra bejelentkezes")
            self._logged_in = False
            await self.login(force=True)
            return await self._get(url, retry=False)
        return response

    # --- publikus műveletek ---

    async def search_movies(self, query: str) -> list[SearchResult]:
        """Keresés a konfigurált film-kategóriákban (alapértelmezés: HD/HU)."""
        query = (query or "").strip()
        if not query:
            return []

        results: list[SearchResult] = []
        seen: set[str] = set()
        for category in self._config.categories:
            for item in await self._search_one_category(query, category):
                if item.id in seen:
                    continue
                seen.add(item.id)
                results.append(item)

        results.sort(key=lambda r: (r.seeders or 0), reverse=True)
        return results[: self._config.max_results]

    async def _search_one_category(self, query: str, category: str) -> list[SearchResult]:
        url = self._url(
            "torrents.php",
            {
                "oldal": "1",
                "tipus": category,
                "miszerint": "seeders",
                "hogyan": "DESC",
                "mire": query,
                "miben": "name",
            },
        )
        response = await self._get(url)
        if response.status_code >= 400:
            logger.warning("nCore kereses HTTP %s", response.status_code)
            raise NcoreSearchError(detail=f"HTTP {response.status_code}")
        if self._rss_key is None:
            self._rss_key = self.parser.parse_rss_key(response.text)
        try:
            return self.parser.parse_search_page(response.text)
        except Exception as exc:  # a HTML szerkezete változhatott
            logger.exception("nCore talalati oldal feldolgozasa sikertelen")
            raise NcoreSearchError(detail=str(exc)) from exc

    async def get_torrent_details(self, torrent_id: str) -> TorrentDetails:
        torrent_id = validate_torrent_id(torrent_id)
        url = self._url("torrents.php", {"action": "details", "id": torrent_id})
        response = await self._get(url)
        if response.status_code == 404:
            raise TorrentNotFoundError()
        if response.status_code >= 400:
            raise NcoreSearchError(detail=f"HTTP {response.status_code}")
        if self._rss_key is None:
            self._rss_key = self.parser.parse_rss_key(response.text)
        return self.parser.parse_detail_page(response.text, torrent_id)

    async def get_torrent(self, torrent_id: str) -> bytes:
        """A .torrent fájl nyers tartalma."""
        torrent_id = validate_torrent_id(torrent_id)
        key = await self._ensure_rss_key()
        params = {"action": "download", "id": torrent_id}
        if key:
            params["key"] = key
        response = await self._get(self._url("torrents.php", params))

        if response.status_code == 404:
            raise TorrentNotFoundError()
        if response.status_code >= 400:
            logger.warning("nCore torrent letoltes HTTP %s", response.status_code)
            raise TorrentDownloadError(detail=f"HTTP {response.status_code}")

        content = response.content
        if not content.startswith(b"d"):  # bencode szótár kezdete
            logger.warning(
                "Az nCore nem .torrent fajlt adott vissza (content-type=%s)",
                response.headers.get("content-type", "?"),
            )
            raise TorrentDownloadError()
        return content

    async def _ensure_rss_key(self) -> str | None:
        if self._rss_key:
            return self._rss_key
        response = await self._get(self._url("index.php"))
        self._rss_key = self.parser.parse_rss_key(response.text)
        return self._rss_key


def build_client(
    *,
    base_url: str,
    username: str,
    password: str,
    categories: Iterable[str],
    timeout: float,
    max_results: int,
) -> NcoreClient:
    return NcoreClient(
        NcoreConfig(
            base_url=base_url,
            username=username,
            password=password,
            categories=tuple(categories) or ("hd_hun",),
            timeout=timeout,
            max_results=max_results,
        )
    )
