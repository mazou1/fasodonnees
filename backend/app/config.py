from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FASO_", extra="ignore")

    database_url: str = "postgresql+psycopg://faso:faso@localhost:5434/faso"
    # Archive brute : disque local, ou bucket S3-compatible (cf. app/stockage.py).
    # `data_dir` reste le dossier local - racine du stockage local, et source de
    # la migration vers le bucket.
    data_dir: Path = Path("data")
    stockage: str = "local"  # local | s3
    # S3-compatible : Garage (conteneur du compose) ou n'importe quel S3 externe.
    # Seul l'endpoint change entre les deux.
    s3_endpoint: str = ""  # ex. http://garage:3900 ou https://s3.eu-central-1.example
    s3_bucket: str = "faso-archives"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "garage"
    # Base des URL PUBLIQUES et STABLES du corpus (ex. « /archives », proxifié
    # vers le point d'accès web de Garage par nginx). Renseignée, elle remplace
    # les URL présignées : un lien vers un document officiel doit rester valable
    # des années et pouvoir être miroité, pas expirer au bout d'une heure.
    s3_url_publique: str = ""
    # repli quand aucune URL publique n'est configurée (bucket privé)
    s3_duree_url: int = 3600

    admin_user: str = "admin"
    admin_password: str = "change-me"
    secret_key: str = "change-me-long-random"

    # Identification claire auprès des sites collectés (politesse)
    user_agent: str = "FasoDonnees/0.1 (plateforme civique open source)"

    # Extraction LLM : mistral (tier gratuit) | anthropic - cf. extraction/conseil_ministres.py
    llm_provider: str = "mistral"
    mistral_api_key: str = ""
    anthropic_api_key: str = ""

    # ── Diffusion sur les réseaux sociaux (cf. app/diffusion/) ─────────────
    # Coupe-circuit unique : tant qu'il est à False, aucun appel réseau n'est
    # fait, même avec des jetons valides. Un déploiement, une restauration de
    # base ou un test ne doivent jamais poster par surprise sur une page
    # publique.
    diffusion_active: bool = False
    # Base des liens partagés. Un lien vers localhost publié sur Facebook n'est
    # pas rattrapable : la valeur par défaut est le site public.
    site_url: str = "https://fasodonnees.org"
    # genres publiés : conseil (compte rendu du CM), decision (mesure validée),
    # actualite (article de presse ou communiqué archivé)
    diffusion_genres: str = "conseil,decision,actualite"
    # Types de documents repris dans le genre « actualite ». Par défaut les
    # SOURCES OFFICIELLES seules : actualités du gouvernement et communiqués.
    # Ajouter « article_presse » y verse le fil des cinq médias collectés, soit
    # une centaine de dépêches par jour - un fil de presse généraliste, pas le
    # relais d'information publique que la plateforme annonce.
    diffusion_types_actualite: str = "actualite_gouv,communique"
    # Un item plus vieux que cette fenêtre n'est jamais publié. C'est ce qui
    # évite qu'une activation, une panne réparée ou un arriéré ne déverse des
    # mois d'archives d'un coup sur les pages, et ce qui empêche un flux
    # d'actualités plus rapide que le quota de créer un retard permanent.
    diffusion_fraicheur_jours: int = 2
    # pause entre deux posts d'un même réseau (politesse et lissage)
    diffusion_pause_s: float = 2.0

    # ── Réglages PAR RÉSEAU ────────────────────────────────────────────────
    # Vides, ils héritent des réglages généraux ci-dessus. Renseignés, ils
    # permettent à chaque compte d'avoir sa ligne éditoriale : le canal
    # Telegram s'en tient aux annonces officielles, la Page Facebook reprend
    # tout le fil du site.
    telegram_genres: str = ""
    telegram_types_actualite: str = ""
    facebook_genres: str = ""
    facebook_types_actualite: str = ""
    x_genres: str = ""
    x_types_actualite: str = ""

    # Nombre maximal de posts par PASSAGE (le worker en fait un par heure).
    # 0 = pas d'autre limite que le quota du jour. Sur un fil qui produit plus
    # que le quota, sans ce plafond la première passe le consomme d'un coup :
    # une rafale de dizaines de posts, puis vingt-trois heures de silence.
    telegram_max_par_passe: int = 0
    facebook_max_par_passe: int = 0
    x_max_par_passe: int = 0
    # Vignette des cartes de partage (Open Graph). Vide : les réseaux affichent
    # une carte texte, correcte mais discrète. Renseignée avec une URL absolue
    # vers une image 1200x630, ils affichent une grande carte illustrée.
    og_image_url: str = ""

    # Telegram : un bot (@BotFather), administrateur du canal.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""  # « @faso_donnees » ou l'identifiant numérique
    telegram_quota_jour: int = 40

    # Facebook : page + jeton de page longue durée (Graph API).
    facebook_page_id: str = ""
    facebook_page_token: str = ""
    facebook_quota_jour: int = 15

    # X : authentification OAuth 1.0a en contexte utilisateur (4 secrets).
    # Le palier gratuit plafonne à 500 posts/mois en écriture : 12/jour laisse
    # ~370/mois, sous le plafond même un mois chargé.
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_secret: str = ""
    x_quota_jour: int = 12


settings = Settings()
