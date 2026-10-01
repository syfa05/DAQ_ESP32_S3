# Créer et gérer les utilisateurs

Deux rôles : **chef de projet** (importe, analyse, valide, administre les comptes) et **opérateur** (lance la production).

## Depuis l'application (méthode normale)
Connecté en **chef de projet** → menu **Utilisateurs** :
* **Ajouter** : nom complet, identifiant (3–64 caractères : minuscules, chiffres, `.` `_` `-`), rôle, mot de passe provisoire (≥ 8 caractères).
* **Désactiver / Réactiver** un compte (l'historique est conservé ; la personne est déconnectée immédiatement).
  Impossible de désactiver son propre compte ni le **dernier chef de projet actif**.
* **Mot de passe** : définir un nouveau mot de passe pour quelqu'un qui l'a oublié (ses sessions sont fermées).
* Chaque utilisateur change son propre mot de passe via son nom en haut à droite (**Mon compte**) ; ses autres sessions sont alors fermées.
* Toutes ces actions sont tracées dans le **Journal** (jamais les mots de passe).

Premier démarrage d'une installation vierge : la page « Première configuration » crée le premier chef de projet
(uniquement depuis le PC qui héberge BrikIA, et une seule fois).

## En ligne de commande (dépannage, ex. chef de projet verrouillé)
```
python -m brikia.cli list-users
python -m brikia.cli create-user --login awa --nom "Awa Diallo" --role chef_projet
python -m brikia.cli reset-password --login awa
python -m brikia.cli set-active --login awa --off        # sans --off : réactive
```
Sur une installation Windows : `"C:\Program Files\BrikIA\python\python.exe" "C:\Program Files\BrikIA\app\launcher.py" cli list-users`
