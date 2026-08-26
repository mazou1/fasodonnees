"""Texte des publications sociales.

C'est la seule partie du module qu'un citoyen lira jamais : elle est isolée des
clients réseau pour se tester intégralement sans jeton ni appel HTTP.

Le texte reste factuel - titre, contexte, lien. La plateforme rapporte ce que
les sources officielles publient ; sa page ne commente pas, sinon elle cesse
d'être un point de repère neutre.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

# Longueur maximale d'un post, par réseau.
LIMITES = {"x": 280, "telegram": 4096, "facebook": 60000}

# X ne compte pas les URL pour leur longueur réelle : toute URL vaut 23
# caractères (raccourcisseur t.co). Compter les caractères réels ferait rejeter
# les posts dont le lien est long, ou gaspillerait du texte sur les autres.
LONGUEUR_LIEN_X = 23

# Longueur maximale du résumé repris de la source, là où la place le permet.
LIMITE_RESUME = 400

EMOJI = {"conseil": "\U0001f3db️", "decision": "\U0001f4cc", "actualite": "\U0001f4f0"}

# Le contexte se lit différemment selon le genre : « via Sidwaya » pour un
# article de presse (la source doit être créditée dans le post lui-même, pas
# seulement sur la page d'arrivée), le ministère seul pour une décision.
PREFIXE_CONTEXTE = {"actualite": "via "}

HASHTAGS = {
    "conseil": ("#BurkinaFaso", "#ConseilDesMinistres"),
    "decision": ("#BurkinaFaso", "#ConseilDesMinistres"),
    "actualite": ("#BurkinaFaso",),
}


@dataclass(frozen=True)
class Item:
    """Une publication du site, prête à être diffusée.

    `cle` est l'identifiant stable qui sert de garde anti-doublon dans le
    journal `publication` : il ne doit dépendre que de l'entité, jamais de la
    date d'exécution ni du réseau.
    """

    cle: str
    genre: str  # conseil | decision | actualite
    titre: str
    lien: str
    date: date | None = None
    resume: str | None = None
    contexte: str | None = None  # média d'origine, ou ministère


def tronquer(texte: str, limite: int) -> str:
    """Coupe sur un mot entier. Une coupure au milieu d'un nom propre ou d'un
    montant se lit comme une erreur de la plateforme, pas comme un résumé."""
    texte = texte.strip()
    if len(texte) <= limite:
        return texte
    coupe = texte[: max(limite - 1, 1)]
    espace = coupe.rfind(" ")
    # On ne recule jusqu'au mot précédent que si cela ne sacrifie pas la moitié
    # du texte : sur un libellé sans espace, mieux vaut couper net.
    if espace > limite * 0.6:
        coupe = coupe[:espace]
    return coupe.rstrip(" ,;:.’'-") + "…"


# Passe-partout que les flux WordPress collent en fin de résumé : « The post X
# appeared first on Y », sa variante française, et le « […] » de troncature de
# l'AIB. Repris tel quel, il occupe la place du texte utile et donne des posts
# qui se terminent tous pareil.
_PASSE_PARTOUT = re.compile(
    r"\s*(?:The post\b|L(?:’|')article\b|Cet article\b|Continue reading\b|\[…\]|\[\.\.\.\]).*",
    re.IGNORECASE | re.DOTALL,
)


def lisible(texte: str) -> str:
    """Ramène les fantaisies typographiques à des lettres ordinaires.

    Les annonces de gouvernement.gov.bf emploient les mathematical bold du
    plan 1 : « 𝐒𝐨𝐮𝐯𝐞𝐫𝐚𝐢𝐧𝐞𝐭é 𝐚𝐥𝐢𝐦𝐞𝐧𝐭𝐚𝐢𝐫𝐞 ». Un lecteur d'écran les épelle
    caractère par caractère, la recherche du réseau ne les trouve pas, et
    certaines polices ne les ont pas. NFKC les rend au texte qu'elles imitent,
    sans rien retirer au sens - c'est de la mise en forme, pas du contenu.
    """
    return unicodedata.normalize("NFKC", texte)


def _sans_accent_ni_ponctuation(texte: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texte.lower())
    sans = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", sans)).strip()


def nettoyer_resume(resume: str | None, titre: str) -> str | None:
    """Résumé débarrassé de ce qui ne dit rien de plus que le titre.

    Les fils de l'AIB republient le titre en tête du chapô : affiché tel quel,
    le post dit deux fois la même chose et le lecteur croit à un bogue. Le
    passe-partout WordPress, lui, occupe la place du texte utile.
    """
    if not resume:
        return None
    texte = _PASSE_PARTOUT.sub("", resume).strip()
    # le titre en tête se compare sans accent ni ponctuation : les flux le
    # reprennent en le retouchant (tiret, espace insécable, capitales)
    reference = _sans_accent_ni_ponctuation(titre)
    if reference:
        mots = texte.split()
        for fin in range(len(mots), 0, -1):
            if _sans_accent_ni_ponctuation(" ".join(mots[:fin])) == reference:
                texte = " ".join(mots[fin:]).lstrip(" -–:;,.")
                break
    return texte.strip() or None


def _corps(item: Item, reseau: str, budget: int) -> str:
    """Le corps du post, ajusté au budget disponible.

    Les blocs secondaires sont ABANDONNÉS plutôt que coupés : un post qui se
    termine par « Ministère de la… » se lit comme une panne d'affichage, là où
    un titre seul reste une information complète. Le résumé part le premier, le
    contexte ensuite ; le titre, jamais.
    """
    blocs = [f"{EMOJI.get(item.genre, '')} {lisible(item.titre)}".strip()]
    if item.contexte:
        blocs.append(f"{PREFIXE_CONTEXTE.get(item.genre, '')}{item.contexte}")
    # Le résumé est un confort de lecture, pas une information de plus : sur X
    # il mangerait la place du titre, qui lui est indispensable.
    resume = nettoyer_resume(item.resume, item.titre) if reseau != "x" else None
    if resume:
        blocs.append("\n" + tronquer(lisible(resume), LIMITE_RESUME))
    while len(blocs) > 1 and len("\n".join(blocs)) > budget:
        blocs.pop()
    return tronquer("\n".join(blocs), budget)


def composer(item: Item, reseau: str) -> str:
    """Le texte complet du post : corps, hashtags, lien.

    Le lien est réservé AVANT de tronquer le corps, jamais l'inverse : un post
    coupé reste utile si le lien survit, l'inverse ne l'est pas.
    """
    hashtags = " ".join(HASHTAGS.get(item.genre, ()))
    limite = LIMITES.get(reseau, LIMITES["telegram"])
    cout_lien = LONGUEUR_LIEN_X if reseau == "x" else len(item.lien)
    bas = f"{hashtags}\n{item.lien}" if hashtags else item.lien
    reserve = cout_lien + (len(hashtags) + 1 if hashtags else 0) + 2  # + les 2 sauts de ligne
    corps = _corps(item, reseau, max(limite - reserve, 40))
    return f"{corps}\n\n{bas}"


def longueur_percue(message: str, lien: str, reseau: str) -> int:
    """Longueur telle que le réseau la compte (X applique son forfait d'URL)."""
    if reseau != "x" or lien not in message:
        return len(message)
    return len(message) - len(lien) + LONGUEUR_LIEN_X
