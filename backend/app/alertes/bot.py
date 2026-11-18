"""La conversation avec le bot : s'abonner, lister, se désabonner.

`repondre` est une fonction pure de la base et du message reçu : c'est elle que
les tests exercent. `ecouter` n'est que la boucle qui la branche sur Telegram.

Le bot est celui qui publie déjà sur le canal (@faso_donnees_bot). Il ne répond
qu'en conversation privée : dans un groupe ou sur le canal, un abonnement
n'aurait pas de destinataire clair.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
import time
import unicodedata

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Abonnement, Personne, Structure

logger = logging.getLogger(__name__)

CANAL = "telegram"
MAX_ABONNEMENTS = 20
MOT_MIN, MOT_MAX = 3, 60

AIDE = (
    "Je vous préviens quand une nomination, une décision du Conseil des ministres, "
    "un texte de loi ou un vote de l'Assemblée correspond à ce que vous suivez.\n\n"
    "/suivre budget - suivre un mot-clé ou un nom (ex : /suivre Ouédraogo)\n"
    "/liste - voir ce que vous suivez\n"
    "/arreter 2 - arrêter l'alerte n°2 de la liste\n"
    "/arreter tout - tout arrêter et effacer vos données\n\n"
    "Pour suivre une personne ou une institution précise, ouvrez sa fiche sur "
    f"{settings.site_url} et touchez « Recevoir une alerte ».\n\n"
    "Je ne conserve que l'identifiant de cette conversation et vos alertes."
)


def normaliser(texte: str | None) -> str:
    """Minuscules sans accents ni ponctuation : « Ouédraogo » = « OUEDRAOGO »."""
    sans_accents = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).strip()


def charge_utile(mot: str) -> str:
    """Mot-clé encodé pour un lien `t.me/<bot>?start=…` (64 caractères sûrs au plus)."""
    return "m" + base64.urlsafe_b64encode(mot.encode()).decode().rstrip("=")


def _decoder(charge: str) -> str | None:
    try:
        brut = charge + "=" * (-len(charge) % 4)
        return base64.urlsafe_b64decode(brut.encode()).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def _abonnements(db: Session, chat_id: str) -> list[Abonnement]:
    return list(
        db.scalars(
            select(Abonnement)
            .where(Abonnement.canal == CANAL, Abonnement.destinataire == chat_id)
            .order_by(Abonnement.id)
        )
    )


def _abonner(db: Session, chat_id: str, genre: str, valeur: str, libelle: str) -> str:
    existants = _abonnements(db, chat_id)
    if any(a.genre == genre and a.valeur == valeur for a in existants):
        return f"Vous suivez déjà « {libelle} ». /liste pour tout voir."
    if len(existants) >= MAX_ABONNEMENTS:
        return (
            f"Vous suivez déjà {MAX_ABONNEMENTS} alertes, le maximum. "
            "Arrêtez-en une avec /arreter avant d'en ajouter."
        )
    db.add(
        Abonnement(canal=CANAL, destinataire=chat_id, genre=genre, valeur=valeur, libelle=libelle)
    )
    db.commit()
    return (
        f"C'est noté : vous suivez « {libelle} ».\n"
        "Vous recevrez un message dès qu'une publication validée y correspond. "
        "/liste pour voir vos alertes, /arreter pour en retirer une."
    )


def _suivre_mot(db: Session, chat_id: str, mot: str) -> str:
    mot = " ".join(mot.split())
    cle = normaliser(mot)
    if len(cle) < MOT_MIN:
        return (
            f"Indiquez un mot d'au moins {MOT_MIN} lettres après la commande, "
            "par exemple : /suivre budget"
        )
    if len(mot) > MOT_MAX:
        return f"Ce mot-clé est trop long ({MOT_MAX} caractères au plus)."
    return _abonner(db, chat_id, "mot", cle, mot)


def _suivre_personne(db: Session, chat_id: str, identifiant: int) -> str:
    personne = db.get(Personne, identifiant)
    if personne is None:
        return "Cette fiche n'existe plus sur la plateforme."
    return _abonner(db, chat_id, "personne", str(personne.id), personne.nom_complet)


def _suivre_structure(db: Session, chat_id: str, identifiant: int) -> str:
    structure = db.get(Structure, identifiant)
    if structure is None:
        return "Cette institution n'existe plus sur la plateforme."
    # les renommages pointent vers une structure canonique : c'est elle qu'on suit
    canonique = structure.canonique or structure
    libelle = f"Nominations - {canonique.sigle or canonique.nom}"
    return _abonner(db, chat_id, "structure", str(canonique.id), libelle[:300])


def _demarrer(db: Session, chat_id: str, charge: str) -> str:
    """`/start` suivi de la charge d'un lien du site : p<id>, s<id> ou m<mot encodé>."""
    if not charge:
        return "Bienvenue sur les alertes de Faso Données Publiques.\n\n" + AIDE
    genre, reste = charge[0], charge[1:]
    if genre == "p" and reste.isdigit():
        return _suivre_personne(db, chat_id, int(reste))
    if genre == "s" and reste.isdigit():
        return _suivre_structure(db, chat_id, int(reste))
    if genre == "m":
        mot = _decoder(reste)
        if mot:
            return _suivre_mot(db, chat_id, mot)
    return "Je n'ai pas compris ce lien.\n\n" + AIDE


def _lister(db: Session, chat_id: str) -> str:
    abonnements = _abonnements(db, chat_id)
    if not abonnements:
        return "Vous ne suivez rien pour l'instant. Essayez : /suivre budget"
    lignes = [f"{i}. {a.libelle}" for i, a in enumerate(abonnements, start=1)]
    return "Vous suivez :\n" + "\n".join(lignes) + "\n\n/arreter 1 pour retirer la première."


def _arreter(db: Session, chat_id: str, argument: str) -> str:
    abonnements = _abonnements(db, chat_id)
    if not abonnements:
        return "Vous ne suivez rien : il n'y a rien à arrêter."
    argument = argument.strip().lower()
    if argument in ("tout", "tous", "toutes"):
        oublier(db, chat_id)
        return "Toutes vos alertes sont arrêtées et vos données effacées."
    if not argument.isdigit() or not 1 <= int(argument) <= len(abonnements):
        return "Indiquez le numéro de l'alerte à arrêter (voir /liste), ou /arreter tout."
    cible = abonnements[int(argument) - 1]
    libelle = cible.libelle
    db.delete(cible)
    db.commit()
    return f"Alerte « {libelle} » arrêtée."


def oublier(db: Session, chat_id: str) -> None:
    """Efface tout ce que la plateforme sait de cette conversation."""
    db.execute(
        delete(Abonnement).where(Abonnement.canal == CANAL, Abonnement.destinataire == chat_id)
    )
    db.commit()


def repondre(db: Session, chat_id: str, texte: str) -> str:
    """La réponse du bot à un message privé."""
    texte = (texte or "").strip()
    if not texte.startswith("/"):
        apercu = " ".join(texte.split())[:MOT_MAX]
        if len(normaliser(apercu)) >= MOT_MIN:
            return f"Pour suivre « {apercu} », envoyez : /suivre {apercu}\n\n/aide pour le reste."
        return AIDE
    commande, _, argument = texte.partition(" ")
    # « /suivre@faso_donnees_bot » : Telegram ajoute le nom du bot dans certains clients
    commande = commande.split("@", 1)[0].lower()
    if commande == "/start":
        return _demarrer(db, chat_id, argument.strip())
    if commande == "/suivre":
        return _suivre_mot(db, chat_id, argument)
    if commande == "/liste":
        return _lister(db, chat_id)
    if commande in ("/arreter", "/stop"):
        return _arreter(db, chat_id, argument)
    return AIDE


def nombre_abonnes(db: Session) -> int:
    return db.scalar(select(func.count(func.distinct(Abonnement.destinataire)))) or 0


# ── Boucle d'écoute ───────────────────────────────────────────────────────

def traiter_mises_a_jour(db: Session, telegram, mises_a_jour: list[dict]) -> int:
    """Répond aux messages privés ; renvoie l'identifiant de la dernière mise à jour."""
    dernier = 0
    for maj in mises_a_jour:
        dernier = max(dernier, maj.get("update_id", 0))
        message = maj.get("message") or {}
        chat = message.get("chat") or {}
        if chat.get("type") != "private" or not message.get("text"):
            continue
        chat_id = str(chat["id"])
        try:
            reponse = repondre(db, chat_id, message["text"])
            telegram.envoyer(chat_id, reponse)
        except Exception:  # noqa: BLE001 - un message qui échoue ne bloque pas les suivants
            db.rollback()
            logger.exception("Bot d'alertes : échec sur un message")
    return dernier


def ecouter() -> None:
    """Interroge Telegram en continu (attente longue) et répond.

    La confirmation des messages lus est tenue par Telegram lui-même : rappeler
    `getUpdates` avec `offset = dernier + 1` les retire de sa file. Rien à
    mémoriser de notre côté, et un redémarrage ne rejoue que le message en
    cours - les commandes sont sans effet si on les répète.
    """
    from app.diffusion.reseaux import Telegram

    telegram = Telegram(client=httpx.Client(timeout=httpx.Timeout(70.0)))
    # une ligne de journal par attente longue noierait celles des collectes
    logging.getLogger("httpx").addFilter(_SansAttenteLongue())
    decalage = None
    attente = 5
    logger.info("Bot d'alertes à l'écoute (@%s)", settings.telegram_bot_nom)
    while True:
        try:
            parametres = {"timeout": 50, "allowed_updates": ["message"]}
            if decalage is not None:
                parametres["offset"] = decalage
            mises_a_jour = telegram._appel("getUpdates", **parametres)
            if mises_a_jour:
                with SessionLocal() as db:
                    decalage = traiter_mises_a_jour(db, telegram, mises_a_jour) + 1
            attente = 5
        except Exception as exc:  # noqa: BLE001 - la boucle doit survivre à tout
            logger.warning("Bot d'alertes : %s - nouvel essai dans %d s", type(exc).__name__, attente)
            time.sleep(attente)
            attente = min(attente * 2, 300)


class _SansAttenteLongue(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/getUpdates" not in record.getMessage()
