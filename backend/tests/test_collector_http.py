"""Politesse HTTP du collecteur de base.

Le cadrage impose ≥ 1 requête/seconde et un User-Agent identifiant le projet.
S'y ajoute une règle de bon sens : ne pas marteler un serveur officiel pour une
ressource qui n'existe pas.
"""

import httpx
import pytest

from app.ingestion.base import Collector


class _CollecteurNu(Collector):
    """Instancie la mécanique HTTP sans toucher à la base."""

    slug = "test"

    def __init__(self, reponses):
        self.client = httpx.Client(transport=httpx.MockTransport(self._repondre))
        self._last_request = 0.0
        self.nb_nouveaux = self.nb_vus = 0
        self._reponses = list(reponses)
        self.appels = 0

    def _repondre(self, request):
        self.appels += 1
        code = self._reponses[min(self.appels - 1, len(self._reponses) - 1)]
        return httpx.Response(code, request=request)

    def collect(self):  # pragma: no cover — non utilisé ici
        raise NotImplementedError


def test_un_404_nest_pas_reessaye():
    """Les sites officiels publient des liens morts vers leurs propres
    documents. Réessayer ne les ressuscite pas — une seule requête suffit."""
    c = _CollecteurNu([404])
    with pytest.raises(httpx.HTTPStatusError):
        c.get("https://exemple.bf/mort.pdf", min_interval=0)
    assert c.appels == 1


def test_un_500_est_reessaye():
    """Une panne serveur est transitoire : là, insister a du sens."""
    c = _CollecteurNu([500])
    with pytest.raises(httpx.HTTPStatusError):
        c.get("https://exemple.bf/x", min_interval=0, retries=3)
    assert c.appels == 3


def test_un_429_est_reessaye():
    """Trop de requêtes : c'est nous qui sommes en faute, on attend."""
    c = _CollecteurNu([429])
    with pytest.raises(httpx.HTTPStatusError):
        c.get("https://exemple.bf/x", min_interval=0, retries=2)
    assert c.appels == 2


def test_une_reponse_valide_est_rendue_sans_retry():
    c = _CollecteurNu([200])
    assert c.get("https://exemple.bf/ok", min_interval=0).status_code == 200
    assert c.appels == 1


def test_un_500_puis_200_finit_par_reussir():
    c = _CollecteurNu([500, 200])
    assert c.get("https://exemple.bf/x", min_interval=0).status_code == 200
    assert c.appels == 2
