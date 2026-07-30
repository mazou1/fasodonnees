"""Relecture ciblée des marchés dont l'extraction s'est contredite.

Deux défauts se recoupent sur les mêmes lignes :

1. **Contradiction attribution / présélection.** Une référence d'avis à
   manifestation d'intérêt accompagnée d'un montant. La manifestation d'intérêt
   sert aussi de mode de passation pour les prestations intellectuelles : le
   Quotidien publie alors une vraie attribution sous cette référence. Le premier
   passage n'a pas tranché et a renvoyé la ligne en revue (cf. la migration
   `c8e1f4a7b902`).

2. **Objet fabriqué.** Quatre de ces lignes portent, textuellement, « Lot 3 :
   Réalisation d'un marché public (non précisé dans l'extrait) » - avec un score
   de 0,95. Le modèle a comblé un champ obligatoire faute de l'avoir lu, et
   s'est déclaré sûr de lui. Publier cela reviendrait à annoncer 24 M FCFA
   attribués à un objet qui n'existe pas.

Cette passe relit chaque ligne sur son extrait d'origine, avec une fenêtre plus
large que celle de l'extraction. Elle ne touche qu'à `nature` et à `objet`, et
seulement quand le texte le dit clairement : dans le doute, la ligne reste en
`a_valider` telle quelle.

Usage : python -m app.extraction.marches_arbitrage [--appliquer]
"""

from __future__ import annotations

import logging
import sys
import time

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from typing import Literal

from app.config import settings
from app.db import SessionLocal
from app.models import Document, Marche

logger = logging.getLogger(__name__)

AVANT, APRES = 3000, 2500
SEUIL = 0.85

# marque laissée par le modèle quand il n'a pas trouvé l'objet et l'a inventé
AVEUX = ("non précisé", "non precise", "non indiqué", "non indique", "non spécifié")


class Relecture(BaseModel):
    nature: Literal["attribution", "preselection"] = Field(
        description="'attribution' si un marché est effectivement attribué à "
        "cette entreprise pour un montant ; 'preselection' si elle est seulement "
        "retenue à l'issue d'un avis à manifestation d'intérêt, sans contrat."
    )
    objet: str | None = Field(
        default=None,
        description="Objet réel du marché tel qu'il est ÉCRIT dans l'extrait. "
        "null si l'extrait ne le donne pas - ne jamais le reconstituer.",
    )
    confiance: float = Field(ge=0, le=1)
    motif: str = Field(description="Une phrase justifiant le verdict")


PROMPT_SYSTEME = """\
Tu relis UNE ligne déjà extraite du Quotidien des Marchés Publics du Burkina \
Faso, dont l'extraction s'est contredite, et tu la tranches sur l'extrait \
d'origine qui t'est fourni.

Deux questions, et deux seulement :

1. **Attribution ou présélection ?** L'avis à manifestation d'intérêt sert \
tantôt à présélectionner des candidats pour la suite d'une procédure - le \
candidat est retenu, sans contrat ni montant - tantôt de mode de passation \
pour des prestations intellectuelles, et le marché est alors réellement \
attribué. Le texte le dit : cherche « attributaire », « attribué », \
« attribution provisoire », un montant contractuel, par opposition à « liste \
restreinte », « candidats retenus », « présélectionnés ».

2. **Quel est l'objet réel ?** Recopie-le tel qu'il est écrit. Si l'extrait ne \
le contient pas, réponds null. N'écris JAMAIS une formule de remplacement du \
genre « non précisé dans l'extrait » : un champ vide se corrige, un champ \
inventé se publie.

`confiance` basse dès que l'extrait est ambigu. Cette ligne sera publiée telle \
quelle si tu es sûr."""


def _demander(texte: str) -> Relecture:
    if settings.llm_provider == "anthropic":
        import anthropic

        from app.extraction.marches_llm import MODELE_ANTHROPIC

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        reponse = client.messages.parse(
            model=MODELE_ANTHROPIC,
            max_tokens=1000,
            system=PROMPT_SYSTEME,
            messages=[{"role": "user", "content": texte}],
            output_format=Relecture,
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
                    {"role": "user", "content": texte},
                ],
                response_format=Relecture,
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


def _contradictoires(db):
    """Marchés en attente portant une référence de manifestation d'intérêt ET
    un montant : les deux ne vont pas ensemble sans vérification."""
    texte = func.translate(
        func.lower(
            func.coalesce(Marche.reference, "")
            + " "
            + func.coalesce(Marche.objet, "")
            + " "
            + func.coalesce(Marche.mode, "")
        ),
        "éèêëàâîïôöûüç’",
        "eeeeaaiioouuc'",
    )
    return db.scalars(
        select(Marche)
        .where(
            Marche.statut_validation == "a_valider",
            Marche.montant_fcfa.is_not(None),
            texte.like("%manifestation%interet%"),
        )
        .order_by(Marche.document_id, Marche.id)
    ).all()


def _objet_est_fabrique(objet: str | None) -> bool:
    reduit = (objet or "").lower()
    return any(aveu in reduit for aveu in AVEUX)


def arbitrer(appliquer: bool = False) -> dict[str, int]:
    from app.extraction.autorites import _cle_disponible, _position

    if not _cle_disponible():
        raise RuntimeError(
            f"Aucune clé API pour le fournisseur '{settings.llm_provider}' : "
            "lancer cette passe depuis le conteneur worker."
        )

    compte = {
        "relus": 0, "attributions": 0, "preselections": 0,
        "objets_corriges": 0, "objets_fabriques_restants": 0,
        "introuvables": 0, "doute": 0, "echecs": 0,
    }
    with SessionLocal() as db:
        marches = _contradictoires(db)
        print(f"{len(marches)} ligne(s) contradictoire(s) à relire.\n")
        doc_id, texte = None, ""
        for i, m in enumerate(marches):
            if m.document_id != doc_id:
                d = db.get(Document, m.document_id)
                texte = (d.texte_extrait or "") if d else ""
                doc_id = m.document_id
            position = _position(texte, m) if texte else None
            if position is None:
                compte["introuvables"] += 1
                print(f"  [{m.id}] introuvable dans le Quotidien - laissé tel quel")
                continue
            if i:
                time.sleep(1.2)
            extrait = texte[max(0, position - AVANT) : position + APRES]
            contenu = (
                f"{extrait}\n\n---\nLIGNE À RELIRE\n"
                f"Référence : {m.reference}\n"
                f"Entreprise : {m.attributaire}\n"
                f"Montant extrait : {m.montant_fcfa}\n"
                f"Objet actuellement enregistré : {m.objet}"
            )
            try:
                r = _demander(contenu)
            except Exception:  # noqa: BLE001
                compte["echecs"] += 1
                continue
            compte["relus"] += 1
            sûr = r.confiance >= SEUIL
            marque = "✓" if sûr else "?"
            print(f"  [{m.id}] {marque} {r.nature} ({r.confiance:.2f}) - {r.motif[:88]}")

            if not sûr:
                compte["doute"] += 1
                continue
            compte["attributions" if r.nature == "attribution" else "preselections"] += 1

            if appliquer:
                m.nature = r.nature
                if r.nature == "preselection":
                    # une présélection ne chiffre rien : le montant lu appartient
                    # à une autre ligne du tableau
                    m.montant_fcfa = None
                if _objet_est_fabrique(m.objet):
                    if r.objet and not _objet_est_fabrique(r.objet):
                        print(f"        objet corrigé : {r.objet[:80]}")
                        m.objet = r.objet
                        compte["objets_corriges"] += 1
                    else:
                        # l'objet reste introuvable : la ligne ne peut pas être
                        # publiée, elle ne dit pas ce qui a été acheté
                        compte["objets_fabriques_restants"] += 1
                        continue
                m.statut_validation = "valide"
        if appliquer:
            db.commit()
            print("\nModifications enregistrées.")
        else:
            print("\n(simulation - relancer avec --appliquer pour écrire)")
    return compte


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    c = arbitrer(appliquer="--appliquer" in sys.argv)
    print(
        f"\n{c['relus']} relue(s) : {c['attributions']} attribution(s), "
        f"{c['preselections']} présélection(s), {c['objets_corriges']} objet(s) corrigé(s), "
        f"{c['objets_fabriques_restants']} objet(s) toujours introuvable(s), "
        f"{c['doute']} laissée(s) en revue, {c['introuvables']} introuvable(s), "
        f"{c['echecs']} échec(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
