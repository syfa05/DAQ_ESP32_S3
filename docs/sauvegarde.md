# Sauvegarde et restauration

Tout l'état de BrikIA tient dans le dossier `data/` (ou `BRIKIA_DATA_DIR`) :

| Élément | Chemin |
|---|---|
| Base de données | `data/brikia.db` (+ `-wal`/`-shm` pendant l'exécution) |
| Plans importés | `data/uploads/` |
| Sauvegardes | `data/backups/` |
| Logs techniques | `data/logs/` |

Les commandes sont en Python (identiques sous Windows et Linux).

## Sauvegarder

```bash
python -m brikia.cli backup                      # -> data/backups/brikia-AAAAMMJJ-HHMMSS.zip
python -m brikia.cli backup --dest D:\sauv\brikia.zip     # destination au choix
```

L'archive contient `brikia.db` — copie **cohérente** via l'API de sauvegarde SQLite, réalisable
**pendant que l'application tourne** — et le dossier `uploads/`. L'écriture est atomique : une
archive n'apparaît qu'une fois complète. Les logs ne sont pas inclus.

**Planification** (à mettre en place par l'exploitant) : Planificateur de tâches Windows ou `cron`
lançant la commande ci-dessus chaque jour, puis **copie de l'archive hors du PC** (disque réseau,
support externe) : une sauvegarde qui reste sur la machine ne protège pas d'une panne du disque.

## Restaurer

1. **Arrêter BrikIA** (la restauration remplace la base pendant qu'aucun processus ne l'utilise).
2. Restaurer :
   ```bash
   python -m brikia.cli restore data/backups/brikia-20260930-101500.zip --yes
   ```
   Sans `--yes`, la commande refuse d'écraser quoi que ce soit.
3. Une **copie de sécurité de l'état courant** est créée d'abord
   (`data/backups/avant-restauration-<date>.zip`) : en cas d'erreur de manipulation, elle permet de revenir en arrière.
4. Redémarrer BrikIA (`serve` applique les migrations si l'archive vient d'une version plus ancienne).

La restauration refuse les archives invalides (pas un zip, sans `brikia.db`, chemins suspects).

## Tester la restauration

Une sauvegarde jamais restaurée n'est pas une sauvegarde. Au moins une fois par trimestre :
restaurer une archive dans un répertoire de test (`BRIKIA_DATA_DIR=/chemin/test python -m brikia.cli restore … --yes`),
lancer `serve` sur un autre port et vérifier que les projets et plans sont présents.

## Cas particuliers

- **Ordre de production en cours lors d'une restauration** : l'état de la ligne simulée est
  recalculé à la reprise (l'ordre est renvoyé à la ligne avec son horodatage d'origine). Avec une
  vraie ligne (phase 3), coordonner la restauration avec l'exploitation de la ligne.
- **Migration de PC** : installer BrikIA, copier une archive, `restore --yes`, `serve`.
