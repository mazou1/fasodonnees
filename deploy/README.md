# Déploiement — VPS unique (Hetzner)

Tout tourne sur une seule machine avec Docker Compose, derrière **Caddy** qui
gère l'HTTPS automatiquement (Let's Encrypt). Aucun retraitement des données :
la base déjà calculée en local est migrée telle quelle.

## Ce que contiennent ces fichiers

| Fichier | Rôle |
|---|---|
| `../docker-compose.prod.yml` | Pile de prod autonome (db, api, worker, web, caddy). Seul Caddy expose 80/443. |
| `Caddyfile` | Reverse proxy + TLS. Route `/admin` et `/docs` vers l'API, le reste vers le front. |
| `.env.prod.example` | Modèle des variables d'environnement (secrets, domaine, clé LLM). |
| `migrate-data.sh` | Copie base + archives depuis le local vers la prod (sans recalcul). |
| `backup.sh` | Sauvegarde quotidienne (pg_dump + archive de `data/`). |

## 1. Provisionner le VPS

- Hetzner Cloud, **CX22** (2 vCPU / 4 Go RAM / 40 Go) suffit largement ; prévoir
  un **volume** ou un CX32 si `data/` doit grandir (3,7 Gio aujourd'hui).
- Image Ubuntu 24.04. Installer Docker :
  ```bash
  curl -fsSL https://get.docker.com | sh
  ```
- Pare-feu (Hetzner Cloud Firewall ou `ufw`) : n'ouvrir que **22, 80, 443**.

## 2. DNS

Créer un enregistrement **A** `faso.example.org` → IP du VPS (et `AAAA` si IPv6).
Attendre la propagation avant le premier lancement (Caddy a besoin du domaine
résolu pour obtenir le certificat).

## 3. Déployer

```bash
git clone git@github.com:mazou1/fasodonnees.git /srv/faso
cd /srv/faso
cp deploy/.env.prod.example .env
nano .env          # domaine + secrets (voir les commandes openssl dans le fichier)

docker compose -f docker-compose.prod.yml up -d --build
```

Caddy obtient le certificat tout seul. Le site est en ligne sur
`https://faso.example.org`, le back-office sur `/admin`.

## 4. Migrer les données locales (sans rien relancer)

Depuis votre **machine de dev** (base et `data/` locaux) :

```bash
./deploy/migrate-data.sh user@IP_DU_VPS /srv/faso
```

Le script : dump de la base (~50-100 Mo), copie vers la prod, `rsync` des
archives `data/` (une fois), puis restauration. Détail manuel équivalent :

```bash
# local
docker compose exec -T db pg_dump -U faso -Fc faso > faso.dump
scp faso.dump user@vps:/srv/faso/
rsync -avz backend/data/ user@vps:/srv/faso/backend/data/
# vps
docker compose -f docker-compose.prod.yml up -d db
cat faso.dump | docker compose -f docker-compose.prod.yml exec -T db \
  pg_restore -U faso -d faso --clean --if-exists --no-owner
docker compose -f docker-compose.prod.yml up -d
```

> Des avertissements bénins peuvent apparaître au `pg_restore` (extension
> `postgis` déjà présente dans l'image) — sans conséquence.

Ensuite le worker **poursuit en incrémental** : il ne collecte que le nouveau.

## 5. Exploitation

```bash
# Logs
docker compose -f docker-compose.prod.yml logs -f api worker caddy

# Après un git pull (le code est baké dans les images api/worker/web)
docker compose -f docker-compose.prod.yml up -d --build

# Traitements manuels (validation, annuaire…)
docker compose -f docker-compose.prod.yml exec api python -m app.validation 0.9
docker compose -f docker-compose.prod.yml exec api python -m app.annuaire
```

## 5 bis. Archive brute : disque ou stockage objet

L'archive (`data/`) pèse plus de 5 Go et grandit à chaque collecte. Deux modes,
choisis par `FASO_STOCKAGE` :

| | `local` (défaut) | `s3` |
|---|---|---|
| Où | disque du VPS | bucket S3-compatible |
| Dépendance | aucune | un endpoint S3 |
| Sauvegarde | `backup.sh` (tar) | réplication/versioning du bucket |
| Service des PDF | FastAPI lit le fichier | redirection vers une URL présignée |

En mode `s3`, l'endpoint peut être **Garage** (conteneur fourni) ou **n'importe
quel S3 externe** (Hetzner Object Storage, Scaleway, Cloudflare R2…). Le code ne
voit qu'un endpoint : basculer de l'un à l'autre ne change que des variables.

> ⚠️ **Garage sur ce même VPS n'apporte aucune durabilité** : même disque, même
> domaine de panne. Si le serveur est perdu, le bucket l'est aussi. Il ne
> protège vraiment que sur une **autre machine**, en réplication multi-nœud, ou
> si vous pointez vers un S3 externe. Lancé ici, il apporte surtout le service
> par URL présignée et la préparation d'une bascule ultérieure.

### Activer Garage

```bash
# secrets distincts dans le .env
for v in GARAGE_RPC_SECRET GARAGE_ADMIN_TOKEN GARAGE_METRICS_TOKEN; do
  echo "$v=$(openssl rand -hex 32)" >> .env
done

docker compose -f docker-compose.prod.yml --profile garage up -d garage

# initialisation du cluster (une seule fois)
NODE=$(docker compose -f docker-compose.prod.yml exec -T garage /garage node id -q | cut -d@ -f1)
docker compose -f docker-compose.prod.yml exec -T garage /garage layout assign -z faso -c 100G "$NODE"
docker compose -f docker-compose.prod.yml exec -T garage /garage layout apply --version 1

# bucket et clé applicative
docker compose -f docker-compose.prod.yml exec -T garage /garage bucket create faso-archives
docker compose -f docker-compose.prod.yml exec -T garage /garage key create faso-app
KEYID=$(docker compose -f docker-compose.prod.yml exec -T garage /garage key info faso-app | awk '/^Key ID/{print $3}')
docker compose -f docker-compose.prod.yml exec -T garage /garage bucket allow --read --write --owner faso-archives --key "$KEYID"
```

Reporter le *Key ID* et le *Secret key* dans le `.env` (`FASO_S3_ACCESS_KEY`,
`FASO_S3_SECRET_KEY`), avec `FASO_S3_ENDPOINT=http://garage:3900`.

### Pointer vers un S3 externe

Ne pas activer le profil `garage` ; renseigner l'endpoint, le bucket, les clés
et la région du fournisseur. Rien d'autre ne change.

### Migrer l'archive existante

```bash
FASO_STOCKAGE=s3 docker compose -f docker-compose.prod.yml exec -T api \
  python -m app.stockage migrer            # ajouter --garder-local pour ne rien supprimer
docker compose -f docker-compose.prod.yml up -d api worker   # bascule effective
```

La migration est **reprenable** (un objet déjà présent à la bonne taille est
sauté) et ne supprime un fichier local qu'après avoir vérifié la taille côté
bucket : un envoi interrompu laisse l'original intact. En cas d'échec partiel,
la commande sort en erreur et les fichiers concernés restent sur le disque.

> Sans `--garder-local`, chaque passe d'OCR ou d'extraction retéléchargera son
> fichier depuis le bucket (dans un temporaire, supprimé aussitôt). C'est le
> compromis assumé du disque libéré.

## 6. Sauvegardes

`deploy/backup.sh` **suit le mode de stockage** déclaré dans le `.env` — c'est
important : sauvegarder `backend/data/` sans regarder produirait, après la
bascule en stockage objet, une archive vide sans que rien ne l'annonce.

| `FASO_STOCKAGE` | Ce qui est sauvegardé | Comment |
|---|---|---|
| `local` | `backend/data/` | archive `tar.gz` horodatée, 14 générations |
| `s3` + Garage local | volumes `garage_meta` et `garage_data` | snapshot des métadonnées puis miroir `rsync` incrémental |
| `s3` externe | rien ici | la durabilité relève du fournisseur (versioning, réplication) |

En mode Garage, les noms de volumes sont **lus sur le conteneur** et non déduits
du nom du dossier : plusieurs projets peuvent cohabiter sur une machine avec des
volumes `<projet>_garage_data`, et se tromper de préfixe sauvegarderait les
données d'un autre. Le miroir est incrémental — seuls les nouveaux blocs
traversent, les blocs de données Garage étant immuables (adressés par contenu).

En mode `local`, le script **échoue** si `backend/data/` est vide : mieux vaut
une sauvegarde en erreur qu'une archive vide passée inaperçue.

```bash
chmod +x deploy/backup.sh
# cron quotidien à 3h
( crontab -l 2>/dev/null; echo "0 3 * * * cd /srv/faso && ./deploy/backup.sh >> /var/log/faso-backup.log 2>&1" ) | crontab -
```

Pousser aussi les sauvegardes hors du VPS (Hetzner Storage Box, rclone vers R2…)
pour se prémunir d'une perte de la machine.

## Durcissement (rappels)

- **Secrets neufs** en prod (ne pas réutiliser le `.env` de dev) : régénérer
  `FASO_SECRET_KEY`, `FASO_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`.
- **Postgres non exposé** : la pile de prod ne publie aucun port de base — n'y
  ajoutez pas de mapping `5432`.
- **`/admin`** : envisager une restriction par IP dans le `Caddyfile` (bloc
  commenté `@adminblocked`) en plus du mot de passe.
- Garder le système à jour (`unattended-upgrades`).
