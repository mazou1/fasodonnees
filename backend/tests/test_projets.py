"""Rapprochement annonce → attribution → livraison.

Le risque de ce module n'est pas de rater un rapprochement (un humain relit la
liste), c'est d'en proposer un faux avec assurance : sur une plateforme de
transparence, relier à tort une inauguration à un marché serait une accusation
implicite. Ces tests protègent donc la PRÉCISION.
"""

import math

from app.projets import (
    SEUIL_IDENTIFIANT,
    Piece,
    poids_rarete,
    proximite_montants,
    score,
    similarite_tokens,
    tokens_distinctifs,
)


def piece(genre, id_, libelle, montant=None, secteur=None, region=None, date=None):
    ordre = {"engagement": 0, "marche": 1, "realisation": 2}[genre]
    return Piece(genre, id_, libelle, tokens_distinctifs(libelle), montant, secteur,
                 region, ordre, date)


# --- tokens ---------------------------------------------------------------

def test_le_vocabulaire_des_travaux_publics_est_ecarte():
    """« Construction de… au profit de… » décrit la moitié du corpus : ces mots
    ne peuvent pas servir à identifier un projet."""
    tokens = tokens_distinctifs(
        "Travaux de construction et d'équipement au profit du Ministère de la Santé"
    )
    for generique in ("travaux", "construction", "equipement", "profit", "ministere"):
        assert generique not in tokens
    assert "sante" in tokens


def test_les_nombres_et_sigles_sont_conserves():
    """« 306 lits », « 26,4 MW », « R+5 » portent souvent l'identité du projet."""
    tokens = tokens_distinctifs("Construction d'un CHR de 306 lits et d'un immeuble R+5")
    assert "306" in tokens
    assert "lits" in tokens
    assert "r+5" in tokens
    assert "chr" in tokens


def test_accents_et_casse_ne_separent_pas():
    assert tokens_distinctifs("Réhabilitation de l'Hôpital de Gaoua") == tokens_distinctifs(
        "rehabilitation de l hopital de GAOUA"
    )


# --- pondération par la rareté --------------------------------------------

def test_un_mot_rare_pese_plus_quun_mot_frequent():
    corpus = [{"hopital", "gaoua"}] + [{"hopital", f"ville{i}"} for i in range(50)]
    poids = poids_rarete(corpus)
    assert poids["gaoua"] > poids["hopital"]


def test_partager_un_mot_rare_vaut_mieux_que_partager_trois_mots_courants():
    """Cas réel : « CHU de Bogodogo » et un marché « au profit du centre
    hospitalier universitaire » partagent trois mots — tous fréquents, et le
    toponyme qui identifie manque. Une paire qui partage le toponyme doit
    passer devant."""
    corpus = [{"centre", "hospitalier", "universitaire", f"ville{i}"} for i in range(60)]
    corpus += [{"centre", "hospitalier", "universitaire", "bogodogo"}]
    poids = poids_rarete(corpus)

    courants = similarite_tokens(
        {"centre", "hospitalier", "universitaire", "bogodogo"},
        {"centre", "hospitalier", "universitaire", "materiel"},
        poids,
    )
    rare = similarite_tokens(
        {"centre", "hospitalier", "bogodogo"}, {"hospitalier", "bogodogo"}, poids
    )
    assert rare > courants


def test_sans_ponderation_le_dice_classique_est_utilise():
    assert similarite_tokens({"a", "b"}, {"a", "b"}) == 1.0
    assert similarite_tokens({"a", "b"}, {"c", "d"}) == 0.0
    assert similarite_tokens(set(), {"a"}) == 0.0


# --- montants -------------------------------------------------------------

def test_proximite_des_montants():
    assert proximite_montants(1_000_000, 1_000_000) == 1.0
    # un marché ne couvre souvent qu'un lot de l'annonce : le rapport 1→4 reste toléré
    assert 0 < proximite_montants(1_000_000, 4_000_000) < 1.0
    assert proximite_montants(1_000, 1_000_000_000) == 0.0
    assert proximite_montants(None, 1_000) is None
    assert proximite_montants(0, 1_000) is None


# --- score ----------------------------------------------------------------

def test_sans_mot_identifiant_commun_le_score_est_penalise():
    """Garde-fou de précision : deux libellés qui ne partagent que des mots
    courants ne décrivent pas le même projet."""
    corpus = [{"centre", "hospitalier", f"ville{i}"} for i in range(60)]
    poids = poids_rarete(corpus)
    a = piece("marche", 1, "Acquisition de matériel pour le centre hospitalier")
    b = piece("realisation", 2, "Centre hospitalier de Bogodogo")
    valeur, indices = score(a, b, poids)
    assert indices["mot_identifiant"].startswith("aucun")
    sans_penalite, _ = score(a, b, None)
    assert valeur < sans_penalite


def test_le_seuil_didentification_ne_depend_pas_de_la_taille_du_corpus():
    """Le seuil est exprimé en IDF (log(1/0,015)) : un token présent dans 1,5 %
    du corpus est à la limite, que le corpus fasse 100 ou 10 000 pièces."""
    for n in (200, 1_000, 10_000):
        rares, courants = round(n * 0.005), round(n * 0.10)
        corpus = []
        for i in range(n):
            tokens = {f"piece{i}"}
            if i < rares:
                tokens.add("toponyme")  # 0,5 % du corpus → identifiant
            if i < courants:
                tokens.add("hospitalier")  # 10 % du corpus → trop courant
            corpus.append(tokens)
        poids = poids_rarete(corpus)
        assert poids["toponyme"] > SEUIL_IDENTIFIANT
        assert poids["hospitalier"] < SEUIL_IDENTIFIANT
    assert math.isclose(SEUIL_IDENTIFIANT, math.log(1 / 0.015))


def test_une_chronologie_impossible_penalise():
    """On annonce avant d'attribuer : une attribution antérieure à son annonce
    est un signal de rapprochement douteux."""
    from datetime import date

    a = piece("engagement", 1, "Bitumage de la voirie de Bobo-Dioulasso", date=date(2026, 6, 1))
    tard = piece("marche", 2, "Bitumage de la voirie de Bobo-Dioulasso", date=date(2026, 7, 1))
    tot = piece("marche", 3, "Bitumage de la voirie de Bobo-Dioulasso", date=date(2025, 1, 1))
    assert score(a, tard)[1]["chronologie"] == "plausible"
    assert score(a, tot)[1]["chronologie"].startswith("incohérente")
    assert score(a, tot)[0] < score(a, tard)[0]


def test_secteurs_divergents_penalisent():
    a = piece("marche", 1, "Forage de puits à Nasso", secteur="Eau & assainissement")
    meme = piece("realisation", 2, "Forage de puits à Nasso", secteur="Eau & assainissement")
    autre = piece("realisation", 3, "Forage de puits à Nasso", secteur="Éducation")
    assert score(a, meme)[0] > score(a, autre)[0]
    assert score(a, autre)[1]["secteur"] == "Eau & assainissement ≠ Éducation"


def test_le_score_reste_borne():
    a = piece("engagement", 1, "Barrage de Samendéni", montant=1_000_000, secteur="Eau")
    b = piece("realisation", 2, "Barrage de Samendéni", montant=1_000_000, secteur="Eau")
    valeur, _ = score(a, b)
    assert 0.0 <= valeur <= 1.0
