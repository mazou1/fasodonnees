"""Comptes rendus du Conseil des ministres - gouvernement.gov.bf.

Le site est un WordPress avec API REST ouverte ; la catégorie 23
(« Compte rendu », vérifiée le 2026-07-10) contient les CR officiels.
Chaîne complète : collecte → texte → extraction LLM des nominations
(app.extraction.nominations) → validation humaine → annuaire (app.annuaire).
"""

from __future__ import annotations

import re

from app.ingestion.wordpress import WordPressCollector

# traductions en langues nationales publiées à côté de la version française -
# archivées mais typées à part (l'extraction LLM sur ces textes divague)
LANGUES_NATIONALES = re.compile(
    r"GULI?MANCEMA|MOOR[EÉ]|FULFULD[EÉ]|DIOULA|JULA", re.IGNORECASE
)


# code stable → ce que le titre de la source peut contenir
LANGUES = {
    "moore": (r"MOOR[EÉ]", "Mooré"),
    "fulfulde": (r"FULFULD[EÉ]", "Fulfuldé"),
    "dioula": (r"DIOULA|JULA", "Dioula"),
    "gulmancema": (r"GULI?MANCEMA", "Gulmancéma"),
}


def langue_nationale(titre: str | None) -> str | None:
    """Code de la langue d'une traduction, lu dans son titre."""
    for code, (motif, _libelle) in LANGUES.items():
        if re.search(motif, titre or "", re.IGNORECASE):
            return code
    return None


def lien_pdf(html: str) -> str | None:
    """Le PDF vers lequel renvoie une page « Télécharger »."""
    from selectolax.parser import HTMLParser

    for a in HTMLParser(html).css("a[href]"):
        href = a.attributes.get("href") or ""
        if ".pdf" in href.lower():
            return href
    return None


def completer_traductions(db) -> int:
    """Renseigne langue et PDF sur les traductions archivées avant ce champ.

    Une traduction est une page WordPress réduite à un lien « Télécharger » :
    sans l'adresse du PDF, la plateforme n'a rien à proposer au lecteur.
    """
    from sqlalchemy import select

    from app.models import Document
    from app.stockage import stockage

    faits = 0
    docs = db.scalars(select(Document).where(Document.type_doc == "cr_conseil_traduction"))
    for doc in docs:
        meta = dict(doc.meta or {})
        if meta.get("langue") and "pdf_url" in meta:
            continue
        meta["langue"] = langue_nationale(doc.titre)
        html = ""
        if doc.fichier and stockage.existe(doc.fichier):
            html = stockage.lire(doc.fichier).decode(errors="replace")
        meta["pdf_url"] = lien_pdf(html)
        doc.meta = meta
        faits += 1
    db.commit()
    return faits


class ConseilMinistresCollector(WordPressCollector):
    slug = "conseil_ministres"
    groupe = "cm"  # cadence hebdomadaire propre (mercredi), distincte du quotidien institutionnel
    api_base = "https://gouvernement.gov.bf/wp-json/wp/v2"
    categories = "23"  # « Compte rendu » (parent « Conseil des ministres »)
    type_doc = "cr_conseil"

    def type_doc_pour(self, titre: str) -> str:
        if LANGUES_NATIONALES.search(titre or ""):
            return "cr_conseil_traduction"
        return self.type_doc

    def meta_supplementaire(self, titre: str, html: str) -> dict:
        langue = langue_nationale(titre)
        if not langue:
            return {}
        return {"langue": langue, "pdf_url": lien_pdf(html)}


if __name__ == "__main__":
    from app.db import SessionLocal

    with SessionLocal() as _db:
        print(f"{completer_traductions(_db)} traduction(s) complétée(s)")
