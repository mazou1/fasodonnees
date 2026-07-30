"""DGCMEF (dgcmef.gov.bf) - Quotidien des Marchés Publics.

La Direction générale du contrôle des marchés publics publie chaque jour un
« Quotidien des Marchés Publics » : le journal officiel de la commande publique
(avis d'appels d'offres et surtout SYNTHÈSE DES RÉSULTATS - attributions avec
autorité contractante, objet, attributaire et montant). PDF en texte natif.

Le site (Drupal) dépublie au fil du temps : on archive chaque numéro et on en
extrait le texte intégral pour le rendre cherchable. L'extraction structurée
des marchés individuels (attributaire/montant par contrat) est un chantier
ultérieur - ici on archive et on indexe le plein texte.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date
from urllib.parse import unquote, urljoin

from selectolax.parser import HTMLParser

from app.extraction.pdf import extraire_texte
from app.ingestion.base import Collector
from app.stockage import stockage

logger = logging.getLogger(__name__)

MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
RE_NUMERO = re.compile(r"n[°ºo]?\s*0*(\d{3,5})", re.IGNORECASE)
# la date d'édition suit le numéro : « N° 4442 - Lundi 13 juillet 2026 »
RE_DATE = re.compile(
    r"N[°ºo]?\s*\d{3,5}\s*[–\-]\s*(?:\w+\s+)?(\d{1,2})\s+([A-Za-zéûôà]+)\s+(\d{4})",
    re.IGNORECASE,
)


class DgcmefCollector(Collector):
    slug = "dgcmef"
    groupe = "institutionnel"
    listing = "https://www.dgcmef.gov.bf/fr/revue-de-march-s-pour-tous"
    max_pages = 1  # pages du listing par passe (≈18 numéros récents) ; quotidien

    def collect(self) -> None:
        vus: set[str] = set()
        for page in range(self.max_pages):
            url = self.listing if page == 0 else f"{self.listing}?page={page}"
            try:
                resp = self.get(url)
            except Exception:
                logger.warning("%s : listing page %d inaccessible", self.slug, page)
                break
            tree = HTMLParser(resp.text)
            liens = [
                urljoin(url, a.attributes.get("href", ""))
                for a in tree.css("a[href]")
                if (a.attributes.get("href") or "").lower().endswith(".pdf")
                and "quotidien" in (a.attributes.get("href") or "").lower()
            ]
            for pdf_url in liens:
                if pdf_url not in vus:
                    vus.add(pdf_url)
                    self._traiter(pdf_url)
            self.db.commit()
            time.sleep(1.0)

    def _date_et_numero(self, texte: str, url: str) -> tuple[str | None, date | None]:
        entete = texte[:500]
        numero = RE_NUMERO.search(unquote(url).rsplit("/", 1)[-1]) or RE_NUMERO.search(entete)
        num = numero.group(1) if numero else None
        pub = None
        m = RE_DATE.search(entete)
        if m and m.group(2).lower() in MOIS:
            try:
                pub = date(int(m.group(3)), MOIS[m.group(2).lower()], int(m.group(1)))
            except ValueError:
                pub = None
        return num, pub

    def _traiter(self, pdf_url: str) -> None:
        # dédup rapide avant de télécharger 5 Mo : url déjà en base ?
        from sqlalchemy import select

        from app.models import Document

        deja = self.db.scalar(
            select(Document.id).where(
                Document.source_id == self.source.id, Document.url == pdf_url
            )
        )
        if deja is not None:
            self.nb_vus += 1
            return
        try:
            resp = self.get(pdf_url, min_interval=1.5)
        except Exception:
            logger.warning("%s : téléchargement échoué %s", self.slug, pdf_url)
            return
        if not resp.content.startswith(b"%PDF"):
            return
        fichier, digest = self.archive(resp.content, "pdf")
        with stockage.fichier_local(fichier) as chemin:
            texte, statut = extraire_texte(chemin, ocr=False)
        num, pub = self._date_et_numero(texte, pdf_url)
        titre = f"Quotidien des Marchés Publics n°{num}" if num else "Quotidien des Marchés Publics"
        doc = self.upsert_document(
            url=pdf_url,
            type_doc="marche_public",
            titre=titre,
            date_publication=pub,
            hash_contenu=digest,
            fichier=fichier,
            mime="application/pdf",
            texte_extrait=texte or None,
            statut_extraction="ok" if statut == "ok" else "scan",
        )
        logger.info("%s : %s (%s)", self.slug, titre, pub or "date ?")
        # extraction déterministe des marchés attribués (a_valider) - pas de LLM
        if doc is not None:
            self.db.commit()  # persiste l'archivage d'abord (doc.id affecté)
            try:
                from app.extraction.marches import traiter_document

                n, republications = traiter_document(self.db, doc)
                logger.info(
                    "%s : %d marché(s) attribué(s) extraits de %s"
                    " (%d republication(s) d'un numéro précédent ignorée(s))",
                    self.slug, n, titre, republications,
                )
            except Exception:
                logger.exception("%s : extraction des marchés échouée pour %s", self.slug, titre)
                self.db.rollback()  # le numéro reste archivé, seuls ses marchés sont annulés
