"""Passe OCR ciblée sur les textes juridiques scannés.

Légiburkina publie ~96 % de scans : cette passe océrise en priorité les
textes à plus forte valeur citoyenne - Constitution, chartes, puis lois
(des plus récentes aux plus anciennes). Conçue pour tourner en fond dans
le conteneur worker (Tesseract + français installés).

Usage : python -m app.extraction.ocr_textes [max_docs]
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import case, select

from app.db import SessionLocal
from app.extraction.pdf import extraire_texte
from app.models import Document
from app.stockage import stockage

logger = logging.getLogger(__name__)

PRIORITE = case(
    (Document.type_doc == "constitution", 0),
    (Document.type_doc == "charte", 1),
    # jurisprudence constitutionnelle et rapports de contrôle : peu nombreux,
    # entièrement scannés, et sans texte ils sont introuvables - donc tôt
    (Document.type_doc == "decision_constitutionnelle", 2),
    (Document.type_doc == "avis_constitutionnel", 2),
    (Document.type_doc == "ordonnance_constitutionnelle", 2),
    (Document.type_doc == "rapport_controle", 2),
    (Document.type_doc == "loi", 3),
    (Document.type_doc == "ordonnance", 4),
    else_=5,  # décrets, arrêtés… - le gros volume, en dernier
)
TYPES_CIBLES = (
    "constitution", "charte", "loi", "ordonnance", "decret", "arrete", "texte_juridique",
    "decision_constitutionnelle", "avis_constitutionnel", "ordonnance_constitutionnelle",
    "rapport_controle", "affaire_anticorruption",
)


def main(max_docs: int | None = None) -> int:
    # `max_docs` permet au worker d'appeler cette passe avec un budget borné
    # sans passer par la ligne de commande (cf. app/ingestion/scheduler.py)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if max_docs is None:
        max_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    with SessionLocal() as db:
        docs = db.scalars(
            select(Document)
            .where(
                Document.meta["pdf_statut"].astext == "scan",
                Document.type_doc.in_(TYPES_CIBLES),
                Document.fichier.is_not(None),
            )
            .order_by(PRIORITE, Document.date_publication.desc().nulls_last())
            .limit(max_docs)
        ).all()
        if not docs:
            print("Aucun scan cible en attente d'OCR.")
            return 0
        ok = echecs = 0
        for i, doc in enumerate(docs):
            # en stockage objet, chaque document est retiré du bucket dans un
            # fichier temporaire puis effacé - d'où le context manager
            with stockage.fichier_local(doc.fichier) as chemin:
                texte, statut = extraire_texte(chemin, ocr=True)
            meta = dict(doc.meta or {})
            if statut == "ocr" and len(texte) >= 200:
                doc.texte_extrait = texte
                doc.statut_extraction = "ocr"
                meta["pdf_statut"] = "ocr"
                ok += 1
            else:
                meta["pdf_statut"] = "echec_ocr"
                echecs += 1
            doc.meta = meta
            db.commit()
            if (i + 1) % 20 == 0:
                logger.info("%d/%d océrisés (%d échecs)", i + 1, len(docs), echecs)
        print(f"{len(docs)} document(s) : {ok} océrisés, {echecs} échec(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
