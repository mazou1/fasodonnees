"""Récupération des PDF des comptes rendus « coquilles ».

Les CR anciens (2022-2024 surtout) sont publiés sur gouvernement.gov.bf comme
pages quasi vides avec un lien « Télécharger » vers un PDF. Ce module suit le
lien depuis le HTML archivé, télécharge et archive le PDF, en extrait le texte
(pdfplumber + OCR fra en secours) et remet date_structuration à NULL pour que
l'extraction LLM retraite le document.

Les traductions en langues nationales sont exclues : leur contenu duplique la
version française déjà traitée.

Usage : python -m app.extraction.pdf_cr [max_docs]
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.extraction.pdf import extraire_texte
from app.models import Document
from app.stockage import stockage

logger = logging.getLogger(__name__)

TEXTE_MINIMUM = 500  # même seuil que l'extraction : en dessous, le CR est une coquille
LANGUES_NATIONALES = r"(GULIMANCEMA|MOORE|MOORÉ|FULFULDE|DIOULA|JULA)"


def _lien_pdf(doc: Document) -> str | None:
    if not doc.fichier:
        return None
    if not stockage.existe(doc.fichier):
        logger.warning("Archive HTML introuvable pour le document %s : %s", doc.id, doc.fichier)
        return None
    tree = HTMLParser(stockage.lire(doc.fichier).decode(errors="replace"))
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        if ".pdf" in href.lower():
            return href
    return None


def _archiver_pdf(contenu: bytes, annee: str) -> tuple[str, str]:
    digest = hashlib.sha256(contenu).hexdigest()
    rel = f"conseil_ministres/pdf/{annee}/{digest[:16]}.pdf"
    stockage.ecrire(rel, contenu)
    return rel, digest


def traiter(db: Session, doc: Document, client: httpx.Client) -> str:
    """Renvoie le statut : ok | ocr | aucun_lien | echec."""
    url = _lien_pdf(doc)
    meta = dict(doc.meta or {})
    if url is None:
        meta["pdf_statut"] = "aucun_lien"
        doc.meta = meta
        db.commit()
        return "aucun_lien"

    resp = client.get(url)
    resp.raise_for_status()
    annee = str(doc.date_publication.year) if doc.date_publication else "inconnue"
    rel, _digest = _archiver_pdf(resp.content, annee)

    with stockage.fichier_local(rel) as chemin:
        texte, statut = extraire_texte(chemin)
    meta.update({"pdf_url": url, "pdf_statut": statut, "html_fichier": doc.fichier})
    doc.meta = meta
    doc.fichier = rel
    doc.mime = "application/pdf"
    if statut != "echec" and len(texte) >= 200:
        doc.texte_extrait = texte
        doc.statut_extraction = statut
        doc.date_structuration = None  # → l'extraction LLM retraitera ce document
    else:
        doc.statut_extraction = "echec"
        statut = "echec"
    db.commit()
    return statut


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    max_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    client = httpx.Client(
        headers={"User-Agent": settings.user_agent}, timeout=60, follow_redirects=True
    )
    with SessionLocal() as db:
        docs = db.scalars(
            select(Document)
            .where(
                Document.type_doc == "cr_conseil",
                func.length(func.coalesce(Document.texte_extrait, "")) < TEXTE_MINIMUM,
                ~Document.titre.op("~*")(LANGUES_NATIONALES),
                ~Document.meta.has_key("pdf_statut"),
            )
            .order_by(Document.date_publication.desc().nulls_last())
            .limit(max_docs)
        ).all()
        if not docs:
            print("Aucune coquille CR à traiter.")
            return 0
        stats: dict[str, int] = {}
        for i, doc in enumerate(docs):
            if i:
                time.sleep(1.0)  # politesse envers gouvernement.gov.bf
            try:
                statut = traiter(db, doc, client)
            except Exception:  # noqa: BLE001 - un PDF en échec ne doit pas arrêter le lot
                logging.exception("Échec sur le document %s - on continue", doc.id)
                db.rollback()
                statut = "echec"
            stats[statut] = stats.get(statut, 0) + 1
            logger.info("Document %s (%s) : %s", doc.id, doc.date_publication, statut)
        print(f"{len(docs)} document(s) : {stats}")
        print("Relancer ensuite : python -m app.extraction.run 250")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
