"""Extraction LLM des marchés attribués du Quotidien des Marchés Publics.

Remplace la lecture déterministe des tableaux (`marches_tableau.py`), qui
dépendait de la géométrie des colonnes détectée par pdfplumber : elle ratait les
Quotidiens dont la mise en page changeait, et n'attribuait aucun score de
confiance - donc aucune validation automatique n'était défendable sur ces
lignes.

Le problème de taille
---------------------
Un Quotidien fait **277 000 caractères en médiane**, jusqu'à 1,1 million : hors
de portée d'un seul appel. On ne peut pas non plus se rabattre sur les sections
« SYNTHÈSE DES RÉSULTATS » - elles couvrent 99 % du texte, et certains numéros
n'en contiennent aucune tout en publiant des attributions.

D'où un découpage autour du mot **« attributaire »**, qui accompagne toute
attribution quelle que soit la mise en page. La charge tombe à 16-37 % du texte,
en fenêtres de quelques milliers de caractères. Ce repérage reste volontairement
grossier : c'est le LLM qui lit, le mot-clé ne fait que cadrer. Un numéro sans
aucune section « SYNTHÈSE » mais avec 43 occurrences d'« attributaire » est
justement le cas que l'ancien extracteur perdait en silence.
"""

from __future__ import annotations

import logging
import re
import time

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.config import settings

logger = logging.getLogger(__name__)

MODELE_ANTHROPIC = "claude-opus-5"
MODELE_MISTRAL = "mistral-small-latest"

RE_ATTRIBUTAIRE = re.compile(r"attributaire", re.IGNORECASE)
# de quoi contenir l'objet et l'autorité contractante qui précèdent l'attributaire,
# et le montant qui le suit
AVANT, APRES = 1200, 1300


class MarcheExtrait(BaseModel):
    autorite: str | None = Field(
        default=None,
        description="Autorité contractante : le ministère, la société d'État ou la "
        "collectivité qui passe le marché. null si absente.",
    )
    objet: str = Field(description="Objet du marché, tel qu'écrit dans le document")
    reference: str | None = Field(
        default=None,
        description="Référence de l'appel ou de la demande de prix "
        "(ex. « Demande de prix n°2026-006/DG-SONATUR/PRM du 27-04-2026 »)",
    )
    mode: str | None = Field(
        default=None,
        description="Mode de passation : demande de prix, appel d'offres ouvert, "
        "demande de cotation… null si absent.",
    )
    attributaire: str | None = Field(
        default=None,
        description="Raison sociale de l'entreprise retenue, telle qu'écrite, sans "
        "préfixe de phrase ni civilité. null si le marché est déclaré infructueux.",
    )
    montant_fcfa: int | None = Field(
        default=None,
        description="Montant attribué en FCFA, en entier et sans séparateur. Prendre "
        "le montant TTC s'il est distingué. null s'il n'est pas indiqué.",
    )
    nature: Literal["attribution", "preselection"] = Field(
        default="attribution",
        description="'preselection' si le texte résulte d'un avis à MANIFESTATION "
        "D'INTÉRÊT ou d'une pré-qualification - le candidat est retenu pour la "
        "suite de la procédure, sans contrat chiffré. 'attribution' si un marché "
        "est effectivement attribué.",
    )
    region: str | None = Field(
        default=None, description="Région du Burkina Faso concernée si elle apparaît"
    )
    confiance: float = Field(
        ge=0, le=1, description="Certitude de l'extraction de CETTE ligne, entre 0 et 1"
    )

    @model_validator(mode="after")
    def _preselection_chiffree_est_douteuse(self):
        """Une présélection chiffrée est contradictoire : à revoir à la main.

        La manifestation d'intérêt sert aussi de mode de passation pour les
        prestations intellectuelles, et le Quotidien publie alors une vraie
        attribution sous cette référence - parfois « attribution provisoire ».
        Trancher automatiquement se paierait dans un sens ou dans l'autre :
        classer en attribution gonflerait le total public d'un contrat qui
        n'existe pas, classer en présélection en effacerait un qui existe. On
        abaisse donc la confiance sous le seuil de validation automatique (0,9)
        pour que la ligne passe par la file de `/admin`.
        """
        if self.nature == "preselection" and self.montant_fcfa is not None:
            self.confiance = min(self.confiance, 0.5)
        return self


class ExtractionMarches(BaseModel):
    marches: list[MarcheExtrait]


PROMPT_SYSTEME = """\
Tu relèves les MARCHÉS PUBLICS ATTRIBUÉS dans un extrait du Quotidien des \
Marchés Publics du Burkina Faso (DGCMEF). Le texte provient d'un PDF : les \
colonnes des tableaux sont souvent mélangées, les lignes coupées, les montants \
éclatés. C'est précisément pour cela que tu lis plutôt qu'un automate.

Pour chaque attribution, relève l'autorité contractante, l'objet, la référence \
de l'appel, le mode de passation, l'entreprise retenue et le montant en FCFA.

Règles :
- Une seule entrée par marché attribué. Un marché en plusieurs lots attribués à \
des entreprises différentes donne une entrée par lot, en le précisant dans l'objet.
- Distingue l'ATTRIBUTION d'un marché de la PRÉSÉLECTION issue d'un avis à \
manifestation d'intérêt ou d'une pré-qualification : dans le second cas le \
candidat est retenu pour la suite de la procédure, sans contrat ni montant. \
Renseigne `nature` en conséquence - ne devine pas un montant qui n'existe pas.
- Ne relève PAS les avis d'appel d'offres, les avis de recrutement, les \
rectificatifs ni les marchés déclarés infructueux ou sans attributaire retenu.
- Le montant est un entier en FCFA, sans espace ni devise. S'il y a un montant \
HT et un TTC, prends le TTC.
- L'attributaire est la raison sociale seule : pas de « A l'entreprise », pas de \
« Attributaire : », pas de numéro de lot collé au nom.
- N'invente rien. Un champ absent reste null. Si l'extrait ne contient aucune \
attribution, retourne une liste vide.
- `confiance` reflète TA certitude sur cette ligne : basse si les colonnes sont \
manifestement mélangées ou si l'attributaire et le montant pourraient appartenir \
à deux marchés différents."""


def fenetres_candidates(texte: str) -> list[str]:
    """Extraits susceptibles de contenir une attribution.

    Les fenêtres qui se chevauchent sont fusionnées : sans cela un tableau dense
    produirait dix fenêtres quasi identiques, donc dix appels pour rien.
    """
    if not texte:
        return []
    bornes: list[list[int]] = []
    for m in RE_ATTRIBUTAIRE.finditer(texte):
        debut, fin = max(0, m.start() - AVANT), min(len(texte), m.start() + APRES)
        if bornes and debut <= bornes[-1][1]:
            bornes[-1][1] = max(bornes[-1][1], fin)
        else:
            bornes.append([debut, fin])
    return [texte[a:b] for a, b in bornes]


def extraire_marches_llm(texte: str) -> list[MarcheExtrait]:
    """Marchés attribués relevés dans un Quotidien, fenêtre par fenêtre.

    Une fenêtre en échec ne fait pas perdre les autres : le Quotidien contient
    des dizaines d'attributions, et en abandonner l'ensemble parce qu'un extrait
    a mal passé serait le pire des compromis.
    """
    fenetres = fenetres_candidates(texte)
    if not fenetres:
        return []
    marches: list[MarcheExtrait] = []
    for i, fenetre in enumerate(fenetres):
        if i:
            time.sleep(1.2)  # politesse tier gratuit Mistral (~1 req/s)
        try:
            marches.extend(_extraire_fenetre(fenetre).marches)
        except Exception:  # noqa: BLE001 - le SDK lève des types variés
            logger.warning(
                "Fenêtre %d/%d non exploitable - les autres sont conservées",
                i + 1, len(fenetres),
            )
    return marches


def _extraire_fenetre(texte: str) -> ExtractionMarches:
    if settings.llm_provider == "anthropic":
        return _extraire_anthropic(texte)
    return _extraire_mistral(texte)


def _extraire_mistral(texte: str) -> ExtractionMarches:
    from mistralai.client import Mistral

    client = Mistral(api_key=settings.mistral_api_key)
    for tentative in range(4):
        try:
            response = client.chat.parse(
                model=MODELE_MISTRAL,
                messages=[
                    {"role": "system", "content": PROMPT_SYSTEME},
                    {"role": "user", "content": texte},
                ],
                response_format=ExtractionMarches,
                temperature=0,
            )
            break
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "status_code", None) == 429 and tentative < 3:
                attente = 5 * (tentative + 1)
                logger.info("Mistral 429 (tier gratuit) - nouvelle tentative dans %ds", attente)
                time.sleep(attente)
                continue
            raise
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("Réponse Mistral non conforme au schéma")
    return parsed


def _extraire_anthropic(texte: str) -> ExtractionMarches:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    response = client.messages.parse(
        model=MODELE_ANTHROPIC,
        max_tokens=8000,
        system=PROMPT_SYSTEME,
        messages=[{"role": "user", "content": texte}],
        output_format=ExtractionMarches,
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Sortie tronquée (max_tokens)")
    return response.parsed_output
