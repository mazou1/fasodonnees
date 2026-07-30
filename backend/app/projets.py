"""Dossiers de suivi : relier l'annonce, l'attribution et la livraison.

L'État parle d'un même projet à trois endroits, sans jamais lui donner le même
identifiant :

  1. le Conseil des ministres l'ANNONCE      → `EngagementFinancier`
  2. le Quotidien de la DGCMEF l'ATTRIBUE    → `Marche`
  3. l'inauguration le déclare LIVRÉ         → `Realisation`

Recoller ces trois maillons est ce que la plateforme peut faire et qu'aucune
des trois sources ne fait. C'est aussi ce qui se prête le plus à l'erreur :
« Construction d'infrastructures sanitaires » ressemble à tout. Le
rapprochement est donc une PROPOSITION relue par un humain, jamais un fait
publié d'office — même principe que `app/fusion.py`.

Comment le score est construit
------------------------------
Le trigramme brut sur les libellés ne discrimine rien : le vocabulaire des
travaux publics (« construction », « acquisition », « travaux », « profit »)
sature la similarité. On score donc sur les **tokens distinctifs** — ce qui
reste une fois ce vocabulaire retiré : toponymes, noms d'ouvrages, sigles,
quantités. Trois indices corroborent ensuite, sans jamais suffire seuls :

- **montant** : des ordres de grandeur proches (rapport ≤ 4) confortent ;
- **chronologie** : on annonce avant d'attribuer, on attribue avant de livrer ;
- **secteur/région** : une divergence franche pénalise.

Usage : python -m app.projets proposer [seuil] | appliquer <csv> | statuts
"""

from __future__ import annotations

import csv
import logging
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import EngagementFinancier, Marche, Projet, Realisation

logger = logging.getLogger(__name__)

CSV_PROPOSITIONS = Path("projets_propositions.csv")

# Vocabulaire commun à presque toutes les lignes des trois corpus : il gonfle
# la similarité sans rien distinguer. Retiré AVANT de comparer.
VOCABULAIRE_GENERIQUE = {
    # actes
    "construction", "constructions", "construire", "realisation", "realisations",
    "acquisition", "acquisitions", "acquerir", "travaux", "equipement",
    "equipements", "fourniture", "fournitures", "livraison", "installation",
    "installations", "amenagement", "amenagements", "rehabilitation",
    "renovation", "extension", "amelioration", "mise", "oeuvre", "service",
    "services", "prestation", "prestations", "entretien", "maintenance",
    "achat", "vente", "location", "financement", "attribution", "attributions",
    "marche", "marches", "projet", "projets", "programme", "programmes",
    "lot", "lots", "unique", "profit", "compte", "cadre", "faveur", "titre",
    "relatif", "relative", "portant", "concernant", "divers", "diverses",
    # institutions/administration
    "ministere", "ministeres", "etat", "burkina", "faso", "burkinabe",
    "gouvernement", "national", "nationale", "nationaux", "nationales",
    "public", "publics", "publique", "publiques", "direction", "generale",
    "general", "societe", "agence", "office", "conseil", "ministres",
    "administration", "budget", "fonds", "programme",
    # liaison
    "pour", "dans", "avec", "les", "des", "une", "aux", "par", "sur", "sous",
    "entre", "chez", "leur", "leurs", "cette", "cet", "ces", "son", "sen",
    "est", "sont", "ont", "ete", "etre", "plus", "tout", "tous", "toute",
    "toutes", "autre", "autres", "ainsi", "que", "qui", "dont", "afin",
}

MOTS_COURTS_UTILES = {"cm", "km", "mw", "kv", "r5", "r1", "chu", "chr", "csps"}

# Un token présent dans plus de ~1,5 % du corpus ne désigne plus un projet en
# particulier. Deux pièces qui ne partagent QUE de tels mots (« centre »,
# « hospitalier », « universitaire ») ne sont pas identifiées comme le même
# projet : il leur manque le nom propre. Exprimé en IDF, ce seuil ne dépend pas
# de la taille du corpus — log(1 / 0,015).
SEUIL_IDENTIFIANT = math.log(1 / 0.015)


def normaliser(texte: str | None) -> str:
    nfkd = unicodedata.normalize("NFKD", texte or "")
    sans_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sans_accents.replace("’", "'")).strip().lower()


def tokens_distinctifs(texte: str | None) -> set[str]:
    """Ce qui reste d'un libellé une fois le vocabulaire générique retiré.

    Les nombres sont conservés (« 431 salles », « 26,4 MW », « R+5 ») : ils
    portent souvent l'essentiel de l'identité d'un projet.
    """
    brut = re.split(r"[^a-z0-9+]+", normaliser(texte))
    return {
        mot
        for mot in brut
        if mot
        and mot not in VOCABULAIRE_GENERIQUE
        and (len(mot) >= 4 or mot in MOTS_COURTS_UTILES or any(c.isdigit() for c in mot))
    }


def poids_rarete(corpus: list[set[str]]) -> dict[str, float]:
    """Poids IDF de chaque token : un mot rare identifie, un mot courant non.

    Sans cela, « CHU de Bogodogo » se rapproche de n'importe quel marché passé
    « au profit du centre hospitalier universitaire » : trois mots communs,
    tous fréquents, et le toponyme — le seul qui identifie — absent. Pondérer
    par la rareté fait tomber ces paires et remonter celles qui partagent un
    nom propre.
    """
    n = max(1, len(corpus))
    frequences: dict[str, int] = {}
    for tokens in corpus:
        for t in tokens:
            frequences[t] = frequences.get(t, 0) + 1
    return {t: math.log(n / (1 + df)) for t, df in frequences.items()}


def similarite_tokens(a: set[str], b: set[str], poids: dict[str, float] | None = None) -> float:
    """Dice pondéré par la rareté des tokens (0 → 1).

    Sans `poids`, retombe sur un Dice classique — pratique pour les tests.
    """
    if not a or not b:
        return 0.0
    if poids is None:
        return 2 * len(a & b) / (len(a) + len(b))

    def masse(tokens):
        return sum(max(poids.get(t, 0.0), 0.0) for t in tokens)

    denominateur = masse(a) + masse(b)
    if denominateur <= 0:  # que des tokens ultra-fréquents : rien d'identifiant
        return 0.0
    return 2 * masse(a & b) / denominateur


def proximite_montants(m1: int | None, m2: int | None) -> float | None:
    """1.0 si les montants se valent, 0.0 s'ils sont hors d'échelle, None si
    l'un manque. Un marché ne couvre souvent qu'un lot de l'annonce : on
    tolère un rapport de 1 à 4 avant de pénaliser."""
    if not m1 or not m2:
        return None
    grand, petit = max(m1, m2), min(m1, m2)
    rapport = grand / petit
    if rapport <= 1.1:
        return 1.0
    if rapport >= 10:
        return 0.0
    return max(0.0, 1.0 - (rapport - 1.1) / 8.9)


@dataclass
class Piece:
    """Un maillon comparable, quelle que soit sa table d'origine."""

    genre: str  # engagement | marche | realisation
    id: int
    libelle: str
    tokens: set[str]
    montant: int | None
    secteur: str | None
    region: str | None
    ordre: int  # rang attendu dans la chaîne : 0 annonce, 1 attribution, 2 livraison
    date: object | None

    def resume(self) -> str:
        return f"{self.genre}#{self.id} {self.libelle[:70]}"


ORDRE = {"engagement": 0, "marche": 1, "realisation": 2}


def _pieces(db: Session) -> list[Piece]:
    """Charge les trois corpus validés sous une forme comparable."""
    pieces: list[Piece] = []
    for e in db.scalars(
        select(EngagementFinancier).where(EngagementFinancier.statut_validation == "valide")
    ):
        texte = f"{e.objet} {e.beneficiaire or ''}"
        pieces.append(
            Piece("engagement", e.id, e.objet, tokens_distinctifs(texte), e.montant_fcfa,
                  None, None, ORDRE["engagement"],
                  e.document.date_publication if e.document else None)
        )
    for m in db.scalars(select(Marche).where(Marche.statut_validation == "valide")):
        texte = f"{m.objet} {m.autorite or ''}"
        pieces.append(
            Piece("marche", m.id, m.objet, tokens_distinctifs(texte), m.montant_fcfa,
                  m.secteur, m.region, ORDRE["marche"], m.date_attribution)
        )
    for r in db.scalars(select(Realisation).where(Realisation.statut_validation == "valide")):
        texte = f"{r.titre} {r.description or ''} {r.localisation_nom or ''}"
        pieces.append(
            Piece("realisation", r.id, r.titre, tokens_distinctifs(texte), r.montant_fcfa,
                  r.secteur, r.region, ORDRE["realisation"], r.date_evenement)
        )
    return pieces


def score(a: Piece, b: Piece, poids: dict[str, float] | None = None) -> tuple[float, dict[str, str]]:
    """Score de rapprochement et indices lisibles pour la relecture."""
    base = similarite_tokens(a.tokens, b.tokens, poids)
    indices: dict[str, str] = {}
    communs = sorted(a.tokens & b.tokens, key=lambda t: -(poids or {}).get(t, 0.0))
    indices["tokens_communs"] = " ".join(communs)

    total = base
    prox = proximite_montants(a.montant, b.montant)
    if prox is None:
        indices["montants"] = "montant manquant"
    else:
        indices["montants"] = f"{prox:.2f}"
        total += 0.15 * (prox - 0.5)  # conforte ou pénalise, sans dominer

    amont, aval = (a, b) if a.ordre <= b.ordre else (b, a)
    if amont.date and aval.date and aval.date < amont.date:
        indices["chronologie"] = "incohérente (le maillon aval précède l'amont)"
        total -= 0.10
    else:
        indices["chronologie"] = "plausible"

    if a.secteur and b.secteur:
        concorde = a.secteur == b.secteur
        indices["secteur"] = "identique" if concorde else f"{a.secteur} ≠ {b.secteur}"
        total += 0.05 if concorde else -0.10
    else:
        indices["secteur"] = "inconnu"

    # garde-fou de précision : sans mot rare partagé, rien n'identifie le projet
    if poids is not None:
        rarete = max((poids.get(t, 0.0) for t in communs), default=0.0)
        if rarete >= SEUIL_IDENTIFIANT:
            indices["mot_identifiant"] = communs[0]
        else:
            indices["mot_identifiant"] = "aucun (mots trop courants)"
            total *= 0.6
    else:
        indices["mot_identifiant"] = ""

    return max(0.0, min(1.0, total)), indices


def proposer(db: Session, seuil: float) -> int:
    """Écrit les paires candidates à relire, la plus probable d'abord.

    On ne compare que des maillons de genres DIFFÉRENTS : deux marchés qui se
    ressemblent ne forment pas un projet, ils sont juste deux marchés.
    """
    pieces = _pieces(db)
    poids = poids_rarete([p.tokens for p in pieces])
    # index inversé : deux pièces sans aucun token distinctif commun ne peuvent
    # pas atteindre le seuil — inutile de les comparer (évite le produit complet)
    par_token: dict[str, list[int]] = {}
    for i, p in enumerate(pieces):
        for t in p.tokens:
            par_token.setdefault(t, []).append(i)

    vues: set[tuple[int, int]] = set()
    lignes = []
    for indices_pieces in par_token.values():
        if len(indices_pieces) > 60:  # token trop commun pour être discriminant
            continue
        for pos, i in enumerate(indices_pieces):
            for j in indices_pieces[pos + 1:]:
                cle = (min(i, j), max(i, j))
                if cle in vues:
                    continue
                vues.add(cle)
                a, b = pieces[i], pieces[j]
                if a.genre == b.genre:
                    continue
                valeur, ind = score(a, b, poids)
                if valeur >= seuil:
                    amont, aval = (a, b) if a.ordre <= b.ordre else (b, a)
                    lignes.append((valeur, amont, aval, ind))

    lignes.sort(key=lambda ligne: ligne[0], reverse=True)
    with CSV_PROPOSITIONS.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "appliquer", "score", "genre_amont", "id_amont", "libelle_amont", "montant_amont",
            "genre_aval", "id_aval", "libelle_aval", "montant_aval",
            "mot_identifiant", "tokens_communs", "montants", "chronologie", "secteur",
        ])
        for valeur, amont, aval, ind in lignes:
            w.writerow([
                "", f"{valeur:.2f}", amont.genre, amont.id, amont.libelle[:200], amont.montant or "",
                aval.genre, aval.id, aval.libelle[:200], aval.montant or "",
                ind["mot_identifiant"], ind["tokens_communs"], ind["montants"],
                ind["chronologie"], ind["secteur"],
            ])
    return len(lignes)


def _table(genre: str):
    return {
        "engagement": EngagementFinancier,
        "marche": Marche,
        "realisation": Realisation,
    }[genre]


def appliquer(db: Session, chemin: Path) -> tuple[int, int]:
    """Regroupe les paires acceptées en dossiers de suivi.

    Les paires acceptées forment un graphe ; chaque composante connexe est un
    projet. Une pièce déjà rattachée à un projet y ramène toute sa composante :
    accepter « A–B » puis « B–C » construit bien un seul dossier A-B-C.
    """
    parent: dict[tuple[str, int], tuple[str, int]] = {}

    def racine(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def unir(x, y):
        rx, ry = racine(x), racine(y)
        if rx != ry:
            parent[rx] = ry

    acceptees = 0
    with chemin.open(newline="") as f:
        for ligne in csv.DictReader(f):
            if ligne["appliquer"].strip().lower() not in ("oui", "o", "x", "1", "true"):
                continue
            unir(
                (ligne["genre_amont"], int(ligne["id_amont"])),
                (ligne["genre_aval"], int(ligne["id_aval"])),
            )
            acceptees += 1

    composantes: dict[tuple[str, int], list[tuple[str, int]]] = {}
    for cle in parent:
        composantes.setdefault(racine(cle), []).append(cle)

    projets_crees = 0
    for membres in composantes.values():
        objets = [db.get(_table(genre), id_) for genre, id_ in membres]
        objets = [o for o in objets if o is not None]
        if len(objets) < 2:
            continue

        # une pièce déjà rattachée impose son dossier : on ne duplique pas
        existant = next((o.projet_id for o in objets if o.projet_id), None)
        if existant:
            projet = db.get(Projet, existant)
        else:
            projet = Projet(
                titre=_titre(membres, objets),
                secteur=next((getattr(o, "secteur", None) for o in objets
                              if getattr(o, "secteur", None)), None),
                region=next((getattr(o, "region", None) for o in objets
                             if getattr(o, "region", None)), None),
                statut_validation="valide",  # la relecture du CSV EST la validation
            )
            db.add(projet)
            db.flush()
            projets_crees += 1
        for o in objets:
            o.projet_id = projet.id

    db.commit()
    return acceptees, projets_crees


def _titre(membres, objets) -> str:
    """Titre du dossier : le libellé de l'annonce si elle est là (c'est le
    vocabulaire officiel du projet), sinon le libellé le plus complet."""
    for (genre, _), o in zip(membres, objets):
        if genre == "engagement":
            return o.objet[:500]
    libelles = [getattr(o, "titre", None) or getattr(o, "objet", "") for o in objets]
    return max(libelles, key=len)[:500]


# Du plus avancé au moins avancé — l'ordre EST la règle de priorité.
STADES = ("livre", "en_travaux", "attribue", "annonce")


def stade(a_un_marche: bool, statuts_realisations: list[str]) -> str:
    """Stade d'avancement, déduit des pièces rattachées.

    La nuance vient du `statut` des réalisations : une **première pierre** dit
    que le chantier a commencé, pas qu'il est livré — le confondre avec une
    inauguration reviendrait à annoncer livré ce qui ne l'est pas.
    """
    statuts = set(statuts_realisations)
    if statuts & {"inauguration", "mise_en_service"}:
        return "livre"
    if "premiere_pierre" in statuts:
        return "en_travaux"
    if a_un_marche:
        return "attribue"
    return "annonce"


def statuts(db: Session) -> int:
    """Récapitulatif des dossiers existants (contrôle après application)."""
    projets = db.scalars(select(Projet)).all()
    if not projets:
        print("Aucun dossier de suivi. Lancer : python -m app.projets proposer")
        return 0
    for p in projets:
        n_e = len(db.scalars(
            select(EngagementFinancier.id).where(EngagementFinancier.projet_id == p.id)
        ).all())
        n_m = len(db.scalars(select(Marche.id).where(Marche.projet_id == p.id)).all())
        realisations = db.scalars(
            select(Realisation).where(Realisation.projet_id == p.id)
        ).all()
        print(
            f"#{p.id:3} [{stade(bool(n_m), [r.statut for r in realisations]):10}] "
            f"{n_e} annonce(s) · {n_m} marché(s) · {len(realisations)} réalisation(s)  "
            f"{p.titre[:60]}"
        )
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    commande = sys.argv[1] if len(sys.argv) > 1 else "proposer"
    with SessionLocal() as db:
        if commande == "proposer":
            seuil = float(sys.argv[2]) if len(sys.argv) > 2 else 0.30
            n = proposer(db, seuil)
            print(
                f"{n} paire(s) candidate(s) dans {CSV_PROPOSITIONS} — mettre 'oui' dans la "
                f"colonne appliquer (colonnes tokens_communs/montants/chronologie pour juger), "
                f"puis : python -m app.projets appliquer {CSV_PROPOSITIONS}"
            )
        elif commande == "appliquer":
            acceptees, crees = appliquer(db, Path(sys.argv[2]))
            print(f"{acceptees} paire(s) acceptée(s) → {crees} dossier(s) de suivi créé(s).")
        elif commande == "statuts":
            return statuts(db)
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
