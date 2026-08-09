"""Versions d'un même document : la source réécrit ses pages après publication.

Le gouvernement retouche ses comptes rendus (constaté : +5 Ko sur le n°024 entre
le 24 et le 29 juillet 2026). L'archivage versionné est voulu - il établit le
fait - mais toutes les versions ne doivent pas compter comme des documents
distincts. Ces tests figent la règle et, surtout, ce qu'elle ne doit jamais
détruire.
"""

import pytest

from app.versions import _cle_decision, _cle_nomination, _est_reformulation, _normaliser


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


def test_a_valider_face_a_un_verdict_nest_pas_une_divergence():
    """Le gouvernement réécrit ses pages : l'extraction repasse et produit
    toujours des `a_valider`. Les traiter comme des relectures divergentes
    remettait dans la file 86 nominations déjà validées à la main - et
    recommençait à chaque réécriture.

    Une divergence réelle, c'est `valide` contre `rejete` : deux humains qui se
    contredisent. Là, on ne tranche pas à leur place.
    """
    import inspect

    from app.versions import consolider_entites

    source = inspect.getsource(consolider_entites)
    assert 'e.statut_validation == "a_valider"' in source, (
        "Un doublon fraîchement extrait doit être supprimé face à une entité "
        "déjà relue, sinon la file de validation se remplit de redites."
    )


# --- reformulation d'un même poste ----------------------------------------

# Le gouvernement ne réécrit pas que la typographie : le LLM repasse sur la page
# réécrite et reformule les intitulés. Constaté après la re-collecte du 6 août
# 2026 : 151 nominations validées en double, 146 personnes affichées deux fois
# dans l'annuaire pour le même siège. La clé exacte ne voyait pas la différence
# entre « un accent » et « une autre nomination ».

def _nom(poste, personne_id=7, type_="nomination"):
    return _cle_nomination(_Faux(personne_id=personne_id, poste=poste, type=type_))


@pytest.mark.parametrize(
    "court,long_",
    [
        # troncature : l'intitulé long ne fait que situer le même poste
        ("Administrateur civil, Administrateur représentant l'État",
         "Administrateur civil, Administrateur représentant l'État au Conseil "
         "d'administration de l'École nationale"),
        # un seul accent d'écart, au milieu du libellé
        ("Directeur général de la Société industrielle burkinabé de matériels",
         "Directeur général de la Société industrielle burkinabè de matériels"),
        # casse et complément de structure
        ("Administrateur représentant la Chambre des mines du Burkina",
         "Administrateur représentant la Chambre des Mines du Burkina au Conseil "
         "d'administration du BUMIGEB"),
    ],
)
def test_une_reformulation_nest_pas_une_seconde_nomination(court, long_):
    assert _est_reformulation(_nom(court), _nom(long_))
    assert _est_reformulation(_nom(long_), _nom(court)), "la règle est symétrique"


@pytest.mark.parametrize(
    "a,b",
    [
        # LE piège : un préfixe qui introduit un AUTRE poste. Les fondre
        # fermerait le siège du directeur général au profit de son adjoint.
        ("Directeur général", "Directeur général adjoint"),
        ("Secrétaire général", "Secrétaire général adjoint du ministère"),
        # deux sièges distincts au même conseil : ni l'un ni l'autre n'est un
        # préfixe, mais le début est long et identique
        ("Administrateur représentant l'État au Conseil d'administration de l'Université",
         "Administrateur représentant l'État au Conseil d'administration de l'Agence"),
        # deux rôles réellement distincts issus du même acte de nomination
        ("Administrateur représentant l'État au Conseil d'administration du CHU",
         "Président du Conseil d'administration du CHU"),
    ],
)
def test_deux_postes_differents_ne_sont_jamais_fondus(a, b):
    assert not _est_reformulation(_nom(a), _nom(b))


def test_la_reformulation_ne_traverse_ni_la_personne_ni_le_type():
    """Deux personnes au même poste, c'est un poste collégial ou une
    succession - jamais un doublon. Et une fin de fonction n'est pas une
    nomination."""
    assert not _est_reformulation(_nom("Directeur général"), _nom("Directeur général", personne_id=8))
    assert not _est_reformulation(
        _nom("Directeur général"), _nom("Directeur général", type_="fin_fonction")
    )


def test_la_consolidation_garde_le_libelle_le_plus_complet():
    """À statut égal, c'est le libellé complet qui doit survivre : « au Conseil
    d'administration de l'École nationale » dit au lecteur de quel siège il
    s'agit, « Administrateur représentant l'État » ne dit rien."""
    import inspect

    from app.versions import consolider_entites

    source = inspect.getsource(consolider_entites)
    assert '-len(getattr(x, "poste", "") or "")' in source
    assert "_est_reformulation" in source


# --- le sigle contre le nom développé -------------------------------------

@pytest.mark.parametrize(
    "sigle,developpe",
    [
        ("Administrateur représentant le Conseil régional du Kadiogo au Conseil "
         "d’administration de l’UV-BF",
         "Administrateur représentant le Conseil régional du Kadiogo au Conseil "
         "d’administration de l’Université virtuelle du Burkina Faso (UV-BF)"),
        ("Administrateur représentant l’État au Conseil d’administration de l’UV-BF",
         "Administrateur représentant l’État au Conseil d’administration de "
         "l’Université virtuelle du Burkina Faso (UV-BF)"),
    ],
)
def test_le_sigle_et_le_nom_developpe_sont_le_meme_siege(sigle, developpe):
    """Aucun n'est le préfixe de l'autre - c'est pourtant la même nomination,
    et l'annuaire affichait la personne deux fois sur le même conseil."""
    assert _est_reformulation(_nom(sigle), _nom(developpe))


@pytest.mark.parametrize(
    "a,b",
    [
        # même long début, deux établissements différents : le reste du libellé
        # court ne se retrouve pas dans le long
        ("Administrateur représentant l’État au Conseil d’administration de l’Université "
         "de Ouahigouya",
         "Administrateur représentant l’État au Conseil d’administration de l’Agence "
         "nationale de l’eau"),
        # début commun trop court pour prouver quoi que ce soit
        ("Conseiller technique", "Conseiller spécial du Premier ministre"),
    ],
)
def test_un_long_debut_commun_ne_suffit_pas(a, b):
    assert not _est_reformulation(_nom(a), _nom(b))


def test_un_prefixe_commun_court_ne_fonde_aucune_fusion():
    """« Administrateur représentant l'État » ouvre la moitié des nominations
    d'un conseil : trois mots communs ne disent rien."""
    from app.versions import _PREFIXE_MINIMUM

    assert _PREFIXE_MINIMUM >= 4


# --- une précision ajoutée en fin de libellé ------------------------------

@pytest.mark.parametrize(
    "court,long_",
    [
        # le sigle du poste, ajouté entre parenthèses
        ("Directeur général des études et des statistiques sectorielles",
         "Directeur général des études et des statistiques sectorielles (DGESS)"),
        ("Directeur des moyennes entreprises du Centre 1",
         "Directeur des moyennes entreprises du Centre 1 (DME C1)"),
        # la précision introduite par une virgule
        ("Consul général du Burkina Faso à Cotonou",
         "Consul général du Burkina Faso à Cotonou, République du Benin"),
    ],
)
def test_une_precision_entre_parentheses_ou_virgule_ne_change_pas_le_poste(court, long_):
    assert _est_reformulation(_nom(court), _nom(long_))


@pytest.mark.parametrize(
    "adjoint",
    ["Directeur général adjoint", "Directeur général adjoint de la SONABEL"],
)
def test_un_adjoint_reste_un_autre_siege(adjoint):
    """Sans parenthèse ni virgule, le mot qui suit qualifie le RÔLE : fondre
    le directeur général avec son adjoint fermerait un siège à tort."""
    assert not _est_reformulation(_nom("Directeur général"), _nom(adjoint))
