"""Extraction déterministe des marchés attribués depuis les tableaux du
Quotidien des Marchés Publics (DGCMEF).

Chaque « SYNTHÈSE DES RÉSULTATS » est un tableau à colonnes préservées par
pdfplumber : en-tête (autorité, référence + objet), puis les soumissionnaires
avec leur montant et une appréciation ; le retenu porte « Conforme … 1er » et
une ligne « Attributaire : NOM pour un montant de … » clôt le bloc. Pas de LLM,
pas d'aléa - on lit la structure.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)

RE_MONTANT = re.compile(r"([\d][\d  .]{4,})")
RE_REF = re.compile(r"((?:Demande de prix|Appel d['’]offres?|Manifestation|Consultation)[^\n.]{0,90})", re.I)
RE_ATTR_LIGNE = re.compile(r"(.+?)\s+pour un montant de\b", re.I)
RE_MONTANT_PAREN = re.compile(r"\(([\d  .]+)\)")

# --- nettoyage de l'objet -----------------------------------------------------
# L'en-tête du tableau accole à l'objet des rubriques administratives
# (financement, référence de publication, dates, convocation, …). On coupe
# l'objet au premier de ces marqueurs, en préférant le champ « Objet : … »
# explicite et en retirant préambules de référence et préfixes géographiques.
RE_OBJET_COUPE = re.compile(
    r"\s*(?:[-.;:]\s*)?\b(?:"
    r"r[ée]f[ée]rences?\b"
    r"|financement\b"
    r"|publi(?:cation|[ée]s?)\b"
    r"|avis\s+(?:publi|de\s+(?:la\s+)?(?:demande|publication)|d[e’'])"
    r"|n[°o]\s+de\s+la\s+revue\b"
    r"|date\s+d[e’']"
    r"|dates?\s+de\b"
    r"|nombre\s+de\b"
    r"|convocation\b"
    r"|lettre\s+de\s+convocation\b"
    r"|revue\s+des\s+march[ée]s\b"
    r"|quotidien\s+(?:des\s+march[ée]s|n[°o])"
    r"|rmp\s*n[°o]"
    r"|budget\s+pr[ée]visionnel\b"
    r"|montants?\s+(?:lus|corrig|pr[ée]visionnel|minimum|maximum)"
    r"|bornes?\s+(?:sup|inf)"
    r"|seuil\s+de\b"
    r"|moyenne\s+arithm"
    r"|note\s+pond[ée]r"
    r"|d[ée]lai\s+d"
    r"|offre\s+anormalement\b"
    r"|envelop"
    r")",
    re.I,
)
RE_OBJET_ENTETE = re.compile(r"\bobjet\s*:\s*", re.I)
RE_OBJET_PREAMBULE = re.compile(
    r"^(?:r[ée]gion\s+d[eu]\s+[A-ZÀ-Ÿ' -]+?\s+)?"
    r"(?:demande\s+de\s+prix|demande\s+de\s+cotations?|appel\s+d['’]offres?"
    r"|ddp|manifestation\s+d['’]int[ée]r[êe]t)\b"
    r"[^.]*?\bn[°o][^.]*?"
    r"\b(?:relati[fv]e?s?\s+(?:à|aux?|au)|portant\s+sur|pour)\s+",
    re.I,
)
RE_OBJET_GEO = re.compile(
    r"^(?:r[ée]gion\s+d[eu]\s+[A-ZÀ-Ÿ' -]+?\s+)?"
    r"(?:commun[eu]{1,2}\s+(?:de\s+|d[’'])[A-ZÀ-Ÿ' -]+?\s+)?",
    re.I,
)
# objet resté purement administratif = capture ratée (aucun objet réel dans le
# tableau) ; un vrai objet ne commence jamais par ces mots
RE_OBJET_BRUIT = re.compile(
    r"^(?:r[ée]f[ée]rence|marge|dates?|financement|nombre|montant|publication"
    r"|convocation|lettre|bornes?|revue|quotidien|attributaire|moyenne|offre)\b",
    re.I,
)
OBJET_INCONNU = "Objet non précisé (voir le Quotidien)"


def nettoyer_objet(brut: str | None) -> str | None:
    """Objet lisible : coupe les rubriques administratives, retire préambules
    de référence et préfixes géographiques. Idempotent."""
    if not brut:
        return brut
    txt = re.sub(r"\s+", " ", brut).strip()
    # préférer le champ explicite « Objet : … » où qu'il soit dans l'en-tête
    # (souvent précédé de rubriques administratives), sinon retirer un
    # préambule « DEMANDE DE PRIX N°… relatif à … »
    m = RE_OBJET_ENTETE.search(txt)
    if m:
        txt = txt[m.end() :]
    else:
        p = RE_OBJET_PREAMBULE.match(txt)
        if p and len(txt) - p.end() >= 12:
            txt = txt[p.end() :]
    # couper au premier marqueur de section administrative
    c = RE_OBJET_COUPE.search(txt)
    if c and c.start() >= 8:
        txt = txt[: c.start()]
    # retirer un préfixe région/commune en capitales resté en tête
    g = RE_OBJET_GEO.match(txt)
    if g and g.end() >= 8 and len(txt) - g.end() >= 12:
        txt = txt[g.end() :]
    txt = txt.strip(" :.,;---")
    if not txt:
        txt = brut.strip()
    # capture ratée : l'objet est resté une rubrique administrative
    if RE_OBJET_BRUIT.match(txt):
        return OBJET_INCONNU
    return txt[:300]


# --- nettoyage de l'attributaire ---------------------------------------------
# Même mal que l'objet : préfixes (« Lot N : », « L'attributaire est … ») et
# suffixes (« … pour un montant de … », « … est attributaire », adresses) qui
# collent au nom de l'entreprise ; parfois l'objet a débordé dans la cellule.
RE_ATT_PREFIXE = re.compile(
    r"^\s*(?:"
    r"s\s+(?=lot|provisoire|r[ée]sultat)"
    r"|(?:r[ée]sultats?\s+)?provisoires?\s*:?\s*"
    r"|provi(?:so|oi)re\s*:\s*"
    r"|lot\s*(?:unique|n[°o]?\s*\d+|\d+)\s*:?\s*"
    r"|l['’]attributaire\s+(?:provisoire\s+)?est\s+"
    r"|attributaire\s*(?:provisoire\s*)?:\s*"
    r")",
    re.I,
)
RE_ATT_SUFFIXE = re.compile(
    r"\s+(?:"
    r"est\s+(?:d[ée]clar[ée]e?\s+)?attributaire.*"
    r"|attributaire(?:\s+provisoire)?\b.*"
    r"|pour\s+un\s+montant.*"
    r"|pour\s+(?:l['’]acquisition|l['’]installation|les\s+travaux|la\s+r[ée]alisation"
    r"|la\s+fourniture|la\s+construction|le\s+march).*"
    r"|,?\s*adresse\s*:.*"
    r"|\d{2}\s*BP\b.*"
    r")$",
    re.I,
)
RE_ATT_OBJET = re.compile(
    r"^(?:l['’])?(?:acquisition|demande|travaux|r[ée]alisation|fourniture|prestation"
    r"|construction|r[ée]habilitation|entretien|achat|livraison|installation|dossier"
    r"|confection|location)\b",
    re.I,
)


def nettoyer_attributaire(brut: str | None) -> str | None:
    """Nom d'entreprise seul. None si l'objet a débordé dans la cellule et
    qu'aucun nom exploitable n'en ressort (extraction à revoir). Idempotent."""
    if not brut:
        return brut
    txt = re.sub(r"\s+", " ", brut).strip()
    for _ in range(4):  # préfixes empilés : « s provisoires : Lot unique : NOM »
        nouv = RE_ATT_PREFIXE.sub("", txt).strip()
        if nouv == txt:
            break
        txt = nouv
    txt = RE_ATT_SUFFIXE.sub("", txt).strip()
    # objet qui a débordé : tenter le nom après le dernier « : », sinon abandon
    if RE_ATT_OBJET.match(txt):
        if ":" in txt:
            cand = txt.rsplit(":", 1)[1].strip(" :.,;-«»<>")
            if 3 <= len(cand) <= 50 and not RE_ATT_OBJET.match(cand):
                txt = cand
            else:
                return None
        else:
            return None
    txt = txt.strip(" :.,;-«»<>")
    if len(txt) < 3 or RE_ATT_OBJET.match(txt):
        return None
    return txt[:400]


MONTANT_MAX = 500_000_000_000  # 500 Mds FCFA - au-delà = colonnes concaténées


def _montant(brut: str) -> int | None:
    """Un montant FCFA plausible extrait d'un fragment - None si aberrant."""
    if not brut:
        return None
    # un nombre = suite de chiffres séparés par espaces/points ; on prend le
    # premier groupe cohérent, pas une concaténation de plusieurs cellules
    m = re.search(r"\d[\d  .]{4,}", brut)
    if not m:
        return None
    ch = re.sub(r"[^\d]", "", m.group(0))
    if not (5 <= len(ch) <= 12):
        return None
    val = int(ch)
    return val if 100_000 <= val <= MONTANT_MAX else None


def _nettoyer_nom(nom: str) -> str:
    nom = re.sub(r"^\s*(?:lot\s*(?:unique|n?°?\s*\d+)?\s*:?\s*)", "", nom, flags=re.I)
    nom = re.sub(r"^\s*(?:provisoire|attributaire)\s*:?\s*", "", nom, flags=re.I)
    nom = re.sub(r"^\d{1,2}\s+", "", nom)  # colonne « N° ordre » (1-99) en tête, pas « 226 TECH »
    # coordonnées collées après le nom : « … / TEL : », « … Tél : », « … ( »
    nom = re.split(r"\s*/?\s*T[ÉE]L\s*[:.]|\s*\(", nom, maxsplit=1, flags=re.I)[0]
    nom = re.sub(r"\s*[/-]\s*$", "", nom)  # « GROUPEMENT … / » en fin
    return nom.strip(" :.,-")[:400]


def _est_autorite(ligne: str) -> bool:
    """Une ligne d'en-tête qui ressemble à une autorité contractante, pas à un
    intitulé de référence/montant."""
    ligne = ligne.strip()
    if len(ligne) < 6:
        return False
    if re.match(r"(?i)(montant|objet|demande de prix|appel d|référence|financement|n°|lot)", ligne):
        return False
    lettres = [c for c in ligne if c.isalpha()]
    majuscules = sum(1 for c in lettres if c.isupper())
    return bool(lettres) and majuscules / len(lettres) > 0.6  # majoritairement en capitales


def _cellule(row, i) -> str:
    return (row[i] or "").replace("\n", " ").strip() if i < len(row) else ""


def _texte_ligne(row) -> str:
    return " ".join((c or "").replace("\n", " ") for c in row).strip()


def _est_tableau_resultats(t: list) -> bool:
    entete = " ".join(_texte_ligne(r) for r in t[:4]).lower()
    return "soumissionnaire" in entete and ("montant" in entete or "appréciation" in entete)


def _parse_tableau(t: list) -> dict | None:
    """Renvoie {autorite, objet, reference, attributaire, montant} ou None."""
    lignes = [r for r in t if _texte_ligne(r)]
    if len(lignes) < 4:
        return None

    # en-tête : les 1-2 premières lignes avant la ligne de colonnes « Soumissionnaires »
    idx_col = next(
        (i for i, r in enumerate(lignes) if "soumissionnaire" in _texte_ligne(r).lower()), None
    )
    if idx_col is None or idx_col == 0:
        return None
    # autorité : la première ligne d'en-tête qui en a l'allure (capitales, pas
    # « Montant »/« Objet »/« Demande de prix ») ; None si le tableau ne la
    # nomme pas en clair (elle reste alors lisible dans la référence)
    autorite = next(
        (_texte_ligne(r) for r in lignes[:idx_col] if _est_autorite(_texte_ligne(r))),
        None,
    )
    bloc_entete = " ".join(_texte_ligne(r) for r in lignes[:idx_col])
    ref_m = RE_REF.search(bloc_entete)
    reference = ref_m.group(1).strip() if ref_m else None
    # objet : ce qui suit « pour » dans la référence, sinon le bloc d'en-tête,
    # puis nettoyage des rubriques administratives accolées
    objet = None
    if reference:
        apres = re.split(r"\bpour\b", bloc_entete, maxsplit=1, flags=re.I)
        objet = apres[1].strip() if len(apres) > 1 else reference
    objet = nettoyer_objet(objet or bloc_entete)

    # attributaire : ligne explicite « Attributaire … pour un montant de (CHIFFRES) »
    # (signal le plus fiable : le montant retenu est entre parenthèses)
    attributaire = montant = None
    for r in lignes[idx_col:]:
        txt = _texte_ligne(r)
        if re.search(r"attributaire", txt, re.I):
            reste = re.sub(r"^.*?attributaire\s*:?\s*", "", txt, flags=re.I)
            nom_m = RE_ATTR_LIGNE.match(reste)
            paren = RE_MONTANT_PAREN.search(reste)
            if nom_m and paren:
                attributaire = _nettoyer_nom(nom_m.group(1))
                montant = _montant(paren.group(1))
                break

    # sinon : la ligne « Conforme … 1er » (soumissionnaire retenu), montant pris
    # dans une seule cellule chiffrée cohérente
    if not (attributaire and montant):
        for r in lignes[idx_col + 1 :]:
            appr = _cellule(r, len(r) - 1).lower()
            if re.search(r"conforme.{0,8}1\s*er|1\s*er.{0,8}conforme", appr):
                nom = _nettoyer_nom(_cellule(r, 0) or _cellule(r, 1))
                mt = next(
                    (_montant(_cellule(r, j)) for j in range(1, len(r)) if _montant(_cellule(r, j))),
                    None,
                )
                if nom and mt:
                    attributaire, montant = nom, mt
                break

    # nettoyage fin de l'attributaire (préfixes/suffixes, objet débordé → None)
    if attributaire:
        attributaire = nettoyer_attributaire(attributaire)

    if not attributaire or not montant:
        return None
    if len(attributaire) < 3 or attributaire.lower() in ("néant", "attributaire", "conforme"):
        return None
    # l'attributaire ne peut pas être l'autorité (ligne d'en-tête mal découpée)
    if autorite and attributaire.lower()[:20] == autorite.lower()[:20]:
        return None
    return {
        "autorite": autorite[:400] if autorite else None,
        "objet": objet,
        "reference": reference,
        "attributaire": attributaire,
        "montant_fcfa": montant,
    }


def extraire_marches(pdf_path: str | Path) -> list[dict]:
    """Tous les marchés attribués d'un Quotidien, dédupliqués."""
    resultats: list[dict] = []
    vus: set[tuple] = set()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables():
                if not _est_tableau_resultats(t):
                    continue
                m = _parse_tableau(t)
                if not m:
                    continue
                cle = (re.sub(r"\s+", "", m["attributaire"].lower()), m["montant_fcfa"])
                if cle in vus:
                    continue
                vus.add(cle)
                resultats.append(m)
    return resultats
