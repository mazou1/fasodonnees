"""Versions d'un même document : la source réécrit ses pages après publication.

`upsert_document` versionne au lieu d'écraser : même URL + hash différent = une
nouvelle ligne. C'est délibéré et précieux - cela **établit** que le
gouvernement retouche ses comptes rendus après coup. Constaté sur le Conseil des
ministres n°024 du 23 juillet 2026 : la page est passée de 66 571 à 71 390
octets entre le 24 et le 29 juillet, près de 5 Ko de contenu ajouté.

Mais toutes les versions ne doivent pas être traitées comme des documents
distincts, sinon :

- le LLM ré-extrait chaque version - appels gaspillés, entités en double à
  valider (15 décisions et 86 nominations deux fois pour le même conseil) ;
- le site liste le même conseil deux à quatre fois.

D'où une règle unique, appliquée partout : **la version de référence d'une URL
est la plus récemment collectée**. Les précédentes restent archivées et
consultables, mais ne portent ni l'extraction ni l'affichage.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import Document


def ids_versions_de_reference():
    """Sous-requête des `document.id` les plus récents pour chaque (source, url).

    `date_collecte` départage, `id` tranche les ex æquo - deux collectes dans la
    même transaction partageraient l'horodatage par défaut de PostgreSQL.
    """
    rang = (
        func.row_number()
        .over(
            partition_by=(Document.source_id, Document.url),
            order_by=(Document.date_collecte.desc(), Document.id.desc()),
        )
        .label("rang")
    )
    classement = select(Document.id.label("doc_id"), rang).subquery()
    return select(classement.c.doc_id).where(classement.c.rang == 1)


def historique_versions(db, doc: Document) -> list[Document]:
    """Toutes les versions d'un document, de la plus ancienne à la plus récente."""
    return list(
        db.scalars(
            select(Document)
            .where(Document.source_id == doc.source_id, Document.url == doc.url)
            .order_by(Document.date_collecte, Document.id)
        )
    )


# --- consolidation des entités réparties entre versions -------------------

# Une entité est « la même » d'une version à l'autre si son contenu l'est. Pas
# d'identifiant côté source : on se rabat sur les champs de fond, en ignorant la
# casse et les espaces - le gouvernement retouche justement la typographie.
def _cle_decision(d) -> tuple:
    return ("decision", _normaliser(d.ministere), d.type, _normaliser(d.objet))


def _cle_nomination(n) -> tuple:
    return ("nomination", n.personne_id, _normaliser(n.poste), n.type)


def _cle_engagement(e) -> tuple:
    return ("engagement", e.type, _normaliser(e.objet), e.montant_fcfa)


# Les réécritures de la source sont d'abord typographiques : apostrophe droite
# remplacée par une courbe, espace insécable insérée (`&nbsp;` vu dans le diff
# du n°024). Sans les unifier, « nomination d'un » et « nomination d’un »
# passaient pour deux décisions distinctes et le conseil en affichait le double.
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "‛": "'", "´": "'", "`": "'"})


def _normaliser(valeur) -> str:
    import re
    import unicodedata

    texte = unicodedata.normalize("NFC", str(valeur or "")).translate(_APOSTROPHES)
    # \s couvre l'espace insécable une fois la chaîne normalisée en NFC
    return re.sub(r"\s+", " ", texte.replace(" ", " ")).strip().lower()


# valide et rejete sont des DÉCISIONS HUMAINES : on ne les supprime jamais.
# Seul un doublon encore « a_valider » peut disparaître.
_RANG_STATUT = {"valide": 0, "rejete": 1, "a_valider": 2}


def consolider_entites(db) -> dict[str, int]:
    """Ramène sur la version de référence les entités extraites des versions
    précédentes, et supprime les doublons non encore relus.

    Sans cela, basculer l'affichage sur la version la plus récente rendrait
    invisible tout le travail de validation déjà fait sur les versions
    antérieures - et la file de `/admin` afficherait deux fois le même conseil.
    """
    from sqlalchemy import update

    from app.models import Decision, EngagementFinancier, Mandat, Nomination

    def reporter_mandats(doomed_id: int, garde_id: int) -> None:
        """Les mandats de l'annuaire pointent sur la nomination qui les ouvre ou
        les ferme. Supprimer un doublon sans reporter ces liens violerait la
        contrainte et, pire, effacerait des mandats reconstitués."""
        for colonne in (Mandat.nomination_debut_id, Mandat.nomination_fin_id):
            db.execute(
                update(Mandat).where(colonne == doomed_id).values({colonne: garde_id})
            )

    stats = {"rattachees": 0, "doublons_supprimes": 0, "conflits_conserves": 0}
    references = set(db.scalars(ids_versions_de_reference()))

    groupes: dict[tuple, list[int]] = {}
    for doc_id, source_id, url in db.execute(
        select(Document.id, Document.source_id, Document.url)
    ):
        groupes.setdefault((source_id, url), []).append(doc_id)

    for ids in groupes.values():
        if len(ids) < 2:
            continue
        reference = next((i for i in ids if i in references), None)
        if reference is None:
            continue
        for modele, cle in (
            (Decision, _cle_decision),
            (Nomination, _cle_nomination),
            (EngagementFinancier, _cle_engagement),
        ):
            entites = list(db.scalars(select(modele).where(modele.document_id.in_(ids))))
            # la meilleure entité de chaque contenu est conservée sur la référence
            meilleures: dict[tuple, object] = {}
            for e in sorted(entites, key=lambda x: _RANG_STATUT.get(x.statut_validation, 3)):
                k = cle(e)
                if k not in meilleures:
                    meilleures[k] = e
                    if e.document_id != reference:
                        e.document_id = reference
                        stats["rattachees"] += 1
                elif e.statut_validation == meilleures[k].statut_validation:
                    # même contenu, même statut : c'est un doublon, y compris
                    # entre deux « valide ». Supprimer n'efface aucun jugement
                    # humain - le même verdict subsiste sur l'entité conservée.
                    if modele is Nomination:
                        reporter_mandats(e.id, meilleures[k].id)
                    db.delete(e)
                    stats["doublons_supprimes"] += 1
                else:
                    # statuts DIVERGENTS sur le même contenu (validé d'un côté,
                    # rejeté de l'autre) : deux relectures se contredisent, on ne
                    # tranche pas à leur place.
                    if e.document_id != reference:
                        e.document_id = reference
                        stats["rattachees"] += 1
                    stats["conflits_conserves"] += 1
    db.commit()
    return stats


def main() -> int:
    """Usage : python -m app.versions consolider"""
    import logging
    import sys

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) < 2 or sys.argv[1] != "consolider":
        print(main.__doc__)
        return 1
    with SessionLocal() as db:
        stats = consolider_entites(db)
    print(
        f"{stats['rattachees']} entité(s) rattachée(s) à la version de référence, "
        f"{stats['doublons_supprimes']} doublon(s) non relu(s) supprimé(s), "
        f"{stats['conflits_conserves']} relecture(s) divergente(s) conservée(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
