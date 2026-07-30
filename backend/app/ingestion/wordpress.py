"""Collecteur générique pour sites WordPress via l'API REST wp-json.

Beaucoup de sites institutionnels burkinabè (gouvernement.gov.bf, …) sont
des WordPress avec l'API REST ouverte - bien plus robuste que le scraping
HTML : titres, dates et contenu arrivent structurés, et la pagination est
native (en-tête X-WP-TotalPages).
"""

from __future__ import annotations

import logging
from datetime import date

from app.extraction.texte import html_vers_texte
from app.ingestion.base import Collector

logger = logging.getLogger(__name__)


class WordPressCollector(Collector):
    api_base: str  # ex: https://gouvernement.gov.bf/wp-json/wp/v2
    categories: str | None = None  # ids de catégories WP, ex: "23"
    type_doc: str = "communique"

    def type_doc_pour(self, titre: str) -> str:
        """Type du document selon son titre - surchargé par les collecteurs."""
        return self.type_doc
    par_page: int = 20

    def collect(self) -> None:
        page = 1
        total_pages = 1
        while page <= total_pages:
            url = f"{self.api_base}/posts?per_page={self.par_page}&page={page}"
            if self.categories:
                url += f"&categories={self.categories}"
            resp = self.get(url)
            total_pages = int(resp.headers.get("X-WP-TotalPages", "1"))
            posts = resp.json()
            nouveaux_page = 0
            for post in posts:
                if self._traiter_post(post):
                    nouveaux_page += 1
            self.db.commit()
            logger.info("%s : page %d/%d, %d nouveaux", self.slug, page, total_pages, nouveaux_page)
            # Posts triés par date décroissante : une page sans nouveauté
            # signifie que la suite est déjà en base.
            if nouveaux_page == 0:
                break
            page += 1

    def _traiter_post(self, post: dict) -> bool:
        html = post.get("content", {}).get("rendered", "") or ""
        titre = html_vers_texte(post.get("title", {}).get("rendered", "") or "")
        lien = post.get("link", "")
        if not lien:
            return False
        pub: date | None = None
        if post.get("date"):
            pub = date.fromisoformat(post["date"][:10])
        fichier, digest = self.archive(html.encode(), "html")
        doc = self.upsert_document(
            url=lien,
            type_doc=self.type_doc_pour(titre),
            titre=titre or None,
            date_publication=pub,
            hash_contenu=digest,
            fichier=fichier,
            mime="text/html",
            texte_extrait=html_vers_texte(html) or None,
            statut_extraction="ok",
            meta={"wp_id": post.get("id"), "wp_modified": post.get("modified")},
        )
        return doc is not None
