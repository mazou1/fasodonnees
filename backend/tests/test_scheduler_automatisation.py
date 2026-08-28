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
    "annuaire_quotidien": "reconstruction des mandats depuis les nominations validées",
    "ocr_nocturne": "OCR des scans",
    "alerte_sources_muettes": "alerte quand une source se tait",
    "diffusion_horaire": "publication sur les réseaux sociaux",
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


def test_la_consolidation_des_versions_suit_la_structuration():
    """Le gouvernement réécrit ses pages : chaque réécriture crée une version,
    et la structuration repasse dessus. Sans consolidation dans la foulée, le
    conseil du 23 juillet 2026 s'est retrouvé avec ses décisions extraites deux
    fois - comptées deux fois dans la file de validation et les statistiques."""
    import inspect

    source = inspect.getsource(scheduler.run_conseil_ministres)
    assert "consolider_entites" in source, (
        "La structuration des CR doit être suivie d'une consolidation des "
        "versions, sinon les doublons s'accumulent à chaque réécriture."
    )


def test_le_rattrapage_de_demarrage_ne_bloque_pas_les_cadences():
    """`main()` doit planifier AVANT de collecter, jamais l'inverse.

    Tant que le rattrapage tournait en amont de `scheduler.start()`, un worker
    qui redémarrait plus souvent que la durée de ce rattrapage n'atteignait
    jamais ses cadences : le 28 août 2026, un PDF de 626 pages a fait tuer le
    process 97 fois d'affilée et la diffusion horaire n'a plus tourné pendant
    huit heures, sans autre trace que l'absence de ligne dans le journal.
    """
    import inspect

    source = inspect.getsource(scheduler.main)
    assert "run_demarrage" in source, "le rattrapage doit passer par le planificateur"
    for etape in ("run_medias()", "run_conseil_ministres()", "run_institutionnel()"):
        assert etape not in source, (
            f"« {etape} » est appelé directement dans main() : une collecte lente "
            "ou fatale reprendrait le worker en otage avant qu'il ne planifie quoi "
            "que ce soit."
        )


def test_une_etape_de_rattrapage_qui_echoue_laisse_passer_les_suivantes(monkeypatch):
    """Une source cassée ne doit pas priver les autres de leur collecte."""
    passees = []

    def rate():
        raise RuntimeError("source injoignable")

    monkeypatch.setattr(scheduler, "run_medias", rate)
    for nom in ("run_conseil_ministres", "run_institutionnel", "run_marches_publics",
                "run_annuaire", "verifier_sources_muettes"):
        monkeypatch.setattr(scheduler, nom, lambda nom=nom: passees.append(nom))

    scheduler.run_demarrage()  # ne doit pas lever

    assert passees == [
        "run_conseil_ministres", "run_institutionnel", "run_marches_publics",
        "run_annuaire", "verifier_sources_muettes",
    ]
