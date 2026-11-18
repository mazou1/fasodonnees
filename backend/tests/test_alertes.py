"""Alertes Telegram : la conversation du bot et ce qui part aux abonnés.

Deux choses ne doivent jamais arriver : prévenir quelqu'un d'une donnée non
validée, et lui envoyer deux fois la même nouveauté.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.alertes.bot import MAX_ABONNEMENTS, charge_utile, normaliser, repondre
from app.alertes.envoi import envoyer_alertes
from app.diffusion.reseaux import ErreurReseau
from app.models import (
    Abonnement,
    AlerteEnvoyee,
    Base,
    Decision,
    Document,
    Nomination,
    Personne,
    Source,
    Structure,
    VotePlenier,
)

_TABLES = (Source, Document, Personne, Structure, Nomination, Decision, VotePlenier,
           Abonnement, AlerteEnvoyee)
MAINTENANT = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


class FauxTelegram:
    def __init__(self, refuse=()):
        self.envois = []
        self.refuse = set(refuse)

    def envoyer(self, chat_id, texte):
        if chat_id in self.refuse:
            raise ErreurReseau("HTTP 403 : Forbidden: bot was blocked by the user")
        self.envois.append((chat_id, texte))
        return "1"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _TABLES])
    with Session(engine) as session:
        session.add(Source(id=1, slug="conseil_ministres", nom="CM",
                           url_base="https://gouvernement.gov.bf", type="institutionnel"))
        session.add(Document(id=10, source_id=1, url="https://g/cm31", hash_contenu="h",
                             type_doc="cr_conseil", titre="CM n°31", statut_extraction="ok",
                             date_publication=date(2026, 11, 5),
                             date_collecte=datetime(2026, 11, 14, tzinfo=timezone.utc)))
        session.add(Personne(id=1, nom_complet="Pingdwendé Gilbert OUEDRAOGO",
                             nom_normalise="pingdwende gilbert ouedraogo"))
        session.add(Structure(id=5, nom="Ministère de la Santé", sigle="MS", type="ministere"))
        session.commit()
        yield session


def nomination(db, statut="valide", **champs):
    n = Nomination(document_id=10, personne_id=1, structure_id=5,
                   poste="Directeur général des hôpitaux", statut_validation=statut, **champs)
    db.add(n)
    db.commit()
    return n


def decision(db, objet, statut="valide"):
    d = Decision(document_id=10, objet=objet, ministere="Santé", type="adoption_decret",
                 statut_validation=statut)
    db.add(d)
    db.commit()
    return d


# ── la conversation ───────────────────────────────────────────────────────

def test_suivre_un_mot_puis_le_lister_et_l_arreter(db):
    assert "C'est noté" in repondre(db, "42", "/suivre Budget de l'État")
    assert "1. Budget de l'État" in repondre(db, "42", "/liste")
    assert "arrêtée" in repondre(db, "42", "/arreter 1")
    assert db.scalars(select(Abonnement)).all() == []


def test_le_meme_mot_n_est_pas_suivi_deux_fois_quels_que_soient_les_accents(db):
    repondre(db, "42", "/suivre Ouédraogo")
    assert "déjà" in repondre(db, "42", "/suivre OUEDRAOGO")
    assert len(db.scalars(select(Abonnement)).all()) == 1


def test_un_mot_trop_court_est_refuse(db):
    assert "au moins" in repondre(db, "42", "/suivre le")
    assert db.scalars(select(Abonnement)).all() == []


def test_le_nombre_d_alertes_est_plafonne(db):
    for i in range(MAX_ABONNEMENTS):
        repondre(db, "42", f"/suivre motcle{i}")
    assert "maximum" in repondre(db, "42", "/suivre encore")
    assert len(db.scalars(select(Abonnement)).all()) == MAX_ABONNEMENTS


def test_les_liens_du_site_abonnent_a_une_personne_une_institution_ou_un_mot(db):
    assert "OUEDRAOGO" in repondre(db, "42", "/start p1")
    assert "Nominations - MS" in repondre(db, "42", "/start s5")
    assert "marchés publics" in repondre(db, "42", f"/start {charge_utile('marchés publics')}")
    genres = sorted(a.genre for a in db.scalars(select(Abonnement)))
    assert genres == ["mot", "personne", "structure"]
    assert "n'existe plus" in repondre(db, "42", "/start p999")


def test_arreter_tout_efface_les_donnees_de_la_conversation(db):
    repondre(db, "42", "/suivre budget")
    repondre(db, "43", "/suivre budget")
    assert "effacées" in repondre(db, "42", "/arreter tout")
    assert [a.destinataire for a in db.scalars(select(Abonnement))] == ["43"]


def test_un_message_libre_propose_la_commande_sans_abonner(db):
    assert "/suivre mines" in repondre(db, "42", "mines")
    assert db.scalars(select(Abonnement)).all() == []


def test_normaliser():
    assert normaliser("  Ouédraogo, P. Gilbert ") == "ouedraogo p gilbert"


# ── l'envoi ───────────────────────────────────────────────────────────────

def test_une_nomination_validee_previent_celui_qui_suit_la_personne(db):
    repondre(db, "42", "/start p1")
    nomination(db)
    telegram = FauxTelegram()

    bilan = envoyer_alertes(db, telegram, MAINTENANT)

    assert bilan["messages"] == 1
    chat, texte = telegram.envois[0]
    assert chat == "42" and "Directeur général des hôpitaux" in texte
    assert "/personnes/1" in texte


def test_rien_ne_part_pour_une_donnee_non_validee(db):
    repondre(db, "42", "/start p1")
    repondre(db, "42", "/suivre hôpitaux")
    nomination(db, statut="a_valider")
    decision(db, "Construction de deux hôpitaux", statut="a_valider")
    telegram = FauxTelegram()

    envoyer_alertes(db, telegram, MAINTENANT)

    assert telegram.envois == []


def test_la_meme_nouveaute_ne_part_qu_une_fois(db):
    repondre(db, "42", "/suivre hôpitaux")
    nomination(db)
    telegram = FauxTelegram()

    envoyer_alertes(db, telegram, MAINTENANT)
    envoyer_alertes(db, telegram, MAINTENANT)

    assert len(telegram.envois) == 1


def test_plusieurs_correspondances_tiennent_dans_un_seul_message(db):
    repondre(db, "42", "/suivre santé")
    for i in range(12):
        decision(db, f"Décret n°{i} relatif à la santé publique")
    telegram = FauxTelegram()

    bilan = envoyer_alertes(db, telegram, MAINTENANT)

    assert len(telegram.envois) == 1 and bilan["elements"] == 12
    assert "12 nouveautés" in telegram.envois[0][1] and "4 autres" in telegram.envois[0][1]


def test_un_mot_cle_ne_s_accroche_pas_a_un_morceau_de_mot(db):
    repondre(db, "42", "/suivre mine")
    decision(db, "Nomination d'un ministre délégué")
    telegram = FauxTelegram()

    envoyer_alertes(db, telegram, MAINTENANT)

    assert telegram.envois == []


def test_suivre_une_institution_ne_previent_que_de_ses_nominations(db):
    repondre(db, "42", "/start s5")
    nomination(db)
    decision(db, "Décret sur la santé")
    telegram = FauxTelegram()

    envoyer_alertes(db, telegram, MAINTENANT)

    assert len(telegram.envois) == 1 and "1 nouveauté" in telegram.envois[0][1]


def test_un_document_ancien_ne_declenche_rien(db):
    """Un rattrapage d'archives ne doit pas inonder les abonnés."""
    db.get(Document, 10).date_publication = date(2024, 3, 1)
    db.commit()
    repondre(db, "42", "/suivre hôpitaux")
    nomination(db)
    telegram = FauxTelegram()

    envoyer_alertes(db, telegram, MAINTENANT)

    assert telegram.envois == []


def test_un_abonne_qui_a_bloque_le_bot_est_oublie(db):
    repondre(db, "42", "/suivre hôpitaux")
    nomination(db)

    bilan = envoyer_alertes(db, FauxTelegram(refuse={"42"}), MAINTENANT)

    assert bilan["desabonnes"] == 1
    assert db.scalars(select(Abonnement)).all() == []
