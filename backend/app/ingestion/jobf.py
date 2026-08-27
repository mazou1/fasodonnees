"""Journal officiel du Burkina Faso (jobf.gov.bf) - numéros hebdomadaires.

Le JO paraît chaque jeudi et fait foi : c'est là qu'un décret devient
opposable. Légiburkina l'indexe ensuite texte par texte, avec un décalage qui
peut se transformer en arrêt - au 2026-08-27, elle s'était arrêtée au n°30 du
23 juillet quand le JO en était au n°34 du 20 août, soit quatre numéros et un
mois de droit manquants. Collecter le JO directement affranchit la plateforme
de ce décalage ; les deux sources restent complémentaires, le JO pour la
fraîcheur et le numéro intégral, Légiburkina pour l'index structuré
(référence, type, secteur).

API publique découverte le 2026-08-27 en capturant le trafic du site (une SPA
React), sans authentification :

- POST /api/frontoffice/newspapers/page/{n}  corps {} → 10 numéros par page,
  du plus récent au plus ancien : id, uuid, numero, type, date_pub, sommaire ;
- POST /api/newspapers/jo-file-url  corps {"joUuid": …} → chemin du PDF, servi
  sous /storage/.

Ne pas confondre avec `/api/clients/newspapers` ni `/api/newspapers/page/{n}`,
qui exigent un compte. Le site vend des abonnements et des insertions
d'annonces, pas l'accès au Journal officiel lui-même : les PDF sont servis
librement, ce que le statut de document public commande.
"""

from __future__ import annotations

import logging
import time
from datetime import date

from app.extraction.pdf import extraire_texte
from app.extraction.texte import html_vers_texte
from app.ingestion.base import Collector
from app.stockage import stockage

logger = logging.getLogger(__name__)


class JobfCollector(Collector):
    slug = "jobf"
    groupe = "institutionnel"
    api = "https://jobf.gov.bf/api"
    stockage_public = "https://jobf.gov.bf/storage"

    # Un numéro pèse ~7 Mo et il en existe près de 900 : tout rapatrier d'un
    # coup, ce sont 6 Go sur un disque partagé avec une autre application. La
    # collecte est donc bornée par passage et l'arriéré se résorbe sur
    # plusieurs jours - le même parti que l'OCR et les PDF de Légiburkina.
    max_nouveaux = 15

    def collect(self) -> None:
        nouveaux = 0
        page = 1
        while nouveaux < self.max_nouveaux:
            numeros, total_source = self._page(page)
            if not numeros:
                break
            vus_avant = self.nb_vus
            for numero in numeros:
                if nouveaux >= self.max_nouveaux:
                    break
                if self._traiter(numero):
                    nouveaux += 1
            self.db.commit()
            # Les numéros arrivent du plus récent au plus ancien : une page
            # entièrement connue signifie d'ordinaire que la suite l'est aussi,
            # et s'arrêter là évite de relire 90 pages d'archives chaque jour.
            #
            # Sauf pendant le rattrapage : la collecte étant bornée par
            # passage, les premières pages sont connues bien avant les
            # dernières. S'arrêter à la première page connue condamnerait
            # l'arriéré à ne jamais être rapatrié. Le total annoncé par la
            # source dit lequel des deux cas on est.
            if self.nb_vus - vus_avant == len(numeros) and not self._rattrapage(total_source):
                break
            page += 1
        if nouveaux >= self.max_nouveaux:
            logger.info(
                "%s : plafond de %d numéros atteint - le reste suivra au prochain passage",
                self.slug, self.max_nouveaux,
            )

    def _rattrapage(self, total_source: int | None) -> bool:
        """Reste-t-il des numéros anciens à rapatrier ?"""
        if not total_source:
            return False
        return self.nb_archives() < total_source

    def nb_archives(self) -> int:
        from sqlalchemy import func, select

        from app.models import Document

        return self.db.scalar(
            select(func.count()).select_from(Document).where(
                Document.source_id == self.source.id
            )
        ) or 0

    def _page(self, page: int) -> tuple[list[dict], int | None]:
        reponse = self.client.post(
            f"{self.api}/frontoffice/newspapers/page/{page}", json={}, timeout=60
        )
        reponse.raise_for_status()
        corps = reponse.json()
        if not corps.get("success"):
            raise ValueError(f"JOBF : réponse inattendue ({corps.get('message')})")
        donnees = corps.get("data") or {}
        return (donnees.get("data") or []), donnees.get("total")

    def url_pdf(self, uuid: str) -> str | None:
        """Adresse du PDF d'un numéro, résolue par l'API.

        Le chemin est un identifiant de stockage, pas une adresse devinable :
        il faut le demander numéro par numéro.
        """
        try:
            reponse = self.client.post(
                f"{self.api}/newspapers/jo-file-url", json={"joUuid": uuid}, timeout=30
            )
            reponse.raise_for_status()
            chemin = ((reponse.json().get("data")) or {}).get("pathJo")
        except Exception as exc:  # réseau, JSON, champ absent
            logger.warning("%s : chemin du PDF introuvable pour %s (%s)", self.slug, uuid, exc)
            return None
        return f"{self.stockage_public}/{chemin}" if chemin else None

    def _traiter(self, numero: dict) -> bool:
        """Archive un numéro. Renvoie True s'il était nouveau."""
        uuid = numero.get("uuid")
        if not uuid:
            return False
        pdf_url = self.url_pdf(uuid)
        if not pdf_url:
            return False

        # Une date illisible ne doit pas emporter la collecte entière : le
        # numéro reste archivé, sa date manquera - c'est réparable, un numéro
        # perdu ne l'est pas une fois le site dépublié.
        pub: date | None = None
        if numero.get("date_pub"):
            try:
                pub = date.fromisoformat(str(numero["date_pub"])[:10])
            except ValueError:
                logger.warning(
                    "%s : date illisible « %s » sur le numéro %s",
                    self.slug, numero["date_pub"], numero.get("numero"),
                )
        libelle = f"n°{numero.get('numero')}" if numero.get("numero") else uuid[:8]
        edition = "spécial" if (numero.get("type") or "").lower().startswith("spec") else None
        titre = f"Journal officiel {libelle}" + (f" ({edition})" if edition else "")
        if pub:
            titre += f" du {pub:%d/%m/%Y}"

        # L'identité tient à l'URL du PDF. Le permalien du site, lui, serait
        # /newspapers/{numero} - ambigu d'une année sur l'autre, la numérotation
        # repartant à 1 chaque janvier.
        #
        # Le stockage attribue un nom de fichier aléatoire à chaque dépôt : une
        # même adresse désigne donc toujours le même fichier, et un numéro
        # redéposé apparaîtra comme une pièce distincte plutôt que comme une
        # version. C'est acceptable ici - un Journal officiel ne se réécrit pas,
        # il s'errate dans un numéro suivant.
        if self.deja_connu(pdf_url):
            self.nb_vus += 1
            return False

        try:
            reponse = self.get(pdf_url, min_interval=1.0)
        except Exception as exc:
            logger.warning("%s : téléchargement échoué %s (%s)", self.slug, pdf_url, exc)
            return False
        if not reponse.content.startswith(b"%PDF"):
            logger.warning("%s : ce n'est pas un PDF %s", self.slug, pdf_url)
            return False

        fichier, digest = self.archive(reponse.content, "pdf")
        with stockage.fichier_local(fichier) as chemin:
            # ocr=False : les JO sont des PDF natifs. Un numéro scanné serait
            # marqué « scan » et repris par la passe d'OCR nocturne.
            texte, statut = extraire_texte(chemin, ocr=False)

        doc = self.upsert_document(
            url=pdf_url,
            type_doc="journal_officiel",
            titre=titre[:1000],
            date_publication=pub,
            hash_contenu=digest,
            fichier=fichier,
            mime="application/pdf",
            texte_extrait=texte or None,
            statut_extraction=statut,
            meta={
                "jo_uuid": uuid,
                "jo_id": numero.get("id"),
                "jo_numero": str(numero.get("numero") or "") or None,
                "jo_type": numero.get("type"),
                # Le sommaire énumère tous les actes du numéro : c'est le
                # meilleur résumé possible, et il vient de la source.
                "sommaire": html_vers_texte(numero.get("sommaire") or "") or None,
                "permalien": f"https://jobf.gov.bf/newspapers/{numero.get('numero')}",
            },
        )
        if doc is not None:
            logger.info("%s : %s archivé (%s)", self.slug, titre, statut)
        time.sleep(0.5)  # politesse : le JO sert des fichiers de plusieurs mégaoctets
        return doc is not None

    def deja_connu(self, url: str) -> bool:
        """Ce numéro est-il déjà archivé, sous cette même adresse ?

        Évite de retélécharger 7 Mo pour découvrir ensuite que le document
        existe : `upsert_document` ne se prononce qu'une fois l'empreinte du
        contenu calculée, donc après téléchargement.
        """
        from sqlalchemy import select

        from app.models import Document

        return (
            self.db.scalars(
                select(Document.id).where(
                    Document.source_id == self.source.id, Document.url == url
                ).limit(1)
            ).first()
            is not None
        )
