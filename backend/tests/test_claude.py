"""Appels à Claude : ce que chaque appel envoie, et ce qu'il refuse de rendre.

Le budget est de 100 $ par mois. Ces tests figent les deux leviers qui le
tiennent - le modèle configuré et l'effort minimal - et le journal de tokens
qui permet de rapprocher le worker de la facture.
"""

import logging
import sys
import types
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from app.config import settings
from app.extraction import claude


class Verdict(BaseModel):
    meme_projet: bool


@dataclass
class _Usage:
    input_tokens: int = 1200
    output_tokens: int = 40


@dataclass
class _Reponse:
    parsed_output: object
    stop_reason: str = "end_turn"
    usage: _Usage = None  # type: ignore[assignment]


@pytest.fixture
def api(monkeypatch):
    """Un faux module `anthropic` qui note la requête et rend ce qu'on lui dit."""
    appels = []
    etat = {"reponse": _Reponse(Verdict(meme_projet=True), usage=_Usage())}

    class _Messages:
        def parse(self, **kw):
            appels.append(kw)
            return etat["reponse"]

    class _Client:
        def __init__(self, api_key=None):
            self.messages = _Messages()

    faux = types.ModuleType("anthropic")
    faux.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", faux)
    monkeypatch.setattr(settings, "anthropic_model", "claude-haiku-5-5")
    monkeypatch.setattr(settings, "anthropic_effort", "low")
    return appels, etat


def test_le_modele_et_leffort_viennent_de_la_configuration(api):
    appels, _ = api

    claude.extraire("texte", schema=Verdict, systeme="consigne", max_tokens=2000)

    (requete,) = appels
    assert requete["model"] == "claude-haiku-5-5"
    assert requete["output_config"] == {"effort": "low"}
    assert requete["output_format"] is Verdict
    assert requete["messages"] == [{"role": "user", "content": "texte"}]
    assert "temperature" not in requete, "refusée par les modèles actuels"


def test_un_effort_vide_nenvoie_pas_le_parametre(api, monkeypatch):
    """Haiku 4.5 refuse `effort` : la configuration doit pouvoir l'omettre."""
    appels, _ = api
    monkeypatch.setattr(settings, "anthropic_effort", "")

    claude.extraire("texte", schema=Verdict, systeme="consigne", max_tokens=2000)

    assert "output_config" not in appels[0]


def test_les_tokens_sont_journalises(api, caplog):
    with caplog.at_level(logging.INFO, logger="app.extraction.claude"):
        claude.extraire("texte", schema=Verdict, systeme="consigne", max_tokens=2000)

    assert "1200 tokens en entrée, 40 en sortie" in caplog.text
    assert "Verdict" in caplog.text, "la passe concernée doit être lisible dans le journal"


def test_une_sortie_tronquee_est_une_erreur(api):
    _, etat = api
    etat["reponse"] = _Reponse(None, stop_reason="max_tokens", usage=_Usage())

    with pytest.raises(RuntimeError, match="max_tokens"):
        claude.extraire("texte", schema=Verdict, systeme="consigne", max_tokens=2000)


def test_une_reponse_hors_schema_est_une_erreur(api):
    """`parsed_output` vide (refus, format inattendu) : ne jamais rendre None à
    un appelant qui attend un schéma."""
    _, etat = api
    etat["reponse"] = _Reponse(None, stop_reason="refusal", usage=_Usage())

    with pytest.raises(RuntimeError, match="refusal"):
        claude.extraire("texte", schema=Verdict, systeme="consigne", max_tokens=2000)
