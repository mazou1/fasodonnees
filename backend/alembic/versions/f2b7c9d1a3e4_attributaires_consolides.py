"""attributaires consolidés (entité derrière les raisons sociales des marchés)

Revision ID: f2b7c9d1a3e4
Revises: d5a2b6c7e8f9
Create Date: 2026-07-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2b7c9d1a3e4"
down_revision: Union[str, None] = "d5a2b6c7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attributaire",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nom", sa.String(length=400), nullable=False),
        sa.Column("nom_normalise", sa.String(length=400), nullable=False),
        sa.Column("canonique_id", sa.Integer(), nullable=True),
        sa.Column("nom_fige", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["canonique_id"], ["attributaire.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_attributaire_nom_normalise"), "attributaire", ["nom_normalise"], unique=False
    )
    op.create_index(
        op.f("ix_attributaire_canonique_id"), "attributaire", ["canonique_id"], unique=False
    )
    op.add_column("marche", sa.Column("attributaire_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_marche_attributaire_id"), "marche", ["attributaire_id"], unique=False
    )
    op.create_foreign_key(
        "fk_marche_attributaire", "marche", "attributaire", ["attributaire_id"], ["id"]
    )
    # rapprochement flou des raisons sociales (app/attributaires.py proposer)
    op.execute("CREATE INDEX IF NOT EXISTS ix_attributaire_nom_trgm "
               "ON attributaire USING gin (nom_normalise gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_attributaire_nom_trgm")
    op.drop_constraint("fk_marche_attributaire", "marche", type_="foreignkey")
    op.drop_index(op.f("ix_marche_attributaire_id"), table_name="marche")
    op.drop_column("marche", "attributaire_id")
    op.drop_index(op.f("ix_attributaire_canonique_id"), table_name="attributaire")
    op.drop_index(op.f("ix_attributaire_nom_normalise"), table_name="attributaire")
    op.drop_table("attributaire")
