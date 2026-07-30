"""Identité d'un « siège » pour détecter les successions dans l'annuaire.

Les comptes rendus annoncent rarement une fin de fonction explicite : ils
nomment un successeur au même poste. Pour savoir qui est encore en fonction,
il faut reconnaître qu'une nouvelle nomination au même siège chasse le
titulaire précédent - mais seulement pour les postes à titulaire UNIQUE
(directeur général, secrétaire général, préfet…), jamais pour les postes
collégiaux (administrateurs d'un conseil, conseillers, inspecteurs…) où
plusieurs personnes coexistent.

`cle_siege(poste)` renvoie une clé si le poste est à titulaire unique, sinon
None. Deux nominations partageant (structure canonique, clé) désignent le même
siège : la plus récente met fin à la précédente.
"""

from __future__ import annotations

import re
import unicodedata


def _plier(texte: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texte or "")
    sans = "".join(c for c in nfkd if not unicodedata.combining(c))
    sans = sans.replace("’", "'").replace("‘", "'").replace("-", " ")
    return re.sub(r"\s+", " ", sans).strip().lower()


# Postes collégiaux : plusieurs titulaires simultanés légitimes - jamais de
# succession. Testé sur le début du poste plié.
_COLLEGIAL = re.compile(
    r"^(?:administrateur|administratrice|membre|conseiller|conseillere|"
    r"charge|chargee|inspecteur|inspectrice|maitre|professeur|magistrat|"
    r"representant|representante|assesseur|juge(?! des)|deleguee?|"
    r"personne responsable des marches)\b"
)

# Rôles « sommet » à titulaire unique par structure : reconnaître le rôle
# malgré les variations du nom de structure qui suit. Ordre = du plus
# spécifique au plus général (le premier motif qui matche gagne).
_ROLES_SOMMET = [
    ("dga", r"directeur general adjoint|directrice generale adjointe"),
    ("dg", r"directeur general|directrice generale"),
    ("sga", r"secretaire general adjoint|secretaire generale adjointe"),
    ("sg", r"secretaire general|secretaire generale"),
    ("pca", r"president(?:e)? du conseil d'administration"),
    ("dircab", r"directeur de cabinet|directrice de cabinet"),
    ("gouverneur", r"gouverneur"),
    ("haut-commissaire", r"haut commissaire"),
    ("prefet", r"prefet|prefete"),
    ("ambassadeur", r"ambassadeur|ambassadrice"),
    ("recteur", r"recteur|rectrice"),
    ("controleur-fin", r"controleur financier|controleuse financiere"),
    ("agent-comptable", r"agent comptable"),
    ("tresorier", r"tresorier|tresoriere|payeur|payeuse"),
]
_ROLES_SOMMET = [(cle, re.compile(r"^(?:" + motif + r")\b")) for cle, motif in _ROLES_SOMMET]

# Têtes de poste à titulaire unique dont l'intitulé complet identifie le siège
# (ex. « Directeur des ressources humaines » ≠ « Directeur financier »). On
# exige alors une correspondance exacte de l'intitulé (hors nom de structure).
_TETE_UNIQUE = re.compile(
    r"^(?:directeur|directrice|chef|president|presidente|vice president|"
    r"vice presidente|coordonnateur|coordinateur|coordonnatrice|"
    r"greffier en chef|premier president|proviseur|controleur|controleuse|"
    r"commissaire|fonde de pouvoir)\b"
)


def cle_siege(poste: str | None, structure_unique: bool = True) -> str | None:
    """Clé du siège à titulaire unique, ou None si poste collégial/inconnu.

    `structure_unique` = la structure canonique désigne UNE entité (un
    établissement), où « le directeur général » est sans ambiguïté. Un rôle
    sommet reçoit alors une clé courte stable au libellé de structure
    (« dg », « sg »…), ce qui suit une succession malgré une reformulation du
    nom (cas ANPTIC : « DG pour la promotion des TIC » → « DG de promotion des
    TIC »).

    Si `structure_unique` est faux - structure « Ministère … » qui héberge
    plusieurs entités (DG des impôts, DG des douanes, DG du budget…) - le repli
    court serait DANGEREUX : tous ces DG partageraient la clé « dg » et se
    fermeraient l'un l'autre. On garde alors l'intitulé complet plié, distinct
    par objet ; on suit moins bien les reformulations mais on ne ferme jamais à
    tort le titulaire d'un autre siège.

    Les postes collégiaux (administrateurs d'un conseil, conseillers,
    inspecteurs…) renvoient toujours None : plusieurs titulaires coexistent.
    """
    p = _plier(poste)
    if not p or _COLLEGIAL.match(p):
        return None
    if structure_unique:
        for cle, motif in _ROLES_SOMMET:
            if motif.match(p):
                return cle
    if _TETE_UNIQUE.match(p) or any(motif.match(p) for _, motif in _ROLES_SOMMET):
        return p
    return None
