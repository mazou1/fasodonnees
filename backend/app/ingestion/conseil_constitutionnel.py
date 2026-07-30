"""Conseil constitutionnel (conseil-constitutionnel.gov.bf) - jurisprudence.

Le Conseil publie ses **décisions, avis et ordonnances** en PDF, regroupés par
année sous la rubrique « Jurisprudence » : conformité des lois et des traités à
la Constitution, contentieux électoral, exceptions d'inconstitutionnalité,
prestations de serment. C'est la seule source publique de la jurisprudence
constitutionnelle burkinabè.

Site TYPO3. Chaque publication est un bloc « frame-type-uploads » :

    <header class="frame-header">
      <h2 class="element-header"><span>OBJET DE LA DÉCISION</span></h2>
      <h3 class="element-subheader"><span>précision</span></h3>
    </header>
    <ul class="media-list">… <a href="/fileadmin/user_upload/decision_n__2026-18_….pdf">

Le titre du bloc porte l'objet réel (« conformité à la constitution de l'accord
de prêt… »), le lien ne porte qu'un nom de fichier : on prend les deux.

Les URL des pages annuelles sont irrégulières (`/decisions-et-avis-2020`,
`/juriste-prudence-1/decisions`, `/juriste-prudence-1/titre-par-defaut`…) : on
les **découvre depuis le menu** de la page d'accueil plutôt que de les
construire, pour ne pas casser au prochain millésime.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from app.extraction.pdf import extraire_texte
from app.ingestion.base import Collector
from app.stockage import stockage

logger = logging.getLogger(__name__)

RACINE = "https://www.conseil-constitutionnel.gov.bf"

# « Décisions, Avis et Ordonnances 2026 », « Décisions et avis 2019 »…
RE_PAGE_ANNUELLE = re.compile(r"d[ée]cisions?\b.*\b(19|20)\d{2}\b", re.IGNORECASE)
RE_ANNEE = re.compile(r"\b((?:19|20)\d{2})\b")

# Deux façons de référencer une même décision, souvent dans le même millésime :
#   « décision n°2026-18 »       → l'année est dans la référence
#   « décision n°22 du 18 déc. » → l'année vient du contexte (date ou page)
# NB : pas de `\b` en fin de motif - dans « 2026-06_du_17_fev », l'underscore
# est un caractère de mot, donc il n'y a pas de frontière après le « 6 ».
RE_REF_ANNEE = re.compile(r"((?:19|20)\d{2})\s*[-–_]\s*0*(\d{1,3})(?!\d)")
RE_REF_NUMERO = re.compile(r"num[ée]ro\s*0*(\d{1,3})(?!\d)", re.IGNORECASE)
RE_REF_SIMPLE = re.compile(r"n[°ºo]?\s*_*\s*0*(\d{1,3})(?![\d\-–])", re.IGNORECASE)

# Le site abrège librement les mois (« oct », « fev », « déc »)
MOIS = {
    "janvier": 1, "janv": 1, "jan": 1,
    "fevrier": 2, "février": 2, "fev": 2, "fév": 2,
    "mars": 3, "mar": 3,
    "avril": 4, "avr": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7, "juil": 7, "jul": 7,
    "aout": 8, "août": 8,
    "septembre": 9, "sept": 9, "sep": 9,
    "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11,
    "decembre": 12, "décembre": 12, "dec": 12, "déc": 12,
}
RE_DATE = re.compile(
    r"du[_\s]+(\d{1,2})[_\s]+([a-zéûôàA-ZÉÛÔÀ]+)\.?[_\s]*((?:19|20)\d{2})?"
)

NATURES = (
    ("avis", "avis_constitutionnel"),
    ("ordonnance", "ordonnance_constitutionnelle"),
    ("decision", "decision_constitutionnelle"),
    ("décision", "decision_constitutionnelle"),
    ("decison", "decision_constitutionnelle"),  # coquille présente sur le site
)


def nature(titre: str, nom_fichier: str) -> str:
    """Décision, avis ou ordonnance - la rubrique mélange les trois.

    La nature se lit au DÉBUT du libellé, pas n'importe où : « Avis sur le
    projet d'ordonnance… » est un avis, pas une ordonnance. Les confondre
    donnerait à un simple avis la portée d'une décision.
    """
    for source in (titre, nom_fichier):
        tete = re.sub(r"^[\s_«\"'\-]+", "", (source or "")).lower()
        for prefixe, valeur in NATURES:
            if tete.startswith(prefixe):
                return valeur
    return "decision_constitutionnelle"


def reference(titre: str, nom_fichier: str, annee_contexte: int | None = None) -> str | None:
    """Référence normalisée « 2026-18 », depuis le titre ou le nom de fichier."""
    for source in (titre, nom_fichier):
        m = RE_REF_ANNEE.search(source or "")
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}"
    if annee_contexte:
        for source in (titre, nom_fichier):
            m = RE_REF_NUMERO.search(source or "") or RE_REF_SIMPLE.search(source or "")
            if m:
                return f"{annee_contexte}-{int(m.group(1)):02d}"
    return None


def date_publication(titre: str, nom_fichier: str, annee_page: int | None) -> date | None:
    """Date de la décision, lue dans le nom de fichier ou dans le titre.

    Les deux la portent selon les millésimes (« _du_10_juin_2026.pdf »,
    « Décision numéro 020/CC du 24 Octobre 2025 »). L'année manque parfois :
    celle de la page annuelle prend alors le relais. Sans jour ET mois
    exploitables, on renvoie None - mieux vaut une date absente qu'inventée.
    """
    for source in (nom_fichier, titre):
        m = RE_DATE.search((source or "").replace("-", "_"))
        if not m:
            continue
        mois = MOIS.get(m.group(2).lower())
        if not mois:
            continue
        an = int(m.group(3)) if m.group(3) else annee_page
        if not an:
            continue
        try:
            return date(an, mois, int(m.group(1)))
        except ValueError:
            continue
    return None


def publications_de_la_page(html: str, url_page: str) -> list[dict]:
    """Les blocs (titre, sous-titre, PDF) d'une page annuelle."""
    tree = HTMLParser(html)
    annee_page = None
    m = RE_ANNEE.search(url_page)
    if m:
        annee_page = int(m.group(1))

    publications = []
    for bloc in tree.css("div.frame-type-uploads"):
        entete = bloc.css_first("header .element-header span")
        sous = bloc.css_first("header .element-subheader span")
        titre = entete.text(strip=True) if entete else ""
        sous_titre = sous.text(strip=True) if sous else ""
        for lien in bloc.css("a"):
            href = lien.attributes.get("href", "")
            if not href.lower().endswith(".pdf"):
                continue
            nom_fichier = href.rsplit("/", 1)[-1]
            quand = date_publication(titre, nom_fichier, annee_page)
            publications.append(
                {
                    "url": urljoin(RACINE, href),
                    "titre": titre or nom_fichier,
                    "sous_titre": sous_titre or None,
                    "nom_fichier": nom_fichier,
                    "type_doc": nature(titre, nom_fichier),
                    # l'année de la décision prime sur celle de la page (une
                    # page annuelle publie parfois un texte de fin d'année
                    # précédente)
                    "reference": reference(
                        titre, nom_fichier, quand.year if quand else annee_page
                    ),
                    "date": quand,
                    "annee_page": annee_page,
                }
            )
    return publications


def pages_annuelles(html_accueil: str) -> list[str]:
    """URL des pages annuelles, découvertes dans le menu « Jurisprudence »."""
    tree = HTMLParser(html_accueil)
    vues: dict[str, None] = {}
    for lien in tree.css("a"):
        href = lien.attributes.get("href", "")
        texte = lien.text(strip=True)
        if href and RE_PAGE_ANNUELLE.search(texte):
            vues.setdefault(urljoin(RACINE, href), None)
    return list(vues)


class ConseilConstitutionnelCollector(Collector):
    slug = "conseil_constitutionnel"
    groupe = "institutionnel"
    accueil = RACINE
    # les millésimes anciens ne bougent plus : on ne repart pas de 2011 à chaque
    # passe, seules les pages les plus récentes sont revisitées
    annees_revisitees = 2
    # rattrapage : repasser sur TOUTES les années. Nécessaire au premier
    # remplissage, et après une collecte interrompue - sinon la passe
    # incrémentale ne redescendra jamais chercher les millésimes anciens.
    complet = False

    def collect(self) -> None:
        try:
            accueil = self.get(self.accueil)
        except Exception:
            logger.warning("%s : page d'accueil inaccessible", self.slug)
            return

        pages = pages_annuelles(accueil.text)
        if not pages:
            logger.warning("%s : aucune page annuelle trouvée (structure du site modifiée ?)",
                           self.slug)
            return

        connues = self._urls_connues()
        for url_page in self._pages_a_visiter(pages, connues):
            try:
                page = self.get(url_page)
            except Exception:
                logger.warning("%s : page inaccessible %s", self.slug, url_page)
                continue
            for pub in publications_de_la_page(page.text, url_page):
                if pub["url"] in connues:
                    self.nb_vus += 1
                    continue
                self._archiver(pub)
            self.db.commit()

    def _pages_a_visiter(self, pages: list[str], connues: set[str]) -> list[str]:
        """Toutes les pages au premier passage, les plus récentes ensuite.

        Le corpus ancien est figé ; le revisiter à chaque cadence coûterait une
        quinzaine de requêtes pour rien.
        """
        if self.complet or not connues:
            return pages
        return pages[: self.annees_revisitees]

    def _urls_connues(self) -> set[str]:
        from sqlalchemy import select

        from app.models import Document

        return set(
            self.db.scalars(
                select(Document.url).where(Document.source_id == self.source.id)
            ).all()
        )

    def _archiver(self, pub: dict) -> None:
        try:
            resp = self.get(pub["url"], min_interval=1.5)
        except Exception:
            logger.warning("%s : téléchargement échoué %s", self.slug, pub["url"])
            return
        if not resp.content.startswith(b"%PDF"):
            logger.warning("%s : %s n'est pas un PDF", self.slug, pub["url"])
            return
        fichier, digest = self.archive(resp.content, "pdf")
        with stockage.fichier_local(fichier) as chemin:
            texte, statut = extraire_texte(chemin, ocr=False)
        self.upsert_document(
            url=pub["url"],
            type_doc=pub["type_doc"],
            titre=pub["titre"][:1000],
            date_publication=pub["date"],
            hash_contenu=digest,
            fichier=fichier,
            mime="application/pdf",
            texte_extrait=texte or None,
            statut_extraction=statut,
            meta={
                "reference": pub["reference"],
                "sous_titre": pub["sous_titre"],
                "annee": pub["annee_page"],
                "juridiction": "Conseil constitutionnel",
                # le Conseil publie presque exclusivement des scans : c'est ce
                # marqueur que la passe OCR (app.extraction.ocr_textes) suit
                "pdf_statut": statut,
            },
        )


def main() -> int:
    """Rattrapage manuel : `python -m app.ingestion.conseil_constitutionnel`.

    Repasse sur toutes les années, contrairement à la collecte périodique du
    worker qui ne revisite que les millésimes récents. À lancer au premier
    remplissage, ou après une collecte interrompue.
    """
    import logging as _logging

    from app.db import SessionLocal

    _logging.basicConfig(level=_logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with SessionLocal() as db:
        collecteur = ConseilConstitutionnelCollector(db)
        collecteur.complet = True
        collecteur.run()
        print(f"{collecteur.nb_nouveaux} nouvelle(s) pièce(s), {collecteur.nb_vus} déjà connue(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
