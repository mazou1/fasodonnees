"""Collecteur de base : politesse HTTP, archivage des bruts, upsert des documents.

Principes (cadrage §5) :
- max ~1 requête/seconde par collecteur, User-Agent identifiant le projet ;
- tout document collecté est archivé tel quel AVANT extraction (le corpus
  archivé est l'actif du projet — les sites officiels dépublient) ;
- chaque exécution est journalisée dans `run` (alerte « source muette »).
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document, Run, Source
from app.stockage import stockage

logger = logging.getLogger(__name__)


class Collector:
    slug: str  # doit correspondre à Source.slug
    groupe: str = "autre"  # media | institutionnel — utilisé par le scheduler

    def __init__(self, db: Session):
        self.db = db
        self.source = db.scalars(select(Source).where(Source.slug == self.slug)).one()
        self.client = httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=30,
            follow_redirects=True,
        )
        self._last_request = 0.0
        self.nb_nouveaux = 0
        self.nb_vus = 0

    # ---- HTTP ----

    def get(self, url: str, min_interval: float = 1.0, retries: int = 3) -> httpx.Response:
        for attempt in range(retries):
            wait = self._last_request + min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            try:
                resp = self.client.get(url)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError("5xx", request=resp.request, response=resp)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                # 4xx = la ressource est en faute, pas le réseau : réessayer
                # n'y changera rien. Les sites officiels publient des liens
                # morts vers leurs propres documents (404 constatés sur des
                # décisions du Conseil constitutionnel) — insister trois fois
                # avec backoff ne fait que les marteler pour rien. Seul 429
                # (trop de requêtes) mérite d'attendre et de recommencer.
                if 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                    raise
                if attempt == retries - 1:
                    raise
                time.sleep(2**attempt * 2)  # backoff 2s, 4s
            except httpx.TransportError:
                if attempt == retries - 1:
                    raise
                time.sleep(2**attempt * 2)
        raise RuntimeError("unreachable")

    # ---- Archivage ----

    def archive(self, content: bytes, ext: str) -> tuple[str, str]:
        """Archive le brut sous <slug>/<annee>/<hash>.<ext> ; renvoie (clé, sha256).

        La clé est indépendante du support : disque local ou bucket S3 selon
        `FASO_STOCKAGE` (cf. app/stockage.py). `Document.fichier` la stocke
        telle quelle, ce qui rend le basculement transparent pour la base.
        """
        digest = hashlib.sha256(content).hexdigest()
        year = datetime.now(timezone.utc).strftime("%Y")
        cle = f"{self.slug}/{year}/{digest[:16]}.{ext}"
        stockage.ecrire(cle, content)
        return cle, digest

    # ---- Persistance ----

    def upsert_document(
        self,
        *,
        url: str,
        type_doc: str,
        titre: str | None = None,
        date_publication: date | None = None,
        hash_contenu: str | None = None,
        fichier: str | None = None,
        mime: str | None = None,
        texte_extrait: str | None = None,
        statut_extraction: str = "en_attente",
        meta: dict | None = None,
    ) -> Document | None:
        """Insère le document s'il est nouveau (même source + url + hash) ; renvoie None sinon.

        Un même url avec un hash différent crée une nouvelle ligne : on versionne,
        on n'écrase jamais (détection des republications silencieuses).
        """
        existing = self.db.scalars(
            select(Document.id).where(
                Document.source_id == self.source.id,
                Document.url == url,
                Document.hash_contenu == hash_contenu,
            )
        ).first()
        if existing is not None:
            self.nb_vus += 1
            return None
        doc = Document(
            source_id=self.source.id,
            url=url,
            titre=titre,
            type_doc=type_doc,
            date_publication=date_publication,
            hash_contenu=hash_contenu,
            fichier=fichier,
            mime=mime,
            texte_extrait=texte_extrait,
            statut_extraction=statut_extraction,
            meta=meta,
        )
        self.db.add(doc)
        self.nb_nouveaux += 1
        return doc

    # ---- Cycle de vie ----

    def collect(self) -> None:
        """À implémenter par chaque collecteur."""
        raise NotImplementedError

    def run(self) -> Run:
        """Exécute collect() en journalisant dans la table run."""
        run = Run(source_id=self.source.id)
        self.db.add(run)
        self.db.commit()
        try:
            self.collect()
            run.statut = "ok"
        except Exception as exc:  # noqa: BLE001 — on journalise tout échec de collecte
            logger.exception("Échec du collecteur %s", self.slug)
            run.statut = "echec"
            run.erreurs = f"{type(exc).__name__}: {exc}"
        finally:
            run.fin = datetime.now(timezone.utc)
            run.nb_nouveaux = self.nb_nouveaux
            run.nb_vus = self.nb_vus
            self.db.commit()
            self.client.close()
        logger.info(
            "%s : %s — %d nouveaux, %d déjà vus",
            self.slug,
            run.statut,
            run.nb_nouveaux,
            run.nb_vus,
        )
        return run
