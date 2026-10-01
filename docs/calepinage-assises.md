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
4. **Angle** : pile de blocs d'angle au début d'un mur « d'angle ».
5. **Joints décalés** : une assise sur deux commence par un demi-bloc à partir de chaque élément fixe ; la fin de chaque tronçon est fermée par
   un demi, un ¾ ou une pièce **coupée** (une coupe consomme un bloc ; le reste est réemployé s'il est assez long).
6. Chaque assise est un **pavage exact** de la longueur du mur (contrôlé avant d'enregistrer ; sinon le calcul est refusé).
7. **Quantités à produire** = blocs posés + **marge de casse 2 %** (réglable).

Règles réglables (fichier JSON `BRIKIA_LAYOUT_RULES_FILE`) : `breakage_margin`, `chain_spacing_max_mm`, `lintel_bearing_mm`,
`default_window_sill_mm`, `min_piece_mm`, `reuse_offcuts`.

## Résultats sur vos plans (valeurs de départ des moules)
| Plan | Murs | Surface nette | Ancienne estimation | Assises | Coupes |
|---|---|---|---|---|---|
| IFC « Bureau » | 94 | 1 052,9 m² | 36 951 blocs | 39 852 blocs (+7,9 %) | 6 390 |
| DXF « Restaurant » | 13 | 179,2 m² | 6 281 blocs | 6 524 blocs (+3,9 %) | 647 |

Le surcoût vient surtout des coupes (chaque fin de tronçon), des arrondis à l'assise et de la marge de casse : la pose réelle consomme
environ 8 % de matière de plus que la surface nette sur le bureau. C'est plausible mais **non comparé à un chantier réel**.

## Limites connues (à lire)
* **Non validé sur un mur réellement monté** : le calcul est cohérent (pavage exact, quantités recoupées par tests) mais ses hypothèses
  de pose (demi en tête d'assise impaire, chaînage tous les 4 m, jambages chaînés) sont des choix à confirmer avec votre maçon.
* **Angles** : la détection d'un mur « d'angle » est grossière (un seul indicateur par mur) ; la pile d'angle est posée au début du mur seulement.
  Sur le DXF, tous les murs sont marqués d'angle, ce qui surestime les blocs d'angle.
* **Jonctions mur/mur (T)** non modélisées (pas de bloc en T posé automatiquement), **pignons** (rampants) et **épaisseurs de murs** ignorés.
* **Un seul niveau de moule par fonction** : le premier moule disponible de la même gamme est utilisé (pas de choix par assise).
* Ouvertures dont l'allège est inconnue : fenêtre à 900 mm par défaut (DXF) ; portes au sol.
* Pas de contrôle structurel : ce n'est pas un calcul de résistance.
