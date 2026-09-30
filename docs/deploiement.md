# Déploiement sur le PC industriel

Cible : BrikIA hébergée sur le PC industriel, **accessible aux postes autorisés du réseau local de
l'usine**, jamais exposée directement à Internet, et **entièrement fonctionnelle sans Internet**.

> Les exemples de pare-feu, de reverse proxy et de service ci-dessous sont des **modèles à
> adapter et à tester sur votre installation** ; ils n'ont pas été exécutés dans l'environnement de
> développement de la phase 1.

## 1. Écoute réseau

Par défaut BrikIA n'écoute que `127.0.0.1` (poste local). Pour le réseau d'usine :

```bash
BRIKIA_HOST=0.0.0.0            # toutes les interfaces, ou l'adresse LAN du PC (ex. 192.168.1.20)
BRIKIA_PORT=8000
BRIKIA_ALLOWED_HOSTS=192.168.1.20,brikia.usine.local   # noms/IP acceptés dans l'en-tête Host
```

- Préférer l'**adresse LAN précise** du PC à `0.0.0.0` s'il possède plusieurs interfaces
  (réseau d'usine, réseau bureautique, Internet…).
- Interface web et API partagent la **même origine** : aucun CORS à configurer.
- HTTP local : `BRIKIA_COOKIE_SECURE=false` (défaut). Les identifiants circulent alors en clair sur
  le LAN : réservez ce mode à un réseau d'usine isolé/de confiance, ou passez à HTTPS (§3).

## 2. Pare-feu — limiter l'accès au réseau local autorisé

Principe : n'autoriser le port de BrikIA **que depuis le sous-réseau de l'usine** (ex.
`192.168.1.0/24`), refuser le reste, et ne **jamais** rediriger ce port depuis un routeur/box
(pas de NAT / port forwarding vers Internet).

**Windows (PowerShell administrateur)** :

```powershell
New-NetFirewallRule -DisplayName "BrikIA (LAN usine)" -Direction Inbound -Protocol TCP `
  -LocalPort 8000 -RemoteAddress 192.168.1.0/24 -Profile Private,Domain -Action Allow
# Vérifier qu'aucune autre règle n'ouvre le port 8000 au profil « Public » :
Get-NetFirewallRule -DisplayName "*BrikIA*" | Get-NetFirewallPortFilter
```

**Linux (ufw)** :

```bash
sudo ufw default deny incoming
sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp
sudo ufw enable
```

Compléter au besoin par une liste restreinte de postes (`-RemoteAddress 192.168.1.30,192.168.1.31`).
Contrôle : depuis un poste **hors** du sous-réseau autorisé, `http://<ip-du-pc>:8000` ne doit pas répondre.

## 3. HTTPS local via reverse proxy (sans modifier l'application)

BrikIA ne gère pas TLS elle-même : on place un reverse proxy local (Caddy, nginx, IIS…) qui
termine HTTPS et transmet à BrikIA **sur la boucle locale**.

1. BrikIA n'écoute plus que le proxy :
   ```bash
   BRIKIA_HOST=127.0.0.1
   BRIKIA_BEHIND_PROXY=true            # honore X-Forwarded-* uniquement depuis 127.0.0.1
   BRIKIA_COOKIE_SECURE=true           # cookie de session envoyé en HTTPS uniquement
   BRIKIA_ALLOWED_HOSTS=brikia.usine.local
   ```
2. Le proxy écoute en 443 (règle de pare-feu du §2 appliquée au port 443 au lieu de 8000).
   Exemple Caddy (certificat interne, à adapter à votre PKI) :
   ```
   brikia.usine.local {
       tls internal
       reverse_proxy 127.0.0.1:8000
   }
   ```
   Le proxy doit conserver l'en-tête `Host` d'origine (comportement par défaut de Caddy) pour
   satisfaire `BRIKIA_ALLOWED_HOSTS`.
3. Le passage HTTP → HTTPS ne demande **aucune modification de code** : uniquement ces variables.
   Si `COOKIE_SECURE=true` alors que l'accès se fait encore en HTTP, la connexion semblera
   réussir mais le navigateur ne renverra pas le cookie : vérifier l'URL en `https://`.

## 4. Démarrage automatique

BrikIA se lance par `python -m brikia.cli serve` (applique d'abord les migrations, un seul worker).

**Linux (systemd)** — `/etc/systemd/system/brikia.service` :

```ini
[Unit]
Description=BrikIA
After=network.target

[Service]
WorkingDirectory=/opt/brikia
EnvironmentFile=/opt/brikia/.env
ExecStart=/opt/brikia/.venv/bin/python -m brikia.cli serve
Restart=on-failure
User=brikia

[Install]
WantedBy=multi-user.target
```

**Windows** : tâche planifiée « au démarrage » exécutant `.venv\Scripts\python.exe -m brikia.cli serve`
depuis le dossier du dépôt (ou un gestionnaire de service comme NSSM), sous un compte dédié sans
privilèges d'administrateur. Les variables se placent dans le fichier `.env` du dossier de lancement.

## 5. Mise en production — check-list

- [ ] `BRIKIA_ALLOWED_HOSTS` renseigné (plus de `*`).
- [ ] Pare-feu limité au sous-réseau d'usine ; aucune redirection de port depuis Internet.
- [ ] Comptes réels créés (`create-user`) ; **pas de `seed`** en production.
- [ ] HTTPS via reverse proxy si le réseau n'est pas isolé ; `BRIKIA_COOKIE_SECURE=true`.
- [ ] Sauvegardes planifiées et **restauration testée** (voir [sauvegarde.md](sauvegarde.md)).
- [ ] Un seul processus BrikIA (ne pas lancer plusieurs workers).
- [ ] Horloge du PC correcte (horodatages, expiration des sessions, ActionLog).
- [ ] Compte système de service sans droits d'administrateur ; `data/` non accessible aux autres utilisateurs.

## 6. Fonctionnement hors ligne

Aucune dépendance à Internet à l'exécution : pas de CDN, pas de police distante, pas d'API externe,
pas d'IA en ligne. Seule l'**installation** des dépendances Python demande un accès aux paquets.
Un test automatique échoue si une ressource externe apparaît dans les pages, le CSS ou le JS.
