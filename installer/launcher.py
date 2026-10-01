"""Lanceur de BrikIA pour l'installation « application » (double-clic).

Usage :
    python launcher.py                  démarre BrikIA et ouvre le navigateur
    python launcher.py --no-browser     idem sans ouvrir le navigateur
    python launcher.py cli [--pause] <commande>   administration (backup, list-users, ...)

Dossier de travail (base de données, plans, ``.env``, sauvegardes) :
    Windows  %PROGRAMDATA%\\BrikIA     autre  ~/.local/share/brikia
    ou la variable BRIKIA_HOME. Il n'est jamais supprimé par une mise à jour
    ou une désinstallation.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _find_backend() -> Path:
    for base in (HERE, HERE.parent):  # installé : app/ ; dépôt : installer/ -> racine
        if (base / "backend" / "brikia").is_dir():
            return base / "backend"
    raise SystemExit("Installation incomplète : dossier « backend » introuvable.")


def default_home() -> Path:
    if os.environ.get("BRIKIA_HOME"):
        return Path(os.environ["BRIKIA_HOME"])
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "BrikIA"
    return Path.home() / ".local" / "share" / "brikia"


def _pause_if_console() -> None:
    if sys.stdin and sys.stdin.isatty():
        try:
            input("\nAppuyez sur Entrée pour fermer cette fenêtre…")
        except EOFError:
            pass


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=2) as r:  # noqa: S310
            return r.status == 200
    except Exception:  # noqa: BLE001 - toute erreur = pas (encore) prêt
        return False


def _lan_addresses() -> list[str]:
    import socket

    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    return sorted({i[4][0] for i in infos if not i[4][0].startswith("127.")})


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(_find_backend()))
    home = default_home()
    home.mkdir(parents=True, exist_ok=True)
    os.chdir(home)  # « .env » et « data » sont relatifs à ce dossier

    from brikia.cli import main as cli_main  # import après sys.path
    from brikia.config import get_settings

    if argv and argv[0] == "cli":
        pause = len(argv) > 1 and argv[1] == "--pause"
        code = cli_main(argv[2:] if pause else argv[1:])
        if pause:
            _pause_if_console()
        return code

    settings = get_settings()
    local_url = f"http://127.0.0.1:{settings.port}"
    open_browser = "--no-browser" not in argv

    if _healthy(local_url):  # déjà démarré : on ouvre simplement l'interface
        print(f"BrikIA est déjà en cours d'exécution : {local_url}")
        if open_browser:
            webbrowser.open(local_url)
        return 0

    print("BrikIA — pilotage de la ligne de production de briques")
    print(f"  Données : {home}")
    print(f"  Adresse : {local_url}")
    if settings.host not in ("127.0.0.1", "localhost"):
        for ip in _lan_addresses():
            print(f"  Autres PC du réseau : http://{ip}:{settings.port}")
    print("  Fermez cette fenêtre (ou Ctrl+C) pour arrêter BrikIA.\n")

    def _open_when_ready() -> None:
        for _ in range(240):
            if _healthy(local_url):
                if open_browser:
                    webbrowser.open(local_url)
                return
            time.sleep(0.5)

    threading.Thread(target=_open_when_ready, daemon=True).start()
    try:
        return cli_main(["serve"])
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f"\nImpossible de démarrer : {exc}\n"
              f"Le port {settings.port} est peut-être déjà utilisé par un autre programme "
              "(variable BRIKIA_PORT dans le fichier « .env »).", file=sys.stderr)
        _pause_if_console()
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"\nErreur au démarrage : {exc}", file=sys.stderr)
        _pause_if_console()
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()  # indispensable pour l'analyse isolée sous Windows
    sys.exit(main(sys.argv[1:]))
