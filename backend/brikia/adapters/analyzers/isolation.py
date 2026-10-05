"""Exécute une analyse de plan dans un PROCESSUS SÉPARÉ, avec délai maximal.

Pourquoi : IfcOpenShell, Open CASCADE et ezdxf analysent des fichiers fournis par des utilisateurs.
Dans le processus du serveur, un fichier malformé qui ferait planter le code natif (segfault) arrêterait
BrikIA entier, et un fichier pathologique pourrait bloquer un worker indéfiniment. Isolé, le pire cas est
un message d'erreur en français : le serveur, les autres utilisateurs et le projet ne sont pas touchés.

Méthode de démarrage « spawn » (sûre avec des bibliothèques natives et multiplateforme). Le résultat
revient par un tube ; ``ProjectGeometry`` est composé de dataclasses simples, donc sérialisable.
"""

from __future__ import annotations

import logging
import multiprocessing
import threading
from collections.abc import Callable
from typing import Any

from ...domain.errors import AnalysisFailed
from .base import AnalyzerUnavailable

log = logging.getLogger("brikia.analyzers.isolation")

# Au plus N analyses simultanées : chacune peut occuper plusieurs centaines de Mo.
_SLOTS = threading.BoundedSemaphore(2)


def _entry(conn, target: Callable[..., Any], args: tuple) -> None:  # noqa: ANN001
    """Point d'entrée du processus fils : jamais d'exception non capturée."""
    try:
        conn.send(("ok", target(*args)))
    except AnalysisFailed as exc:
        conn.send(("fail", exc.message))
    except AnalyzerUnavailable as exc:
        conn.send(("unavailable", exc.label, exc.package))
    except BaseException as exc:  # noqa: BLE001 - le parent décide du message affiché
        conn.send(("error", f"{type(exc).__name__}: {exc}"[:500]))
    finally:
        conn.close()


def run_isolated(target: Callable[..., Any], args: tuple, timeout_s: float, what: str = "plan") -> Any:
    ctx = multiprocessing.get_context("spawn")
    with _SLOTS:
        receiver, sender = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=_entry, args=(sender, target, args), daemon=True)
        proc.start()
        sender.close()
        try:
            message = receiver.recv() if receiver.poll(timeout_s) else "timeout"
        except (EOFError, OSError):
            message = None   # le fils est mort sans répondre
        finally:
            receiver.close()
        proc.join(3)
        if proc.is_alive():
            proc.kill()
            proc.join()

    if message == "timeout":
        log.warning("Analyse %s interrompue après %.0f s", what, timeout_s)
        raise AnalysisFailed(
            f"L'analyse de ce {what} a dépassé {int(timeout_s)} secondes et a été interrompue : "
            "le fichier est trop volumineux ou trop complexe. Le projet n'a pas été modifié."
        )
    if message is None:
        log.error("Processus d'analyse %s terminé brutalement (code %s)", what, proc.exitcode)
        raise AnalysisFailed(
            f"Le traitement de ce {what} s'est interrompu de façon inattendue (fichier corrompu ou trop "
            "complexe). Le projet n'a pas été modifié."
        )
    kind = message[0]
    if kind == "ok":
        return message[1]
    if kind == "fail":
        raise AnalysisFailed(message[1])
    if kind == "unavailable":
        raise AnalyzerUnavailable(message[1], message[2])
    log.error("Analyse %s : erreur inattendue dans le processus fils : %s", what, message[1])
    raise AnalysisFailed("L'analyse du plan a échoué. Le projet n'a pas été modifié.")
