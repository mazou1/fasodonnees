"""Extraction des réalisations d'infrastructure depuis les actualités.

Sur les billets d'actualité (gouvernement.gov.bf #13, communiqués, presse), on
détecte les inaugurations / ouvertures / lancements d'infrastructures publiques
et on les structure (type, lieu, date, statut…), on géocode à la commune, puis
on dépose en `a_valider`. Registre FACTUEL : le champ `statut` distingue une
annonce d'un ouvrage livré ; chaque entrée renvoie à son document source.

Économie d'appels LLM : un PRÉ-FILTRE par mots-clés écarte d'emblée les
actualités hors sujet (sport, diplomatie…) - l'immense majorité du fil.

Usage : python -m app.extraction.realisations [max_docs]
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.geo import geocoder, normaliser_lieu
from app.models import Document, Realisation

logger = logging.getLogger(__name__)

MODELE_ANTHROPIC = "claude-opus-5"
MODELE_MISTRAL = "mistral-small-latest"

# Types d'ouvrage documentés (chaîne libre en base) → secteur d'affichage.
SECTEUR_PAR_TYPE = {
    "route": "Transport & mobilité",
    "pont": "Transport & mobilité",
    "aeroport": "Transport & mobilité",
    "usine": "Industrie",
    "hopital": "Santé",
    "centre_sante": "Santé",
    "ecole": "Éducation & formation",
    "universite": "Éducation & formation",
    "barrage": "Eau & assainissement",
    "adduction_eau": "Eau & assainissement",
    "electrification": "Énergie",
    "energie": "Énergie",
    "logement": "Habitat & urbanisme",
    "batiment_public": "Bâtiments publics",
    "marche_infrastructure": "Commerce",
    "autre": "Autres",
}
TYPES = tuple(SECTEUR_PAR_TYPE)

# Pré-filtre : l'actualité doit évoquer une infrastructure ET un acte
# d'ouverture/livraison pour valoir un appel LLM.
_OUVRAGE = re.compile(
    r"inaugur|pose\s+(?:de\s+)?(?:la\s+)?premi[eè]re\s+pierre|mise\s+en\s+service"
    r"|mis\s+en\s+service|r[ée]ceptionn|livr[ée]|ouvertur|lancement\s+des?\s+travaux"
    r"|construction|r[ée]habilit|bitum|[ée]lectrifi|raccord",
    re.I,
)
_INFRA = re.compile(
    r"route|pont|[ée]changeur|usine|unit[ée]\s+de\s+production|h[oô]pital|\bcsps\b"
    r"|\bchr\b|\bchu\b|centre\s+de\s+sant[ée]|[ée]cole|lyc[ée]e|coll[èe]ge|universit"
    r"|barrage|forage|adduction|ch[aâ]teau\s+d.eau|centrale|[ée]nergie|solaire"
    r"|logement|cit[ée]|march[ée]|a[ée]roport|infrastructure|b[aâ]timent|si[èe]ge"
    r"|stade|boulevard|voie|piste",
    re.I,
)


def pertinent(titre: str | None, texte: str | None) -> bool:
    """Vrai si l'actualité mérite un passage LLM (parle d'un ouvrage et d'un
    acte d'ouverture)."""
    blob = f"{titre or ''}\n{texte or ''}"
    return bool(_OUVRAGE.search(blob) and _INFRA.search(blob))


class RealisationExtraite(BaseModel):
    type: Literal[
        "route", "pont", "usine", "hopital", "centre_sante", "ecole", "universite",
        "barrage", "adduction_eau", "electrification", "energie", "logement",
        "marche_infrastructure", "aeroport", "batiment_public", "autre",
    ] = Field(description="Nature de l'ouvrage")
    titre: str = Field(description="Intitulé court et neutre de l'ouvrage (sans emphase)")
    description: str | None = Field(
        default=None, description="1 à 2 phrases factuelles décrivant l'ouvrage"
    )
    statut: Literal["annonce", "premiere_pierre", "inauguration", "mise_en_service"] = Field(
        description="annonce=projet évoqué ; premiere_pierre=lancement des travaux ; "
        "inauguration=cérémonie d'ouverture ; mise_en_service=entrée en fonction"
    )
    lieu: str | None = Field(
        default=None, description="Commune ou ville où se situe l'ouvrage (le nom seul) ; "
        "pour une route/piste reliant deux localités, la localité de DÉPART"
    )
    lieu_arrivee: str | None = Field(
        default=None,
        description="UNIQUEMENT pour un ouvrage linéaire (route, piste, pont) reliant deux "
        "localités : la localité d'ARRIVÉE (l'autre extrémité). Sinon null.",
    )
    region: str | None = Field(default=None, description="Région, si mentionnée")
    date_evenement: date | None = Field(
        default=None, description="Date de l'événement si écrite, sinon null"
    )
    maitre_ouvrage: str | None = Field(
        default=None, description="Ministère/structure porteur, si mentionné"
    )
    montant_fcfa: int | None = Field(
        default=None, description="Coût en FCFA si un montant chiffré est donné, sinon null"
    )
    confiance: float = Field(ge=0, le=1, description="Certitude de l'extraction")


class ExtractionRealisations(BaseModel):
    realisations: list[RealisationExtraite]


PROMPT_SYSTEME = """\
Tu analyses un article d'actualité officiel du Burkina Faso pour un registre \
FACTUEL et non partisan des infrastructures publiques.

Relève UNIQUEMENT les inaugurations, poses de première pierre, mises en service \
ou lancements de travaux d'infrastructures PUBLIQUES concrètes : routes, ponts, \
usines/unités de production, hôpitaux/CSPS, écoles/universités, barrages, \
forages/adductions d'eau, centrales/électrification, logements, marchés, \
aéroports, bâtiments publics.

IGNORE tout le reste : nominations, sport, diplomatie, discours, réunions, \
communiqués sans ouvrage, remises de matériel, résultats d'examens, etc. Si \
l'article ne rapporte aucun ouvrage concret, retourne une liste VIDE.

Pour chaque ouvrage : sa nature (type), un intitulé court et NEUTRE (sans \
emphase ni jugement), le lieu (commune/ville) et la région, la date si elle est \
écrite, le statut exact (annonce / première pierre / inauguration / mise en \
service - ne présente pas une annonce comme un ouvrage livré), le maître \
d'ouvrage et le montant si chiffré. N'invente rien : laisse null ce qui manque."""


def extraire(texte: str) -> ExtractionRealisations:
    if settings.llm_provider == "anthropic":
        return _extraire_anthropic(texte)
    return _extraire_mistral(texte)


def _extraire_mistral(texte: str) -> ExtractionRealisations:
    from mistralai.client import Mistral

    client = Mistral(api_key=settings.mistral_api_key)
    for tentative in range(4):
        try:
            response = client.chat.parse(
                model=MODELE_MISTRAL,
                messages=[
                    {"role": "system", "content": PROMPT_SYSTEME},
                    {"role": "user", "content": texte[:12000]},
                ],
                response_format=ExtractionRealisations,
                temperature=0,
            )
            break
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "status_code", None) == 429 and tentative < 3:
                time.sleep(5 * (tentative + 1))
                continue
            raise
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("Réponse Mistral non conforme au schéma")
    return parsed


def _extraire_anthropic(texte: str) -> ExtractionRealisations:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    response = client.messages.parse(
        model=MODELE_ANTHROPIC,
        max_tokens=8000,
        system=PROMPT_SYSTEME,
        messages=[{"role": "user", "content": texte[:12000]}],
        output_format=ExtractionRealisations,
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Sortie tronquée (max_tokens)")
    return response.parsed_output


def _doublon(db: Session, type_: str, localite_id: int | None, lieu_norm: str,
             date_ev: date | None) -> bool:
    """Même ouvrage déjà en base (même événement rapporté plusieurs fois) :
    même type + même localité (ou même lieu normalisé) + même date."""
    q = select(Realisation.id).where(
        Realisation.type == type_,
        Realisation.statut_validation != "rejete",
    )
    if localite_id is not None:
        q = q.where(Realisation.localite_id == localite_id)
    elif lieu_norm:
        q = q.where(Realisation.localisation_nom.is_not(None))
    if date_ev is not None:
        q = q.where(Realisation.date_evenement == date_ev)
    for (rid,) in db.execute(q).all():
        r = db.get(Realisation, rid)
        if localite_id is not None or normaliser_lieu(r.localisation_nom) == lieu_norm:
            return True
    return False


def traiter_document(db: Session, doc: Document) -> int:
    """Extrait les réalisations d'un document ; renvoie le nombre créé.
    Marque le document traité (date_structuration) même si rien n'est trouvé."""
    if doc.date_structuration is not None:
        return 0
    texte = doc.texte_extrait or ""
    if not pertinent(doc.titre, texte):
        doc.date_structuration = datetime.now(timezone.utc)
        db.commit()
        return 0

    extraction = extraire(f"{doc.titre or ''}\n\n{texte}")
    date_doc = doc.date_publication
    cree = 0
    for r in extraction.realisations:
        loc = geocoder(db, r.lieu or r.region)
        loc_arr = geocoder(db, r.lieu_arrivee) if r.lieu_arrivee else None
        lieu_norm = normaliser_lieu(r.lieu or r.region)
        date_ev = r.date_evenement or date_doc
        if _doublon(db, r.type, loc.id if loc else None, lieu_norm, date_ev):
            continue
        db.add(
            Realisation(
                document_id=doc.id,
                type=r.type,
                titre=r.titre[:500],
                description=r.description,
                statut=r.statut,
                date_evenement=date_ev,
                localite_id=loc.id if loc else None,
                localisation_nom=r.lieu or r.region,
                region=(loc.region if loc else r.region),
                latitude=loc.latitude if loc else None,
                longitude=loc.longitude if loc else None,
                localisation_nom_arr=r.lieu_arrivee if loc_arr else None,
                latitude_arr=loc_arr.latitude if loc_arr else None,
                longitude_arr=loc_arr.longitude if loc_arr else None,
                precision_geo=("commune" if loc and loc.type == "commune"
                               else "region" if loc else None),
                secteur=SECTEUR_PAR_TYPE.get(r.type, "Autres"),
                maitre_ouvrage=r.maitre_ouvrage,
                montant_fcfa=r.montant_fcfa,
                source_url=doc.url,
                score_confiance=r.confiance,
                statut_validation="a_valider",
            )
        )
        cree += 1
    doc.date_structuration = datetime.now(timezone.utc)
    db.commit()
    if cree:
        logger.info("Document %s : %d réalisation(s) extraites", doc.id, cree)
    return cree


TYPES_ACTUALITE = ("actualite_gouv", "communique", "article_presse")
TYPES_LINEAIRES = ("route", "pont")


# mot-clé d'ouvrage linéaire suivi du segment décrivant les extrémités
_SEG_LINEAIRE = re.compile(
    r"(?:route|tron[çc]on|autoroute|piste|liaison|axe|voie|bretelle)\s+"
    r"(?:rurale?\s+|nationale?\s+|reliant\s+|de\s+|du\s+|des\s+)*([^,;:.]+)",
    re.I,
)
_RELIANT = re.compile(r"(?:reliant|entre)\s+([^,;:.]+?)\s+(?:et|à|a)\s+([^,;:.]+)", re.I)


def _candidats_termini(titre: str) -> list[tuple[str, str]]:
    """Paires (départ, arrivée) candidates lues dans un titre de route/pont."""
    paires: list[tuple[str, str]] = []
    m = _RELIANT.search(titre)
    if m:
        paires.append((m.group(1).strip(), m.group(2).strip()))
    m = _SEG_LINEAIRE.search(titre)
    if m:
        seg = m.group(1).strip()
        for sep in ["-", "-", " à ", " a ", " et "]:
            if sep in seg:
                a, b = seg.split(sep, 1)
                paires.append((a.strip(), b.strip()))
                break
        else:
            # trait d'union : ambigu (Bobo-Dioulasso). On tente chaque coupure ;
            # la bonne est celle dont les deux côtés géocodent (cf. appelant).
            toks = [t for t in seg.split("-") if t.strip()]
            for k in range(1, len(toks)):
                paires.append(("-".join(toks[:k]).strip(), "-".join(toks[k:]).strip()))
    return paires


def enrichir_liaisons(db: Session) -> int:
    """Pour les réalisations linéaires (route/pont) sans second point, déduit les
    deux extrémités du TITRE (déterministe) et ne retient une liaison que si les
    deux côtés géocodent vers des localités distinctes. Renvoie le nombre tracé."""
    rows = db.scalars(
        select(Realisation).where(
            Realisation.type.in_(TYPES_LINEAIRES),
            Realisation.latitude_arr.is_(None),
        )
    ).all()
    ajouts = 0
    for r in rows:
        for a_nom, b_nom in _candidats_termini(r.titre):
            a, b = geocoder(db, a_nom), geocoder(db, b_nom)
            if a and b and a.id != b.id:
                r.localisation_nom = a.nom
                r.latitude, r.longitude, r.region = a.latitude, a.longitude, a.region
                r.localisation_nom_arr = b.nom
                r.latitude_arr, r.longitude_arr = b.latitude, b.longitude
                ajouts += 1
                logger.info("Liaison %s : %s → %s", r.id, a.nom, b.nom)
                break
    db.commit()
    return ajouts


def traiter_lot(db: Session, max_docs: int) -> tuple[int, int, int, int]:
    """Traite jusqu'à `max_docs` actualités non structurées (plus récentes
    d'abord). Renvoie (docs vus, réalisations créées, écartées, échecs)."""
    docs = db.scalars(
        select(Document)
        .where(
            Document.type_doc.in_(TYPES_ACTUALITE),
            Document.date_structuration.is_(None),
        )
        .order_by(Document.date_publication.desc().nulls_last())
        .limit(max_docs)
    ).all()
    total = filtres = echecs = appels = 0
    for doc in docs:
        if not pertinent(doc.titre, doc.texte_extrait):
            doc.date_structuration = datetime.now(timezone.utc)
            filtres += 1
            continue
        if appels:
            time.sleep(1.5)  # politesse tier gratuit Mistral (~1 req/s)
        appels += 1
        try:
            total += traiter_document(db, doc)
        except Exception:  # noqa: BLE001
            logging.exception("Échec sur le document %s - on continue", doc.id)
            db.rollback()
            echecs += 1
    db.commit()
    return len(docs), total, filtres, echecs


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import sys

    # sous-commande d'enrichissement des liaisons routières
    if len(sys.argv) > 1 and sys.argv[1] == "liaisons":
        with SessionLocal() as db:
            n = enrichir_liaisons(db)
        print(f"{n} liaison(s) routière(s) tracée(s) (départ → arrivée).")
        return 0

    max_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    with SessionLocal() as db:
        vus, total, filtres, echecs = traiter_lot(db, max_docs)
        if not vus:
            print("Aucune actualité en attente.")
            return 0
        print(
            f"{vus} actualité(s) : {total} réalisation(s) extraites (à valider), "
            f"{filtres} écartée(s) par le pré-filtre"
            + (f", {echecs} échec(s)." if echecs else ".")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
