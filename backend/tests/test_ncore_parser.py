"""Az nCore HTML parser tesztjei - hálózat nélkül."""

from __future__ import annotations

import pytest

from app.errors import InvalidTorrentIdError, TorrentNotFoundError
from app.integrations.ncore import (
    NcoreParser,
    NcorePatterns,
    parse_size,
    validate_torrent_id,
)
from tests.fixtures import ncore_pages as pages


@pytest.fixture
def parser() -> NcoreParser:
    return NcoreParser()


# --- találati lista -------------------------------------------------------


def test_parse_search_page_returns_all_rows(parser: NcoreParser) -> None:
    results = parser.parse_search_page(pages.SEARCH_RESULTS)
    assert len(results) == 3
    assert [r.id for r in results] == ["1234567", "7654321", "42"]


def test_parse_search_page_extracts_full_title(parser: NcoreParser) -> None:
    """A címet a title attribútumból vesszük, nem a levágott linkszövegből."""
    first = parser.parse_search_page(pages.SEARCH_RESULTS)[0]
    assert first.title == "Interstellar.2014.HUNGARIAN.1080p.BluRay.DTS.x264-CiNEFiLE"


def test_parse_search_page_sizes_and_peers(parser: NcoreParser) -> None:
    first = parser.parse_search_page(pages.SEARCH_RESULTS)[0]
    assert first.size_text == "12.42 GiB"
    assert first.size_bytes == int(12.42 * 1024**3)
    assert first.seeders == 42
    assert first.leechers == 3


def test_parse_search_page_maps_category_and_language(parser: NcoreParser) -> None:
    hun, eng, _ = parser.parse_search_page(pages.SEARCH_RESULTS)
    assert (hun.category, hun.language) == ("Film HD", "magyar")
    assert (eng.category, eng.language) == ("Film HD", "angol")


def test_parse_search_page_decodes_html_entities(parser: NcoreParser) -> None:
    third = parser.parse_search_page(pages.SEARCH_RESULTS)[2]
    assert third.title == "Szép és a Szörnyeteg 2017 HUN 720p"


def test_parse_search_page_single_result(parser: NcoreParser) -> None:
    results = parser.parse_search_page(pages.SINGLE_RESULT)
    assert len(results) == 1
    assert results[0].id == "999"
    # Ezres elválasztóval írt méret is működjön
    assert results[0].size_bytes == int(1023.50 * 1024**2)


def test_parse_search_page_no_results(parser: NcoreParser) -> None:
    assert parser.parse_search_page(pages.NO_RESULTS) == []


def test_parse_search_page_peers_without_links(parser: NcoreParser) -> None:
    results = parser.parse_search_page(pages.PLAIN_PEERS)
    assert len(results) == 1
    assert results[0].seeders == 17
    assert results[0].leechers == 4


def test_parse_search_page_unknown_structure_is_not_fatal(parser: NcoreParser) -> None:
    """Ha az oldal szerkezete megváltozik, üres listát kapunk, nem kivételt."""
    assert parser.parse_search_page(pages.BROKEN_PAGE) == []


def test_patterns_are_overridable() -> None:
    """A minták konfigurációból felülírhatók, ha az nCore HTML-je változik."""
    custom = NcorePatterns(row_size=r'<div class="uj_meret">(?P<size>.*?)</div>')
    parser = NcoreParser(custom)
    html = pages.SINGLE_RESULT.replace("box_meret2", "uj_meret")
    assert parser.parse_search_page(html)[0].size_text == "1 023.50 MiB"


# --- részletes oldal ------------------------------------------------------


def test_parse_detail_page(parser: NcoreParser) -> None:
    details = parser.parse_detail_page(pages.TORRENT_DETAILS, "1234567")
    assert details.id == "1234567"
    assert details.title == "Interstellar.2014.HUNGARIAN.1080p.BluRay.DTS.x264-CiNEFiLE"
    assert details.size_text == "12.42 GiB"
    assert details.size_bytes == int(12.42 * 1024**3)
    assert details.seeders == 42
    assert details.leechers == 3
    assert details.category == "Film HD"
    assert details.language == "magyar"


def test_parse_detail_page_files(parser: NcoreParser) -> None:
    files = parser.parse_detail_page(pages.TORRENT_DETAILS, "1234567").files
    assert [f.name for f in files] == [
        "Interstellar.2014.HUN.1080p.mkv",
        "Interstellar.2014.HUN.1080p.srt",
        "info.nfo",
    ]
    assert [f.kind for f in files] == ["videó", "felirat", "egyéb"]
    assert files[1].size_bytes == int(64.20 * 1024)


def test_parse_detail_page_without_files(parser: NcoreParser) -> None:
    details = parser.parse_detail_page(pages.DETAILS_NO_FILES, "555")
    assert details.files == []
    assert details.size_bytes == int(7.77 * 1024**3)


def test_parse_detail_page_missing_torrent(parser: NcoreParser) -> None:
    with pytest.raises(TorrentNotFoundError):
        parser.parse_detail_page(pages.DETAILS_MISSING, "1")


# --- RSS kulcs ------------------------------------------------------------


def test_parse_rss_key(parser: NcoreParser) -> None:
    assert parser.parse_rss_key(pages.SEARCH_RESULTS) == "abc123def456"
    assert parser.parse_rss_key(pages.LOGIN_SUCCESS) == "loginkey42"


def test_parse_rss_key_missing(parser: NcoreParser) -> None:
    assert parser.parse_rss_key(pages.BROKEN_PAGE) is None


# --- méret ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 B", 1),
        ("1 KiB", 1024),
        ("1.5 MiB", int(1.5 * 1024**2)),
        ("12.42 GiB", int(12.42 * 1024**3)),
        ("2 TiB", 2 * 1024**4),
        ("1,44 GiB", int(1.44 * 1024**3)),  # vesszős tizedes
        ("700 MB", 700 * 1000**2),  # SI egység
        ("12.42\xa0GiB", int(12.42 * 1024**3)),  # nem törő szóköz
        ("Méret: 4.7 GiB (5 046 586 572 bájt)", int(4.7 * 1024**3)),
    ],
)
def test_parse_size(text: str, expected: int) -> None:
    assert parse_size(text) == expected


@pytest.mark.parametrize("text", [None, "", "ismeretlen", "GiB", "sok"])
def test_parse_size_invalid(text: str | None) -> None:
    assert parse_size(text) is None


# --- torrent ID validáció -------------------------------------------------


@pytest.mark.parametrize("value", ["1", "42", "1234567", " 99 "])
def test_validate_torrent_id_accepts_numeric(value: str) -> None:
    assert validate_torrent_id(value) == value.strip()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "abc",
        "12a",
        "-1",
        "1.5",
        "../../etc/passwd",
        "1;rm -rf /",
        "1 OR 1=1",
        "http://evil.example/x",
        "%2e%2e%2f",
        "1" * 11,  # túl hosszú
    ],
)
def test_validate_torrent_id_rejects_everything_else(value: str) -> None:
    with pytest.raises(InvalidTorrentIdError):
        validate_torrent_id(value)
