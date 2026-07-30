"""Jurisprudence constitutionnelle : lecture des pages annuelles.

Le site nomme ses fichiers de dix façons selon les millésimes. Ces tests
figent les cas réellement rencontrés sur conseil-constitutionnel.gov.bf, pour
qu'une correction de regex n'en casse pas un autre.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from app.ingestion.conseil_constitutionnel import (
    ConseilConstitutionnelCollector,
    date_publication,
    nature,
    pages_annuelles,
    publications_de_la_page,
    reference,
)


# --- nature de la publication ---------------------------------------------

def test_un_avis_sur_un_projet_dordonnance_reste_un_avis():
    """Cas réel : « Avis sur le projet d'ordonnance portant… ». Chercher
    « ordonnance » n'importe où le classait en ordonnance - un avis n'a pas la
    portée d'une décision ni d'une ordonnance."""
    titre = "Avis sur le projet d'ordonnance portant conditions exceptionnelles"
    assert nature(titre, "avis_n__002_du_30_decembre_2025.pdf") == "avis_constitutionnel"


@pytest.mark.parametrize(
    "titre,fichier,attendu",
    [
        ("Décision n°2026-18/CC sur la conformité", "decision_n__2026-18.pdf",
         "decision_constitutionnelle"),
        ("DECISION N°2026-16/CC", "decision_n__2026-16.pdf", "decision_constitutionnelle"),
        # coquille présente sur le site
        ("DECISON N°2026-14/CC sur la conformité", "decision_n__2026-14.pdf",
         "decision_constitutionnelle"),
        ("Ordonnance n°2021-03/CC", "ordonnance_n__2021-03.pdf",
         "ordonnance_constitutionnelle"),
        # titre vide : le nom de fichier prend le relais
        ("", "avis_n__2026-01_cc_du_21_janvier_2026.pdf", "avis_constitutionnel"),
    ],
)
def test_nature(titre, fichier, attendu):
    assert nature(titre, fichier) == attendu


# --- référence ------------------------------------------------------------

def test_reference_avec_annee_dans_le_nom_de_fichier():
    """Piège : « 2026-06_du_17_fev » - l'underscore est un caractère de mot,
    donc un `\\b` après le numéro ne matche pas."""
    assert reference("Décision sur la conformité", "decision_n__2026-06_du_17_fev.pdf") == "2026-06"


def test_reference_sans_annee_utilise_le_contexte():
    """« décision n°22 du 18 décembre 2025 » : le numéro seul ne suffit pas,
    l'année vient de la date de la décision."""
    assert reference("Décision numéro 22 sur l'Accord de Prêt",
                     "decision_n__22_du_18_decembre_2025.pdf", 2025) == "2025-22"
    assert reference("", "avis_n__002_du_30_decembre_2025.pdf", 2025) == "2025-02"


def test_reference_absente_sans_contexte():
    assert reference("Décision numéro 22", "decision_n__22.pdf", None) is None


def test_un_numero_dannee_nest_pas_pris_pour_un_numero_de_decision():
    """« n°2025080/PR BF » dans un intitulé d'accord de prêt ne doit pas
    devenir la référence de la décision."""
    ref = reference(
        "Décision sur la conformité de l'Accord de Prêt n°2025080/PR BF 2025 3900",
        "decision_n__2026-01_cc_du_21_janvier_2026.pdf",
    )
    assert ref == "2026-01"


# --- date -----------------------------------------------------------------

def test_date_lue_dans_le_nom_de_fichier():
    assert date_publication("", "decision_n__2026-18_du_10_juin_2026.pdf", 2026) == date(2026, 6, 10)


def test_date_avec_mois_abrege_et_annee_de_la_page():
    """« du_24_oct » sans année : la page annuelle fournit le millésime."""
    assert date_publication("", "decision_n__20_cc_du_24_oct.pdf", 2025) == date(2025, 10, 24)


def test_date_lue_dans_le_titre_quand_le_fichier_ne_la_porte_pas():
    assert date_publication(
        "Décision numéro 020/CC du 24 Octobre 2025", "decision_n__20_cc.pdf", None
    ) == date(2025, 10, 24)


def test_pas_de_date_inventee():
    """Sans jour ni mois exploitables, mieux vaut une date absente qu'une date
    fausse - la date d'une décision de justice est un fait, pas une estimation."""
    assert date_publication("Décision 2025-01 CC", "decision_n__2025-01-cc.pdf", 2025) is None
    assert date_publication("", "decision_du_32_juin_2026.pdf", 2026) is None
    assert date_publication("", "decision_du_10_brumaire_2026.pdf", 2026) is None


# --- pages et blocs -------------------------------------------------------

ACCUEIL = """
<nav>
  <a href="/decisions-avis-et-ordonnances-2026">Décisions, Avis et Ordonnances 2026</a>
  <a href="/juriste-prudence-1/decisions-et-avis-2020">Décisions et avis 2020</a>
  <a href="/le-conseil">Le Conseil</a>
  <a href="/actualites">Actualités</a>
</nav>
"""


def test_pages_annuelles_decouvertes_depuis_le_menu():
    """Les URL sont irrégulières d'une année à l'autre : on les lit, on ne les
    fabrique pas."""
    pages = pages_annuelles(ACCUEIL)
    assert pages == [
        "https://www.conseil-constitutionnel.gov.bf/decisions-avis-et-ordonnances-2026",
        "https://www.conseil-constitutionnel.gov.bf/juriste-prudence-1/decisions-et-avis-2020",
    ]


PAGE = """
<div class="frame frame-type-uploads">
  <header class="frame-header">
    <h2 class="element-header"><span>Décision n°2026-18/CC sur la conformité de l'accord de prêt FIDA</span></h2>
    <h3 class="element-subheader"><span>dans le cadre de l'opération ORIAMSA</span></h3>
  </header>
  <ul class="media-list"><li><a href="/fileadmin/user_upload/decision_n__2026-18_du_10_juin_2026.pdf">
    <span class="uploads-filename">decision_n__2026-18_du_10_juin_2026.pdf</span></a></li></ul>
</div>
"""


def test_lecture_dun_bloc_de_publication():
    """Le titre du bloc porte l'objet réel de la décision ; le lien ne porte
    qu'un nom de fichier."""
    pubs = publications_de_la_page(PAGE, ".../decisions-avis-et-ordonnances-2026")
    assert len(pubs) == 1
    pub = pubs[0]
    assert pub["titre"].startswith("Décision n°2026-18/CC")
    assert pub["sous_titre"] == "dans le cadre de l'opération ORIAMSA"
    assert pub["reference"] == "2026-18"
    assert pub["date"] == date(2026, 6, 10)
    assert pub["type_doc"] == "decision_constitutionnelle"
    assert pub["url"].startswith("https://www.conseil-constitutionnel.gov.bf/fileadmin/")


def test_page_sans_publication_ne_casse_pas():
    assert publications_de_la_page("<html><body>rien</body></html>", ".../2026") == []


# --- stratégie de visite --------------------------------------------------

PAGES = [f"https://.../{an}" for an in range(2026, 2010, -1)]


def _a_visiter(connues, complet=False):
    """Appel non lié : la méthode ne dépend que de `complet` et `annees_revisitees`."""
    faux = SimpleNamespace(complet=complet, annees_revisitees=2)
    return ConseilConstitutionnelCollector._pages_a_visiter(faux, PAGES, connues)


def test_premier_passage_visite_toutes_les_annees():
    assert _a_visiter(connues=set()) == PAGES


def test_passage_periodique_ne_revisite_que_les_millesimes_recents():
    """Les années anciennes ne bougent plus : les revisiter chaque semaine
    coûterait une quinzaine de requêtes pour rien."""
    assert _a_visiter(connues={"https://.../deja.pdf"}) == PAGES[:2]


def test_le_rattrapage_force_repasse_sur_tout():
    """Sans ce mode, une collecte interrompue laisse un trou définitif : la
    passe incrémentale ne redescend jamais chercher les années anciennes."""
    assert _a_visiter(connues={"https://.../deja.pdf"}, complet=True) == PAGES
