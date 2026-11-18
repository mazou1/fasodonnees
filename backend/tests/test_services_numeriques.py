"""État en direct des téléservices : ce que la page « Services en ligne » affirme.

Dire « en ligne » d'un portail qui sert sa page de maintenance, ou « en panne »
d'un site qui a seulement tardé une fois, ruinerait l'intérêt de l'affichage.
"""

import ssl

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.services_numeriques as module
from app.models import Base, EtatService
from app.services_numeriques import (
    CERTIFICAT,
    EN_LIGNE,
    EN_PANNE,
    INCONNU,
    INJOIGNABLE,
    MAINTENANCE_,
    annuaire,
    enregistrer,
    toutes_les_urls,
    verifier,
    verifier_avec_reprise,
)


def client(repondre):
    return httpx.Client(transport=httpx.MockTransport(repondre), follow_redirects=True)


def test_un_site_qui_repond_est_en_ligne():
    c = client(lambda r: httpx.Response(200, text="<title>e-Timbre</title>"))
    assert verifier(c, "https://a.bf") == (EN_LIGNE, 200, None)


def test_une_page_de_maintenance_servie_en_200_n_est_pas_en_ligne():
    c = client(lambda r: httpx.Response(200, text="<h1>Site en maintenance</h1>"))
    assert verifier(c, "https://a.bf")[0] == MAINTENANCE_


def test_une_erreur_serveur_est_une_panne():
    c = client(lambda r: httpx.Response(502, text="Bad Gateway"))
    assert verifier(c, "https://a.bf")[:2] == (EN_PANNE, 502)


def test_un_refus_d_acces_n_est_affirme_ni_en_ligne_ni_en_panne():
    c = client(lambda r: httpx.Response(403))
    assert verifier(c, "https://a.bf")[0] == INCONNU


def test_un_certificat_invalide_est_distingue_d_une_panne_reseau():
    def certificat(request):
        raise httpx.ConnectError("x") from ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")

    def reseau(request):
        raise httpx.ConnectTimeout("délai dépassé")

    assert verifier(client(certificat), "https://a.bf")[0] == CERTIFICAT
    assert verifier(client(reseau), "https://a.bf")[0] == INJOIGNABLE


def test_un_delai_isole_ne_suffit_pas_a_declarer_la_panne(monkeypatch):
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    appels = []

    def repondre(request):
        appels.append(1)
        if len(appels) == 1:
            raise httpx.ConnectTimeout("délai dépassé")
        return httpx.Response(200, text="ok")

    assert verifier_avec_reprise(client(repondre), "https://a.bf")[0] == EN_LIGNE
    assert len(appels) == 2


def test_depuis_ne_bouge_que_quand_l_etat_change():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[EtatService.__table__])
    with Session(engine) as db:
        enregistrer(db, "https://a.bf", EN_LIGNE, 200, None)
        db.commit()
        debut = db.scalars(select(EtatService)).one().depuis

        enregistrer(db, "https://a.bf", EN_LIGNE, 200, None)
        db.commit()
        assert db.scalars(select(EtatService)).one().depuis == debut

        enregistrer(db, "https://a.bf", EN_PANNE, 502, "erreur HTTP 502")
        db.commit()
        etat = db.scalars(select(EtatService)).one()
        assert etat.statut == EN_PANNE and etat.depuis >= debut
        assert etat.dernier_ok is not None, "la dernière réussite reste connue"


def test_l_annuaire_est_coherent():
    urls = toutes_les_urls()
    assert len(urls) == len(set(urls)) > 100
    assert all(u.startswith("https://") for u in urls)
    for section in annuaire()["sections"]:
        for service in section["services"]:
            assert service["nom"] and service["desc"], service


def test_langue_et_pdf_d_une_traduction():
    from app.ingestion.conseil_ministres import langue_nationale, lien_pdf

    assert langue_nationale("(moore) CONSEIL DES MINISTRES N°29") == "moore"
    assert langue_nationale("CONSEIL DES MINISTRES N°31 – JULA") == "dioula"
    assert langue_nationale("GULIMANCEMA CONSEIL DES MINISTRES") == "gulmancema"
    assert langue_nationale("CONSEIL DES MINISTRES N°31") is None
    html = '<div class="wp-block-file"><a href="https://g/x/FULFULDE-CM.pdf">Télécharger</a></div>'
    assert lien_pdf(html) == "https://g/x/FULFULDE-CM.pdf"
    assert lien_pdf("<p>rien</p>") is None
