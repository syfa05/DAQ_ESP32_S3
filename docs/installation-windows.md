# Installer BrikIA comme une application (Windows)

Objectif : un seul fichier, **`BrikIA-Setup.exe`**, à copier sur une clé USB. Sur le PC cible, un double-clic
installe BrikIA comme n'importe quelle application : ni Python, ni Internet, ni ligne de commande.

## Pour la personne qui reçoit le Setup

1. Double-cliquer sur `BrikIA-Setup.exe` (accepter la demande d'administrateur de Windows).
   *Windows SmartScreen peut afficher « Windows a protégé votre PC » : le programme n'est pas signé
   numériquement. Cliquer sur « Informations complémentaires » puis « Exécuter quand même ».*
2. Suivre l'assistant. Case facultative « Autoriser les autres PC du réseau local » : à cocher
   uniquement si d'autres postes doivent ouvrir BrikIA (ouvre le port 8000 du pare-feu, réseaux privé/domaine).
3. Lancer **BrikIA** (icône du Bureau ou menu Démarrer). Une fenêtre noire s'ouvre (c'est le serveur :
   **ne pas la fermer** tant qu'on utilise BrikIA), puis le navigateur affiche l'application.
4. **Premier lancement** : une page « Première configuration » demande de créer le compte du chef de projet.
   Les autres comptes se créent ensuite depuis l'application (menu **Utilisateurs**, voir `docs/utilisateurs.md`).

| Élément | Emplacement |
|---|---|
| Programme | `C:\Program Files\BrikIA` |
| Données (base, plans importés, sauvegardes, `.env`) | `C:\ProgramData\BrikIA` — **conservées** lors d'une mise à jour ou d'une désinstallation |
| Journal / réglages | `C:\ProgramData\BrikIA\.env` (adresse, port, formats…) |

**Sauvegarde** : menu Démarrer → « Sauvegarder les données BrikIA » (crée un zip dans `C:\ProgramData\BrikIA\data\backups`).
**Mise à jour** : relancer un nouveau `BrikIA-Setup.exe` : le programme est remplacé, les données restent.
**Autres PC du réseau** : `http://<adresse-IP-du-PC>:8000` (l'adresse s'affiche dans la fenêtre du serveur).
Le compte du premier démarrage ne peut être créé que depuis le PC qui héberge BrikIA.

## Pour la personne qui fabrique le Setup

Le `Setup.exe` est construit **sur Windows** (Inno Setup). Deux voies :

### A. Automatique (GitHub Actions) — recommandée
Le workflow `.github/workflows/windows-installer.yml` (déclenché à chaque push sur la branche, ou à la main
via *Actions → Installeur Windows → Run workflow*) :
construit le dossier d'application, le teste (démarrage, création du premier compte, import d'un plan DXF
et d'un plan IFC réels), compile `BrikIA-Setup.exe`, l'**installe en silencieux**, rejoue le test sur
l'installation, la désinstalle, puis publie le fichier : *Actions → l'exécution → Artifacts → BrikIA-Setup*.

### B. Manuelle (un PC Windows avec Internet, une seule fois)
```bat
py -3.12 installer\build_windows.py --profile complet
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\BrikIA.iss
```
Résultat : `dist\BrikIA-Setup.exe`. Prérequis : Python 3.12 et [Inno Setup 6](https://jrsoftware.org/isinfo.php).

### Contenu et profils
Le Setup embarque Python 3.12 (distribution « embeddable » officielle), les dépendances aux versions de
`constraints.txt` (roues Windows 64 bits) et l'application. Rien n'est téléchargé sur le PC cible.

| Profil | Lecture des plans | Taille installée |
|---|---|---|
| `complet` (défaut) | IFC, DXF, **STEP** réels | ≈ 900 Mo |
| `leger` | IFC, DXF réels ; STEP → analyse simulée **signalée** | ≈ 320 Mo |

## Ce qui est vérifié, et ce qui ne l'est pas
* Vérifié ici (Linux) : lanceur, création du premier compte, administration des utilisateurs, import et analyse réels
  d'un DXF via `installer/smoke_test.py`, assemblage du dossier d'application, résolution des roues Windows de toutes les dépendances.
* Vérifié sur un vrai Windows (GitHub Actions, `windows-latest`, exécution du 2026-10-01, toutes étapes vertes) : Python embarqué avec ifcopenshell/ezdxf/OCP,
  démarrage du serveur, premier compte, import et analyse réels d'un DXF et d'un IFC, compilation Inno Setup, installation silencieuse
  (tâche réseau cochée), nouveau test sur l'installation, désinstallation (programme supprimé, données conservées).
  Reste non vérifié : l'assistant graphique (seul le mode silencieux est testé) et les raccourcis.
* **Non vérifié** : affichage SmartScreen, installation avec un antivirus d'entreprise strict, Windows 32 bits (non pris en charge),
  macOS/Linux (utiliser l'installation `pip` du README).
* Le Setup n'est **pas signé** (un certificat de signature de code payant est nécessaire pour supprimer l'avertissement SmartScreen).
