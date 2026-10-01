# Validation de la phase 2 — lecture réelle des plans

Vérifications réalisées sur un **clone vierge** du dépôt (venv neuf, `pip install -c constraints.txt -e ".[dev,phase2]"`),
Python 3.11.15, **Linux uniquement**. Les parcours navigateur (Chromium) ont été exécutés avec le **DNS externe
bloqué** ; les scripts de parcours ne font pas partie du dépôt, la suite `pytest` en fait partie.

## Résultats

| Vérification | Résultat |
|---|---|
| Installation complète depuis versions figées (`constraints.txt`, 52 paquets) | OK, `pip check` propre |
| Installation de base **sans** l'option `phase2` | **291 tests passés**, 6 modules ignorés (bibliothèques absentes), 0 échec |
| `pytest` complet avec l'option `phase2` | **391 passés** |
| … avec le réseau coupé (`unshare -rn`) | 391 passés : aucun test ne dépend d'Internet |
| Migrations depuis une base vide (0001 → 0004) | OK ; `alembic check` : aucune dérive |
| Seed de démonstration avec le code de la phase 2 | OK ; les projets de démo sont marqués « simulated » |
| Parcours navigateur (chef + opérateur) avec **vos vrais IFC**, un DXF, un STEP, un PDF, un IFC corrompu | 29 étapes OK ; 0 erreur console, 0 violation CSP, 0 requête externe |
| Journal du serveur sur ce parcours | 0 erreur, 0 trace, 0 ligne de bruit natif (avant correction : 5 677 lignes de débogage d'IfcOpenShell) |
| Redémarrage en mode `real` : source et notes d'analyse conservées ; PDF **refusé** (422) ; IFC réel analysé | OK |

## IFC — vos deux fichiers réels (IFC Builder 2027.a, IFC4)

| | `Bureau.ifc` | `Batiment d'habitation.ifc` |
|---|---|---|
| Murs IFC → murs droits | 46 → **94** | 112 → **277** |
| Ouvertures de murs lues | **50** (sur 61 ; les 11 autres sont des trémies de dalles) | **127** (sur 135 ; 8 trémies de dalles) |
| Niveaux | RDC, R+1, R+2, R+3, Toiture | Rez-de-Chaussée, R+1 … R+4 |
| Surface brute vs quantités du fichier | −0,0 % | −0,1 % |
| Surface nette vs quantités du fichier | −0,0 % | −0,1 % |
| Durée d'analyse (navigateur, isolation comprise) | ≈ 1,4 s | ≈ 2,4 s |
| Page de calepinage (nœuds DOM) | 1 821 | 5 057 |

Le contrôle de surface est **indépendant** : les valeurs de comparaison sont celles qu'IFC Builder a enregistrées
dans le fichier (`Qto_WallBaseQuantities`), pas celles de BrikIA. Les deux fichiers passent `validate_geometry` et
traversent tout le pipeline : analyse → calepinage → BOM → validation → production simulée.

Testé aussi sur des IFC **synthétiques** : schémas IFC2X3, IFC4 et IFC4X3, projet en mètres et en millimètres, murs
pivotés et translatés, axes polygonaux et contours fermés, murs sans axe, hauteur issue des quantités ou de la
géométrie, ouvertures plus grandes que leur mur, fichiers vides ou corrompus.

## DXF — vos plans IFC Builder

| Contrôle (5 plans commités, 12 analysés pendant le développement) | Résultat |
|---|---|
| Portes et fenêtres détectées = repères de portes/fenêtres dessinés | **12 plans sur 12** |
| Longueur des murs extérieurs = périmètre de la dalle dessinée (4 plans où la dalle couvre le bâtiment) | à **moins de 1,5 %** |
| Unité : l'en-tête annonce « mm » pour des dessins en mètres | détecté et corrigé, avec une note |
| Contrôle visuel (superposition murs détectés / plan d'origine) | maison, restaurant, hôtel, immeuble : conformes |
| Performance : 6 000 murs (12 000 traits) | 0,9 s (36 s avant optimisation) |

## STEP

Validé **uniquement sur des STEP générés** (aucun STEP réel n'a été fourni) : murs droits, fenêtres (trous
traversants), portes (encoches), murs pivotés, niveaux, unités (m, cm, mm, pouces), modèle en Y vertical, poteaux et
dalles ignorés, volumes massifs, fichiers corrompus. Performance : 1 500 solides (36 Mo) en ≈ 10 s.

## Anomalies trouvées et corrigées pendant la validation

1. **Murs à axe polygonal** (IFC) : une boîte englobante donnait des longueurs fausses (jusqu'à −66 % de surface sur certains murs) ;
   remplacé par les segments de l'axe.
2. **Hauteur des murs recoupés par un toit** : la hauteur de la géométrie surestimait jusqu'à +53 % la surface de certains murs ; remplacée par la
   surface brute du fichier ÷ longueur (écart final < 0,1 %).
3. **Trémies de dalles** comptées comme ouvertures de murs : exclues.
4. **En-tête DXF faux** (`$INSUNITS`) : unité validée par la plausibilité de l'emprise.
5. **Jambages de portes/fenêtres** signalés à tort comme repères orphelins : ignorés.
6. **Orientation STEP** : une dalle vue de chant était prise pour un mur ; règle d'orientation prudente (Z par défaut,
   Y seulement avec une évidence forte, ou réglage explicite).
7. **Bruit natif** d'IfcOpenShell (5 677 lignes par analyse) : neutralisé.
8. **Performance** : détection des angles en O(n²) (8,8 s pour 2 000 murs) → quasi linéaire (0,05 s).
9. **Robustesse serveur** : un fichier malformé pouvait faire planter le code natif et arrêter tout BrikIA ; chaque
   analyse réelle s'exécute désormais dans un processus séparé avec délai maximal (plantage et blocage simulés et testés).
10. **Risque de tromperie** : un IFC analysé sans bibliothèque installée aurait reçu des murs de démonstration sans le
    dire ; tout repli simulé est désormais signalé sur la fiche du projet, et le mode `real` le refuse.

## Limites connues

- **Formats** : le PDF n'est pas lu ; les DWG, `.cyp`, glTF ne sont pas pris en charge ; IFC compressé (`.ifcZIP`) non géré.
- **IFC** : seuls les `IfcWall` comptent (pas les murs-rideaux, poteaux, poutres) ; ouvertures sans `IfcOpeningElement`
  ignorées ; validé sur **deux exports d'IFC Builder** et des IFC synthétiques — **pas sur des exports Revit, ArchiCAD,
  Allplan ou Tekla**, dont les conventions varient.
- **DXF** : approximation (hauteurs par défaut, un seul niveau, ouvertures réduites à une largeur) ; suppose des murs
  dessinés en deux faces parallèles sur des calques reconnaissables ; arcs, hachures et murs « interrompus » non gérés.
- **STEP** : heuristique ; murs fusionnés en un seul solide non reconnus ; hauteur = maximum du solide.
- **Angles** : un mur est « d'angle » dès qu'une extrémité forme un L ; combiné à la règle de calepinage temporaire
  (une pile d'angle par mur d'angle), les **blocs d'angle sont probablement surestimés** sur un bâtiment cloisonné.
- **Plans multi-niveaux** : l'IFC et le STEP sont lus en entier ; un DXF représente un seul étage.
- **Une analyse ne se relance pas** : un plan corrigé s'importe dans un nouveau projet.
- **Plateformes** : validé sous Linux ; `spawn` (isolation) et les paquets `ifcopenshell`/`cadquery-ocp` existent pour
  Windows/macOS mais n'ont **pas** été essayés.
- **Isolation** : ≈ 0,5 s de surcoût par analyse ; 2 analyses simultanées au plus (les suivantes attendent).
- **Règles de calepinage et cadences** : toujours **temporaires / de démonstration** (hors périmètre de la phase 2).
