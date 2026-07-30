"""Tirets simples dans les libellés saisis à la main

Revision ID: e4a8b2f6c130
Revises: d7f3a1c5e920
Create Date: 2026-07-30 20:40:00.000000

La plateforme n'écrit plus de tiret cadratin. Restent en base les références
bibliographiques saisies dans l'admin (`source_libre`), du type
« Budget citoyen 2025, MINEFID (Tableau 2) - https://… ».

Seules ces colonnes-là sont reprises : ce sont NOS libellés. Les titres de
documents, le texte extrait et les décisions citent des sources officielles et
gardent leur ponctuation d'origine - une plateforme qui retouche ses archives
pour des raisons de style ne peut plus servir de preuve.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e4a8b2f6c130"
down_revision: Union[str, None] = "d7f3a1c5e920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("dotation_budgetaire", "repartition_budgetaire")


def upgrade() -> None:
    for table in TABLES:
        op.execute(
            f"""
            UPDATE {table}
               SET source_libre = replace(replace(source_libre, '—', '-'), '–', '-')
             WHERE source_libre LIKE '%—%' OR source_libre LIKE '%–%'
            """
        )


def downgrade() -> None:
    # Irréversible sans ambiguïté : un « - » d'origine et un « — » converti ne se
    # distinguent plus. On ne fait donc rien plutôt que de réintroduire des
    # cadratins là où il n'y en avait pas.
    pass
