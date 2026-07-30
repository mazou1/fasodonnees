# Faso Données Publiques — l'information publique du Burkina Faso

[![Licence: GPL-3.0](https://img.shields.io/badge/licence-GPL--3.0-009e49)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-15a35b)
![Vue 3](https://img.shields.io/badge/vue-3-b3841a)
![FastAPI](https://img.shields.io/badge/fastapi-0.11x-15a35b)

Plateforme citoyenne indépendante qui **collecte, archive, structure et restitue
l'information publique burkinabè** : conseils des ministres, nominations, lois et
décrets, marchés publics, budget de l'État, composition du gouvernement et de
l'Assemblée. Chaque donnée affichée est reliée à son document source officiel.

Inspirée de [vie-publique.sn](https://www.vie-publique.sn) (Code for Senegal).

<table>
  <tr>
    <td><img src="docs/captures/accueil.png" alt="Tableau de bord Faso Données Publiques — thème clair"></td>
    <td><img src="docs/captures/accueil-dark.png" alt="Tableau de bord Faso Données Publiques — thème sombre"></td>
  </tr>
</table>

<p align="center"><em>Interface en thème clair et sombre.</em></p>

## Principes

1. **Sources officielles uniquement** — sites gouvernementaux (`.gov.bf`),
   Assemblée, Présidence, Légiburkina, et médias publics pour le fil d'actualités.
2. **Chaque chiffre est sourcé** — toute décision, nomination ou montant renvoie
   au compte rendu ou au texte officiel dont il est extrait.
3. **Rien n'est publié sans validation humaine** — l'extraction automatique
   (LLM) produit des entités `a_valider` ; seules les entités validées dans le
   back-office sortent sur l'API et le site.
4. **Le corpus est archivé en propre** — les sites officiels dépublient ;
   chaque document collecté (HTML, PDF) est conservé tel quel avant traitement.

## Ce que couvre la plateforme

| Section | Contenu |
|---|---|
| **Conseil des ministres** | 160 comptes rendus structurés (2022→) : résumé des décisions, texte intégral, PDF officiel |
| **Décisions** | 1 435 décisions validées, filtrables par ministère et nature |
| **Annuaire de l'État** | 563 institutions (ministères, présidence, justice, régions, police, diplomatie, établissements) ; 8 264 mandats reconstitués, fiches personnalités **désambiguïsées par matricule** (6 157 personnes) ; **titulaires en fonction distingués des anciens** par détection des successions |
| **Gouvernement** | Composition officielle avec portraits (Présidence du Faso), suivie à chaque remaniement |
| **Assemblée** | 71 députés synchronisés depuis an.bf, président de l'ALT, lois votées |
| **Lois & décrets** | ~4 900 textes juridiques (Légiburkina) avec PDF archivés et recherche plein texte (OCR) |
| **Marchés publics** | Attributions extraites des Quotidiens de la DGCMEF (attributaire, montant, objet, secteur), avec **fiche par entreprise** : ce qu'elle a remporté, auprès de quelles autorités contractantes, dans quels secteurs |
| **Finances** | Budget de l'État par exercice, répartition recettes/dépenses, allocations sectorielles, 428 engagements chiffrés du Conseil des ministres |
| **Documents** | Bibliothèque de ~5 000 documents officiels archivés, facettes par type et source |
| **Recherche** | Plein texte français sur tout le corpus, extraits surlignés |
| **Justice & contrôle** | Jurisprudence du Conseil constitutionnel (décisions, avis, ordonnances depuis 2011) et rapports d'audit de l'ASCE-LC (SONABHY, SONABEL, rapports annuels d'activités) |
| **Suivi des annonces** | Dossiers reliant l'annonce en Conseil des ministres, le marché attribué et l'ouvrage livré — le stade atteint n'est affiché que si une pièce l'atteste |
| **Dossiers** | Grands sujets (dont le [Plan de relance PND 2026-2030](apps/plan-relance/)) |

<table>
  <tr>
    <td><img src="docs/captures/conseils.png" alt="Conseils des ministres"></td>
    <td><img src="docs/captures/finances.png" alt="Finances publiques"></td>
    <td><img src="docs/captures/gouvernement.png" alt="Gouvernement"></td>
  </tr>
</table>

L'annuaire est organisé par institution (ministères, régions, juridictions,
établissements…), chaque ministère regroupant ses intitulés successifs :

![Annuaire de l'État par institution](docs/captures/annuaire.png)

## Architecture

Le principe directeur : **une donnée ne devient publique qu'après validation
humaine**. Tout ce qui est automatique (collecte, structuration LLM, géocodage)
produit des entités `a_valider` ; seul un humain les fait passer à `valide`, et
l'API ne sert jamais que le `valide`.

### Vue d'ensemble du pipeline

```mermaid
flowchart TB
    subgraph SRC["1 · Sources officielles"]
        direction LR
        S1["gouvernement.gov.bf<br/>Comptes rendus du CM"]
        S2["legiburkina · dgcmef<br/>finances · assemblée · présidence"]
        S3["Médias (RSS)<br/>lefaso · sidwaya · aib…"]
    end

    subgraph WORKER["2 · Worker (conteneur séparé) — APScheduler"]
        COL["Collecteurs httpx<br/>registre + déclencheurs cron"]
        ARCH[("data/ — archives brutes<br/>PDF · HTML (hors git)")]
    end

    subgraph EXTRACT["3 · Structuration"]
        PDF["PDF → texte (pdfplumber)"]
        OCR["OCR Tesseract (scans)"]
        LLM["Extraction LLM<br/>Mistral small → Claude (repli)<br/>sortie = schéma Pydantic"]
        RGX["Regex déterministe<br/>matricules · liaisons géo"]
    end

    GATE{{"4 · VALIDATION HUMAINE<br/>a_valider ➜ valide<br/>back-office SQLAdmin"}}

    subgraph CONSO["5 · Consolidation (jobs idempotents)"]
        direction LR
        ANN["Annuaire<br/>nominations → mandats + successions"]
        DES["Désambiguïsation<br/>homonymes par matricule"]
        GEO["Géocodage PostGIS<br/>pg_trgm (fuzzy)"]
        FUS["Fusion des doublons<br/>de structures"]
    end

    DB[("6 · PostgreSQL + PostGIS<br/>pg_trgm · tsvector (recherche)")]
    API["7 · API FastAPI<br/>/api/… · RSS · OpenAPI"]
    WEB["8 · SPA Vue 3 (nginx, proxy /api)<br/>ECharts · MapLibre<br/>+ sous-app React /plan-relance"]

    SRC --> COL --> ARCH
    ARCH --> PDF --> LLM
    ARCH --> OCR --> LLM
    PDF --> RGX
    LLM --> GATE
    RGX --> GATE
    GATE -->|entités validées| CONSO
    CONSO --> DB
    DB --> API --> WEB
```

### Le flux, étape par étape

1. **Collecte** — le *worker* (conteneur distinct de l'API) interroge les sources
   à leur cadence (`interval` 30 min pour les médias, `cron` pour l'institutionnel).
   Chaque collecteur est enregistré dans un *registre* et écrit d'abord l'original
   (PDF/HTML) dans `data/` : la source brute est archivée avant tout traitement.
2. **Structuration** — les PDF sont convertis en texte (pdfplumber), les scans
   passent par l'OCR (Tesseract). Le texte est envoyé au LLM (Mistral `small` par
   défaut, repli Claude), qui **retourne un objet conforme à un schéma Pydantic**
   (décisions, nominations, engagements financiers, réalisations). Ce qui est
   déterministe — matricules, paires de localités d'une route — passe par du
   **regex**, pas par le LLM.
3. **Validation humaine** — toute entité extraite naît `a_valider`. Le tableau de
   bord « À valider » de `/admin` (SQLAdmin) la présente par type ; on valide à la
   main, ou en masse au-dessus d'un seuil de confiance (`python -m app.validation 0.9`).
4. **Consolidation** — des jobs *idempotents* recalculent l'annuaire (nominations →
   mandats, fins de poste par succession), éclatent les homonymes par matricule,
   géocodent les lieux (PostGIS + trigrammes) et proposent les doublons de structures.
5. **Publication** — l'API FastAPI ne lit que le `valide`, expose `/api/…`, un flux
   RSS et l'OpenAPI ; la SPA Vue 3 (servie par nginx qui proxifie `/api`) la
   consomme, avec ECharts pour les graphes et MapLibre pour la carte des
   infrastructures.

### Organisation du dépôt

```
backend/
  app/
    api/            # routes publiques (conseils, annuaire, finances, recherche…) + rss
    ingestion/      # collecteurs httpx + registre + scheduler (le worker)
    extraction/     # LLM (Mistral/Claude), PDF → texte, OCR Tesseract, réalisations
    admin.py        # back-office SQLAdmin (validation + tableau « À valider »)
    validation.py   # validation en masse par seuil de confiance
    annuaire.py     # consolidation nominations → mandats (+ fins de poste par succession)
    annuaire_succession.py  # identité d'un siège : titulaire unique vs collégial
    annuaire_taxonomie.py   # type d'institution, portefeuilles, régions (réforme 2025)
    desambiguisation.py     # homonymes : matricules extraits des CR
    fusion.py       # dédoublonnage des structures
    attributaires.py # entreprises attributaires : regroupement des raisons sociales
    projets.py      # dossiers de suivi : annonce → attribution → livraison
    stockage.py     # archive brute : disque local ou bucket S3 (Garage/externe)
    geo.py          # géocodage (PostGIS, pg_trgm) ; geo_seed.py charge le gazetteer
    models.py       # schéma SQLAlchemy ; alembic/ = migrations
frontend/           # SPA Vue 3 + Vite, servie par nginx (proxy /api)
apps/plan-relance/  # dossier interactif PND 2026-2030 (React, servi sous /plan-relance/)
deploy/             # mise en production VPS (compose prod, Caddy, migration des données)
docs/               # cadrage, rapports, captures d'écran
data/               # archives brutes — hors git, à sauvegarder
```

### Évolutions possibles des briques techniques

Les choix actuels privilégient le **coût nul et la simplicité d'un VPS unique**.
Chaque brique a une voie de montée en charge sans réécriture :

| Brique | Choix actuel | Pourquoi | Évolution possible |
|---|---|---|---|
| Extraction LLM | Mistral `small` (tier gratuit) → repli Claude | coût nul, ~1 req/s suffit au volume | modèle plus grand pour les CR difficiles ; ou modèle local (Ollama) pour l'indépendance |
| Ordonnancement | APScheduler `BlockingScheduler` dans un worker | un seul process, zéro infra | file de tâches (Celery/RQ + Redis) si la collecte se parallélise |
| Base de données | PostgreSQL + PostGIS (pg_trgm, tsvector) | recherche plein-texte et géo sans service tiers | index dédié (OpenSearch/Meilisearch) si la recherche devient centrale |
| Validation | back-office SQLAdmin | rapide à livrer, suffisant à un valideur | interface dédiée + rôles/traçabilité pour plusieurs relecteurs |
| Frontend | SPA Vue 3 + Vite, `dist` servie par nginx | statique, cacheable, pas de SSR à opérer | SSR/SSG (Nuxt) pour le SEO et le partage social |
| Cartographie | MapLibre GL + tuiles CARTO | pas de clé API, thème clair/sombre | fonds de carte auto-hébergés (tuiles vectorielles) pour l'autonomie |
| Déploiement | Docker Compose, VPS unique derrière Caddy | un serveur, HTTPS automatique | conteneurs séparés / orchestrateur si le trafic l'exige ; réplique de lecture DB |
| Archivage `data/` | disque du VPS **ou** bucket S3 (`FASO_STOCKAGE`) | le disque ne demande aucune dépendance ; le bucket sert les PDF par URL présignée et prépare la sortie de machine | Garage sur un hôte séparé ou en multi-nœud, ou S3 externe — l'endpoint suffit à basculer |

## Sources collectées

| Source | Type | Cadence |
|---|---|---|
| gouvernement.gov.bf | Comptes rendus du Conseil des ministres | jeudi + rattrapages |
| legiburkina.gov.bf | Lois, décrets, arrêtés (+ PDF) | quotidien |
| assembleenationale.bf | Députés, président de l'ALT | quotidien |
| presidencedufaso.bf | Communiqués (RSS), composition du gouvernement | quotidien |
| dgcmef.gov.bf | Quotidiens des marchés publics (attributions) | quotidien |
| conseil-constitutionnel.gov.bf | Décisions, avis et ordonnances (PDF, par année) | hebdomadaire |
| asce-lc.bf | Rapports d'audit et de contrôle, affaires anticorruption, déclarations de patrimoine | hebdomadaire |
| finances.gov.bf | Veille du Budget citoyen | quotidien |
| lefaso.net, sidwaya.info, aib.media, burkina24.com, lepays.bf | Actualités (RSS) | 30 min |

## Démarrage rapide (Docker)

```bash
cp .env.example .env        # ajuster mots de passe et clé LLM
docker compose up --build
```

- Site : http://localhost:8090
- API + doc OpenAPI : http://localhost:8001/docs (ou /api/docs via le site)
- Back-office : http://localhost:8001/admin
- Le worker collecte selon les cadences ci-dessus.

> ⚠️ Les images `api` et `worker` embarquent le code : après une modification
> backend, `docker compose up -d --build api worker` (un simple `restart` ne
> recharge rien).

## Développement local

```bash
# Backend
docker compose up -d db                      # Postgres/PostGIS sur localhost:5434
cd backend
uv venv && uv pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload      # API sur :8000
.venv/bin/pytest

# Frontend
cd frontend && npm install && npm run dev    # Vite proxy /api → :8000

# Dossier Plan de relance (après modification de apps/plan-relance/src)
cd apps/plan-relance && npm install && npm run build   # sortie dans frontend/public/
```

## Déploiement

Pour mettre en production sur un VPS unique (Hetzner) derrière Caddy (HTTPS
automatique), voir **[`deploy/README.md`](deploy/README.md)** : pile
`docker-compose.prod.yml`, reverse proxy, et **migration des données locales
sans retraitement** (la base déjà calculée est copiée telle quelle ;
l'extraction LLM et l'OCR ne sont pas relancés).

## Cycle de vie des données

```bash
python -m app.ingestion.run all           # collecte manuelle (sinon : worker)
python -m app.extraction.run 5            # structuration LLM des 5 prochains CR
# → valider : back-office /admin (page « ① À valider »), ou en masse par seuil
#   de confiance : python -m app.validation 0.9
python -m app.desambiguisation           # matricules + éclatement des homonymes
python -m app.annuaire                    # reconsolide les mandats (+ successions)
python -m app.fusion proposer 0.75        # doublons de structures → CSV à relire
python -m app.extraction.ocr_textes 500   # OCR des textes scannés (worker, Tesseract)
python -m app.attributaires consolider    # regroupe les raisons sociales des marchés
python -m app.attributaires proposer 0.65 # variantes proches → CSV à relire, puis « appliquer »
python -m app.extraction.marches dedoublonner  # purge les republications du Quotidien
python -m app.projets proposer 0.30       # annonce ↔ marché ↔ réalisation → CSV à relire
python -m app.projets appliquer projets_propositions.csv   # crée les dossiers acceptés
python -m app.projets statuts             # récapitulatif des dossiers et de leur stade
python -m app.versions consolider         # ramène les entités sur la version de référence
python -m app.ingestion.conseil_constitutionnel   # rattrapage : toutes les années
#   (la collecte périodique du worker ne revisite que les millésimes récents ;
#    ce rattrapage est à lancer au premier remplissage ou après interruption)
```

L'extraction LLM ne publie jamais seule : elle produit des entités `a_valider`,
qu'un humain valide dans le back-office. Le tableau de bord **« À valider »** de
`/admin` montre en un coup d'œil ce qui attend une action, par type. L'extraction
utilise **Mistral** par défaut (`FASO_LLM_PROVIDER=mistral`, tier gratuit) avec
bascule possible vers l'API Claude.

## Méthodologie et limites

- Les entités extraites automatiquement portent un score de confiance et ne
  sont **jamais publiées sans validation** dans le back-office.
- Les homonymes de l'annuaire sont distingués par le **matricule de la fonction
  publique** cité dans les comptes rendus (couvre ~91 % des nominations) ; les
  fiches concernées affichent une note de méthode.
- L'annuaire est **organisé par institution** ; le type (ministère, région,
  juridiction, établissement…) et le nom courant sont déduits des données :
  les ministères regroupent leurs intitulés successifs sous le libellé du
  gouvernement en vigueur, et les régions portent leur nom officiel actuel avec
  l'ancien en rappel (« Région Liptako (ex-Sahel) », réforme du 2 juillet 2025).
- Un titulaire est marqué **« Ancien »** quand un successeur a été nommé au même
  siège à titulaire unique (directeur général, secrétaire général, préfet…) ;
  les postes collégiaux (administrateurs, conseillers…) restent multiples. Les
  comptes rendus annonçant rarement une fin explicite, cette détection par
  succession est prudente : au pire un mandat clos reste affiché « en cours »,
  jamais l'inverse.
- Légiburkina publie ~96 % de scans : la recherche couvre référence et
  description pour tout le corpus, le texte intégral progresse avec l'OCR.
- **Entreprises attributaires** : le Quotidien de la DGCMEF ne tient aucun
  registre d'entreprises et écrit la même société de plusieurs façons
  (« ETS WEND-KUUNI », « Ets Wend Kuuni SARL »…). Les fiches entreprise
  regroupent ces graphies, mais **uniquement** sur des différences
  typographiques (casse, accents, ponctuation, forme juridique) ; deux raisons
  sociales réellement distinctes ne sont jamais réunies sans relecture humaine
  (`app.attributaires proposer`). Chaque fiche liste les graphies qu'elle
  réunit. Le regroupement ne dit rien de la propriété réelle : deux sociétés
  liées mais nommées différemment restent deux fiches.
- **La source réécrit ses comptes rendus.** Le gouvernement retouche ses pages
  après publication : le compte rendu du 23 juillet 2026 est passé de 66 571 à
  71 390 octets entre le 24 et le 29 juillet. Chaque version est archivée — cela
  **établit** le fait, et c'est précieux — mais une seule, la plus récente, porte
  l'extraction et l'affichage (`app/versions.py`) ; sans quoi le LLM repassait
  sur chaque version et le site listait le même conseil deux à quatre fois. Les
  fiches signalent « réécrit par la source », avec la date du **constat** — nous
  ne savons pas quand la retouche a eu lieu, seulement quand nous l'avons vue.
  Limite assumée : le LLM ne reformule pas à l'identique d'une passe à l'autre,
  donc les variantes issues des extractions déjà faites subsistent et se
  tranchent à la relecture.
- **Justice & contrôle — une couverture incomplète, et volontairement dite
  comme telle.** Le Conseil constitutionnel et l'ASCE-LC sont collectés ; la
  **Cour des comptes**, juridiction financière qui juge les comptes publics et
  contrôle l'exécution des lois de finances, **n'a aucun site accessible**
  (aucun domaine connu ne répond, vérifié le 2026-07-29). Ses rapports ne sont
  donc pas collectables et la section le signale explicitement plutôt que de
  laisser croire à une couverture complète du contrôle de l'État. Par ailleurs
  le Conseil constitutionnel publie presque exclusivement des **scans** : la
  recherche plein texte sur ces décisions progresse au rythme de l'OCR, qui les
  traite en priorité (peu nombreuses, et introuvables sans texte).
- **Suivi des annonces** : les trois corpus (engagements du Conseil des
  ministres, marchés attribués, inaugurations) ne partagent **aucun
  identifiant de projet**. Un dossier de suivi est donc une *interprétation* :
  le rapprochement est proposé automatiquement — sur les mots rares partagés,
  corroborés par le montant, la chronologie et le secteur — puis **accepté par
  un relecteur** avant publication. Un dossier ne prétend pas être exhaustif :
  d'autres marchés peuvent concerner le même projet sans y figurer. Une étape
  de la chaîne n'est affichée comme franchie que si une pièce l'atteste ; une
  étape éteinte signifie « non documenté ici », pas « non réalisé ». Enfin,
  l'écart entre montant annoncé et montant attribué ne se lit pas comme un
  écart d'exécution — un marché ne couvre souvent qu'un lot de l'annonce.
- **Republications du Quotidien** : la DGCMEF reprend la même synthèse de
  résultats dans des numéros successifs (une attribution vue dans 18 numéros
  d'affilée). Une attribution n'est comptée qu'à sa première parution, ce qui
  évite de multiplier les totaux par entreprise ; les numéros restent tous
  archivés.
- Les traductions des CR en langues nationales (mooré, fulfuldé, dioula,
  gulimancema) sont archivées mais exclues de l'extraction.
- Détail complet : page « À propos & méthodologie » du site, et
  [`docs/cadrage-plateforme-civique-v2.md`](docs/cadrage-plateforme-civique-v2.md).

## API ouverte

Toutes les données validées sont servies par une API documentée (OpenAPI) :

```bash
curl 'http://localhost:8090/api/conseils?par_page=5'
curl 'http://localhost:8090/api/recherche?q=barrage'
curl 'http://localhost:8090/api/finances/stats'
```

## Contribuer

Faso Données Publiques est **libre et collaboratif** : il vit des contributions de chacun.
On peut aider **sans écrire une ligne de code** :

- 🔗 **Signaler une source cassée** — les sites officiels changent d'adresse ou
  dépublient souvent. Ces signalements sont précieux.
- 📚 **Proposer une nouvelle source** officielle à collecter.
- 👀 **Relire les données** — repérer une erreur d'extraction, un doublon, une
  fonction périmée, et l'indiquer en issue.
- 🐛 **Signaler un bug** ou suggérer une amélioration du site.

Et bien sûr, côté technique : nouveaux collecteurs, dossiers thématiques,
améliorations du front, tests. Tout passe par une **issue** (gabarits fournis :
bug, source cassée, proposition de source) puis une **pull request**.

👉 Guide complet dans **[CONTRIBUTING.md](CONTRIBUTING.md)** : mise en place,
conventions du projet, ajout d'un collecteur, pièges connus.

Principe non négociable : le projet est **citoyen, indépendant et non partisan**,
et **aucune donnée n'est publiée sans être sourcée et validée**.

## Licence et crédits

Code sous licence [GPL-3.0](LICENSE). Les données restituées proviennent de
documents publics officiels burkinabè, cités et liés partout où elles
apparaissent. Merci à [Code for Senegal](https://github.com/Code-for-Senegal)
dont [vie-publique.sn](https://www.vie-publique.sn) a inspiré ce projet.
