# Analyse des plans (phase 2)

BrikIA lit désormais les plans **IFC**, **STEP** et **DXF** et en déduit les murs, leurs ouvertures et leurs
niveaux. Un **PDF n'est pas lu** : son analyse reste simulée. Chaque analyse conserve sa **source** et ses
**avertissements**, affichés sur la fiche du projet (*Analyse du plan*) et en étiquette sur le tableau de bord.

| Format | Source affichée | Fiabilité | Ce que BrikIA lit |
|---|---|---|---|
| `.ifc` | Lecture réelle — IFC | **élevée** (modèle BIM sémantique) | murs, ouvertures (portes/fenêtres), niveaux, quantités du fichier |
| `.step` / `.stp` | Lecture réelle — STEP (heuristique) | moyenne | solides 3D reconnus comme murs par leur forme |
| `.dxf` | Lecture réelle — DXF (approximation 2D) | approximative | traits des calques de murs, repères de portes/fenêtres |
| `.pdf` | **Analyse SIMULÉE** | aucune | rien : scénario de démonstration |

> Le calepinage, la BOM et la production fonctionnent à l'identique quelle que soit la source. Les règles de
> calepinage restent **temporaires** (voir [simule-et-futur.md](simule-et-futur.md)).

## Installation et modes

La lecture réelle demande les bibliothèques de l'option `phase2` (≈ 200 Mo) :

```bash
pip install -c constraints.txt -e ".[dev,phase2]"
```

Sans elle, BrikIA reste pleinement fonctionnel ; les plans sont alors analysés par le simulateur **et signalés
comme tels** (« Module de lecture IFC non installé… l'analyse est SIMULÉE »). `BRIKIA_ANALYZER_MODE` :

| Mode | Comportement |
|---|---|
| `auto` (défaut) | lecture réelle si le module est installé ; sinon (ou pour un PDF) simulation **signalée** |
| `real` | lecture réelle uniquement ; refus explicite sinon (recommandé en production) |
| `simulated` | comportement de la phase 1 (démonstrations) |

Un fichier réel **illisible ou sans mur** n'est jamais remplacé par des murs de démonstration : c'est une erreur
claire en français et le projet reste « À analyser ».

## IFC (`IfcPlanAnalyzer`, IfcOpenShell)

Schémas IFC2X3, IFC4 et IFC4X3. Un mur IFC est découpé en **murs droits** (un par segment de son axe) :

- **Longueur** : segments de l'axe (`Axis`, polyligne) — un mur en contour fermé devient autant de murs droits.
- **Hauteur** : `GrossSideArea` (quantités du fichier) ÷ longueur de l'axe, ce qui restitue la hauteur moyenne d'un
  mur recoupé par un toit ; sinon hauteur de la géométrie 3D (Z max − Z min).
- **Ouvertures** : `IfcOpeningElement` du mur ; dimensions = celles du **trou** réel ; type d'après l'objet qui le
  remplit (`IfcDoor` → porte, `IfcWindow` → fenêtre, sinon « ouverture ») ; rattachée au segment le plus proche.
  Les trémies de **dalles** ne sont pas des ouvertures de mur.
- **Niveaux** : `IfcBuildingStorey` (le nom du niveau est dans le nom du mur : « R+1 · Cloison légère n°3.2 »).
- **Angles** : jonctions « en L » entre murs d'un même niveau (voir plus bas).
- **Unités** : lues dans le fichier (m, mm, …), tout est converti en millimètres entiers.

**Contrôle de cohérence** : sur vos deux fichiers IFC Builder, les surfaces brute et nette recalculées par BrikIA
égalent celles enregistrées par l'auteur du modèle (`Qto_WallBaseQuantities`) à **0,1 % près**.

Ignorés (et signalés) : poteaux, poutres, dalles, toitures, murs-rideaux ; murs sans géométrie 3D ; segments de
moins de 150 mm ; ouvertures sans volume.

## DXF (`DxfPlanAnalyzer`, ezdxf) — approximation assumée

Un DXF est un dessin : il ne contient **ni hauteur de mur, ni ouverture typée**. Toute analyse DXF s'ouvre donc par
un avertissement « APPROXIMATION ».

- **Calques** : reconnus par expression régulière (insensible à la casse). Par défaut : murs
  `wall|mur|cloison|partition|paroi|refend|muro`, portes `door|porte|puerta`, fenêtres
  `window|fen[eê]tre|vitr|ventana`. À adapter : `BRIKIA_DXF_WALL_LAYERS`, `…_DOOR_LAYERS`, `…_WINDOW_LAYERS`.
  Si aucun calque de murs n'est reconnu, l'erreur liste les calques trouvés.
- **Murs** : deux traits parallèles (les deux faces) distants de 40 à 700 mm forment un mur ; l'axe est la moyenne des
  deux faces, l'épaisseur leur écart. Un mur dessiné d'un seul trait devient un mur filaire de 200 mm (signalé).
- **Hauteur** : valeur par défaut configurable (`BRIKIA_DXF_WALL_HEIGHT_MM`, 2700 mm).
- **Ouvertures** : repère (trait ou polyligne) d'un calque porte/fenêtre, parallèle et posé sur un mur ; largeur =
  longueur du repère ; hauteur par défaut (`BRIKIA_DXF_DOOR_HEIGHT_MM` 2100, `…_WINDOW_HEIGHT_MM` 1200). Les jambages
  (petits traits perpendiculaires) et les doublons sont ignorés.
- **Unité** : l'en-tête `$INSUNITS` est **souvent faux** (vos plans IFC Builder annoncent « mm » pour des mètres) ;
  l'unité est donc contrôlée par la plausibilité de l'emprise du bâtiment (2 m à 400 m) et corrigée si besoin,
  avec une note explicite.
- **Un DXF = un niveau** : importez un projet par étage.
- Non gérés : arcs/courbes, murs dessinés comme interruption (et non comme repère), hachures, blocs imbriqués
  au-delà de 3 niveaux, **DWG** (binaire AutoCAD : à enregistrer en DXF).

## STEP (`StepPlanAnalyzer`, Open CASCADE via `cadquery-ocp`) — heuristique

Un STEP de CAO ne désigne pas les murs : ils sont **reconnus par leur forme**. Un solide est un mur s'il est vertical
(≥ 800 mm), épais de 40 à 600 mm et au moins 3 fois plus long qu'épais. Les poteaux, dalles et volumes massifs sont
ignorés et comptés dans les notes. Un mur en L ou un contour fermé modélisé en **un seul solide** n'est pas reconnu :
les murs doivent être des solides distincts.

- **Ouvertures** : trous traversants de la plus grande face (fenêtres) et encoches ouvertes en pied (portes).
- **Niveaux** : altitude du pied des murs, regroupée à 100 mm (« Niveau +3,00 m »).
- **Hauteur** : hauteur maximale de chaque solide (surestimée pour un sommet incliné).
- **Unités** : converties en mm à la lecture. **Axe vertical** : Z ; le mode `auto` ne bascule sur Y qu'avec une
  évidence forte (≥ 3 murs et ≥ 2 fois plus qu'en Z) — sinon fixer `BRIKIA_STEP_UP_AXIS=z|y`.
- *Validé uniquement sur des STEP générés* (aucun STEP réel n'a été fourni) : à confirmer sur vos exports.

## Détection des angles (commune)

Un mur est « d'angle » si l'une de ses extrémités rejoint celle d'un mur du **même niveau** avec un angle d'au moins
60° (tolérance : épaisseur + 50 mm). Les jonctions en T et les murs alignés ne sont pas des angles. La règle de
calepinage actuelle compte **une pile d'angle par mur d'angle** : dans un bâtiment cloisonné, presque tous les murs ont
un angle, et les blocs d'angle sont probablement **surestimés** (règle temporaire, à revoir avec le fournisseur).

## Robustesse : analyse dans un processus séparé

Ces bibliothèques natives traitent des fichiers fournis par les utilisateurs. Pour qu'un fichier malformé ne puisse
pas faire tomber BrikIA, chaque analyse réelle s'exécute dans un **processus séparé** (méthode « spawn ») avec un
délai maximal (`BRIKIA_ANALYSIS_TIMEOUT_S`, 180 s) ; au plus 2 analyses simultanées. Un plantage natif ou un blocage
donne un message d'erreur en français, le serveur et le projet ne sont pas touchés. Coût : ≈ 0,5 s par analyse.
`BRIKIA_ANALYSIS_ISOLATED=false` désactive l'isolation (développement seulement).

## Messages d'erreur fréquents

| Message | Cause probable |
|---|---|
| « Ce fichier IFC est illisible… » | fichier corrompu, tronqué, ou pas de l'IFC |
| « Aucun mur n'a été trouvé dans ce fichier IFC… » | le modèle ne contient aucun `IfcWall` |
| « Aucun mur détecté dans ce plan DXF… calques présents : … » | calques de murs non reconnus → adapter `BRIKIA_DXF_WALL_LAYERS` |
| « Aucun mur reconnu parmi les N solide(s)… » (STEP) | murs fusionnés en un solide, ou axe vertical différent de Z |
| « Les dimensions de ce plan DXF… incompatibles avec un bâtiment » | échelle du dessin aberrante |
| « L'analyse de ce plan … a dépassé N secondes » | fichier trop volumineux/complexe |
| « Module de lecture … non installé » | installer l'option `phase2` |

## Performances mesurées

| Cas | Durée |
|---|---|
| IFC `Bureau.ifc` (1,8 Mo, 46 murs → 94 murs droits) | ≈ 1 s (navigateur, isolation comprise) |
| IFC bâtiment d'habitation (6,7 Mo, 112 murs → 277 murs droits) | ≈ 2-3 s |
| DXF de 6 000 murs (12 000 traits) | 0,9 s |
| STEP de 1 500 solides (36 Mo) | ≈ 10 s |
