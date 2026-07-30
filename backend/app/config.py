from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FASO_", extra="ignore")

    database_url: str = "postgresql+psycopg://faso:faso@localhost:5434/faso"
    # Archive brute : disque local, ou bucket S3-compatible (cf. app/stockage.py).
    # `data_dir` reste le dossier local — racine du stockage local, et source de
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

    # Extraction LLM : mistral (tier gratuit) | anthropic — cf. extraction/conseil_ministres.py
    llm_provider: str = "mistral"
    mistral_api_key: str = ""
    anthropic_api_key: str = ""


settings = Settings()
