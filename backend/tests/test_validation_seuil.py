"""Validation en masse par seuil de confiance.

Relire 8 000 nominations une par une n'est pas tenable : le seuil est ce qui
rend la file de `/admin` praticable. Mais valider en masse est irréversible du
point de vue de l'usage - les entités deviennent publiques. Ces tests figent
donc les deux garde-fous : rien ne passe sous le seuil, et rien ne passe SANS
score tant qu'on ne l'a pas demandé explicitement.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.admin import _seuil_demande
from app.models import Base, Decision, Marche, Nomination
from app.validation import SEUIL_DEFAUT, compter_a_valider, valider_par_seuil

# Le modèle Document porte du JSONB (PostgreSQL) : on ne crée que les tables
# nécessaires, sans lui - SQLite n'impose pas les clés étrangères.
_TABLES = (Decision, Nomination, Marche)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _TABLES])
    with Session(engine) as session:
        yield session


def decision(score, statut="a_valider"):
    return Decision(
        document_id=1, type="rapport", objet="objet",
        score_confiance=score, statut_validation=statut,
    )


def statuts(db, modele):
    return sorted(
        db.execute(select(modele.score_confiance, modele.statut_validation)).all(),
        key=lambda ligne: (ligne[0] is None, ligne[0] or 0),
    )


# --- le seuil -------------------------------------------------------------

def test_ce_qui_atteint_le_seuil_est_valide_le_reste_attend(db):
    db.add_all([decision(0.95), decision(0.9), decision(0.6)])
    db.commit()

    rapport = valider_par_seuil(db, 0.9, modeles=[Decision])

    assert rapport["total"] == 2, "le seuil est inclusif : 0,9 atteint 0,9"
    assert statuts(db, Decision) == [
        (0.6, "a_valider"),
        (0.9, "valide"),
        (0.95, "valide"),
    ]
    assert rapport["lignes"][0]["restants"] == 1


def test_un_verdict_humain_deja_rendu_nest_jamais_recouvert(db):
    """Un rejet est une décision humaine : aucun seuil ne doit la renverser."""
    db.add_all([decision(0.99, statut="rejete")])
    db.commit()

    rapport = valider_par_seuil(db, 0.5, modeles=[Decision])

    assert rapport["total"] == 0
    assert statuts(db, Decision) == [(0.99, "rejete")]


# --- les lignes sans score ------------------------------------------------

def test_une_ligne_sans_score_nest_jamais_validee_par_defaut(db):
    """Les marchés viennent d'une extraction déterministe, sans score : aucun
    signal automatique ne les appuie, ils relèvent de la relecture."""
    db.add_all([Marche(document_id=1, objet="lot 1", score_confiance=None, statut_validation="a_valider")])
    db.commit()

    rapport = valider_par_seuil(db, 0.0, modeles=[Marche])

    assert rapport["total"] == 0
    assert rapport["lignes"][0]["sans_score"] == 1
    assert statuts(db, Marche) == [(None, "a_valider")]


def test_les_lignes_sans_score_passent_sur_demande_explicite(db):
    db.add_all([Marche(document_id=1, objet="lot 1", score_confiance=None, statut_validation="a_valider")])
    db.commit()

    rapport = valider_par_seuil(db, 0.9, modeles=[Marche], inclure_sans_score=True)

    assert rapport["total"] == 1
    assert statuts(db, Marche) == [(None, "valide")]


# --- portée ---------------------------------------------------------------

def test_un_type_non_demande_ne_bouge_pas(db):
    """Cocher « décisions » ne doit pas emporter les marchés au passage."""
    db.add_all([decision(0.99), Marche(document_id=1, objet="lot 1", score_confiance=0.99,
                                       statut_validation="a_valider")])
    db.commit()

    valider_par_seuil(db, 0.9, modeles=[Decision])

    assert statuts(db, Marche) == [(0.99, "a_valider")]


def test_compter_naffecte_rien(db):
    """La prévisualisation de /admin doit être sans effet de bord : elle sert
    justement à décider si l'on valide."""
    db.add_all([decision(0.95), decision(0.6)])
    db.commit()

    compte = compter_a_valider(db, Decision, 0.9)

    assert compte == {"total": 2, "au_seuil": 1, "sans_score": 0}
    assert statuts(db, Decision) == [(0.6, "a_valider"), (0.95, "a_valider")]


# --- l'annuaire suit ------------------------------------------------------

def test_valider_des_nominations_reconstruit_lannuaire(db, monkeypatch):
    """Une nomination validée doit apparaître dans l'annuaire tout de suite :
    sinon l'administrateur devrait lancer `python -m app.annuaire` à la main."""
    import app.annuaire

    appels = []
    monkeypatch.setattr(app.annuaire, "consolider", lambda session: appels.append(session) or 7)
    db.add_all([Nomination(document_id=1, personne_id=1, poste="Directeur général", type="nomination",
                           score_confiance=0.95, statut_validation="a_valider")])
    db.commit()

    rapport = valider_par_seuil(db, 0.9, modeles=[Nomination])

    assert appels, "l'annuaire n'a pas été reconstruit après validation"
    assert rapport["mandats"] == 7


def test_sans_nomination_validee_lannuaire_nest_pas_reconstruit(db, monkeypatch):
    """Reconstruire pour rien coûterait quelques secondes à chaque clic."""
    import app.annuaire

    monkeypatch.setattr(
        app.annuaire, "consolider",
        lambda session: pytest.fail("annuaire reconstruit sans nomination validée"),
    )
    db.add_all([decision(0.95)])
    db.commit()

    assert valider_par_seuil(db, 0.9, modeles=[Decision])["mandats"] is None


# --- le seuil saisi dans /admin -------------------------------------------

@pytest.mark.parametrize(
    "saisie,attendu",
    [
        ("0.85", 0.85),
        ("0,85", 0.85),  # séparateur décimal français
        ("2", 1.0),  # borné : un seuil au-dessus de 1 ne validerait plus rien
        ("-1", 0.0),
        ("", SEUIL_DEFAUT),
        (None, SEUIL_DEFAUT),
        ("beaucoup", SEUIL_DEFAUT),
    ],
)
def test_le_seuil_saisi_est_toujours_exploitable(saisie, attendu):
    assert _seuil_demande(saisie) == attendu
