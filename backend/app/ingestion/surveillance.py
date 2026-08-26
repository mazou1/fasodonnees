"""Surveillance des collectes : sources « muettes » et sources « taries ».

Deux pannes distinctes, qu'il faut savoir séparer :

- **muette** : le collecteur ne passe plus (worker arrêté, site injoignable,
  sélecteur cassé). Se voit à la date du dernier run réussi.
- **tarie** : le collecteur passe, réussit, et ne rapporte plus rien de neuf.
  Le site répond 200, la collecte est « verte », et pourtant le contenu le plus
  frais a des semaines. C'est le cas resté invisible en août 2026 : le dernier
  compte rendu du Conseil des ministres datait du 30 juillet alors que tous les
  voyants étaient au vert, parce que seule la date des RUNS était surveillée.

Sans infrastructure d'envoi d'e-mails, l'alerte se matérialise par un WARNING
dans les logs du worker ET par l'état exposé sur `GET /sources/etat`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, Run, Source

logger = logging.getLogger(__name__)

# délai maximal sans run réussi avant de considérer la source muette, par cadence
SEUILS = {
    "30min": timedelta(hours=3),
    "quotidien": timedelta(days=2),
    "hebdo": timedelta(days=10),
}
SEUIL_DEFAUT = timedelta(days=2)

# Délai maximal sans contenu NOUVEAU. Calé sur les écarts réellement observés
# dans le corpus, pas au jugé : entre deux comptes rendus du Conseil des
# ministres, l'écart médian est de 8 jours, le 90e centile de 28, et les mois
# d'août 2024 comme 2025 ont connu un creux de 29 jours. Un seuil hebdomadaire
# à 30 jours crierait donc au loup chaque été - à 45, il ne se déclenche que
# sur un silence sans précédent récent.
#
# Une alerte qui se déclenche tous les ans pour rien est une alerte qu'on
# n'ouvre plus : mieux vaut la rater d'une semaine que la rendre inutile.
SEUILS_NOUVEAUTE = {
    "30min": timedelta(days=2),
    "quotidien": timedelta(days=14),
    "hebdo": timedelta(days=45),
}
SEUIL_NOUVEAUTE_DEFAUT = timedelta(days=14)


def etat_sources(db: Session) -> list[dict]:
    """État de fraîcheur de chaque source collectée, la plus en retard d'abord.

    Les sources déclarées mais sans collecteur (placeholders du cadrage) sont
    exclues : elles seraient toujours « muettes » sans que ce soit une anomalie.
    """
    from app.ingestion.registry import COLLECTORS

    dernier = (
        select(Run.source_id, func.max(Run.fin).label("dernier"))
        .where(Run.statut == "ok")
        .group_by(Run.source_id)
        .subquery()
    )
    # La fraîcheur du CONTENU se juge sur `date_publication`, pas sur
    # `date_collecte` : quand le gouvernement réécrit une vieille page, la
    # collecte crée un document daté d'aujourd'hui alors que rien de neuf n'a
    # été publié. C'est exactement ce qui masquait le silence d'août 2026.
    publication = (
        select(
            Document.source_id,
            func.max(Document.date_publication).label("derniere"),
        )
        .group_by(Document.source_id)
        .subquery()
    )
    lignes = db.execute(
        select(Source, dernier.c.dernier, publication.c.derniere)
        .outerjoin(dernier, dernier.c.source_id == Source.id)
        .outerjoin(publication, publication.c.source_id == Source.id)
        .where(Source.actif.is_(True), Source.slug.in_(list(COLLECTORS)))
    ).all()

    maintenant = datetime.now(timezone.utc)
    aujourdhui = maintenant.date()
    etats = []
    for source, dernier_ok, derniere_publication in lignes:
        dernier_ok = _en_utc(dernier_ok)
        seuil = SEUILS.get(source.cadence, SEUIL_DEFAUT)
        muette = dernier_ok is None or (maintenant - dernier_ok) > seuil
        seuil_neuf = SEUILS_NOUVEAUTE.get(source.cadence, SEUIL_NOUVEAUTE_DEFAUT)
        # Une source muette n'est pas dite tarie en plus : le collecteur ne
        # passe pas, on ne sait donc RIEN de ce que la source publie. Deux
        # alertes pour une panne feraient chercher deux causes.
        anciennete = _anciennete(derniere_publication, aujourdhui)
        tarie = not muette and (anciennete is None or anciennete > seuil_neuf)
        etats.append(
            {
                "slug": source.slug,
                "nom": source.nom,
                "cadence": source.cadence,
                "dernier_run_ok": dernier_ok.isoformat() if dernier_ok else None,
                "muette": muette,
                "derniere_publication": (
                    derniere_publication.isoformat() if derniere_publication else None
                ),
                "tarie": tarie,
            }
        )
    etats.sort(
        key=lambda e: (not (e["muette"] or e["tarie"]), e["dernier_run_ok"] or "")
    )
    return etats


def _en_utc(moment: datetime | None) -> datetime | None:
    """PostgreSQL rend un horodatage conscient du fuseau, SQLite (les tests) le
    rend naïf. Les comparer sans les ramener au même monde lève une TypeError."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def _anciennete(derniere_publication, aujourdhui: date) -> timedelta | None:
    """Âge du contenu le plus frais rapporté par une source.

    `None` quand la source n'a jamais rien rapporté, ou ne date pas ce qu'elle
    rapporte : dans les deux cas on ne peut pas juger de sa fraîcheur, et le
    silence est le cas le plus probable.
    """
    if derniere_publication is None:
        return None
    if isinstance(derniere_publication, datetime):
        derniere_publication = derniere_publication.date()
    return aujourdhui - derniere_publication


def verifier_sources_muettes(db: Session | None = None) -> list[dict]:
    """Journalise un WARNING par source muette OU tarie, et renvoie les deux.

    Le nom reste celui de l'appelant historique (le scheduler) ; ce qu'il
    couvre s'est élargi aux sources qui répondent sans plus rien publier.
    """
    if db is None:
        from app.db import SessionLocal

        with SessionLocal() as db:
            return verifier_sources_muettes(db)

    etats = etat_sources(db)
    muettes = [e for e in etats if e["muette"]]
    taries = [e for e in etats if e["tarie"]]
    for e in muettes:
        logger.warning(
            "SOURCE MUETTE : %s (%s) - dernier run réussi : %s",
            e["slug"],
            e["cadence"],
            e["dernier_run_ok"] or "jamais",
        )
    for e in taries:
        logger.warning(
            "SOURCE TARIE : %s (%s) - collecte OK, mais rien de publié depuis %s. "
            "Vérifier que la source publie toujours, et au même endroit.",
            e["slug"],
            e["cadence"],
            e["derniere_publication"] or "toujours",
        )
    if not muettes and not taries:
        logger.info("Surveillance des sources : toutes à jour.")
    return muettes + taries


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    alertes = verifier_sources_muettes()
    muettes = sum(1 for e in alertes if e["muette"])
    print(f"{muettes} source(s) muette(s), {len(alertes) - muettes} tarie(s).")
    return 1 if alertes else 0


if __name__ == "__main__":
    raise SystemExit(main())
