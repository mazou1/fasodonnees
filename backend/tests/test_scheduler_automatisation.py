"""La chaîne complète tourne seule - l'administrateur ne fait que valider.

C'est l'engagement pris sur cette plateforme : se connecter une fois par jour à
`/admin`, cocher, repartir. Chaque étape qu'on oublierait de planifier le
transforme en opérateur d'un pipeline manuel. Ces tests cassent quand c'est le
cas, plutôt que de laisser la découverte se faire des semaines après, sur un
corpus qui a cessé de grossir.
"""

import pytest

from app.ingestion import scheduler


@pytest.fixture(scope="module")
def jobs():
    return {j.id: j for j in scheduler.construire_scheduler().get_jobs()}


ETAPES_ATTENDUES = {
    "medias": "flux RSS des médias",
    "institutionnel_quotidien": "sources .gov.bf",
    "cm_jeudi": "compte rendu du Conseil des ministres",
    "cm_rattrapage": "rattrapage du CR si publication tardive",
    "marches_quotidien": "extraction LLM des marchés + autorités + consolidation",
    "pdf_textes_quotidien": "PDF des textes juridiques et texte natif",
    "ocr_nocturne": "OCR des scans",
    "alerte_sources_muettes": "alerte quand une source se tait",
}


@pytest.mark.parametrize("identifiant", sorted(ETAPES_ATTENDUES))
def test_chaque_etape_est_planifiee(jobs, identifiant):
    assert identifiant in jobs, (
        f"L'étape « {ETAPES_ATTENDUES[identifiant]} » n'est plus planifiée : "
        "elle devrait être lancée à la main, ce que la plateforme promet d'éviter."
    )


def test_locr_est_bien_planifie_de_nuit():
    """Tesseract sature le CPU, partagé avec le reste de la machine : de jour,
    l'OCR ralentirait le site pour les visiteurs."""
    jobs = {j.id: j for j in scheduler.construire_scheduler().get_jobs()}
    champs = {c.name: str(c) for c in jobs["ocr_nocturne"].trigger.fields}
    assert int(champs["hour"]) < 6


def test_les_marches_passent_apres_la_collecte():
    """Extraire avant d'avoir collecté ne trouverait que les Quotidiens de la
    veille - le décalage se paierait d'un jour de retard permanent."""
    jobs = {j.id: j for j in scheduler.construire_scheduler().get_jobs()}

    def heure(identifiant):
        champs = {c.name: str(c) for c in jobs[identifiant].trigger.fields}
        return int(champs["hour"]) * 60 + int(champs["minute"])

    assert heure("marches_quotidien") > heure("institutionnel_quotidien")


def test_ocr_et_marches_sont_bornes():
    """Un arriéré doit se résorber sur plusieurs passages, jamais immobiliser le
    worker : les passes prennent un `max_docs`, elles ne défilent pas tout."""
    import inspect

    source = inspect.getsource(scheduler)
    assert "max_docs=40" in source  # OCR
    assert "max_marches=120" in source  # autorités
    assert ".limit(15)" in source  # Quotidiens par passage
