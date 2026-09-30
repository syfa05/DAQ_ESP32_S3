"""Logs techniques locaux (distincts de l'ActionLog métier).

Aucun mot de passe, hash ou jeton de session ne doit être journalisé.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import Settings

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(settings: Settings) -> None:
    settings.ensure_dirs()
    root = logging.getLogger("brikia")
    root.setLevel(settings.log_level.upper())
    if any(getattr(h, "_brikia", False) for h in root.handlers):
        return  # déjà configuré (rechargement, tests)
    fh = RotatingFileHandler(
        settings.logs_dir / "brikia.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    sh = logging.StreamHandler()
    for h in (fh, sh):
        h.setFormatter(logging.Formatter(_FORMAT))
        h._brikia = True  # type: ignore[attr-defined]
        root.addHandler(h)
