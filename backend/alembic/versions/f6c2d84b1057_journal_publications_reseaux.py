"""Journal des publications sur les réseaux sociaux

Revision ID: f6c2d84b1057
Revises: e4a8b2f6c130
Create Date: 2026-08-26 10:00:00.000000

Table `publication` : ce que la plateforme a posté, où, quand, avec quel texte.

L'unicité (reseau, cle) porte toute la garantie anti-doublon de la diffusion :
sans elle, un worker relancé republierait le compte rendu du Conseil des
ministres à chaque cycle.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6c2d84b1057"
down_revision: Union[str, None] = "e4a8b2f6c130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "publication",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reseau", sa.String(length=20), nullable=False),
        sa.Column("cle", sa.String(length=80), nullable=False),
        sa.Column("genre", sa.String(length=20), nullable=True),
        sa.Column("statut", sa.String(length=20), nullable=False, server_default="publie"),
        sa.Column("tentatives", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("lien", sa.String(length=1000), nullable=True),
        sa.Column("post_id", sa.String(length=200), nullable=True),
        sa.Column("erreur", sa.Text(), nullable=True),
        sa.Column(
            "date_envoi",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reseau", "cle", name="uq_publication_reseau_cle"),
    )
    op.create_index("ix_publication_reseau", "publication", ["reseau"])
    op.create_index("ix_publication_cle", "publication", ["cle"])
    op.create_index("ix_publication_genre", "publication", ["genre"])
    op.create_index("ix_publication_statut", "publication", ["statut"])
    op.create_index("ix_publication_date_envoi", "publication", ["date_envoi"])


def downgrade() -> None:
    op.drop_table("publication")
