"""Récupération de l'objet réel d'un marché en lots, depuis l'en-tête de section.

Le Quotidien présente les procédures en lots. L'objet de chaque lot est écrit
une seule fois, en tête du tableau des offres :

    Lot 6 : Réalisation de deux latrines à quatre (04) postes à l'école de
    Nabmayaoghin et Loundgo B
    1. MGB   8 850 000  ...
    ...
    Attributaires provisoires :
    Lot1 : l'entreprise GSAD est attributaire du marché pour un montant de...

L'extraction s'ancre sur le mot « attributaire », donc sur la SECONDE
occurrence - celle qui nomme l'entreprise sans dire ce qui a été acheté. D'où
des objets soit inventés (« Réalisation d'un marché public (non précisé dans
l'extrait) »), soit recopiés de la mauvaise ligne (« l'entreprise GSAD est
attributaire du marché pour un montant total de vingt-quatre millions… »).

Ce module va chercher le bon en-tête, et le recopie **textuellement**. Pas de
reformulation : sur une plateforme de transparence, l'objet d'un marché doit
être celui du journal officiel, au mot près.
"""

from __future__ import annotations

import logging
import re
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Document, Marche

logger = logging.getLogger(__name__)

# Un en-tête de lot gouverne le tableau qui le suit : quelques milliers de
# caractères, jamais un Quotidien entier.
PORTEE_AMONT = 25000

# « Lot 6 : », « Lot6 - », « LOT 06 : », « Lot n°6 : »
def _motif_entete(numero: int) -> re.Pattern[str]:
    return re.compile(
        rf"lot\s*(?:n\s*[°ºo]\s*)?0*{numero}\s*[:\-–—]\s*(.{{15,300}}?)"
        rf"(?=\n\s*\d+\s*[.\)]|\nlot\s|\n\s*\n|$)",
        re.IGNORECASE | re.DOTALL,
    )


# marqueurs d'un texte qui décrit l'ATTRIBUTION plutôt que l'objet du marché
_PAS_UN_OBJET = (
    "attributaire",
    "est attributaire",
    "pour un montant",
    "non précisé",
    "non precise",
    "francs cfa",
    "fcfa",
    "htva",
    "publication de l'avis",
    "revue des marchés publics",
    "quotidien des marchés publics",
    # formule creuse produite quand le modèle n'a pas lu l'objet : elle ne dit
    # rien de ce qui a été acheté, et ne porte aucun des marqueurs ci-dessus
    "réalisation d'un marché public",
    "realisation d'un marche public",
    "réalisation d’un marché public",
)

# Un objet de marché commence par ce qu'on achète ou ce qu'on fait faire. La
# liste est volontairement FERMÉE : elle laisse passer moins de lignes, mais
# elle ne laisse passer que des objets. Un premier filtre par simple exclusion
# acceptait « Huit millions deux cent soixante-deux mille… francs CFA » et
# « 13 : lot 2 : 12 Publication de l'avis » comme objets de marché - remplacer
# une erreur par une autre ne vaut pas mieux que ne rien faire.
_DEBUTS_ATTENDUS = (
    "acquisition", "achat", "fourniture", "livraison", "approvisionnement",
    "construction", "réalisation", "realisation", "travaux", "aménagement",
    "amenagement", "réhabilitation", "rehabilitation", "rénovation", "renovation",
    "extension", "installation", "équipement", "equipement", "entretien",
    "maintenance", "réparation", "reparation", "prestation", "service",
    "étude", "etude", "contrôle", "controle", "suivi", "supervision",
    "assistance", "formation", "location", "transport", "confection",
    "impression", "édition", "edition", "gardiennage", "nettoyage",
    "restauration", "assurance", "audit", "élaboration", "elaboration",
    "mise en", "recrutement", "sécurisation", "securisation",
)


def numero_de_lot(objet: str | None) -> int | None:
    """Numéro de lot porté par l'objet actuel, s'il y en a un."""
    m = re.search(r"lot\s*(?:n\s*[°ºo]\s*)?0*(\d{1,2})\b", objet or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


# « accord cadre multi-attributaires » désigne une forme de marché, pas une
# ligne d'attribution mal extraite : le mot « attributaire » y est légitime.
_ATTRIBUTAIRE_LEGITIME = re.compile(r"multi[-\s]?attributaires?", re.IGNORECASE)


def _acceptable(candidat: str) -> bool:
    """Ce fragment peut-il être l'objet d'un marché ?

    Deux conditions, et les deux sont nécessaires : ne porter aucun marqueur de
    la ligne des attributaires, et commencer comme un objet commence.
    """
    reduit = _ATTRIBUTAIRE_LEGITIME.sub("", candidat).strip().lower()
    if any(marqueur in reduit for marqueur in _PAS_UN_OBJET):
        return False
    if len(reduit) < 20 or len(reduit.split()) < 3:
        return False
    return reduit.startswith(_DEBUTS_ATTENDUS)


# Fin d'un en-tête : la première ligne du tableau des offres. Elle commence par
# un rang (« 1. »), un montant, ou une mention de conformité - et le PDF, aplati
# en texte, la colle à l'en-tête sans saut de ligne fiable.
_FIN_ENTETE = re.compile(
    r"\s*(?:"
    # « 1. ENTREPRISE » — le garde-fou `(?<![(\d])` évite de couper sur les
    # quantités que les avis écrivent entre parenthèses : « quatre (04) postes »
    # se lisait comme le début de la ligne 4 du tableau.
    r"(?<![(\d])\d{1,2}\s*[.\)]\s+\S|"
    r"(?:non\s+)?conforme|"                # colonne « Conforme / Non conforme »
    r"(?<![(\d])\d[\d\s]{5,}|"             # un montant : longue suite de chiffres
    r"lot\s*(?:n\s*[°ºo]\s*)?\d|"          # le lot suivant
    r"le\s+d[ée]lai\s+d|"                  # « Le délai d'exécution de… »
    r"seuils?\s+anormaux|"                 # en-tête de la colonne des seuils
    r"montant\s+(?:lu|corrig)|"            # « Montant lu », « Montant corrigé »
    r"les\s+candidats\s+ont\s+la\s+possibilit"  # boilerplate de l'avis
    r")",
    re.IGNORECASE,
)


def _couper_a_la_fin_de_lentete(brut: str) -> str:
    """Coupe ce que le tableau a collé derrière l'en-tête.

    Le texte extrait du PDF ne conserve pas les cellules : « Construction d'un
    hall d'attente au CSPS du secteur 6 » se retrouve suivi de « Conforme :
    -Offre anormalement basse… ». Publier cela mettrait la colonne d'à côté dans
    l'objet du marché.
    """
    coupe = _FIN_ENTETE.search(brut)
    return (brut[: coupe.start()] if coupe else brut).strip(" .:-–—;,")


def objet_du_lot(texte: str, numero: int, position: int | None = None) -> str | None:
    """Objet écrit en en-tête pour ce lot, recopié tel quel.

    `position` est l'endroit du texte où ce marché est imprimé. Elle est
    déterminante : un Quotidien publie des dizaines de procédures, chacune avec
    son « Lot 1 ». Chercher dans tout le document donnait l'objet du lot 1 d'une
    AUTRE procédure - une erreur invisible, puisque le résultat ressemble
    parfaitement à un objet de marché. On ne retient donc que le dernier
    en-tête situé AVANT le marché, celui qui le gouverne.
    """
    zone = texte or ""
    decalage = 0
    if position is not None:
        debut = max(0, position - PORTEE_AMONT)
        zone = zone[debut:position]
        decalage = debut

    candidats: list[tuple[int, str]] = []
    for m in _motif_entete(numero).finditer(zone):
        brut = _couper_a_la_fin_de_lentete(re.sub(r"\s+", " ", m.group(1)))
        if _acceptable(brut):
            candidats.append((m.start() + decalage, brut))
    if not candidats:
        return None
    # le dernier avant le marché : c'est la procédure en cours, pas une
    # précédente qui portait le même numéro de lot
    return candidats[-1][1] if position is not None else max(candidats, key=lambda c: len(c[1]))[1]


# « … pour un montant TTC de quatre-vingt-deux millions » : le montant a été
# recopié à la suite de l'objet. L'objet, lui, est bien là - il suffit de couper.
_QUEUE_MONTANT = re.compile(
    r"\s*[-,;:]?\s*(?:"
    r"\(\s*montant[^)]*\)?|"             # « (montant minimum HTVA) »
    r"pour\s+un\s+montant|"
    r"d[’']un\s+montant|"
    r"au\s+prix\s+de|"
    r"soit\s+un\s+montant|"
    r"montant\s+(?:ttc|htva|total|minimum|maximum)|"
    r"attribution\s+(?:à|a|pour)|"        # « - Attribution à 22 000 000 FCFA »
    r"correction\s+op[ée]r[ée]e"          # « - Correction opérée pour variation… »
    r").*$",
    re.IGNORECASE | re.DOTALL,
)


# « (non précisé dans l'extrait) » : l'aveu du modèle, collé derrière un objet
# parfois complet. Le couper récupère la ligne - à condition que ce qui reste
# dise quelque chose.
_AVEU_FINAL = re.compile(
    r"\s*\(\s*non\s+(?:pr[ée]cis|indiqu|sp[ée]cifi)[^)]*\)?\s*$", re.IGNORECASE
)
# En deçà, ce qui reste est trop vague pour valoir publication : « Fourniture de
# services » ne dit rien d'un contrat de 58 millions FCFA. Le seuil vaut quelle
# que soit la coupe - montant ou aveu : une ligne n'est pas plus informative
# parce que c'est un montant qu'on lui a retiré.
MOTS_MINIMUM_APRES_COUPE = 4


def sans_queue_de_montant(objet: str | None) -> str | None:
    """Retire le montant recopié derrière l'objet, s'il en reste un objet.

    « Acquisition de chaises visiteur (Directeur et Agent) pour un montant TTC
    de quatre-vingt-deux millions… » devient « Acquisition de chaises visiteur
    (Directeur et Agent) ». Retourne None si ce qui précède le montant n'est pas
    un objet - auquel cas il n'y a rien à sauver, et la ligne ne doit pas rester
    publiée.
    """
    if not objet:
        return None
    coupe = _QUEUE_MONTANT.sub("", _AVEU_FINAL.sub("", objet)).strip(" .:-–—;,")
    # le numéro de lot en tête ne compte pas dans l'appréciation
    corps = re.sub(r"^lot\s*(?:n\s*[°ºo]\s*)?\d{0,2}\s*[:\-–—]?\s*", "", coupe, flags=re.I)
    if not _acceptable(corps):
        return None
    if len(corps.split()) < MOTS_MINIMUM_APRES_COUPE:
        return None
    return coupe


def objet_est_douteux(objet: str | None) -> bool:
    """L'objet enregistré décrit-il autre chose que le marché lui-même ?

    Test d'exclusion seulement : un objet parfaitement valide peut commencer par
    un mot absent de `_DEBUTS_ATTENDUS`, et le déclarer douteux le renverrait
    en revue sans raison.
    """
    reduit = _ATTRIBUTAIRE_LEGITIME.sub("", objet or "").lower()
    return bool(objet) and any(marqueur in reduit for marqueur in _PAS_UN_OBJET)


def reparer(appliquer: bool = False) -> dict[str, int]:
    """Remplace les objets douteux par l'en-tête de lot correspondant."""
    from app.extraction.autorites import _position

    compte = {
        "examines": 0, "corriges": 0, "sans_entete": 0,
        "sans_numero": 0, "introuvables": 0,
    }
    with SessionLocal() as db:
        marches = db.scalars(select(Marche).order_by(Marche.document_id, Marche.id)).all()
        doc_id, texte = None, ""
        for m in marches:
            if not objet_est_douteux(m.objet):
                continue
            compte["examines"] += 1
            numero = numero_de_lot(m.objet)
            if numero is None:
                compte["sans_numero"] += 1
                print(f"  [{m.id}] pas de numéro de lot : {str(m.objet)[:70]}")
                continue
            if m.document_id != doc_id:
                d = db.get(Document, m.document_id)
                texte = (d.texte_extrait or "") if d else ""
                doc_id = m.document_id
            position = _position(texte, m) if texte else None
            if position is None:
                compte["introuvables"] += 1
                print(f"  [{m.id}] introuvable dans le Quotidien : sans repère, "
                      "on ne sait pas quelle procédure le gouverne")
                continue
            trouve = objet_du_lot(texte, numero, position)
            if not trouve:
                compte["sans_entete"] += 1
                print(f"  [{m.id}] lot {numero} : en-tête introuvable, laissé tel quel")
                continue
            print(f"  [{m.id}] lot {numero} → {trouve[:88]}")
            if appliquer:
                m.objet = trouve
            compte["corriges"] += 1
        if appliquer:
            db.commit()
            print("\nModifications enregistrées.")
        else:
            print("\n(simulation - relancer avec --appliquer pour écrire)")
    return compte


def assainir_les_publies(appliquer: bool = False) -> dict[str, int]:
    """Traite les marchés PUBLIÉS dont l'objet ne dit pas ce qui a été acheté.

    Deux issues, jamais une seule : si l'objet est là et que seul le montant a
    été recopié derrière, on coupe et la ligne reste publiée. Sinon la ligne
    repart en revue - un marché de 103 millions dont l'objet est « Frais
    généraux (non précisés) » n'apprend rien à personne et abîme la confiance
    dans tout le reste.
    """
    compte = {"examines": 0, "coupes": 0, "depublies": 0}
    with SessionLocal() as db:
        for m in db.scalars(select(Marche).where(Marche.statut_validation == "valide")):
            if not objet_est_douteux(m.objet):
                continue
            compte["examines"] += 1
            recupere = sans_queue_de_montant(m.objet)
            if recupere:
                print(f"  [{m.id}] coupé  → {recupere[:82]}")
                if appliquer:
                    m.objet = recupere
                compte["coupes"] += 1
            else:
                print(f"  [{m.id}] retiré ← {str(m.objet)[:82]}")
                if appliquer:
                    m.statut_validation = "a_valider"
                compte["depublies"] += 1
        if appliquer:
            db.commit()
            print("\nModifications enregistrées.")
        else:
            print("\n(simulation - relancer avec --appliquer pour écrire)")
    return compte


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    appliquer = "--appliquer" in sys.argv
    if "--assainir" in sys.argv:
        a = assainir_les_publies(appliquer)
        print(
            f"\n{a['examines']} ligne(s) publiée(s) à l'objet douteux : "
            f"{a['coupes']} objet(s) récupéré(s), {a['depublies']} remise(s) en revue."
        )
        return 0
    c = reparer(appliquer=appliquer)
    print(
        f"\n{c['examines']} objet(s) douteux : {c['corriges']} corrigé(s), "
        f"{c['sans_entete']} sans en-tête retrouvé, {c['sans_numero']} sans numéro de lot, "
        f"{c['introuvables']} introuvable(s) dans le texte."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
