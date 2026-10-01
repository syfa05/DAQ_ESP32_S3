# Calepinage assise par assise

Depuis cette version, BrikIA **pose chaque bloc, rang par rang**, au lieu d'estimer des quantités par surface et ratios.
Le détail est visible mur par mur (élévation à l'échelle dans la page du projet) et dans le rapport PDF.
L'ancien moteur reste disponible : `BRIKIA_LAYOUT_ENGINE=regles`.

## Ce que le moteur fait pour chaque mur
1. **Assises** = hauteur du mur ÷ hauteur du bloc standard (pris dans la bibliothèque de moules, ex. 100 mm). Un écart de hauteur est signalé.
2. **Ouvertures** : vides sur les assises concernées, à leur **position réelle** et à leur **allège** réelle (lues dans l'IFC, le DXF
   ou le STEP). Hauteurs arrondies à l'assise. Si la position est inconnue (PDF simulé), l'ouverture est **placée automatiquement et signalée**.
3. **Linteau** sur l'assise au-dessus de chaque ouverture, **appui de fenêtre** sur l'assise sous le vide, **chaînages verticaux** de chaque
   côté des ouvertures, aux extrémités libres et au plus tous les 4 m, **ceinture** (chaînage horizontal) sur la dernière assise.
4. **Angles par extrémité** : chaque extrémité de mur est classée (*angle*, *butée*, *contre un autre mur (T)*, *prolongement*, *bout libre*). **Un angle n'a qu'un propriétaire** : un seul des deux murs pose la pile de blocs d'angle, l'autre vient en butée (un rectangle de 4 murs = exactement 4 piles). Les **jonctions en T** reçoivent un chaînage vertical à l'appui du refend ; les butées et prolongements n'ont pas de chaînage d'extrémité.
5. **Joints décalés** : une assise sur deux commence par un demi-bloc à partir de chaque élément fixe ; la fin de chaque tronçon est fermée par
   un demi, un ¾ ou une pièce **coupée** (une coupe consomme un bloc ; le reste est réemployé s'il est assez long).
6. Chaque assise est un **pavage exact** de la longueur du mur (contrôlé avant d'enregistrer ; sinon le calcul est refusé).
7. **Quantités à produire** = blocs posés + **marge de casse 2 %** (réglable).

Règles réglables (fichier JSON `BRIKIA_LAYOUT_RULES_FILE`) : `breakage_margin`, `chain_spacing_max_mm`, `lintel_bearing_mm`,
`default_window_sill_mm`, `min_piece_mm`, `reuse_offcuts`.

## Résultats sur vos plans (valeurs de départ des moules)
| Plan | Murs | Surface nette | Ancienne estimation | Assises | Coupes | Angles : propriétaires / extrémités en butée / T |
|---|---|---|---|---|---|---|
| IFC « Bureau » | 94 | 1 052,9 m² | 36 951 blocs | 40 245 blocs (+8,9 %) | 7 332 | 66 / 82 / 26 |
| IFC « Habitation » | 277 | — | — | — | — | 188 / 228 / 78 |
| DXF « Restaurant » | 13 | 179,2 m² | 6 281 blocs | 6 534 blocs (+4,0 %) | 622 | 14 / 12 / 0 |

Avec un propriétaire par angle, les blocs d'angle du bureau passent de 3 002 à 2 199 (−27 %) et les chaînages de 5 415 à 4 538. Le surcoût
global vient des coupes (chaque fin de tronçon), des arrondis à l'assise et de la marge de casse. **Non comparé à un chantier réel.**

## Corriger l'analyse à la main
Dans la page du projet (chef de projet, avant la validation), le tableau « Murs analysés » a un bouton **Modifier** par mur et **Ajouter un mur** :
nom, longueur, hauteur, épaisseur, nature de chaque extrémité, jonctions en T (abscisses en mm) et ouvertures (type, largeur, hauteur, position,
allège ; vides = placées automatiquement). **Supprimer** retire un mur (un projet garde au moins un mur).
* Toute correction **annule le calepinage** (et le devis courant) ; un projet « à valider » repasse à « à optimiser » ; il faut recalculer.
* Les murs corrigés sont marqués « corrigé », notés dans l'analyse du projet et tracés dans le Journal (avant/après).
* Les contrôles renvoient des messages précis (ouverture plus large que le mur, chevauchement, dépassement de hauteur…).

## Limites connues (à lire)
* **Non validé sur un mur réellement monté** : le calcul est cohérent (pavage exact, quantités recoupées par tests) mais ses hypothèses
  de pose (demi en tête d'assise impaire, chaînage tous les 4 m, jambages chaînés) sont des choix à confirmer avec votre maçon.
* **Jonctions en T** : modélisées par un chaînage vertical à l'appui du refend ; le **bloc en T** (BTC_TE) n'est pas posé automatiquement.
* **Pignons** (rampants) ignorés : les murs sont rectangulaires.
* **Épaisseurs** : lues et enregistrées (IFC, DXF, STEP), affichées et modifiables, mais le moteur **ne choisit pas encore le moule selon l'épaisseur**.
* **Détection des extrémités** : tolérance fondée sur l'épaisseur des murs ; les plans mal dessinés (murs qui ne se touchent pas) donnent des
  bouts libres à corriger à la main. Les murs d'étages différents ne sont jamais connectés.
* **Un seul niveau de moule par fonction** : le premier moule disponible de la même gamme est utilisé (pas de choix par type de mur).
* Ouvertures dont l'allège est inconnue : fenêtre à 900 mm par défaut (DXF) ; portes au sol.
* Pas de contrôle structurel : ce n'est pas un calcul de résistance.
