"""Extraction des informations financières des comptes rendus du Conseil des ministres.

Deux familles :
- ENGAGEMENTS : décisions portant un montant explicite en FCFA (marchés
  publics, conventions, subventions, prêts, garanties, décaissements) ;
- BUDGETS : lois de finances adoptées (initiale, rectificative, règlement)
  avec recettes/dépenses totales de l'exercice.

Même mécanique que l'extraction des décisions/nominations : sortie
structurée Pydantic via le fournisseur configuré (Mistral par défaut),
statut_validation='a_valider', traçabilité vers le CR source.

Usage : python -m app.extraction.finances [max_docs]
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import BudgetExercice, Document, EngagementFinancier

logger = logging.getLogger(__name__)

MODELE_MISTRAL = "mistral-small-latest"
MODELE_ANTHROPIC = "claude-opus-5"
TEXTE_MINIMUM = 500


class EngagementExtrait(BaseModel):
    ministere: str | None = Field(
        default=None, description="Ministère ou institution de rattachement (« AU TITRE DE … »)"
    )
    type: Literal["marche", "convention", "subvention", "pret", "garantie", "decaissement", "autre"]
    objet: str = Field(description="Objet de la dépense en 1 à 2 phrases, fidèle au texte")
    beneficiaire: str | None = Field(
        default=None, description="Entreprise attributaire ou bénéficiaire, si nommé"
    )
    montant_fcfa: int = Field(
        description="Montant TOTAL en francs CFA, en nombre entier. "
        "1 milliard = 1000000000 ; 1 million = 1000000. TTC si précisé."
    )
    confiance: float = Field(ge=0, le=1)


class BudgetExtrait(BaseModel):
    exercice: int = Field(description="Année de l'exercice budgétaire concerné")
    type_loi: Literal["initiale", "rectificative", "reglement"]
    recettes_fcfa: int | None = Field(
        default=None, description="Total des recettes de l'État en FCFA, si chiffré dans le texte"
    )
    depenses_fcfa: int | None = Field(
        default=None, description="Total des dépenses de l'État en FCFA, si chiffré dans le texte"
    )
    confiance: float = Field(ge=0, le=1)


class ExtractionFinances(BaseModel):
    engagements: list[EngagementExtrait]
    budgets: list[BudgetExtrait]


PROMPT_SYSTEME = """\
Tu analyses un compte rendu officiel du Conseil des ministres du Burkina Faso \
pour en extraire les informations FINANCIÈRES uniquement.

1. ENGAGEMENTS : relève chaque décision portant un MONTANT EXPLICITE en francs \
CFA — attribution de marché public, convention, subvention, prêt ou accord de \
financement, garantie, décaissement. Pour chacune : le ministère de rattachement, \
la nature, l'objet (1-2 phrases fidèles), le bénéficiaire ou attributaire s'il est \
nommé, et le montant TOTAL converti en FCFA entier (1 milliard = 1000000000, \
1 million = 1000000). Ignore les décisions sans montant chiffré. Si plusieurs \
lots d'un même marché sont détaillés, une entrée par lot attribué. \
N'inclus PAS dans les engagements : l'adoption ou l'exécution du budget de \
l'État, les lois de finances et de règlement, les situations de trésorerie — \
ces montants relèvent de la partie BUDGETS ci-dessous.

2. BUDGETS : si le conseil adopte une loi de finances (initiale ou rectificative) \
ou une loi de règlement du budget, relève l'exercice (année), le type, et les \
totaux de recettes et de dépenses en FCFA s'ils figurent dans le texte.

N'invente AUCUN chiffre : si un montant est ambigu ou absent, omets l'entrée. \
Si le texte ne contient rien de financier, retourne des listes vides."""


def extraire_finances(texte: str) -> ExtractionFinances:
    if settings.llm_provider == "anthropic":
        return _extraire_anthropic(texte)
    return _extraire_mistral(texte)


def _extraire_mistral(texte: str) -> ExtractionFinances:
    from mistralai.client import Mistral

    client = Mistral(api_key=settings.mistral_api_key)
    for tentative in range(4):
        try:
            response = client.chat.parse(
                model=MODELE_MISTRAL,
                messages=[
                    {"role": "system", "content": PROMPT_SYSTEME},
                    {"role": "user", "content": texte},
                ],
                response_format=ExtractionFinances,
                temperature=0,
            )
            break
        except Exception as exc:  # noqa: BLE001
            status = getattr(exc, "status_code", None)
            if status == 429 and tentative < 3:
                time.sleep(5 * (tentative + 1))
                continue
            raise
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("Réponse Mistral non conforme au schéma")
    return parsed


def _extraire_anthropic(texte: str) -> ExtractionFinances:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    response = client.messages.parse(
        model=MODELE_ANTHROPIC,
        max_tokens=16000,
        system=PROMPT_SYSTEME,
        messages=[{"role": "user", "content": texte}],
        output_format=ExtractionFinances,
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Sortie tronquée (max_tokens)")
    return response.parsed_output


def traiter_document(db: Session, doc: Document) -> tuple[int, int]:
    meta = dict(doc.meta or {})
    if meta.get("finances_extraites"):
        return (0, 0)
    if not doc.texte_extrait or len(doc.texte_extrait) < TEXTE_MINIMUM:
        meta["finances_extraites"] = "sans_texte"
        doc.meta = meta
        db.commit()
        return (0, 0)

    extraction = extraire_finances(doc.texte_extrait)
    for e in extraction.engagements:
        db.add(
            EngagementFinancier(
                document_id=doc.id,
                ministere=e.ministere,
                type=e.type,
                objet=e.objet,
                beneficiaire=e.beneficiaire,
                montant_fcfa=e.montant_fcfa,
                score_confiance=e.confiance,
            )
        )
    for b in extraction.budgets:
        db.add(
            BudgetExercice(
                document_id=doc.id,
                exercice=b.exercice,
                type_loi=b.type_loi,
                recettes_fcfa=b.recettes_fcfa,
                depenses_fcfa=b.depenses_fcfa,
                score_confiance=b.confiance,
            )
        )
    meta["finances_extraites"] = "ok"
    doc.meta = meta
    db.commit()
    logger.info(
        "Document %s : %d engagement(s), %d budget(s)",
        doc.id,
        len(extraction.engagements),
        len(extraction.budgets),
    )
    return (len(extraction.engagements), len(extraction.budgets))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    max_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    with SessionLocal() as db:
        docs = db.scalars(
            select(Document)
            .where(
                Document.type_doc == "cr_conseil",
                ~Document.meta.has_key("finances_extraites"),
            )
            .order_by(Document.date_publication.desc().nulls_last())
            .limit(max_docs)
        ).all()
        if not docs:
            print("Aucun compte rendu en attente d'extraction financière.")
            return 0
        total_e = total_b = echecs = 0
        for i, doc in enumerate(docs):
            if i:
                time.sleep(1.5)
            try:
                e, b = traiter_document(db, doc)
            except Exception:  # noqa: BLE001
                logging.exception("Échec sur le document %s — on continue", doc.id)
                db.rollback()
                echecs += 1
                continue
            total_e += e
            total_b += b
        print(
            f"{len(docs)} CR traités : {total_e} engagement(s) financier(s), "
            f"{total_b} budget(s) d'exercice (à valider dans /admin)."
            + (f" {echecs} échec(s)." if echecs else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
