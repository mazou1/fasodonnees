"""MINEFID (finances.gov.bf) - veille des documents budgétaires citoyens.

Le Budget citoyen (Tableau 2 : allocations par secteur/ministère) n'est publié
qu'une fois par an, à une URL prévisible (budget-citoyen-<année>_web.pdf en
2025) mais sans flux. On sonde donc les URL candidates et les liens de la page
d'accueil ; dès parution, le PDF est archivé comme Document « rapport » - la
saisie des dotations dans l'admin (ou une passe d'extraction) suit.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

import httpx

from app.ingestion.base import Collector

logger = logging.getLogger(__name__)

BASE = "https://www.finances.gov.bf"


class BudgetCitoyenCollector(Collector):
    slug = "finances"
    groupe = "institutionnel"

    def _candidates(self) -> list[str]:
        annee = datetime.now(timezone.utc).year
        urls: list[str] = []
        # les budgets citoyens des exercices à venir (paraissent en fin d'année N-1)
        for ex in (annee, annee + 1):
            if ex < 2026:  # 2025 déjà exploité manuellement
                continue
            for motif in (
                f"/fileadmin/user_upload/storage/fichiers/budget-citoyen-{ex}_web.pdf",
                f"/fileadmin/user_upload/storage/fichiers/budget-citoyen-{ex}.pdf",
                f"/fileadmin/user_upload/storage/fichiers/budget_citoyen_{ex}.pdf",
            ):
                urls.append(BASE + motif)
        return urls

    def _liens_accueil(self) -> list[str]:
        try:
            resp = self.get(BASE)
        except httpx.HTTPError:
            return []
        liens = re.findall(r'href="([^"]*budget[-_]?citoyen[^"]*\.pdf)"', resp.text, re.I)
        return [l if l.startswith("http") else BASE + l for l in liens]

    def collect(self) -> None:
        vus: set[str] = set()
        for url in self._candidates() + self._liens_accueil():
            if url in vus:
                continue
            vus.add(url)
            m = re.search(r"(20\d{2})", url)
            exercice = m.group(1) if m else "?"
            if exercice != "?" and int(exercice) < 2026:
                continue
            try:
                resp = self.get(url, retries=1)  # un 404 = pas encore paru, inutile d'insister
            except httpx.HTTPError:
                self.nb_vus += 1
                continue
            if not resp.content.startswith(b"%PDF"):
                continue
            fichier, digest = self.archive(resp.content, "pdf")
            doc = self.upsert_document(
                url=url,
                type_doc="rapport",
                titre=f"Budget citoyen {exercice} (MINEFID)",
                date_publication=date.today(),
                hash_contenu=digest,
                fichier=fichier,
                mime="application/pdf",
                statut_extraction="en_attente",
            )
            if doc is not None:
                logger.warning(
                    "BUDGET CITOYEN %s PARU - archivé (%s). Saisir les dotations "
                    "(Tableau 2) dans l'admin : /finances les affichera.",
                    exercice,
                    fichier,
                )
        self.db.commit()
