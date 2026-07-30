"""Stockage du corpus archivé : disque local ou objet S3 (Garage).

Le corpus brut — PDF et HTML collectés avant tout traitement — est **l'actif du
projet** : les sites officiels dépublient, et ce qu'on n'a pas archivé est
perdu. D'où deux exigences qui gouvernent ce module :

1. **la durabilité vient de la sortie de machine**, pas du format de stockage.
   Un serveur objet installé sur le VPS applicatif partage son disque et son
   domaine de panne : il n'apporte rien. `deploy/garage/` déploie donc Garage
   sur un hôte SÉPARÉ ;
2. **rien ne lit `settings.data_dir` en dehors d'ici.** Un appelant qui
   fabrique un chemin à la main fonctionne en local et casse en production,
   silencieusement.

Trois usages seulement dans le code, d'où trois primitives :

- `ecrire(cle, contenu)`        — archivage à la collecte ;
- `fichier_local(cle)`          — extraction (pdfplumber, pypdf et Tesseract
                                  veulent un vrai fichier) ; en mode objet, le
                                  fichier est téléchargé puis supprimé ;
- `url_ou_chemin(cle)`          — service du document au public.

Configuration : `FASO_STOCKAGE=local|s3` et les `FASO_S3_*` (cf. config.py).
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterator

from app.config import settings

logger = logging.getLogger(__name__)


class CleInvalide(ValueError):
    """Clé sortant du périmètre de l'archive."""


def normaliser_cle(cle: str | Path) -> str:
    """Clé d'archive canonique : chemin POSIX relatif, sans remontée.

    `Document.fichier` alimente directement cette fonction ; une valeur
    corrompue en base ne doit pas permettre de lire `/etc/passwd` ni d'écrire
    hors du bucket.
    """
    brut = PurePosixPath(str(cle).replace("\\", "/"))
    if brut.is_absolute() or ".." in brut.parts:
        raise CleInvalide(f"clé hors périmètre : {cle!r}")
    morceaux = [p for p in brut.parts if p not in ("", ".")]
    if not morceaux:
        raise CleInvalide("clé vide")
    return "/".join(morceaux)


class StockageLocal:
    """Disque local — le mode de développement, et le défaut."""

    mode = "local"

    def __init__(self, racine: Path):
        self.racine = Path(racine)

    def _chemin(self, cle: str) -> Path:
        return self.racine / normaliser_cle(cle)

    def ecrire(self, cle: str, contenu: bytes) -> None:
        chemin = self._chemin(cle)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        if not chemin.exists():  # le nom porte le hash : même clé = même octets
            chemin.write_bytes(contenu)

    def lire(self, cle: str) -> bytes:
        return self._chemin(cle).read_bytes()

    def existe(self, cle: str) -> bool:
        return self._chemin(cle).is_file()

    def supprimer(self, cle: str) -> None:
        self._chemin(cle).unlink(missing_ok=True)

    def taille(self, cle: str) -> int | None:
        chemin = self._chemin(cle)
        return chemin.stat().st_size if chemin.is_file() else None

    @contextmanager
    def fichier_local(self, cle: str) -> Iterator[Path]:
        """Le fichier EST déjà local : aucune copie, aucune suppression."""
        yield self._chemin(cle)

    def url_ou_chemin(self, cle: str) -> tuple[str, Path | str]:
        return "chemin", self._chemin(cle)


class StockageS3:
    """Bucket S3-compatible (Garage). Import boto3 tardif : le mode local ne
    doit pas dépendre d'une bibliothèque qu'il n'utilise pas."""

    mode = "s3"

    def __init__(self, *, endpoint: str, bucket: str, cle_acces: str,
                 cle_secrete: str, region: str = "garage",
                 duree_url: int = 3600):
        self.bucket = bucket
        self.duree_url = duree_url
        import boto3
        from botocore.config import Config

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=cle_acces,
            aws_secret_access_key=cle_secrete,
            region_name=region,
            # Garage n'accepte pas les URL de type virtual-host par défaut
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ecrire(self, cle: str, contenu: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=normaliser_cle(cle), Body=contenu)

    def lire(self, cle: str) -> bytes:
        objet = self.client.get_object(Bucket=self.bucket, Key=normaliser_cle(cle))
        return objet["Body"].read()

    def existe(self, cle: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=normaliser_cle(cle))
            return True
        except ClientError:
            return False

    def supprimer(self, cle: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=normaliser_cle(cle))

    def taille(self, cle: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            tete = self.client.head_object(Bucket=self.bucket, Key=normaliser_cle(cle))
            return int(tete["ContentLength"])
        except ClientError:
            return None

    @contextmanager
    def fichier_local(self, cle: str) -> Iterator[Path]:
        """Télécharge dans un fichier temporaire, supprimé quoi qu'il arrive.

        Le `finally` n'est pas décoratif : une passe d'OCR sur des milliers de
        PDF laisserait sinon plusieurs gigaoctets dans /tmp le jour où une
        extraction lève.
        """
        cle = normaliser_cle(cle)
        suffixe = Path(cle).suffix or ".bin"
        descripteur, chemin_temp = tempfile.mkstemp(prefix="faso-", suffix=suffixe)
        os.close(descripteur)
        chemin = Path(chemin_temp)
        try:
            self.client.download_file(self.bucket, cle, str(chemin))
            yield chemin
        finally:
            chemin.unlink(missing_ok=True)

    def url_ou_chemin(self, cle: str) -> tuple[str, Path | str]:
        """URL présignée : le document part du bucket, pas de l'API.

        Faire transiter les PDF par FastAPI transformerait l'API en serveur de
        fichiers et saturerait le VPS applicatif.
        """
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": normaliser_cle(cle)},
            ExpiresIn=self.duree_url,
        )
        return "url", url


def _construire():
    if settings.stockage == "s3":
        manquantes = [
            nom
            for nom, valeur in (
                ("FASO_S3_ENDPOINT", settings.s3_endpoint),
                ("FASO_S3_BUCKET", settings.s3_bucket),
                ("FASO_S3_ACCESS_KEY", settings.s3_access_key),
                ("FASO_S3_SECRET_KEY", settings.s3_secret_key),
            )
            if not valeur
        ]
        if manquantes:
            # échouer au démarrage plutôt qu'archiver dans le vide
            raise RuntimeError(
                "FASO_STOCKAGE=s3 mais variable(s) manquante(s) : " + ", ".join(manquantes)
            )
        return StockageS3(
            endpoint=settings.s3_endpoint,
            bucket=settings.s3_bucket,
            cle_acces=settings.s3_access_key,
            cle_secrete=settings.s3_secret_key,
            region=settings.s3_region,
            duree_url=settings.s3_duree_url,
        )
    return StockageLocal(settings.data_dir)


stockage = _construire()


# --- migration ------------------------------------------------------------

def migrer_depuis_local(racine: Path, *, supprimer_apres: bool, cible=None) -> dict[str, int]:
    """Pousse l'archive locale vers le stockage objet.

    Reprenable : un fichier déjà présent à la bonne taille est sauté. La
    suppression locale n'intervient qu'après vérification de la taille côté
    bucket — perdre l'original d'un document parce qu'un envoi a échoué à
    moitié serait irréparable.
    """
    cible = cible or stockage
    if getattr(cible, "mode", None) != "s3":
        raise RuntimeError("migration inutile : la cible est déjà le disque local")

    racine = Path(racine)
    stats = {"envoyes": 0, "deja_presents": 0, "supprimes": 0, "echecs": 0}
    for chemin in sorted(p for p in racine.rglob("*") if p.is_file()):
        cle = normaliser_cle(chemin.relative_to(racine))
        taille_locale = chemin.stat().st_size
        try:
            taille_distante = cible.taille(cle)
            if taille_distante == taille_locale:
                stats["deja_presents"] += 1
            else:
                cible.ecrire(cle, chemin.read_bytes())
                if cible.taille(cle) != taille_locale:
                    raise OSError(f"taille incohérente après envoi : {cle}")
                stats["envoyes"] += 1
            if supprimer_apres:
                chemin.unlink()
                stats["supprimes"] += 1
        except Exception:
            logger.exception("Migration échouée pour %s", cle)
            stats["echecs"] += 1
    if supprimer_apres:
        # dossiers devenus vides après la suppression des fichiers
        for dossier in sorted((p for p in racine.rglob("*") if p.is_dir()), reverse=True):
            if not any(dossier.iterdir()):
                dossier.rmdir()
    return stats


def main() -> int:
    """Usage : python -m app.stockage migrer [--garder-local]"""
    import logging as _logging
    import sys

    _logging.basicConfig(level=_logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) < 2 or sys.argv[1] != "migrer":
        print(main.__doc__)
        return 1
    garder = "--garder-local" in sys.argv
    stats = migrer_depuis_local(settings.data_dir, supprimer_apres=not garder)
    print(
        f"{stats['envoyes']} envoyé(s), {stats['deja_presents']} déjà présent(s), "
        f"{stats['supprimes']} supprimé(s) en local, {stats['echecs']} échec(s)."
    )
    if stats["echecs"]:
        print("⚠ des fichiers n'ont PAS été migrés : ils restent sur le disque local.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CleInvalide",
    "StockageLocal",
    "StockageS3",
    "migrer_depuis_local",
    "normaliser_cle",
    "stockage",
]
