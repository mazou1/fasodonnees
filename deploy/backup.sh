#!/usr/bin/env bash
# Sauvegarde de production : base (pg_dump) + corpus brut.
# À lancer depuis la racine du dépôt sur le VPS. Idéal en cron quotidien.
#
#   0 3 * * *  cd /srv/faso && ./deploy/backup.sh >> /var/log/faso-backup.log 2>&1
#
# Le corpus ne vit pas toujours au même endroit (cf. FASO_STOCKAGE) :
#
#   local        → dossier backend/data/          → archive tar
#   s3 + Garage  → volumes garage_meta/garage_data → miroir rsync incrémental
#   s3 externe   → bucket du fournisseur          → sa propre durabilité
#
# Ce script suit ce que dit le .env. Sauvegarder `data/` sans regarder, comme
# le faisait la version précédente, produirait une archive vide et silencieuse
# le jour de la bascule vers le stockage objet — le pire des scénarios : des
# sauvegardes qui tournent, et rien dedans.
set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"
DEST="${FASO_BACKUP_DIR:-/srv/faso-backups}"
HORODATAGE="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"

# Le .env porte le mode de stockage ; on ne l'exporte pas globalement pour ne
# pas polluer l'environnement avec les secrets qu'il contient.
STOCKAGE="$(grep -E '^FASO_STOCKAGE=' .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' ' || true)"
STOCKAGE="${STOCKAGE:-local}"

echo "[$(date)] Dump de la base…"
$COMPOSE exec -T db pg_dump -U faso -Fc faso > "$DEST/faso-$HORODATAGE.dump"
ls -1t "$DEST"/faso-*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f

sauvegarder_local() {
  echo "[$(date)] Archive de backend/data/ (PDF/HTML bruts)…"
  if [ -z "$(find backend/data -type f -print -quit 2>/dev/null)" ]; then
    echo "ERREUR : FASO_STOCKAGE=local mais backend/data/ est vide." >&2
    echo "         Le corpus est peut-être déjà passé en stockage objet." >&2
    return 1
  fi
  tar -czf "$DEST/data-$HORODATAGE.tar.gz" -C backend data
  ls -1t "$DEST"/data-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
  du -sh "$DEST/data-$HORODATAGE.tar.gz"
}

sauvegarder_garage() {
  local conteneur conteneur_api vol_meta vol_data miroir
  miroir="$DEST/garage"
  mkdir -p "$miroir"
  conteneur_api="$($COMPOSE ps -q api)"

  # Les noms de volumes sont LUS sur le conteneur, jamais déduits du nom du
  # dossier : plusieurs projets peuvent cohabiter sur la même machine avec des
  # volumes « <projet>_garage_data », et se tromper de préfixe sauvegarderait
  # les données de quelqu'un d'autre.
  conteneur="$($COMPOSE ps -q garage)"
  if [ -z "$conteneur" ]; then
    echo "ERREUR : conteneur garage introuvable." >&2
    return 1
  fi
  vol_meta="$(docker inspect "$conteneur" \
    --format '{{range .Mounts}}{{if eq .Destination "/var/lib/garage/meta"}}{{.Name}}{{end}}{{end}}')"
  vol_data="$(docker inspect "$conteneur" \
    --format '{{range .Mounts}}{{if eq .Destination "/var/lib/garage/data"}}{{.Name}}{{end}}{{end}}')"
  if [ -z "$vol_meta" ] || [ -z "$vol_data" ]; then
    echo "ERREUR : volumes Garage introuvables sur le conteneur $conteneur." >&2
    return 1
  fi
  echo "[$(date)] Volumes : $vol_meta, $vol_data"

  # Métadonnées : snapshot cohérent avant copie. Les blocs de données, eux,
  # sont immuables (adressés par contenu) : les copier à chaud est sans risque.
  echo "[$(date)] Snapshot des métadonnées Garage…"
  $COMPOSE exec -T garage /garage meta snapshot --all || {
    echo "AVERTISSEMENT : snapshot impossible — Garage tourne-t-il ?" >&2
    return 1
  }

  # Miroir incrémental : seuls les nouveaux blocs traversent. Un conteneur
  # jetable monte les volumes en lecture seule ; pas besoin de fouiller
  # /var/lib/docker depuis l'hôte.
  #
  # On réutilise l'image du projet (rsync y est installé) plutôt que d'en tirer
  # une tierce : la sauvegarde tourne de nuit, sans surveillance, et ne doit pas
  # dépendre d'un registre joignable ni d'une installation de paquet.
  local image
  image="$(docker inspect "$conteneur_api" --format '{{.Config.Image}}' 2>/dev/null)"
  if [ -z "$image" ]; then
    echo "ERREUR : image applicative introuvable (conteneur api démarré ?)." >&2
    return 1
  fi
  echo "[$(date)] Miroir des volumes Garage vers $miroir…"
  docker run --rm \
    -v "$vol_meta:/src/meta:ro" \
    -v "$vol_data:/src/data:ro" \
    -v "$miroir:/dest" \
    "$image" rsync -a --delete /src/ /dest/
  du -sh "$miroir"
}

case "$STOCKAGE" in
  local)
    sauvegarder_local
    ;;
  s3)
    if $COMPOSE ps --services --filter status=running 2>/dev/null | grep -qx garage; then
      sauvegarder_garage
    else
      echo "[$(date)] FASO_STOCKAGE=s3 sans conteneur Garage : le corpus est chez un"
      echo "           fournisseur S3 externe. Sa durabilité est de son ressort —"
      echo "           activez versioning et réplication côté fournisseur, ou"
      echo "           ajoutez ici un miroir (rclone sync) vers un second stockage."
    fi
    ;;
  *)
    echo "ERREUR : FASO_STOCKAGE inconnu ($STOCKAGE)" >&2
    exit 1
    ;;
esac

echo "[$(date)] Sauvegarde terminée dans $DEST (mode : $STOCKAGE)"
du -sh "$DEST/faso-$HORODATAGE.dump"
