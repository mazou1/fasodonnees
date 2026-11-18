"""Fiches de lecture des décisions constitutionnelles et des rapports de contrôle

Revision ID: e5b1c8d3a274
Revises: d9a3b5c7f142
Create Date: 2026-11-18 19:00:00.000000

Table `fiche_document` : une fiche par document du Conseil constitutionnel ou de
l'ASCE-LC - objet, auteur de la saisine ou entité contrôlée, sens de la décision,
résumé neutre. Passe par la file de validation.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5b1c8d3a274"
down_revision: Union[str, None] = "d9a3b5c7f142"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fiche_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("genre", sa.String(length=20), nullable=False),
        sa.Column("objet", sa.Text(), nullable=False),
        sa.Column("categorie", sa.String(length=40), nullable=False, server_default="autre"),
        sa.Column("partie", sa.String(length=500), nullable=True),
        sa.Column("issue", sa.String(length=40), nullable=True),
        sa.Column("resume", sa.Text(), nullable=False),
        sa.Column("points", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("date_document", sa.Date(), nullable=True),
        sa.Column("score_confiance", sa.Float(), nullable=True),
        sa.Column(
            "statut_validation", sa.String(length=20), nullable=False, server_default="a_valider"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_fiche_document_document_id"),
    )
    op.create_index("ix_fiche_document_categorie", "fiche_document", ["categorie"])
    op.create_index("ix_fiche_document_issue", "fiche_document", ["issue"])
    op.create_index("ix_fiche_document_statut_validation", "fiche_document", ["statut_validation"])


def downgrade() -> None:
    op.drop_table("fiche_document")
