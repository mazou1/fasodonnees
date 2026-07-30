"""Couche de stockage de l'archive brute.

Le corpus archivé est l'actif du projet : ces tests protègent surtout contre
deux façons de le perdre — écrire hors du périmètre, et supprimer un original
avant de s'être assuré que la copie est bonne.
"""

import pytest

from app.stockage import CleInvalide, StockageLocal, migrer_depuis_local, normaliser_cle


# --- normalisation des clés -----------------------------------------------

@pytest.mark.parametrize(
    "brut,attendu",
    [
        ("legiburkina/2026/abc.pdf", "legiburkina/2026/abc.pdf"),
        ("legiburkina\\2026\\abc.pdf", "legiburkina/2026/abc.pdf"),  # séparateurs Windows
        ("./legiburkina//2026/abc.pdf", "legiburkina/2026/abc.pdf"),
    ],
)
def test_normalisation(brut, attendu):
    assert normaliser_cle(brut) == attendu


@pytest.mark.parametrize("brut", ["../etc/passwd", "/etc/passwd", "a/../../b", "", "."])
def test_les_cles_hors_perimetre_sont_refusees(brut):
    """`Document.fichier` alimente directement le stockage : une valeur
    corrompue en base ne doit pas permettre de lire ou d'écrire n'importe où."""
    with pytest.raises(CleInvalide):
        normaliser_cle(brut)


# --- backend local --------------------------------------------------------

def test_ecrire_puis_relire(tmp_path):
    s = StockageLocal(tmp_path)
    s.ecrire("source/2026/doc.pdf", b"%PDF-contenu")
    assert s.existe("source/2026/doc.pdf")
    assert s.lire("source/2026/doc.pdf") == b"%PDF-contenu"
    assert s.taille("source/2026/doc.pdf") == len(b"%PDF-contenu")


def test_reecrire_la_meme_cle_ne_touche_pas_au_fichier(tmp_path):
    """Le nom de fichier porte le hash du contenu : même clé = mêmes octets.
    Réécrire serait au mieux inutile, au pire destructeur."""
    s = StockageLocal(tmp_path)
    s.ecrire("source/doc.pdf", b"original")
    s.ecrire("source/doc.pdf", b"AUTRE CONTENU")
    assert s.lire("source/doc.pdf") == b"original"


def test_fichier_local_rend_un_chemin_lisible(tmp_path):
    s = StockageLocal(tmp_path)
    s.ecrire("source/doc.pdf", b"abc")
    with s.fichier_local("source/doc.pdf") as chemin:
        assert chemin.read_bytes() == b"abc"


def test_fichier_local_ne_supprime_pas_loriginal_en_mode_local(tmp_path):
    """En local le fichier n'est pas une copie temporaire : le context manager
    ne doit surtout pas l'effacer en sortant."""
    s = StockageLocal(tmp_path)
    s.ecrire("source/doc.pdf", b"abc")
    with s.fichier_local("source/doc.pdf"):
        pass
    assert s.existe("source/doc.pdf")


def test_absence_et_suppression(tmp_path):
    s = StockageLocal(tmp_path)
    assert not s.existe("rien.pdf")
    assert s.taille("rien.pdf") is None
    s.supprimer("rien.pdf")  # idempotent, ne lève pas
    s.ecrire("a/b.pdf", b"x")
    s.supprimer("a/b.pdf")
    assert not s.existe("a/b.pdf")


def test_url_ou_chemin_en_local(tmp_path):
    s = StockageLocal(tmp_path)
    s.ecrire("a/b.pdf", b"x")
    genre, valeur = s.url_ou_chemin("a/b.pdf")
    assert genre == "chemin"
    assert valeur.read_bytes() == b"x"


# --- migration ------------------------------------------------------------

class _CibleFactice:
    """Stockage objet simulé, avec possibilité d'échouer sur une clé donnée."""

    mode = "s3"

    def __init__(self, echoue_sur=None, corrompt=False):
        self.objets: dict[str, bytes] = {}
        self.echoue_sur = echoue_sur
        self.corrompt = corrompt

    def ecrire(self, cle, contenu):
        if cle == self.echoue_sur:
            raise OSError("envoi interrompu")
        self.objets[normaliser_cle(cle)] = b"tronque" if self.corrompt else contenu

    def taille(self, cle):
        objet = self.objets.get(normaliser_cle(cle))
        return len(objet) if objet is not None else None


def _archive(tmp_path):
    racine = tmp_path / "data"
    for cle, contenu in (
        ("legiburkina/2026/a.pdf", b"aaa"),
        ("dgcmef/2026/b.pdf", b"bbbb"),
    ):
        chemin = racine / cle
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(contenu)
    return racine


def test_migration_envoie_puis_libere_le_disque(tmp_path):
    racine = _archive(tmp_path)
    cible = _CibleFactice()
    stats = migrer_depuis_local(racine, supprimer_apres=True, cible=cible)
    assert stats == {"envoyes": 2, "deja_presents": 0, "supprimes": 2, "echecs": 0}
    assert cible.objets["legiburkina/2026/a.pdf"] == b"aaa"
    assert not any(p.is_file() for p in racine.rglob("*"))


def test_migration_reprenable_saute_ce_qui_est_deja_la(tmp_path):
    racine = _archive(tmp_path)
    cible = _CibleFactice()
    migrer_depuis_local(racine, supprimer_apres=False, cible=cible)
    stats = migrer_depuis_local(racine, supprimer_apres=False, cible=cible)
    assert stats["deja_presents"] == 2
    assert stats["envoyes"] == 0


def test_un_envoi_echoue_ne_supprime_jamais_loriginal(tmp_path):
    """Le point critique : perdre l'original d'un document officiel parce que
    l'envoi a échoué serait irréparable — le site source l'a peut-être
    dépublié depuis."""
    racine = _archive(tmp_path)
    cible = _CibleFactice(echoue_sur="legiburkina/2026/a.pdf")
    stats = migrer_depuis_local(racine, supprimer_apres=True, cible=cible)
    assert stats["echecs"] == 1
    assert (racine / "legiburkina/2026/a.pdf").is_file()
    assert not (racine / "dgcmef/2026/b.pdf").is_file()  # celui-ci est bien passé


def test_un_envoi_tronque_est_detecte_avant_suppression(tmp_path):
    """Un envoi qui « réussit » mais n'écrit pas les bons octets doit être vu :
    la taille distante est vérifiée avant de toucher au local."""
    racine = _archive(tmp_path)
    stats = migrer_depuis_local(racine, supprimer_apres=True, cible=_CibleFactice(corrompt=True))
    assert stats["echecs"] == 2
    assert all(p.is_file() for p in racine.rglob("*.pdf"))


def test_migrer_vers_le_local_est_refuse(tmp_path):
    with pytest.raises(RuntimeError):
        migrer_depuis_local(tmp_path, supprimer_apres=False, cible=StockageLocal(tmp_path))
