"""État en direct des téléservices de l'État listés sur la page « Services en ligne ».

L'annuaire (app/data/services_numeriques.json) recense les sites officiels.
Jusqu'en novembre 2026, leur accessibilité était vérifiée à la main, une fois,
et la page datait cette vérification ; un portail tombé le lendemain restait
affiché comme sûr. Le worker teste désormais chaque adresse tous les jours et
la page affiche le résultat.

Un site est jugé comme le verrait un visiteur : réponse HTTP, certificat
valide, et pas de page « Site en maintenance » servie en 200 - le cas d'une
bonne partie des ministères le 18 novembre 2026, invisible au seul code HTTP.

Usage manuel : python -m app.services_numeriques
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import EtatService

logger = logging.getLogger(__name__)

FICHIER = Path(__file__).parent / "data" / "services_numeriques.json"

# Un navigateur ordinaire : plusieurs sites de l'administration refusent les
# clients qui s'annoncent comme des robots, et c'est l'expérience d'un visiteur
# qu'on mesure.
AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
DELAI = 30.0
OCTETS_LUS = 300_000
MAINTENANCE = re.compile(
    r"site (temporairement )?en maintenance|under maintenance|maintenance en cours",
    re.IGNORECASE,
)

EN_LIGNE = "en_ligne"
MAINTENANCE_ = "maintenance"
EN_PANNE = "en_panne"
CERTIFICAT = "certificat"
INJOIGNABLE = "injoignable"
INCONNU = "inconnu"


@lru_cache(maxsize=1)
def annuaire() -> dict:
    return json.loads(FICHIER.read_text(encoding="utf-8"))


def toutes_les_urls() -> list[str]:
    donnees = annuaire()
    urls = [donnees["phare"]["url"]]
    urls += [s["url"] for section in donnees["sections"] for s in section["services"]]
    return list(dict.fromkeys(urls))


def _erreur_de_certificat(exc: BaseException) -> bool:
    while exc is not None:
        if isinstance(exc, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def verifier(client: httpx.Client, url: str) -> tuple[str, int | None, str | None]:
    """(statut, code HTTP, détail) pour une adresse, vue comme par un visiteur."""
    try:
        with client.stream("GET", url) as reponse:
            code = reponse.status_code
            debut = b""
            for morceau in reponse.iter_bytes():
                debut += morceau
                if len(debut) >= OCTETS_LUS:
                    break
    except httpx.HTTPError as exc:
        if _erreur_de_certificat(exc):
            return CERTIFICAT, None, "certificat de sécurité invalide"
        return INJOIGNABLE, None, type(exc).__name__
    if code in (401, 403, 429):
        # le site répond mais refuse notre requête : ni en ligne ni en panne
        # avec certitude, on ne l'affirme pas
        return INCONNU, code, "accès refusé à la vérification automatique"
    if code >= 400:
        return EN_PANNE, code, f"erreur HTTP {code}"
    if MAINTENANCE.search(debut.decode(errors="replace")):
        return MAINTENANCE_, code, "page de maintenance"
    return EN_LIGNE, code, None


def verifier_avec_reprise(client: httpx.Client, url: str) -> tuple[str, int | None, str | None]:
    """Une seconde chance avant de déclarer un site en défaut.

    Ces serveurs décrochent volontiers quelques secondes ; afficher « en panne »
    pendant vingt-quatre heures pour un seul délai dépassé serait injuste.
    """
    resultat = verifier(client, url)
    if resultat[0] in (EN_LIGNE, MAINTENANCE_):
        return resultat
    time.sleep(5)
    return verifier(client, url)


def enregistrer(db: Session, url: str, statut: str, code: int | None, detail: str | None) -> None:
    maintenant = datetime.now(timezone.utc)
    etat = db.get(EtatService, url)
    if etat is None:
        etat = EtatService(url=url, statut=statut, depuis=maintenant)
        db.add(etat)
    elif etat.statut != statut:
        # `depuis` date le début de l'état courant : c'est ce qui permet
        # d'écrire « en panne depuis le 18 novembre »
        etat.statut = statut
        etat.depuis = maintenant
    etat.code_http = code
    etat.detail = detail
    etat.verifie_le = maintenant
    if statut == EN_LIGNE:
        etat.dernier_ok = maintenant


def verifier_tout(db: Session, urls: list[str] | None = None) -> dict[str, int]:
    urls = urls if urls is not None else toutes_les_urls()
    with httpx.Client(
        headers={"User-Agent": AGENT, "Accept-Language": "fr"},
        timeout=DELAI,
        follow_redirects=True,
    ) as client, ThreadPoolExecutor(max_workers=8) as pool:
        resultats = list(pool.map(lambda u: verifier_avec_reprise(client, u), urls))
    bilan: dict[str, int] = {}
    for url, (statut, code, detail) in zip(urls, resultats, strict=True):
        enregistrer(db, url, statut, code, detail)
        bilan[statut] = bilan.get(statut, 0) + 1
    # un service retiré de l'annuaire n'a plus d'état à porter
    db.execute(delete(EtatService).where(EtatService.url.notin_(urls)))
    db.commit()
    return bilan


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    with SessionLocal() as db:
        bilan = verifier_tout(db)
    logger.info("Téléservices vérifiés : %s", bilan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
