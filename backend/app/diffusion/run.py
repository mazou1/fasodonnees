"""Orchestration de la diffusion : quota, envoi, journal.

Lancé toutes les heures par le worker (cf. app/ingestion/scheduler.py), et à la
main pour la mise en route :

    python -m app.diffusion.run --verifier     # les jetons sont-ils bons ?
    python -m app.diffusion.run --simulation   # que serait-il publié ?
    python -m app.diffusion.run --amorcer      # repartir de zéro sans rien envoyer
    python -m app.diffusion.run                # publier pour de bon
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.diffusion.messages import Item, composer
from app.diffusion.reseaux import (
    CLASSES,
    ErreurReseau,
    Reseau,
    reseaux_configures,
    reseaux_incomplets,
)
from app.diffusion.selection import items_a_publier
from app.models import Publication

logger = logging.getLogger(__name__)


def _liste(valeur: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in valeur.split(",") if v.strip())


def genres_actifs(reseau: str | None = None) -> tuple[str, ...]:
    """Genres publiés, surchargeables par réseau (`FASO_FACEBOOK_GENRES`…)."""
    propre = getattr(settings, f"{reseau}_genres", "") if reseau else ""
    return _liste(propre) or _liste(settings.diffusion_genres)


def types_actifs(reseau: str | None = None) -> tuple[str, ...]:
    """Sources du genre « actualite », surchargeables par réseau.

    C'est ce qui permet à chaque compte d'avoir sa ligne : le canal Telegram
    s'en tient aux annonces officielles, la Page Facebook reprend tout le fil
    du site.
    """
    propre = getattr(settings, f"{reseau}_types_actualite", "") if reseau else ""
    return _liste(propre) or _liste(settings.diffusion_types_actualite)


def limite_de_passe(reseau: str, quota: int) -> int:
    """Ce qu'on s'autorise à publier en UNE fois.

    Le worker passe une fois par heure. Sur un fil qui produit plus que le
    quota, sans ce plafond la première passe le consomme d'un coup : une rafale
    de dizaines de posts, puis vingt-trois heures de silence. Une page se lit
    comme un fil, pas comme une salve.
    """
    plafond = getattr(settings, f"{reseau}_max_par_passe", 0) or 0
    return min(quota, plafond) if plafond > 0 else quota


def quota_restant(db: Session, reseau: str, quota_jour: int, maintenant=None) -> int:
    """Quota glissant sur 24 h plutôt que remis à zéro à minuit.

    Le palier gratuit de X compte 500 posts par MOIS : un plafond glissant
    garantit le respect du plafond mensuel quelle que soit l'heure des
    redémarrages, là où un compteur calendaire autorise deux fois le quota
    autour de minuit.
    """
    depuis = (maintenant or datetime.now(timezone.utc)) - timedelta(hours=24)
    deja = db.scalar(
        select(func.count())
        .select_from(Publication)
        .where(
            Publication.reseau == reseau,
            Publication.statut == "publie",
            Publication.date_envoi >= depuis,
        )
    )
    return max(quota_jour - (deja or 0), 0)


def journaliser(
    db: Session,
    reseau: str,
    item: Item,
    message: str,
    *,
    post_id: str | None = None,
    erreur: str | None = None,
    statut: str | None = None,
) -> Publication:
    """Une ligne par (réseau, item), créée ou mise à jour.

    Le texte réellement envoyé est conservé : quand un post pose question, il
    faut pouvoir dire ce que la plateforme a publié sans dépendre de ce que le
    réseau veut bien encore afficher.
    """
    publication = db.scalar(
        select(Publication).where(Publication.reseau == reseau, Publication.cle == item.cle)
    )
    if publication is None:
        publication = Publication(reseau=reseau, cle=item.cle, tentatives=0)
        db.add(publication)
    publication.genre = item.genre
    publication.message = message
    publication.lien = item.lien
    # l'amorçage n'est pas un essai d'envoi : le compter fausserait la lecture
    # du journal dans l'admin, où « tentatives » sert à repérer ce qui coince
    if statut != "amorce":
        publication.tentatives = (publication.tentatives or 0) + 1
    publication.post_id = post_id
    publication.erreur = erreur[:2000] if erreur else None
    publication.statut = statut or ("echec" if erreur else "publie")
    publication.date_envoi = datetime.now(timezone.utc)
    db.commit()
    return publication


def diffuser_reseau(db: Session, reseau: Reseau, *, simulation: bool = False) -> dict:
    quota = quota_restant(db, reseau.nom, reseau.quota_jour)
    items = items_a_publier(
        db,
        reseau.nom,
        limite=limite_de_passe(reseau.nom, quota),
        fraicheur_jours=settings.diffusion_fraicheur_jours,
        site_url=settings.site_url,
        genres=genres_actifs(reseau.nom),
        types=types_actifs(reseau.nom),
    )
    bilan = {"quota": quota, "candidats": len(items), "publies": 0, "echecs": 0}
    for rang, item in enumerate(items):
        message = composer(item, reseau.nom)
        if simulation:
            logger.info("[simulation %s] %s\n%s\n", reseau.nom, item.cle, message)
            bilan["publies"] += 1
            continue
        try:
            post_id = reseau.publier(message, item.lien)
        except ErreurReseau as exc:
            journaliser(db, reseau.nom, item, message, erreur=str(exc))
            bilan["echecs"] += 1
            # On arrête CE réseau au premier refus : un jeton expiré ou un quota
            # atteint refusera aussi les suivants, et insister ne ferait
            # qu'épuiser des tentatives sur toute la file.
            logger.warning("%s : publication interrompue (%s)", reseau.nom, exc)
            break
        journaliser(db, reseau.nom, item, message, post_id=post_id)
        bilan["publies"] += 1
        logger.info("%s : %s publié (%s)", reseau.nom, item.cle, post_id)
        if rang + 1 < len(items) and settings.diffusion_pause_s > 0:
            time.sleep(settings.diffusion_pause_s)
    return bilan


def diffuser(db: Session, *, noms=None, simulation: bool = False) -> dict[str, dict]:
    """Publie sur tous les réseaux configurés. Rien ne part tant que
    `FASO_DIFFUSION_ACTIVE` n'est pas vrai : une base restaurée ou un worker
    lancé par erreur sur un poste de développement ne doit pas poster sur une
    page publique, même avec des jetons valides."""
    if not settings.diffusion_active and not simulation:
        logger.info("Diffusion désactivée (FASO_DIFFUSION_ACTIVE) - rien n'est publié")
        return {}
    reseaux = reseaux_configures(noms)
    if simulation and not reseaux:
        # La simulation n'envoie rien : pouvoir répondre « voilà ce qui
        # partirait » AVANT d'avoir créé le moindre compte est justement ce qui
        # rend la mise en route relisible.
        reseaux = [classe() for nom, classe in CLASSES.items() if not noms or nom in noms]
    bilans = {}
    for reseau in reseaux:
        bilans[reseau.nom] = diffuser_reseau(db, reseau, simulation=simulation)
    if not bilans:
        logger.info("Aucun réseau configuré - rien à publier")
    return bilans


def amorcer(db: Session, *, noms=None) -> dict[str, int]:
    """Marque comme VUS, sans rien envoyer, les items déjà publiables.

    À lancer une fois avant d'ouvrir un canal. Sans cela, la première passe
    déverse d'un coup tout ce que la fenêtre de fraîcheur laisse passer : des
    dizaines de messages en quelques secondes sur un canal qui n'a pas encore
    d'abonnés, et qui ressemblera pour toujours à une décharge dans son
    historique. Ce qui sortira ensuite, ce sera ce qui paraît après.
    """
    bilans = {}
    for reseau in reseaux_configures(noms):
        items = items_a_publier(
            db,
            reseau.nom,
            # large : on marque tout ce qui pourrait sortir, pas seulement ce
            # qui sortirait à la prochaine passe
            limite=10_000,
            fraicheur_jours=settings.diffusion_fraicheur_jours,
            site_url=settings.site_url,
            genres=genres_actifs(reseau.nom),
            types=types_actifs(reseau.nom),
        )
        for item in items:
            journaliser(db, reseau.nom, item, composer(item, reseau.nom), statut="amorce")
        bilans[reseau.nom] = len(items)
        logger.info("%s : %d item(s) marqué(s) comme vus, aucun envoi", reseau.nom, len(items))
    return bilans


def verifier(noms=None) -> dict[str, str]:
    resultats = {}
    for reseau in reseaux_configures(noms):
        try:
            resultats[reseau.nom] = reseau.verifier()
        except ErreurReseau as exc:
            resultats[reseau.nom] = f"ÉCHEC : {exc}"
    return resultats


def main() -> None:
    analyseur = argparse.ArgumentParser(description="Diffusion sur les réseaux sociaux")
    analyseur.add_argument(
        "--simulation",
        action="store_true",
        help="afficher les posts sans rien envoyer (ignore le coupe-circuit)",
    )
    analyseur.add_argument(
        "--verifier", action="store_true", help="contrôler les jetons, sans rien publier"
    )
    analyseur.add_argument(
        "--amorcer",
        action="store_true",
        help="marquer comme vus les items déjà publiables, sans rien envoyer "
        "(à lancer une fois avant d'ouvrir un canal)",
    )
    analyseur.add_argument(
        "--reseau", action="append", help="limiter à un réseau (telegram, facebook, x)"
    )
    options = analyseur.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    noms = tuple(options.reseau) if options.reseau else None

    if options.verifier:
        resultats = verifier(noms)
        for nom, etat in resultats.items():
            print(f"{nom:10s} {etat}")
        # Pendant la mise en route, l'information utile est justement celle qui
        # manque. Ne rien afficher laisserait croire à une panne du contrôle.
        for reseau in reseaux_incomplets(noms):
            print(f"{reseau.nom:10s} incomplet - il manque : {', '.join(reseau.manquants())}")
        if not resultats and not reseaux_incomplets(noms):
            print("Aucun réseau configuré - cf. docs/reseaux-sociaux.md")
        return

    if options.amorcer:
        with SessionLocal() as db:
            for nom, nombre in amorcer(db, noms=noms).items():
                print(f"{nom:10s} {nombre} item(s) marqué(s) comme vus, aucun envoi")
        return

    with SessionLocal() as db:
        bilans = diffuser(db, noms=noms, simulation=options.simulation)
    for nom, bilan in bilans.items():
        print(
            f"{nom:10s} quota restant {bilan['quota']:3d} · "
            f"{bilan['publies']} publié(s) · {bilan['echecs']} échec(s)"
        )


if __name__ == "__main__":
    main()
