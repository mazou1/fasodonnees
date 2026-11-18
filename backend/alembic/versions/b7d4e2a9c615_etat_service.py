"""État des téléservices de l'annuaire « Services en ligne »

Revision ID: b7d4e2a9c615
Revises: a3e9d17c4b58
Create Date: 2026-11-18 16:00:00.000000

Table `etat_service` : une ligne par adresse de l'annuaire, réécrite par la
vérification quotidienne du worker. Elle porte l'état courant et la date de son
début, de quoi afficher « en panne depuis le… » sans conserver chaque passage.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d4e2a9c615"
down_revision: Union[str, None] = "a3e9d17c4b58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "etat_service",
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("statut", sa.String(length=20), nullable=False),
        sa.Column("code_http", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(length=300), nullable=True),
        sa.Column("depuis", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "verifie_le",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dernier_ok", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("url"),
    )


def downgrade() -> None:
    op.drop_table("etat_service")
