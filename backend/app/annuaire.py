"""Consolidation de l'annuaire : nominations validées → mandats.

Les mandats sont une vue dérivée : on les reconstruit entièrement à chaque
consolidation (idempotent, pas de logique incrémentale fragile). Seules les
nominations avec statut_validation='valide' comptent.

Règles :
- une nomination ouvre un mandat (personne, poste, structure, date_debut) ;
- une fin_fonction ferme le mandat ouvert le plus récent de la même personne
  (même structure si renseignée) ;
- SUCCESSION : nommer quelqu'un à un siège à titulaire unique (DG, SG,
  préfet… - cf. annuaire_succession) met fin au mandat du titulaire précédent
  à la date de la nouvelle nomination. Les postes collégiaux (administrateurs,
  conseillers, inspecteurs…) n'entraînent jamais de fin : plusieurs titulaires
  coexistent ;
- réattribuer le même siège à la même personne ne crée pas de doublon.

L'identité d'un siège est (structure CANONIQUE, clé de rôle) : un ministère ou
un établissement renommé ne casse pas la chaîne de succession.

Usage : python -m app.annuaire
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.annuaire_succession import cle_siege
from app.db import SessionLocal
from app.models import Document, Mandat, Nomination, Structure

logger = logging.getLogger(__name__)


def _canoniques(db: Session) -> tuple[dict[int, int], set[int]]:
    """(structure_id brut → structure_id canonique, cids de structures « uniques »).

    « Unique » = le nom canonique ne commence pas par « Ministère » : une telle
    structure désigne une seule entité, où « le directeur général » est sans
    ambiguïté. Les structures « Ministère … » hébergent plusieurs directions
    générales, d'où un traitement de succession plus prudent (cf. cle_siege)."""
    import re

    canon: dict[int, int] = {}
    nom_par_id: dict[int, str] = {}
    for sid, cid, nom in db.execute(
        select(Structure.id, func.coalesce(Structure.canonique_id, Structure.id), Structure.nom)
    ).all():
        canon[sid] = cid
        nom_par_id[sid] = nom
    # une structure canonique (sid == cid) est « unique » si son nom n'est pas
    # celui d'un ministère
    uniques = {
        cid
        for sid, cid in canon.items()
        if sid == cid and not re.match(r"^\s*minist[èe]re\b", nom_par_id.get(cid, ""), re.I)
    }
    return canon, uniques


def consolider(db: Session) -> int:
    db.execute(delete(Mandat))
    canon, uniques = _canoniques(db)

    nominations = db.scalars(
        select(Nomination)
        .join(Document)
        .where(Nomination.statut_validation == "valide")
        .order_by(
            Document.date_publication.asc().nulls_first(),
            Nomination.id.asc(),
        )
    ).all()

    ouverts: dict[int, list[Mandat]] = {}  # personne_id -> mandats sans date_fin
    # siège à titulaire unique -> mandat ouvert courant (le dernier titulaire)
    sieges: dict[tuple[int, str], Mandat] = {}
    total = 0

    def _fermer(mandat: Mandat, date_fin, nomination_id: int | None) -> None:
        mandat.date_fin = date_fin
        mandat.nomination_fin_id = nomination_id
        liste = ouverts.get(mandat.personne_id)
        if liste and mandat in liste:
            liste.remove(mandat)

    for nom in nominations:
        date_ref = nom.date_effet or nom.document.date_publication
        cid = canon.get(nom.structure_id) if nom.structure_id is not None else None
        cle = cle_siege(nom.poste, structure_unique=cid in uniques) if cid is not None else None
        siege = (cid, cle) if (cid is not None and cle is not None) else None

        if nom.type == "nomination":
            # même personne déjà ouverte sur ce siège (ou ce poste/structure) :
            # réattribution, pas de doublon
            if siege is not None:
                actuel = sieges.get(siege)
                if actuel is not None and actuel.personne_id == nom.personne_id:
                    continue
            elif any(
                m.poste == nom.poste and m.structure_id == nom.structure_id
                for m in ouverts.get(nom.personne_id, [])
            ):
                continue

            # succession : le titulaire précédent du siège quitte à cette date
            if siege is not None:
                sortant = sieges.get(siege)
                if sortant is not None and sortant.personne_id != nom.personne_id:
                    _fermer(sortant, date_ref, nom.id)

            mandat = Mandat(
                personne_id=nom.personne_id,
                structure_id=nom.structure_id,
                poste=nom.poste,
                date_debut=date_ref,
                nomination_debut_id=nom.id,
            )
            db.add(mandat)
            ouverts.setdefault(nom.personne_id, []).append(mandat)
            if siege is not None:
                sieges[siege] = mandat
            total += 1
        else:  # fin_fonction explicite
            candidats = ouverts.get(nom.personne_id, [])
            if nom.structure_id is not None:
                cibles = [m for m in candidats if m.structure_id == nom.structure_id] or candidats
            else:
                cibles = candidats
            if cibles:
                mandat = cibles[-1]
                _fermer(mandat, date_ref, nom.id)
                if siege is not None and sieges.get(siege) is mandat:
                    del sieges[siege]

    db.commit()
    logger.info("Annuaire consolidé : %d mandat(s) à partir de %d nomination(s) validées",
                total, len(nominations))
    return total


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with SessionLocal() as db:
        n = consolider(db)
        print(f"{n} mandat(s) consolidés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
