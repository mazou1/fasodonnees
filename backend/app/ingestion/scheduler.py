"""Worker d'ingestion : APScheduler, cadences du cadrage §3.

Un seul process, pas de file distribuée - les volumes (dizaines de
documents/jour) ne justifient ni Celery ni Airflow.
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.ingestion.registry import active_collectors, seed_sources
from app.ingestion.surveillance import verifier_sources_muettes

logger = logging.getLogger(__name__)


def _cle_llm() -> str | None:
    return (
        settings.mistral_api_key
        if settings.llm_provider == "mistral"
        else settings.anthropic_api_key
    )


def run_medias() -> None:
    with SessionLocal() as db:
        for cls in active_collectors(db, groupe="media"):
            cls(db).run()


def run_institutionnel() -> None:
    """Sources institutionnelles quotidiennes (Légiburkina, actualités gouv…)
    puis extraction bornée des réalisations d'infrastructure sur les nouvelles
    actualités (si une clé LLM est disponible)."""
    with SessionLocal() as db:
        for cls in active_collectors(db, groupe="institutionnel"):
            cls(db).run()
    if not _cle_llm():
        return
    from app.extraction.realisations import traiter_lot

    with SessionLocal() as db:
        # borné : le flot quotidien est faible ; le backfill se lance à la main
        vus, total, _, echecs = traiter_lot(db, max_docs=60)
    logger.info(
        "Réalisations : %d actualité(s) examinée(s), %d extraite(s) (à valider), %d échec(s)",
        vus, total, echecs,
    )


def run_marches_publics() -> None:
    """Chaîne complète des marchés : extraction LLM, autorités, consolidation.

    Elle tourne APRÈS la collecte institutionnelle du matin, qui a rapatrié les
    Quotidiens de la DGCMEF. Rien ici ne doit rester à lancer à la main : le
    rôle de l'administrateur se limite à valider dans `/admin`.
    """
    if not _cle_llm():
        logger.warning("Aucune clé LLM - extraction des marchés non lancée")
        return
    from app.attributaires import consolider
    from app.extraction.autorites import reparer
    from app.extraction.marches import empreintes_connues, traiter_document
    from app.models import Document, Marche

    with SessionLocal() as db:
        deja = select(Marche.document_id).distinct().subquery()
        docs = db.scalars(
            select(Document)
            .where(
                Document.type_doc == "marche_public",
                Document.texte_extrait.is_not(None),
                Document.id.not_in(select(deja.c.document_id)),
            )
            .order_by(Document.date_publication.desc().nulls_last())
            # borné : le flot quotidien est de quelques Quotidiens ; un arriéré
            # se résorbe sur plusieurs jours plutôt qu'en saturant le worker,
            # qui partage 3 vCPU avec le reste de la machine
            .limit(15)
        ).all()
        connues = empreintes_connues(db) if docs else set()
        total = republications = 0
        for doc in docs:
            n, ignores = traiter_document(db, doc, connues)
            total += n
            republications += ignores
    logger.info(
        "Marchés : %d Quotidien(s), %d attribution(s) à valider, %d republication(s) ignorée(s)",
        len(docs), total, republications,
    )

    # L'autorité contractante figure en en-tête de section, hors de la fenêtre
    # de l'extracteur : sans cette passe, 30 % des marchés restent sans
    # ministère rattaché (cf. app/extraction/autorites.py).
    c = reparer(max_marches=120)
    logger.info(
        "Autorités : %d complétée(s) sur %d examinée(s)", c["remplis"], c["traites"]
    )

    # Sans consolidation, chaque graphie d'une même entreprise reste une fiche
    # séparée et les nouveaux marchés n'ont pas d'attributaire rattaché.
    with SessionLocal() as db:
        r = consolider(db)
    logger.info("Attributaires consolidés : %s", r)


def run_ocr() -> None:
    """Océrisation des scans, de nuit : Tesseract sature le CPU partagé.

    Bornée par passage - l'arriéré se résorbe sur plusieurs nuits plutôt que
    d'immobiliser la machine, et un document non océrisé reste consultable en
    PDF entre-temps.
    """
    from app.extraction.ocr_textes import main as ocr_main

    ocr_main(max_docs=40)


def run_pdf_textes() -> None:
    """Rapatriement des PDF de Légiburkina et texte natif, avant l'OCR."""
    from app.extraction.pdf_textes import main as pdf_main

    pdf_main(max_docs=150)


def run_conseil_ministres() -> None:
    """Collecte des CR puis structuration LLM (si une clé API est disponible)."""
    with SessionLocal() as db:
        for cls in active_collectors(db, groupe="cm"):
            cls(db).run()
    if not _cle_llm():
        logger.warning(
            "Aucune clé API pour le fournisseur '%s' - structuration des CR non lancée",
            settings.llm_provider,
        )
        return
    from app.extraction import run as extraction_run

    extraction_run.main()

    # Le gouvernement RÉÉCRIT ses pages après publication : `upsert_document`
    # crée alors une nouvelle version, et la structuration repasse dessus. Sans
    # consolidation, le conseil du 23 juillet 2026 s'est retrouvé avec ses
    # décisions extraites deux fois, sur deux versions du même document - donc
    # comptées deux fois dans la file de validation et dans les statistiques.
    from app.versions import consolider_entites

    with SessionLocal() as db:
        stats = consolider_entites(db)
    logger.info("Versions consolidées : %s", stats)


def construire_scheduler() -> BlockingScheduler:
    """Toutes les cadences, sans effet de bord.

    Séparé de `main()` pour qu'un test puisse vérifier qu'AUCUNE étape de la
    chaîne n'est restée à lancer à la main : la promesse faite à
    l'administrateur est qu'il n'a qu'à valider dans `/admin`, et cette
    promesse doit se casser dans les tests, pas en production.
    """
    # misfire_grace_time large : sur une machine qui se met en veille (WSL2,
    # portable), un déclenchement dû pendant la suspension serait sinon « manqué »
    # et sauté au réveil - d'où des sources muettes silencieuses. 6h de tolérance
    # + coalesce : le job dû tourne une fois au réveil.
    scheduler = BlockingScheduler(
        timezone="Africa/Ouagadougou",
        job_defaults={"coalesce": True, "misfire_grace_time": 6 * 3600},
    )
    scheduler.add_job(run_medias, "interval", minutes=30, id="medias", coalesce=True)
    scheduler.add_job(
        verifier_sources_muettes,
        CronTrigger(hour=7, minute=30),
        id="alerte_sources_muettes",
    )
    # Le Conseil des ministres se tient désormais le jeudi ; le CR est publié
    # le soir ou le lendemain - passage jeudi soir + rattrapages.
    scheduler.add_job(
        run_conseil_ministres,
        CronTrigger(day_of_week="thu", hour=20, minute=0),
        id="cm_jeudi",
        coalesce=True,
    )
    scheduler.add_job(
        run_conseil_ministres,
        CronTrigger(day_of_week="fri,sat", hour=10, minute=0),
        id="cm_rattrapage",
        coalesce=True,
    )
    # Institutionnel quotidien : Légiburkina (textes juridiques) tôt le matin.
    # La Présidence passe par le job RSS « medias » toutes les 30 min.
    scheduler.add_job(
        run_institutionnel,
        CronTrigger(hour=6, minute=0),
        id="institutionnel_quotidien",
        coalesce=True,
    )

    # Chaîne des marchés publics, après la collecte institutionnelle de 6h qui
    # a rapatrié les Quotidiens de la DGCMEF.
    scheduler.add_job(
        run_marches_publics,
        CronTrigger(hour=7, minute=15),
        id="marches_quotidien",
        coalesce=True,
    )
    # PDF des textes juridiques : le texte natif d'abord, l'OCR ne prend que ce
    # qui reste illisible.
    scheduler.add_job(
        run_pdf_textes,
        CronTrigger(hour=6, minute=45),
        id="pdf_textes_quotidien",
        coalesce=True,
    )
    # OCR de nuit : Tesseract sature le CPU, que le worker partage avec le reste
    # de la machine. Heure creuse à Ouagadougou.
    scheduler.add_job(
        run_ocr,
        CronTrigger(hour=2, minute=0),
        id="ocr_nocturne",
        coalesce=True,
    )

    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with SessionLocal() as db:
        seed_sources(db)
    scheduler = construire_scheduler()

    logger.info("Worker d'ingestion démarré - collecte immédiate puis cadences planifiées")
    run_medias()
    run_conseil_ministres()
    run_institutionnel()
    # Au redémarrage, les Quotidiens collectés juste avant attendraient sinon
    # le prochain créneau : la passe est bornée (15 documents), donc un
    # redéploiement ne coûte que quelques minutes d'appels.
    run_marches_publics()
    verifier_sources_muettes()
    scheduler.start()


if __name__ == "__main__":
    main()
