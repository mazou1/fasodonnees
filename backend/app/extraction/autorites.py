"""Réparation ciblée de l'autorité contractante manquante.

30 % des marchés extraits n'ont pas d'autorité contractante (801 sur 2 629, au
30 juillet 2026). Ce n'est pas une lacune du Quotidien : l'autorité y figure en
EN-TÊTE DE SECTION, et une même section couvre parfois plusieurs pages
d'attributions. La fenêtre de `marches_llm.py` s'arrête 1 200 caractères avant
le mot « attributaire » - assez pour l'objet et le montant, pas pour remonter
jusqu'à l'en-tête.

Élargir la fenêtre de l'extracteur principal coûterait cher sur les 100 % des
lignes pour ne servir qu'aux 30 % concernées, et le réextraire en entier
risquerait de créer des doublons : la moindre reformulation de l'objet par le
LLM change l'empreinte, donc échappe au garde-fou des republications.

D'où cette passe séparée qui, pour chaque marché déjà en base :
  1. le RETROUVE dans le texte du Quotidien (par sa référence, à défaut par son
     attributaire),
  2. remonte largement en arrière depuis ce point,
  3. ne demande au LLM que l'autorité contractante,
  4. n'écrit QUE ce champ - jamais de ligne créée, jamais un autre champ modifié.

Une autorité douteuse est pire qu'une autorité absente : elle attribuerait la
dépense au mauvais ministère. En dessous de `SEUIL_ECRITURE`, on ne touche à
rien.

Usage : python -m app.extraction.autorites [max_marches]
"""

from __future__ import annotations

import logging
import re
import sys
import time

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Document, Marche

logger = logging.getLogger(__name__)

# assez pour remonter à l'en-tête de section par-dessus quelques attributions
AVANT, APRES = 6000, 400
SEUIL_ECRITURE = 0.9

# Le Quotidien range ses attributions sous de grandes RUBRIQUES avant de nommer
# l'autorité elle-même. En remontant loin, le LLM tombe parfois sur la rubrique
# et la donne comme réponse : « Ministères, institutions et maîtrises d'ouvrages
# déléguées » n'est l'autorité contractante de personne, et remplirait le champ
# d'un intitulé qui ne désigne aucune administration.
#
# La comparaison porte sur le nom ENTIER : « Agence nationale d'appui au
# développement des collectivités territoriales » est une vraie autorité, et un
# test par sous-chaîne l'aurait écartée avec la rubrique « Collectivités
# territoriales ».
_RUBRIQUES = frozenset(
    {
        "ministeres, institutions et maitrises d'ouvrages deleguees",
        "ministeres, institutions et maitrises d'ouvrage deleguees",
        "maitrises d'ouvrages deleguees",
        "regions",
        "societes d'etat",
        "etablissements publics",
        "etablissements publics de l'etat",
        "collectivites territoriales",
        "autorites contractantes",
    }
)


def _est_une_rubrique(nom: str) -> bool:
    reduit = (
        nom.strip()
        .lower()
        .translate(str.maketrans("éèêëàâîïôöûüç’", "eeeeaaiioouuc'"))
        .strip(" .:-–—")
    )
    return reduit in _RUBRIQUES


class AutoriteExtraite(BaseModel):
    autorite: str | None = Field(
        default=None,
        description="Nom de l'autorité contractante (ministère, société d'État, "
        "collectivité, hôpital…) sous laquelle ce marché est publié, telle "
        "qu'écrite dans l'en-tête de section. null si elle n'apparaît pas.",
    )
    confiance: float = Field(
        ge=0, le=1, description="Certitude que cette autorité est bien celle DE CE marché"
    )


PROMPT_SYSTEME = """\
Tu lis un extrait du Quotidien des Marchés Publics du Burkina Faso (DGCMEF) et \
tu cherches UNE SEULE information : l'autorité contractante dont relève le \
marché signalé à la fin de l'extrait.

L'autorité contractante est le ministère, la société d'État, la collectivité \
territoriale ou l'établissement public qui passe le marché. Elle figure \
généralement en en-tête de section, au-dessus d'une série d'attributions, et \
peut se trouver loin en amont du marché concerné.

Règles :
- Réponds pour LE marché indiqué, pas pour un autre de l'extrait.
- Reprends le nom tel qu'il est écrit, sans l'abréger ni le développer.
- Si l'extrait contient plusieurs en-têtes, prends celui qui gouverne le marché \
indiqué, c'est-à-dire le dernier avant lui.
- Ne réponds JAMAIS par un intitulé de rubrique du journal - « Ministères, \
institutions et maîtrises d'ouvrages déléguées », « Régions », « Sociétés \
d'État », « Établissements publics » : ce sont les grandes sections du \
Quotidien, pas des autorités contractantes. Descends jusqu'à l'administration \
qui passe réellement le marché.
- `confiance` basse si tu hésites entre deux en-têtes ou si l'en-tête est \
tronqué. N'invente jamais : en cas de doute réel, autorite = null."""


def _position(texte: str, marche: Marche) -> int | None:
    """Où ce marché est-il imprimé dans le Quotidien ?

    La référence est le repère le plus sûr (elle est unique), l'attributaire le
    recours. Les deux peuvent avoir été normalisés à l'extraction alors que le
    PDF, lui, a gardé ses espaces multiples et ses apostrophes typographiques :
    on cherche donc sur une forme souple.
    """
    for indice in _reperes(marche):
        motif = re.escape(indice)
        # espaces du PDF : un seul dans nos données peut en valoir plusieurs
        motif = re.sub(r"\\ ", r"\\s+", motif)
        # apostrophes : ' et ’ sont interchangeables selon la police du PDF
        motif = motif.replace("'", "['’]").replace("’", "['’]")
        trouve = re.search(motif, texte, re.IGNORECASE)
        if trouve:
            return trouve.start()
    return None


# ponctuation et mise en forme que le LLM a pu ajouter ou retirer en recopiant
_BRUIT = re.compile(r"^[\s«»\"'\-–—:;,.()\[\]]+|[\s«»\"'\-–—:;,.()\[\]]+$")


def _reperes(marche: Marche):
    """Chaînes à chercher dans le PDF, de la plus sûre à la plus approximative.

    La référence identifie sans ambiguïté, l'attributaire presque. Restait 13 %
    des marchés introuvables : le LLM avait normalisé la référence (« n° » pour
    « N° ») ou nettoyé la raison sociale, si bien qu'aucune des deux ne se
    retrouvait telle quelle. D'où un troisième repère, le DÉBUT DE L'OBJET —
    moins distinctif, mais recopié plus littéralement, et suffisant ici : on ne
    cherche pas à identifier le marché, seulement à savoir OÙ il est imprimé
    pour remonter à l'en-tête qui le gouverne.
    """
    for brut in (marche.reference, marche.attributaire):
        indice = _BRUIT.sub("", brut or "")
        if len(indice) >= 6:
            yield indice
    objet = _BRUIT.sub("", marche.objet or "")
    # un préfixe : la fin de l'objet est souvent reformulée, le début non
    if len(objet) >= 25:
        yield objet[:60].rsplit(" ", 1)[0]


def _fenetre(texte: str, position: int, marche: Marche) -> str:
    extrait = texte[max(0, position - AVANT) : position + APRES]
    repere = marche.reference or marche.attributaire or marche.objet
    return (
        f"{extrait}\n\n---\nMARCHÉ CONCERNÉ : {repere}\n"
        f"Objet : {marche.objet}\n"
        "De quelle autorité contractante ce marché relève-t-il ?"
    )


def _demander(texte: str) -> AutoriteExtraite:
    if settings.llm_provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        from app.extraction.marches_llm import MODELE_ANTHROPIC

        reponse = client.messages.parse(
            model=MODELE_ANTHROPIC,
            max_tokens=500,
            system=PROMPT_SYSTEME,
            messages=[{"role": "user", "content": texte}],
            output_format=AutoriteExtraite,
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
                response_format=AutoriteExtraite,
                temperature=0,
            )
            break
        except Exception as exc:  # noqa: BLE001 - le SDK lève des types variés
            if getattr(exc, "status_code", None) == 429 and tentative < 3:
                attente = 5 * (tentative + 1)
                logger.info("Mistral 429 - nouvelle tentative dans %ds", attente)
                time.sleep(attente)
                continue
            raise
    parsee = reponse.choices[0].message.parsed
    if parsee is None:
        raise RuntimeError("Réponse Mistral non conforme au schéma")
    return parsee


def reparer(max_marches: int = 100) -> dict[str, int]:
    """Complète l'autorité des marchés qui n'en ont pas. Retourne le décompte."""
    compte = {
        "traites": 0, "remplis": 0, "introuvables": 0,
        "doute": 0, "rubriques": 0, "echecs": 0,
    }
    with SessionLocal() as db:
        marches = db.scalars(
            select(Marche)
            .where(Marche.autorite.is_(None))
            # groupés par document : le texte est chargé une fois par Quotidien
            .order_by(Marche.document_id, Marche.id)
            .limit(max_marches)
        ).all()
        if not marches:
            print("Aucun marché sans autorité contractante.")
            return compte

        doc_id_courant, texte = None, ""
        for i, marche in enumerate(marches):
            if marche.document_id != doc_id_courant:
                doc = db.get(Document, marche.document_id)
                texte = (doc.texte_extrait or "") if doc else ""
                doc_id_courant = marche.document_id
            compte["traites"] += 1
            if not texte:
                compte["introuvables"] += 1
                continue
            position = _position(texte, marche)
            if position is None:
                compte["introuvables"] += 1
                continue
            if i:
                time.sleep(1.2)  # politesse tier gratuit Mistral (~1 req/s)
            try:
                resultat = _demander(_fenetre(texte, position, marche))
            except Exception:  # noqa: BLE001
                compte["echecs"] += 1
                logger.warning("Marché %d : appel en échec, laissé tel quel", marche.id)
                continue
            if resultat.autorite and _est_une_rubrique(resultat.autorite):
                compte["rubriques"] += 1
            elif resultat.autorite and resultat.confiance >= SEUIL_ECRITURE:
                marche.autorite = resultat.autorite.strip()
                compte["remplis"] += 1
                if compte["remplis"] % 25 == 0:
                    db.commit()
                    logger.info("%d autorité(s) complétée(s)", compte["remplis"])
            else:
                # mieux vaut une autorité absente qu'une dépense imputée au
                # mauvais ministère
                compte["doute"] += 1
        db.commit()
    return compte


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    max_marches = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    c = reparer(max_marches)
    print(
        f"{c['traites']} marché(s) examiné(s) : {c['remplis']} autorité(s) complétée(s), "
        f"{c['doute']} laissée(s) vide(s) par prudence, "
        f"{c['rubriques']} rubrique(s) de journal écartée(s), "
        f"{c['introuvables']} introuvable(s) dans le texte, {c['echecs']} échec(s) d'appel."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
