"""Ce qui reste à publier, réseau par réseau.

Deux garde-fous portent l'essentiel du comportement :

0. la version de référence et la clé stable - le gouvernement RÉÉCRIT ses
   pages après publication (cf. app/versions.py) : un même compte rendu existe
   en base en quatre exemplaires, et une réécriture survenue le lendemain d'un
   post en créerait un cinquième. Sans ces deux règles, la page publierait
   quatre fois le conseil du 2 juillet, puis une cinquième après retouche ;

1. la fenêtre de fraîcheur - un item plus vieux que quelques jours n'est jamais
   publié. C'est elle qui fait qu'activer la diffusion sur une base contenant
   160 comptes rendus et 5 000 documents ne déverse pas des années d'archives
   sur la page, et qu'un flux d'actualités plus rapide que le quota d'un réseau
   ne crée pas un retard qui s'aggrave chaque jour ;

2. la priorité par genre - un compte rendu du Conseil des ministres passe avant
   une dépêche. Sans elle, le volume des actualités mangerait tout le quota et
   le contenu propre de la plateforme ne sortirait jamais.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.diffusion.messages import Item
from app.models import Decision, Document, Publication
# `_cle_decision` est LA définition, dans ce dépôt, de « la même décision d'une
# version à l'autre » : la réutiliser garantit que la diffusion et la
# consolidation ne se contredisent pas.
from app.versions import _cle_decision, ids_versions_de_reference

# Au-delà, l'item est abandonné : trois refus d'affilée signalent un jeton
# expiré ou un contenu rejeté, pas un incident réseau. Réessayer indéfiniment
# consommerait le quota mensuel de X sans rien publier.
MAX_TENTATIVES = 3

# Garde-fou de volume par requête : la fenêtre de fraîcheur borne déjà le
# nombre d'items, cette limite protège d'un import massif de documents antidatés.
PLAFOND_REQUETE = 300

GENRES = ("conseil", "decision", "actualite")
_PRIORITE = {genre: rang for rang, genre in enumerate(GENRES)}

TYPES_ACTUALITE = ("article_presse", "communique")


def plancher(fraicheur_jours: int, aujourdhui: date | None = None) -> date:
    return (aujourdhui or date.today()) - timedelta(days=max(fraicheur_jours, 0))


def cles_bloquees(db: Session, reseau: str) -> set[str]:
    """Les clés déjà publiées sur ce réseau, ou abandonnées après trop d'échecs.

    Un échec récent n'est PAS bloquant : le prochain passage réessaiera, ce qui
    couvre la coupure réseau et l'API momentanément indisponible.
    """
    return set(
        db.scalars(
            select(Publication.cle).where(
                Publication.reseau == reseau,
                or_(Publication.statut == "publie", Publication.tentatives >= MAX_TENTATIVES),
            )
        )
    )


def racines(db: Session, docs) -> dict[int, int]:
    """Identifiant stable d'un document à travers ses versions successives.

    Le `document.id` ne l'est pas : chaque réécriture d'une page officielle en
    crée un nouveau. La plus ancienne version d'un couple (source, url), elle,
    ne bouge plus - elle sert donc de racine aux clés du journal, sans quoi une
    page retouchée le lendemain d'un post serait republiée comme une nouveauté.
    """
    couples = {(d.source_id, d.url) for d in docs}
    if not couples:
        return {}
    lignes = db.execute(
        select(Document.source_id, Document.url, func.min(Document.id))
        .where(tuple_(Document.source_id, Document.url).in_(couples))
        .group_by(Document.source_id, Document.url)
    ).all()
    index = {(source_id, url): racine for source_id, url, racine in lignes}
    return {d.id: index.get((d.source_id, d.url), d.id) for d in docs}


def _empreinte(*parties) -> str:
    return hashlib.sha1("|".join(str(p) for p in parties).encode()).hexdigest()[:10]


def _nettoyer_ministere(libelle: str | None) -> str | None:
    """Retire le « AU TITRE DE … » qui introduit la rubrique dans le compte
    rendu. La casse du nom, elle, n'est pas retouchée : c'est le libellé
    officiel, et la plateforme ne réécrit pas ce qu'elle cite."""
    if not libelle:
        return None
    net = libelle.strip()
    for prefixe in ("AU TITRE DE LA ", "AU TITRE DE L'", "AU TITRE DES ", "AU TITRE DU ",
                    "AU TITRE DE "):
        if net.upper().startswith(prefixe):
            return net[len(prefixe):].strip() or None
    return net or None


def _conseils(db: Session, depuis: date, site: str) -> list[Item]:
    docs = db.scalars(
        select(Document)
        .where(
            Document.type_doc == "cr_conseil",
            Document.date_publication.is_not(None),
            Document.date_publication >= depuis,
            Document.id.in_(ids_versions_de_reference()),
        )
        .order_by(Document.date_publication, Document.id)
        .limit(PLAFOND_REQUETE)
    ).all()
    origines = racines(db, docs)
    return [
        Item(
            # la clé suit la racine, le lien la version de référence : c'est la
            # page à jour qui est partagée, mais le journal sait qu'elle a déjà
            # été publiée sous son ancienne version
            cle=f"conseil-{origines[d.id]}",
            genre="conseil",
            titre=d.titre or "Compte rendu du Conseil des ministres",
            lien=f"{site}/conseils/{d.id}",
            date=d.date_publication,
        )
        for d in docs
    ]


def _decisions(db: Session, depuis: date, site: str) -> list[Item]:
    """Seules les décisions VALIDÉES sortent : c'est la règle de la plateforme,
    et une extraction LLM non relue publiée sur une page publique serait bien
    plus difficile à rattraper qu'une ligne fausse dans le back-office."""
    lignes = db.execute(
        select(Decision, Document)
        .join(Document, Decision.document_id == Document.id)
        .where(
            Decision.statut_validation == "valide",
            Document.date_publication.is_not(None),
            Document.date_publication >= depuis,
            Document.id.in_(ids_versions_de_reference()),
        )
        .order_by(Document.date_publication, Decision.id)
        .limit(PLAFOND_REQUETE)
    ).all()
    origines = racines(db, [doc for _, doc in lignes])
    return [
        Item(
            # PAS `decision.id` : la consolidation qui suit une réécriture peut
            # garder la ligne de la nouvelle version et supprimer l'ancienne.
            # L'empreinte du contenu, elle, ne bouge pas - c'est la même
            # définition que celle qui sert à dédoublonner les entités.
            cle=f"decision-{origines[doc.id]}-{_empreinte(*_cle_decision(d))}",
            genre="decision",
            titre=d.objet,
            lien=f"{site}/conseils/{doc.id}",
            date=doc.date_publication,
            contexte=_nettoyer_ministere(d.ministere),
        )
        for d, doc in lignes
    ]


def _actualites(db: Session, depuis: date, site: str) -> list[Item]:
    """Le lien pointe vers l'article du média, pas vers une page du site.

    C'est déjà le choix de la page /actualites, et c'est le bon : la
    plateforme collecte les métadonnées de presse, pas le texte des articles.
    Renvoyer vers une page d'archive quasi vide pour capter le trafic
    d'un travail journalistique qui n'est pas le nôtre desservirait le lecteur
    autant que le média. La source est créditée dans le post lui-même
    (« via … »), ce qu'un simple partage de lien ne fait pas.
    """
    from app.extraction.texte import html_vers_texte

    docs = db.scalars(
        select(Document)
        .where(
            Document.type_doc.in_(TYPES_ACTUALITE),
            Document.date_publication.is_not(None),
            Document.date_publication >= depuis,
            Document.id.in_(ids_versions_de_reference()),
        )
        .order_by(Document.date_publication, Document.id)
        .limit(PLAFOND_REQUETE)
    ).all()
    origines = racines(db, docs)
    items = []
    for d in docs:
        resume = (d.meta or {}).get("resume")
        items.append(
            Item(
                cle=f"actu-{origines[d.id]}",
                genre="actualite",
                titre=d.titre or d.url,
                lien=d.url,
                date=d.date_publication,
                resume=html_vers_texte(resume) if resume else None,
                contexte=d.source.nom if d.source else None,
            )
        )
    return items


_COLLECTES = {"conseil": _conseils, "decision": _decisions, "actualite": _actualites}


def ordonner(items: list[Item], limite: int) -> list[Item]:
    """Priorité au genre, puis chronologie.

    Chronologie CROISSANTE : la page doit se lire comme un fil, pas rejouer les
    évènements à l'envers quand plusieurs items attendent.
    """
    tries = sorted(
        items,
        key=lambda it: (_PRIORITE.get(it.genre, 99), it.date or date.min, it.cle),
    )
    return tries[: max(limite, 0)]


def items_a_publier(
    db: Session,
    reseau: str,
    *,
    limite: int,
    fraicheur_jours: int,
    site_url: str,
    genres: tuple[str, ...] = GENRES,
    aujourdhui: date | None = None,
) -> list[Item]:
    if limite <= 0:
        return []
    depuis = plancher(fraicheur_jours, aujourdhui)
    site = site_url.rstrip("/")
    bloquees = cles_bloquees(db, reseau)
    candidats: list[Item] = []
    for genre in genres:
        collecte = _COLLECTES.get(genre)
        if collecte is None:
            continue
        candidats.extend(it for it in collecte(db, depuis, site) if it.cle not in bloquees)
    return ordonner(candidats, limite)
