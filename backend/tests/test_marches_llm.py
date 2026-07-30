"""Découpage du Quotidien avant appel LLM.

Un Quotidien fait 277 000 caractères en médiane, jusqu'à 1,1 million : il faut le
découper. Le repérage se fait sur « attributaire », pas sur les sections
« SYNTHÈSE DES RÉSULTATS » — celles-ci couvrent 99 % du texte et certains numéros
n'en contiennent aucune tout en publiant des attributions.

Ces tests portent sur le découpage, seule partie déterministe qui reste : la
lecture, elle, est confiée au LLM et se juge sur pièces.
"""

from app.extraction.marches_llm import AVANT, APRES, fenetres_candidates


def test_aucune_fenetre_sans_le_mot_cle():
    """Pas d'appel LLM sur un numéro qui ne publie aucune attribution."""
    assert fenetres_candidates("Avis de recrutement. Rectificatif.") == []
    assert fenetres_candidates("") == []
    assert fenetres_candidates(None) == []


def test_la_fenetre_englobe_le_contexte_avant_et_apres():
    """L'objet et l'autorité contractante précèdent l'attributaire, le montant
    le suit : une fenêtre trop serrée couperait l'un ou l'autre."""
    texte = "A" * 5000 + "Attributaire : ETS ALPHA" + "B" * 5000
    (fenetre,) = fenetres_candidates(texte)
    assert "Attributaire : ETS ALPHA" in fenetre
    assert fenetre.startswith("A" * 10)
    assert len(fenetre) == AVANT + APRES


def test_le_debut_du_texte_ne_deborde_pas():
    texte = "Attributaire : ETS ALPHA" + "B" * 3000
    (fenetre,) = fenetres_candidates(texte)
    assert fenetre.startswith("Attributaire")


def test_deux_mentions_proches_donnent_une_seule_fenetre():
    """Un tableau dense mentionne « attributaire » à chaque ligne. Sans fusion,
    on paierait dix appels pour dix extraits quasi identiques."""
    texte = "X" * 2000 + "attributaire A" + "Y" * 100 + "attributaire B" + "Z" * 2000
    fenetres = fenetres_candidates(texte)
    assert len(fenetres) == 1
    assert "attributaire A" in fenetres[0] and "attributaire B" in fenetres[0]


def test_deux_mentions_eloignees_donnent_deux_fenetres():
    texte = "X" * 500 + "attributaire A" + "Y" * 10000 + "attributaire B" + "Z" * 500
    fenetres = fenetres_candidates(texte)
    assert len(fenetres) == 2
    assert "attributaire A" in fenetres[0]
    assert "attributaire B" in fenetres[1]


def test_la_casse_est_ignoree():
    """Le Quotidien écrit « Attributaire », « ATTRIBUTAIRE » et « attributaire »
    selon les tableaux."""
    for graphie in ("Attributaire", "ATTRIBUTAIRE", "attributaire"):
        assert len(fenetres_candidates("X" * 2000 + graphie + "Y" * 2000)) == 1


def test_les_fenetres_couvrent_toutes_les_mentions():
    """Garde-fou : aucune attribution ne doit tomber entre deux fenêtres."""
    texte = ("bloc " * 400 + "attributaire ") * 6
    fenetres = fenetres_candidates(texte)
    assert sum(f.lower().count("attributaire") for f in fenetres) == texte.lower().count(
        "attributaire"
    )
