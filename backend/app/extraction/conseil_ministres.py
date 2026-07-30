"""Structuration des comptes rendus du Conseil des ministres.

Étage 3 du pipeline (cadrage §5) : les CR sont en prose, l'extraction passe
par l'API Claude avec sortie structurée validée Pydantic. Un seul appel
extrait les DÉCISIONS (adoptions de décrets, rapports, communications,
autorisations…) et les NOMINATIONS individuelles. Tout arrive avec
statut_validation='a_valider' — l'extraction automatique ne publie jamais seule.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.extraction.texte import normaliser_nom
from app.models import Decision, Document, Nomination, Personne, Structure

logger = logging.getLogger(__name__)

MODELE_ANTHROPIC = "claude-opus-5"
MODELE_MISTRAL = "mistral-small-latest"
TEXTE_MINIMUM = 500  # en dessous, le document est un lien PDF / une traduction, pas un CR complet


class NominationExtraite(BaseModel):
    nom_complet: str = Field(description="Nom complet de la personne, tel qu'écrit dans le texte")
    poste: str = Field(description="Intitulé exact du poste ou de la fonction")
    structure: str | None = Field(
        default=None,
        description="Ministère, direction ou organisme concerné (nom complet si présent)",
    )
    sigle_structure: str | None = Field(
        default=None, description="Sigle de la structure s'il apparaît (ex: ARCOP, SONABEL)"
    )
    date_effet: date | None = Field(
        default=None, description="Date d'effet si mentionnée explicitement, sinon null"
    )
    type: Literal["nomination", "fin_fonction"] = Field(
        description="'fin_fonction' uniquement s'il s'agit d'une fin de mission/abrogation"
    )
    confiance: float = Field(ge=0, le=1, description="Certitude de l'extraction, entre 0 et 1")


class DecisionExtraite(BaseModel):
    ministere: str | None = Field(
        default=None,
        description="Ministère ou institution au titre duquel la mesure est prise "
        "(la rubrique « AU TITRE DE … »), sinon null",
    )
    type: Literal[
        "adoption_decret", "adoption_loi", "rapport", "communication", "autorisation", "autre"
    ] = Field(description="Nature de la mesure")
    objet: str = Field(
        description="Résumé fidèle de la mesure en 1 à 3 phrases, sans interprétation"
    )
    confiance: float = Field(ge=0, le=1, description="Certitude de l'extraction, entre 0 et 1")


class ExtractionCR(BaseModel):
    decisions: list[DecisionExtraite]
    nominations: list[NominationExtraite]


PROMPT_SYSTEME = """\
Tu structures un compte rendu officiel du Conseil des ministres du Burkina Faso.

1. DÉCISIONS : relève chaque mesure délibérée — adoption de décret ou de projet \
de loi, rapport adopté, communication, autorisation (missions, marchés…). Pour \
chacune : le ministère de rattachement (rubrique « AU TITRE DE … »), sa nature, \
et un résumé fidèle en 1 à 3 phrases, sans interprétation ni commentaire.

2. NOMINATIONS : relève chaque personne nommée (ou dont il est mis fin aux \
fonctions) : nom complet, poste, structure de rattachement, date d'effet si elle \
est écrite. Une mesure qui nomme des personnes va dans NOMINATIONS (une entrée \
par personne), pas dans DÉCISIONS.

N'invente rien — si une information manque, laisse le champ null. Si le texte ne \
contient rien pour une catégorie, retourne une liste vide."""


def extraire_cr(texte: str) -> ExtractionCR:
    """Point d'entrée unique — le fournisseur se choisit via FASO_LLM_PROVIDER."""
    if settings.llm_provider == "anthropic":
        return _extraire_anthropic(texte)
    return _extraire_mistral(texte)


def _extraire_mistral(texte: str) -> ExtractionCR:
    """Mistral La Plateforme — tier gratuit : ~1 req/s, retry sur 429."""
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
                response_format=ExtractionCR,
                temperature=0,
            )
            break
        except Exception as exc:  # noqa: BLE001 — le SDK lève des types variés selon le transport
            status = getattr(exc, "status_code", None)
            if status == 429 and tentative < 3:
                attente = 5 * (tentative + 1)
                logger.info("Mistral 429 (tier gratuit) — nouvelle tentative dans %ds", attente)
                time.sleep(attente)
                continue
            raise
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("Réponse Mistral non conforme au schéma — document à traiter manuellement")
    return parsed


def _extraire_anthropic(texte: str) -> ExtractionCR:
    import anthropic

    # api_key=None → le SDK résout la clé depuis l'environnement (ANTHROPIC_API_KEY / profil)
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    response = client.messages.parse(
        model=MODELE_ANTHROPIC,
        max_tokens=16000,
        system=PROMPT_SYSTEME,
        messages=[{"role": "user", "content": texte}],
        output_format=ExtractionCR,
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Sortie tronquée (max_tokens) — document à traiter manuellement")
    return response.parsed_output


def _personne(db: Session, nom_complet: str) -> Personne:
    norm = normaliser_nom(nom_complet)
    p = db.scalars(select(Personne).where(Personne.nom_normalise == norm)).first()
    if p is None:
        p = Personne(nom_complet=nom_complet, nom_normalise=norm)
        db.add(p)
        db.flush()
    return p


def _structure(db: Session, nom: str | None, sigle: str | None) -> Structure | None:
    if not nom and not sigle:
        return None
    if sigle:
        s = db.scalars(select(Structure).where(Structure.sigle == sigle)).first()
        if s:
            return s
    if nom:
        s = db.scalars(select(Structure).where(Structure.nom.ilike(nom))).first()
        if s:
            return s
    s = Structure(nom=nom or sigle, sigle=sigle)
    db.add(s)
    db.flush()
    return s


def traiter_document(db: Session, doc: Document) -> tuple[int, int]:
    """Structure un CR ; renvoie (nb décisions, nb nominations) créées.

    Un document déjà structuré (date_structuration non nulle) n'est pas retraité.
    """
    if doc.date_structuration is not None:
        return (0, 0)
    if not doc.texte_extrait or len(doc.texte_extrait) < TEXTE_MINIMUM:
        logger.info("Document %s ignoré (texte insuffisant) — marqué structuré", doc.id)
        doc.date_structuration = datetime.now(timezone.utc)
        db.commit()
        return (0, 0)

    extraction = extraire_cr(doc.texte_extrait)
    for d in extraction.decisions:
        db.add(
            Decision(
                document_id=doc.id,
                ministere=d.ministere,
                type=d.type,
                objet=d.objet,
                score_confiance=d.confiance,
                statut_validation="a_valider",
            )
        )
    for n in extraction.nominations:
        db.add(
            Nomination(
                document_id=doc.id,
                personne_id=_personne(db, n.nom_complet).id,
                structure_id=(s.id if (s := _structure(db, n.structure, n.sigle_structure)) else None),
                poste=n.poste,
                date_effet=n.date_effet,
                type=n.type,
                score_confiance=n.confiance,
                statut_validation="a_valider",
            )
        )
    doc.date_structuration = datetime.now(timezone.utc)
    db.commit()
    logger.info(
        "Document %s : %d décision(s), %d nomination(s) extraites",
        doc.id,
        len(extraction.decisions),
        len(extraction.nominations),
    )
    return (len(extraction.decisions), len(extraction.nominations))
