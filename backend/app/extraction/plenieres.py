"""Textes adoptés en séance plénière de l'Assemblée législative du peuple.

Les comptes rendus de plénière (cf. app/ingestion/pleniere.py) disent ce que ni
Légiburkina ni le Journal officiel ne disent, ou seulement des semaines plus
tard : quel texte a été adopté, quel jour, par combien de votants, sur le
rapport de quelle commission. On en tire un registre des votes, déposé en
`a_valider` comme toute extraction.

Registre FACTUEL : on ne retient que ce que le compte rendu affirme. Un nombre
de voix absent du texte reste vide - « adopté à l'unanimité » ne dit pas
combien de députés siégeaient, et l'inventer fausserait la seule donnée
chiffrée de la page.

Usage : python -m app.extraction.plenieres [max_docs]
"""

from __future__ import annotations

import logging
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Document, VotePlenier
from app.versions import ids_versions_de_reference

logger = logging.getLogger(__name__)

TYPE_DOC = "compte_rendu_pleniere"

NATURES = {
    "projet_loi": "Projet de loi",
    "proposition_loi": "Proposition de loi",
    "ratification": "Autorisation de ratification",
    "loi_finances": "Loi de finances",
    "resolution": "Résolution",
    "autre": "Autre texte",
}

# Pré-filtre : une séance de questions au gouvernement ou d'ouverture de session
# n'adopte rien, et ne vaut pas un appel.
_VOTE = re.compile(r"adopt|vot[ée]|ratifi|rejet", re.IGNORECASE)


def pertinent(titre: str | None, texte: str | None) -> bool:
    return bool(_VOTE.search(f"{titre or ''} {texte or ''}"))


class VoteExtrait(BaseModel):
    intitule: str = Field(
        description="Intitulé du texte soumis au vote, tel que le compte rendu le nomme, "
        "sans le verbe : « projet de loi portant initiatives carbone »."
    )
    nature: Literal[
        "projet_loi", "proposition_loi", "ratification", "loi_finances", "resolution", "autre"
    ] = Field(
        description="projet_loi (déposé par le gouvernement), proposition_loi (déposée par des "
        "députés), ratification (loi autorisant la ratification d'un accord ou d'un traité), "
        "loi_finances (budget, loi de finances rectificative, loi de règlement), "
        "resolution, autre."
    )
    resultat: Literal["adopte", "rejete"] = "adopte"
    date_seance: date | None = Field(
        default=None, description="Date de la séance où le vote a eu lieu, si le texte la donne."
    )
    unanimite: bool | None = Field(
        default=None, description="true seulement si le texte dit « à l'unanimité »."
    )
    votants: int | None = Field(default=None, description="Nombre de votants, s'il est écrit.")
    pour: int | None = Field(default=None, description="Voix pour, si elles sont écrites.")
    contre: int | None = Field(default=None, description="Voix contre, si elles sont écrites.")
    abstentions: int | None = Field(default=None, description="Abstentions, si elles sont écrites.")
    commission: str | None = Field(
        default=None, description="Commission saisie au fond, avec son sigle s'il est donné."
    )
    presente_par: str | None = Field(
        default=None,
        description="Membre du gouvernement ou député qui a défendu le texte : nom et fonction.",
    )
    resume: str | None = Field(
        default=None, description="Une ou deux phrases neutres sur ce que le texte change."
    )
    confiance: float = Field(ge=0, le=1, description="Confiance dans cette extraction, de 0 à 1.")


class ExtractionPleniere(BaseModel):
    votes: list[VoteExtrait] = Field(default_factory=list)


SYSTEME = """Tu lis un compte rendu de séance plénière de l'Assemblée législative du peuple \
(Burkina Faso, anciennement Assemblée législative de transition) et tu en extrais les textes \
soumis au VOTE des députés pendant cette séance.

Règles :
- Une entrée par texte voté. Une séance peut en adopter plusieurs, ou aucun : questions au \
gouvernement, ouverture ou clôture de session, installation de députés, discours, audiences \
ne sont pas des votes. Dans ce cas, renvoie une liste vide.
- N'invente rien. Un nombre absent du compte rendu reste null. « À l'unanimité des 71 votants » \
donne unanimite=true, votants=71, pour=71, contre=0, abstentions=0. « À l'unanimité » sans \
chiffre donne unanimite=true et tout le reste null.
- Un texte seulement présenté, examiné en commission ou annoncé pour une séance future n'est \
pas voté : ne le retiens pas.
- Le résumé est neutre et factuel, sans reprendre les formules d'éloge du compte rendu."""


def extraire(texte: str) -> ExtractionPleniere:
    from app.extraction.claude import extraire as appel

    return appel(texte, schema=ExtractionPleniere, systeme=SYSTEME, max_tokens=6000)


def cle_intitule(intitule: str) -> str:
    """Intitulé réduit à ses lettres, pour reconnaître un même texte d'un compte
    rendu à l'autre (le site en publie parfois deux pour une même séance)."""
    sans_accents = unicodedata.normalize("NFKD", intitule).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).strip()


def _doublon(db: Session, date_seance: date | None, intitule: str) -> bool:
    cle = cle_intitule(intitule)
    candidats = db.scalars(
        select(VotePlenier.intitule).where(
            VotePlenier.date_seance == date_seance, VotePlenier.statut_validation != "rejete"
        )
    )
    return any(cle_intitule(autre) == cle for autre in candidats)


def traiter_document(db: Session, doc: Document) -> int:
    """Extrait les votes d'un compte rendu ; renvoie le nombre créé."""
    if doc.date_structuration is not None:
        return 0
    extraction = extraire(f"{doc.titre or ''}\n\n{doc.texte_extrait or ''}")
    crees = 0
    for v in extraction.votes:
        date_seance = v.date_seance or doc.date_publication
        intitule = v.intitule.strip()
        if not intitule or _doublon(db, date_seance, intitule):
            continue
        db.add(
            VotePlenier(
                document_id=doc.id,
                intitule=intitule,
                nature=v.nature,
                resultat=v.resultat,
                date_seance=date_seance,
                unanimite=v.unanimite,
                votants=v.votants,
                pour=v.pour,
                contre=v.contre,
                abstentions=v.abstentions,
                commission=(v.commission or None) and v.commission[:300],
                presente_par=(v.presente_par or None) and v.presente_par[:300],
                resume=v.resume,
                score_confiance=v.confiance,
                statut_validation="a_valider",
            )
        )
        db.flush()  # le texte suivant du même compte rendu doit voir celui-ci
        crees += 1
    doc.date_structuration = datetime.now(timezone.utc)
    db.commit()
    if crees:
        logger.info("Plénière %s : %d vote(s) extrait(s)", doc.id, crees)
    return crees


def traiter_lot(db: Session, max_docs: int) -> tuple[int, int, int, int]:
    """Renvoie (comptes rendus vus, votes créés, écartés par le pré-filtre, échecs)."""
    docs = db.scalars(
        select(Document)
        .where(
            Document.type_doc == TYPE_DOC,
            Document.date_structuration.is_(None),
            Document.id.in_(ids_versions_de_reference()),
        )
        .order_by(Document.date_publication.desc().nulls_last())
        .limit(max_docs)
    ).all()
    total = filtres = echecs = appels = 0
    for doc in docs:
        if not pertinent(doc.titre, doc.texte_extrait):
            doc.date_structuration = datetime.now(timezone.utc)
            filtres += 1
            continue
        if appels:
            time.sleep(0.5)
        appels += 1
        try:
            total += traiter_document(db, doc)
        except Exception:  # noqa: BLE001 - un compte rendu en échec n'arrête pas le lot
            logger.exception("Échec sur le compte rendu %s - on continue", doc.id)
            db.rollback()
            echecs += 1
    db.commit()
    return len(docs), total, filtres, echecs


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    max_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    with SessionLocal() as db:
        vus, total, filtres, echecs = traiter_lot(db, max_docs)
    print(
        f"{vus} compte(s) rendu(s) : {total} vote(s) extrait(s) (à valider), "
        f"{filtres} sans vote" + (f", {echecs} échec(s)." if echecs else ".")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
