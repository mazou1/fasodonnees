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
    s3_duree_url: int = 3600  # validité des URL présignées servies au public

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
