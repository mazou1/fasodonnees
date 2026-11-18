"""Votes en séance plénière de l'Assemblée législative

Revision ID: c2f8a6d1e930
Revises: b7d4e2a9c615
Create Date: 2026-11-18 17:00:00.000000

Table `vote_plenier` : un texte soumis au vote, extrait d'un compte rendu de
plénière, avec ce que la source dit du scrutin. Passe par la file de validation
comme les décisions et les nominations.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2f8a6d1e930"
down_revision: Union[str, None] = "b7d4e2a9c615"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vote_plenier",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("intitule", sa.Text(), nullable=False),
        sa.Column("nature", sa.String(length=30), nullable=False, server_default="autre"),
        sa.Column("resultat", sa.String(length=20), nullable=False, server_default="adopte"),
        sa.Column("date_seance", sa.Date(), nullable=True),
        sa.Column("unanimite", sa.Boolean(), nullable=True),
        sa.Column("votants", sa.Integer(), nullable=True),
        sa.Column("pour", sa.Integer(), nullable=True),
        sa.Column("contre", sa.Integer(), nullable=True),
        sa.Column("abstentions", sa.Integer(), nullable=True),
        sa.Column("commission", sa.String(length=300), nullable=True),
        sa.Column("presente_par", sa.String(length=300), nullable=True),
        sa.Column("resume", sa.Text(), nullable=True),
        sa.Column("score_confiance", sa.Float(), nullable=True),
        sa.Column(
            "statut_validation", sa.String(length=20), nullable=False, server_default="a_valider"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vote_plenier_document_id", "vote_plenier", ["document_id"])
    op.create_index("ix_vote_plenier_nature", "vote_plenier", ["nature"])
    op.create_index("ix_vote_plenier_date_seance", "vote_plenier", ["date_seance"])
    op.create_index("ix_vote_plenier_statut_validation", "vote_plenier", ["statut_validation"])


def downgrade() -> None:
    op.drop_table("vote_plenier")
