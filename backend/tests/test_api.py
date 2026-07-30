from fastapi.testclient import TestClient

from app.main import app


def test_health_repond():
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "db" in body
    assert body["status"] in ("ok", "degraded")


def test_openapi_expose_les_routes():
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert "/documents" in paths
    assert "/sources" in paths
    assert "/attributaires" in paths
    assert "/attributaires/{attributaire_id}" in paths


def test_attributaire_inconnu_repond_404():
    with TestClient(app) as client:
        resp = client.get("/attributaires/999999999")
    assert resp.status_code == 404


def test_marche_expose_le_lien_vers_lentite_consolidee():
    """La graphie du document ET l'entité consolidée sont servies : le site
    affiche la première, mais peut lier vers la fiche entreprise."""
    with TestClient(app) as client:
        champs = client.get("/openapi.json").json()["components"]["schemas"]["MarcheOut"][
            "properties"
        ]
    assert "attributaire" in champs
    assert "attributaire_id" in champs
