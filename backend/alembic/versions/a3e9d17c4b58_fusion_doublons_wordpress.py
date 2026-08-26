"""Fusionner les documents WordPress dupliqués par changement d'URL

Revision ID: a3e9d17c4b58
Revises: f6c2d84b1057
Create Date: 2026-08-26 18:20:00.000000

Le 22 août 2026, gouvernement.gov.bf est passé des permaliens lisibles à la
forme « /?p=19635 ». L'identité d'un document reposant sur son URL, le site a
été recollecté en entier sous ces nouvelles adresses : 3 283 documents en
quatre jours, les 1 744 actualités du fonds en double, et 3 537 exemplaires
surnuméraires portant 298 décisions et 1 468 nominations déjà extraites.

Cette migration RAMÈNE ces exemplaires sous l'adresse d'origine plutôt que de
les supprimer : ce sont de vraies versions successives de la même publication,
et le versionnement est ce qui permet de détecter les republications
silencieuses. Une fois regroupées, `app.versions.consolider_entites` sait les
replier - c'est exactement ce à quoi elle sert.

Deux cas, dans cet ordre :

1. exemplaire dont le contenu est DÉJÀ archivé sous l'adresse d'origine
   (même empreinte) : il n'apporte rien. Ses entités sont rattachées à
   l'exemplaire conservé, puis il est supprimé. Sans ce rattachement
   préalable, 1 766 décisions et nominations disparaîtraient ;
2. exemplaire dont le contenu diffère : son URL est ramenée à l'adresse
   d'origine, il devient une version de plus.

L'adresse d'origine reste valable : le site la redirige en 301.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a3e9d17c4b58"
down_revision: Union[str, None] = "f6c2d84b1057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Groupes concernés : un même wp_id archivé sous plusieurs URL, avec l'adresse
# d'origine (celle du plus ancien document du groupe).
_GROUPES = """
    WITH groupes AS (
        SELECT source_id, meta->>'wp_id' AS wp, min(id) AS racine
          FROM document
         WHERE meta->>'wp_id' IS NOT NULL
         GROUP BY source_id, meta->>'wp_id'
        HAVING count(DISTINCT url) > 1
    )
    SELECT g.source_id, g.wp, d.url AS url_origine
      FROM groupes g JOIN document d ON d.id = g.racine
"""

# Dans chaque groupe, un seul exemplaire par empreinte : le plus ancien. Les
# autres sont surnuméraires. On ne touche jamais à ceux qui sont DÉJÀ sous
# l'adresse d'origine - l'historique légitime reste intact.
_SURNUMERAIRES_REDONDANTS = f"""
    WITH canonique AS ({_GROUPES}),
    classement AS (
        SELECT d.id, d.url, c.url_origine,
               row_number() OVER (
                   PARTITION BY d.source_id, d.meta->>'wp_id', d.hash_contenu
                   ORDER BY d.id
               ) AS rang
          FROM document d
          JOIN canonique c
            ON c.source_id = d.source_id AND c.wp = d.meta->>'wp_id'
    )
    SELECT id FROM classement WHERE rang > 1 AND url <> url_origine
"""

# Le jumeau conservé : même groupe, même empreinte, plus petit identifiant.
_JUMEAU = f"""
    WITH canonique AS ({_GROUPES})
    SELECT d.id AS surnumeraire, j.id AS jumeau
      FROM document d
      JOIN canonique c ON c.source_id = d.source_id AND c.wp = d.meta->>'wp_id'
      JOIN LATERAL (
            SELECT e.id FROM document e
             WHERE e.source_id = d.source_id
               AND e.meta->>'wp_id' = d.meta->>'wp_id'
               AND e.hash_contenu IS NOT DISTINCT FROM d.hash_contenu
             ORDER BY e.id LIMIT 1
      ) j ON TRUE
     WHERE d.id <> j.id AND d.url <> c.url_origine
"""

_ENTITES = ("decision", "nomination", "engagement_financier", "realisation", "marche")


def upgrade() -> None:
    # 1. rattacher les entités des exemplaires redondants à leur jumeau
    for table in _ENTITES:
        op.execute(
            f"""
            UPDATE {table} t
               SET document_id = p.jumeau
              FROM ({_JUMEAU}) p
             WHERE t.document_id = p.surnumeraire
            """
        )

    # 2. supprimer les exemplaires redondants, désormais sans rattachement
    op.execute(
        f"DELETE FROM document WHERE id IN (SELECT id FROM ({_SURNUMERAIRES_REDONDANTS}) s)"
    )

    # 3. ramener les exemplaires restants sous l'adresse d'origine : ils
    #    deviennent des versions de plus, que la consolidation saura replier
    op.execute(
        f"""
        UPDATE document d
           SET url = c.url_origine
          FROM ({_GROUPES}) c
         WHERE c.source_id = d.source_id
           AND c.wp = d.meta->>'wp_id'
           AND d.url <> c.url_origine
        """
    )


def downgrade() -> None:
    # Irréversible : les URL d'origine des exemplaires ramenés ne sont plus
    # distinguables de celles des versions légitimes, et les exemplaires
    # supprimés étaient par construction des copies conformes. Rétablir un état
    # « avant » demanderait de réinventer des données - une plateforme
    # d'archives ne le fait pas.
    pass
