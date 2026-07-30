"""Jeu de référence saisi à la main : grandes infrastructures ANTÉRIEURES au
fil officiel (qui ne remonte qu'à 2022). Documenté et sourcé (Wikipédia,
presse), non exhaustif - signalé comme « Référence historique » et affiché
comme tel dans la note de méthode de la page.

Idempotent (clé = titre). Publié directement `valide` (données de référence
vérifiées à la main). Usage : python -m app.realisations_seed
"""

from __future__ import annotations

import csv
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.extraction.realisations import SECTEUR_PAR_TYPE
from app.geo import geocoder
from app.models import Realisation

logger = logging.getLogger(__name__)

CSV = Path(__file__).parent / "data" / "realisations_curatees.csv"
MARQUEUR = "Référence historique (jeu curé)"


def seed(db) -> int:
    existants = set(db.scalars(select(Realisation.titre)).all())
    ajouts = 0
    with CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            titre = row["titre"].strip()
            if titre in existants:
                continue
            loc = geocoder(db, row["lieu"])
            if loc is None:
                logger.warning("Curé : lieu non géocodé « %s » (%s) - ignoré", row["lieu"], titre)
                continue
            db.add(
                Realisation(
                    type=row["type"],
                    titre=titre,
                    description=row.get("description") or None,
                    statut=row["statut"],
                    date_evenement=date.fromisoformat(row["date"]),
                    localite_id=loc.id,
                    localisation_nom=loc.nom,
                    region=loc.region,
                    latitude=loc.latitude,
                    longitude=loc.longitude,
                    precision_geo="commune",
                    secteur=SECTEUR_PAR_TYPE.get(row["type"], "Autres"),
                    maitre_ouvrage=MARQUEUR,
                    montant_fcfa=int(row["montant_fcfa"]) if row.get("montant_fcfa") else None,
                    source_url=row.get("source_url") or None,
                    statut_validation="valide",
                )
            )
            existants.add(titre)
            ajouts += 1
    db.commit()
    return ajouts


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with SessionLocal() as db:
        n = seed(db)
    print(f"{n} infrastructure(s) de référence ajoutée(s) (jeu curé, validées).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
