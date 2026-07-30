"""marche.nature - distinguer attribution et présélection

Revision ID: c8e1f4a7b902
Revises: a7d3e5f1b820
Create Date: 2026-07-30 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8e1f4a7b902"
down_revision: Union[str, None] = "a7d3e5f1b820"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "marche",
        sa.Column("nature", sa.String(length=20), nullable=False,
                  server_default="attribution"),
    )
    op.create_index(op.f("ix_marche_nature"), "marche", ["nature"], unique=False)
    # Classement de l'existant. Les avis à manifestation d'intérêt se nomment
    # explicitement dans la référence, l'objet ou le mode - inutile de repasser
    # le LLM sur 2 629 lignes pour retrouver ce que le texte dit en toutes lettres.
    #
    # Mais nommer la procédure ne suffit PAS : la manifestation d'intérêt sert
    # aussi de mode de passation pour les prestations intellectuelles, et le
    # Quotidien publie alors une vraie attribution sous cette référence. Sur
    # 77 lignes ainsi repérées, 24 portaient un montant - dont une explicitement
    # « attribution provisoire ». Le montant tranche : une présélection retient
    # un candidat sans contrat, donc sans somme. Il n'y en a donc pas.
    op.execute(
        """
        WITH texte AS (
            SELECT id,
                   translate(
                     lower(coalesce(reference, '') || ' ' || coalesce(objet, '')
                           || ' ' || coalesce(mode, '')),
                     'éèêëàâîïôöûüç’', 'eeeeaaiioouuc'''
                   ) AS t
              FROM marche
             WHERE montant_fcfa IS NULL
        )
        UPDATE marche SET nature = 'preselection'
          FROM texte
         WHERE marche.id = texte.id
           AND (texte.t LIKE '%manifestation%interet%'
                OR texte.t LIKE '%prequalification%'
                OR texte.t LIKE '%pre-qualification%')
        """
    )
    # Les lignes chiffrées portant la même référence restent des attributions,
    # mais on les renvoie en revue humaine plutôt que de trancher à leur place -
    # même règle que `MarcheExtrait._preselection_chiffree_est_douteuse`. Elles
    # comptent dans les totaux publics : une erreur s'y verrait.
    op.execute(
        """
        WITH texte AS (
            SELECT id,
                   translate(
                     lower(coalesce(reference, '') || ' ' || coalesce(objet, '')
                           || ' ' || coalesce(mode, '')),
                     'éèêëàâîïôöûüç’', 'eeeeaaiioouuc'''
                   ) AS t
              FROM marche
             WHERE montant_fcfa IS NOT NULL
               AND statut_validation = 'valide'
        )
        UPDATE marche SET statut_validation = 'a_valider'
          FROM texte
         WHERE marche.id = texte.id
           AND texte.t LIKE '%manifestation%interet%'
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_marche_nature"), table_name="marche")
    op.drop_column("marche", "nature")
