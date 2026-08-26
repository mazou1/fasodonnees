"""Surveillance des sources : muettes et taries.

Août 2026 : le dernier compte rendu du Conseil des ministres datait du
30 juillet, et rien ne l'a signalé. Le collecteur passait, réussissait, et la
surveillance ne regardait que ça.

Ces tests figent deux exigences opposées, dont l'équilibre fait toute la valeur
de l'alerte : elle doit voir une source qui se tait, et elle doit se taire sur
les creux normaux. Une alerte toujours allumée est une alerte qu'on n'ouvre
plus - et c'est le premier essai de ce module qui l'a montré, en déclarant
taries cinq sources dont trois publiaient normalement.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ingestion.surveillance import MINIMUM_POINTS, etat_sources
from app.models import Base, Document, Run, Source

_TABLES = (Source, Document, Run)

MAINTENANT = datetime.now(timezone.utc)
AUJOURDHUI = MAINTENANT.date()


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _TABLES])
    with Session(engine) as session:
        yield session


def source(db, slug="conseil_ministres", cadence="hebdo", ident=1):
    """Un slug du registre : `etat_sources` écarte les sources sans collecteur."""
    db.add(Source(id=ident, slug=slug, nom=slug, url_base=f"https://{ident}.bf",
                  type="institutionnel", cadence=cadence))
    return db


def run_reussi(db, il_y_a_jours, source_id=1):
    db.add(Run(source_id=source_id, statut="ok",
               fin=MAINTENANT - timedelta(days=il_y_a_jours)))


def publie(db, *jours_avant, source_id=1, collecte_il_y_a=None):
    """Une publication par âge donné, en jours avant aujourd'hui."""
    for n in jours_avant:
        publiee = AUJOURDHUI - timedelta(days=n)
        db.add(Document(
            source_id=source_id,
            url=f"https://{source_id}.bf/{n}",
            type_doc="cr_conseil",
            date_publication=publiee,
            date_collecte=MAINTENANT - timedelta(days=collecte_il_y_a if collecte_il_y_a
                                                 is not None else n),
        ))


def rythme_regulier(db, tous_les, jusqua, source_id=1):
    """Des publications régulières, la plus récente il y a `jusqua` jours."""
    publie(db, *[jusqua + tous_les * i for i in range(12)], source_id=source_id)


def etat(db, slug="conseil_ministres"):
    db.commit()
    return next(e for e in etat_sources(db) if e["slug"] == slug)


# --- les deux pannes, distinguées ----------------------------------------

def test_une_source_a_jour_ne_declenche_rien(db):
    source(db)
    run_reussi(db, il_y_a_jours=1)
    rythme_regulier(db, tous_les=7, jusqua=3)

    resultat = etat(db)
    assert (resultat["muette"], resultat["tarie"]) == (False, False)


def test_un_collecteur_qui_ne_passe_plus_rend_la_source_muette(db):
    source(db)
    run_reussi(db, il_y_a_jours=20)  # cadence hebdo : seuil à 10 jours
    rythme_regulier(db, tous_les=7, jusqua=1)

    assert etat(db)["muette"] is True


def test_une_source_qui_repond_sans_rien_publier_est_tarie(db):
    """Le cas d'août 2026 : tous les voyants au vert, et pourtant plus rien."""
    source(db)
    run_reussi(db, il_y_a_jours=1)
    rythme_regulier(db, tous_les=7, jusqua=120)

    resultat = etat(db)
    assert (resultat["muette"], resultat["tarie"]) == (False, True)
    assert resultat["silence_jours"] == 120


def test_une_source_muette_nest_pas_dite_tarie_en_plus(db):
    """Le collecteur ne passe pas : on ne sait rien de ce que la source publie.
    Deux alertes pour une panne feraient chercher deux causes."""
    source(db)
    run_reussi(db, il_y_a_jours=40)
    rythme_regulier(db, tous_les=7, jusqua=120)

    resultat = etat(db)
    assert (resultat["muette"], resultat["tarie"]) == (True, False)


def test_une_reecriture_de_vieille_page_ne_masque_pas_le_silence(db):
    """Le gouvernement retouche ses archives : la collecte crée un document
    daté d'aujourd'hui alors que RIEN de neuf n'a été publié. Juger sur
    `date_collecte` rendrait la source verte à tort."""
    source(db)
    run_reussi(db, il_y_a_jours=1)
    publie(db, *[120 + 7 * i for i in range(12)], collecte_il_y_a=0)

    assert etat(db)["tarie"] is True


# --- le seuil vient du rythme de la source, pas d'une constante ----------

def test_le_creux_dete_du_conseil_des_ministres_ne_declenche_pas_lalerte(db):
    """Mesuré en production : le plus long silence de l'année sur cette source
    est de 28 jours (creux d'août 2025 comme 2026). Les 27 jours de silence du
    26 août 2026 ne sont donc pas une panne."""
    source(db, cadence="hebdo")
    run_reussi(db, il_y_a_jours=1)
    publie(db, 27, 55, 62, 69, 76, 83, 90, 97)  # un creux de 28 j dans l'historique

    resultat = etat(db)
    # 28 jours observés majorés de moitié font 43 ; le plancher hebdomadaire,
    # à 45, l'emporte de peu. Les deux voies mènent au même verdict, ce qui est
    # rassurant : le réglage ne tient pas à un seul chiffre.
    assert resultat["seuil_jours"] == 45
    assert (resultat["silence_jours"], resultat["tarie"]) == (27, False)


def test_une_source_rare_nest_pas_taxee_de_silence(db):
    """L'ASCE-LC est interrogée chaque semaine et publie quelques rapports par
    an. Un seuil fixé sur la cadence d'interrogation la déclarerait tarie en
    permanence - c'est ce qu'a fait le premier essai en production."""
    source(db, slug="asce_lc", cadence="hebdo")
    run_reussi(db, il_y_a_jours=1)
    publie(db, 75, 250, 300, 330, 350)  # publications espacées de plusieurs mois

    resultat = etat(db, "asce_lc")
    assert resultat["seuil_jours"] > 75
    assert resultat["tarie"] is False


def test_une_source_quotidienne_qui_sarrete_est_vue_vite(db):
    """Légiburkina publie tous les deux ou trois jours : 50 jours de silence
    n'y ont pas la même signification que sur un conseil hebdomadaire."""
    source(db, slug="legiburkina", cadence="quotidien")
    run_reussi(db, il_y_a_jours=1)
    publie(db, 50, *[52 + 3 * i for i in range(15)])

    resultat = etat(db, "legiburkina")
    assert resultat["seuil_jours"] < 50
    assert resultat["tarie"] is True


def test_les_fonds_anciens_ne_gonflent_pas_le_seuil(db):
    """Légiburkina archive des textes du XIXe siècle : sur l'historique brut,
    son plus grand écart dépasse 270 000 jours et aucun silence ne serait
    jamais anormal. Seule l'année écoulée compte."""
    source(db, slug="legiburkina", cadence="quotidien")
    run_reussi(db, il_y_a_jours=1)
    publie(db, 50, *[52 + 3 * i for i in range(15)])
    db.add(Document(source_id=1, url="https://1.bf/ancien", type_doc="loi",
                    date_publication=date(1898, 5, 1)))

    assert etat(db, "legiburkina")["tarie"] is True


# --- ce qu'on refuse de juger --------------------------------------------

def test_un_collecteur_qui_necrit_pas_de_documents_nest_pas_juge(db):
    """Assemblée et Finances alimentent les tables de députés et de budget, pas
    la table des documents. Les déclarer taries serait une alerte permanente
    sur une chaîne qui fonctionne."""
    source(db, slug="assemblee", cadence="quotidien")
    run_reussi(db, il_y_a_jours=1)

    resultat = etat(db, "assemblee")
    assert (resultat["tarie"], resultat["seuil_jours"]) == (False, None)


def test_une_source_a_peine_branchee_nest_pas_jugee(db):
    """Deux publications ne font pas un rythme : mieux vaut ne rien dire que
    d'accuser une source sur un historique qui ne veut rien dire."""
    source(db, slug="presidence", cadence="quotidien")
    run_reussi(db, il_y_a_jours=1)
    publie(db, *range(200, 200 + MINIMUM_POINTS - 1))

    assert etat(db, "presidence")["tarie"] is False


# --- restitution ----------------------------------------------------------

def test_les_sources_en_alerte_remontent_en_tete(db):
    """La liste sert à ouvrir /sources/etat et voir le problème sans chercher."""
    source(db, slug="conseil_ministres", cadence="hebdo", ident=1)
    source(db, slug="legiburkina", cadence="quotidien", ident=2)
    run_reussi(db, il_y_a_jours=1, source_id=1)
    run_reussi(db, il_y_a_jours=1, source_id=2)
    rythme_regulier(db, tous_les=7, jusqua=200, source_id=1)  # tarie
    rythme_regulier(db, tous_les=3, jusqua=1, source_id=2)  # à jour

    assert [e["slug"] for e in etat_sources(db)] == ["conseil_ministres", "legiburkina"]
