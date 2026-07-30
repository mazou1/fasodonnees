# Contribuer à Faso Données Publiques

Merci de votre intérêt ! Faso Données Publiques est un projet **citoyen, indépendant et
libre** (GPL-3.0) qui rend l'information publique burkinabè accessible et
vérifiable. Il vit de contributions de toutes sortes — et beaucoup ne demandent
aucune compétence technique.

## Aider sans coder

- 🔗 **Signaler une source cassée ou dépubliée.** Les sites officiels changent
  d'URL, tombent en panne ou retirent des documents. Ouvrez une issue « source
  cassée » avec l'adresse concernée — c'est l'une des contributions les plus
  utiles.
- 📚 **Proposer une source officielle** à collecter (issue « proposition de
  source ») : quelle institution, quelle URL, quel type de contenu.
- 👀 **Relire les données publiées.** Une nomination mal rattachée, un doublon,
  un montant douteux, une fonction périmée ? Signalez-le en issue avec le lien
  de la page et, si possible, celui du document source.
- 🐛 **Signaler un bug** ou proposer une amélioration de l'interface.

Pas besoin de tout vérifier vous-même : décrivez ce que vous avez vu, on
s'occupe du reste.

## Contribuer au code

### Mise en place

Voir le [README](README.md#développement-local). En résumé : Postgres via Docker
(`docker compose up -d db`), backend Python 3.12 avec
[uv](https://github.com/astral-sh/uv), frontend Vue 3 avec Vite.

Ports locaux non standard (des projets voisins occupent les ports usuels) :
Postgres **5434**, API **8001**, site **8090**.

### Conventions du projet

- **Tout est en français** : code (noms de variables, docstrings), interface,
  messages de commit. Le projet s'adresse à des lecteurs francophones.
- **Rien n'est publié sans validation humaine.** Toute extraction automatique
  produit des entités `statut_validation='a_valider'` ; les routes publiques ne
  servent que le statut `valide`. Ne contournez **jamais** ce principe.
- **Chaque donnée est sourcée.** Une nouvelle table de faits porte un
  `document_id` (ou un `source_libre` explicite) ; une nouvelle vue affiche le
  lien vers la source.
- **Archiver avant de traiter.** Un collecteur écrit le brut dans `data/` (voir
  `Collector.archive`) avant toute extraction.
- **Politesse de collecte** : ≥ 1 s entre requêtes, User-Agent identifiant le
  projet (déjà gérés par `Collector.get`).

### Le cycle de validation

L'extraction (LLM ou déterministe) dépose des entités `a_valider`. Un humain les
valide dans le back-office `/admin` :

- la page **« ① À valider »** liste, par type, ce qui attend une action, avec un
  accès direct à chaque file ;
- chaque file n'affiche que les éléments `a_valider`, avec cases à cocher et
  boutons **✓ Valider / ✗ Rejeter** ;
- pour dégrossir un lot, `python -m app.validation 0.9` valide en masse ce qui
  dépasse un seuil de confiance ; le reste est revu à la main.

Après validation de nominations, reconsolider l'annuaire :
`python -m app.desambiguisation` puis `python -m app.annuaire`.

### Ajouter un collecteur

1. Créer `backend/app/ingestion/<source>.py` héritant de `Collector`
   (voir `assemblee.py` pour un exemple court, `wordpress.py` pour un site WP).
2. Déclarer la source dans `SEEDS` et la classe dans `COLLECTORS`
   (`ingestion/registry.py`).
3. Tester en réel : `python -m app.ingestion.run <slug>` — l'exécution est
   journalisée dans la table `run` (visible dans /admin).

### Ajouter un dossier thématique

Ajouter une entrée dans `frontend/src/views/DossiersView.vue` (titre,
description, étiquettes, lien). Pour un dossier interactif autonome, suivre le
modèle de `apps/plan-relance/` (build embarqué dans `frontend/public/`).

### Pièges connus

- Les images Docker `api` et `worker` **embarquent le code** : après une
  modification backend, `docker compose up -d --build api worker` (pas
  `restart`). Sur WSL, le cache de la couche `COPY` peut ne pas voir un
  changement — `--no-cache` au besoin, et vérifier le code dans l'image.
- **Migrations Alembic** : la colonne `tsv` et l'index `ix_document_tsv` sont
  créés en SQL brut et **exclus de l'autogénération** (filtre `include_name`
  dans `alembic/env.py`). Vérifiez toujours une migration autogénérée.
- L'OCR (Tesseract) tourne dans le worker et monopolise le CPU : mettez le
  conteneur en pause pendant les builds npm.
- **Le Quotidien de la DGCMEF republie ses synthèses de résultats** dans des
  numéros successifs : une même attribution peut apparaître dans une dizaine
  de PDF. Toute agrégation sur les marchés (total par entreprise, par secteur)
  compterait plusieurs fois la même chose. `app/extraction/marches.py` ne
  retient une attribution qu'à sa première parution, via une empreinte
  (référence, attributaire, montant, objet) — n'insérez jamais un `Marche`
  sans passer par `traiter_document`.
- **Ne construisez jamais un chemin vers `settings.data_dir`.** L'archive vit
  sur le disque *ou* dans un bucket S3 selon `FASO_STOCKAGE` : un chemin
  fabriqué à la main marche en local et casse en production, sans bruit. Tout
  passe par `app/stockage.py` — `stockage.ecrire()` pour archiver,
  `with stockage.fichier_local(cle) as chemin:` quand une bibliothèque exige un
  vrai fichier (pdfplumber, pypdf, Tesseract), `stockage.url_ou_chemin()` pour
  servir. `Document.fichier` contient une **clé**, pas un chemin.
- **Un même document existe en plusieurs versions.** `upsert_document`
  versionne au lieu d'écraser (même URL + hash différent = nouvelle ligne), car
  les sources réécrivent leurs pages après publication. Toute requête qui
  compte, extrait ou affiche des documents doit donc filtrer sur
  `app.versions.ids_versions_de_reference()` — sinon le LLM retraite chaque
  version et le site liste le même conseil plusieurs fois.
- **Un PDF téléchargé n'est pas un texte cherchable.** Un collecteur qui
  archive un PDF doit poser `meta["pdf_statut"]` : c'est ce marqueur — et non
  `statut_extraction` — que suit la passe OCR (`app/extraction/ocr_textes.py`),
  et un nouveau `type_doc` doit être ajouté à ses `TYPES_CIBLES`. Sans les
  deux, les scans restent invisibles à la recherche, en silence.
- **Un dossier de suivi n'est pas une donnée officielle** : relier une
  inauguration à un marché et à une annonce est une *interprétation* de la
  plateforme. Ne créez jamais de rattachement automatique publié d'office —
  `app/projets.py` propose, un humain accepte. Et n'affichez une étape de la
  chaîne comme franchie que si une pièce l'atteste : sur ce sujet, laisser
  croire qu'un ouvrage est livré ou qu'un marché existe est une faute, pas une
  approximation.
- **Les raisons sociales des marchés ne sont pas un référentiel** : la même
  entreprise y est écrite de plusieurs façons. Comptez les entreprises sur
  l'entité consolidée (`attributaire.id`, regroupée par
  `coalesce(canonique_id, id)`), jamais sur la chaîne `marche.attributaire`
  — celle-ci reste la trace exacte du document et ne doit pas être réécrite.

## Issues et pull requests

- Utilisez les **gabarits d'issues** : bug, source cassée ou dépubliée,
  proposition de source.
- **Une PR = un sujet.** Décrivez ce qui change et comment vous l'avez vérifié.
- `pytest` doit passer (`cd backend && .venv/bin/pytest`). Pour le front,
  vérifiez au navigateur les pages touchées, dans les **deux thèmes**
  (clair/sombre), sans erreur console.
- Terminez les messages de commit et descriptions de PR en français.

## Code de conduite

Projet citoyen, indépendant et **non partisan**. Soyez respectueux et
constructif dans les échanges. Les contributions à visée partisane ou les
données non sourcées ne sont pas acceptées.
