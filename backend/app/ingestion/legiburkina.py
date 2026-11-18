"""Légiburkina (SGG-CM) - textes juridiques, lus dans les pages du site.

Le site a été refondu à l'automne 2026 (constaté le 2026-11-18) : l'ancienne
application Angular et son API JSON (`/api/documents/search-mot-cle`) ont
disparu, `www.` redirige vers le domaine nu, et la collecte est restée en échec
du 23 octobre au 18 novembre.

La nouvelle plateforme est une application Inertia : chaque page embarque ses
données dans l'attribut `data-page` de la racine. On lit donc la liste publique
`/documents-publics?page=N` (10 textes par page, du plus récent au plus ancien)
et on en extrait ce JSON - sans dépendre du numéro de version qu'exigerait le
protocole Inertia en mode XHR.

Deux conséquences de la refonte, qui commandent le reste du module :

- **Les identifiants et les adresses de tous les textes ont changé** (entiers
  → UUID). L'identité d'un texte ne peut donc pas tenir à son URL, sous peine
  de recréer les ~5 000 textes déjà archivés : elle tient à sa référence
  (« 2026-1165/PF/MGDP ») et à son type. Un texte déjà connu est rattaché à sa
  nouvelle adresse, l'ancienne étant morte.
- La fiche détaillée exige désormais un compte ; seule la liste et le PDF
  (`/documents/{uuid}/visualiser`) restent publics. Le secteur et le Journal
  officiel de publication ne sont plus fournis.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.ingestion.base import Collector
from app.models import Document

logger = logging.getLogger(__name__)

TYPES_CONNUS = {
    "DECRET": "decret",
    "LOI": "loi",
    "ARRETE": "arrete",
    "ORDONNANCE": "ordonnance",
    "CHARTE": "charte",
    "CONSTITUTION": "constitution",
}

_DATA_PAGE = re.compile(r'data-page="([^"]*)"')


def cle_reference(reference: str | None) -> str:
    """Référence débarrassée de ce que la saisie fait varier (espaces, casse)."""
    return re.sub(r"\s+", "", reference or "").upper()


def donnees_page(page_html: str) -> dict:
    """Le JSON qu'Inertia embarque dans la page (`props.documents`)."""
    trouve = _DATA_PAGE.search(page_html)
    if not trouve:
        raise ValueError("Légiburkina : attribut data-page introuvable - le site a encore changé")
    documents = json.loads(html.unescape(trouve.group(1)))["props"].get("documents")
    if not isinstance(documents, dict) or "data" not in documents:
        raise ValueError("Légiburkina : liste des documents absente de la page")
    return documents


class LegiburkinaCollector(Collector):
    slug = "legiburkina"
    groupe = "institutionnel"
    base = "https://legiburkina.gov.bf"

    # La liste va du plus récent au plus ancien : quelques pages entièrement
    # connues signifient que la suite l'est aussi, et s'arrêter là évite de
    # relire 650 pages chaque matin. Plusieurs pages plutôt qu'une, parce que
    # le SGG publie aussi des textes anciens, qui s'intercalent plus bas.
    # Pour une reprise complète (après une refonte, par exemple), relever ce
    # seuil le temps d'un passage manuel.
    pages_connues_max = 3

    def collect(self) -> None:
        connus = self._textes_connus()
        page = 1
        connues_de_suite = 0
        while True:
            reponse = self.get(f"{self.base}/documents-publics?page={page}", min_interval=1.0)
            documents = donnees_page(reponse.text)
            items = documents["data"]
            if not items:
                break
            nouveaux_avant = self.nb_nouveaux
            for item in items:
                self._traiter(item, connus)
            self.db.commit()
            if self.nb_nouveaux == nouveaux_avant:
                connues_de_suite += 1
                if connues_de_suite >= self.pages_connues_max:
                    break
            else:
                connues_de_suite = 0
            if page % 25 == 0:
                logger.info("%s : page %d, %d nouveaux cumulés", self.slug, page, self.nb_nouveaux)
            if page >= (documents.get("last_page") or page):
                break
            page += 1

    def _textes_connus(self) -> dict[str, list[tuple[int, str]]]:
        """Référence normalisée → [(id, type_doc)] des textes déjà archivés."""
        connus: dict[str, list[tuple[int, str]]] = {}
        lignes = self.db.execute(
            select(Document.id, Document.type_doc, Document.meta).where(
                Document.source_id == self.source.id
            )
        )
        for doc_id, type_doc, meta in lignes:
            cle = cle_reference((meta or {}).get("reference"))
            if cle:
                connus.setdefault(cle, []).append((doc_id, type_doc))
        return connus

    def _deja_archive(self, connus: dict, cle: str, type_doc: str) -> list[int]:
        """Identifiants des versions déjà archivées sous cette référence.

        Le type départage deux textes de même numéro (une loi et un décret).
        Seule tolérance : le type générique « texte juridique », où l'ancien
        site rangeait ce qu'il ne savait pas classer, s'accorde avec n'importe
        quel type précis.
        """
        candidats = connus.get(cle) or []
        du_type = [doc_id for doc_id, type_connu in candidats if type_connu == type_doc]
        if du_type:
            return du_type
        generique = "texte_juridique"
        if type_doc == generique:
            return [doc_id for doc_id, _ in candidats]
        return [doc_id for doc_id, type_connu in candidats if type_connu == generique]

    def _traiter(self, item: dict, connus: dict) -> None:
        uuid = item.get("id")
        if not uuid:
            return
        libelle = ((item.get("type") or {}).get("libelle") or "").upper()
        type_doc = TYPES_CONNUS.get(libelle, "texte_juridique")
        reference = (item.get("reference") or "").strip()
        description = item.get("description") or ""
        url = f"{self.base}/documents/{uuid}/visualiser"

        cle = cle_reference(reference)
        archives = self._deja_archive(connus, cle, type_doc) if cle else []
        if archives:
            self.nb_vus += 1
            # toutes les versions suivent : la version de référence se choisit
            # par URL, en laisser une sur l'ancienne adresse la dédoublerait
            for doc_id in archives:
                self._rattacher(doc_id, uuid, url)
            return

        pub: date | None = None
        if item.get("date"):
            try:
                pub = date.fromisoformat(str(item["date"])[:10])
            except ValueError:
                pub = None
            # la source porte des dates de saisie aberrantes (an 1, an 971…)
            if pub and pub.year < 1900:
                pub = None

        digest = hashlib.sha256(
            f"{uuid}|{item.get('file_name')}|{item.get('file_size')}".encode()
        ).hexdigest()
        doc = self.upsert_document(
            url=url,
            type_doc=type_doc,
            titre=f"{libelle or 'TEXTE'} {reference}".strip()[:1000],
            date_publication=pub,
            hash_contenu=digest,
            mime="application/pdf",
            texte_extrait=description or None,
            statut_extraction="na",  # métadonnées seules - le PDF suit (pdf_textes)
            meta={
                "legi_uuid": uuid,
                "reference": reference,
                "categorie": (item.get("type") or {}).get("categorie"),
                "nom_fichier": item.get("file_name"),
                "taille_pdf": item.get("file_size"),
            },
        )
        if doc is not None and cle:
            self.db.flush()
            connus.setdefault(cle, []).append((doc.id, type_doc))

    def _rattacher(self, doc_id: int, uuid: str, url: str) -> None:
        """Donne à un texte archivé avant la refonte sa nouvelle adresse.

        L'ancienne URL ne répond plus : la laisser, c'est afficher un lien
        « source » mort sur chaque texte. Le PDF, le texte extrait et l'OCR
        déjà faits sont conservés tels quels.
        """
        doc = self.db.get(Document, doc_id)
        if doc is None or (doc.meta or {}).get("legi_uuid") == uuid:
            return
        meta = dict(doc.meta or {})
        meta.setdefault("url_avant_refonte", doc.url)
        meta["legi_uuid"] = uuid
        doc.meta = meta
        flag_modified(doc, "meta")
        doc.url = url
