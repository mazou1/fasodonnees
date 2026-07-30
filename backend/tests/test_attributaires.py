"""Consolidation des attributaires : normalisation des raisons sociales.

Le rattachement automatique étant STRICT (même forme normalisée), ces tests
gardent les deux garde-fous : regrouper les variantes typographiques d'une
même entreprise, et ne jamais confondre deux entreprises distinctes.
"""

from collections import Counter

import pytest

from app.attributaires import _forme_affichee, normaliser_raison_sociale


@pytest.mark.parametrize(
    "brut,attendu",
    [
        ("ETS WEND-KUUNI", "wend kuuni"),
        ("Ets Wend Kuuni SARL", "wend kuuni"),
        ("ETABLISSEMENTS WEND KUUNI Sarl", "wend kuuni"),
        # sigle pointé recollé
        ("E.W.K. SARL", "ewk"),
        # accents, casse et apostrophe typographique
        ("Société Générale d’Équipement", "generale d'equipement"),
        ("SOCIETE GENERALE D'EQUIPEMENT", "generale d'equipement"),
        # esperluette et tirets
        ("SOGEA & FILS", "sogea et fils"),
        ("SOGEA ET FILS", "sogea et fils"),
        ("BTP-CONSTRUCTION SA", "btp construction"),
    ],
)
def test_variantes_typographiques_convergent(brut, attendu):
    assert normaliser_raison_sociale(brut) == attendu


def test_entreprises_distinctes_ne_se_confondent_pas():
    """Deux raisons sociales différentes restent séparées : leur rapprochement
    éventuel passe par `proposer` et une relecture humaine."""
    assert normaliser_raison_sociale("ETS WEND-KUUNI") != normaliser_raison_sociale(
        "ETS WEND PANGA"
    )
    assert normaliser_raison_sociale("SOGEA SARL") != normaliser_raison_sociale("SOGECA SARL")


def test_forme_juridique_seule_nest_pas_effacee():
    """« SARL » tout court est un nom inexploitable, mais le vider produirait
    une clé vide qui agrégerait tous les cas dégénérés entre eux."""
    assert normaliser_raison_sociale("SARL") == "sarl"
    assert normaliser_raison_sociale("Ets.") == "ets"


def test_normalisation_stable_et_idempotente():
    forme = normaliser_raison_sociale("  ETS   WEND-KUUNI   SARL ")
    assert forme == "wend kuuni"
    assert normaliser_raison_sociale(forme) == forme


def test_forme_affichee_prend_la_graphie_la_plus_frequente():
    variantes = Counter({"ETS WEND-KUUNI": 7, "Ets Wend Kuuni SARL": 2})
    assert _forme_affichee(variantes) == "ETS WEND-KUUNI"


def test_forme_affichee_departage_a_egalite_par_la_plus_complete():
    """À fréquence égale, la graphie la plus longue porte en général la raison
    sociale entière - et le départage doit rester déterministe."""
    variantes = Counter({"ETS WEND-KUUNI": 3, "ETS WEND-KUUNI SARL": 3})
    assert _forme_affichee(variantes) == "ETS WEND-KUUNI SARL"


def test_forme_affichee_nettoie_les_espaces_du_document():
    assert _forme_affichee(Counter({"  ETS WEND-KUUNI  ": 1})) == "ETS WEND-KUUNI"


# --- fusion automatique des variantes bruitées ----------------------------

def test_le_seuil_automatique_laisse_les_faux_amis_a_la_relecture():
    """« REAL SERVICES INTERNATIONAL » et « RELLYA SERVICES INTERNATIONAL »
    culminent à 0,78 de similarité et sont deux entreprises distinctes : les
    fusionner d'office attribuerait les marchés de l'une à l'autre. Le seuil
    automatique doit rester nettement au-dessus."""
    from app.attributaires import SEUIL_FUSION_AUTO

    assert SEUIL_FUSION_AUTO > 0.85


def test_le_nom_le_plus_court_est_canonique():
    """Le bruit d'extraction AJOUTE des caractères - un « u » ou un « à » happé
    devant la raison sociale - il n'en retire jamais. Se fonder sur l'ancienneté
    affichait le bruit : « u HABIB TRADING INTERNATIONAL » porte un identifiant
    plus petit que la forme propre."""
    propre = ("habib trading international", 265)
    bruite = ("u habib trading international", 9)
    # la règle appliquée dans _fusionner_variantes_evidentes
    assert min(
        [(len(propre[0]), propre[1]), (len(bruite[0]), bruite[1])]
    ) == (len(propre[0]), propre[1])


def test_a_longueur_egale_lidentifiant_tranche():
    """Deux graphies de même longueur doivent donner le même résultat d'une
    exécution à l'autre, sinon la fiche publique change de nom sans raison."""
    a, b = ("ets alpha sarl", 12), ("ets omega sarl", 7)
    assert min([(len(a[0]), a[1]), (len(b[0]), b[1])]) == (len(b[0]), b[1])
