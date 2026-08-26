"""Collecteur générique pour sites WordPress via l'API REST wp-json.

Beaucoup de sites institutionnels burkinabè (gouvernement.gov.bf, …) sont
des WordPress avec l'API REST ouverte - bien plus robuste que le scraping
HTML : titres, dates et contenu arrivent structurés, et la pagination est
native (en-tête X-WP-TotalPages).
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import String, func, select

from app.extraction.texte import html_vers_texte
from app.ingestion.base import Collector
from app.models import Document

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

    def url_deja_connue(self, wp_id) -> str | None:
        """L'adresse sous laquelle cette publication est DÉJÀ archivée.

        L'identité d'un document repose sur son URL (cf. base.upsert_document),
        or WordPress en change : le 22 août 2026, gouvernement.gov.bf est passé
        des permaliens lisibles à « /?p=19635 », et le site a été recollecté en
        entier sous ces nouvelles adresses - 3 283 documents en quatre jours,
        les 1 744 actualités du fonds en double, et l'extraction LLM repartie
        sur des articles déjà traités.

        L'identifiant du billet, lui, ne bouge pas. On s'y raccroche pour
        continuer de VERSIONNER sous l'adresse d'origine plutôt que de repartir
        de zéro. L'adresse d'origine reste par ailleurs valable : le site la
        redirige.
        """
        if wp_id is None:
            return None
        # cast explicite : PostgreSQL rend du texte là où SQLite rend l'entier
        # natif, et la comparaison ne rapprocherait alors jamais rien
        cle = func.cast(Document.meta["wp_id"].as_string(), String)
        return self.db.scalars(
            select(Document.url)
            .where(Document.source_id == self.source.id, cle == str(wp_id))
            .order_by(Document.id)
            .limit(1)
        ).first()

    def _traiter_post(self, post: dict) -> bool:
        html = post.get("content", {}).get("rendered", "") or ""
        titre = html_vers_texte(post.get("title", {}).get("rendered", "") or "")
        lien = self.url_deja_connue(post.get("id")) or post.get("link", "")
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
