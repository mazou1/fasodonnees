"""ASCE-LC : tri des publications de contrôle et récupération des rapports."""

from app.ingestion.asce_lc import pdfs_du_contenu, type_du_post


def test_un_rapport_daudit_reste_un_rapport_meme_publie_en_actualite():
    """Les articles portent plusieurs catégories : un audit de la SONABHY est
    aussi rangé en « actualités ». La rubrique de contrôle doit l'emporter."""
    assert type_du_post(["actualites", "rapports-daudits-controles"]) == "rapport_controle"
    assert type_du_post(["rapports-daudits-controles", "affaires-judiciaires"]) == "rapport_controle"


def test_les_rubriques_de_controle_sont_distinguees():
    assert type_du_post(["dossiers-juges"]) == "affaire_anticorruption"
    assert type_du_post(["dossiers-en-cours-de-jugement"]) == "affaire_anticorruption"
    assert type_du_post(["declaration-d-interet-et-de-patrimoine"]) == "declaration_patrimoine"
    assert type_du_post(["denonciations-traitees"]) == "plainte_denonciation"


def test_une_actualite_institutionnelle_est_ecartee():
    """Séminaires, audiences et communiqués n'ont pas leur place dans le
    corpus documentaire de contrôle."""
    assert type_du_post(["actualites", "agenda"]) is None
    assert type_du_post([]) is None


CONTENU = """
<p>Rapport annuel général d'activités 2023.</p>
<a href="https://www.asce-lc.bf/wp-content/uploads/2025/07/RAGA-2023-TOME-1.pdf">Tome 1</a>
<a href="https://www.asce-lc.bf/wp-content/uploads/2025/07/RAGA-2023-TOME-1.pdf">Tome 1 (bis)</a>
<a href="https://www.asce-lc.bf/wp-content/uploads/2025/07/RAGA-2023-TOME-2.pdf">Tome 2</a>
<a href="/wp-content/uploads/2024/07/Organigramme_SONABEL_2023.pdf">Organigramme</a>
<a href="https://www.asce-lc.bf/une-page">Page liée</a>
"""


def test_pdfs_dedoublonnes_en_gardant_lordre():
    """Un même rapport est souvent lié deux fois (image + texte) : le
    télécharger deux fois est inutile, et l'ordre des tomes compte."""
    urls = pdfs_du_contenu(CONTENU, "https://www.asce-lc.bf/un-article/")
    assert urls == [
        "https://www.asce-lc.bf/wp-content/uploads/2025/07/RAGA-2023-TOME-1.pdf",
        "https://www.asce-lc.bf/wp-content/uploads/2025/07/RAGA-2023-TOME-2.pdf",
        "https://www.asce-lc.bf/wp-content/uploads/2024/07/Organigramme_SONABEL_2023.pdf",
    ]


def test_les_liens_relatifs_sont_resolus():
    urls = pdfs_du_contenu('<a href="/docs/rapport.pdf">R</a>', "https://www.asce-lc.bf/article/")
    assert urls == ["https://www.asce-lc.bf/docs/rapport.pdf"]


def test_contenu_vide_ne_casse_pas():
    assert pdfs_du_contenu("", "https://www.asce-lc.bf/") == []
    assert pdfs_du_contenu(None, "https://www.asce-lc.bf/") == []
