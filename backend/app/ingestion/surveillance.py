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

# Le seuil de silence n'est PAS choisi à la main : chaque source est jugée sur
# son propre rythme, mesuré sur ses publications de l'année écoulée.
#
# La cadence déclarée dit à quelle fréquence on INTERROGE la source, pas à
# quelle fréquence elle PUBLIE. L'ASCE-LC est interrogée toutes les semaines et
# publie quelques rapports par an ; les plénières de l'Assemblée suivent les
# sessions parlementaires. Un seuil unique par cadence les déclarerait taries en
# permanence - et une alerte toujours allumée est une alerte qu'on n'ouvre plus.
FENETRE_RYTHME = timedelta(days=365)

# En deçà, la source n'a pas de rythme mesurable : on ne la juge pas plutôt que
# de la déclarer tarie sur deux points. Cela écarte aussi les collecteurs qui
# n'écrivent pas de documents (Assemblée, Finances : ils alimentent les tables
# de députés et de budget), qu'un test fondé sur les documents ne peut pas voir.
MINIMUM_POINTS = 5

# Marge au-dessus du plus long silence déjà observé. À 1,5, le creux estival du
# Conseil des ministres (28 jours en 2025 comme en 2026) donne un seuil de
# 45 jours : le silence de l'été 2026 ne déclenche rien, un silence d'un mois et
# demi déclenche.
MARGE = 1.5

# Plancher par cadence : une source qui vient d'être branchée n'a pas encore
# d'historique, et un média interrogé toutes les 30 minutes ne doit pas hériter
# d'un seuil de quelques heures sur un rythme mal mesuré.
PLANCHERS_NOUVEAUTE = {
    "30min": timedelta(days=2),
    "quotidien": timedelta(days=14),
    "hebdo": timedelta(days=45),
}
PLANCHER_NOUVEAUTE_DEFAUT = timedelta(days=14)


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
    lignes = db.execute(
        select(Source, dernier.c.dernier)
        .outerjoin(dernier, dernier.c.source_id == Source.id)
        .where(Source.actif.is_(True), Source.slug.in_(list(COLLECTORS)))
    ).all()

    maintenant = datetime.now(timezone.utc)
    aujourdhui = maintenant.date()
    rythmes = _dates_de_publication(db, aujourdhui)

    etats = []
    for source, dernier_ok in lignes:
        dernier_ok = _en_utc(dernier_ok)
        seuil = SEUILS.get(source.cadence, SEUIL_DEFAUT)
        muette = dernier_ok is None or (maintenant - dernier_ok) > seuil

        dates = rythmes.get(source.id, [])
        derniere_publication = dates[-1] if dates else None
        silence = (aujourdhui - derniere_publication).days if derniere_publication else None
        seuil_neuf = _seuil_de_silence(dates, source.cadence)
        # Une source muette n'est pas dite tarie en plus : le collecteur ne
        # passe pas, on ne sait donc RIEN de ce que la source publie. Deux
        # alertes pour une panne feraient chercher deux causes.
        tarie = (
            not muette
            and seuil_neuf is not None
            and silence is not None
            and silence > seuil_neuf.days
        )
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
                "silence_jours": silence,
                # renseigné seulement quand la source a un rythme mesurable ;
                # exposé pour que l'alerte soit relisible sans lire le code
                "seuil_jours": seuil_neuf.days if seuil_neuf else None,
                "tarie": tarie,
            }
        )
    etats.sort(
        key=lambda e: (not (e["muette"] or e["tarie"]), e["dernier_run_ok"] or "")
    )
    return etats


def _dates_de_publication(db: Session, aujourdhui: date) -> dict[int, list[date]]:
    """Dates de publication distinctes de l'année écoulée, par source.

    La fraîcheur du CONTENU se juge sur `date_publication`, pas sur
    `date_collecte` : quand le gouvernement réécrit une vieille page, la
    collecte crée un document daté d'aujourd'hui alors que rien de neuf n'a été
    publié. C'est exactement ce qui masquait le silence d'août 2026.

    La fenêtre d'un an écarte aussi les dates aberrantes des fonds anciens :
    Légiburkina archive des textes du XIXe siècle, et l'écart maximal brut de
    cette source dépasse 270 000 jours.
    """
    lignes = db.execute(
        select(Document.source_id, Document.date_publication)
        .where(
            Document.date_publication.is_not(None),
            Document.date_publication >= aujourdhui - FENETRE_RYTHME,
            Document.date_publication <= aujourdhui,
        )
        .group_by(Document.source_id, Document.date_publication)
    ).all()
    par_source: dict[int, list[date]] = {}
    for source_id, jour in lignes:
        par_source.setdefault(source_id, []).append(jour)
    for dates in par_source.values():
        dates.sort()
    return par_source


def _seuil_de_silence(dates: list[date], cadence: str) -> timedelta | None:
    """Combien de jours de silence sont anormaux POUR CETTE SOURCE.

    Le plus long silence déjà observé sur l'année, majoré d'une marge. `None`
    quand la source n'a pas assez publié pour qu'un rythme veuille dire quelque
    chose : mieux vaut ne pas la juger que l'accuser sur deux points.
    """
    plancher = PLANCHERS_NOUVEAUTE.get(cadence, PLANCHER_NOUVEAUTE_DEFAUT)
    if len(dates) < MINIMUM_POINTS:
        return None
    plus_long = max((b - a).days for a, b in zip(dates, dates[1:]))
    return max(plancher, timedelta(days=int(plus_long * MARGE) + 1))


def _en_utc(moment: datetime | None) -> datetime | None:
    """PostgreSQL rend un horodatage conscient du fuseau, SQLite (les tests) le
    rend naïf. Les comparer sans les ramener au même monde lève une TypeError."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


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
            "SOURCE TARIE : %s - collecte OK, mais rien de publié depuis le %s "
            "(%s jours de silence, seuil %s d'après son propre rythme). "
            "Vérifier que la source publie toujours, et au même endroit.",
            e["slug"],
            e["derniere_publication"],
            e["silence_jours"],
            e["seuil_jours"],
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
