"""Taxonomie de l'annuaire : type d'institution (déduit du nom, le champ
`structure.type` n'ayant jamais été peuplé) et catégorie de fonction (déduite
de l'intitulé du poste). Heuristiques déterministes par mots-clés, priorité du
spécifique au générique - la première règle qui matche gagne.
"""

from __future__ import annotations

import re
import unicodedata

# --- type d'institution -------------------------------------------------------
# groupe d'affichage → ordre + libellé
GROUPES_INSTITUTION = [
    ("ministere", "Ministères"),
    ("institution", "Présidence, Primature & institutions"),
    ("juridiction", "Justice & juridictions"),
    ("territoriale", "Régions, provinces & communes"),
    ("police", "Directions territoriales de la police"),
    ("diplomatique", "Représentations diplomatiques"),
    ("etablissement", "Établissements publics & sociétés d'État"),
]

# Noms nus de régions (les collecteurs les stockent tantôt « Sahel », tantôt
# « Région du Sahel ») : 13 régions historiques + les nouvelles régions de la
# réforme territoriale de 2025. Comparaison sur nom plié (cf. _plier_simple).
_REGIONS_NUES = {
    "boucle du mouhoun", "cascades", "centre", "centre est", "centre nord",
    "centre ouest", "centre sud", "est", "hauts bassins", "nord",
    "plateau central", "sahel", "sud ouest",
    # réforme 2025 (nouveaux noms)
    "bankui", "djoro", "goulmou", "guiriko", "kadiogo", "kuilse",
    "liptako", "nakambe", "nando", "nazinon", "oubri", "sirba",
    "sourou", "tannounyan", "tapoa", "yaadga",
}


def _plier_simple(nom: str) -> str:
    nfkd = unicodedata.normalize("NFKD", nom or "")
    sans = "".join(c for c in nfkd if not unicodedata.combining(c))
    sans = sans.replace("’", " ").replace("'", " ").replace("-", " ")
    return re.sub(r"\s+", " ", sans).strip().lower()


# Réforme territoriale du 2 juillet 2025 : les 13 régions historiques sont
# renommées (toponymes endogènes). Clé = ancien nom plié → nom officiel actuel.
# Les 4 régions créées (Soum, Sirba, Tapoa, Sourou) n'ont pas d'ancien nom.
# Sourou/Kadiogo sont aussi des noms de PROVINCES : ce mapping étant indexé par
# les ANCIENS noms, il ne les touche pas (voir type_institution).
_REGIONS_REFORME = {
    "boucle du mouhoun": "Bankui",
    "cascades": "Tannounyan",
    "centre": "Kadiogo",
    "centre est": "Nakambé",
    "centre nord": "Kuilsé",
    "centre ouest": "Nando",
    "centre sud": "Nazinon",
    "est": "Goulmou",
    "hauts bassins": "Guiriko",
    "nord": "Yaadga",
    "plateau central": "Oubri",
    "sahel": "Liptako",
    "sud ouest": "Djôrô",
}

# préfixe territorial éventuel à retirer avant de consulter le mapping
_PREFIXE_REGION = re.compile(r"^r[ée]gion\s+(?:du|des|de\s+la|de\s+l|de)\s+", re.I)


def region_officielle(nom: str | None) -> str | None:
    """Nom officiel actuel d'une région désignée par son ancien nom (réforme
    2025), ou None si le nom n'est pas un ancien nom de région. Tolère le
    préfixe « Région du … » et les noms nus."""
    plie = _plier_simple(_PREFIXE_REGION.sub("", nom or ""))
    return _REGIONS_REFORME.get(plie)


def nom_region_affiche(nom: str | None) -> str:
    """Libellé d'affichage d'une région : nom officiel actuel avec l'ancien en
    rappel (« Région Liptako (ex-Sahel) »). Renvoie le nom tel quel hors
    région renommée."""
    officiel = region_officielle(nom)
    if not officiel:
        return nom or ""
    ancien = _PREFIXE_REGION.sub("", nom or "").strip()
    return f"Région {officiel} (ex-{ancien})"


_INSTIT = [
    ("ministere", re.compile(r"^\s*minist[èe]re\b", re.I)),
    ("institution", re.compile(
        r"^\s*(?:pr[ée]sidence|primature|premier\s+minist|assembl[ée]e|"
        r"conseil\s+[ée]conomique|conseil\s+sup[ée]rieur|m[ée]diateur|"
        r"grande\s+chancellerie|secr[ée]tariat\s+g[ée]n[ée]ral\s+du\s+gouvernement)", re.I)),
    ("juridiction", re.compile(
        r"^\s*(?:cour\b|tribunal|conseil\s+constitutionnel|conseil\s+d.[ée]tat|"
        r"conseil\s+sup[ée]rieur\s+de\s+la\s+magistrature|parquet|minist[èe]re\s+public)", re.I)),
    # une direction de police (déconcentrée) AVANT le motif territorial, qui
    # sinon avalerait « … de la région/province de X »
    ("police", re.compile(
        r"^\s*direction\s+(?:r[ée]gionale|provinciale)\s+de\s+la\s+police", re.I)),
    ("diplomatique", re.compile(
        r"^\s*(?:ambassade|consulat|mission\s+diplomatique|"
        r"repr[ée]sentation\s+permanente|haut\s+commissariat\s+du\s+burkina)", re.I)),
    # circonscription territoriale : le niveau doit être suivi d'un NOM DE LIEU
    # capitalisé (« Département de Korsimoro »), ce qui écarte les unités
    # organisationnelles homographes (« Département de formation permanente… »).
    # Casse significative → pas de flag re.I.
    ("territoriale", re.compile(
        r"^\s*(?:R[ée]gion|Province|D[ée]partement|Commune)\s+"
        r"(?:du|des|de\s+la|de\s+l['’]|de)\s+[A-ZÉÈ]")),
]


# Part des mandats qui doivent être des sièges au CA de l'entité désignée par
# le sigle pour que la structure SOIT cette entité plutôt que le ministère.
SEUIL_CONSEIL_ADMINISTRATION = 0.9


def type_institution(
    nom: str | None, sigle: str | None = None, part_ca: float | None = None
) -> str:
    """ministere | institution | juridiction | etablissement (défaut).

    Le nom fait foi, à une exception près. Un « Ministère … » portant un sigle
    est presque toujours le ministère, le sigle étant recopié d'une nomination
    voisine : vérifié en base le 2026-07-21, aucun de ces sigles ne désigne une
    structure par ailleurs et les mandats sont des postes ministériels variés
    (directeurs provinciaux, inspecteurs techniques…).

    Mais quand TOUS les mandats de la structure sont des sièges au conseil
    d'administration de l'entité du sigle, c'est l'inverse : la structure est
    cette entité et c'est son nom qui a été recopié du ministère de tutelle
    (cas SOGEMAB, seule à 100 % sur les 14 structures concernées ; les autres
    plafonnent à 62 %). `part_ca` porte ce ratio, mesuré sur les mandats.
    """
    n = nom or ""
    if (
        sigle
        and part_ca is not None
        and part_ca >= SEUIL_CONSEIL_ADMINISTRATION
        and re.match(r"^\s*minist[èe]re\b", n, re.I)
    ):
        return "etablissement"
    for code, motif in _INSTIT:
        if motif.search(n):
            return code
    # région désignée par son seul nom (« Sahel », « Boucle du Mouhoun »)
    if _plier_simple(n) in _REGIONS_NUES:
        return "territoriale"
    return "etablissement"


def sigle_fiable(
    nom: str | None, sigle: str | None, part_ca: float | None = None
) -> bool:
    """Un sigle accolé à un nom de ministère provient d'une nomination voisine
    (« Directeur général de l'ONEA ») et ne désigne pas la structure : on ne
    l'affiche pas - sauf si les mandats montrent que la structure est bien
    l'entité du sigle."""
    return bool(sigle) and type_institution(nom, sigle, part_ca) != "ministere"


# --- portefeuille ministériel -------------------------------------------------
# Les ministères sont renommés à chaque remaniement (« Ministère de la Santé »
# → « … de la Santé et de l'Hygiène publique ») et chaque intitulé a créé sa
# propre structure. On les regroupe sous un portefeuille commun, sans rien
# fusionner en base : les intitulés successifs restent visibles.

_ARTICLES = re.compile(
    r"^(?:de(?:s|\s+la|\s+l)?|du|d|l|le|la|les|et|en|aux?|charg[ée]e?s?)$", re.I)
_ACCENTS = str.maketrans("àâäçéèêëîïôöùûüÿ", "aaaceeeeiioouuuy")

# Mots de tête trop génériques pour identifier seuls un portefeuille : on prend
# alors les deux premiers mots significatifs (« Enseignement de base » ≠
# « Enseignement supérieur »).
_LEADS_AMBIGUS = {
    "affaires", "action", "developpement", "enseignement",
    "fonction", "transition", "conseil", "secretariat",
}


def _mots_significatifs(nom: str) -> list[str]:
    n = re.sub(r"^\s*minist[èe]re\s*", "", nom or "", flags=re.I)
    # minuscules AVANT le pliage : la table ne couvre que le bas de casse, et
    # un « É » résiduel serait mangé par le découpage (« Économie » → conomie)
    n = n.lower().translate(_ACCENTS).replace("’", " ").replace("'", " ")
    mots = [m for m in re.split(r"[^a-z]+", n) if m]
    return [m for m in mots if not _ARTICLES.match(m)]


# Renommages que le nom seul ne rattrape pas (remaniements de 2024-2026, dont
# les intitulés « révolutionnaires » de janvier 2026). Chaque rapprochement est
# établi sur deux signaux mesurés en base le 2026-07-21 : le nombre d'agents
# communs aux deux intitulés, et des plages de nominations qui se succèdent
# sans se chevaucher. Les intitulés successifs restent affichés sur la fiche.
#
# Écarté faute de preuve : « Guerre et Défense patriotique » ↔ « Défense et
# Anciens Combattants » - 0 agent commun et des plages qui se chevauchent
# depuis 2023 (la structure porteuse est en fait le CA de la SOGEMAB).
_ALIAS_PORTEFEUILLE = {
    # « Défense et Anciens Combattants » → « Guerre et Défense patriotique »,
    # intitulé du gouvernement en vigueur (trombinoscope de janvier 2026). Le
    # rapprochement ne ressort PAS des agents communs : la seule structure
    # portant déjà le nouveau nom est en fait le CA de la SOGEMAB.
    "defense": "guerre",
    # 16 agents communs, Infrastructures s'arrête 10/2025 → 02/2026
    "construction": "infrastructures",   # « Construction de la Patrie »
    # 10 agents communs avec « Construction de la Patrie », fin 05/2024
    "urbanisme": "infrastructures",
    # 14 agents communs, fin 07/2024 → reprise 08/2024
    "developpement industriel": "industrie",
    # 7 agents communs, Fonction publique s'arrête 11/2025 → 01/2026
    "serviteurs": "fonction publique",   # « Serviteurs du Peuple »
    # chaîne Solidarité (fin 06/2024) → Action humanitaire (fin 12/2025) →
    # Famille (depuis 02/2026) ; 14 puis 9 agents communs
    "action humanitaire": "solidarite",
    "famille": "solidarite",
}


# Postes du gouvernement qui ne désignent pas un ministère de plein exercice
_POSTE_HORS_MINISTERE = re.compile(
    r"d[ée]l[ée]gu[ée]|pr[ée]sident\s+du\s+faso|premier\s+minist|"
    r"secr[ée]taire\s+g[ée]n[ée]ral\s+du\s+gouvernement|direct(?:eur|rice)\s+de\s+cabinet",
    re.I,
)


def intitule_officiel(poste: str | None) -> str | None:
    """Intitulé du ministère porté par un membre du gouvernement, ou None si le
    poste n'en désigne pas un.

    Les noms tirés des nominations en Conseil des ministres retardent d'un
    remaniement : le trombinoscope officiel fait foi pour l'intitulé courant.
    « Ministre d'État, Ministre de la Guerre et de la Défense patriotique »
    → « Ministère de la Guerre et de la Défense patriotique ».
    """
    if not poste or _POSTE_HORS_MINISTERE.search(poste):
        return None
    # on garde la dernière accroche « Ministre de… » : « Ministre d'État,
    # Ministre de X » désigne le portefeuille X
    accroches = list(re.finditer(r"\bministre\s+(?=d)", poste, re.I))
    if not accroches:
        return None
    reste = poste[accroches[-1].end():]
    reste = re.sub(r",\s*porte-parole.*$", "", reste, flags=re.I).strip(" ,")
    return f"Ministère {reste}" if reste else None


def meme_intitule(a: str | None, b: str | None) -> bool:
    """Deux écritures du même intitulé. Le trombinoscope et les comptes rendus
    ne s'accordent ni sur l'apostrophe typographique ni sur les capitales
    (« des Langues nationales » / « des langues nationales »)."""
    def normaliser(s: str | None) -> str:
        s = (s or "").lower().replace("’", "'")
        return re.sub(r"\s+", " ", s).strip(" .")

    return normaliser(a) == normaliser(b)


def portefeuille(nom: str | None, type_deduit: str | None = None) -> str | None:
    """Clé de regroupement des intitulés successifs d'un même ministère, ou
    None hors ministère. Heuristique volontairement prudente : deux intitulés
    ne sont regroupés que s'ils partagent leur(s) mot(s) de tête - les cas que
    le nom ne rattrape pas passent par `_ALIAS_PORTEFEUILLE`.

    `type_deduit` évite de recalculer le type quand l'appelant le connaît (et
    de perdre au passage le correctif porté par `part_ca`)."""
    if (type_deduit or type_institution(nom)) != "ministere":
        return None
    mots = _mots_significatifs(nom or "")
    if not mots:
        return None
    if mots[0] in _LEADS_AMBIGUS and len(mots) > 1:
        cle = f"{mots[0]} {mots[1]}"
    else:
        cle = mots[0]
    return _ALIAS_PORTEFEUILLE.get(cle, cle)


# --- catégorie de fonction ----------------------------------------------------
# ordre = priorité (spécifique avant générique)
CATEGORIES_FONCTION = [
    "Membres du gouvernement",
    "Diplomatie & représentation",
    "Conseils d'administration",
    "Cabinet & conseil",
    "Direction & encadrement",
    "Inspection & contrôle",
    "Autres fonctions",
]

_FONCTION = [
    ("Membres du gouvernement", re.compile(
        r"\bministres?\b|secr[ée]taire\s+d.[ée]tat|ministre\s+d.[ée]tat", re.I)),
    ("Diplomatie & représentation", re.compile(
        r"ambassad|consul\b|consulaire|charg[ée]\s+d.affaires|mission\s+diplomatique|"
        r"repr[ée]sentant\s+permanent", re.I)),
    ("Conseils d'administration", re.compile(
        r"administrateur|conseil\s+d.administration|repr[ée]sentant.{0,25}[ée]tat", re.I)),
    ("Cabinet & conseil", re.compile(
        r"cabinet|charg[ée]s?\s+de\s+missions?|conseiller|charg[ée]s?\s+d.[ée]tudes?|"
        r"attach[ée]|secr[ée]taire\s+particulier", re.I)),
    ("Direction & encadrement", re.compile(
        r"directeur|directrice|direction|chef\s+de\b|secr[ée]taire\s+g[ée]n[ée]ral|"
        r"secr[ée]taire\s+technique|coordonnateur|coordinateur|pr[ée]sident|recteur|"
        r"proviseur|gouverneur|haut-?commissaire|pr[ée]fet", re.I)),
    ("Inspection & contrôle", re.compile(
        r"inspect|contr[ôo]le|contr[ôo]leur|v[ée]rificateur|auditeur", re.I)),
]


def categorie_fonction(poste: str | None) -> str:
    p = poste or ""
    for cat, motif in _FONCTION:
        if motif.search(p):
            return cat
    return "Autres fonctions"
