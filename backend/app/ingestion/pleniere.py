"""Comptes rendus de séance plénière de l'Assemblée législative du peuple.

La liste des députés d'assembleenationale.bf ne bouge qu'une fois la
composition officiellement mise à jour - parfois longtemps après. Les comptes
rendus de plénière, eux, annoncent le changement le jour même : c'est là qu'on
lit « vingt nouveaux députés font officiellement leur entrée au Parlement »
(séance du 31 juillet 2026) alors que la page des députés en affichait encore
soixante-et-onze plusieurs jours plus tard.

D'où cette source : elle capte l'événement au moment où il est annoncé, sans
attendre que le site rattrape son propre annuaire. Elle donne aussi ce que ni
la liste ni le Journal officiel ne donnent - les ratifications d'accords, les
budgets votés, les débats.

Le site n'expose pas d'API : la liste est rendue côté serveur, chaque entrée
pointant vers une page numérotée (`/826`). On lit la liste, on récupère les
pages nouvelles.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
from datetime import date

from selectolax.parser import HTMLParser

from sqlalchemy import select

from app.ingestion.base import Collector
from app.models import Document

logger = logging.getLogger(__name__)

MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
# « 1er février » : le premier jour du mois s'écrit en ordinal, en toutes
# lettres comme en abrégé - et c'est le seul jour concerné.
RE_DATE = re.compile(
    r"(\d{1,2})\s*(?:er|ᵉʳ|re)?\s+(" + "|".join(MOIS) + r")\s+(\d{4})",
    re.IGNORECASE,
)
# une entrée de la liste : un lien vers /<id> portant le titre en gras
RE_ENTREE = re.compile(
    r'href="(https://www\.assembleenationale\.bf/(\d+))"[^>]*'
    r'class="text-sm[^"]*font-bold[^"]*"\s*>\s*(.{10,300}?)\s*</a>',
    re.DOTALL,
)


def date_du_texte(texte: str) -> date | None:
    """Première date en toutes lettres du compte rendu.

    C'est la date de la séance : les comptes rendus s'ouvrent sur « réunie en
    séance plénière le vendredi 31 juillet 2026 ». Le site n'expose aucune date
    structurée, et l'ordre de la liste ne suffit pas - il faut la lire.
    """
    m = RE_DATE.search(texte or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), MOIS[m.group(2).lower()], int(m.group(1)))
    except (ValueError, KeyError):
        return None


class PleniereCollector(Collector):
    slug = "pleniere"
    groupe = "institutionnel"
    url_liste = "https://www.assembleenationale.bf/pleniere"
    type_doc = "compte_rendu_pleniere"
    # Les comptes rendus déjà collectés sont relus, mais pas tous : seuls les
    # plus récents peuvent encore être corrigés par l'Assemblée. Sans cette
    # borne, chaque passage quotidien retéléchargeait la centaine de pages -
    # deux minutes de requêtes pour, presque toujours, rien de neuf.
    RELECTURE_RECENTS = 10

    def _corps(self, page_html: str) -> tuple[str | None, str]:
        """Titre et texte d'une page de compte rendu.

        La page n'a ni `<h1>` ni `<article>` : le titre est un `div` en gras de
        classe `text-2xl`, le corps une suite de `div` frères. On s'appuie donc
        sur le conteneur `space-y-6`, seul repère stable du gabarit.
        """
        tree = HTMLParser(page_html)
        conteneur = tree.css_first("div.space-y-6")
        if conteneur is None:
            return None, ""
        titre = None
        morceaux: list[str] = []
        # enfants directs seulement : `css("div")` renvoie le conteneur
        # lui-même, dont le texte est tout le compte rendu d'un bloc - titre
        # compris, et le corps s'en trouvait dupliqué
        for bloc in conteneur.iter():
            if bloc.tag != "div":
                continue
            texte = re.sub(r"\s+", " ", bloc.text(separator=" ")).strip()
            if not texte or len(texte) < 15:
                continue
            classes = bloc.attributes.get("class") or ""
            if "text-2xl" in classes and titre is None:
                titre = texte
            elif texte not in morceaux:
                morceaux.append(texte)
        return titre, "\n\n".join(morceaux)

    def collect(self) -> None:
        resp = self.get(self.url_liste)
        entrees = RE_ENTREE.findall(resp.text)
        if not entrees:
            raise ValueError(
                "Aucun compte rendu de plénière trouvé - le gabarit du site a "
                "probablement changé"
            )
        logger.info("pleniere : %d entrée(s) listée(s)", len(entrees))

        connues = set(
            self.db.scalars(
                select(Document.url).where(Document.source_id == self.source.id)
            )
        )
        a_relire = {url for url, _n, _t in entrees[: self.RELECTURE_RECENTS]}

        for url, _numero, titre_liste in entrees:
            if url in connues and url not in a_relire:
                self.nb_vus += 1
                continue
            titre_liste = re.sub(r"\s+", " ", html.unescape(titre_liste)).strip()
            page = self.get(url)
            titre, texte = self._corps(page.text)
            if not texte:
                logger.warning("pleniere : %s illisible, ignoré", url)
                continue
            self.upsert_document(
                url=url,
                type_doc=self.type_doc,
                titre=titre or titre_liste,
                date_publication=date_du_texte(texte),
                hash_contenu=hashlib.sha256(texte.encode("utf-8")).hexdigest(),
                texte_extrait=texte,
                statut_extraction="ok",
            )
