# BrikIA — phase 1 (en cours de construction)

Cerveau logiciel de la ligne de production de briques (BTC / parpaings autobloquants).
Monolithe modulaire : FastAPI + SQLAlchemy + SQLite + Alembic, interface Jinja2 + JS léger.
Fonctionne hors connexion. Accès prévu : PC industriel **et** postes autorisés du réseau
local (HTTP local, HTTPS ultérieur via reverse proxy).

> Ce dépôt hébergeait auparavant une note sur une carte d'acquisition ESP32-S3 ; le README
> a été remplacé par celui de BrikIA.

## Installation (développement)

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m brikia.cli migrate      # crée data/brikia.db
.venv/bin/pytest
```

## Configuration (variables d'environnement `BRIKIA_*`)

| Variable | Défaut | Rôle |
|---|---|---|
| `BRIKIA_HOST` | `127.0.0.1` | Interface d'écoute (`0.0.0.0` ou IP LAN pour le déploiement réseau) |
| `BRIKIA_PORT` | `8000` | Port |
| `BRIKIA_ALLOWED_HOSTS` | `*` | Noms/IP acceptés dans l'en-tête Host (CSV) |
| `BRIKIA_BEHIND_PROXY` | `false` | `true` derrière un reverse proxy HTTPS local |
| `BRIKIA_COOKIE_SECURE` | `false` | `true` dès que l'accès se fait en HTTPS |
| `BRIKIA_DATA_DIR` | `data` | Base, plans importés, sauvegardes, logs |
| `BRIKIA_MAX_UPLOAD_MB` | `50` | Taille max d'un plan (`.step .stp .ifc .pdf`) |

## Sauvegarde / restauration (multiplateforme)

```bash
python -m brikia.cli backup                       # -> data/backups/brikia-<date>.zip
python -m brikia.cli restore <archive.zip> --yes  # application arrêtée ; copie de sécurité automatique
```

## Comptes et démarrage

```bash
python -m brikia.cli create-user --login chef --nom "Nom Prénom" --role chef_projet   # mot de passe saisi au clavier
python -m brikia.cli serve      # applique les migrations puis écoute sur BRIKIA_HOST:BRIKIA_PORT
```

Rôles : `chef_projet`, `operateur`. Authentification par session serveur (cookie `HttpOnly`,
`SameSite=Strict`, `Secure` si `BRIKIA_COOKIE_SECURE=true`) + jeton CSRF (`X-CSRF-Token`) sur toute
requête modifiante. Les permissions sont contrôlées côté backend par `require_role(...)`.
Limitation des essais de connexion : 5 échecs / 60 s par identifiant.

Les sections utilisation, architecture, éléments simulés, phases futures et
déploiement/pare-feu seront complétées au fil des incréments.
