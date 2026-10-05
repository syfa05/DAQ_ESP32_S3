# Moules, chiffrage EUR/FCFA, rapport PDF et plans

## Bibliothèque de moules (71 moules fournis, tous modifiables)
*Les 23 moules ci-dessous sont les gammes de base (BTC 150 mm, parpaing 200 mm). Six gammes dérivées s'y ajoutent (BTC 100/200/300, parpaing 100/150/300) : voir `docs/calepinage-assises.md`, section « Épaisseurs et gammes de moules ».*

Menu **Moules** : chaque moule a un code, une catégorie, des **dimensions** (L × l × h en mm), un **poids**, une **cadence**
(blocs/heure) et un **coût de revient estimé**. Tout se modifie à tout moment (bouton *Modifier*) et on peut créer d'autres moules.

| Famille (catégorie) | BTC autobloquante (300×150×100) | Parpaing autobloquant (400×200×200) |
|---|---|---|
| Bloc plein / standard | BTC_STD | PARP_STD (creux) |
| Bloc creux | BTC_CREUX | — |
| Demi-bloc / trois-quarts | BTC_DEMI, BTC_TROIS_QUARTS | PARP_DEMI, PARP_TROIS_QUARTS |
| Angle 90° / 135° | BTC_ANGLE, BTC_ANGLE_135 | PARP_ANGLE, PARP_ANGLE_135 |
| Bloc en T | BTC_TE | — |
| Chaînage vertical / horizontal (U) | BTC_CHAINAGE, BTC_CHAINAGE_H | PARP_CHAINAGE, PARP_CHAINAGE_H |
| Linteau | BTC_LINTEAU (450 mm) | PARP_LINTEAU |
| Appui de fenêtre | BTC_APPUI (450×150×80) | PARP_APPUI |
| Pignon (rampant) | BTC_PIGNON | — |
| Acrotère | BTC_ACROTERE | PARP_ACROTERE |

**Valeurs de départ ESTIMATIVES** choisies par BrikIA (poids = volume × masse volumique approximative : BTC ≈ 1 900 kg/m³,
parpaing creux ≈ 1 100 kg/m³ apparent ; coûts de revient en EUR par bloc). À remplacer par vos valeurs réelles.

### Ce qui est posé automatiquement, et ce qui ne l'est pas
*(Voir `docs/calepinage-assises.md` : le calepinage pose maintenant les blocs rang par rang. Le texte ci-dessous décrit l'ancien moteur « regles », encore disponible.)*

Le calepinage lit **les dimensions des moules** (face du bloc, hauteur d'assise, longueurs de linteau et d'appui) et prélève sur le
total d'un mur : angle (une pile par assise, mur d'angle), linteaux, **appuis de fenêtre** (fenêtres et vitrines, si un moule d'appui existe),
chaînage vertical, **demi-blocs** (si un moule demi existe ; sinon simple indicateur) et blocs standard. Les moules d'un autre produit que
le moule standard ne sont jamais mélangés pour demi/appui.

Avec le moteur « assises », **¾ et chaînage horizontal (ceinture)** sont aussi posés. Les types **creux, angle 135°, T, pignon, acrotère** sont en bibliothèque (poids, plans, coûts, production) mais
**n'ont pas de quantité automatique** : le moteur ne sait pas encore où les placer sur un plan. Ils s'affichent « saisie manuelle ».
Les ratios (5 % de chutes, 10 % de chaînage, 6 % de demi-blocs) restent des règles temporaires à valider.

## Plans 2D et 3D de chaque moule
Bouton **Plan 2D/3D** : fiche A4 avec vues de dessus, de face, de côté (cotées, même échelle) et vue 3D en projection oblique, générée
à partir des dimensions saisies. **Représentation paramétrique indicative** (tenons, alvéoles, pentes selon des proportions types) :
à valider avec le fabricant avant usinage. Ouvrable et imprimable (SVG), et incluse dans le rapport PDF pour chaque moule utilisé.
Pas de visionneuse 3D interactive pour l'instant.

## Chiffrage en EUR et en FCFA
Menu **Tarifs** (chef de projet) : taux de change (parité fixe officielle **1 EUR = 655,957 FCFA**, modifiable), marge %, TVA %, frais
fixes par projet, et **coût de revient par moule** avec aperçu du prix de vente. Valeurs de départ : marge 20 %, TVA 18 %, frais 0
(à adapter à votre pays et à vos coûts).

* Prix unitaire = coût × (1 + marge) × taux, arrondi (2 décimales en EUR, entier en FCFA) ; total ligne = quantité × prix unitaire arrondi ;
  TVA arrondie sur le total HT.
* **Devis courant** (indicatif) tant que le projet n'est pas validé ; **figé à la validation** : un changement de tarif ne modifie plus
  un projet validé (il faut un nouveau projet).
* Moule sans coût renseigné : ligne non chiffrée et avertissement. Coûts et devis sont **réservés au chef de projet** ; les modifications
  de tarifs et de coûts sont tracées dans le Journal.
* Estimation non contractuelle.

## Rapport PDF
Bouton **Rapport PDF** sur chaque projet : informations, provenance de l'analyse (une analyse simulée est signalée en rouge), murs et
surfaces, nomenclature avec poids, durée indicative, chiffrage EUR/FCFA (chef de projet uniquement), bloc de signatures et une fiche
par moule utilisé. Généré hors ligne, avec la date, l'auteur et la version.

## Limites connues
Valeurs de moules, coûts et ratios = estimations à valider ; pas de visionneuse 3D interactive ; polices PDF standard (caractères
Latin-1) ; le calepinage ne dessine pas encore les rangs assise par assise.
