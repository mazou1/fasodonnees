"""Consolidation des attributaires de marchés publics.

Le Quotidien de la DGCMEF ne tient aucun registre d'entreprises : chaque
synthèse de résultats écrit la raison sociale comme elle vient. « ETS
WEND-KUUNI », « Ets Wend Kuuni SARL » et « ETS WEND KUUNI Sarl » sont la même
entreprise, mais trois lignes distinctes dans `marche.attributaire`. Sans
regroupement, aucune question intéressante n'est calculable : combien cette
entreprise a-t-elle remporté, auprès de quelles autorités contractantes,
dans quels secteurs.

Ce module construit une entité `Attributaire` DÉRIVÉE :

- `marche.attributaire` garde toujours la chaîne exacte du document — comme
  les mandats gardent leur structure d'époque, la source brute n'est jamais
  réécrite ;
- `consolider` est **idempotent** : on peut le relancer après chaque lot de
  validations, il ne crée que ce qui manque.

Le rattachement automatique est **strict** (même forme normalisée). Les
variantes plus éloignées passent par une relecture humaine, comme la fusion
des structures (`app/fusion.py`) :

- `consolider`          : (re)construit les entités, rattache les marchés, et
                          fusionne d'office les variantes dont la similarité
                          dépasse `SEUIL_FUSION_AUTO` (bruit d'extraction).
- `proposer [seuil]`    : écrit attributaires_propositions.csv pour la bande
                          AMBIGUË, sous le seuil automatique — mettre « oui » en
                          colonne `appliquer` pour fusionner.
- `appliquer <csv>`     : applique les fusions relues.
- `rapprocher [seuil]`  : signale les raisons sociales qui ressemblent au nom
                          d'une personne de l'annuaire. Rapport de relecture
                          interne — cf. la note déontologique dans `rapprocher`.

Usage : python -m app.attributaires consolider | proposer [seuil]
                                     | appliquer <csv> | rapprocher [seuil]
"""

from __future__ import annotations

import csv
import logging
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Attributaire, Marche

logger = logging.getLogger(__name__)

CSV_PROPOSITIONS = Path("attributaires_propositions.csv")
CSV_RAPPROCHEMENTS = Path("attributaires_personnes.csv")

# Seuil de fusion AUTOMATIQUE des variantes proches. Calibré sur le corpus : au
# delà, les paires observées sont du bruit d'extraction sur une même raison
# sociale (« u HABIB TRADING INTERNATIONAL » / « HABIB TRADING INTERNATIONAL »
# à 0,93 ; « à GENERAL MICRO SYSTEM » à 0,91). En dessous apparaissent les vrais
# faux amis : « REAL SERVICES INTERNATIONAL » et « RELLYA SERVICES
# INTERNATIONAL » à 0,78 sont deux entreprises différentes, et les fusionner
# attribuerait les marchés de l'une à l'autre. Cette bande-là reste en
# proposition à relire (`proposer`).
SEUIL_FUSION_AUTO = 0.90

# Formes juridiques et préfixes de commerce : ils varient d'une publication à
# l'autre pour une même entreprise, donc ils ne discriminent pas. Retirés
# uniquement en tant que mots isolés, et jamais au point de vider le nom.
FORMES_JURIDIQUES = {
    "sarl", "sarlu", "suarl", "sa", "sau", "sas", "sasu", "eurl", "eirl",
    "ei", "gie", "snc", "sci", "scp", "scop", "sprl", "ltd", "llc", "inc",
    "ste", "societe", "ets", "etp", "etablissement", "etablissements",
    "entreprise", "entreprises", "compagnie", "cie",
}

# « E.W.K. » → « ewk » : sigle pointé, à recoller avant de retirer la ponctuation
_SIGLE_POINTE = re.compile(r"^(?:[a-z]\.){2,}$")


def normaliser_raison_sociale(nom: str) -> str:
    """Forme canonique d'une raison sociale, pour le rattachement strict.

    Volontairement modérée : elle unifie ce qui est typographique (accents,
    casse, ponctuation, forme juridique) et rien de plus. Deux entreprises
    réellement distinctes ne doivent jamais tomber sur la même forme — le
    rapprochement des variantes plus lointaines est une décision humaine
    (`proposer`/`appliquer`).
    """
    nfkd = unicodedata.normalize("NFKD", nom)
    texte = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    texte = texte.replace("’", "'").replace("‘", "'")
    texte = texte.replace("&", " et ")
    texte = re.sub(r"[-–—_/\\]", " ", texte)

    jetons = []
    for jeton in texte.split():
        if _SIGLE_POINTE.match(jeton):  # e.w.k. → ewk
            jeton = jeton.replace(".", "")
        jeton = re.sub(r"[^\w']", "", jeton)
        if jeton:
            jetons.append(jeton)

    utiles = [j for j in jetons if j not in FORMES_JURIDIQUES]
    # « SARL » seul, ou « Ets » seul : on ne peut rien retirer sans tout perdre
    retenus = utiles or jetons
    return " ".join(retenus).strip()


def _forme_affichee(variantes: Counter[str]) -> str:
    """Choisit la graphie à afficher parmi celles vues dans les documents.

    La plus fréquente ; à égalité, la plus longue (elle porte en général la
    raison sociale complète), puis l'ordre alphabétique pour rester
    déterministe d'une exécution à l'autre.
    """
    return max(variantes.items(), key=lambda kv: (kv[1], len(kv[0]), kv[0]))[0].strip()


def _resoudre(db: Session, attributaire_id: int) -> int:
    """Suit la chaîne canonique_id jusqu'à la racine (cf. app/fusion.py)."""
    vu: set[int] = set()
    aid = attributaire_id
    while True:
        if aid in vu:  # cycle — on s'arrête
            return aid
        vu.add(aid)
        cid = db.scalar(select(Attributaire.canonique_id).where(Attributaire.id == aid))
        if cid is None:
            return aid
        aid = cid


def consolider(db: Session) -> dict[str, int]:
    """(Re)construit les entités et rattache chaque marché à la sienne.

    Idempotent : relançable après chaque lot de validations. Porte sur TOUS
    les marchés, y compris `a_valider` — le rattachement n'est pas une
    publication ; l'API, elle, ne sert que le validé.
    """
    variantes: dict[str, Counter[str]] = defaultdict(Counter)
    lignes = db.execute(
        select(Marche.attributaire, func.count())
        .where(Marche.attributaire.is_not(None), func.trim(Marche.attributaire) != "")
        .group_by(Marche.attributaire)
    ).all()
    for brut, n in lignes:
        forme = normaliser_raison_sociale(brut)
        if forme:
            # clé = la valeur EXACTE en base (le `in_()` du rattachement s'y réfère)
            variantes[forme][brut] += n

    existants = {a.nom_normalise: a for a in db.scalars(select(Attributaire)).all()}
    crees = 0
    for forme, formes_brutes in variantes.items():
        affiche = _forme_affichee(formes_brutes)
        entite = existants.get(forme)
        if entite is None:
            entite = Attributaire(nom=affiche, nom_normalise=forme)
            db.add(entite)
            existants[forme] = entite
            crees += 1
        elif not entite.nom_fige and entite.nom != affiche:
            # un nouveau document a fait émerger une graphie plus fréquente
            entite.nom = affiche
    db.flush()

    rattaches = 0
    for forme, formes_brutes in variantes.items():
        entite_id = existants[forme].id
        resultat = db.execute(
            update(Marche)
            .where(
                Marche.attributaire.in_(list(formes_brutes)),
                (Marche.attributaire_id.is_(None)) | (Marche.attributaire_id != entite_id),
            )
            .values(attributaire_id=entite_id)
        )
        rattaches += resultat.rowcount or 0

    fusions = _fusionner_variantes_evidentes(db)
    db.commit()
    return {
        "entites": len(variantes),
        "creees": crees,
        "marches_rattaches": rattaches,
        "fusions_auto": fusions,
    }


def _fusionner_variantes_evidentes(db: Session) -> int:
    """Fusionne sans relecture les raisons sociales très proches.

    Le rattachement strict ne voit que les variantes typographiques. Restait le
    bruit d'extraction — un caractère parasite collé devant le nom — qui créait
    une entité fantôme par occurrence. Au-dessus de `SEUIL_FUSION_AUTO`, ces
    paires sont sans ambiguïté ; en dessous, la relecture reste requise.

    Le nom conservé est le plus COURT des deux. Le bruit d'extraction ajoute des
    caractères — un « u » ou un « à » happé devant la raison sociale — il n'en
    retire jamais. Se fonder sur l'ancienneté serait trompeur : « u HABIB TRADING
    INTERNATIONAL » porte un identifiant plus petit que la forme propre, et
    l'avoir pris pour canonique affichait le bruit sur la fiche publique.
    """
    lignes = db.execute(
        text(
            """
            SELECT a1.id AS id_a, a1.nom_normalise AS nom_a,
                   a2.id AS id_b, a2.nom_normalise AS nom_b
            FROM attributaire a1
            JOIN attributaire a2 ON a2.id < a1.id
            WHERE a1.canonique_id IS NULL AND a2.canonique_id IS NULL
              AND similarity(a1.nom_normalise, a2.nom_normalise) >= :seuil
            ORDER BY similarity(a1.nom_normalise, a2.nom_normalise) DESC
            """
        ),
        {"seuil": SEUIL_FUSION_AUTO},
    ).all()
    fusions = 0
    for ligne in lignes:
        # à longueur égale, l'identifiant tranche pour rester déterministe
        if (len(ligne.nom_a), ligne.id_a) <= (len(ligne.nom_b), ligne.id_b):
            cible, source = ligne.id_a, ligne.id_b
        else:
            cible, source = ligne.id_b, ligne.id_a
        # une entité déjà fusionnée entre-temps ne l'est pas deux fois
        if db.scalar(select(Attributaire.canonique_id).where(Attributaire.id == source)):
            continue
        fusionner(db, source, cible)
        fusions += 1
    return fusions


def fusionner(db: Session, source_id: int, canonique_id: int) -> None:
    racine = _resoudre(db, canonique_id)
    if racine == source_id:
        return
    source = db.get(Attributaire, source_id)
    if source is None or db.get(Attributaire, racine) is None:
        return
    source.canonique_id = racine


def proposer(db: Session, seuil: float) -> int:
    """Paires de raisons sociales proches, à relire.

    La similarité porte sur `nom_normalise` (déjà désaccentué en Python) :
    inutile de dépendre de l'extension `unaccent`, qui n'est pas installée
    par les migrations.
    """
    lignes = db.execute(
        text(
            """
            SELECT a1.id AS id_source, a1.nom AS nom_source,
                   a2.id AS id_canonique, a2.nom AS nom_canonique,
                   round(similarity(a1.nom_normalise, a2.nom_normalise)::numeric, 2) AS sim,
                   (SELECT count(*) FROM marche m WHERE m.attributaire_id = a1.id) AS n_source,
                   (SELECT count(*) FROM marche m WHERE m.attributaire_id = a2.id) AS n_canonique
            FROM attributaire a1
            JOIN attributaire a2 ON a2.id < a1.id
            WHERE a1.canonique_id IS NULL AND a2.canonique_id IS NULL
              AND similarity(a1.nom_normalise, a2.nom_normalise) >= :seuil
              -- au-dessus, `consolider` a déjà fusionné : ne pas redemander un
              -- arbitrage sur ce qui est tranché
              AND similarity(a1.nom_normalise, a2.nom_normalise) < :plafond
            ORDER BY sim DESC
            """
        ),
        {"seuil": seuil, "plafond": SEUIL_FUSION_AUTO},
    ).all()
    with CSV_PROPOSITIONS.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "appliquer", "id_source", "nom_source", "nb_marches_source",
            "id_canonique", "nom_canonique", "nb_marches_canonique", "similarite",
        ])
        for ligne in lignes:
            w.writerow([
                "", ligne.id_source, ligne.nom_source, ligne.n_source,
                ligne.id_canonique, ligne.nom_canonique, ligne.n_canonique, ligne.sim,
            ])
    return len(lignes)


def appliquer(db: Session, chemin: Path) -> int:
    fusions = 0
    with chemin.open(newline="") as f:
        for ligne in csv.DictReader(f):
            if ligne["appliquer"].strip().lower() in ("oui", "o", "x", "1", "true"):
                fusionner(db, int(ligne["id_source"]), int(ligne["id_canonique"]))
                fusions += 1
    db.commit()
    return fusions


def rapprocher(db: Session, seuil: float) -> int:
    """Attributaires dont la raison sociale ressemble au nom d'une personne
    de l'annuaire.

    ⚠️ Rapport de RELECTURE INTERNE, jamais publié par l'API ni par le site.

    Une homonymie n'est pas un fait : au Burkina, beaucoup d'entreprises
    individuelles portent le patronyme de leur fondateur, et les patronymes
    les plus courants du pays sont partagés par des milliers de personnes.
    Une ligne de ce CSV ne dit qu'une chose : « ces deux chaînes se
    ressemblent, quelqu'un doit aller vérifier sur pièces ». Rien ne doit
    sortir de ce fichier sans une source qui l'établisse.
    """
    lignes = db.execute(
        text(
            """
            SELECT a.id AS attributaire_id, a.nom AS attributaire,
                   p.id AS personne_id, p.nom_complet AS personne,
                   round(similarity(a.nom_normalise, p.nom_normalise)::numeric, 2) AS sim,
                   (SELECT count(*) FROM marche m
                     WHERE m.attributaire_id = a.id AND m.statut_validation = 'valide') AS n_marches,
                   (SELECT coalesce(sum(m.montant_fcfa), 0) FROM marche m
                     WHERE m.attributaire_id = a.id AND m.statut_validation = 'valide') AS montant
            FROM attributaire a
            JOIN personne p ON similarity(a.nom_normalise, p.nom_normalise) >= :seuil
            WHERE a.canonique_id IS NULL
            ORDER BY montant DESC, sim DESC
            """
        ),
        {"seuil": seuil},
    ).all()
    with CSV_RAPPROCHEMENTS.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "verifie", "attributaire_id", "attributaire", "personne_id", "personne",
            "similarite", "nb_marches_valides", "montant_fcfa",
        ])
        for ligne in lignes:
            w.writerow([
                "", ligne.attributaire_id, ligne.attributaire, ligne.personne_id,
                ligne.personne, ligne.sim, ligne.n_marches, ligne.montant,
            ])
    return len(lignes)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    commande = sys.argv[1] if len(sys.argv) > 1 else "consolider"
    with SessionLocal() as db:
        if commande == "consolider":
            stats = consolider(db)
            print(
                f"{stats['entites']} entité(s) ({stats['creees']} nouvelle(s)) — "
                f"{stats['marches_rattaches']} marché(s) rattaché(s), "
                f"{stats['fusions_auto']} variante(s) fusionnée(s) automatiquement "
                f"(similarité ≥ {SEUIL_FUSION_AUTO})."
            )
        elif commande == "proposer":
            seuil = float(sys.argv[2]) if len(sys.argv) > 2 else 0.65
            n = proposer(db, seuil)
            print(
                f"{n} proposition(s) écrites dans {CSV_PROPOSITIONS} — mettre 'oui' dans "
                f"la colonne appliquer puis : python -m app.attributaires appliquer "
                f"{CSV_PROPOSITIONS}"
            )
        elif commande == "appliquer":
            n = appliquer(db, Path(sys.argv[2]))
            print(f"{n} fusion(s) appliquée(s).")
        elif commande == "rapprocher":
            seuil = float(sys.argv[2]) if len(sys.argv) > 2 else 0.75
            n = rapprocher(db, seuil)
            print(
                f"{n} rapprochement(s) à vérifier dans {CSV_RAPPROCHEMENTS} — "
                "homonymies possibles, rien n'est publiable en l'état."
            )
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
