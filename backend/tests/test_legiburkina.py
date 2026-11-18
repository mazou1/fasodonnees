"""Collecte de Légiburkina après la refonte de l'automne 2026.

L'API JSON a disparu et tous les textes ont changé d'identifiant et d'adresse.
Ces tests figent ce qui évite le pire : recréer les milliers de textes déjà
archivés parce que leur URL n'est plus la même, et relire 650 pages par jour.
"""

import html
import json

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.extraction.pdf_cr import choisir_lien
from app.ingestion.legiburkina import LegiburkinaCollector, cle_reference, donnees_page
from app.models import Base, Document, Source

_TABLES = (Source, Document)


def texte(n, type_="DECRET", ref=None):
    return {
        "id": f"uuid-{n}",
        "reference": ref or f"2026-{n:04d}/PF/PRIM",
        "description": f"Objet du texte {n}",
        "date": "2026-10-16",
        "file_name": f"texte_{n}.pdf",
        "file_size": 1000 + n,
        "type": {"id": "t", "libelle": type_, "categorie": "reglementaire"},
        "fichier": f"/documents/uuid-{n}/visualiser",
    }


def page_html(items, page, derniere):
    props = {"documents": {"data": items, "current_page": page, "last_page": derniere}}
    donnees = html.escape(json.dumps({"component": "public/documents", "props": props}))
    return f'<html><body><div id="app" data-page="{donnees}"></div></body></html>'


class _Legi(LegiburkinaCollector):
    def __init__(self, db, pages):
        self.db = db
        self.source = db.scalars(select(Source).where(Source.slug == self.slug)).one()
        self.nb_nouveaux = self.nb_vus = 0
        self._last_request = 0.0
        self._pages = pages
        self.pages_lues = []
        self.client = httpx.Client(transport=httpx.MockTransport(self._repondre))

    def _repondre(self, request):
        page = int(request.url.params.get("page", 1))
        self.pages_lues.append(page)
        items = self._pages[page - 1] if page <= len(self._pages) else []
        return httpx.Response(200, text=page_html(items, page, len(self._pages)))

    def get(self, url, min_interval=1.0, retries=3):
        return self.client.get(url)


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[t.__table__ for t in _TABLES])
    db = Session(engine)
    db.add(Source(slug="legiburkina", nom="Légiburkina",
                  url_base="https://legiburkina.gov.bf", type="institutionnel"))
    db.commit()
    return db


def test_donnees_page_lit_le_json_embarque():
    documents = donnees_page(page_html([texte(1)], 1, 1))
    assert documents["data"][0]["reference"] == "2026-0001/PF/PRIM"


def test_un_texte_nouveau_est_archive_sous_l_adresse_du_pdf():
    db = _db()
    collecteur = _Legi(db, [[texte(1)]])
    collecteur.collect()
    doc = db.scalars(select(Document)).one()
    assert doc.url == "https://legiburkina.gov.bf/documents/uuid-1/visualiser"
    assert doc.type_doc == "decret"
    assert doc.meta["legi_uuid"] == "uuid-1"
    assert collecteur.nb_nouveaux == 1


def test_un_texte_d_avant_la_refonte_n_est_pas_recree_mais_rattache():
    db = _db()
    source = db.scalars(select(Source)).one()
    ancien = Document(
        source_id=source.id, url="https://www.legiburkina.gov.bf/document/42",
        type_doc="decret", hash_contenu="h", texte_extrait="texte OCR déjà fait",
        statut_extraction="ocr", meta={"legi_id": 42, "reference": "2026-0001 /pf/prim"},
    )
    db.add(ancien)
    db.commit()

    collecteur = _Legi(db, [[texte(1)]])
    collecteur.collect()

    docs = db.scalars(select(Document)).all()
    assert len(docs) == 1, "le texte déjà archivé ne doit pas être dupliqué"
    assert docs[0].url == "https://legiburkina.gov.bf/documents/uuid-1/visualiser"
    assert docs[0].meta["url_avant_refonte"] == "https://www.legiburkina.gov.bf/document/42"
    assert docs[0].texte_extrait == "texte OCR déjà fait"
    assert (collecteur.nb_nouveaux, collecteur.nb_vus) == (0, 1)


def test_meme_numero_mais_type_different_reste_un_texte_distinct():
    db = _db()
    collecteur = _Legi(db, [[texte(1, "LOI", ref="010-2026/ALT"), texte(2, "DECRET", ref="010-2026/ALT")],
                            [texte(3, "ARRETE", ref="010-2026/ALT")]])
    collecteur.collect()
    # loi et décret coexistent ; l'arrêté, troisième type, ne peut être confondu
    assert len(db.scalars(select(Document)).all()) == 3


def test_la_collecte_s_arrete_apres_quelques_pages_connues():
    db = _db()
    pages = [[texte(p * 10 + i) for i in range(3)] for p in range(8)]
    _Legi(db, pages).collect()
    second = _Legi(db, pages)
    second.collect()
    assert second.pages_lues == [1, 2, 3]
    assert second.nb_nouveaux == 0


def test_cle_reference_ignore_espaces_et_casse():
    assert cle_reference(" 2026-1165 /pf/MGDP ") == "2026-1165/PF/MGDP"


def test_cr_coquille_prefere_le_rectificatif_et_ecarte_les_traductions():
    liens = [
        ("https://g/CONSEIL-DES-MINISTRES-N31.pdf", "Télécharger"),
        ("https://g/RECTIF.-CONSEIL-DES-MINISTRES-N031.pdf", "Télécharger"),
        ("https://g/moore-CONSEIL-DES-MINISTRES-N31.pdf", "Télécharger"),
        ("https://g/page", "Accueil"),
    ]
    assert choisir_lien(liens) == "https://g/RECTIF.-CONSEIL-DES-MINISTRES-N031.pdf"
    assert choisir_lien(liens[:1] + liens[2:]) == "https://g/CONSEIL-DES-MINISTRES-N31.pdf"
    assert choisir_lien(liens[2:]) is None
