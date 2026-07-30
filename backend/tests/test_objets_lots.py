"""L'objet d'un marché doit être celui du journal officiel, au mot près.

Le Quotidien écrit l'objet d'un lot une seule fois, en tête du tableau des
offres, puis nomme les attributaires plus bas. L'extraction s'ancre sur le mot
« attributaire » : elle tombe donc sur la seconde occurrence, qui dit qui a
gagné mais pas ce qui a été acheté.
"""

from app.extraction.objets_lots import (
    numero_de_lot,
    objet_du_lot,
    objet_est_douteux,
)

# reproduit la structure réelle d'un Quotidien (numéro 2026-03/ROBR/PGNZ/CMGT)
QUOTIDIEN = """
Lot 5 : Construction d'un logement + carrelage et électrification solaire de la
maternité et du dispensaire au CSPS du secteur6
1. CAB SARL - 24 987 858 - 24 987 858 Conforme 3ème
2. GCS - 21 924 297 - 21 924 297 Conforme 1er

Lot 6 : Réalisation de deux latrines à quatre (04) postes à l'école de
Nabmayaoghin et Loundgo B
1. MGB 8 850 000 - 8 850 000 Non conforme
2. EGMS - 9 792 950 - 9 792 950 Conforme

Attributaires provisoires :
Lot1 : l'entreprise GSAD est attributaire du marché pour un montant total de
vingt-quatre millions six cent quatre-vingt-dix mille
Lot 5 : l'entreprise GCS est attributaire du marché pour un montant de
vingt et un millions
"""


def test_lentete_de_lot_est_recopie_telle_quelle():
    objet = objet_du_lot(QUOTIDIEN, 6)
    assert objet.startswith("Réalisation de deux latrines à quatre (04) postes")
    assert "Nabmayaoghin" in objet


def test_la_ligne_des_attributaires_nest_jamais_prise_pour_lobjet():
    """Le même « Lot 5 » apparaît deux fois : en en-tête, et dans la liste des
    attributaires. Prendre la seconde publierait « l'entreprise GCS est
    attributaire… » comme objet du marché."""
    objet = objet_du_lot(QUOTIDIEN, 5)
    assert "attributaire" not in objet.lower()
    assert objet.startswith("Construction d'un logement")


def test_un_lot_absent_ne_donne_rien():
    """Mieux vaut ne rien écrire que reconstituer : un objet vide se corrige,
    un objet inventé se publie."""
    assert objet_du_lot(QUOTIDIEN, 9) is None


def test_reconnaissance_des_objets_douteux():
    assert objet_est_douteux("Lot 3 : Réalisation d'un marché public (non précisé dans l'extrait)")
    assert objet_est_douteux("Lot1 : l'entreprise GSAD est attributaire du marché pour un montant")
    assert not objet_est_douteux("Lot 7 : Réalisation d'une latrine à deux (02) postes")
    assert not objet_est_douteux(None)


def test_lecture_du_numero_de_lot():
    assert numero_de_lot("Lot1 : quelque chose") == 1
    assert numero_de_lot("Lot 06 : autre chose") == 6
    assert numero_de_lot("LOT n°12 - encore") == 12
    assert numero_de_lot("Acquisition de fournitures de bureau") is None


def test_un_montant_en_toutes_lettres_nest_pas_un_objet():
    """Premier filtre, par simple exclusion : il acceptait « Huit millions deux
    cent soixante-deux mille sept cent onze (8 262 711) francs CFA HTVA » comme
    objet de marché. Remplacer une erreur par une autre ne vaut pas mieux."""
    texte = (
        "Lot 2 : Huit millions deux cent soixante-deux mille sept cent onze "
        "(8 262 711) francs CFA HTVA soit 9 749 999 TTC\n1. ENTREPRISE X\n\n"
    )
    assert objet_du_lot(texte, 2) is None


def test_un_fragment_de_mise_en_page_nest_pas_un_objet():
    texte = "Lot 1 : 13 : lot 2 : 12 Publication de l'avis : Revue des Marchés Publics N°4427\n\n"
    assert objet_du_lot(texte, 1) is None


def test_un_objet_legitime_qui_commence_autrement_nest_pas_declare_douteux():
    """`objet_est_douteux` reste un test d'exclusion : sinon on renverrait en
    revue des lignes parfaitement valides au seul motif de leur premier mot."""
    assert not objet_est_douteux("Bitumage de la voirie du port sec de Bobo-Dioulasso")
    assert not objet_est_douteux("Pose de canalisations sur 4 km")


def test_une_quantite_entre_parentheses_ne_coupe_pas_lentete():
    """« quatre (04) postes » se lisait comme le début de la ligne 4 du tableau
    des offres, et l'objet était tronqué à « ...à quatre ( »."""
    objet = objet_du_lot(QUOTIDIEN, 6)
    assert objet.endswith("Nabmayaoghin et Loundgo B")


def test_la_colonne_daccote_nest_pas_collee_a_lobjet():
    """Le texte extrait du PDF ne conserve pas les cellules : « Conforme :
    -Offre anormalement basse » suivait l'objet et se serait publié avec lui."""
    texte = (
        "Lot 4 : Construction d'un hall d'attente au CSPS du secteur 6 "
        "Conforme : -Offre anormalement basse\n\n"
    )
    assert objet_du_lot(texte, 4) == "Construction d'un hall d'attente au CSPS du secteur 6"


def test_le_lot_dune_autre_procedure_nest_jamais_pris():
    """Un Quotidien publie des dizaines de procédures, chacune avec son
    « Lot 1 ». Sans la position du marché, on récupérait l'objet du lot 1 d'une
    autre procédure - une erreur indétectable, puisque le résultat ressemble
    parfaitement à un objet de marché."""
    texte = (
        "Lot 1 : Acquisition de véhicules pour le ministère de la Santé\n\n"
        "AUTRE PROCÉDURE\n"
        "Lot 1 : Construction de trois salles de classe à Koudougou\n\n"
        "Attributaire : ENTREPRISE ZED\n"
    )
    position = texte.index("Attributaire")
    assert objet_du_lot(texte, 1, position).startswith("Construction de trois salles")
    # sans position, on ne sait pas laquelle choisir
    assert objet_du_lot(texte, 1).startswith(("Acquisition", "Construction"))
