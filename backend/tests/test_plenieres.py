"""Votes en séance plénière : ce que le registre affirme vient du compte rendu.

L'appel au modèle est remplacé par une réponse en dur ; ce qui est figé ici est
ce qui entoure cet appel - ne pas payer pour une séance sans vote, ne pas
enregistrer deux fois le même texte, ne pas repasser sur un compte rendu traité.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.extraction.plenieres as module
from app.extraction.plenieres import (
    ExtractionPleniere,
    VoteExtrait,
    cle_intitule,
    pertinent,
    traiter_lot,
)
from app.models import Base, Document, Source, VotePlenier

_TABLES = (Source, Document, VotePlenier)


def vote(intitule="projet de loi portant initiatives carbone", **champs):
    return VoteExtrait(intitule=intitule, nature="projet_loi", confiance=0.95, **champs)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _TABLES])
    with Session(engine) as session:
        session.add(Source(id=1, slug="pleniere", nom="Plénières",
                           url_base="https://www.assembleenationale.bf", type="institutionnel"))
        session.commit()
        yield session


def compte_rendu(db, n, texte="Les députés ont adopté le projet de loi.", jour=9):
    doc = Document(source_id=1, url=f"https://www.assembleenationale.bf/{n}", hash_contenu=str(n),
                   type_doc="compte_rendu_pleniere", titre=f"Séance {n}", texte_extrait=texte,
                   date_publication=date(2026, 11, jour), statut_extraction="ok")
    db.add(doc)
    db.commit()
    return doc


@pytest.fixture
def modele(monkeypatch):
    """Remplace l'appel LLM ; `appels` compte ce qui aurait été facturé."""
    etat = {"reponse": ExtractionPleniere(votes=[vote()]), "appels": 0}

    def faux(texte):
        etat["appels"] += 1
        return etat["reponse"]

    monkeypatch.setattr(module, "extraire", faux)
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    return etat


def test_un_vote_est_depose_a_valider_avec_la_date_de_la_seance(db, modele):
    modele["reponse"] = ExtractionPleniere(
        votes=[vote(unanimite=True, votants=71, pour=71, contre=0, abstentions=0)]
    )
    compte_rendu(db, 985)

    assert traiter_lot(db, 10) == (1, 1, 0, 0)

    v = db.scalars(select(VotePlenier)).one()
    assert v.statut_validation == "a_valider"
    assert v.date_seance == date(2026, 11, 9), "à défaut de date extraite, celle du compte rendu"
    assert (v.votants, v.pour, v.unanimite) == (71, 71, True)


def test_une_seance_sans_vote_ne_coute_aucun_appel(db, modele):
    compte_rendu(db, 900, texte="Séance de questions orales au gouvernement sur la santé.")

    assert traiter_lot(db, 10) == (1, 0, 1, 0)
    assert modele["appels"] == 0
    assert db.scalars(select(Document)).one().date_structuration is not None


def test_un_compte_rendu_traite_n_est_pas_repris(db, modele):
    compte_rendu(db, 985)
    traiter_lot(db, 10)

    assert traiter_lot(db, 10) == (0, 0, 0, 0)
    assert modele["appels"] == 1


def test_le_meme_texte_rapporte_deux_fois_n_est_enregistre_qu_une_fois(db, modele):
    """Le site publie parfois deux comptes rendus de la même séance."""
    compte_rendu(db, 985)
    compte_rendu(db, 986)
    modele["reponse"] = ExtractionPleniere(
        votes=[vote("Projet de loi portant Initiatives Carbone.")]
    )

    traiter_lot(db, 10)

    assert len(db.scalars(select(VotePlenier)).all()) == 1


def test_un_echec_du_modele_laisse_le_compte_rendu_en_file(db, monkeypatch):
    def casse(texte):
        raise RuntimeError("Sortie tronquée")

    monkeypatch.setattr(module, "extraire", casse)
    compte_rendu(db, 985)

    assert traiter_lot(db, 10) == (1, 0, 0, 1)
    assert db.scalars(select(Document)).one().date_structuration is None


def test_pre_filtre_et_cle():
    assert pertinent("Les députés adoptent la révision du règlement", "")
    assert not pertinent("Ouverture de la session", "Discours du président.")
    assert cle_intitule("Projet de loi portant Initiatives Carbone.") == cle_intitule(
        "projet de loi portant initiatives carbone"
    )
