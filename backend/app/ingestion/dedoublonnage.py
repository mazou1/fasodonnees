"""Purge des versions redondantes : même source, même adresse, même texte.

Jusqu'au 20 octobre 2026, le collecteur WordPress prenait l'empreinte du HTML
brut. Or WordPress numérote ses galeries à chaque rendu (« wp-block-gallery-16 »
un matin, « -20 » le lendemain) : un article au texte strictement identique
revenait chaque jour avec une empreinte neuve et passait pour une version de
plus. Constaté en production : 31 378 lignes pour 2 192 adresses d'actualités,
337 pour 151 comptes rendus du Conseil, le n°29 structuré deux fois.

Ce module ramène chaque groupe (source, url, texte) à UNE ligne, la plus
ancienne, et aligne son empreinte sur celle que le collecteur calcule désormais
(`empreinte_texte`), sans quoi la prochaine collecte recréerait tout le fonds.

Ce qu'il ne détruit pas :
- les entités extraites (décisions, nominations, réalisations, marchés…) des
  lignes supprimées sont reportées sur la ligne conservée - la consolidation
  les avait justement poussées sur la version la plus récente, souvent un
  doublon ;
- la ligne conservée est la plus ancienne : son identifiant sert de clé de
  diffusion sur les réseaux (cf. app/diffusion/selection.py), le changer
  republierait d'anciens conseils ;
- les versions au texte réellement différent restent des versions ;
- seules les pages HTML sont concernées : les PDF archivés par les mêmes
  collecteurs (comptes rendus, rapports) ont une empreinte fiable, celle du
  fichier, et deux PDF distincts sans texte extrait partageraient à tort
  l'empreinte du texte vide.

Usage, depuis le worker :

    python -m app.ingestion.dedoublonnage --simuler      # compte, ne touche à rien
    python -m app.ingestion.dedoublonnage                # purge base + bucket
    python -m app.ingestion.dedoublonnage conseil_ministres --garder-fichiers
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Iterable

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.ingestion.base import empreinte_texte
from app.models import (
    BudgetExercice,
    Decision,
    Document,
    DotationBudgetaire,
    EngagementFinancier,
    Marche,
    MembreGouvernement,
    Nomination,
    Realisation,
    RepartitionBudgetaire,
    Source,
)

logger = logging.getLogger(__name__)

MIME_HTML = "text/html"

# Toutes les tables qui pointent sur `document.id`. En oublier une ferait
# échouer la suppression (contrainte) - ou pire, perdrait des entités si la
# contrainte était en cascade.
ENFANTS: tuple[type, ...] = (
    Nomination,
    Decision,
    EngagementFinancier,
    BudgetExercice,
    MembreGouvernement,
    DotationBudgetaire,
    RepartitionBudgetaire,
    Marche,
    Realisation,
)


def slugs_wordpress() -> list[str]:
    """Les sources collectées via l'API WordPress - les seules touchées."""
    from app.ingestion.registry import COLLECTORS
    from app.ingestion.wordpress import WordPressCollector

    return [slug for slug, cls in COLLECTORS.items() if issubclass(cls, WordPressCollector)]


def dedoublonner(
    db: Session,
    slugs: Iterable[str],
    *,
    enfants: tuple[type, ...] = ENFANTS,
    supprimer_fichier: Callable[[str], None] | None = None,
    simuler: bool = False,
) -> dict[str, int]:
    """Supprime les versions au texte identique, source par source.

    `supprimer_fichier` reçoit la clé d'archive de chaque ligne supprimée,
    APRÈS validation en base - jamais en simulation.
    """
    stats = {
        "examinees": 0,
        "conservees": 0,
        "supprimees": 0,
        "entites_reportees": 0,
        "empreintes_alignees": 0,
        "fichiers_supprimes": 0,
        "fichiers_en_echec": 0,
    }
    for slug in slugs:
        source_id = db.scalar(select(Source.id).where(Source.slug == slug))
        if source_id is None:
            logger.warning("Source inconnue : %s", slug)
            continue
        orphelins: list[str] = []
        urls = db.scalars(
            select(Document.url)
            .where(Document.source_id == source_id, Document.mime == MIME_HTML)
            .distinct()
        ).all()
        avant = dict(stats)
        for url in urls:
            orphelins += _traiter_adresse(db, source_id, url, enfants, stats)
        if simuler:
            db.rollback()
        else:
            db.commit()
            if supprimer_fichier is not None:
                for cle in orphelins:
                    try:
                        supprimer_fichier(cle)
                        stats["fichiers_supprimes"] += 1
                    except Exception:  # noqa: BLE001 - un fichier qui résiste ne doit pas arrêter la purge
                        logger.exception("Fichier non supprimé : %s", cle)
                        stats["fichiers_en_echec"] += 1
        logger.info(
            "%s : %d ligne(s) examinée(s), %d conservée(s), %d supprimée(s), "
            "%d entité(s) reportée(s)%s",
            slug,
            stats["examinees"] - avant["examinees"],
            stats["conservees"] - avant["conservees"],
            stats["supprimees"] - avant["supprimees"],
            stats["entites_reportees"] - avant["entites_reportees"],
            " (simulation)" if simuler else "",
        )
    return stats


def _traiter_adresse(db: Session, source_id: int, url: str, enfants, stats) -> list[str]:
    """Une adresse : regroupe ses versions par texte, garde la première de chaque
    groupe, renvoie les clés d'archive devenues orphelines."""
    lignes = db.execute(
        select(
            Document.id,
            Document.texte_extrait,
            Document.fichier,
            Document.hash_contenu,
            Document.date_structuration,
        )
        .where(Document.source_id == source_id, Document.url == url, Document.mime == MIME_HTML)
        .order_by(Document.id)
    ).all()
    groupes: dict[str, list] = {}
    for ligne in lignes:
        groupes.setdefault(empreinte_texte(ligne.texte_extrait), []).append(ligne)

    orphelins: list[str] = []
    conservees = set()
    for empreinte, membres in groupes.items():
        garde, *redondantes = membres
        conservees.add(garde.fichier)
        stats["examinees"] += len(membres)
        stats["conservees"] += 1
        if redondantes:
            ids = [r.id for r in redondantes]
            for modele in enfants:
                stats["entites_reportees"] += db.execute(
                    update(modele)
                    .where(modele.document_id.in_(ids))
                    .values(document_id=garde.id)
                    .execution_options(synchronize_session=False)
                ).rowcount
            db.execute(delete(Document).where(Document.id.in_(ids)))
            stats["supprimees"] += len(ids)
            orphelins += [r.fichier for r in redondantes if r.fichier]

        valeurs = {}
        if garde.hash_contenu != empreinte:
            valeurs["hash_contenu"] = empreinte
            stats["empreintes_alignees"] += 1
        # la structuration d'un doublon vaut pour le texte qu'il partage
        structuration = max(
            (m.date_structuration for m in membres if m.date_structuration is not None),
            default=None,
        )
        if structuration is not None and structuration != garde.date_structuration:
            valeurs["date_structuration"] = structuration
        if valeurs:
            db.execute(update(Document).where(Document.id == garde.id).values(**valeurs))
    # une clé d'archive est propre à un contenu brut : jamais partagée avec une
    # ligne conservée, mais on s'en assure plutôt que de le supposer
    return [cle for cle in orphelins if cle not in conservees]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "slugs", nargs="*", help="sources à traiter (défaut : toutes les WordPress)"
    )
    parser.add_argument("--simuler", action="store_true", help="compter sans rien modifier")
    parser.add_argument(
        "--garder-fichiers", action="store_true", help="ne pas supprimer les bruts du bucket"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from app.db import SessionLocal
    from app.stockage import stockage

    with SessionLocal() as db:
        stats = dedoublonner(
            db,
            args.slugs or slugs_wordpress(),
            supprimer_fichier=None if args.garder_fichiers else stockage.supprimer,
            simuler=args.simuler,
        )
    print(
        f"{stats['examinees']} ligne(s) examinée(s) : {stats['conservees']} conservée(s), "
        f"{stats['supprimees']} supprimée(s), {stats['entites_reportees']} entité(s) reportée(s), "
        f"{stats['empreintes_alignees']} empreinte(s) alignée(s), "
        f"{stats['fichiers_supprimes']} fichier(s) supprimé(s)"
        + (f", {stats['fichiers_en_echec']} en échec" if stats["fichiers_en_echec"] else "")
        + (" - SIMULATION, rien n'a été modifié" if args.simuler else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
