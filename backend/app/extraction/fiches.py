"""Fiches de lecture des décisions du Conseil constitutionnel et des rapports de l'ASCE-LC.

Ces deux corpus sont archivés depuis l'été 2026 mais restaient illisibles sans
ouvrir chaque PDF : une décision s'intitule « Décision n° 2016-019 CC », un
rapport d'audit pèse plusieurs centaines de pages. La fiche dit en quelques
lignes de quoi il s'agit - qui a saisi le Conseil, sur quoi, ce qu'il a décidé ;
quelle entité a été contrôlée, sur quelle période, ce qui a été constaté.

Trois garde-fous, parce que résumer une décision de justice n'est pas anodin :

- la fiche RAPPORTE, elle ne commente pas : pas d'appréciation, pas de portée
  politique, seulement ce que le document énonce ;
- le sens de la décision (« issue ») est une liste fermée, et « autre » plutôt
  qu'un choix forcé quand le dispositif ne s'y range pas ;
- comme toute extraction, la fiche est déposée en `a_valider` : elle n'est
  publiée qu'après relecture, et le document officiel reste à un clic.

Beaucoup de ces textes viennent d'une OCR : le modèle est prévenu, et un champ
illisible reste vide plutôt que deviné.

Usage : python -m app.extraction.fiches [max_docs]
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Document, FicheDocument
from app.versions import ids_versions_de_reference

logger = logging.getLogger(__name__)

TYPES_CONSTITUTIONNEL = (
    "decision_constitutionnelle",
    "avis_constitutionnel",
    "ordonnance_constitutionnelle",
)
TYPES_CONTROLE = (
    "rapport_controle",
    "affaire_anticorruption",
    "declaration_patrimoine",
    "plainte_denonciation",
)

# En dessous, il n'y a pas de quoi établir une fiche (page d'annonce, scan non lu).
TEXTE_MINIMUM = 600
# Un rapport d'audit peut dépasser le million de caractères. On lit le début
# (objet, périmètre, synthèse) et la fin (conclusions, recommandations) : c'est
# là que se trouve ce qu'une fiche rapporte, et cela borne le coût de l'appel.
DEBUT, FIN = 45_000, 15_000

CATEGORIES = {
    "controle_constitutionnalite": "Contrôle de constitutionnalité",
    "contentieux_electoral": "Contentieux électoral",
    "engagement_international": "Traité ou engagement international",
    "reglement_assemblee": "Règlement d'une assemblée",
    "vacance_empechement": "Vacance ou empêchement",
    "avis_consultatif": "Avis consultatif",
    "audit_controle": "Audit ou contrôle",
    "rapport_annuel": "Rapport annuel d'activités",
    "lutte_anticorruption": "Lutte anticorruption",
    "declaration_patrimoine": "Déclarations de patrimoine",
    "plaintes": "Plaintes et dénonciations",
    "autre": "Autre",
}

ISSUES = {
    "conforme": "Conforme à la Constitution",
    "conforme_sous_reserve": "Conforme sous réserve",
    "non_conforme": "Non conforme à la Constitution",
    "irrecevable": "Requête irrecevable",
    "rejet": "Requête rejetée",
    "admission": "Requête admise",
    "incompetence": "Incompétence du Conseil",
    "constat": "Constat",
    "avis_rendu": "Avis rendu",
    "autre": "Autre",
}


class FicheConstitutionnelle(BaseModel):
    objet: str = Field(
        description="Une phrase : ce sur quoi le Conseil se prononce. Ex. « Conformité à la "
        "Constitution de la loi organique n°… portant statut de la magistrature »."
    )
    categorie: Literal[
        "controle_constitutionnalite", "contentieux_electoral", "engagement_international",
        "reglement_assemblee", "vacance_empechement", "avis_consultatif", "autre",
    ]
    partie: str | None = Field(
        default=None,
        description="Auteur de la saisine : fonction et nom s'ils sont lisibles "
        "(« le Premier ministre », « M. X, candidat »). null si illisible.",
    )
    issue: Literal[
        "conforme", "conforme_sous_reserve", "non_conforme", "irrecevable", "rejet",
        "admission", "incompetence", "constat", "avis_rendu", "autre",
    ] = Field(description="Le sens du dispositif. « autre » s'il ne se range dans aucun cas.")
    resume: str = Field(
        description="Deux à quatre phrases neutres : la question posée, le raisonnement en bref, "
        "ce que le Conseil décide. Aucune appréciation."
    )
    points: list[str] = Field(
        default_factory=list,
        description="Jusqu'à cinq points : les articles du dispositif, reformulés fidèlement.",
    )
    date_document: date | None = Field(
        default=None, description="Date de la décision ou de l'avis, si elle est lisible."
    )
    confiance: float = Field(ge=0, le=1)


class FicheControle(BaseModel):
    objet: str = Field(
        description="Une phrase : ce que le document rapporte. Ex. « Audit de la gestion de la "
        "commune de X, exercices 2019 à 2021 »."
    )
    categorie: Literal[
        "audit_controle", "rapport_annuel", "lutte_anticorruption",
        "declaration_patrimoine", "plaintes", "autre",
    ]
    partie: str | None = Field(
        default=None,
        description="Entité contrôlée ou concernée (ministère, commune, société d'État…). "
        "null pour un rapport général.",
    )
    resume: str = Field(
        description="Deux à quatre phrases neutres : périmètre, période, principaux constats "
        "tels que le document les énonce. Aucune appréciation."
    )
    points: list[str] = Field(
        default_factory=list,
        description="Jusqu'à cinq constats ou recommandations, avec les chiffres que le document "
        "donne (montants, nombres de dossiers). Jamais de nom de personne mise en cause.",
    )
    date_document: date | None = Field(
        default=None, description="Date du rapport ou de la publication, si elle est lisible."
    )
    confiance: float = Field(ge=0, le=1)


_COMMUN = """Le texte peut venir d'une reconnaissance optique (OCR) : lettres confondues, \
mots coupés, en-têtes parasites. Rapporte ce qui est lisible ; laisse null ce qui ne l'est pas ; \
baisse la confiance si le texte est très dégradé. N'invente aucun nom, numéro, date ou montant.
Tu rapportes, tu ne commentes pas : aucune appréciation sur le bien-fondé, la portée ou les \
personnes. Écris en français, au présent, phrases courtes."""

SYSTEME_CONSTITUTIONNEL = (
    "Tu établis la fiche d'une décision, d'un avis ou d'une ordonnance du Conseil constitutionnel "
    "du Burkina Faso, à partir de son texte intégral.\n"
    "L'« issue » reprend le dispositif : ce que le Conseil décide dans ses articles finaux, pas "
    "ce que demandait le requérant. Pour un avis, l'issue est « avis_rendu » sauf s'il déclare "
    "une conformité ou une non-conformité.\n" + _COMMUN
)

SYSTEME_CONTROLE = (
    "Tu établis la fiche d'un document de l'ASCE-LC, l'Autorité supérieure de contrôle d'État et "
    "de lutte contre la corruption du Burkina Faso : rapport d'audit, rapport annuel, dossier "
    "anticorruption, situation des déclarations de patrimoine ou des plaintes. Si le texte est "
    "long, seuls son début et sa fin te sont donnés.\n"
    "Ne cite jamais le nom d'une personne mise en cause ou soupçonnée : désigne-la par sa "
    "fonction. Une irrégularité relevée par un audit n'est pas une condamnation.\n" + _COMMUN
)


def genre_de(type_doc: str) -> str | None:
    if type_doc in TYPES_CONSTITUTIONNEL:
        return "constitutionnel"
    if type_doc in TYPES_CONTROLE:
        return "controle"
    return None


def extrait_utile(texte: str) -> str:
    """Le texte à lire : entier s'il est court, début et fin sinon."""
    if len(texte) <= DEBUT + FIN:
        return texte
    return f"{texte[:DEBUT]}\n\n[… passage non transmis …]\n\n{texte[-FIN:]}"


def extraire(genre: str, texte: str):
    from app.extraction.claude import extraire as appel

    if genre == "constitutionnel":
        return appel(
            texte, schema=FicheConstitutionnelle, systeme=SYSTEME_CONSTITUTIONNEL, max_tokens=5000
        )
    return appel(texte, schema=FicheControle, systeme=SYSTEME_CONTROLE, max_tokens=5000)


def traiter_document(db: Session, doc: Document) -> bool:
    """Établit la fiche d'un document ; renvoie True si elle a été créée."""
    genre = genre_de(doc.type_doc)
    if genre is None or doc.date_structuration is not None:
        return False
    if db.scalar(select(FicheDocument.id).where(FicheDocument.document_id == doc.id)):
        return False
    extraite = extraire(genre, f"{doc.titre or ''}\n\n{extrait_utile(doc.texte_extrait or '')}")
    points = [p.strip() for p in extraite.points if p and p.strip()][:5]
    db.add(
        FicheDocument(
            document_id=doc.id,
            genre=genre,
            objet=extraite.objet.strip(),
            categorie=extraite.categorie,
            partie=(extraite.partie or None) and extraite.partie.strip()[:500],
            issue=getattr(extraite, "issue", None),
            resume=extraite.resume.strip(),
            points=points,
            date_document=extraite.date_document,
            score_confiance=extraite.confiance,
            statut_validation="a_valider",
        )
    )
    doc.date_structuration = datetime.now(timezone.utc)
    db.commit()
    return True


def traiter_lot(db: Session, max_docs: int) -> tuple[int, int, int]:
    """Renvoie (documents vus, fiches créées, échecs).

    Les documents sans texte exploitable (page d'annonce, scan non encore lu)
    sont écartés par la requête, sans être marqués : ils seront repris une fois
    passés par l'OCR, et ne font pas écran aux autres dans un lot borné.
    """
    docs = db.scalars(
        select(Document)
        .where(
            Document.type_doc.in_(TYPES_CONSTITUTIONNEL + TYPES_CONTROLE),
            Document.date_structuration.is_(None),
            func.length(func.coalesce(Document.texte_extrait, "")) >= TEXTE_MINIMUM,
            Document.id.in_(ids_versions_de_reference()),
        )
        .order_by(Document.date_publication.desc().nulls_last(), Document.id.desc())
        .limit(max_docs)
    ).all()
    creees = echecs = 0
    for i, doc in enumerate(docs):
        if i:
            time.sleep(0.5)
        try:
            creees += traiter_document(db, doc)
        except Exception:  # noqa: BLE001 - un document en échec n'arrête pas le lot
            logger.exception("Fiche en échec sur le document %s - on continue", doc.id)
            db.rollback()
            echecs += 1
    return len(docs), creees, echecs


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    max_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    with SessionLocal() as db:
        vus, creees, echecs = traiter_lot(db, max_docs)
    print(
        f"{vus} document(s) : {creees} fiche(s) établie(s) (à valider)"
        + (f", {echecs} échec(s)." if echecs else ".")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
