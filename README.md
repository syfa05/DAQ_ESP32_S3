# BrikIA — phases 1 et 2

Cerveau logiciel de la ligne de production de briques de terre comprimée (BTC) et de
parpaings autobloquants. BrikIA relie le plan de l'architecte, le calepinage, la nomenclature
(BOM), la validation par le chef de projet et l'ordre de fabrication.

**Phase 1** : application locale complète, sans machine réelle — FastAPI + SQLite + Alembic, interface
Jinja2 + JavaScript léger, entièrement en français, **fonctionnement 100 % hors connexion**.
**Phase 2** : lecture **réelle** des plans **IFC, STEP et DXF** (murs, ouvertures, niveaux) ; un PDF n'est pas lu.
Le calepinage « IA » (moteur de règles) et la production restent **simulés ou temporaires** — voir
[docs/simule-et-futur.md](docs/simule-et-futur.md) et [docs/analyse-des-plans.md](docs/analyse-des-plans.md).

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
pip install -c constraints.txt -e ".[dev,phase2]"    # phase2 = lecture réelle IFC / STEP / DXF (≈ 200 Mo)
# installation minimale (sans lecture réelle des plans) : pip install -c constraints.txt -e ".[dev]"
```

```powershell
# Windows (PowerShell)
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -c constraints.txt -e ".[dev,phase2]"
```

> `constraints.txt` fixe les versions des dépendances **validées** en phase 1 (sans lui, `pip` installerait
> les dernières versions, non testées). Validé avec Python 3.11 sous Linux ; les commandes Windows
> ci-dessus n'ont pas été exécutées dans l'environnement de développement.
>
> **Option `phase2`** : sans elle, BrikIA fonctionne mais tout plan est analysé par le **simulateur** — et l'application
> le signale clairement. Validé sous Linux ; non vérifié sous Windows/macOS (les bibliothèques publient des paquets
> pour ces systèmes, mais ils n'ont pas été essayés ici).
>
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

**Projet « en production » de la démo** : la ligne simulée avance en temps réel, donc ce projet se
termine tout seul — environ **2 minutes** après le `seed` à la cadence par défaut (40 blocs/s),
et l'état « terminé » est enregistré à la première consultation. Pour le garder en production plus
longtemps, démarrer avec une cadence lente : `BRIKIA_SIM_BLOCKS_PER_SECOND=1 python -m brikia.cli serve`
(cette valeur est celle du serveur ; elle se règle aussi dans `.env`). Pour voir un cycle complet
en direct, lancer la production du projet « validé » avec la cadence par défaut.
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
| `BRIKIA_MAX_UPLOAD_MB` | `50` | Taille max d'un plan (`.step .stp .ifc .dxf .pdf`) |
| `BRIKIA_ANALYZER_MODE` | `auto` | `auto` (réel si installé, sinon simulé **signalé**), `real` (refus sinon), `simulated` |
| `BRIKIA_ANALYSIS_TIMEOUT_S` | `180` | Durée maximale d'une analyse de plan (processus isolé) |
| `BRIKIA_ANALYSIS_ISOLATED` | `true` | Analyse dans un processus séparé (à ne désactiver qu'en développement) |
| `BRIKIA_DXF_WALL_HEIGHT_MM` | `2700` | Hauteur de mur par défaut pour un plan DXF (2D) |
| `BRIKIA_DXF_WALL_LAYERS` | `wall\|mur\|cloison\|partition…` | Calques de murs d'un DXF (regex) ; idem `…_DOOR_LAYERS`, `…_WINDOW_LAYERS` |
| `BRIKIA_STEP_UP_AXIS` | `auto` | Axe vertical d'un STEP : `auto`, `z` ou `y` |
| `BRIKIA_LAYOUT_RULES_FILE` | *(aucun)* | JSON de surcharge des règles de calepinage **temporaires** |
| `BRIKIA_SIM_BLOCKS_PER_SECOND` | `40` | Cadence de la ligne **simulée** |
| `BRIKIA_SIM_FAULT_AT_PERCENT` | *(aucun)* | Défaut simulé à ce % d'avancement (1-99) |
| `BRIKIA_LOG_LEVEL` | `INFO` | Niveau des logs techniques (`data/logs/brikia.log`) |

Déploiement en réseau local (écoute réseau, pare-feu, HTTPS via reverse proxy, service au
démarrage) : [docs/deploiement.md](docs/deploiement.md).

## Utilisation

Résumé : le **chef de projet** importe un plan (IFC, STEP, DXF), lance l'analyse puis le calepinage, consulte la
BOM et valide ; l'**opérateur** voit les projets validés, lance la production et suit sa progression
jusqu'à `termine`. Guide détaillé : [docs/utilisation.md](docs/utilisation.md).

```
a_analyser → a_optimiser → a_valider → valide → en_production → termine
```

## Tests

```bash
pytest          # 391 tests (291 sans l'option phase2), aucun accès Internet, base SQLite temporaire migrée par Alembic
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

## Limites connues

Principales limites (liste complète dans [docs/architecture.md](docs/architecture.md) et
[docs/validation-phase2.md](docs/validation-phase2.md)) : un seul processus serveur ; lecture DXF et STEP
**approximatives** (STEP validé sur des fichiers générés seulement) ; PDF non lu ; calepinage et production simulés ou temporaires ; pas de reprise
après une erreur de la ligne ; pas d'écran d'administration des comptes (création en ligne de commande) ;
exemples de pare-feu / HTTPS / service non exécutés en conditions réelles.

## Documentation

| Document | Contenu |
|---|---|
| [docs/utilisation.md](docs/utilisation.md) | Guide par rôle, parcours pas à pas |
| [docs/architecture.md](docs/architecture.md) | Architecture, modèle de données, machine d'états, endpoints et permissions |
| [docs/analyse-des-plans.md](docs/analyse-des-plans.md) | Phase 2 : lecture IFC / STEP / DXF, règles, limites, messages |
| [docs/validation-phase2.md](docs/validation-phase2.md) | Résultats de validation de la phase 2 |
| [docs/simule-et-futur.md](docs/simule-et-futur.md) | Ce qui est simulé/temporaire, et ce qui appartient aux phases futures |
| [docs/deploiement.md](docs/deploiement.md) | Réseau local, pare-feu, HTTPS, service |
| [docs/sauvegarde.md](docs/sauvegarde.md) | Sauvegarde et restauration |

## Licences tierces

Bibliothèques de lecture des plans (option `phase2`) : IfcOpenShell, ezdxf et Open CASCADE (via `cadquery-ocp`) — installées par
`pip`, non redistribuées dans ce dépôt ; se référer à leurs licences respectives avant toute redistribution.

Polices Oswald, Inter et IBM Plex Mono (SIL Open Font License 1.1), embarquées dans
`backend/brikia/static/fonts/` avec leurs licences.


## Installation « application » (Windows) et utilisateurs
* Fichier d'installation double-clic `BrikIA-Setup.exe` (Python embarqué, hors ligne) : voir `docs/installation-windows.md`.
* Création et gestion des comptes (page **Utilisateurs**, mot de passe, désactivation, première configuration) : voir `docs/utilisateurs.md`.
* Bibliothèque de moules étendue, chiffrage EUR/FCFA, rapport PDF et plans 2D/3D des moules : voir `docs/moules-et-chiffrage.md`.
* Calepinage assise par assise (pose réelle, élévations, PDF) : voir `docs/calepinage-assises.md`.
* Correction manuelle des murs et ouvertures, angles et jonctions en T par extrémité : voir `docs/calepinage-assises.md`.
* Épaisseurs de murs et gammes de moules (choix automatique ou imposé par mur) : voir `docs/calepinage-assises.md`.
