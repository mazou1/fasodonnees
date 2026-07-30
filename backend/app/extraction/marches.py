"""Extraction des marchés attribués depuis le Quotidien des Marchés Publics.

Approche déterministe (pas de LLM) : les « Synthèses des résultats » du
Quotidien (DGCMEF) sont des tableaux à colonnes préservées par pdfplumber ;
`marches_tableau.extraire_marches` lit l'autorité contractante, l'objet, la
référence, l'attributaire retenu et son montant. Les résultats arrivent en
statut_validation='a_valider' — validation humaine avant publication.

⚠️ Le Quotidien REPUBLIE la même synthèse de résultats dans des numéros
successifs (une attribution vue dans 18 numéros d'affilée, constatée en
juillet 2026). Sans garde-fou, chaque republication crée une ligne de plus et
multiplie d'autant le total attribué à l'entreprise. Une attribution est donc
identifiée par son EMPREINTE (référence, attributaire, montant, objet) et
n'est enregistrée qu'à sa première parution.

Usage : python -m app.extraction.marches [max_docs]
        python -m app.extraction.marches renettoyer | dedoublonner
"""

from __future__ import annotations

import logging
import re
import sys
from datetime import date

from sqlalchemy import select

from app.db import SessionLocal
from app.extraction.marches_tableau import extraire_marches
from app.models import Document, Marche
from app.stockage import stockage


def _normaliser(valeur) -> str:
    return re.sub(r"\s+", " ", str(valeur or "")).strip().lower()


def empreinte(reference, attributaire, montant_fcfa, objet) -> str:
    """Identifie une ATTRIBUTION, indépendamment du numéro qui la publie.

    Deux lignes de même référence, même attributaire, même montant et même
    objet sont la même attribution republiée — jamais deux marchés distincts.
    La normalisation ne touche qu'à la casse et aux espaces : elle absorbe les
    variations de mise en page du PDF, pas une différence de fond.
    """
    return "|".join(
        [
            _normaliser(reference),
            _normaliser(attributaire),
            str(montant_fcfa if montant_fcfa is not None else ""),
            _normaliser(objet),
        ]
    )


def empreinte_de(m: Marche) -> str:
    return empreinte(m.reference, m.attributaire, m.montant_fcfa, m.objet)


def empreintes_connues(db) -> set[str]:
    lignes = db.execute(
        select(Marche.reference, Marche.attributaire, Marche.montant_fcfa, Marche.objet)
    ).all()
    return {empreinte(*ligne) for ligne in lignes}


def traiter_document(db, doc: Document, connues: set[str] | None = None) -> tuple[int, int]:
    """Extrait les marchés attribués d'un Quotidien depuis son PDF archivé.

    Retourne (ajoutés, republications ignorées). `connues` permet à l'appelant
    de porter l'ensemble des empreintes d'un document à l'autre plutôt que de
    le relire à chaque fois.
    """
    if not doc.fichier:
        return 0, 0
    from app.extraction.secteurs import secteur_de

    if connues is None:
        connues = empreintes_connues(db)

    ajoutes = ignores = 0
    with stockage.fichier_local(doc.fichier) as chemin:
        marches = extraire_marches(chemin)
    for m in marches:
        cle = empreinte(m.get("reference"), m["attributaire"], m["montant_fcfa"], m["objet"])
        if cle in connues:  # déjà parue dans un numéro précédent (ou plus haut
            ignores += 1    # dans ce même numéro)
            continue
        connues.add(cle)
        db.add(
            Marche(
                document_id=doc.id,
                autorite=m["autorite"],
                objet=m["objet"],
                reference=m.get("reference"),
                mode=m.get("mode"),
                attributaire=m["attributaire"],
                montant_fcfa=m["montant_fcfa"],
                secteur=secteur_de(m["objet"], m["autorite"]),
                region=m.get("region"),
                date_attribution=doc.date_publication,
                score_confiance=None,  # extraction déterministe, pas de score
                statut_validation="a_valider",
            )
        )
        ajoutes += 1
    db.commit()
    return ajoutes, ignores


def dedoublonner() -> int:
    """Supprime les republications déjà en base (stock antérieur au garde-fou).

    On garde la PREMIÈRE parution — la date d'attribution en est d'autant plus
    juste — et on lui reporte le statut `valide` si une des republications
    avait déjà été validée à la main : le travail du valideur n'est pas perdu.
    Les Quotidiens eux-mêmes restent archivés, seule la ligne dérivée part.
    """
    with SessionLocal() as db:
        groupes: dict[str, list[Marche]] = {}
        for m in db.scalars(select(Marche)):
            groupes.setdefault(empreinte_de(m), []).append(m)

        supprimes = valides_reportes = 0
        for lignes in groupes.values():
            if len(lignes) < 2:
                continue
            lignes.sort(key=lambda m: (m.date_attribution or date.max, m.id))
            garde, doublons = lignes[0], lignes[1:]
            if garde.statut_validation != "valide" and any(
                d.statut_validation == "valide" for d in doublons
            ):
                garde.statut_validation = "valide"
                valides_reportes += 1
            for d in doublons:
                db.delete(d)
                supprimes += 1
        db.commit()
        print(
            f"{supprimes} republication(s) supprimée(s) ; {valides_reportes} validation(s) "
            "humaine(s) reportée(s) sur la première parution."
        )
        if supprimes:
            print("Pensez à relancer : python -m app.attributaires consolider")
    return 0


def renettoyer_objets() -> int:
    """Nettoie objet ET attributaire des marchés en base (idempotent). Les
    lignes dont l'attributaire est cassé (objet débordé) sont démotées en
    'a_valider' pour revue plutôt que publiées avec un faux attributaire."""
    from app.extraction.marches_tableau import nettoyer_attributaire, nettoyer_objet
    from app.extraction.secteurs import secteur_de

    with SessionLocal() as db:
        marches = db.scalars(select(Marche)).all()
        obj_mod = att_mod = demotes = sect_mod = 0
        for m in marches:
            net_o = nettoyer_objet(m.objet)
            if net_o and net_o != m.objet:
                m.objet = net_o
                obj_mod += 1
            net_a = nettoyer_attributaire(m.attributaire)
            if net_a is None:  # attributaire inexploitable → à revoir
                if m.statut_validation == "valide":
                    m.statut_validation = "a_valider"
                    demotes += 1
            elif net_a != m.attributaire:
                m.attributaire = net_a
                att_mod += 1
            sect = secteur_de(m.objet, m.autorite)
            if sect != m.secteur:
                m.secteur = sect
                sect_mod += 1
        db.commit()
        print(
            f"{obj_mod} objet(s), {att_mod} attributaire(s), {sect_mod} secteur(s) mis à jour ; "
            f"{demotes} ligne(s) cassée(s) démotée(s) en a_valider."
        )
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) > 1 and sys.argv[1] == "renettoyer":
        return renettoyer_objets()
    if len(sys.argv) > 1 and sys.argv[1] == "dedoublonner":
        return dedoublonner()
    max_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    with SessionLocal() as db:
        deja = select(Marche.document_id).distinct().subquery()
        docs = db.scalars(
            select(Document)
            .where(
                Document.type_doc == "marche_public",
                Document.fichier.is_not(None),
                Document.id.not_in(select(deja.c.document_id)),
            )
            .order_by(Document.date_publication.desc().nulls_last())
            .limit(max_docs)
        ).all()
        if not docs:
            print("Aucun Quotidien en attente d'extraction.")
            return 0
        connues = empreintes_connues(db)
        total = republications = 0
        for doc in docs:
            n, ignores = traiter_document(db, doc, connues)
            total += n
            republications += ignores
            logging.info(
                "%s : %d marché(s) attribué(s), %d republication(s) ignorée(s)",
                doc.titre, n, ignores,
            )
        print(
            f"{len(docs)} Quotidien(s) : {total} marché(s) à valider dans /admin"
            f" ({republications} republication(s) ignorée(s))."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
