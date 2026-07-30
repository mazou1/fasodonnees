"""Registre des sources et de leurs collecteurs.

SEEDS décrit les sources en base (idempotent) ; COLLECTORS associe un
collecteur aux sources actives. Les sources institutionnelles vérifiées le
2026-07-09 (cadrage §3) sont pré-déclarées pour la suite, sans collecteur
tant que leur scraper n'existe pas.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.base import Collector
from app.ingestion.actualites_gouv import ActualitesGouvCollector
from app.ingestion.asce_lc import AsceLcCollector
from app.ingestion.assemblee import AssembleeCollector
from app.ingestion.conseil_constitutionnel import ConseilConstitutionnelCollector
from app.ingestion.conseil_ministres import ConseilMinistresCollector
from app.ingestion.dgcmef import DgcmefCollector
from app.ingestion.finances import BudgetCitoyenCollector
from app.ingestion.legiburkina import LegiburkinaCollector
from app.ingestion.rss import make_rss_collector
from app.models import Source

# (slug, nom, url_base, type, cadence)
SEEDS: list[tuple[str, str, str, str, str]] = [
    # Médias - flux RSS vérifiés (rapport v1 §1)
    ("lefaso", "leFaso.net", "https://lefaso.net", "media", "30min"),
    ("sidwaya", "Sidwaya", "https://www.sidwaya.info", "media", "30min"),
    ("burkina24", "Burkina24", "https://burkina24.com", "media", "30min"),
    ("aib", "Agence d'Information du Burkina", "https://www.aib.media", "media", "30min"),
    ("lepays", "Le Pays", "https://lepays.bf", "media", "30min"),
    # Institutionnel - vérifié HTTP 200 le 2026-07-09, scrapers à venir (phases 1-2)
    ("conseil_ministres", "Conseil des ministres", "https://www.gouvernement.gov.bf", "institutionnel", "hebdo"),
    ("actualites_gouv", "Actualités du gouvernement", "https://www.gouvernement.gov.bf", "institutionnel", "quotidien"),
    ("sig", "Service d'information du gouvernement", "https://www.sig.gov.bf", "institutionnel", "quotidien"),
    ("presidence", "Présidence du Faso", "https://www.presidencedufaso.bf", "institutionnel", "quotidien"),
    ("legiburkina", "Légiburkina (SGG-CM)", "https://www.legiburkina.gov.bf", "institutionnel", "quotidien"),
    ("assemblee", "Assemblée législative du peuple", "https://www.assembleenationale.bf", "institutionnel", "quotidien"),
    ("finances", "Ministère de l'Économie et des Finances", "https://www.finances.gov.bf", "institutionnel", "quotidien"),
    ("dgcmef", "Marchés publics (DGCMEF)", "https://www.dgcmef.gov.bf", "institutionnel", "quotidien"),
    ("jobf", "Journal officiel du Burkina Faso", "https://www.jobf.gov.bf", "institutionnel", "hebdo"),
    # Justice & contrôle - vérifié HTTP 200 le 2026-07-29. Publication peu
    # fréquente (quelques pièces par mois) : une passe hebdomadaire suffit.
    ("conseil_constitutionnel", "Conseil constitutionnel",
     "https://www.conseil-constitutionnel.gov.bf", "institutionnel", "hebdo"),
    ("asce_lc", "ASCE-LC (contrôle d'État et lutte anticorruption)",
     "https://www.asce-lc.bf", "institutionnel", "hebdo"),
    # NB : la Cour des comptes n'a pas de site accessible (aucun domaine ne
    # répond au 2026-07-29) - ses rapports ne sont donc pas collectables.
]

RSS_FEEDS: dict[str, str] = {
    "lefaso": "https://lefaso.net/spip.php?page=backend",
    "sidwaya": "https://www.sidwaya.info/feed",
    "burkina24": "https://burkina24.com/feed",
    "aib": "https://www.aib.media/feed",
    "lepays": "https://lepays.bf/feed",
}

COLLECTORS: dict[str, type[Collector]] = {
    slug: make_rss_collector(slug, url) for slug, url in RSS_FEEDS.items()
} | {
    ConseilMinistresCollector.slug: ConseilMinistresCollector,
    ActualitesGouvCollector.slug: ActualitesGouvCollector,
    LegiburkinaCollector.slug: LegiburkinaCollector,
    AssembleeCollector.slug: AssembleeCollector,
    BudgetCitoyenCollector.slug: BudgetCitoyenCollector,
    DgcmefCollector.slug: DgcmefCollector,
    ConseilConstitutionnelCollector.slug: ConseilConstitutionnelCollector,
    AsceLcCollector.slug: AsceLcCollector,
    # Présidence : wp-json fermé (401) mais flux RSS actif - communiqués officiels
    "presidence": make_rss_collector(
        "presidence", "https://www.presidencedufaso.bf/feed/", type_doc="communique"
    ),
    # NB : sig.gov.bf n'est pas collectable à ce jour (wp-json, /feed et
    # wp-sitemap redirigent tous vers l'accueil) - vérifié le 2026-07-10.
}


def seed_sources(db: Session) -> None:
    """Crée les sources manquantes (ne modifie jamais l'existant)."""
    known = set(db.scalars(select(Source.slug)).all())
    for slug, nom, url_base, type_, cadence in SEEDS:
        if slug not in known:
            db.add(Source(slug=slug, nom=nom, url_base=url_base, type=type_, cadence=cadence))
    db.commit()


def active_collectors(db: Session, groupe: str | None = None) -> list[type[Collector]]:
    actifs = set(db.scalars(select(Source.slug).where(Source.actif.is_(True))).all())
    return [
        cls
        for slug, cls in COLLECTORS.items()
        if slug in actifs and (groupe is None or cls.groupe == groupe)
    ]
