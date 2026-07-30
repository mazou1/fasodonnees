"""Structuration manuelle des CR : python -m app.extraction.run [max_docs]

Traite les comptes rendus du Conseil des ministres pas encore structurés
(décisions + nominations), les plus récents d'abord.

Seules les **versions de référence** sont extraites : le gouvernement réécrit
ses pages après publication, et sans ce filtre le LLM repassait sur chaque
version du même conseil (cf. app/versions.py).
"""

import logging
import sys
import time

from sqlalchemy import select

from app.db import SessionLocal
from app.extraction.conseil_ministres import traiter_document
from app.models import Document
from app.versions import ids_versions_de_reference


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    max_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    with SessionLocal() as db:
        docs = db.scalars(
            select(Document)
            .where(
                Document.type_doc == "cr_conseil",
                Document.date_structuration.is_(None),
                Document.id.in_(ids_versions_de_reference()),
            )
            .order_by(Document.date_publication.desc().nulls_last())
            .limit(max_docs)
        ).all()
        if not docs:
            print("Aucun compte rendu en attente de structuration.")
            return 0
        total_d = total_n = echecs = 0
        for i, doc in enumerate(docs):
            if i:
                time.sleep(1.5)  # politesse tier gratuit Mistral (~1 req/s)
            try:
                d, n = traiter_document(db, doc)
            except Exception:  # noqa: BLE001 — un CR en échec ne doit pas arrêter le backfill
                logging.exception("Échec sur le document %s — on continue", doc.id)
                db.rollback()
                echecs += 1
                continue
            total_d += d
            total_n += n
        print(
            f"{len(docs)} document(s) traité(s) : {total_d} décision(s) et "
            f"{total_n} nomination(s) extraites (à valider dans /admin)."
            + (f" {echecs} échec(s) à retraiter." if echecs else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
