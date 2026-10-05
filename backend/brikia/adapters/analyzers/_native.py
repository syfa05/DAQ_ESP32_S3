"""Neutralise les écritures parasites des bibliothèques natives (C++) sur la sortie standard.

IfcOpenShell / Open CASCADE impriment parfois des milliers de lignes de débogage
directement sur le descripteur 1 : le module ``logging`` ne les voit pas et elles
noieraient les logs du serveur. On redirige donc le descripteur 1 vers /dev/null
pendant le calcul géométrique.

Un verrou global est indispensable : deux analyses simultanées qui sauvegarderaient
le descripteur en même temps pourraient laisser la sortie standard détournée
définitivement.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager

_LOCK = threading.RLock()


@contextmanager
def silence_native_stdout() -> Iterator[None]:
    with _LOCK:
        try:
            sys.stdout.flush()
        except Exception:  # stdout fermé ou remplacé : rien à préserver
            pass
        try:
            saved = os.dup(1)
        except OSError:  # descripteur 1 indisponible (service sans console)
            yield
            return
        devnull = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(devnull, 1)
            yield
        finally:
            os.dup2(saved, 1)
            os.close(saved)
            os.close(devnull)
