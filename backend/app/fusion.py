"""Fusion assistée des structures en doublon.

Les renommages de ministères au fil des remaniements (et les variantes
d'orthographe issues de l'extraction) éclatent l'annuaire. Principe du
cadrage : fusion manuelle ASSISTÉE, jamais automatique seule.

- `auto`     : fusionne les doublons STRICTS (même nom aux accents,
               majuscules et espaces près) - sans risque.
- `proposer` : écrit fusion_propositions.csv (paires similaires, pg_trgm)
               à relire ; passer la colonne `appliquer` à « oui » pour
               accepter une fusion (le canonique est la cible).
- `appliquer <csv>` : applique les lignes validées.

Les mandats/nominations gardent leur structure d'époque (fidélité
historique) ; les statistiques regroupent par coalesce(canonique_id, id).

Usage : python -m app.fusion auto | proposer [seuil] | appliquer <csv>
"""

from __future__ import annotations

import csv
import logging
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.extraction.texte import normaliser_nom
from app.models import Structure

logger = logging.getLogger(__name__)
CSV_PROPOSITIONS = Path("fusion_propositions.csv")


def _resoudre(db: Session, structure_id: int) -> int:
    """Suit la chaîne canonique_id jusqu'à la racine."""
    vu = set()
    sid = structure_id
    while True:
        if sid in vu:  # cycle - on s'arrête
            return sid
        vu.add(sid)
        cid = db.scalar(select(Structure.canonique_id).where(Structure.id == sid))
        if cid is None:
            return sid
        sid = cid


def fusionner(db: Session, source_id: int, canonique_id: int) -> None:
    racine = _resoudre(db, canonique_id)
    if racine == source_id:
        return
    source = db.get(Structure, source_id)
    cible = db.get(Structure, racine)
    source.canonique_id = racine
    if not cible.sigle and source.sigle:
        cible.sigle = source.sigle


def auto(db: Session) -> int:
    groupes: dict[str, list[Structure]] = defaultdict(list)
    for s in db.scalars(select(Structure).where(Structure.canonique_id.is_(None))).all():
        groupes[normaliser_nom(s.nom)].append(s)
    fusions = 0
    for membres in groupes.values():
        if len(membres) < 2:
            continue
        canonique = min(membres, key=lambda s: s.id)
        for doublon in membres:
            if doublon.id != canonique.id:
                fusionner(db, doublon.id, canonique.id)
                fusions += 1
    db.commit()
    return fusions


def proposer(db: Session, seuil: float) -> int:
    lignes = db.execute(
        text(
            """
            SELECT s1.id AS id_source, s1.nom AS nom_source,
                   s2.id AS id_canonique, s2.nom AS nom_canonique,
                   round(similarity(lower(unaccent(s1.nom)), lower(unaccent(s2.nom)))::numeric, 2) AS sim
            FROM structure s1
            JOIN structure s2 ON s2.id < s1.id
            WHERE s1.canonique_id IS NULL AND s2.canonique_id IS NULL
              AND similarity(lower(unaccent(s1.nom)), lower(unaccent(s2.nom))) >= :seuil
            ORDER BY sim DESC
            """
        ),
        {"seuil": seuil},
    ).all()
    with CSV_PROPOSITIONS.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["appliquer", "id_source", "nom_source", "id_canonique", "nom_canonique", "similarite"])
        for ligne in lignes:
            w.writerow(
                ["", ligne.id_source, ligne.nom_source, ligne.id_canonique, ligne.nom_canonique, ligne.sim]
            )
    return len(lignes)


def appliquer(db: Session, chemin: Path) -> int:
    fusions = 0
    with chemin.open(newline="") as f:
        for ligne in csv.DictReader(f):
            if ligne["appliquer"].strip().lower() in ("oui", "o", "x", "1", "true"):
                fusionner(db, int(ligne["id_source"]), int(ligne["id_canonique"]))
                fusions += 1
    db.commit()
    return fusions


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    commande = sys.argv[1] if len(sys.argv) > 1 else "auto"
    with SessionLocal() as db:
        if commande == "auto":
            n = auto(db)
            print(f"{n} doublon(s) strict(s) fusionné(s).")
        elif commande == "proposer":
            seuil = float(sys.argv[2]) if len(sys.argv) > 2 else 0.55
            n = proposer(db, seuil)
            print(f"{n} proposition(s) écrites dans {CSV_PROPOSITIONS} - "
                  "mettre 'oui' dans la colonne appliquer puis : python -m app.fusion appliquer "
                  f"{CSV_PROPOSITIONS}")
        elif commande == "appliquer":
            n = appliquer(db, Path(sys.argv[2]))
            print(f"{n} fusion(s) appliquée(s).")
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
