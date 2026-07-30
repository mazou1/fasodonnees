"""Légiburkina (SGG-CM) - textes juridiques via l'API JSON de la plateforme Angular.

Endpoints découverts le 2026-07-10 (aucune authentification requise) :
- POST /api/documents/search-mot-cle?size=N&page=P  (corps {}) → métadonnées
  paginées : référence, type (DECRET/LOI/ARRETE…), secteur, description,
  date, URL du PDF, et le Journal officiel de publication (numéro, date,
  lien jobf.gov.bf) - le recoupement texte ↔ JO est fourni par la source.

On ingère les MÉTADONNÉES (la description sert de texte interrogeable) ;
le téléchargement des PDF des textes est un chantier ultérieur.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import date

from app.ingestion.base import Collector

logger = logging.getLogger(__name__)

TYPES_CONNUS = {
    "DECRET": "decret",
    "LOI": "loi",
    "ARRETE": "arrete",
    "ORDONNANCE": "ordonnance",
    "CHARTE": "charte",
    "CONSTITUTION": "constitution",
}


class LegiburkinaCollector(Collector):
    slug = "legiburkina"
    groupe = "institutionnel"
    api = "https://www.legiburkina.gov.bf/api/documents/search-mot-cle"
    par_page = 50

    def collect(self) -> None:
        page = 0
        while True:
            resp = self.client.post(
                f"{self.api}?size={self.par_page}&page={page}",
                json={},
                timeout=60,
            )
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            for item in items:
                self._traiter(item)
            self.db.commit()
            if page % 10 == 0:
                logger.info("%s : page %d, %d nouveaux cumulés", self.slug, page, self.nb_nouveaux)
            page += 1
            time.sleep(1.0)  # politesse (le throttle du client de base ne couvre que get())

    def _traiter(self, item: dict) -> None:
        libelle = ((item.get("type") or {}).get("libelle") or "").upper()
        type_doc = TYPES_CONNUS.get(libelle, "texte_juridique")
        reference = item.get("reference") or ""
        description = item.get("description") or ""
        titre = f"{libelle or 'TEXTE'} {reference}".strip()[:1000]
        url = item.get("url") or f"https://www.legiburkina.gov.bf/document/{item.get('id')}"
        pub: date | None = None
        if item.get("date"):
            pub = date.fromisoformat(str(item["date"])[:10])
        jo = item.get("journalOfficiel") or {}
        digest = hashlib.sha256(
            f"{item.get('id')}|{item.get('lastModifiedDate')}".encode()
        ).hexdigest()
        self.upsert_document(
            url=url,
            type_doc=type_doc,
            titre=titre,
            date_publication=pub,
            hash_contenu=digest,
            mime="application/pdf",
            texte_extrait=description or None,
            statut_extraction="na",  # métadonnées seules - PDF non téléchargé à ce stade
            meta={
                "legi_id": item.get("id"),
                "reference": reference,
                "secteur": (item.get("secteur") or {}).get("libelle"),
                "jo_numero": jo.get("numero"),
                "jo_date": str(jo.get("dateJournal") or "")[:10] or None,
                "jo_url": jo.get("url"),
                "taille_pdf": item.get("fileSize"),
            },
        )
