"""Comptes rendus du Conseil des ministres - gouvernement.gov.bf.

Le site est un WordPress avec API REST ouverte ; la catégorie 23
(« Compte rendu », vérifiée le 2026-07-10) contient les CR officiels.
Chaîne complète : collecte → texte → extraction LLM des nominations
(app.extraction.nominations) → validation humaine → annuaire (app.annuaire).
"""

from __future__ import annotations

import re

from app.ingestion.wordpress import WordPressCollector

# traductions en langues nationales publiées à côté de la version française -
# archivées mais typées à part (l'extraction LLM sur ces textes divague)
LANGUES_NATIONALES = re.compile(
    r"GULI?MANCEMA|MOOR[EÉ]|FULFULD[EÉ]|DIOULA|JULA", re.IGNORECASE
)


class ConseilMinistresCollector(WordPressCollector):
    slug = "conseil_ministres"
    groupe = "cm"  # cadence hebdomadaire propre (mercredi), distincte du quotidien institutionnel
    api_base = "https://gouvernement.gov.bf/wp-json/wp/v2"
    categories = "23"  # « Compte rendu » (parent « Conseil des ministres »)
    type_doc = "cr_conseil"

    def type_doc_pour(self, titre: str) -> str:
        if LANGUES_NATIONALES.search(titre or ""):
            return "cr_conseil_traduction"
        return self.type_doc
