"""Collecte du Journal officiel (jobf.gov.bf).

Le JO fait foi : c'est là qu'un décret devient opposable. Légiburkina l'indexe
ensuite, avec un décalage qui s'est transformé en arrêt à l'été 2026 - quatre
numéros et un mois de droit manquants. Ces tests figent ce qui rend cette
seconde source tenable : ne pas retélécharger sept mégaoctets pour rien, ne pas
relire quatre-vingt-dix pages d'archives à chaque passage, et ne pas rapatrier
six gigaoctets d'un coup sur un disque partagé.
"""

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ingestion.jobf import JobfCollector
from app.models import Base, Document, Source

_TABLES = (Source, Document)

PDF = b"%PDF-1.4 contenu du journal officiel"


def numero(n, uuid=None, type_="ordinaire", jour=None):
    # le JO paraît chaque jeudi : le jour importe peu ici, il doit surtout
    # rester un jour valide quel que soit le numéro
    jour = jour if jour is not None else (n - 1) % 28 + 1
    return {
        "id": 1000 + n,
        "uuid": uuid or f"uuid-{n}",
        "numero": n,
        "type": type_,
        "date_pub": f"2026-08-{jour:02d}T00:00:00.000000Z",
        "sommaire": f"<p><strong>PARTIE OFFICIELLE</strong> Décret n°{n}</p>",
    }


class _Jobf(JobfCollector):
    """Le collecteur, son réseau remplacé par des réponses en dur."""

    def __init__(self, db, pages, pdf=PDF):
        self.db = db
        self.source = db.scalars(select(Source).where(Source.slug == self.slug)).one()
        self.nb_nouveaux = self.nb_vus = 0
        self._last_request = 0.0
        self._pages = pages
        self.pdf = pdf
        self.telechargements = []
        self.pages_lues = []
        self.client = httpx.Client(transport=httpx.MockTransport(self._repondre))

    def _repondre(self, request):
        chemin = request.url.path
        if "frontoffice/newspapers/page" in chemin:
            page = int(chemin.rsplit("/", 1)[-1])
            self.pages_lues.append(page)
            items = self._pages[page - 1] if page <= len(self._pages) else []
            total = sum(len(p) for p in self._pages)
            return httpx.Response(
                200, json={"success": True, "data": {"data": items, "total": total}}
            )
        if "jo-file-url" in chemin:
            uuid = request.read().decode().split('"joUuid":"')[1].split('"')[0]
            return httpx.Response(
                200, json={"success": True, "data": {"pathJo": f"newspapers/{uuid}.pdf"}}
            )
        self.telechargements.append(str(request.url))
        return httpx.Response(200, content=self.pdf)

    def archive(self, contenu, extension):
        import hashlib

        return f"jobf/2026/{hashlib.sha256(contenu).hexdigest()[:16]}.pdf", hashlib.sha256(
            contenu
        ).hexdigest()


@pytest.fixture(autouse=True)
def sans_extraction_pdf(monkeypatch):
    """Le texte du PDF ne concerne pas ces tests, et pdfplumber n'ouvrirait
    pas ces octets factices."""
    import app.ingestion.jobf as module

    monkeypatch.setattr(module, "extraire_texte", lambda chemin, ocr=True: ("texte", "ok"))

    class _StockageFactice:
        def fichier_local(self, cle):
            from contextlib import nullcontext

            return nullcontext(cle)

    monkeypatch.setattr(module, "stockage", _StockageFactice())
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _TABLES])
    with Session(engine) as session:
        session.add(
            Source(id=1, slug="jobf", nom="Journal officiel",
                   url_base="https://jobf.gov.bf", type="institutionnel", cadence="hebdo")
        )
        session.commit()
        yield session


def documents(db):
    return db.scalars(select(Document).order_by(Document.id)).all()


def test_un_numero_est_archive_avec_son_sommaire(db):
    collecteur = _Jobf(db, [[numero(34, jour=20)], []])

    collecteur.collect()

    doc = documents(db)[0]
    assert doc.type_doc == "journal_officiel"
    assert doc.titre == "Journal officiel n°34 du 20/08/2026"
    assert doc.mime == "application/pdf"
    assert "Décret n°34" in doc.meta["sommaire"], "le sommaire vient de la source"
    assert doc.meta["jo_numero"] == "34"


def test_une_edition_speciale_est_signalee_dans_le_titre(db):
    """Les numéros spéciaux ont leur propre numérotation : sans mention, deux
    « n°12 » de la même année seraient indiscernables dans une liste."""
    _Jobf(db, [[numero(12, type_="special")], []]).collect()

    assert "spécial" in documents(db)[0].titre


def test_un_numero_deja_archive_nest_pas_retelecharge(db):
    """Sept mégaoctets par numéro : découvrir APRÈS téléchargement qu'on le
    connaissait déjà rendrait la collecte hebdomadaire absurde."""
    premier = _Jobf(db, [[numero(34)], []])
    premier.collect()

    second = _Jobf(db, [[numero(34)], []])
    second.collect()

    assert second.telechargements == [], "aucun octet de PDF ne doit repartir"
    assert len(documents(db)) == 1


def test_une_fois_a_jour_une_page_connue_arrete_la_collecte(db):
    """Les numéros arrivent du plus récent au plus ancien. Sans cette sortie,
    chaque passage relirait les quatre-vingt-dix pages d'archives."""
    pages = [[numero(34), numero(33)], [numero(32), numero(31)], [numero(30)]]
    _Jobf(db, pages).collect()

    suivant = _Jobf(db, pages)
    suivant.collect()

    assert suivant.pages_lues == [1], "la première page suffit à conclure"


def test_pendant_le_rattrapage_une_page_connue_narrete_rien(db):
    """La collecte étant bornée par passage, les premières pages sont connues
    bien avant les dernières. S'arrêter à la première page connue
    condamnerait l'arriéré à ne jamais être rapatrié."""
    pages = [[numero(20), numero(19)], [numero(18), numero(17)], [numero(16)]]
    premier = _Jobf(db, pages)
    premier.max_nouveaux = 2
    premier.collect()
    assert premier.pages_lues == [1], "la borne suffit à arrêter le premier passage"

    suivant = _Jobf(db, pages)
    suivant.max_nouveaux = 2
    suivant.collect()

    assert suivant.pages_lues == [1, 2], "page 1 connue, mais l'arriéré appelle la suite"
    assert len(documents(db)) == 4


def test_la_collecte_est_bornee_par_passage(db):
    """Près de 900 numéros à sept mégaoctets : tout rapatrier d'un coup, ce
    sont six gigaoctets sur un disque partagé avec une autre application."""
    collecteur = _Jobf(db, [[numero(n) for n in range(1, 11)], [numero(n) for n in range(11, 21)]])
    collecteur.max_nouveaux = 4

    collecteur.collect()

    assert len(documents(db)) == 4


def test_larriere_se_resorbe_au_passage_suivant(db):
    pages = [[numero(n) for n in range(20, 10, -1)], [numero(n) for n in range(10, 0, -1)]]
    for _ in range(3):
        collecteur = _Jobf(db, pages)
        collecteur.max_nouveaux = 5
        collecteur.collect()

    assert len(documents(db)) == 15, "cinq de plus à chaque passage"


def test_un_chemin_de_pdf_introuvable_ne_casse_pas_la_collecte(db):
    """L'API répond numéro par numéro : une réponse manquante ne doit pas
    emporter les autres."""

    class _SansChemin(_Jobf):
        def url_pdf(self, uuid):
            return None if uuid == "uuid-33" else super().url_pdf(uuid)

    _SansChemin(db, [[numero(34), numero(33), numero(32)], []]).collect()

    assert sorted(d.meta["jo_numero"] for d in documents(db)) == ["32", "34"]


def test_un_contenu_qui_nest_pas_un_pdf_est_refuse(db):
    """Le site répond parfois par sa page d'erreur en HTTP 200 : l'archiver
    comme un Journal officiel salirait le corpus."""
    _Jobf(db, [[numero(34)], []], pdf=b"<!DOCTYPE html><html>Server Error").collect()

    assert documents(db) == []


def test_une_date_illisible_narrete_pas_la_collecte(db):
    """Le numéro reste archivé, sa date manquera - c'est réparable, un numéro
    perdu ne l'est pas une fois le site dépublié."""
    casse = {**numero(34), "date_pub": "2026-08-34T00:00:00.000000Z"}

    _Jobf(db, [[casse, numero(33)], []]).collect()

    docs = documents(db)
    assert len(docs) == 2
    assert docs[0].date_publication is None
    assert docs[1].date_publication is not None
