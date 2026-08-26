"""Clients Telegram, Facebook et X.

Chaque client fait une chose : envoyer un texte déjà composé et rendre
l'identifiant du post. Aucun ne décide de ce qui est publié ni ne consulte la
base - c'est ce qui permet de les remplacer un par un quand une API change, et
de tester le reste du module sans jeton.

La signature OAuth 1.0a de X est écrite ici plutôt qu'apportée par une
bibliothèque : c'est une soixantaine de lignes de HMAC-SHA1 sur des primitives
de la bibliothèque standard, là où le client officiel tirerait un arbre de
dépendances entier pour un seul appel POST.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from urllib.parse import quote

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DELAI = httpx.Timeout(20.0)


class ErreurReseau(RuntimeError):
    """Publication refusée : jeton expiré, quota atteint, contenu rejeté."""


def _client(client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(timeout=DELAI, headers={"User-Agent": settings.user_agent})


def _json(reponse: httpx.Response) -> dict:
    try:
        donnees = reponse.json()
    except ValueError:
        donnees = {}
    if reponse.status_code >= 400:
        # Le corps porte le diagnostic utile (jeton expiré, permission
        # manquante) ; il est tronqué avant d'entrer dans le journal, mais
        # jamais remplacé par un message générique.
        raise ErreurReseau(f"HTTP {reponse.status_code} : {reponse.text[:400]}")
    return donnees if isinstance(donnees, dict) else {}


# ── OAuth 1.0a (X) ────────────────────────────────────────────────────────

def _encoder(valeur: str) -> str:
    """Encodage pourcent RFC 3986. `quote` laisse déjà `-._~` intacts ; il faut
    lui retirer `/` de ses caractères sûrs, que la spécification OAuth encode."""
    return quote(str(valeur), safe="")


def chaine_de_signature(methode: str, url: str, parametres: dict[str, str]) -> str:
    """Chaîne de base signée. Le corps JSON n'y entre pas : OAuth 1.0a n'y
    intègre que les paramètres de requête et les champs oauth_*."""
    normalises = "&".join(
        f"{_encoder(cle)}={_encoder(valeur)}" for cle, valeur in sorted(parametres.items())
    )
    return f"{methode.upper()}&{_encoder(url)}&{_encoder(normalises)}"


def entete_oauth1(
    methode: str,
    url: str,
    *,
    cle_api: str,
    secret_api: str,
    jeton: str,
    secret_jeton: str,
    nonce: str | None = None,
    horodatage: int | None = None,
) -> str:
    parametres = {
        "oauth_consumer_key": cle_api,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(horodatage if horodatage is not None else int(time.time())),
        "oauth_token": jeton,
        "oauth_version": "1.0",
    }
    cle_signature = f"{_encoder(secret_api)}&{_encoder(secret_jeton)}".encode()
    empreinte = hmac.new(
        cle_signature, chaine_de_signature(methode, url, parametres).encode(), hashlib.sha1
    ).digest()
    parametres["oauth_signature"] = base64.b64encode(empreinte).decode()
    champs = ", ".join(
        f'{_encoder(cle)}="{_encoder(valeur)}"' for cle, valeur in sorted(parametres.items())
    )
    return f"OAuth {champs}"


# ── Réseaux ───────────────────────────────────────────────────────────────

class Reseau:
    nom: str
    quota_jour: int = 0
    # (variable d'environnement, attribut) : sert à la fois à décider si le
    # réseau est utilisable et à DIRE ce qui manque. Un réseau à moitié
    # configuré est le cas normal pendant la mise en route ; se contenter de
    # l'ignorer en silence laisse chercher la panne du mauvais côté.
    VARIABLES: tuple[tuple[str, str], ...] = ()

    def manquants(self) -> list[str]:
        return [env for env, attribut in self.VARIABLES if not getattr(self, attribut, "")]

    def est_configure(self) -> bool:
        return bool(self.VARIABLES) and not self.manquants()

    def publier(self, message: str, lien: str) -> str:
        """Rend l'identifiant du post, ou lève `ErreurReseau`."""
        raise NotImplementedError

    def verifier(self) -> str:
        """Identité du compte, pour contrôler les jetons sans rien publier."""
        raise NotImplementedError


class Telegram(Reseau):
    nom = "telegram"
    API = "https://api.telegram.org"
    VARIABLES = (
        ("FASO_TELEGRAM_BOT_TOKEN", "token"),
        ("FASO_TELEGRAM_CHAT_ID", "chat_id"),
    )

    def __init__(self, token: str | None = None, chat_id: str | None = None, client=None):
        self.token = settings.telegram_bot_token if token is None else token
        self.chat_id = settings.telegram_chat_id if chat_id is None else chat_id
        self.quota_jour = settings.telegram_quota_jour
        self._client = _client(client)

    def _appel(self, methode: str, **corps) -> dict:
        reponse = self._client.post(f"{self.API}/bot{self.token}/{methode}", json=corps)
        donnees = _json(reponse)
        if not donnees.get("ok"):
            raise ErreurReseau(f"Telegram : {donnees.get('description') or reponse.text[:300]}")
        return donnees.get("result") or {}

    def publier(self, message: str, lien: str) -> str:
        # Le lien est déjà en fin de message : Telegram en tire l'aperçu, il
        # n'y a pas de champ séparé à renseigner.
        return str(self._appel("sendMessage", chat_id=self.chat_id, text=message)["message_id"])

    def verifier(self) -> str:
        bot = self._appel("getMe")
        return f"bot @{bot.get('username')} vers {self.chat_id}"


class Facebook(Reseau):
    nom = "facebook"
    API = "https://graph.facebook.com/v21.0"
    VARIABLES = (
        ("FASO_FACEBOOK_PAGE_ID", "page_id"),
        ("FASO_FACEBOOK_PAGE_TOKEN", "token"),
    )

    def __init__(self, page_id: str | None = None, token: str | None = None, client=None):
        self.page_id = settings.facebook_page_id if page_id is None else page_id
        self.token = settings.facebook_page_token if token is None else token
        self.quota_jour = settings.facebook_quota_jour
        self._client = _client(client)

    def publier(self, message: str, lien: str) -> str:
        # Facebook construit l'aperçu (titre, image, domaine) à partir du champ
        # `link`, pas d'une URL trouvée dans le texte. Le lien est donc retiré
        # du corps : l'y laisser afficherait l'URL brute EN PLUS de la carte.
        corps = message.replace(lien, "").rstrip()
        donnees = _json(
            self._client.post(
                f"{self.API}/{self.page_id}/feed",
                data={"message": corps, "link": lien, "access_token": self.token},
            )
        )
        identifiant = donnees.get("id")
        if not identifiant:
            raise ErreurReseau(f"Facebook : réponse sans identifiant de post ({donnees})")
        return str(identifiant)

    def verifier(self) -> str:
        page = _json(
            self._client.get(
                f"{self.API}/{self.page_id}", params={"fields": "name", "access_token": self.token}
            )
        )
        return f"page « {page.get('name')} » ({self.page_id})"


class X(Reseau):
    nom = "x"
    API_POST = "https://api.x.com/2/tweets"
    API_MOI = "https://api.x.com/2/users/me"
    VARIABLES = (
        ("FASO_X_API_KEY", "cle_api"),
        ("FASO_X_API_SECRET", "secret_api"),
        ("FASO_X_ACCESS_TOKEN", "jeton"),
        ("FASO_X_ACCESS_SECRET", "secret_jeton"),
    )

    def __init__(
        self,
        cle_api: str | None = None,
        secret_api: str | None = None,
        jeton: str | None = None,
        secret_jeton: str | None = None,
        client=None,
    ):
        self.cle_api = settings.x_api_key if cle_api is None else cle_api
        self.secret_api = settings.x_api_secret if secret_api is None else secret_api
        self.jeton = settings.x_access_token if jeton is None else jeton
        self.secret_jeton = settings.x_access_secret if secret_jeton is None else secret_jeton
        self.quota_jour = settings.x_quota_jour
        self._client = _client(client)

    def _entete(self, methode: str, url: str) -> str:
        return entete_oauth1(
            methode,
            url,
            cle_api=self.cle_api,
            secret_api=self.secret_api,
            jeton=self.jeton,
            secret_jeton=self.secret_jeton,
        )

    def publier(self, message: str, lien: str) -> str:
        donnees = _json(
            self._client.post(
                self.API_POST,
                json={"text": message},
                headers={"Authorization": self._entete("POST", self.API_POST)},
            )
        )
        identifiant = (donnees.get("data") or {}).get("id")
        if not identifiant:
            raise ErreurReseau(f"X : réponse sans identifiant de post ({donnees})")
        return str(identifiant)

    def verifier(self) -> str:
        donnees = _json(
            self._client.get(
                self.API_MOI, headers={"Authorization": self._entete("GET", self.API_MOI)}
            )
        )
        compte = donnees.get("data") or {}
        return f"compte @{compte.get('username')}"


CLASSES = {"telegram": Telegram, "facebook": Facebook, "x": X}


def reseaux_incomplets(noms: tuple[str, ...] | None = None) -> list[Reseau]:
    """Réseaux dont il manque au moins un secret - mais pas tous.

    Un réseau dont RIEN n'est renseigné n'est pas en panne : il n'est
    simplement pas encore ouvert, et l'annoncer noierait le vrai manque.
    """
    partiels = []
    for nom, classe in CLASSES.items():
        if noms and nom not in noms:
            continue
        reseau = classe()
        manque = reseau.manquants()
        if manque and len(manque) < len(reseau.VARIABLES):
            partiels.append(reseau)
    return partiels


def reseaux_configures(noms: tuple[str, ...] | None = None) -> list[Reseau]:
    """Les réseaux dont les jetons sont renseignés. Un réseau non configuré est
    simplement absent : ajouter Facebook plus tard ne demande rien d'autre que
    de remplir deux variables d'environnement."""
    actifs = []
    for nom, classe in CLASSES.items():
        if noms and nom not in noms:
            continue
        reseau = classe()
        if reseau.est_configure():
            actifs.append(reseau)
        else:
            logger.debug("Réseau %s non configuré - ignoré", nom)
    return actifs
