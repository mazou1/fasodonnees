"""Téléchargement des PDF des textes juridiques (Légiburkina).

Le champ `url` publié par Légiburkina est cassé (il renvoie la coquille de
l'application Angular) ; le vrai endpoint, retrouvé dans leur bundle, est
GET /api/documents/download/{fileName} - le fileName étant la fin de l'URL
après « sggcm ». On télécharge, archive, et remplit texte_extrait avec le
texte natif du PDF (les scans sont marqués « scan » pour une passe OCR
ultérieure). La description courte d'origine est préservée dans
meta['description'] pour l'affichage.

Usage : python -m app.extraction.pdf_textes [max_docs]
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time
from urllib.parse import quote, unquote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.extraction.pdf import extraire_texte
from app.models import Document
from app.stockage import stockage

logger = logging.getLogger(__name__)

ENDPOINT = "https://www.legiburkina.gov.bf/api/documents/download/"


def _nom_fichier(url: str) -> str | None:
    if "sggcm" in url:
        nom = url.rsplit("sggcm", 1)[-1]
    else:
        nom = url.rsplit("/", 1)[-1]
    return nom or None


def traiter(db: Session, doc: Document, client: httpx.Client) -> str:
    """Renvoie le statut : ok | scan | echec_source | echec."""
    meta = dict(doc.meta or {})
    meta.setdefault("description", doc.texte_extrait)

    nom = _nom_fichier(doc.url)
    if not nom:
        meta["pdf_statut"] = "echec"
        doc.meta = meta
        db.commit()
        return "echec"

    # l'URL publiée est déjà percent-encodée : on normalise pour éviter le double encodage
    resp = client.get(ENDPOINT + quote(unquote(nom)))
    if resp.status_code >= 400:
        # 500 « NonUniqueResult » = doublon côté Légiburkina - irrécupérable de notre côté
        meta["pdf_statut"] = "echec_source"
        meta["pdf_erreur"] = resp.status_code
        doc.meta = meta
        db.commit()
        return "echec_source"

    digest = hashlib.sha256(resp.content).hexdigest()
    annee = str(doc.date_publication.year) if doc.date_publication else "inconnue"
    rel = f"legiburkina/pdf/{annee}/{digest[:16]}.pdf"
    stockage.ecrire(rel, resp.content)

    with stockage.fichier_local(rel) as chemin:
        texte, statut = extraire_texte(chemin, ocr=False)
    meta["pdf_statut"] = statut
    doc.meta = meta
    doc.fichier = rel
    if statut == "ok":
        doc.texte_extrait = texte
        doc.statut_extraction = "ok"
    # « scan » : on garde la description en texte_extrait, l'OCR viendra plus tard
    db.commit()
    return statut


def main(max_docs: int | None = None) -> int:
    # `max_docs` permet au worker d'appeler cette passe avec un budget borné
    # sans passer par la ligne de commande (cf. app/ingestion/scheduler.py)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if max_docs is None:
        max_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    client = httpx.Client(
        headers={"User-Agent": settings.user_agent}, timeout=90, follow_redirects=True
    )
    with SessionLocal() as db:
        docs = db.scalars(
            select(Document)
            .where(
                Document.meta.has_key("legi_id"),
                ~Document.meta.has_key("pdf_statut"),
            )
            .order_by(Document.date_publication.desc().nulls_last())
            .limit(max_docs)
        ).all()
        if not docs:
            print("Aucun texte juridique en attente de téléchargement.")
            return 0
        stats: dict[str, int] = {}
        for i, doc in enumerate(docs):
            if i:
                time.sleep(1.0)  # politesse envers legiburkina.gov.bf
            try:
                statut = traiter(db, doc, client)
            except Exception:  # noqa: BLE001 - un PDF en échec ne doit pas arrêter le lot
                logging.exception("Échec sur le document %s - on continue", doc.id)
                db.rollback()
                statut = "echec"
            stats[statut] = stats.get(statut, 0) + 1
            if (i + 1) % 100 == 0:
                logger.info("%d/%d - %s", i + 1, len(docs), stats)
        print(f"{len(docs)} document(s) : {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
