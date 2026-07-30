"""projets : dossiers de suivi annonce → attribution → livraison

Revision ID: a7d3e5f1b820
Revises: f2b7c9d1a3e4
Create Date: 2026-07-29 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d3e5f1b820"
down_revision: Union[str, None] = "f2b7c9d1a3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# les trois maillons rattachables à un dossier de suivi
MAILLONS = ("engagement_financier", "marche", "realisation")


def upgrade() -> None:
    op.create_table(
        "projet",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titre", sa.String(length=500), nullable=False),
        sa.Column("secteur", sa.String(length=60), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("statut_validation", sa.String(length=20), nullable=False,
                  server_default="a_valider"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projet_secteur"), "projet", ["secteur"], unique=False)
    op.create_index(
        op.f("ix_projet_statut_validation"), "projet", ["statut_validation"], unique=False
    )
    for table in MAILLONS:
        op.add_column(table, sa.Column("projet_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{table}_projet_id", table, ["projet_id"], unique=False)
        op.create_foreign_key(f"fk_{table}_projet", table, "projet", ["projet_id"], ["id"])


def downgrade() -> None:
    for table in MAILLONS:
        op.drop_constraint(f"fk_{table}_projet", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_projet_id", table_name=table)
        op.drop_column(table, "projet_id")
    op.drop_index(op.f("ix_projet_statut_validation"), table_name="projet")
    op.drop_index(op.f("ix_projet_secteur"), table_name="projet")
    op.drop_table("projet")
