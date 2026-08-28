"""Extraction PDF → texte : pdfplumber, puis OCR Tesseract (fra) en secours.

Les sites .gov.bf publient beaucoup de scans : si le texte natif est quasi
vide, on bascule en OCR. Renvoie (texte, statut) avec statut ∈ ok | ocr | echec.

Troisième point d'attention : **pdfplumber garde en cache tout ce qu'il a lu de
chaque page**, si bien que la mémoire croît linéairement avec le nombre de
pages - mesuré à ~6 Mo/page, soit 3,9 Go sur le recueil de 626 pages de
l'ASCE-LC. Sur le VPS, qui dispose d'environ 3 Go, le worker était tué par le
noyau au milieu de l'extraction : le document n'étant enregistré qu'à la fin,
son URL ne rejoignait jamais les « connues » et la passe suivante retéléchargeait
le même PDF. Le conteneur a ainsi redémarré 97 fois d'affilée sans jamais
atteindre `scheduler.start()` - donc sans plus rien publier sur les réseaux
pendant huit heures. Fermer chaque page après lecture ramène le pic à 66 Mo.

Deuxième filet, moins évident : **pdfminer (le moteur de pdfplumber) rend
parfois 0 page sur un PDF pourtant valide et complet**. Le Conseil
constitutionnel en publie beaucoup - fins de ligne à l'ancienne (`\\r` seul) et
table xref non standard - soit ~23 % de son corpus. Le fichier n'est pas
tronqué (le marqueur `%%EOF` est bien là) : c'est le parseur qui renonce, sans
lever d'erreur. Un document à 0 page ressort alors avec un texte vide, donc
introuvable, et **rien ne le signale**. `pypdf`, plus tolérant, sert de lecteur
de secours ; sur un scan, chaque page porte une image plein cadre qu'on envoie
à Tesseract.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)

SEUIL_TEXTE_NATIF = 100  # en dessous de ~100 caractères, on considère le PDF scanné


def extraire_texte(path: Path, ocr: bool = True) -> tuple[str, str]:
    """Renvoie (texte, statut) avec statut ∈ ok | ocr | scan | echec.

    ocr=False saute la passe Tesseract : les PDF scannés sont marqués « scan »
    pour un traitement ultérieur (utile pour les gros lots sur une machine
    sans tesseract).
    """
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                # pdfminer a renoncé sans le dire : on repasse par pypdf
                return _via_pypdf(path, ocr)
            natif = _texte_natif(pdf)
            if len(natif) >= SEUIL_TEXTE_NATIF:
                return natif, "ok"
            if not ocr:
                return natif, "scan"
            return _ocr(pdf), "ocr"
    except Exception:
        logger.exception("Extraction impossible : %s", path)
        return "", "echec"


def _texte_natif(pdf: pdfplumber.PDF) -> str:
    """Le texte de toutes les pages, en fermant chacune après lecture.

    `page.close()` vide le cache que pdfplumber remplit page après page. Sans
    lui, la mémoire croît linéairement et un recueil de plusieurs centaines de
    pages fait tomber le process (cf. l'en-tête du module).
    """
    morceaux = []
    for page in pdf.pages:
        morceaux.append(page.extract_text() or "")
        page.close()
    return "\n\n".join(morceaux).strip()


def _ocr(pdf: pdfplumber.PDF) -> str:
    import pytesseract  # import tardif : dépend du binaire tesseract

    pages = []
    for page in pdf.pages:
        image = page.to_image(resolution=200).original
        pages.append(pytesseract.image_to_string(image, lang="fra"))
        # une page rastérisée à 200 dpi pèse plus lourd encore que son texte
        page.close()
    return "\n\n".join(pages).strip()


def _via_pypdf(path: Path, ocr: bool) -> tuple[str, str]:
    """Lecteur de secours pour les PDF que pdfminer n'ouvre pas.

    Même contrat de retour que `extraire_texte`. Sur un scan, on océrise les
    images plein cadre portées par chaque page plutôt que de rastériser le PDF
    (pas de dépendance à poppler, absent des images Docker).
    """
    from pypdf import PdfReader

    lecteur = PdfReader(str(path))
    if not lecteur.pages:
        logger.warning("PDF illisible même par pypdf : %s", path)
        return "", "echec"

    natif = "\n\n".join(page.extract_text() or "" for page in lecteur.pages).strip()
    if len(natif) >= SEUIL_TEXTE_NATIF:
        return natif, "ok"
    if not ocr:
        return natif, "scan"

    import pytesseract

    pages = []
    for page in lecteur.pages:
        for image in page.images:
            pages.append(pytesseract.image_to_string(image.image, lang="fra"))
    return "\n\n".join(pages).strip(), "ocr"
