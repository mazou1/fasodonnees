"""Arbitrage LLM des rapprochements de dossiers de suivi.

`app/projets.py` propose des paires par recouvrement de tokens rares. Ce score
a bien la RECALL - il remonte les vraies paires - mais pas la PRÉCISION : au
seuil 0,55, il apparie « Maintenance de diverses installations » avec
« Acquisition de vivres », et « Lot 2 : consommables pour les urgences » avec
« CHU de Bogodogo », qui ne partagent qu'un lieu. Publier ces chaînes ferait
dire à la plateforme que l'État a annoncé puis attribué puis livré un projet
qui n'a jamais existé - le contraire de ce qu'elle promet.

D'où deux étages : le score fait le tri grossier (119 candidats sur des
millions de paires possibles), le LLM tranche sur chacun. Les paires retenues
partent en `a_valider` comme le reste, jamais publiées d'office.

Usage : python -m app.projets_llm arbitrer <csv> [max]
"""

from __future__ import annotations

import csv
import logging
import sys
import time
from pathlib import Path

from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

SEUIL_RETENU = 0.85


class Verdict(BaseModel):
    meme_projet: bool = Field(
        description="true seulement si les deux libellés désignent le MÊME "
        "projet concret : même ouvrage, même acquisition, même chantier."
    )
    confiance: float = Field(ge=0, le=1, description="Certitude du verdict")
    motif: str = Field(
        description="Une phrase : ce qui identifie le projet commun, ou ce qui "
        "distingue les deux libellés."
    )


PROMPT_SYSTEME = """\
Tu vérifies si deux libellés issus de sources publiques burkinabè désignent le \
MÊME projet concret, pour relier une annonce en Conseil des ministres, une \
attribution de marché et une livraison d'ouvrage.

Réponds `meme_projet: true` seulement si un lecteur informé conclurait qu'il \
s'agit du même ouvrage, de la même acquisition ou du même chantier.

Ce qui ne suffit PAS :
- le même lieu ou le même établissement (« CHU de Bogodogo » figure dans des \
dizaines de marchés sans rapport entre eux) ;
- le même secteur, le même ministère, le même type d'acte ;
- des montants voisins ;
- un vocabulaire commun (« acquisition », « travaux », « construction »).

Ce qui compte : un objet identifiable partagé - le nom de l'ouvrage, la route \
et ses extrémités, l'équipement précis, le programme nommé.

Dans le doute, réponds false. Un faux rapprochement publierait une chaîne \
« annoncé → attribué → livré » qui n'a jamais eu lieu ; un rapprochement \
manqué ne coûte qu'une occasion."""


def juger(libelle_amont: str, libelle_aval: str, contexte: str = "") -> Verdict:
    contenu = (
        f"Libellé A (en amont) : {libelle_amont}\n"
        f"Libellé B (en aval) : {libelle_aval}\n"
        f"{contexte}\n\nS'agit-il du même projet ?"
    )
    if settings.llm_provider == "anthropic":
        import anthropic

        from app.extraction.marches_llm import MODELE_ANTHROPIC

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        reponse = client.messages.parse(
            model=MODELE_ANTHROPIC,
            max_tokens=500,
            system=PROMPT_SYSTEME,
            messages=[{"role": "user", "content": contenu}],
            output_format=Verdict,
        )
        return reponse.parsed_output

    from mistralai.client import Mistral

    from app.extraction.marches_llm import MODELE_MISTRAL

    client = Mistral(api_key=settings.mistral_api_key)
    for tentative in range(4):
        try:
            reponse = client.chat.parse(
                model=MODELE_MISTRAL,
                messages=[
                    {"role": "system", "content": PROMPT_SYSTEME},
                    {"role": "user", "content": contenu},
                ],
                response_format=Verdict,
                temperature=0,
            )
            break
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "status_code", None) == 429 and tentative < 3:
                time.sleep(5 * (tentative + 1))
                continue
            raise
    parsee = reponse.choices[0].message.parsed
    if parsee is None:
        raise RuntimeError("Réponse Mistral non conforme au schéma")
    return parsee


def arbitrer(chemin: Path, maximum: int | None = None) -> dict[str, int]:
    """Annote le CSV de propositions d'un verdict LLB. Écrit `<nom>.arbitre.csv`."""
    lignes = list(csv.DictReader(chemin.open(encoding="utf-8")))
    if maximum:
        lignes = lignes[:maximum]
    compte = {"juges": 0, "retenus": 0, "ecartes": 0, "echecs": 0}
    for i, ligne in enumerate(lignes):
        if i:
            time.sleep(1.2)  # politesse tier gratuit Mistral
        contexte = (
            f"Montant A : {ligne.get('montant_amont') or 'non indiqué'}\n"
            f"Montant B : {ligne.get('montant_aval') or 'non indiqué'}\n"
            f"Mot identifiant partagé : {ligne.get('mot_identifiant') or '-'}"
        )
        try:
            v = juger(ligne["libelle_amont"], ligne["libelle_aval"], contexte)
        except Exception:  # noqa: BLE001
            compte["echecs"] += 1
            ligne["verdict"] = "echec"
            continue
        compte["juges"] += 1
        retenu = v.meme_projet and v.confiance >= SEUIL_RETENU
        ligne["verdict"] = "oui" if retenu else "non"
        ligne["verdict_confiance"] = f"{v.confiance:.2f}"
        ligne["verdict_motif"] = v.motif
        ligne["appliquer"] = "oui" if retenu else ""
        compte["retenus" if retenu else "ecartes"] += 1

    sortie = chemin.with_suffix(".arbitre.csv")
    champs = list(lignes[0].keys()) if lignes else []
    with sortie.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=champs)
        w.writeheader()
        w.writerows(lignes)
    print(f"→ {sortie}")
    return compte


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) < 3 or sys.argv[1] != "arbitrer":
        print(__doc__)
        return 1
    maximum = int(sys.argv[3]) if len(sys.argv) > 3 else None
    c = arbitrer(Path(sys.argv[2]), maximum)
    print(
        f"{c['juges']} paire(s) jugée(s) : {c['retenus']} retenue(s), "
        f"{c['ecartes']} écartée(s), {c['echecs']} échec(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
