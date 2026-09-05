"""A napló titok-szűrőjének tesztjei.

Az nCore / qBittorrent jelszó soha nem kerülhet a logba.
"""

from __future__ import annotations

import logging

import pytest

from app.logging_setup import MASK, SecretFilter


def make_record(msg: str, args: object = ()) -> logging.LogRecord:
    return logging.LogRecord(
        name="teszt", level=logging.INFO, pathname=__file__, lineno=1, msg=msg, args=args, exc_info=None
    )


def test_masks_secret_in_message() -> None:
    record = make_record("belepes jelszoval: sup3r-titok")
    SecretFilter(["sup3r-titok"]).filter(record)
    assert "sup3r-titok" not in record.getMessage()
    assert MASK in record.getMessage()


def test_masks_secret_in_string_args() -> None:
    record = make_record("ertek: %s", ("sup3r-titok",))
    SecretFilter(["sup3r-titok"]).filter(record)
    assert record.getMessage() == f"ertek: {MASK}"


def test_numeric_args_are_left_intact() -> None:
    """A számokat nem szabad stringgé alakítani, mert a %d formázás eltörne."""
    record = make_record("Kereses: '%s' -> %d talalat", ("Interstellar", 3))
    SecretFilter(["sup3r-titok"]).filter(record)
    assert record.getMessage() == "Kereses: 'Interstellar' -> 3 talalat"


def test_dict_args_are_masked() -> None:
    # A logging egyetlen dict argumentumot mappingként kezel.
    record = make_record("%(jelszo)s", ({"jelszo": "sup3r-titok"},))
    SecretFilter(["sup3r-titok"]).filter(record)
    assert record.getMessage() == MASK


def test_multiple_secrets_longest_first() -> None:
    record = make_record("a=titok-hosszabb b=titok")
    SecretFilter(["titok", "titok-hosszabb"]).filter(record)
    message = record.getMessage()
    assert "titok-hosszabb" not in message
    assert message == f"a={MASK} b={MASK}"


@pytest.mark.parametrize("secrets", [[], [""], ["ab"]])
def test_short_or_empty_secrets_are_ignored(secrets: list[str]) -> None:
    """Rövid/üres titkokra nem szűrünk, különben mindent kimaszkolnánk."""
    record = make_record("ab cd ef")
    SecretFilter([s for s in secrets if len(s) > 3]).filter(record)
    assert record.getMessage() == "ab cd ef"


def test_settings_expose_all_secrets(monkeypatch) -> None:
    from app.config import Settings

    settings = Settings(
        ncore_password="ncore-titkos-jelszo",
        qbittorrent_password="qbit-titkos-jelszo",
        app_secret_key="app-titkos-kulcs",
        admin_password_hash="$2b$12$hash-ertek",
    )
    assert set(settings.secrets) == {
        "ncore-titkos-jelszo",
        "qbit-titkos-jelszo",
        "app-titkos-kulcs",
        "$2b$12$hash-ertek",
    }
