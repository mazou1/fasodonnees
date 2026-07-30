"""Validation en masse par seuil de confiance.

Complément CLI aux actions de l'admin : valide d'un coup toutes les entités
`a_valider` dont le score de confiance atteint le seuil. Celles qui restent
sous le seuil demeurent en file pour revue manuelle dans /admin.

⚠️ Une entité SANS score n'est jamais validée ici, et ce n'est pas un oubli :
les marchés publics sont extraits de façon déterministe (tableaux du Quotidien
DGCMEF, pas de LLM) et ne portent donc aucun score. Rien ne permet de les
départager automatiquement — ils relèvent de la relecture dans /admin.

Usage : python -m app.validation [seuil]   (défaut : 0.9)
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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    seuil = float(sys.argv[1]) if len(sys.argv) > 1 else 0.9
    inclure_sans_score = "--sans-score" in sys.argv
    with SessionLocal() as db:
        total_valides = sans_score = 0
        for modele, nom in CIBLES:
            condition = modele.score_confiance >= seuil
            if inclure_sans_score:
                # les marchés n'ont pas de score : sans cette option, « valider
                # tous les types » les laisserait indéfiniment en attente
                sans_score += db.scalar(
                    select(func.count())
                    .select_from(modele)
                    .where(
                        modele.statut_validation == "a_valider",
                        modele.score_confiance.is_(None),
                    )
                )
                condition = condition | modele.score_confiance.is_(None)
            valides = db.execute(
                update(modele)
                .where(modele.statut_validation == "a_valider", condition)
                .values(statut_validation="valide")
            ).rowcount
            restants = db.scalar(
                select(func.count())
                .select_from(modele)
                .where(modele.statut_validation == "a_valider")
            )
            total_valides += valides
            print(f"{nom} : {valides} validée(s), {restants} restante(s) à revoir")
        db.commit()
    print(f"\nTotal : {total_valides} entité(s) validée(s) au seuil {seuil}.")
    if inclure_sans_score and sans_score:
        print(
            f"Dont {sans_score} sans score de confiance (extraction déterministe) : "
            "validées sur demande explicite, aucun signal automatique ne les appuie."
        )
    print("Penser à consolider l'annuaire : python -m app.annuaire")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
