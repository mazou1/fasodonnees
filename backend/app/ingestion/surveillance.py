"""Surveillance des collectes : détecte les sources « muettes ».

Une source est muette si son dernier run réussi remonte à plus longtemps que
ne l'autorise sa cadence (avec une marge tolérant les week-ends et les mises
en veille de la machine). Sans infrastructure d'envoi d'e-mails, l'alerte se
matérialise par un WARNING dans les logs du worker ET par l'état exposé sur
`GET /sources/etat` (bandeau possible côté site, colonne dans l'admin).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Run, Source

logger = logging.getLogger(__name__)

# délai maximal sans run réussi avant de considérer la source muette, par cadence
SEUILS = {
    "30min": timedelta(hours=3),
    "quotidien": timedelta(days=2),
    "hebdo": timedelta(days=10),
}
SEUIL_DEFAUT = timedelta(days=2)


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
    etats = []
    for source, dernier_ok in lignes:
        seuil = SEUILS.get(source.cadence, SEUIL_DEFAUT)
        muette = dernier_ok is None or (maintenant - dernier_ok) > seuil
        etats.append(
            {
                "slug": source.slug,
                "nom": source.nom,
                "cadence": source.cadence,
                "dernier_run_ok": dernier_ok.isoformat() if dernier_ok else None,
                "muette": muette,
            }
        )
    etats.sort(key=lambda e: (not e["muette"], e["dernier_run_ok"] or ""))
    return etats


def verifier_sources_muettes(db: Session | None = None) -> list[dict]:
    """Journalise un WARNING par source muette. Renvoie la liste des muettes."""
    if db is None:
        from app.db import SessionLocal

        with SessionLocal() as db:
            return verifier_sources_muettes(db)

    muettes = [e for e in etat_sources(db) if e["muette"]]
    for e in muettes:
        logger.warning(
            "SOURCE MUETTE : %s (%s) - dernier run réussi : %s",
            e["slug"],
            e["cadence"],
            e["dernier_run_ok"] or "jamais",
        )
    if not muettes:
        logger.info("Surveillance des sources : toutes à jour.")
    return muettes


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    muettes = verifier_sources_muettes()
    print(f"{len(muettes)} source(s) muette(s).")
    return 1 if muettes else 0


if __name__ == "__main__":
    raise SystemExit(main())
