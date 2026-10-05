# Éléments simulés, temporaires et phases futures

## Ce qui est réel (phases 1 et 2)

Comptes et authentification, rôles et permissions côté backend, base SQLite persistante et
migrations, pipeline et machine d'états, stockage des plans, bibliothèque de moules (CRUD),
validation, ActionLog, sauvegarde/restauration, interface complète, tests — et, depuis la **phase 2**, la **lecture réelle des
plans IFC, STEP et DXF** (murs, ouvertures, niveaux ; voir [analyse-des-plans.md](analyse-des-plans.md)).

## Ce qui est simulé ou temporaire

| Élément | État | Où c'est isolé |
|---|---|---|
| **Analyse de plan PDF** | Un PDF n'est **pas lu** : scénario de démonstration choisi par le SHA-256 du fichier, toujours signalé « Analyse SIMULÉE ». Idem si l'option `phase2` n'est pas installée (mode `auto`). | `adapters/analyzers/simulated.py`, `dispatch.py` |
| **Analyse DXF / STEP** | Lecture **réelle** mais **approximative** : DXF = plan 2D (hauteurs par défaut, un niveau, ouvertures par repères) ; STEP = murs reconnus par leur forme (validé sur fichiers générés seulement). Avertissement affiché. | `dxf.py`, `step.py` |
| **Calepinage « IA »** | Ce n'est **pas** une IA : moteur de règles déterministe, aucun service externe. | `adapters/layout/rule_based.py` |
| **Règles de calepinage** | **Temporaires** (héritées du prototype, brique jointée 240×115×90 mm) : marge 5 %, angle = 1 pile par mur d'angle, linteau = ouverture + 2×200 mm, chaînage 10 % du corps, demi-blocs 6 % (indicateur seulement). Ne correspondent pas au système autobloquant mâle-femelle définitif. | `adapters/layout/rules_config.py` (surchargeable par JSON) |
| **Durée de production** | **Indicative** : cadences de démonstration (240 blocs/h standard, 120 blocs/h autres formes, 30 min par changement de moule). | `rules_config.py`, affichée « indicative » |
| **Production** | Aucune machine : la ligne est simulée (cadence constante, forme après forme, défaut simulable). | `adapters/production/simulated.py` |
| **Schéma des murs** | Illustration schématique, pas un rendu physique ni une simulation structurelle. | `static/js/lib/wallgrid.js` |
| **Données de démonstration** | Comptes et 6 projets de démo, à ne jamais charger en production. | `seed.py` |

Comportements simulés à connaître : le projet démo « en production » se termine seul (environ 2 minutes après le `seed` à la cadence par défaut — voir le README pour le garder plus longtemps) ; un défaut
peut être provoqué avec `BRIKIA_SIM_FAULT_AT_PERCENT` ; les cadences se règlent avec
`BRIKIA_SIM_BLOCKS_PER_SECOND`.

## Sécurité machine — principe non négociable

BrikIA (et la future Raspberry Pi) **ne portent jamais** la sécurité physique. Ils peuvent
transmettre une recette / un ordre logique, lire un état, afficher une progression. Ils ne gèrent
**ni** arrêt d'urgence, **ni** interverrouillage, **ni** sécurité opérateur, **ni** cycle de
sécurité. L'automate reste seul responsable du cycle machine et de la sécurité. Une panne de BrikIA
ne doit jamais créer de condition dangereuse ni interrompre un cycle de façon non maîtrisée. Le
contrat `ProductionGateway` ne contient donc aucune commande de cycle, d'arrêt ou de sécurité.

## Architecture matérielle cible

```
BrikIA ──REST/JSON, réseau local──▶ Raspberry Pi ──Modbus TCP / OPC-UA──▶ Automate Siemens S7 ──▶ Presse hydraulique
```

Contrat prévu BrikIA → Raspberry Pi : `POST /ordres` (`lot_id`, `quantites_par_forme`) et
`GET /etat/{lot_id}` (cibles, produits, progression, état, alarmes **informatives**).
Le simulateur de production de la phase 1 en reprend déjà la forme.

## Roadmap

| Phase | Contenu |
|---|---|
| **2** — Parsing géométrique réel | ✅ **Fait** : `IfcPlanAnalyzer` (IfcOpenShell), `StepPlanAnalyzer` (Open CASCADE via `cadquery-ocp`, l'alternative pip à pythonOCC) et `DxfPlanAnalyzer` (ezdxf, ajout demandé). Reste : validation sur des exports réels d'autres logiciels (Revit, ArchiCAD…) et sur de vrais STEP ; lecture des PDF et des DWG. |
| **3** — Passerelle Raspberry Pi | API REST locale de la Pi, driver automate abstrait (`PLCDriver` : `envoyer_recette()`, `lire_etat()`), `ModbusPLCDriver` (pymodbus), simulateur Modbus, tests d'intégration, `RaspberryPiProductionGateway` (avec annulation d'ordre). |
| **4** — OPC-UA si pertinent | `OPCUAPLCDriver` (asyncua) selon le modèle exact du Siemens S7 (**[À CONFIRMER]**). |
| **5** — Ligne pilote | Communication avec le matériel réel, validation des recettes, tests avec l'automaticien et les opérateurs, durcissement production. |

Autres points ouverts : règles définitives de calepinage des blocs autobloquants (à valider avec
le fournisseur des moules ; le moteur est interchangeable), vraies cadences de production,
gestion de reprise après erreur de ligne, administration des comptes dans l'interface.

**Toujours non implémentés** (volontairement) : Raspberry Pi, Modbus/OPC-UA, communication Siemens, service cloud, LLM ou API
externe.
