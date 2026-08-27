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

### Facebook

**Aucune revue Meta n'est nécessaire** pour publier sur sa PROPRE Page : une app
en mode Développement suffit dès lors qu'on est administrateur de l'app ET de la
Page, et les publications sont visibles de tous, normalement. Le mode
Développement limite qui peut UTILISER l'app, pas ce qu'elle publie. L'icône
1024x1024, la politique de confidentialité et la catégorie ne servent qu'au
passage en mode Live, c'est-à-dire à l'usage sur des Pages appartenant à
d'autres. Vérifié le 2026-08-27 en ouvrant la Page de la plateforme.

1. Créer la **Page** Facebook.
2. Sur [developers.facebook.com](https://developers.facebook.com), créer une app
   avec le cas d'utilisation **« Gérer des Pages »**. Le type ne se change pas
   après coup : une app **Consommateur** n'ouvrira jamais l'accès aux Pages, et
   le symptôme est net - l'explorateur d'API ne propose que `public_profile`.
3. Dans **Cas d'utilisation → Personnaliser**, ajouter en **accès standard**
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`. L'accès
   avancé déclencherait la revue, dont on n'a pas besoin.
4. Dans l'[explorateur d'API](https://developers.facebook.com/tools/explorer/),
   générer un jeton **utilisateur** avec ces autorisations. À l'écran de
   consentement, **cocher la Page** : c'est là que se fait le rattachement, il
   n'y a rien à « associer » ailleurs.
5. Prolonger le jeton (ⓘ → outil de jeton d'accès → **Prolonger**). Cette étape
   est celle qui compte : le jeton de Page tiré d'un jeton utilisateur PROLONGÉ
   n'expire jamais, alors que celui tiré du jeton brut meurt en une heure - et
   la page s'arrêterait sans prévenir.
6. Avec le jeton prolongé : `GET /me/accounts?fields=id,name,access_token`.
   C'est une **arête**, pas un champ : `/me` n'a pas de champ `access_token`.

```
FASO_FACEBOOK_PAGE_ID=1234567890
FASO_FACEBOOK_PAGE_TOKEN=EAAG...
```

Contrôle du jeton avant de s'en remettre à lui :

```bash
curl -s -G https://graph.facebook.com/v21.0/debug_token \
  --data-urlencode "input_token=$JETON_DE_PAGE" \
  --data-urlencode "access_token=$JETON_UTILISATEUR"
```

`"expires_at": 0` signifie « n'expire jamais ». Toute autre valeur veut dire que
l'étape 5 a été sautée.

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

### Une ligne éditoriale par réseau

Chaque réseau peut surcharger les réglages généraux ; laissé vide, il en hérite.

| Variable | Effet |
|---|---|
| `FASO_<RESEAU>_GENRES` | ce que ce réseau publie |
| `FASO_<RESEAU>_TYPES_ACTUALITE` | ses sources du genre `actualite` |
| `FASO_<RESEAU>_QUOTA_JOUR` | son plafond glissant sur 24 h |
| `FASO_<RESEAU>_MAX_PAR_PASSE` | son plafond par passage horaire |

Réglage en production : le **canal Telegram** s'en tient aux annonces
officielles, la **Page Facebook** reprend tout le fil du site, médias compris.

Deux points comptent quand un fil produit plus que le quota - le fil de presse
sort une centaine de dépêches par jour :

- **le plafond par passage.** Le worker passe une fois par heure ; sans lui, la
  première passe consomme tout le quota d'un coup, et la page enchaîne une
  rafale puis vingt-trois heures de silence ;
- **ce sont les plus RÉCENTS qui sortent.** Publier les plus anciens ferait
  paraître éternellement l'actualité de l'avant-veille : le retard ne se
  résorbe jamais, il s'installe. Les retenus sortent tout de même dans l'ordre
  chronologique, pour qu'une page se lise comme un fil.

Meta ne publie aucun plafond quotidien, mais applique des régulations
anti-spam qui se déclenchent sur le comportement, et le seuil couramment
constaté tourne autour de 25 publications par jour. Une Page neuve, sans
historique d'engagement, est le profil le plus exposé : le quota Facebook est
donc à 25/jour, à monter progressivement plutôt que d'emblée.

## 7. Ce qui n'est pas couvert

- **WhatsApp** n'a pas d'API de publication pour les canaux. Le partage y reste
  manuel.
- **LinkedIn** demande l'accès à la Community Management API, soumis à
  validation Microsoft ; le client n'est pas écrit.
- Les **images** générées par post (vignette avec le titre) ne sont pas
  produites : les posts sont du texte plus un lien.
