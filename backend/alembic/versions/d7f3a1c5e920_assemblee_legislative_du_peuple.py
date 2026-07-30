"""L'ALT devient l'Assemblée législative du peuple

Revision ID: d7f3a1c5e920
Revises: c8e1f4a7b902
Create Date: 2026-07-30 20:10:00.000000

La Charte de la Révolution, adoptée le 27 mars 2026, a renommé l'Assemblée
législative de Transition (ALT) en Assemblée législative du peuple (ALP).

On ne touche QU'AUX ENTITÉS - le nom de la structure et le rôle courant du
président. Les archives gardent leur libellé d'origine : `document.titre`,
`document.texte_extrait` et `decision.objet` citent des textes officiels qui
disaient « Assemblée législative de Transition » au moment de leur publication,
et 326 occurrences de texte source seraient réécrites. Une plateforme qui
corrige rétroactivement ses sources ne peut plus servir de preuve.

Même raisonnement pour `mandat.poste` et `nomination.poste` : une nomination
prononcée sous l'ALT l'a été sous ce nom-là, et le rendre au nom d'aujourd'hui
antidaterait la réforme.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d7f3a1c5e920"
down_revision: Union[str, None] = "c8e1f4a7b902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ANCIEN = "Assemblée Législative de Transition (ALT)"
NOUVEAU = "Assemblée législative du peuple (ALP)"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE structure SET nom = '{NOUVEAU}'
         WHERE nom ILIKE '%législative de transition%'
        """
    )
    # regexp_replace insensible à la casse : le site officiel écrit tantôt
    # « de Transition », tantôt « de transition », et un replace() littéral
    # laisserait passer la variante qu'on n'a pas prévue.
    op.execute(
        """
        UPDATE depute
           SET role = regexp_replace(
                 role, 'Assembl[ée]e L?[ée]gislative de Transition',
                 'Assemblée législative du peuple', 'gi')
         WHERE role ILIKE '%législative de transition%'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE structure SET nom = '{ANCIEN}'
         WHERE nom = '{NOUVEAU}'
        """
    )
    op.execute(
        """
        UPDATE depute
           SET role = replace(role, 'Assemblée législative du peuple',
                              'Assemblée législative de Transition')
         WHERE role ILIKE '%législative du peuple%'
        """
    )
