"""Republications du Quotidien : une attribution ne doit compter qu'une fois.

La DGCMEF reprend la même synthèse de résultats dans des numéros successifs
(cas constaté : 18 numéros pour une seule demande de prix SONATUR). Sans
empreinte, le total attribué à l'entreprise est multiplié par le nombre de
parutions.
"""

from app.extraction.marches import empreinte


def test_meme_attribution_republieee_a_la_meme_empreinte():
    """Deux numéros, une seule attribution : les champs de fond sont identiques,
    seul le Quotidien qui la porte change."""
    a = empreinte(
        "Demande de prix n°2026-006/DG-SONATUR/PRM du 27-04-2026",
        "226 TECH",
        28_700_000,
        "l'acquisition de logiciels ArchiCAD, QGIS et MS PROJECT (lot unique)",
    )
    b = empreinte(
        "Demande de prix n°2026-006/DG-SONATUR/PRM du 27-04-2026",
        "226 TECH",
        28_700_000,
        "l'acquisition de logiciels ArchiCAD, QGIS et MS PROJECT (lot unique)",
    )
    assert a == b


def test_empreinte_absorbe_la_mise_en_page_du_pdf():
    """Espaces multiples, retours à la ligne et casse viennent du découpage du
    tableau, pas d'une différence de fond."""
    assert empreinte("Réf   N°12", "ETS  WEND\nKUUNI", 1_000, "Objet  du   marché") == empreinte(
        "réf n°12", "ets wend kuuni", 1_000, "objet du marché"
    )


def test_montant_different_reste_une_attribution_distincte():
    ref, att, objet = "Réf N°12", "ETS WEND-KUUNI", "Fourniture de matériel"
    assert empreinte(ref, att, 1_000_000, objet) != empreinte(ref, att, 2_000_000, objet)


def test_lots_distincts_du_meme_appel_ne_se_confondent_pas():
    """Une même référence couvre souvent plusieurs lots, attribués à des
    entreprises différentes : l'empreinte ne doit surtout pas les fusionner."""
    ref = "Appel d'offres n°2026-004/MS/SG/DMP"
    assert empreinte(ref, "ETS ALPHA", 5_000_000, "lot 1 : matériel médical") != empreinte(
        ref, "ETS BETA", 7_000_000, "lot 2 : consommables"
    )
    # même attributaire, mais deux lots distincts du même appel
    assert empreinte(ref, "ETS ALPHA", 5_000_000, "lot 1 : matériel médical") != empreinte(
        ref, "ETS ALPHA", 5_000_000, "lot 2 : consommables"
    )


def test_attribution_sans_reference_reste_identifiable():
    """Le Quotidien omet parfois la référence : l'empreinte tient alors sur
    l'attributaire, le montant et l'objet - et distingue toujours deux
    attributions différentes."""
    assert empreinte(None, "COOL SHOP Sarl", 38_615_000, "fourniture de mobilier") == empreinte(
        "", "COOL SHOP Sarl", 38_615_000, "fourniture de mobilier"
    )
    assert empreinte(None, "COOL SHOP Sarl", 38_615_000, "fourniture de mobilier") != empreinte(
        None, "COOL SHOP Sarl", 38_615_000, "fourniture de fournitures de bureau"
    )


def test_montant_absent_ne_vaut_pas_montant_nul():
    assert empreinte("R", "A", None, "O") != empreinte("R", "A", 0, "O")
