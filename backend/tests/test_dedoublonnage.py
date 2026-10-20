"""Purge des versions redondantes d'un même document (texte identique).

Le HTML rendu par WordPress change d'un jour à l'autre sans republication :
le hash pris sur le brut faisait de chaque collecte une « version ». Ces tests
figent ce que la purge supprime, et surtout ce qu'elle doit préserver : les
entités extraites, l'identifiant le plus ancien, les vraies versions.
"""

import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ingestion.base import empreinte_texte
from app.ingestion.dedoublonnage import dedoublonner
from app.models import Base, Decision, Document, Source

_TABLES = (Source, Document, Decision)
URL = "https://gouvernement.gov.bf/actualites/inauguration/"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _TABLES])
    with Session(engine) as session:
        session.add(
            Source(
                id=1,
                slug="actualites_gouv",
                nom="Gouvernement",
                url_base="https://gouvernement.gov.bf",
                type="institutionnel",
            )
        )
        session.commit()
        yield session


_RENDUS = iter(range(10_000))


def version(db, texte, *, html_brut=None, url=URL, structuree=False, mime="text/html"):
    """Une ligne telle que l'ancien collecteur la créait : hash du HTML brut,
    et un brut différent à chaque rendu (galerie renumérotée)."""
    brut = html_brut or f'<figure class="wp-block-gallery-{next(_RENDUS)}"><p>{texte}</p>'
    doc = Document(
        source_id=1,
        url=url,
        type_doc="actualite_gouv",
        texte_extrait=texte,
        hash_contenu=hashlib.sha256(brut.encode()).hexdigest(),
        fichier=f"actualites_gouv/2026/{hashlib.sha256(brut.encode()).hexdigest()[:16]}.html",
        statut_extraction="ok",
        mime=mime,
        date_structuration=datetime(2026, 10, 15, tzinfo=timezone.utc) if structuree else None,
    )
    db.add(doc)
    db.commit()
    return doc


def purger(db, **kw):
    supprimes = []
    stats = dedoublonner(
        db, ["actualites_gouv"], enfants=(Decision,), supprimer_fichier=supprimes.append, **kw
    )
    return stats, supprimes


def test_le_meme_texte_sous_un_html_different_est_une_seule_ligne(db):
    """Le cas des galeries renumérotées : trois matins, trois HTML, un texte."""
    for n in (16, 18, 20):
        version(
            db,
            "Inauguration du pont",
            html_brut=f'<figure class="wp-block-gallery-{n}"><p>Inauguration du pont</p>',
        )

    stats, supprimes = purger(db)

    assert db.query(Document).count() == 1
    assert stats["supprimees"] == 2
    assert len(supprimes) == 2, "les bruts des doublons quittent le bucket"


def test_la_ligne_la_plus_ancienne_est_conservee(db):
    """Son identifiant sert de clé de diffusion : il ne doit pas bouger."""
    premiere = version(db, "Texte").id
    version(db, "Texte")
    version(db, "Texte")

    purger(db)

    assert [d.id for d in db.scalars(select(Document))] == [premiere]


def test_une_vraie_reecriture_reste_une_version(db):
    version(db, "Le pont sera livré en 2027")
    version(db, "Le pont sera livré en 2027")
    version(db, "Le pont a été livré en 2026")

    stats, _ = purger(db)

    assert stats["supprimees"] == 1
    assert sorted(db.scalars(select(Document.texte_extrait))) == [
        "Le pont a été livré en 2026",
        "Le pont sera livré en 2027",
    ]


def test_les_entites_des_doublons_rejoignent_la_ligne_conservee(db):
    """La consolidation avait poussé décisions et nominations sur la version la
    plus récente - souvent un doublon. Les supprimer sans les reporter
    effacerait du travail de validation."""
    garde = version(db, "CONSEIL DES MINISTRES N°29")
    doublon = version(db, "CONSEIL DES MINISTRES N°29")
    db.add(
        Decision(
            document_id=doublon.id,
            type="adoption_decret",
            objet="Adoption d'un décret",
            statut_validation="valide",
        )
    )
    db.commit()

    stats, _ = purger(db)

    decision = db.scalars(select(Decision)).one()
    assert decision.document_id == garde.id
    assert decision.statut_validation == "valide"
    assert stats["entites_reportees"] == 1


def test_lempreinte_conservee_est_celle_du_texte(db):
    """Sans cela, la prochaine collecte ne reconnaîtrait rien et recréerait
    tout le fonds une fois de plus."""
    version(db, "Texte")
    seule = version(db, "Texte unique", url=URL + "autre/")

    purger(db)

    empreintes = dict(db.execute(select(Document.url, Document.hash_contenu)).all())
    assert empreintes[URL] == empreinte_texte("Texte")
    assert empreintes[seule.url] == empreinte_texte("Texte unique"), "même sans doublon"


def test_la_structuration_dun_doublon_vaut_pour_le_texte_partage(db):
    """Le CR n°29 avait été structuré sur sa seconde copie : la première ne
    doit pas repasser dans la file d'extraction."""
    garde = version(db, "Texte")
    version(db, "Texte", structuree=True)

    purger(db)

    db.refresh(garde)
    assert garde.date_structuration is not None


def test_la_simulation_ne_modifie_rien(db):
    version(db, "Texte")
    version(db, "Texte")

    stats, supprimes = purger(db, simuler=True)

    assert stats["supprimees"] == 1, "elle compte ce qu'elle ferait"
    assert db.query(Document).count() == 2
    assert supprimes == []


def test_une_source_absente_est_ignoree(db):
    stats = dedoublonner(db, ["inconnue"], enfants=(Decision,))
    assert stats["examinees"] == 0


def test_les_pdf_ne_sont_pas_touches(db):
    """Deux PDF distincts sous la même adresse, sans texte extrait, partageraient
    l'empreinte du texte vide : leur identité reste celle du fichier."""
    version(db, None, html_brut="%PDF-1", url=URL + "cr.pdf", mime="application/pdf")
    version(db, None, html_brut="%PDF-2", url=URL + "cr.pdf", mime="application/pdf")

    stats, supprimes = purger(db)

    assert stats["supprimees"] == 0
    assert db.query(Document).count() == 2
    assert supprimes == []
