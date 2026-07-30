"""Actualités du gouvernement - gouvernement.gov.bf, catégorie 13.

WordPress à API REST ouverte (comme les CR). La catégorie 13 « Actualités »
(1 600+ billets depuis oct. 2022, vérifiée le 2026-07-23) contient les
inaugurations, poses de première pierre et lancements de chantiers - la source
OFFICIELLE qui alimente la page « Infrastructures & inaugurations ».

Chaîne : collecte → texte → extraction LLM des réalisations
(app.extraction.realisations) → validation humaine → carte/stats.
"""

from __future__ import annotations

from app.ingestion.wordpress import WordPressCollector


class ActualitesGouvCollector(WordPressCollector):
    slug = "actualites_gouv"
    groupe = "institutionnel"  # collecte quotidienne (le backfill se lance à la main)
    api_base = "https://gouvernement.gov.bf/wp-json/wp/v2"
    categories = "13"  # « Actualités »
    type_doc = "actualite_gouv"
