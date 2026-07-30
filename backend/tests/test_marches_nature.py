"""Attribution ou présélection : deux objets qu'il ne faut pas confondre.

Un avis à manifestation d'intérêt retient un candidat pour la suite de la
procédure ; il ne lui attribue ni contrat ni montant. Les mêler aux attributions
gonflerait le nombre de marchés sans rien ajouter au total — donc fausserait le
montant moyen — et ferait passer un candidat présélectionné pour un
adjudicataire sur sa fiche entreprise.
"""

from app.extraction.marches_llm import MarcheExtrait


def _marche(**kw):
    base = dict(objet="Fourniture de matériel", confiance=0.9)
    return MarcheExtrait(**{**base, **kw})


def test_une_attribution_est_la_valeur_par_defaut():
    """Le gros du corpus est constitué d'attributions : le défaut doit être
    celui-là, pour qu'un champ absent ne déclasse pas une ligne valide."""
    assert _marche().nature == "attribution"


def test_la_preselection_est_un_choix_explicite():
    assert _marche(nature="preselection").nature == "preselection"


def test_seules_deux_natures_sont_admises():
    """Le schéma est fermé : une valeur inventée par le modèle doit être
    rejetée à la validation plutôt que d'atterrir en base."""
    import pydantic
    import pytest

    with pytest.raises(pydantic.ValidationError):
        _marche(nature="appel_offres")


def test_une_preselection_sans_montant_reste_valide():
    """C'est le cas normal, pas une anomalie : le montant se négocie après la
    présélection. Le schéma ne doit pas forcer à en inventer un."""
    m = _marche(nature="preselection", montant_fcfa=None)
    assert m.montant_fcfa is None
    assert m.nature == "preselection"


def test_le_mode_de_passation_nest_pas_la_nature():
    """« Demande de prix » et « appel d'offres » sont des modes de passation :
    les marchés qu'ils produisent sont bien des attributions. Confondre les deux
    aurait écarté 1 832 lignes parfaitement valides du corpus."""
    for mode in ("demande de prix", "appel d'offres ouvert", "demande de cotation"):
        assert _marche(mode=mode).nature == "attribution"


def test_une_preselection_chiffree_part_en_revue_humaine():
    """Contradiction dans les termes : la manifestation d'intérêt sert aussi de
    mode de passation, et le Quotidien publie alors une vraie attribution sous
    cette référence. On ne tranche pas à l'aveugle — on descend sous le seuil de
    validation automatique (0,9)."""
    m = _marche(nature="preselection", montant_fcfa=178_541_401, confiance=0.95)
    assert m.confiance <= 0.5


def test_une_confiance_deja_basse_nest_pas_relevee():
    m = _marche(nature="preselection", montant_fcfa=1_000, confiance=0.2)
    assert m.confiance == 0.2
