"""Comptes rendus de plénière : capter le changement quand il est annoncé.

La liste des députés du site officiel affichait encore 71 membres plusieurs
jours après la séance du 31 juillet 2026 qui en installait vingt nouveaux. Le
compte rendu de cette séance, lui, était en ligne le jour même.
"""

from datetime import date

import pytest

from app.ingestion.pleniere import PleniereCollector, date_du_texte

EXTRAIT = (
    "L'Assemblée législative du Peuple (ALP) réunie en séance plénière le "
    "vendredi 31 juillet 2026 sous la présidence du Chef du Parlement, le "
    "Camarade Dr Ousmane BOUGOUMA, elle a procédé à la validation des mandats "
    "des nouveaux députés."
)


def test_la_date_de_seance_se_lit_dans_le_texte():
    """Le site n'expose aucune date structurée et l'ordre de la liste ne suffit
    pas : la date est dans la première phrase du compte rendu."""
    assert date_du_texte(EXTRAIT) == date(2026, 7, 31)


@pytest.mark.parametrize(
    "texte,attendu",
    [
        ("séance du 1er février 2025", date(2025, 2, 1)),
        ("le 08 décembre 2024 à Ouagadougou", date(2024, 12, 8)),
        ("réunie le 3 aout 2026", date(2026, 8, 3)),
        ("le 13 Avril 2026", date(2026, 4, 13)),
    ],
)
def test_variantes_de_date(texte, attendu):
    assert date_du_texte(texte) == attendu


def test_un_texte_sans_date_ne_produit_pas_de_date_inventee():
    assert date_du_texte("Les députés ont adopté le projet de loi") is None
    assert date_du_texte("") is None
    assert date_du_texte(None) is None


def test_une_date_impossible_est_refusee():
    """« 31 février » existe dans les fautes de frappe, pas dans le calendrier :
    mieux vaut aucune date qu'une date fausse, qui classerait le compte rendu
    au mauvais endroit dans la chronologie."""
    assert date_du_texte("le 31 février 2026") is None


PAGE = """
<html><body>
<div class="max-w-7xl mx-auto space-y-6">
  <div class="text-2xl text-justify font-bold">
    Assemblée législative du Peuple : vingt nouveaux députés font leur entrée
  </div>
  <div>L'ALP réunie en séance plénière le vendredi 31 juillet 2026 a validé les mandats.</div>
  <div>Vingt (20) députés ont été installés, dont douze remplacent des partis.</div>
</div>
</body></html>
"""


def test_le_titre_et_le_corps_sont_separes():
    """La page n'a ni `<h1>` ni `<article>` : sans le repère du conteneur, le
    titre se retrouverait collé au corps et le menu du site avec."""
    collecteur = PleniereCollector.__new__(PleniereCollector)
    titre, texte = collecteur._corps(PAGE)
    assert titre.startswith("Assemblée législative du Peuple : vingt nouveaux députés")
    assert "vingt nouveaux députés font leur entrée" not in texte
    assert "Vingt (20) députés ont été installés" in texte
    assert date_du_texte(texte) == date(2026, 7, 31)


def test_une_page_au_gabarit_inconnu_ne_produit_rien():
    """Plutôt que d'enregistrer le menu de navigation comme compte rendu."""
    collecteur = PleniereCollector.__new__(PleniereCollector)
    titre, texte = collecteur._corps("<html><body><p>rien à voir</p></body></html>")
    assert titre is None
    assert texte == ""


def test_seuls_les_comptes_rendus_recents_sont_relus():
    """Une centaine de pages relues chaque jour, c'est deux minutes de requêtes
    pour presque jamais rien de neuf. Seuls les plus récents peuvent encore être
    corrigés par l'Assemblée."""
    assert PleniereCollector.RELECTURE_RECENTS < 20
    import inspect

    source = inspect.getsource(PleniereCollector.collect)
    assert "connues" in source and "RELECTURE_RECENTS" in source
