"""Appels à l'API Claude : un seul endroit pour le modèle, l'effort et les tokens.

Le budget est de 100 $ par mois : chaque appel compte. Trois choix en découlent.

- Le modèle vient de la configuration (`FASO_ANTHROPIC_MODEL`), par défaut le
  moins cher de la gamme : Claude Haiku 5.5 vaut 0,10 $ le million de tokens
  en entrée et 0,50 $ en sortie, dix fois moins que Haiku 4.5.
- L'effort est au minimum (`FASO_ANTHROPIC_EFFORT=low`). Sur cette génération
  le modèle réfléchit avant de répondre et cette réflexion est facturée en
  sortie ; le travail ici est de l'extraction structurée de textes
  administratifs, pas du raisonnement. Monter à `medium` seulement si la
  relecture dans /admin révèle des erreurs récurrentes. Haiku 4.5 refuse ce
  paramètre : avec ce modèle, laisser l'effort vide.
- Chaque réponse journalise ses tokens : c'est la seule façon de rapprocher le
  journal du worker de la facture, et de voir quelle passe coûte.

Pas de `temperature` : les modèles actuels refusent toute valeur autre que la
valeur par défaut ; la régularité vient du schéma de sortie.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def extraire(texte: str, *, schema: type[T], systeme: str, max_tokens: int) -> T:
    """Un appel structuré : `texte` en entrée, une instance de `schema` en sortie.

    `max_tokens` couvre la réflexion ET la réponse : pour un verdict d'un mot,
    prévoir tout de même quelques milliers de tokens, sinon la réflexion seule
    épuise le plafond et la réponse est vide.
    """
    import anthropic

    # api_key=None → le SDK résout la clé depuis l'environnement (ANTHROPIC_API_KEY / profil)
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    options = {}
    if settings.anthropic_effort:
        options["output_config"] = {"effort": settings.anthropic_effort}
    reponse = client.messages.parse(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=systeme,
        messages=[{"role": "user", "content": texte}],
        output_format=schema,
        **options,
    )
    usage = getattr(reponse, "usage", None)
    if usage is not None:
        logger.info(
            "Claude %s (%s) : %d tokens en entrée, %d en sortie",
            settings.anthropic_model,
            schema.__name__,
            usage.input_tokens,
            usage.output_tokens,
        )
    if reponse.stop_reason == "max_tokens":
        raise RuntimeError("Sortie tronquée (max_tokens) - document à traiter manuellement")
    if reponse.parsed_output is None:
        raise RuntimeError(
            f"Réponse Claude non conforme au schéma ({reponse.stop_reason}) - document à traiter manuellement"
        )
    return reponse.parsed_output
