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
| `BRIKIA_SIM_BLOCKS_PER_SECOND` | `40` | Cadence de la ligne **simulée** (démo) |
| `BRIKIA_SIM_FAULT_AT_PERCENT` | *(aucun)* | Provoque un défaut simulé à ce % d'avancement (1-99) |
| `BRIKIA_LAYOUT_RULES_FILE` | *(aucun)* | JSON de surcharge des règles de calepinage **temporaires** (voir `adapters/layout/rules_config.py`) |

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

## Interface

Pages Jinja2 (coquilles) + JavaScript léger en modules ES, sans build ni framework. Toutes les
données passent par l'API JSON ; le JS ne porte aucune règle métier (les transitions et
permissions sont validées côté backend). Tout est servi localement : CSS, JS et polices
(Oswald, IBM Plex Mono, Inter — licence SIL OFL, voir `static/fonts/LICENSE-*.txt`).
La CSP interdit scripts et styles inline : les valeurs dynamiques (barres de progression, mise
à l'échelle des schémas) sont posées via le CSSOM.

| Page | Rôle | Contenu |
|---|---|---|
| `/connexion` | tous | Authentification |
| `/` | tous | Pipeline (chef : 6 colonnes ; opérateur : validés / en production / terminés) |
| `/projets/nouveau` | chef | Import d'un plan |
| `/projets/{id}` | tous (filtré) | Étapes, murs, calepinage IA, BOM, schéma des murs, validation / lancement |
| `/moules` | tous ; CRUD chef | Bibliothèque de moules |
| `/production` | tous | Suivi en direct des ordres |
| `/journal` | chef | Journal d'audit (ActionLog) |

Les pages masquent les actions interdites par confort ; la protection réelle est celle de l'API.

Les sections utilisation, architecture, éléments simulés, phases futures et
déploiement/pare-feu seront complétées au fil des incréments.
