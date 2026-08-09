"""Validation en masse par seuil de confiance.

Une seule règle, deux portes d'entrée : la page « ① À valider » de `/admin`
(champ « seuil » + bouton « Valider tout ce qui atteint le seuil ») et la CLI
ci-dessous. Valide d'un coup toutes les entités `a_valider` dont le score de
confiance atteint le seuil ; celles qui restent sous le seuil demeurent en file
pour revue manuelle, une par une.

⚠️ Une entité SANS score n'est jamais validée par défaut, et ce n'est pas un
oubli : les marchés publics sont extraits de façon déterministe (tableaux du
Quotidien DGCMEF, pas de LLM) et ne portent donc aucun score. Rien ne permet de
les départager automatiquement - il faut le demander explicitement
(`--sans-score`, ou la case correspondante dans /admin).

Usage : python -m app.validation [seuil] [--sans-score]   (défaut : 0.9)
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import func, select, update

from app.db import SessionLocal
from app.models import (
    BudgetExercice,
    Decision,
    DotationBudgetaire,
    EngagementFinancier,
    Marche,
    MembreGouvernement,
    Nomination,
    Realisation,
)

# Tous les modèles portant à la fois un statut de validation et un score.
# `RepartitionBudgetaire` et `Projet` en sont absents faute de score : la
# première est saisie à la main, le second naît d'une décision humaine.
CIBLES = (
    (Decision, "décisions"),
    (Nomination, "nominations"),
    (EngagementFinancier, "engagements financiers"),
    (BudgetExercice, "budgets d'exercice"),
    (DotationBudgetaire, "dotations budgétaires"),
    (MembreGouvernement, "membres du gouvernement"),
    (Marche, "marchés publics"),
    (Realisation, "infrastructures"),
)

SEUIL_DEFAUT = 0.9


def compter_a_valider(db, modele, seuil: float) -> dict[str, int]:
    """Ce que le seuil emporterait pour ce modèle, sans rien modifier.

    C'est ce qui permet à /admin d'afficher l'effet AVANT de cliquer : valider
    en masse sans savoir combien de lignes basculent serait un pari.
    """

    def compte(*conditions) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(modele)
                .where(modele.statut_validation == "a_valider", *conditions)
            )
            or 0
        )

    return {
        "total": compte(),
        "au_seuil": compte(modele.score_confiance >= seuil),
        "sans_score": compte(modele.score_confiance.is_(None)),
    }


def valider_par_seuil(
    db,
    seuil: float = SEUIL_DEFAUT,
    *,
    modeles=None,
    inclure_sans_score: bool = False,
) -> dict:
    """Bascule en « valide » les `a_valider` dont le score atteint le seuil.

    `modeles` restreint aux modèles donnés (None = tous ceux de CIBLES).
    Reconstruit l'annuaire si des nominations ont été validées : sans cela, une
    nomination publiée n'apparaît ni dans l'annuaire ni sur la fiche de la
    personne, et l'administrateur devrait lancer `python -m app.annuaire` à la
    main - exactement la corvée que la plateforme promet d'éviter.
    """
    lignes = []
    total = nominations_validees = 0
    for modele, nom in CIBLES:
        if modeles is not None and modele not in modeles:
            continue
        condition = modele.score_confiance >= seuil
        avant = compter_a_valider(db, modele, seuil)
        if inclure_sans_score:
            condition = condition | modele.score_confiance.is_(None)
        valides = db.execute(
            update(modele)
            .where(modele.statut_validation == "a_valider", condition)
            .values(statut_validation="valide")
        ).rowcount
        restants = avant["total"] - valides
        total += valides
        if modele is Nomination:
            nominations_validees = valides
        lignes.append(
            {
                "cle": modele.__tablename__,
                "nom": nom,
                "valides": valides,
                "restants": restants,
                "sans_score": avant["sans_score"],
            }
        )
    db.commit()

    mandats = None
    if nominations_validees:
        from app.annuaire import consolider

        mandats = consolider(db)
    return {"lignes": lignes, "total": total, "mandats": mandats, "seuil": seuil}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    arguments = [a for a in sys.argv[1:] if not a.startswith("-")]
    seuil = float(arguments[0]) if arguments else SEUIL_DEFAUT
    inclure_sans_score = "--sans-score" in sys.argv
    with SessionLocal() as db:
        rapport = valider_par_seuil(db, seuil, inclure_sans_score=inclure_sans_score)
    sans_score = 0
    for ligne in rapport["lignes"]:
        print(f"{ligne['nom']} : {ligne['valides']} validée(s), {ligne['restants']} restante(s) à revoir")
        sans_score += ligne["sans_score"]
    print(f"\nTotal : {rapport['total']} entité(s) validée(s) au seuil {seuil}.")
    if inclure_sans_score and sans_score:
        print(
            f"Dont {sans_score} sans score de confiance (extraction déterministe) : "
            "validées sur demande explicite, aucun signal automatique ne les appuie."
        )
    if rapport["mandats"] is not None:
        print(f"Annuaire reconstruit : {rapport['mandats']} mandat(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
