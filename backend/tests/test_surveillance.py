"""Surveillance des sources : muettes et taries.

Août 2026 : le dernier compte rendu du Conseil des ministres datait du
30 juillet, et rien ne l'a signalé. Le collecteur passait, réussissait, et la
surveillance ne regardait que ça. Ces tests figent la distinction entre « le
collecteur ne passe plus » et « la source ne publie plus », parce qu'une
plateforme d'archives qui cesse de grossir sans le dire ne se découvre
autrement que des semaines plus tard, par hasard.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ingestion.surveillance import etat_sources
from app.models import Base, Document, Run, Source

_TABLES = (Source, Document, Run)

MAINTENANT = datetime.now(timezone.utc)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _TABLES])
    with Session(engine) as session:
        yield session


def source(db, slug="conseil_ministres", cadence="hebdo"):
    """Un slug du registre : `etat_sources` écarte les sources sans collecteur."""
    db.add(Source(id=1, slug=slug, nom=slug, url_base="https://x.bf",
                  type="institutionnel", cadence=cadence))
    return db


def run_reussi(db, il_y_a_jours):
    db.add(Run(source_id=1, statut="ok", fin=MAINTENANT - timedelta(days=il_y_a_jours)))


def publication(db, il_y_a_jours, doc_id=1, collecte_il_y_a=0):
    db.add(
        Document(
            id=doc_id,
            source_id=1,
            url=f"https://x.bf/{doc_id}",
            type_doc="cr_conseil",
            date_publication=date.today() - timedelta(days=il_y_a_jours),
            date_collecte=MAINTENANT - timedelta(days=collecte_il_y_a),
        )
    )


def etat(db):
    db.commit()
    return etat_sources(db)[0]


def test_une_source_a_jour_ne_declenche_rien(db):
    source(db)
    run_reussi(db, il_y_a_jours=1)
    publication(db, il_y_a_jours=3)

    assert (etat(db)["muette"], etat(db)["tarie"]) == (False, False)


def test_un_collecteur_qui_ne_passe_plus_rend_la_source_muette(db):
    source(db)
    run_reussi(db, il_y_a_jours=20)  # cadence hebdo : seuil à 10 jours
    publication(db, il_y_a_jours=1)

    assert etat(db)["muette"] is True


def test_une_source_qui_repond_sans_rien_publier_est_tarie(db):
    """Le cas d'août 2026 : tous les voyants au vert, et pourtant plus rien."""
    source(db)
    run_reussi(db, il_y_a_jours=1)
    publication(db, il_y_a_jours=60)

    resultat = etat(db)
    assert (resultat["muette"], resultat["tarie"]) == (False, True)
    assert resultat["derniere_publication"] is not None


def test_une_reecriture_de_vieille_page_ne_masque_pas_le_silence(db):
    """Le gouvernement retouche ses archives : la collecte crée un document
    daté d'aujourd'hui alors que RIEN de neuf n'a été publié. Juger sur
    `date_collecte` rendrait la source verte à tort - c'est précisément ce qui
    a masqué le silence de l'été."""
    source(db)
    run_reussi(db, il_y_a_jours=1)
    publication(db, il_y_a_jours=60, collecte_il_y_a=0)

    assert etat(db)["tarie"] is True


def test_une_source_muette_nest_pas_dite_tarie_en_plus(db):
    """Le collecteur ne passe pas : on ne sait rien de ce que la source publie.
    Deux alertes pour une panne feraient chercher deux causes."""
    source(db)
    run_reussi(db, il_y_a_jours=40)
    publication(db, il_y_a_jours=60)

    resultat = etat(db)
    assert (resultat["muette"], resultat["tarie"]) == (True, False)


def test_le_creux_dete_du_conseil_des_ministres_ne_declenche_pas_lalerte(db):
    """Mesuré sur le corpus : écart médian de 8 jours entre deux conseils, 90e
    centile à 28, et un creux de 29 jours en août 2024 comme en août 2025. Une
    alerte qui sonne chaque été est une alerte qu'on n'ouvre plus."""
    source(db, cadence="hebdo")
    run_reussi(db, il_y_a_jours=1)
    publication(db, il_y_a_jours=29)

    assert etat(db)["tarie"] is False


def test_un_silence_sans_precedent_finit_par_alerter(db):
    source(db, cadence="hebdo")
    run_reussi(db, il_y_a_jours=1)
    publication(db, il_y_a_jours=46)

    assert etat(db)["tarie"] is True


def test_une_source_quotidienne_est_jugee_bien_plus_vite(db):
    """Légiburkina publie tous les jours ouvrés : deux semaines de silence n'y
    ont pas la même signification que sur un conseil hebdomadaire."""
    source(db, slug="legiburkina", cadence="quotidien")
    run_reussi(db, il_y_a_jours=1)
    publication(db, il_y_a_jours=20)

    assert etat(db)["tarie"] is True


def test_une_source_qui_na_jamais_rien_rapporte_est_signalee(db):
    source(db)
    run_reussi(db, il_y_a_jours=1)

    assert etat(db)["tarie"] is True


def test_les_sources_en_alerte_remontent_en_tete(db):
    """La liste sert à ouvrir /sources/etat et voir le problème sans chercher."""
    db.add_all([
        Source(id=1, slug="conseil_ministres", nom="CM", url_base="https://x.bf",
               type="institutionnel", cadence="hebdo"),
        Source(id=2, slug="legiburkina", nom="Legi", url_base="https://y.bf",
               type="institutionnel", cadence="quotidien"),
    ])
    db.add_all([
        Run(source_id=1, statut="ok", fin=MAINTENANT - timedelta(days=1)),
        Run(source_id=2, statut="ok", fin=MAINTENANT - timedelta(days=1)),
    ])
    db.add_all([
        Document(id=1, source_id=1, url="https://x.bf/1", type_doc="cr_conseil",
                 date_publication=date.today() - timedelta(days=90)),
        Document(id=2, source_id=2, url="https://y.bf/1", type_doc="loi",
                 date_publication=date.today()),
    ])
    db.commit()

    assert [e["slug"] for e in etat_sources(db)] == ["conseil_ministres", "legiburkina"]
