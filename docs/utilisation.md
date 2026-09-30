# Guide d'utilisation

Ouvrir BrikIA dans un navigateur : `http://127.0.0.1:8000` (poste local) ou l'adresse du PC
industriel sur le réseau d'usine (voir [deploiement.md](deploiement.md)). Se connecter avec son
identifiant nominatif. Comptes de démonstration : voir le README (`seed`).

Les statuts d'un projet :

| Statut | Signification | Couleur |
|---|---|---|
| À analyser | plan importé, pas encore analysé | gris |
| À optimiser | murs détectés, calepinage à faire | bleu acier |
| À valider | calepinage proposé, en attente de validation | ocre |
| Validé | agencement validé, prêt pour la production | vert |
| En production | ordre lancé, fabrication en cours | brique (indicateur animé) |
| Terminé | production achevée | vert |

## Chef de projet

Menu : **Projets · Moules · Production · Journal**.

1. **Importer un plan** — *Projets → Nouveau projet* : nom, ville, architecte, fichier
   (`.step`, `.stp`, `.ifc`, `.pdf`, 50 Mo max). Le projet est créé « À analyser ».
   *En phase 1 le contenu du plan n'est pas lu.*
2. **Analyser** — sur la fiche projet, *Lancer l'analyse* : les murs et leurs ouvertures
   apparaissent avec leurs surfaces (brute, ouvertures, nette). Le projet passe « À optimiser ».
3. **Calepinage IA** — *Lancer le calepinage IA* : proposition de quantités par forme et par mur,
   **nomenclature (BOM)** regroupée par forme, durée indicative, et **schéma des murs** (grille de
   blocs colorés par forme — illustratif, les quantités font foi). Les avertissements (ex. moule
   remplacé faute de disponibilité) s'affichent en ocre. Le projet passe « À valider ».
   Les règles de calcul sont **temporaires** (voir [simule-et-futur.md](simule-et-futur.md)).
4. **Ajuster si besoin** — dans *Moules*, activer/désactiver une forme, puis *Recalculer le
   calepinage* sur la fiche projet (tant que le projet n'est pas validé).
5. **Valider** — *Valider le projet* (confirmation). Le projet est figé, l'action est tracée dans le
   journal. Il devient visible pour les opérateurs.
6. **Suivre** — *Production* montre les ordres ; *Journal* liste les validations et lancements.

**Bibliothèque de moules** — création (code, nom, produit, catégorie fonctionnelle
standard/angle/chaînage/linteau, dimensions facultatives), modification, activation/désactivation,
suppression. Un moule déjà utilisé par un calepinage ou une production ne peut pas être supprimé :
désactivez-le. Un moule désactivé n'est plus utilisé pour les nouveaux calculs.

## Opérateur

Menu : **Projets · Moules (lecture) · Production**.

1. **Voir les projets validés** — la page *Projets* montre trois colonnes : Validé, En production, Terminé.
2. **Ouvrir un projet validé** — consulter sa nomenclature et le schéma des murs.
3. **Lancer la production** — *Lancer la production*, puis confirmer. Le bouton se désactive
   pendant l'envoi : un double clic ne crée pas deux ordres. Si une production est déjà en cours pour
   ce projet, un message l'indique.
4. **Suivre la progression** — page *Production* (ou fiche projet) : barre globale et une barre par
   forme, mises à jour automatiquement.
5. **Fin de production** — quand tout est produit, l'ordre et le projet passent « Terminé ».
   Si la ligne signale une erreur, l'ordre passe « Erreur » avec l'alarme affichée ; le projet reste
   « En production » (aucune reprise n'est prévue en phase 1).

L'opérateur ne peut ni analyser, ni calepiner, ni modifier les moules, ni valider : ces actions ne
sont pas proposées, et l'API les refuse de toute façon (403).

## Messages et erreurs

Toutes les erreurs sont affichées en français (ex. « Ce projet est déjà validé. »). Après un refus,
l'écran se recharge pour refléter l'état réel du serveur. Une session expirée renvoie à la page de
connexion. Le détail technique des erreurs se trouve dans `data/logs/brikia.log`.

## Comptes

Les comptes sont nominatifs et créés en ligne de commande par un administrateur :

```bash
python -m brikia.cli create-user --login jdupont --nom "Jean Dupont" --role operateur
```

Après 5 mots de passe erronés en 60 secondes, la connexion de cet identifiant est bloquée un court instant.
