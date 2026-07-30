"""Extraction de la composition du gouvernement depuis le décret officiel.

Le décret « portant composition du Gouvernement » liste les membres dans
l'ordre protocolaire. On extrait (ordre, civilité/grade, nom, poste) via le
fournisseur LLM configuré, en a_valider - la revue se fait dans l'admin.

Usage : python -m app.extraction.gouvernement <document_id>
"""

from __future__ import annotations

import logging
import sys
import time

from pydantic import BaseModel, Field
from sqlalchemy import delete

from app.config import settings
from app.db import SessionLocal
from app.models import Document, MembreGouvernement

logger = logging.getLogger(__name__)

MODELE_MISTRAL = "mistral-small-latest"


class MembreExtrait(BaseModel):
    ordre: int = Field(description="Numéro d'ordre protocolaire dans le décret")
    civilite: str | None = Field(
        default=None,
        description="Civilité ou grade tel qu'écrit : Monsieur, Madame, Commandant, "
        "Général de Brigade… (null si absent)",
    )
    nom_complet: str = Field(description="Nom complet de la personne")
    poste: str = Field(description="Intitulé complet du poste ministériel")
    confiance: float = Field(ge=0, le=1)


class CompositionGouvernement(BaseModel):
    membres: list[MembreExtrait]


PROMPT_SYSTEME = """\
Tu extrais la composition du gouvernement du Burkina Faso depuis le texte OCR \
d'un décret officiel « portant composition du Gouvernement ». Le décret liste \
les membres numérotés dans l'ordre protocolaire, chaque entrée donnant \
l'intitulé du poste puis la civilité (Monsieur/Madame) ou le grade militaire \
et le nom complet. Corrige les artefacts évidents d'OCR (accents, espaces) \
mais n'invente aucun nom ni poste. Reprends l'intitulé de poste complet, \
y compris « Ministre d'État, » ou « Ministre délégué… » le cas échéant."""


def extraire(texte: str) -> CompositionGouvernement:
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
                response_format=CompositionGouvernement,
                temperature=0,
            )
            break
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "status_code", None) == 429 and tentative < 3:
                time.sleep(5 * (tentative + 1))
                continue
            raise
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("Réponse non conforme au schéma")
    return parsed


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) != 2:
        print("Usage : python -m app.extraction.gouvernement <document_id>")
        return 1
    doc_id = int(sys.argv[1])
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        if doc is None or not doc.texte_extrait:
            print(f"Document {doc_id} introuvable ou sans texte.")
            return 1
        composition = extraire(doc.texte_extrait)
        # re-extraction : on remplace les membres issus de ce décret
        db.execute(delete(MembreGouvernement).where(MembreGouvernement.document_id == doc_id))
        for m in composition.membres:
            db.add(
                MembreGouvernement(
                    document_id=doc_id,
                    ordre=m.ordre,
                    civilite=m.civilite,
                    nom_complet=m.nom_complet,
                    poste=m.poste,
                    score_confiance=m.confiance,
                )
            )
        db.commit()
        print(f"{len(composition.membres)} membre(s) extraits (à valider dans /admin).")
        for m in composition.membres[:5]:
            print(f"  {m.ordre}. {m.poste[:60]} - {m.civilite or ''} {m.nom_complet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
