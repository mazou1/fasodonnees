"""Versions d'un même document : la source réécrit ses pages après publication.

Le gouvernement retouche ses comptes rendus (constaté : +5 Ko sur le n°024 entre
le 24 et le 29 juillet 2026). L'archivage versionné est voulu - il établit le
fait - mais toutes les versions ne doivent pas compter comme des documents
distincts. Ces tests figent la règle et, surtout, ce qu'elle ne doit jamais
détruire.
"""

import pytest

from app.versions import _cle_decision, _cle_nomination, _normaliser


class _Faux:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# --- normalisation typographique ------------------------------------------

def test_lapostrophe_courbe_et_droite_sont_le_meme_texte():
    """Le cas qui doublait les décisions : la réécriture remplaçait
    « nomination d'un » par « nomination d’un »."""
    assert _normaliser("nomination d'un Administrateur") == _normaliser(
        "nomination d’un Administrateur"
    )


def test_lespace_insecable_est_un_espace():
    """`&nbsp;` inséré par la source lors d'une réécriture."""
    assert _normaliser("Sahel. Il contribuera") == _normaliser("Sahel. Il contribuera")


def test_casse_et_espaces_multiples_sont_ignores():
    assert _normaliser("  ADOPTION   du   Décret ") == _normaliser("adoption du décret")


def test_une_difference_de_fond_reste_une_difference():
    """La normalisation ne doit unifier que la typographie : deux mesures
    différentes ne doivent jamais se confondre."""
    assert _normaliser("nomination d'un administrateur") != _normaliser(
        "nomination de deux administrateurs"
    )


# --- identité d'une entité entre versions ---------------------------------

def test_deux_decisions_identiques_a_la_typographie_pres_ont_la_meme_cle():
    a = _Faux(ministere="Santé", type="decret", objet="Adoption d'un décret")
    b = _Faux(ministere="Santé", type="decret", objet="Adoption d’un décret")
    assert _cle_decision(a) == _cle_decision(b)


def test_le_ministere_distingue_deux_decisions_au_meme_objet():
    a = _Faux(ministere="Santé", type="decret", objet="Adoption d'un décret")
    b = _Faux(ministere="Défense", type="decret", objet="Adoption d'un décret")
    assert _cle_decision(a) != _cle_decision(b)


def test_deux_nominations_se_distinguent_par_la_personne_et_le_poste():
    base = dict(personne_id=7, poste="Directeur général", type="nomination")
    assert _cle_nomination(_Faux(**base)) == _cle_nomination(_Faux(**base))
    assert _cle_nomination(_Faux(**base)) != _cle_nomination(
        _Faux(**{**base, "personne_id": 8})
    )
    assert _cle_nomination(_Faux(**base)) != _cle_nomination(
        _Faux(**{**base, "poste": "Secrétaire général"})
    )
    # une fin de fonction n'est pas une nomination au même poste
    assert _cle_nomination(_Faux(**base)) != _cle_nomination(
        _Faux(**{**base, "type": "fin_fonction"})
    )


# --- ce que la consolidation ne doit jamais faire -------------------------

def test_le_rang_des_statuts_protege_les_decisions_humaines():
    """`valide` et `rejete` sont des jugements humains : ils passent devant
    `a_valider` au moment de choisir l'entité à conserver, donc un doublon
    supprimé n'est jamais celui qui portait une relecture."""
    from app.versions import _RANG_STATUT

    assert _RANG_STATUT["valide"] < _RANG_STATUT["a_valider"]
    assert _RANG_STATUT["rejete"] < _RANG_STATUT["a_valider"]


@pytest.mark.parametrize("statut", ["valide", "rejete", "a_valider"])
def test_tous_les_statuts_connus_sont_ranges(statut):
    """Un statut inconnu tomberait en dernier et pourrait être supprimé à la
    place d'un statut relu : mieux vaut que la table soit complète."""
    from app.versions import _RANG_STATUT

    assert statut in _RANG_STATUT
