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


def _acceptable(candidat: str) -> bool:
    """Ce fragment peut-il être l'objet d'un marché ?

    Deux conditions, et les deux sont nécessaires : ne porter aucun marqueur de
    la ligne des attributaires, et commencer comme un objet commence.
    """
    reduit = candidat.strip().lower()
    if any(marqueur in reduit for marqueur in _PAS_UN_OBJET):
        return False
    if len(reduit) < 20 or len(reduit.split()) < 3:
        return False
    return reduit.startswith(_DEBUTS_ATTENDUS)


def objet_du_lot(texte: str, numero: int) -> str | None:
    """Objet écrit en en-tête pour ce lot, recopié tel quel.

    Le même numéro apparaît plusieurs fois dans un Quotidien - une fois en
    en-tête de tableau, une fois dans la liste des attributaires. On ne retient
    que les occurrences qui décrivent un ouvrage ou une fourniture, jamais
    celles qui nomment une entreprise.
    """
    candidats = [
        re.sub(r"\s+", " ", m.group(1)).strip(" .:-–—")
        for m in _motif_entete(numero).finditer(texte or "")
    ]
    retenus = [c for c in candidats if _acceptable(c)]
    if not retenus:
        return None
    # le plus long est le plus descriptif : les en-têtes tronqués par un saut de
    # colonne du PDF donnent des fragments courts
    return max(retenus, key=len)


def objet_est_douteux(objet: str | None) -> bool:
    """L'objet enregistré décrit-il autre chose que le marché lui-même ?

    Test d'exclusion seulement : un objet parfaitement valide peut commencer par
    un mot absent de `_DEBUTS_ATTENDUS`, et le déclarer douteux le renverrait
    en revue sans raison.
    """
    reduit = (objet or "").lower()
    return bool(objet) and any(marqueur in reduit for marqueur in _PAS_UN_OBJET)


def reparer(appliquer: bool = False) -> dict[str, int]:
    """Remplace les objets douteux par l'en-tête de lot correspondant."""
    compte = {"examines": 0, "corriges": 0, "sans_entete": 0, "sans_numero": 0}
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
            trouve = objet_du_lot(texte, numero)
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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    c = reparer(appliquer="--appliquer" in sys.argv)
    print(
        f"\n{c['examines']} objet(s) douteux : {c['corriges']} corrigé(s), "
        f"{c['sans_entete']} sans en-tête retrouvé, {c['sans_numero']} sans numéro de lot."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
