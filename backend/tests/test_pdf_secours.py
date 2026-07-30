"""Lecteur de secours pour les PDF que pdfminer n'ouvre pas.

pdfminer (moteur de pdfplumber) rend parfois 0 page sur un PDF valide et
complet - ~23 % du corpus du Conseil constitutionnel. Le piège est le silence :
aucune erreur n'est levée, le document ressort simplement sans texte, donc
introuvable. Ces tests verrouillent le comportement du repli.
"""

import warnings

import pytest

from app.extraction.pdf import _via_pypdf, extraire_texte

warnings.filterwarnings("ignore")


@pytest.fixture
def pdf_vierge(tmp_path):
    """Un PDF valide d'une page, sans texte : le cas d'un scan."""
    from pypdf import PdfWriter

    chemin = tmp_path / "vierge.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)  # A4
    with chemin.open("wb") as f:
        writer.write(f)
    return chemin


def test_un_pdf_sans_texte_est_signale_comme_scan_pas_comme_vide(pdf_vierge):
    """Le point qui compte : un document sans texte natif doit ressortir en
    « scan » pour entrer dans la file d'OCR. S'il ressortait en « ok » ou
    « ocr » avec un texte vide, il serait perdu sans que rien ne l'indique."""
    texte, statut = _via_pypdf(pdf_vierge, ocr=False)
    assert statut == "scan"
    assert texte == ""


def test_le_repli_respecte_le_meme_contrat_que_lextraction_normale(pdf_vierge):
    texte, statut = extraire_texte(pdf_vierge, ocr=False)
    assert statut in ("ok", "scan", "ocr", "echec")
    assert isinstance(texte, str)


def test_un_fichier_illisible_ressort_en_echec(tmp_path):
    """Un échec doit être un échec explicite, jamais un texte vide silencieux."""
    faux = tmp_path / "casse.pdf"
    faux.write_bytes(b"%PDF-1.4\nceci n'est pas un PDF\n%%EOF")
    texte, statut = extraire_texte(faux, ocr=False)
    assert statut == "echec"
    assert texte == ""
