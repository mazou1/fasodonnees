"""ASCE-LC (asce-lc.bf) - Autorité supérieure de contrôle d'État et de lutte
contre la corruption.

L'ASCE-LC est l'organe de contrôle interne de l'État : elle audite les sociétés
publiques et les administrations, instruit les plaintes et dénonciations, suit
les dossiers judiciaires de corruption et collecte les déclarations d'intérêts
et de patrimoine. Ses **rapports d'audit** (SONABHY, SONABEL…) et son rapport
annuel général d'activités sont les documents de redevabilité les plus directs
que publie l'État burkinabè.

Le site est un WordPress à API REST ouverte, donc :

- les **articles** viennent structurés (titre, date, contenu, catégories) ;
- mais l'essentiel est dans les **PDF joints** : l'article annonce l'audit, le
  PDF *est* l'audit. On archive donc les deux, le PDF comme document à part
  entière - c'est lui qui sera cherchable en plein texte.

Les identifiants numériques de catégories WordPress changent si le site est
refondu : on les résout à l'exécution depuis leurs *slugs*, plus stables.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import urljoin, urlparse

from app.extraction.pdf import extraire_texte
from app.ingestion.wordpress import WordPressCollector
from app.stockage import stockage

logger = logging.getLogger(__name__)

# slug de catégorie WordPress → type de document dans notre corpus
TYPES_PAR_CATEGORIE: dict[str, str] = {
    "rapports-daudits-controles": "rapport_controle",
    "audit-et-controle": "rapport_controle",
    "exploitation-de-rapports": "rapport_controle",
    "affaires-judiciaires": "affaire_anticorruption",
    "dossiers-juges": "affaire_anticorruption",
    "dossiers-en-cours-de-jugement": "affaire_anticorruption",
    "dossiers-denquetes-et-dinvestigations": "affaire_anticorruption",
    "liste-des-affaires-et-decisions": "affaire_anticorruption",
    "declaration-d-interet-et-de-patrimoine": "declaration_patrimoine",
    "plaintes-et-denonciations": "plainte_denonciation",
    "denonciations": "plainte_denonciation",
    "denonciations-traitees": "plainte_denonciation",
    "denonciations-validees": "plainte_denonciation",
    "situation-plaintes-et-denonciations": "plainte_denonciation",
}

# priorité quand un article porte plusieurs catégories : un rapport d'audit
# publié aussi en « actualité » reste un rapport d'audit
PRIORITE = ("rapport_controle", "affaire_anticorruption", "declaration_patrimoine",
            "plainte_denonciation")

RE_PDF = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)


def type_du_post(slugs: list[str]) -> str | None:
    """Type de document d'un article, d'après ses catégories.

    None si l'article ne relève d'aucune rubrique de contrôle : la source
    publie aussi beaucoup d'actualités institutionnelles (séminaires,
    audiences) qui n'ont pas leur place dans le corpus documentaire.
    """
    types = {TYPES_PAR_CATEGORIE[s] for s in slugs if s in TYPES_PAR_CATEGORIE}
    for candidat in PRIORITE:
        if candidat in types:
            return candidat
    return None


def pdfs_du_contenu(html: str, base_url: str) -> list[str]:
    """URL des PDF joints, dédoublonnées en gardant l'ordre de l'article."""
    vues: dict[str, None] = {}
    for href in RE_PDF.findall(html or ""):
        vues.setdefault(urljoin(base_url, href), None)
    return list(vues)


class AsceLcCollector(WordPressCollector):
    slug = "asce_lc"
    groupe = "institutionnel"
    api_base = "https://www.asce-lc.bf/wp-json/wp/v2"
    # petites pages volontairement : la classe de base ne commite qu'en fin de
    # page, et un article peut porter plusieurs rapports d'audit de dizaines de
    # Mo. Une interruption ne doit pas coûter tout le lot.
    par_page = 10

    def __init__(self, db):
        super().__init__(db)
        self._slugs_par_id: dict[int, str] = {}
        self._post_courant: dict | None = None
        self._urls_connues: set[str] | None = None

    # ---- résolution des catégories ----

    def _resoudre_categories(self) -> str | None:
        """slugs → identifiants WordPress, et la liste à interroger."""
        try:
            resp = self.get(f"{self.api_base}/categories?per_page=100&_fields=id,slug")
        except Exception:
            logger.warning("%s : catégories illisibles, collecte abandonnée", self.slug)
            return None
        self._slugs_par_id = {c["id"]: c["slug"] for c in resp.json()}
        ids = [i for i, s in self._slugs_par_id.items() if s in TYPES_PAR_CATEGORIE]
        if not ids:
            logger.warning(
                "%s : aucune catégorie de contrôle trouvée (site refondu ?)", self.slug
            )
            return None
        return ",".join(str(i) for i in sorted(ids))

    def collect(self) -> None:
        categories = self._resoudre_categories()
        if not categories:
            return
        self.categories = categories
        super().collect()

    # ---- traitement d'un article ----

    def type_doc_pour(self, titre: str) -> str:
        """Le type vient des catégories de l'article, pas de son titre.

        `WordPressCollector` n'expose que le titre à ce point du traitement :
        on lit l'article courant, mémorisé par `_traiter_post`.
        """
        slugs = [
            self._slugs_par_id.get(c, "")
            for c in (self._post_courant or {}).get("categories", [])
        ]
        return type_du_post(slugs) or "communique"

    def _traiter_post(self, post: dict) -> bool:
        self._post_courant = post
        slugs = [self._slugs_par_id.get(c, "") for c in post.get("categories", [])]
        if type_du_post(slugs) is None:
            # l'API a pu élargir la sélection : on ne garde que le contrôle
            self.nb_vus += 1
            return False

        nouveau = super()._traiter_post(post)
        html = post.get("content", {}).get("rendered", "") or ""
        for url_pdf in pdfs_du_contenu(html, post.get("link", "") or self.api_base):
            if url_pdf in self._connues():
                self.nb_vus += 1  # rapport déjà archivé : ne pas le retélécharger
                continue
            self._archiver_pdf(url_pdf, post, slugs)
            self._connues().add(url_pdf)
        # les rapports pèsent lourd : on sécurise article par article plutôt que
        # de tout perdre si la passe est interrompue
        self.db.commit()
        return nouveau

    def _connues(self) -> set[str]:
        if self._urls_connues is None:
            from sqlalchemy import select

            from app.models import Document

            self._urls_connues = set(
                self.db.scalars(
                    select(Document.url).where(Document.source_id == self.source.id)
                ).all()
            )
        return self._urls_connues

    def _archiver_pdf(self, url_pdf: str, post: dict, slugs: list[str]) -> None:
        """Le rapport lui-même : c'est la pièce qui compte, pas son annonce.

        Le serveur coupe la connexion sur ses plus gros fichiers (constaté sur
        les annexes SONABEL, ~16 Mo - `curl` échoue pareil, ce n'est pas notre
        client). Après les trois tentatives de `get()`, on renonce et on
        journalise : comme aucun document n'est créé, l'URL reste absente des
        connues et la passe suivante réessaiera d'elle-même.
        """
        try:
            resp = self.get(url_pdf, min_interval=1.5)
        except Exception:
            logger.warning("%s : téléchargement échoué %s", self.slug, url_pdf)
            return
        if not resp.content.startswith(b"%PDF"):
            return
        fichier, digest = self.archive(resp.content, "pdf")
        with stockage.fichier_local(fichier) as chemin:
            texte, statut = extraire_texte(chemin, ocr=False)
        pub: date | None = None
        if post.get("date"):
            pub = date.fromisoformat(post["date"][:10])
        nom = urlparse(url_pdf).path.rsplit("/", 1)[-1]
        self.upsert_document(
            url=url_pdf,
            type_doc=type_du_post(slugs) or "rapport_controle",
            titre=nom[:1000],
            date_publication=pub,
            hash_contenu=digest,
            fichier=fichier,
            mime="application/pdf",
            texte_extrait=texte or None,
            statut_extraction=statut,
            meta={
                "piece_jointe_de": post.get("link"),
                "wp_id": post.get("id"),
                "categories": [s for s in slugs if s],
                "organisme": "ASCE-LC",
                # suivi par la passe OCR quand le rapport est un scan
                "pdf_statut": statut,
            },
        )
