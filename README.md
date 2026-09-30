# BrikIA — phase 1

Cerveau logiciel de la ligne de production de briques de terre comprimée (BTC) et de
parpaings autobloquants. BrikIA relie le plan de l'architecte, le calepinage, la nomenclature
(BOM), la validation par le chef de projet et l'ordre de fabrication.

**Phase 1 = application locale complète, sans machine réelle** : FastAPI + SQLite + Alembic,
interface Jinja2 + JavaScript léger, entièrement en français, **fonctionnement 100 % hors
connexion**. L'analyse de plan, le calepinage « IA » (moteur de règles) et la production sont
**simulés ou temporaires** — voir [docs/simule-et-futur.md](docs/simule-et-futur.md).

> BrikIA ne porte **aucune** logique de sécurité machine : cycle, verrouillages et arrêts
> d'urgence restent de la seule responsabilité de l'automate.

## Prérequis

- Python **3.11 ou plus** (Linux, macOS ou Windows).
- Accès Internet **uniquement pour l'installation** des dépendances (`pip`). L'application, elle,
  n'utilise jamais Internet. Pour un PC sans Internet : `pip download` sur une machine connectée,
  puis installation depuis le dossier de paquets.

## Installation

Depuis la racine du dépôt :

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

```powershell
# Windows (PowerShell)
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

> Installer avec `-e` (mode éditable) : les migrations et les ressources sont lues depuis le dépôt.
> Lancer toutes les commandes suivantes **depuis la racine du dépôt** (le dossier `data/` y est relatif).

## Démarrage rapide

```bash
python -m brikia.cli migrate     # crée data/brikia.db (schéma + bibliothèque de moules initiale)
python -m brikia.cli seed        # DÉMO : 2 comptes + 1 projet par statut
python -m brikia.cli serve       # http://127.0.0.1:8000
```

`seed` affiche **une seule fois** les mots de passe générés des comptes de démonstration
(`chef` et `operateur`) : notez-les. Ils ne sont écrits nulle part dans le dépôt ni en clair en
base. Pour les choisir vous-même : `BRIKIA_SEED_CHEF_PASSWORD` / `BRIKIA_SEED_OPERATEUR_PASSWORD`.
**Ne pas utiliser `seed` sur une installation de production.**

Créer un compte réel (mot de passe saisi au clavier) :

```bash
python -m brikia.cli create-user --login jdupont --nom "Jean Dupont" --role chef_projet
# rôles : chef_projet | operateur
```

Le projet de démonstration « en production » avance en temps réel et se termine tout seul
(environ 2 minutes à la cadence par défaut ; ralentir avec `BRIKIA_SIM_BLOCKS_PER_SECOND=2`).
Pour repartir de zéro : arrêter l'application, supprimer `data/brikia.db*`, relancer `migrate` puis `seed`.

## Configuration

Variables d'environnement `BRIKIA_*`, ou fichier `.env` à la racine (modèle : [.env.example](.env.example)).

| Variable | Défaut | Rôle |
|---|---|---|
| `BRIKIA_HOST` | `127.0.0.1` | Interface d'écoute. `0.0.0.0` ou l'IP LAN pour le réseau d'usine |
| `BRIKIA_PORT` | `8000` | Port |
| `BRIKIA_ALLOWED_HOSTS` | `*` | Noms/IP acceptés dans l'en-tête Host (CSV) — à renseigner en LAN |
| `BRIKIA_BEHIND_PROXY` | `false` | `true` derrière un reverse proxy HTTPS local |
| `BRIKIA_COOKIE_SECURE` | `false` | `true` dès que l'accès se fait en HTTPS |
| `BRIKIA_COOKIE_SAMESITE` | `strict` | `strict` ou `lax` |
| `BRIKIA_SESSION_TTL_HOURS` | `12` | Durée d'une session |
| `BRIKIA_DATA_DIR` | `data` | Base, plans importés, sauvegardes, logs |
| `BRIKIA_DATABASE_URL` | *(SQLite dans `DATA_DIR`)* | URL SQLAlchemy (migrations validées sur SQLite uniquement) |
| `BRIKIA_MAX_UPLOAD_MB` | `50` | Taille max d'un plan (`.step .stp .ifc .pdf`) |
| `BRIKIA_LAYOUT_RULES_FILE` | *(aucun)* | JSON de surcharge des règles de calepinage **temporaires** |
| `BRIKIA_SIM_BLOCKS_PER_SECOND` | `40` | Cadence de la ligne **simulée** |
| `BRIKIA_SIM_FAULT_AT_PERCENT` | *(aucun)* | Défaut simulé à ce % d'avancement (1-99) |
| `BRIKIA_LOG_LEVEL` | `INFO` | Niveau des logs techniques (`data/logs/brikia.log`) |

Déploiement en réseau local (écoute réseau, pare-feu, HTTPS via reverse proxy, service au
démarrage) : [docs/deploiement.md](docs/deploiement.md).

## Utilisation

Résumé : le **chef de projet** importe un plan, lance l'analyse puis le calepinage, consulte la
BOM et valide ; l'**opérateur** voit les projets validés, lance la production et suit sa progression
jusqu'à `termine`. Guide détaillé : [docs/utilisation.md](docs/utilisation.md).

```
a_analyser → a_optimiser → a_valider → valide → en_production → termine
```

## Tests

```bash
pytest          # 263 tests, aucun accès Internet, base SQLite temporaire migrée par Alembic
```

## Sauvegarde / restauration

```bash
python -m brikia.cli backup                        # -> data/backups/brikia-<date>.zip
python -m brikia.cli restore <archive.zip> --yes   # application ARRÊTÉE
```

Procédure complète : [docs/sauvegarde.md](docs/sauvegarde.md).

## Organisation du dépôt

```
backend/brikia/   code (domain, models, services, adapters, api, web, static)
migrations/       migrations Alembic (seul moyen de faire évoluer le schéma)
tests/            tests pytest
docs/             documentation
data/             données locales (ignorées par git) : brikia.db, uploads/, backups/, logs/
```

## Documentation

| Document | Contenu |
|---|---|
| [docs/utilisation.md](docs/utilisation.md) | Guide par rôle, parcours pas à pas |
| [docs/architecture.md](docs/architecture.md) | Architecture, modèle de données, machine d'états, endpoints et permissions |
| [docs/simule-et-futur.md](docs/simule-et-futur.md) | Ce qui est simulé/temporaire, et ce qui appartient aux phases futures |
| [docs/deploiement.md](docs/deploiement.md) | Réseau local, pare-feu, HTTPS, service |
| [docs/sauvegarde.md](docs/sauvegarde.md) | Sauvegarde et restauration |

## Licences tierces

Polices Oswald, Inter et IBM Plex Mono (SIL Open Font License 1.1), embarquées dans
`backend/brikia/static/fonts/` avec leurs licences.
