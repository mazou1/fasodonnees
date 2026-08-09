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

import csv
import re
import unicodedata
from pathlib import Path

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
    texte = unicodedata.normalize("NFC", str(valeur or "")).translate(_APOSTROPHES)
    # \s couvre l'espace insécable une fois la chaîne normalisée en NFC
    return re.sub(r"\s+", " ", texte.replace(" ", " ")).strip().lower()


def _plier(valeur) -> str:
    """Comme `_normaliser`, accents et ponctuation en moins.

    La réécriture d'une page ne se limite pas à la typographie : le texte
    lui-même bouge. « Société industrielle burkinabé » est redevenue
    « burkinabè » entre deux versions du conseil du 2 juillet 2026 - un accent,
    et l'annuaire affichait deux fois le même directeur général.
    """
    nfkd = unicodedata.normalize("NFKD", _normaliser(valeur))
    sans_accent = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", sans_accent)).strip()


# Mots par lesquels un libellé plus long ne fait que SITUER le même poste :
# « Administrateur représentant l'État » → « … AU Conseil d'administration DE
# l'École… ». S'il commence autrement (« Directeur général » → « … ADJOINT »),
# c'est un autre poste, et les fondre fermerait un siège à tort.
_SUITE_QUI_SITUE = re.compile(r"^(?:au|aux|a|de|du|des|d|en|pour|dans|pres|aupres|chargee?)\b")


def _est_reformulation(cle_a: tuple, cle_b: tuple) -> bool:
    """Deux clés de nomination qui désignent la même nomination re-formulée.

    Même personne, même type, et un libellé qui n'est que l'autre précisé : le
    LLM repasse sur une page réécrite et tronque ou complète l'intitulé.
    « Administrateur civil, Administrateur représentant l'État » d'un côté, le
    même suivi de « au Conseil d'administration de l'École… » de l'autre - deux
    fois la même nomination, donc deux fois la même personne dans l'annuaire.
    """
    if cle_a[0] != "nomination" or cle_b[0] != "nomination":
        return False
    if cle_a[1] != cle_b[1] or cle_a[3] != cle_b[3]:
        return False
    court, long_ = sorted((_plier(cle_a[2]), _plier(cle_b[2])), key=len)
    if not court:
        return False
    if court == long_:
        return True  # ne différaient que par un accent ou une virgule
    return long_.startswith(court + " ") and bool(
        _SUITE_QUI_SITUE.match(long_[len(court) + 1 :])
    )


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
            # À statut égal, le libellé le PLUS COMPLET l'emporte : entre
            # « Administrateur représentant l'État » et le même suivi du conseil
            # d'administration concerné, c'est le second qui informe le lecteur.
            for e in sorted(entites, key=lambda x: (_RANG_STATUT.get(x.statut_validation, 3),
                                                    -len(getattr(x, "poste", "") or ""))):
                k = cle(e)
                if modele is Nomination:
                    # une reformulation n'ouvre pas une nouvelle entrée
                    k = next((autre for autre in meilleures if _est_reformulation(k, autre)), k)
                if k not in meilleures:
                    meilleures[k] = e
                    if e.document_id != reference:
                        e.document_id = reference
                        stats["rattachees"] += 1
                elif (
                    e.statut_validation == meilleures[k].statut_validation
                    or e.statut_validation == "a_valider"
                ):
                    # Même contenu, même statut : doublon, y compris entre deux
                    # « valide ». Supprimer n'efface aucun jugement humain - le
                    # même verdict subsiste sur l'entité conservée.
                    #
                    # Et « a_valider » face à un verdict n'est PAS une
                    # divergence : c'est l'absence d'avis. La réécriture d'une
                    # page par le gouvernement fait repasser l'extraction, qui
                    # produit toujours des `a_valider` - les garder comme des
                    # conflits remettait dans la file 86 nominations déjà
                    # validées à la main, à chaque réécriture.
                    if modele is Nomination:
                        reporter_mandats(e.id, meilleures[k].id)
                    db.delete(e)
                    stats["doublons_supprimes"] += 1
                else:
                    # Divergence réelle : validé d'un côté, rejeté de l'autre.
                    # Deux relectures humaines se contredisent, on ne tranche
                    # pas à leur place.
                    if e.document_id != reference:
                        e.document_id = reference
                        stats["rattachees"] += 1
                    stats["conflits_conserves"] += 1
    db.commit()
    return stats


# --- rattrapage des doublons DÉJÀ publiés ---------------------------------

# La règle de reformulation ci-dessus empêche les prochains doublons. Elle ne
# défait pas ceux d'hier : une nomination validée porte un VERDICT HUMAIN, que
# ce module ne supprime jamais tout seul. D'où la démarche maison, la même que
# pour les structures (app/fusion.py) : `doublons` propose, un humain relit,
# `doublons-appliquer` exécute - et rejette (trace conservée) au lieu de
# supprimer.
CSV_DOUBLONS = Path("nominations_doublons.csv")


def doublons_publies(db) -> list[dict]:
    """Paires de nominations validées qui décrivent la même nomination.

    Même compte rendu, même personne, et deux libellés dont l'un n'est que
    l'autre précisé. On propose de garder le plus complet.
    """
    from app.models import Document, Nomination, Personne

    lignes = db.execute(
        select(Nomination, Personne.nom_complet, Document.titre, Document.url)
        .join(Personne, Personne.id == Nomination.personne_id)
        .join(Document, Document.id == Nomination.document_id)
        .where(Nomination.statut_validation == "valide")
        .order_by(Nomination.document_id, Nomination.personne_id, Nomination.id)
    ).all()

    par_groupe: dict[tuple, list] = {}
    for nomination, personne, titre, url in lignes:
        par_groupe.setdefault(
            (nomination.document_id, nomination.personne_id, nomination.type), []
        ).append((nomination, personne, titre, url))

    propositions = []
    for membres in par_groupe.values():
        if len(membres) < 2:
            continue
        # le libellé le plus complet sert de référence, les autres s'y rattachent
        membres = sorted(membres, key=lambda m: -len(m[0].poste or ""))
        absorbes: set[int] = set()
        for i, (garde, personne, titre, url) in enumerate(membres):
            if garde.id in absorbes:
                continue
            for autre, *_ in membres[i + 1:]:
                if autre.id in absorbes:
                    continue
                if not _est_reformulation(_cle_nomination(garde), _cle_nomination(autre)):
                    continue
                absorbes.add(autre.id)
                propositions.append(
                    {
                        "motif": "identique" if _plier(garde.poste) == _plier(autre.poste)
                        else "precise",
                        "id_rejeter": autre.id,
                        "poste_rejeter": autre.poste,
                        "id_conserver": garde.id,
                        "poste_conserver": garde.poste,
                        "personne": personne,
                        "compte_rendu": titre,
                        "source_url": url,
                    }
                )
    return propositions


def proposer_doublons(db, chemin: Path = CSV_DOUBLONS) -> tuple[int, int]:
    """Écrit les paires à relire. Renvoie (total, pré-cochées).

    Les paires « identique » (mêmes mots, un accent ou une virgule d'écart)
    arrivent pré-cochées : il n'y a rien à arbitrer. Les « precise » restent
    vides - c'est là que le jugement compte.
    """
    propositions = doublons_publies(db)
    colonnes = ["appliquer", "motif", "id_rejeter", "poste_rejeter", "id_conserver",
                "poste_conserver", "personne", "compte_rendu", "source_url"]
    pre_cochees = 0
    with chemin.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colonnes)
        w.writeheader()
        for proposition in propositions:
            coche = "oui" if proposition["motif"] == "identique" else ""
            pre_cochees += coche == "oui"
            w.writerow({"appliquer": coche, **proposition})
    return len(propositions), pre_cochees


def appliquer_doublons(db, chemin: Path) -> tuple[int, int]:
    """Rejette les doublons cochés, puis reconstruit l'annuaire.

    Rejeter plutôt que supprimer : la ligne reste consultable dans /admin avec
    `?statut=rejete`, et l'API cesse de la publier. Renvoie (rejetées, mandats).
    """
    from sqlalchemy import update

    from app.annuaire import consolider
    from app.models import Nomination

    ids = []
    with chemin.open(newline="") as f:
        for ligne in csv.DictReader(f):
            if ligne["appliquer"].strip().lower() in ("oui", "o", "x", "1", "true"):
                ids.append(int(ligne["id_rejeter"]))
    if not ids:
        return 0, 0
    rejetees = db.execute(
        update(Nomination)
        .where(Nomination.id.in_(ids), Nomination.statut_validation == "valide")
        .values(statut_validation="rejete")
    ).rowcount
    db.commit()
    return rejetees, consolider(db)


def main() -> int:
    """Usage : python -m app.versions consolider
              python -m app.versions doublons            (écrit le CSV à relire)
              python -m app.versions doublons-appliquer <csv>"""
    import logging
    import sys

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    commande = sys.argv[1] if len(sys.argv) > 1 else ""
    with SessionLocal() as db:
        if commande == "consolider":
            stats = consolider_entites(db)
            print(
                f"{stats['rattachees']} entité(s) rattachée(s) à la version de référence, "
                f"{stats['doublons_supprimes']} doublon(s) non relu(s) supprimé(s), "
                f"{stats['conflits_conserves']} relecture(s) divergente(s) conservée(s)."
            )
        elif commande == "doublons":
            chemin = Path(sys.argv[2]) if len(sys.argv) > 2 else CSV_DOUBLONS
            total, pre_cochees = proposer_doublons(db, chemin)
            print(
                f"{total} paire(s) écrite(s) dans {chemin}, dont {pre_cochees} "
                "pré-cochée(s) (libellés identiques aux accents près).\n"
                "Relire, mettre 'oui' dans la colonne appliquer, puis : "
                f"python -m app.versions doublons-appliquer {chemin}"
            )
        elif commande == "doublons-appliquer" and len(sys.argv) > 2:
            rejetees, mandats = appliquer_doublons(db, Path(sys.argv[2]))
            print(f"{rejetees} nomination(s) rejetée(s), annuaire reconstruit : {mandats} mandat(s).")
        else:
            print(main.__doc__)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
