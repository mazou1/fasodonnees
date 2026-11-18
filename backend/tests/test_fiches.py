"""Fiches de lecture (Conseil constitutionnel, ASCE-LC).

L'appel au modèle est remplacé ; ce qui est figé ici, c'est qu'une fiche n'est
jamais publiée sans validation, qu'un document n'en reçoit qu'une, et qu'un
rapport de mille pages ne part pas entier dans un appel.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.extraction.fiches as module
from app.api.routes import fiches_validees
from app.extraction.fiches import (
    DEBUT,
    FIN,
    FicheConstitutionnelle,
    FicheControle,
    extrait_utile,
    genre_de,
    traiter_lot,
)
from app.models import Base, Document, FicheDocument, Source

_TABLES = (Source, Document, FicheDocument)
TEXTE = "Le Conseil constitutionnel, saisi par le Premier ministre, décide. " * 20


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _TABLES])
    with Session(engine) as session:
        session.add(Source(id=1, slug="conseil_constitutionnel", nom="CC",
                           url_base="https://cc.gov.bf", type="institutionnel"))
        session.commit()
        yield session


def document(db, n, type_doc="decision_constitutionnelle", texte=TEXTE):
    doc = Document(source_id=1, url=f"https://cc.gov.bf/{n}.pdf", hash_contenu=str(n),
                   type_doc=type_doc, titre=f"Décision n° 2016-{n:03d} CC",
                   texte_extrait=texte, statut_extraction="ocr")
    db.add(doc)
    db.commit()
    return doc


@pytest.fixture
def modele(monkeypatch):
    etat = {"appels": []}

    def faux(genre, texte):
        etat["appels"].append((genre, texte))
        if genre == "constitutionnel":
            return FicheConstitutionnelle(
                objet="Conformité de la loi organique portant statut de la magistrature",
                categorie="controle_constitutionnalite", partie="le Premier ministre",
                issue="conforme", resume="Le Conseil déclare la loi conforme.",
                points=["Article 1 : la loi est conforme.", "  ", "Article 2 : publication."],
                date_document=date(2016, 5, 12), confiance=0.93,
            )
        return FicheControle(
            objet="Audit de la commune de X", categorie="audit_controle", partie="Commune de X",
            resume="L'audit porte sur 2019-2021.", points=["Irrégularités de 12 millions FCFA."],
            confiance=0.9,
        )

    monkeypatch.setattr(module, "extraire", faux)
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    return etat


def test_une_fiche_est_deposee_a_valider_et_reste_invisible_avant_validation(db, modele):
    doc = document(db, 19)

    assert traiter_lot(db, 10) == (1, 1, 0)

    fiche = db.scalars(select(FicheDocument)).one()
    assert (fiche.genre, fiche.issue, fiche.statut_validation) == (
        "constitutionnel", "conforme", "a_valider",
    )
    assert fiche.points == ["Article 1 : la loi est conforme.", "Article 2 : publication."]
    assert fiches_validees(db, [doc.id]) == {}, "rien n'est publié avant relecture"

    fiche.statut_validation = "valide"
    db.commit()
    publiee = fiches_validees(db, [doc.id])[doc.id]
    assert publiee["issue_libelle"] == "Conforme à la Constitution"
    assert publiee["categorie_libelle"] == "Contrôle de constitutionnalité"


def test_un_document_ne_recoit_qu_une_fiche(db, modele):
    document(db, 19)
    traiter_lot(db, 10)

    assert traiter_lot(db, 10) == (0, 0, 0)
    assert len(modele["appels"]) == 1


def test_un_rapport_de_controle_n_a_pas_d_issue(db, modele):
    document(db, 7, type_doc="rapport_controle")
    traiter_lot(db, 10)

    fiche = db.scalars(select(FicheDocument)).one()
    assert (fiche.genre, fiche.issue, fiche.partie) == ("controle", None, "Commune de X")


def test_un_document_sans_texte_n_est_ni_traite_ni_marque(db, modele):
    """Un scan pas encore lu par l'OCR doit pouvoir être repris plus tard."""
    doc = document(db, 3, texte="Télécharger")

    assert traiter_lot(db, 10) == (0, 0, 0)
    assert modele["appels"] == [] and doc.date_structuration is None


def test_un_rapport_fleuve_n_est_transmis_que_par_son_debut_et_sa_fin(db, modele):
    long = "A" * 400_000 + "CONCLUSION ET RECOMMANDATIONS"
    document(db, 8, type_doc="rapport_controle", texte=long)
    traiter_lot(db, 10)

    transmis = modele["appels"][0][1]
    assert len(transmis) < DEBUT + FIN + 500
    assert "CONCLUSION ET RECOMMANDATIONS" in transmis and "passage non transmis" in transmis
    assert extrait_utile("court") == "court"


def test_un_echec_laisse_le_document_en_file(db, monkeypatch):
    def casse(genre, texte):
        raise RuntimeError("Sortie tronquée")

    monkeypatch.setattr(module, "extraire", casse)
    doc = document(db, 19)

    assert traiter_lot(db, 10) == (1, 0, 1)
    assert doc.date_structuration is None
    assert db.scalars(select(FicheDocument)).all() == []


def test_genre_par_type():
    assert genre_de("avis_constitutionnel") == "constitutionnel"
    assert genre_de("affaire_anticorruption") == "controle"
    assert genre_de("cr_conseil") is None
