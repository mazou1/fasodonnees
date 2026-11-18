"""Ce qui est nouveau, à qui l'envoyer, et le journal qui évite les doublons.

Lancé toutes les heures par le worker. Une alerte ne part que pour une donnée
VALIDÉE : tant qu'une nomination attend dans la file de /admin, personne n'en
est prévenu - la règle du site vaut aussi pour ses messages.

Un abonné reçoit au plus un message par alerte et par passage, qui regroupe
toutes les correspondances : suivre « ministère » un jeudi de Conseil ne doit
pas valoir quarante notifications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.alertes.bot import CANAL, normaliser, oublier
from app.config import settings
from app.models import (
    Abonnement,
    AlerteEnvoyee,
    Decision,
    Document,
    Nomination,
    VotePlenier,
)

logger = logging.getLogger(__name__)

# Fenêtre des nouveautés. Elle porte sur la COLLECTE du document, parce que la
# validation n'est pas datée : une nomination validée huit jours après le
# Conseil doit encore partir. Le plafond sur la date de publication écarte les
# rattrapages d'archives (2 795 textes anciens entrés d'un coup le 18/11/2026).
FENETRE_COLLECTE = timedelta(days=10)
ANCIENNETE_MAX = timedelta(days=45)
MAX_PAR_MESSAGE = 8
TYPES_TEXTES = ("loi", "decret", "arrete", "ordonnance", "texte_juridique")


@dataclass
class Element:
    """Une nouveauté susceptible de déclencher une alerte."""

    cle: str  # stable : sert au journal des envois
    titre: str
    lien: str
    texte: str  # normalisé, pour la recherche par mot-clé
    personne_id: int | None = None
    structures: set[int] = field(default_factory=set)
    mots: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        self.texte = normaliser(self.texte)
        self.mots = frozenset(self.texte.split())


def _court(texte: str, longueur: int = 220) -> str:
    texte = " ".join((texte or "").split())
    return texte if len(texte) <= longueur else texte[: longueur - 1].rstrip() + "…"


def _recents(maintenant: datetime):
    return (
        Document.date_collecte >= maintenant - FENETRE_COLLECTE,
        Document.date_publication >= (maintenant - ANCIENNETE_MAX).date(),
    )


def nouveautes(db: Session, maintenant: datetime | None = None) -> list[Element]:
    maintenant = maintenant or datetime.now(timezone.utc)
    site = settings.site_url
    elements: list[Element] = []

    nominations = db.scalars(
        select(Nomination)
        .join(Document, Nomination.document_id == Document.id)
        .where(Nomination.statut_validation == "valide", *_recents(maintenant))
    )
    for n in nominations:
        structure = n.structure
        nom_structure = f"{structure.nom} {structure.sigle or ''}" if structure else ""
        verbe = "Fin de fonction" if n.type == "fin_fonction" else "Nomination"
        ids = {structure.id, structure.canonique_id or structure.id} if structure else set()
        elements.append(
            Element(
                cle=f"nomination-{n.id}",
                titre=_court(f"{verbe} : {n.personne.nom_complet} - {n.poste}"),
                lien=f"{site}/personnes/{n.personne_id}",
                texte=f"{n.personne.nom_complet} {n.poste} {nom_structure}",
                personne_id=n.personne_id,
                structures=ids,
            )
        )

    decisions = db.scalars(
        select(Decision)
        .join(Document, Decision.document_id == Document.id)
        .where(Decision.statut_validation == "valide", *_recents(maintenant))
    )
    for d in decisions:
        elements.append(
            Element(
                cle=f"decision-{d.id}",
                titre=_court(f"Conseil des ministres : {d.objet}"),
                lien=f"{site}/conseils/{d.document_id}",
                texte=f"{d.objet} {d.ministere or ''}",
            )
        )

    votes = db.scalars(
        select(VotePlenier)
        .join(Document, VotePlenier.document_id == Document.id)
        .where(VotePlenier.statut_validation == "valide", *_recents(maintenant))
    )
    for v in votes:
        verbe = "rejette" if v.resultat == "rejete" else "adopte"
        elements.append(
            Element(
                cle=f"vote-{v.id}",
                titre=_court(f"L'Assemblée {verbe} : {v.intitule}"),
                lien=f"{site}/assemblee/votes",
                texte=f"{v.intitule} {v.resume or ''}",
            )
        )

    textes = db.scalars(
        select(Document).where(Document.type_doc.in_(TYPES_TEXTES), *_recents(maintenant))
    )
    for t in textes:
        meta = t.meta or {}
        # la description d'origine ; `texte_extrait` peut porter des pages d'OCR
        description = meta.get("description") or (
            t.texte_extrait if t.statut_extraction == "na" else ""
        )
        elements.append(
            Element(
                cle=f"texte-{t.id}",
                titre=_court(f"{t.titre or 'Texte'} : {description}"),
                lien=f"{site}/documents/{t.id}",
                texte=f"{t.titre or ''} {meta.get('reference') or ''} {description or ''}",
            )
        )
    return elements


def correspond(abonnement: Abonnement, element: Element) -> bool:
    if abonnement.genre == "personne":
        return element.personne_id is not None and str(element.personne_id) == abonnement.valeur
    if abonnement.genre == "structure":
        return any(str(s) == abonnement.valeur for s in element.structures)
    # mot-clé : tous ses mots, entiers, dans n'importe quel ordre - « ouedraogo
    # gilbert » trouve « Pingdwendé Gilbert OUEDRAOGO », « mine » ne trouve pas
    # « ministre »
    mots = abonnement.valeur.split()
    return bool(mots) and all(mot in element.mots for mot in mots)


def composer(abonnement: Abonnement, elements: list[Element]) -> str:
    total = len(elements)
    entete = f"🔔 {abonnement.libelle} - {total} nouveauté{'s' if total > 1 else ''}"
    lignes = [entete, ""]
    for e in elements[:MAX_PAR_MESSAGE]:
        lignes += [f"• {e.titre}", f"  {e.lien}"]
    if total > MAX_PAR_MESSAGE:
        lignes += ["", f"… et {total - MAX_PAR_MESSAGE} autres sur {settings.site_url}"]
    lignes += ["", "/liste pour gérer vos alertes"]
    return "\n".join(lignes)


def envoyer_alertes(db: Session, telegram, maintenant: datetime | None = None) -> dict[str, int]:
    """Envoie à chaque abonné ce qui correspond et n'a pas encore été envoyé."""
    from app.diffusion.reseaux import ErreurReseau

    bilan = {"abonnements": 0, "messages": 0, "elements": 0, "echecs": 0, "desabonnes": 0}
    abonnements = db.scalars(select(Abonnement).where(Abonnement.canal == CANAL)).all()
    if not abonnements:
        return bilan
    elements = nouveautes(db, maintenant)
    bloques: set[str] = set()
    for abonnement in abonnements:
        bilan["abonnements"] += 1
        if abonnement.destinataire in bloques:
            continue
        deja = set(
            db.scalars(
                select(AlerteEnvoyee.cle).where(AlerteEnvoyee.abonnement_id == abonnement.id)
            )
        )
        a_envoyer = [e for e in elements if e.cle not in deja and correspond(abonnement, e)]
        if not a_envoyer:
            continue
        try:
            telegram.envoyer(abonnement.destinataire, composer(abonnement, a_envoyer))
        except ErreurReseau as exc:
            if "403" in str(exc) or "blocked" in str(exc).lower():
                # l'abonné a bloqué ou supprimé le bot : on n'insiste pas, et on
                # ne garde pas ses données
                bloques.add(abonnement.destinataire)
                bilan["desabonnes"] += 1
            else:
                bilan["echecs"] += 1
                logger.warning("Alerte %s non envoyée : %s", abonnement.id, exc)
            continue
        for e in a_envoyer:
            db.add(AlerteEnvoyee(abonnement_id=abonnement.id, cle=e.cle))
        db.commit()
        bilan["messages"] += 1
        bilan["elements"] += len(a_envoyer)
    for chat_id in bloques:
        oublier(db, chat_id)
    return bilan


def purger_journal(db: Session) -> int:
    """Retire du journal les envois sortis de la fenêtre : ils ne peuvent plus
    être reproposés, les garder ne servirait qu'à faire grossir la table."""
    limite = datetime.now(timezone.utc) - (ANCIENNETE_MAX + FENETRE_COLLECTE)
    resultat = db.execute(delete(AlerteEnvoyee).where(AlerteEnvoyee.date_envoi < limite))
    db.commit()
    return resultat.rowcount or 0
