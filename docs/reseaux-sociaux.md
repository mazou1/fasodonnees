# Diffusion automatique sur les réseaux sociaux

La plateforme publie elle-même, depuis le worker, ce qu'elle vient de collecter :
comptes rendus du Conseil des ministres, décisions validées et fil d'actualités.
Aucun service tiers n'a la main sur les pages.

Le code vit dans `backend/app/diffusion/` ; ce document décrit ce qui reste à
faire **hors du dépôt** : créer les comptes, obtenir les jetons, activer.

---

## 1. Ce qui est publié, et où

| Genre | Contenu | Lien du post |
|---|---|---|
| `conseil` | Compte rendu du Conseil des ministres | page du site `/conseils/{id}` |
| `decision` | Décision **validée** dans `/admin` | page du conseil dont elle est issue |
| `actualite` | Annonces officielles (`actualite_gouv`) et communiqués | l'article de la source, créditée dans le post |

Les actualités renvoient à leur source, comme le fait déjà la page
`/actualites` du site : la plateforme collecte les métadonnées, pas le texte
des articles, et capter le trafic d'un travail qui n'est pas le sien
desservirait le lecteur autant que la source. Le post porte donc « via … ».

**Par défaut, seules les sources officielles sont diffusées**
(`FASO_DIFFUSION_TYPES_ACTUALITE=actualite_gouv,communique`). Mesuré en
production : les cinq médias collectés publient une centaine de dépêches par
jour, contre une dizaine d'annonces gouvernementales. Les verser sans
distinction noie l'information publique sous les dépêches - jusqu'aux tournois
de quartier et aux avis de recrutement. Ajouter `article_presse` à la liste
verse le fil de presse ; le canal devient alors un fil d'actualité généraliste,
ce qui est un autre métier.

Les comptes rendus et les décisions, eux, sont du contenu propre : ils renvoient
au site.

**Rien n'est publié sans validation humaine.** Seules les décisions dont le
statut est `valide` sortent. Une extraction LLM non relue publiée sur une page
publique serait bien plus difficile à rattraper qu'une ligne fausse dans le
back-office.

## 2. Les garde-fous

Ils sont là parce qu'un post n'est plus rattrapable une fois parti :

- **Coupe-circuit** — `FASO_DIFFUSION_ACTIVE=false` par défaut. Une base
  restaurée, une pile de recette ou un worker lancé par erreur ne postent rien,
  même avec des jetons valides.
- **Anti-doublon** — une ligne par couple (réseau, item) dans la table
  `publication`, sous contrainte d'unicité. La clé ne dépend ni de la date
  d'exécution ni du `document.id` : le gouvernement réécrit ses pages après
  publication, et une réécriture ne doit pas passer pour une nouveauté.
- **Fenêtre de fraîcheur** — `FASO_DIFFUSION_FRAICHEUR_JOURS=2`. Activer la
  diffusion sur une base de 160 comptes rendus et 5 000 documents ne déverse
  pas des années d'archives, et un flux d'actualités plus rapide que le quota
  d'un réseau ne crée pas un retard qui s'aggrave chaque jour.
- **Quota glissant sur 24 h**, par réseau. Il protège le plafond mensuel de X
  quelles que soient les heures de redémarrage.
- **Priorité** — un compte rendu passe avant une dépêche. Sans cela le volume
  des actualités mangerait tout le quota.
- **Arrêt au premier refus** — un jeton expiré refusera aussi les suivants.
  Après trois échecs sur un même item, il est abandonné.

## 3. Créer les comptes

### Telegram (le plus simple, à faire en premier)

1. Sur Telegram, écrire à **@BotFather** → `/newbot`, choisir un nom et un
   identifiant (ex. `faso_donnees_bot`). Il renvoie un jeton `123456:AA...`.
2. Créer un **canal public** (ex. `@faso_donnees`).
3. Ajouter le bot comme **administrateur du canal**, avec le droit de publier.
   Sans ce droit, l'API répond `chat not found` ou `not enough rights`.

```
FASO_TELEGRAM_BOT_TOKEN=123456:AA...
FASO_TELEGRAM_CHAT_ID=@faso_donnees
```

### Facebook (le plus utile au Burkina, le plus long à ouvrir)

1. Créer la **page** Facebook.
2. Sur [developers.facebook.com](https://developers.facebook.com) : créer une
   application de type « Entreprise ».
3. Ajouter le produit **Facebook Login**, puis dans l'explorateur d'API
   (Graph API Explorer) demander les permissions
   `pages_manage_posts` et `pages_read_engagement`.
4. Récupérer un jeton d'utilisateur, l'échanger contre un **jeton longue durée**,
   puis obtenir le **jeton de page** via `GET /me/accounts`. Un jeton de page
   issu d'un jeton utilisateur longue durée n'expire pas.
5. Publier l'application (mode « Live ») : en mode développement, seuls les
   comptes de test peuvent publier.

```
FASO_FACEBOOK_PAGE_ID=1234567890
FASO_FACEBOOK_PAGE_TOKEN=EAAG...
```

> La revue Meta est la seule étape qui peut prendre plusieurs jours. Les deux
> autres réseaux fonctionnent sans attendre : rien n'oblige à tout activer le
> même jour.

### X

1. Sur [developer.x.com](https://developer.x.com), créer un projet et une app.
2. Régler les **permissions de l'app sur « Read and write »** AVANT de générer
   les jetons : des jetons créés en lecture seule restent en lecture seule, et
   l'erreur renvoyée à la publication (`403`) ne le dit pas clairement.
3. Générer les 4 secrets OAuth 1.0a.

```
FASO_X_API_KEY=...
FASO_X_API_SECRET=...
FASO_X_ACCESS_TOKEN=...
FASO_X_ACCESS_SECRET=...
```

Le palier gratuit plafonne à **500 posts par mois** en écriture. Le quota par
défaut (12/jour) laisse environ 370 par mois, sous le plafond même un mois
chargé.

## 4. Mise en route

Tout se fait depuis le conteneur `worker`, sans rien publier tant que le
coupe-circuit est ouvert.

```bash
# 1. les jetons sont-ils bons ? (aucune publication)
docker compose -f docker-compose.prod.yml exec worker \
  python -m app.diffusion.run --verifier

# 2. que serait-il publié, et à quoi ressemblerait le texte ?
docker compose -f docker-compose.prod.yml exec worker \
  python -m app.diffusion.run --simulation

# 3. amorcer : marque comme vu ce qui existe déjà, SANS rien envoyer.
#    Sans cette étape, la première passe déverse d'un coup tout ce que la
#    fenêtre de fraîcheur laisse passer, devant des abonnés pas encore arrivés.
docker compose -f docker-compose.prod.yml exec worker \
  python -m app.diffusion.run --amorcer

# 4. activer : FASO_DIFFUSION_ACTIVE=true dans .env, puis
docker compose -f docker-compose.prod.yml up -d worker

# 5. un premier envoi à la main, sur un seul réseau
docker compose -f docker-compose.prod.yml exec worker \
  python -m app.diffusion.run --reseau telegram
```

Ensuite, le worker publie tout seul à chaque heure (`:20`).

Le résultat se relit dans le back-office : **/admin → Publications (réseaux
sociaux)**. Chaque ligne conserve le texte réellement envoyé, l'identifiant du
post et l'erreur éventuelle. Supprimer une ligne autorise la republication de
cet item — c'est la façon de rejouer un post effacé par erreur.

## 5. Cartes de partage

Le site est une application Vue rendue dans le navigateur : son `index.html`
porte le même titre et la même description pour toutes les pages, et les robots
de Facebook, X ou Telegram n'exécutent pas de JavaScript. Sans traitement
particulier, **tous les posts s'afficheraient avec la même vignette générique**.

`deploy/Caddyfile` route donc ces robots — et eux seuls — vers
`backend/app/api/partage.py`, qui rend le titre et le résumé réels de l'entité.
Un visiteur reçoit la SPA comme avant.

Vérification depuis n'importe quelle machine :

```bash
curl -s -A 'facebookexternalhit/1.1' https://fasodonnees.org/conseils/11473 | grep 'og:'
```

Pour une grande carte illustrée plutôt qu'une carte texte, renseigner
`FASO_OG_IMAGE_URL` avec l'URL absolue d'une image 1200x630.

## 6. Réglages

Toutes les variables sont documentées dans `.env.example`. Les plus utiles au
quotidien :

| Variable | Défaut | Effet |
|---|---|---|
| `FASO_DIFFUSION_ACTIVE` | `false` | coupe-circuit général |
| `FASO_DIFFUSION_GENRES` | `conseil,decision,actualite` | ce qui est publié |
| `FASO_DIFFUSION_TYPES_ACTUALITE` | `actualite_gouv,communique` | sources du genre `actualite` ; ajouter `article_presse` y verse le fil de presse |
| `FASO_DIFFUSION_FRAICHEUR_JOURS` | `2` | au-delà, un item n'est jamais publié |
| `FASO_TELEGRAM_QUOTA_JOUR` | `40` | plafond glissant sur 24 h |
| `FASO_FACEBOOK_QUOTA_JOUR` | `15` | idem |
| `FASO_X_QUOTA_JOUR` | `12` | idem (palier gratuit : 500/mois) |

Publier les actualités uniquement sur Telegram, et garder Facebook pour le
contenu propre, se fait aujourd'hui en réglant `FASO_DIFFUSION_GENRES`
globalement : le filtrage par genre **et** par réseau n'est pas implémenté.

## 7. Ce qui n'est pas couvert

- **WhatsApp** n'a pas d'API de publication pour les canaux. Le partage y reste
  manuel.
- **LinkedIn** demande l'accès à la Community Management API, soumis à
  validation Microsoft ; le client n'est pas écrit.
- Les **images** générées par post (vignette avec le titre) ne sont pas
  produites : les posts sont du texte plus un lien.
