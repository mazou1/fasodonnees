"""Identité d'un document WordPress quand le site change ses permaliens.

Le 22 août 2026, gouvernement.gov.bf est passé des permaliens lisibles à la
forme « /?p=19635 ». L'identité d'un document reposant sur son URL, le site a
été recollecté en entier sous ces nouvelles adresses : 3 283 documents en
quatre jours, tout le fonds en double, l'extraction LLM repartie sur des
articles déjà traités, et les doublons visibles sur le site public.

Ces tests figent le raccrochage à l'identifiant du billet, seul repère que la
source ne change pas.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ingestion.wordpress import WordPressCollector
from app.models import Base, Document, Source

_TABLES = (Source, Document)

PRETTY = "https://gouvernement.gov.bf/actualites/importance-des-informations-meteo/"
COURT = "https://gouvernement.gov.bf/?p=19635"


class _Collecteur(WordPressCollector):
    """La mécanique d'identité, sans HTTP ni archivage."""

    slug = "actualites_gouv"
    api_base = "https://gouvernement.gov.bf/wp-json/wp/v2"
    type_doc = "actualite_gouv"

    def __init__(self, db):
        self.db = db
        self.source = db.scalars(select(Source).where(Source.slug == self.slug)).one()
        self.nb_nouveaux = self.nb_vus = 0

    def archive(self, contenu, extension):
        import hashlib

        return None, hashlib.sha256(contenu).hexdigest()


def post(wp_id, lien, titre="Importance des informations météo", contenu="<p>a</p>"):
    return {
        "id": wp_id,
        "link": lien,
        "title": {"rendered": titre},
        "content": {"rendered": contenu},
        "date": "2026-08-24T10:00:00",
    }


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _TABLES])
    with Session(engine) as session:
        session.add(
            Source(id=1, slug="actualites_gouv", nom="Gouvernement",
                   url_base="https://gouvernement.gov.bf", type="institutionnel")
        )
        session.commit()
        yield session


def urls(db):
    return sorted(db.scalars(select(Document.url)))


def test_un_changement_de_permalien_ne_recree_pas_le_fonds(db):
    """Le cas du 22 août : le même billet revient sous une autre adresse. Il
    doit rester UN document, versionné, pas deux fonds parallèles."""
    collecteur = _Collecteur(db)
    collecteur._traiter_post(post(19635, PRETTY))
    db.commit()

    collecteur._traiter_post(post(19635, COURT, contenu="<p>b</p>"))
    db.commit()

    assert urls(db) == [PRETTY, PRETTY], "la seconde adresse doit rejoindre la première"
    assert db.query(Document).count() == 2, "contenu différent : une version de plus"


def test_un_contenu_inchange_ne_cree_rien(db):
    """Recollecter sous une nouvelle adresse un contenu déjà archivé ne doit
    rien produire du tout - c'est ce qui a gonflé le fonds de 3 283 lignes."""
    collecteur = _Collecteur(db)
    collecteur._traiter_post(post(19635, PRETTY))
    db.commit()

    cree = collecteur._traiter_post(post(19635, COURT))
    db.commit()

    assert cree is False, "rien de neuf : le collecteur doit le dire"
    assert db.query(Document).count() == 1


def test_un_billet_inconnu_garde_ladresse_que_la_source_donne(db):
    """Rien à raccrocher : un article publié après le changement s'archive
    sous sa nouvelle adresse, sans invention de notre part."""
    _Collecteur(db)._traiter_post(post(19720, "https://gouvernement.gov.bf/?p=19720"))
    db.commit()

    assert urls(db) == ["https://gouvernement.gov.bf/?p=19720"]


def test_deux_billets_distincts_restent_distincts(db):
    """Le raccrochage se fait sur l'identifiant du billet, pas sur le titre :
    deux annonces différentes ne doivent pas fusionner."""
    collecteur = _Collecteur(db)
    collecteur._traiter_post(post(19635, PRETTY))
    collecteur._traiter_post(post(19608, "https://gouvernement.gov.bf/?p=19608", titre="Autre"))
    db.commit()

    assert len(urls(db)) == 2


def test_un_billet_sans_identifiant_ne_casse_pas_la_collecte(db):
    """Tous les WordPress ne renvoient pas d'`id` exploitable."""
    _Collecteur(db)._traiter_post({**post(19635, PRETTY), "id": None})
    db.commit()

    assert urls(db) == [PRETTY]
