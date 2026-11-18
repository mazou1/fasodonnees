"""Alertes personnalisées par Telegram

Revision ID: d9a3b5c7f142
Revises: c2f8a6d1e930
Create Date: 2026-11-18 18:00:00.000000

`abonnement` : ce qu'un lecteur suit (mot-clé, personne, institution).
`alerte_envoyee` : le journal qui empêche de lui envoyer deux fois la même
nouveauté ; il disparaît avec l'abonnement.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9a3b5c7f142"
down_revision: Union[str, None] = "c2f8a6d1e930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "abonnement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canal", sa.String(length=20), nullable=False, server_default="telegram"),
        sa.Column("destinataire", sa.String(length=100), nullable=False),
        sa.Column("genre", sa.String(length=20), nullable=False),
        sa.Column("valeur", sa.String(length=300), nullable=False),
        sa.Column("libelle", sa.String(length=300), nullable=False),
        sa.Column(
            "cree_le", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canal", "destinataire", "genre", "valeur", name="uq_abonnement"),
    )
    op.create_index("ix_abonnement_destinataire", "abonnement", ["destinataire"])
    op.create_table(
        "alerte_envoyee",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("abonnement_id", sa.Integer(), nullable=False),
        sa.Column("cle", sa.String(length=80), nullable=False),
        sa.Column(
            "date_envoi",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["abonnement_id"], ["abonnement.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("abonnement_id", "cle", name="uq_alerte_envoyee"),
    )
    op.create_index("ix_alerte_envoyee_abonnement_id", "alerte_envoyee", ["abonnement_id"])


def downgrade() -> None:
    op.drop_table("alerte_envoyee")
    op.drop_table("abonnement")
