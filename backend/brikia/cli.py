"""Commandes d'administration : ``python -m brikia.cli <commande>``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .backup import BackupError, create_backup, restore_backup
from .config import get_settings
from .domain.enums import Role
from .domain.errors import DomainError
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
    sub.add_parser("serve", help="Démarre le serveur (BRIKIA_HOST / BRIKIA_PORT)")
    sub.add_parser("seed", help="Charge les données de DÉMONSTRATION (comptes + un projet par statut)")
    p_u = sub.add_parser("create-user", help="Crée un compte (mot de passe saisi au clavier)")
    p_u.add_argument("--login", required=True)
    p_u.add_argument("--nom", required=True)
    p_u.add_argument("--role", required=True, choices=[r.value for r in Role])
    sub.add_parser("list-users", help="Liste les comptes")
    p_p = sub.add_parser("reset-password", help="Définit un nouveau mot de passe (saisi au clavier)")
    p_p.add_argument("--login", required=True)
    p_a = sub.add_parser("set-active", help="Active ou désactive un compte")
    p_a.add_argument("--login", required=True)
    p_a.add_argument("--off", action="store_true", help="Désactive (sinon : active)")
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        if args.cmd == "migrate":
            upgrade(settings)
            print(f"Base à jour : {settings.db_path}")
        elif args.cmd == "serve":
            import uvicorn

            from .main import create_app

            upgrade(settings)
            # Un seul worker : SQLite n'a qu'un écrivain et la limitation
            # des essais de connexion est en mémoire.
            uvicorn.run(
                create_app(settings), host=settings.host, port=settings.port,
                proxy_headers=settings.behind_proxy,
                forwarded_allow_ips="127.0.0.1" if settings.behind_proxy else None,
            )
        elif args.cmd == "seed":
            from .db import init_db, session_scope
            from .seed import seed_demo

            upgrade(settings)
            init_db(settings)
            with session_scope() as db:
                report = seed_demo(db, settings)
            print("Données de démonstration (développement uniquement).")
            for name in report.created_projects:
                print(f"  projet créé : {name}")
            for name in report.skipped_projects:
                print(f"  projet déjà présent : {name}")
            if report.new_passwords:
                print("\nComptes créés — mots de passe affichés UNE SEULE FOIS, notez-les :")
                for login, pwd in report.new_passwords.items():
                    print(f"  {login:<10} {pwd}")
            for login in report.existing_users:
                print(f"  compte « {login} » déjà présent : mot de passe inchangé")
        elif args.cmd == "create-user":
            import getpass

            from .db import init_db, session_scope
            from .services.auth import create_user

            upgrade(settings)
            init_db(settings)
            password = getpass.getpass("Mot de passe : ")
            if password != getpass.getpass("Confirmation : "):
                print("Erreur : les mots de passe diffèrent.", file=sys.stderr)
                return 1
            with session_scope() as db:
                create_user(db, nom=args.nom, login=args.login, password=password,
                            role=Role(args.role))
            print(f"Compte créé : {args.login}")
        elif args.cmd in ("list-users", "reset-password", "set-active"):
            import getpass

            from sqlalchemy import select

            from .db import init_db, session_scope
            from .models import User
            from .services import users as users_service

            upgrade(settings)
            init_db(settings)
            with session_scope() as db:
                if args.cmd == "list-users":
                    for u in users_service.list_users(db):
                        print(f"  {u.login:<20} {u.role:<12} {'actif' if u.actif else 'DÉSACTIVÉ':<10} {u.nom}")
                    return 0
                user = db.scalar(select(User).where(User.login == args.login.strip().lower()))
                if user is None:
                    print(f"Erreur : compte « {args.login} » introuvable.", file=sys.stderr)
                    return 1
                if args.cmd == "set-active":
                    users_service.set_active(db, None, user.id, not args.off)
                    print(f"Compte « {user.login} » {'désactivé' if args.off else 'activé'}.")
                else:
                    password = getpass.getpass("Nouveau mot de passe : ")
                    if password != getpass.getpass("Confirmation : "):
                        print("Erreur : les mots de passe diffèrent.", file=sys.stderr)
                        return 1
                    users_service.reset_password(db, None, user.id, password)
                    print(f"Mot de passe de « {user.login} » modifié.")
        elif args.cmd == "backup":
            print(f"Sauvegarde créée : {create_backup(settings, args.dest)}")
        elif args.cmd == "restore":
            if not args.yes:
                print("Refusé : cette opération écrase les données actuelles. "
                      "Arrêtez l'application puis relancez avec --yes.", file=sys.stderr)
                return 2
            safety = restore_backup(settings, args.archive)
            print(f"Restauration terminée. Copie de sécurité : {safety}")
    except (BackupError, DomainError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
