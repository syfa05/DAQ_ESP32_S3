"""Commandes d'administration : ``python -m brikia.cli <commande>``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .backup import BackupError, create_backup, restore_backup
from .config import get_settings
from .migrate import upgrade


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brikia", description="Administration BrikIA")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="Applique les migrations (crée la base si absente)")
    p_b = sub.add_parser("backup", help="Crée une sauvegarde (base + plans importés)")
    p_b.add_argument("--dest", type=Path, help="Fichier zip de destination")
    p_r = sub.add_parser("restore", help="Restaure une sauvegarde (application arrêtée !)")
    p_r.add_argument("archive", type=Path)
    p_r.add_argument("--yes", action="store_true", help="Confirme l'écrasement des données")
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        if args.cmd == "migrate":
            upgrade(settings)
            print(f"Base à jour : {settings.db_path}")
        elif args.cmd == "backup":
            print(f"Sauvegarde créée : {create_backup(settings, args.dest)}")
        elif args.cmd == "restore":
            if not args.yes:
                print("Refusé : cette opération écrase les données actuelles. "
                      "Arrêtez l'application puis relancez avec --yes.", file=sys.stderr)
                return 2
            safety = restore_backup(settings, args.archive)
            print(f"Restauration terminée. Copie de sécurité : {safety}")
    except BackupError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
