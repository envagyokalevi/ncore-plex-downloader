"""Naplózás beállítása titok-szűréssel.

A `SecretFilter` minden log rekordból (üzenet és argumentumok) kimaszkolja a
konfigurált titkokat, így az nCore / qBittorrent jelszó véletlenül sem
kerülhet a logba.
"""

from __future__ import annotations

import logging
from typing import Iterable

MASK = "***"


class SecretFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def _scrub(self, value: str) -> str:
        for secret in self._secrets:
            if secret in value:
                value = value.replace(secret, MASK)
        return value

    def _scrub_arg(self, value: object) -> object:
        """Csak a szöveges argumentumokat maszkoljuk.

        A számokat érintetlenül hagyjuk, különben a `%d` formázás eltörne.
        """
        return self._scrub(value) if isinstance(value, str) else value

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        if isinstance(record.msg, str):
            record.msg = self._scrub(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._scrub_arg(v) for k, v in record.args.items()}
            else:
                record.args = tuple(self._scrub_arg(a) for a in record.args)
        return True


def setup_logging(level: str, secrets: Iterable[str]) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    secret_filter = SecretFilter(secrets)
    for handler in logging.getLogger().handlers:
        handler.addFilter(secret_filter)
    # A httpx a kérés URL-jét logolná – az tartalmazhat nCore kulcsot.
    logging.getLogger("httpx").setLevel(logging.WARNING)
