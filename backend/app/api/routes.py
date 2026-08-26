from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Attributaire,
    BudgetExercice,
    Decision,
    Document,
    EngagementFinancier,
    Mandat,
    Marche,
    Nomination,
    Personne,
    Realisation,
    Source,
    Structure,
)
from app.versions import ids_versions_de_reference

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/health")
def health() -> dict:
    db_ok = False
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    """Agrégats pour le tableau de bord - contenus validés uniquement."""
    valide_d = Decision.statut_validation == "valide"
    valide_n = Nomination.statut_validation == "valide"
    annee = func.extract("year", Document.date_publication).label("annee")

    par_annee_d = dict(
        db.execute(
            select(annee, func.count()).join_from(Decision, Document).where(valide_d).group_by(annee)
        ).all()
    )
    par_annee_n = dict(
        db.execute(
            select(annee, func.count()).join_from(Nomination, Document).where(valide_n).group_by(annee)
        ).all()
    )
    annees = sorted(set(par_annee_d) | set(par_annee_n))

    par_type = db.execute(
        select(Decision.type, func.count()).where(valide_d).group_by(Decision.type).order_by(func.count().desc())
    ).all()

    # regroupement par structure canonique (fusion des renommages - cf. app/fusion.py)
    from sqlalchemy.orm import aliased

    canon = aliased(Structure)
    top_structures = db.execute(
        select(func.coalesce(canon.sigle, canon.nom), func.count())
        .join_from(Mandat, Structure, Mandat.structure_id == Structure.id)
        .join(canon, canon.id == func.coalesce(Structure.canonique_id, Structure.id))
        .group_by(canon.id)
        .order_by(func.count().desc())
        .limit(10)
    ).all()

    return {
        "totaux": {
            "decisions": db.scalar(select(func.count()).select_from(Decision).where(valide_d)),
            "nominations": db.scalar(select(func.count()).select_from(Nomination).where(valide_n)),
            "personnes": db.scalar(select(func.count(func.distinct(Mandat.personne_id)))),
            "mandats": db.scalar(select(func.count()).select_from(Mandat)),
            "comptes_rendus": db.scalar(
                select(func.count()).select_from(Document).where(Document.type_doc == "cr_conseil")
            ),
        },
        "par_annee": [
            {
                "annee": int(a),
                "decisions": int(par_annee_d.get(a, 0)),
                "nominations": int(par_annee_n.get(a, 0)),
            }
            for a in annees
        ],
        "decisions_par_type": [{"type": t, "n": int(n)} for t, n in par_type],
        "top_structures": [{"structure": s, "mandats": int(n)} for s, n in top_structures],
    }


@router.get("/assemblee")
def assemblee(db: Session = Depends(get_db)) -> dict:
    """Composition de l'Assemblée législative (synchronisée depuis le site officiel)."""
    from app.models import Depute

    deputes = db.scalars(
        select(Depute).where(Depute.actif.is_(True)).order_by(Depute.nom_complet)
    ).all()
    president = next((d for d in deputes if d.role), None)
    return {
        "stats": {
            "deputes": len(deputes),
            "legislature": deputes[0].legislature if deputes else None,
        },
        "president": {
            "nom_complet": president.nom_complet,
            "role": president.role,
            "photo_url": president.photo_url,
        }
        if president
        else None,
        "deputes": [
            {"nom_complet": d.nom_complet, "photo_url": d.photo_url, "role": d.role}
            for d in deputes
        ],
    }


@router.get("/gouvernement")
def gouvernement(db: Session = Depends(get_db)) -> dict:
    """Composition officielle du gouvernement (décret de composition), validée."""
    from app.models import MembreGouvernement

    membres = db.scalars(
        select(MembreGouvernement)
        .where(
            MembreGouvernement.statut_validation == "valide",
            MembreGouvernement.actif.is_(True),
        )
        .order_by(MembreGouvernement.ordre)
    ).all()
    doc = membres[0].document if membres else None
    # ordre -1 = Président du Faso (préside le Conseil, hors effectif gouvernement)
    gouv = [m for m in membres if m.ordre >= 0]
    femmes = sum(1 for m in gouv if m.genre == "F")

    def _sortie(m):
        return {
            "ordre": m.ordre,
            "civilite": m.civilite,
            "nom_complet": m.nom_complet,
            "poste": m.poste,
            "photo_url": m.photo_url,
        }

    return {
        "source": {
            "titre": doc.titre if doc else None,
            "date": doc.date_publication if doc else None,
            "url": doc.url if doc else None,
        },
        "stats": {"membres": len(gouv), "femmes": femmes},
        "president": next((_sortie(m) for m in membres if m.ordre == -1), None),
        "premier_ministre": next((_sortie(m) for m in gouv if m.ordre == 0), None),
        "ministres": [_sortie(m) for m in gouv if m.ordre > 0],
    }


class ActualiteOut(BaseModel):
    id: int
    source: str
    source_nom: str
    titre: str | None
    url: str
    date_publication: date | None
    resume: str | None
    type_doc: str


@router.get("/actualites", response_model=list[ActualiteOut])
def list_actualites(
    db: Session = Depends(get_db),
    source: str | None = Query(None, description="Slug de la source (lefaso, aib, presidence…)"),
    page: int = Query(1, ge=1),
    par_page: int = Query(20, ge=1, le=100),
):
    """Fil d'actualités agrégé : médias burkinabè (RSS) et communiqués officiels."""
    stmt = (
        select(Document)
        .join(Source)
        .where(Document.type_doc.in_(("article_presse", "communique")))
    )
    if source:
        stmt = stmt.where(Source.slug == source)
    stmt = (
        stmt.order_by(Document.date_publication.desc().nulls_last(), Document.id.desc())
        .offset((page - 1) * par_page)
        .limit(par_page)
    )
    resultats = []
    for d in db.scalars(stmt).all():
        resume = (d.meta or {}).get("resume")
        if resume:
            from app.extraction.texte import html_vers_texte

            resume = html_vers_texte(resume)[:280] or None
        resultats.append(
            ActualiteOut(
                id=d.id,
                source=d.source.slug,
                source_nom=d.source.nom,
                titre=d.titre,
                url=d.url,
                date_publication=d.date_publication,
                resume=resume,
                type_doc=d.type_doc,
            )
        )
    return resultats


@router.get("/recherche")
def recherche(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=2, description="Recherche globale sur tout le site"),
) -> dict:
    """Recherche fédérée : personnes, conseils des ministres, décisions,
    textes juridiques et actualités - top résultats par catégorie."""
    motif = f"%{q}%"

    personnes = db.execute(
        select(Personne.id, Personne.nom_complet, Personne.matricule)
        .where(Personne.nom_complet.ilike(motif))
        .order_by(Personne.nom_complet)
        .limit(8)
    ).all()

    def _docs(types: tuple[str, ...], n: int = 8):
        requete = func.websearch_to_tsquery("french", q)
        return db.execute(
            select(
                Document.id,
                Document.type_doc,
                Document.titre,
                Document.date_publication,
                Document.url,
                Document.meta,
                func.ts_headline(
                    "french",
                    func.coalesce(Document.texte_extrait, Document.titre, ""),
                    requete,
                    "MaxWords=28, MinWords=16, MaxFragments=1",
                ).label("extrait"),
            )
            .where(
                Document.type_doc.in_(types),
                text("document.tsv @@ websearch_to_tsquery('french', :q)"),
            )
            .order_by(
                text("ts_rank(document.tsv, websearch_to_tsquery('french', :q)) desc"),
                Document.date_publication.desc().nulls_last(),
            )
            .limit(n)
            .params(q=q)
        ).all()

    conseils = _docs(("cr_conseil",))
    textes = _docs(TYPES_TEXTES)
    actualites = _docs(("article_presse", "communique"))
    marches = _docs(("marche_public",), n=6)

    decisions = db.execute(
        select(Decision.id, Decision.objet, Decision.ministere, Decision.document_id, Document.date_publication)
        .join(Document)
        .where(
            Decision.statut_validation == "valide",
            Decision.objet.ilike(motif) | Decision.ministere.ilike(motif),
        )
        .order_by(Document.date_publication.desc().nulls_last())
        .limit(8)
    ).all()

    return {
        "q": q,
        "personnes": [
            {"id": p.id, "nom_complet": p.nom_complet, "matricule": p.matricule} for p in personnes
        ],
        "conseils": [
            {"id": d.id, "titre": d.titre, "date": d.date_publication, "extrait": d.extrait}
            for d in conseils
        ],
        "decisions": [
            {
                "id": d.id,
                "objet": d.objet,
                "ministere": d.ministere,
                "document_id": d.document_id,
                "date": d.date_publication,
            }
            for d in decisions
        ],
        "textes": [
            {
                "id": d.id,
                "type_doc": d.type_doc,
                "titre": d.titre,
                "reference": (d.meta or {}).get("reference"),
                "date": d.date_publication,
                "url_pdf": d.url,
                "extrait": d.extrait,
            }
            for d in textes
        ],
        "actualites": [
            {"id": d.id, "titre": d.titre, "date": d.date_publication, "url": d.url, "extrait": d.extrait}
            for d in actualites
        ],
        "marches": [
            {"id": d.id, "titre": d.titre, "date": d.date_publication, "url": d.url, "extrait": d.extrait}
            for d in marches
        ],
    }


class ConseilOut(BaseModel):
    id: int
    titre: str | None
    date_conseil: date | None
    url: str
    decisions: int
    nominations: int
    engagements: int
    # La source réécrit ses comptes rendus après publication : on archive chaque
    # version et on l'assume à l'affichage. `nb_versions` > 1 signale une
    # réécriture ; `modification_constatee_le` est la date à laquelle NOUS
    # l'avons constatée, pas celle de la retouche - le site ne la publie pas.
    nb_versions: int
    modification_constatee_le: date | None


class ConseilsPage(BaseModel):
    total: int
    conseils: list[ConseilOut]


# en dessous, la page collectée est une coquille sans compte rendu réel
# (même seuil que app/extraction/pdf_cr.py)
TEXTE_MINIMUM_CR = 500


def _versions_par_document(db: Session, ids: list[int]) -> dict[int, tuple[int, date | None]]:
    """Pour chaque document : nombre de versions archivées, et date à laquelle la
    dernière réécriture a été constatée (None s'il n'y en a qu'une)."""
    if not ids:
        return {}
    refs = db.execute(
        select(Document.id, Document.source_id, Document.url).where(Document.id.in_(ids))
    ).all()
    resultat: dict[int, tuple[int, date | None]] = {}
    for doc_id, source_id, url in refs:
        lignes = db.execute(
            select(func.count(), func.max(Document.date_collecte)).where(
                Document.source_id == source_id, Document.url == url
            )
        ).one()
        nb = int(lignes[0] or 1)
        vue_le = lignes[1].date() if nb > 1 and lignes[1] else None
        resultat[doc_id] = (nb, vue_le)
    return resultat


@router.get("/conseils", response_model=ConseilsPage)
def list_conseils(
    db: Session = Depends(get_db),
    q: str | None = Query(None, min_length=2, description="Recherche dans le titre ou le texte"),
    page: int = Query(1, ge=1),
    par_page: int = Query(20, ge=1, le=100),
):
    """Comptes rendus du Conseil des ministres, avec le volume de contenus validés extraits."""
    n_dec = (
        select(Decision.document_id, func.count().label("n"))
        .where(Decision.statut_validation == "valide")
        .group_by(Decision.document_id)
        .subquery()
    )
    n_nom = (
        select(Nomination.document_id, func.count().label("n"))
        .where(Nomination.statut_validation == "valide")
        .group_by(Nomination.document_id)
        .subquery()
    )
    n_eng = (
        select(EngagementFinancier.document_id, func.count().label("n"))
        .where(EngagementFinancier.statut_validation == "valide")
        .group_by(EngagementFinancier.document_id)
        .subquery()
    )
    base = (
        select(Document, n_dec.c.n, n_nom.c.n, n_eng.c.n)
        .outerjoin(n_dec, n_dec.c.document_id == Document.id)
        .outerjoin(n_nom, n_nom.c.document_id == Document.id)
        .outerjoin(n_eng, n_eng.c.document_id == Document.id)
        .where(
            Document.type_doc == "cr_conseil",
            # Une seule entrée par conseil : la version de référence. Sans ce
            # filtre, un conseil réécrit par la source apparaissait deux à
            # quatre fois (cf. app/versions.py).
            Document.id.in_(ids_versions_de_reference()),
            # on écarte les coquilles : une page sans compte rendu réel. Le test
            # porte sur le texte lui-même et non, comme avant, sur la présence
            # d'entités validées - sinon un conseil collecté depuis six jours et
            # dont l'extraction attend la relecture reste invisible.
            func.length(func.coalesce(Document.texte_extrait, "")) >= TEXTE_MINIMUM_CR,
        )
    )
    if q:
        base = base.where(Document.titre.ilike(f"%{q}%") | Document.texte_extrait.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    lignes = db.execute(
        base.order_by(Document.date_publication.desc().nulls_last(), Document.id.desc())
        .offset((page - 1) * par_page)
        .limit(par_page)
    ).all()

    versions = _versions_par_document(db, [d.id for d, *_ in lignes])
    return ConseilsPage(
        total=int(total or 0),
        conseils=[
            ConseilOut(
                id=d.id,
                titre=d.titre,
                date_conseil=d.date_publication,
                url=d.url,
                decisions=int(nd or 0),
                nominations=int(nn or 0),
                engagements=int(ne or 0),
                nb_versions=versions.get(d.id, (1, None))[0],
                modification_constatee_le=versions.get(d.id, (1, None))[1],
            )
            for d, nd, nn, ne in lignes
        ],
    )


@router.get("/conseils/{doc_id}")
def get_conseil(doc_id: int, db: Session = Depends(get_db)) -> dict:
    """Un conseil des ministres et tout son contenu validé, traçable."""
    d = db.get(Document, doc_id)
    if d is None or d.type_doc != "cr_conseil":
        raise HTTPException(404, "Compte rendu introuvable")
    decisions = db.scalars(
        select(Decision)
        .where(Decision.document_id == doc_id, Decision.statut_validation == "valide")
        .order_by(Decision.id)
    ).all()
    nominations = db.scalars(
        select(Nomination)
        .where(Nomination.document_id == doc_id, Nomination.statut_validation == "valide")
        .order_by(Nomination.id)
    ).all()
    engagements = db.scalars(
        select(EngagementFinancier)
        .where(
            EngagementFinancier.document_id == doc_id,
            EngagementFinancier.statut_validation == "valide",
        )
        .order_by(EngagementFinancier.montant_fcfa.desc().nulls_last())
    ).all()
    return {
        "id": d.id,
        "titre": d.titre,
        "date_conseil": d.date_publication,
        "url": d.url,
        "texte": d.texte_extrait,
        "pdf": bool(d.fichier and d.mime == "application/pdf"),
        "decisions": [
            {"id": x.id, "ministere": x.ministere, "type": x.type, "objet": x.objet}
            for x in decisions
        ],
        "nominations": [
            {
                "id": x.id,
                "personne": x.personne.nom_complet,
                "poste": x.poste,
                "structure": str(x.structure) if x.structure else None,
                "type": x.type,
            }
            for x in nominations
        ],
        "engagements": [
            {
                "id": x.id,
                "type": x.type,
                "objet": x.objet,
                "beneficiaire": x.beneficiaire,
                "montant_fcfa": x.montant_fcfa,
            }
            for x in engagements
        ],
    }


@router.get("/finances/stats")
def finances_stats(db: Session = Depends(get_db)) -> dict:
    """Agrégats financiers - engagements et budgets validés uniquement."""
    valide = EngagementFinancier.statut_validation == "valide"
    annee = func.extract("year", Document.date_publication).label("annee")

    par_annee = db.execute(
        select(annee, func.count(), func.sum(EngagementFinancier.montant_fcfa))
        .join_from(EngagementFinancier, Document)
        .where(valide)
        .group_by(annee)
        .order_by(annee)
    ).all()
    par_type = db.execute(
        select(EngagementFinancier.type, func.count(), func.sum(EngagementFinancier.montant_fcfa))
        .where(valide)
        .group_by(EngagementFinancier.type)
        .order_by(func.sum(EngagementFinancier.montant_fcfa).desc())
    ).all()
    par_ministere = db.execute(
        select(EngagementFinancier.ministere, func.sum(EngagementFinancier.montant_fcfa))
        .where(valide, EngagementFinancier.ministere.is_not(None))
        .group_by(EngagementFinancier.ministere)
        .order_by(func.sum(EngagementFinancier.montant_fcfa).desc())
        .limit(10)
    ).all()
    budgets = db.scalars(
        select(BudgetExercice)
        .where(
            BudgetExercice.statut_validation == "valide",
            BudgetExercice.recettes_fcfa.is_not(None)
            | BudgetExercice.depenses_fcfa.is_not(None),
        )
        .order_by(BudgetExercice.exercice, BudgetExercice.id)
    ).all()
    from app.models import DotationBudgetaire, RepartitionBudgetaire

    dotations = db.execute(
        select(
            DotationBudgetaire.exercice,
            DotationBudgetaire.ministere,
            DotationBudgetaire.montant_fcfa,
            DotationBudgetaire.source_libre,
        )
        .where(DotationBudgetaire.statut_validation == "valide")
        .order_by(DotationBudgetaire.exercice.desc(), DotationBudgetaire.montant_fcfa.desc())
    ).all()
    repartitions = db.execute(
        select(
            RepartitionBudgetaire.exercice,
            RepartitionBudgetaire.sens,
            RepartitionBudgetaire.libelle,
            RepartitionBudgetaire.montant_fcfa,
            RepartitionBudgetaire.source_libre,
        )
        .where(RepartitionBudgetaire.statut_validation == "valide")
        .order_by(RepartitionBudgetaire.exercice.desc(), RepartitionBudgetaire.montant_fcfa.desc())
    ).all()

    return {
        "totaux": {
            "engagements": db.scalar(
                select(func.count()).select_from(EngagementFinancier).where(valide)
            ),
            "montant_total_fcfa": int(
                db.scalar(select(func.sum(EngagementFinancier.montant_fcfa)).where(valide)) or 0
            ),
        },
        "par_annee": [
            {"annee": int(a), "engagements": int(n), "montant_fcfa": int(m or 0)}
            for a, n, m in par_annee
        ],
        "par_type": [
            {"type": t, "engagements": int(n), "montant_fcfa": int(m or 0)} for t, n, m in par_type
        ],
        "par_ministere": [
            {"ministere": mi, "montant_fcfa": int(m or 0)} for mi, m in par_ministere
        ],
        "budgets": [
            {
                "exercice": b.exercice,
                "type_loi": b.type_loi,
                "recettes_fcfa": b.recettes_fcfa,
                "depenses_fcfa": b.depenses_fcfa,
            }
            for b in budgets
        ],
        "dotations": [
            {"exercice": ex, "ministere": mi, "montant_fcfa": int(m), "source": src}
            for ex, mi, m, src in dotations
        ],
        "repartitions": [
            {"exercice": ex, "sens": s, "libelle": l, "montant_fcfa": int(m), "source": src}
            for ex, s, l, m, src in repartitions
        ],
    }


class EngagementOut(BaseModel):
    id: int
    document_url: str
    date_conseil: date | None
    ministere: str | None
    type: str
    objet: str
    beneficiaire: str | None
    montant_fcfa: int | None


@router.get("/finances/engagements", response_model=list[EngagementOut])
def list_engagements(
    db: Session = Depends(get_db),
    type: str | None = None,
    q: str | None = Query(None, min_length=2, description="Filtre sur objet/bénéficiaire/ministère"),
    tri: str = Query("montant", description="montant | date"),
    page: int = Query(1, ge=1),
    par_page: int = Query(20, ge=1, le=100),
):
    """Engagements financiers décidés en Conseil des ministres - validés uniquement."""
    stmt = (
        select(EngagementFinancier)
        .join(Document)
        .where(EngagementFinancier.statut_validation == "valide")
    )
    if type:
        stmt = stmt.where(EngagementFinancier.type == type)
    if q:
        motif = f"%{q}%"
        stmt = stmt.where(
            EngagementFinancier.objet.ilike(motif)
            | EngagementFinancier.beneficiaire.ilike(motif)
            | EngagementFinancier.ministere.ilike(motif)
        )
    if tri == "date":
        stmt = stmt.order_by(Document.date_publication.desc().nulls_last(), EngagementFinancier.id.desc())
    else:
        stmt = stmt.order_by(EngagementFinancier.montant_fcfa.desc().nulls_last())
    stmt = stmt.offset((page - 1) * par_page).limit(par_page)
    return [
        EngagementOut(
            id=e.id,
            document_url=e.document.url,
            date_conseil=e.document.date_publication,
            ministere=e.ministere,
            type=e.type,
            objet=e.objet,
            beneficiaire=e.beneficiaire,
            montant_fcfa=e.montant_fcfa,
        )
        for e in db.scalars(stmt).all()
    ]


class MandatOut(BaseModel):
    id: int
    personne_id: int
    personne: str
    matricule: str | None
    poste: str
    structure: str | None
    date_debut: date | None
    date_fin: date | None
    document_url: str | None


class AnnuairePage(BaseModel):
    total: int
    mandats: list[MandatOut]


@router.get("/annuaire", response_model=AnnuairePage)
def annuaire(
    db: Session = Depends(get_db),
    q: str | None = Query(None, min_length=2, description="Nom de personne ou de structure"),
    en_cours: bool = Query(False, description="Seulement les mandats sans date de fin"),
    page: int = Query(1, ge=1),
    par_page: int = Query(25, ge=1, le=100),
):
    """Annuaire de l'État : mandats issus des nominations validées."""
    stmt = select(Mandat).join(Personne).outerjoin(Structure)
    if q:
        motif = f"%{q}%"
        stmt = stmt.where(
            Personne.nom_complet.ilike(motif)
            | Structure.nom.ilike(motif)
            | Structure.sigle.ilike(motif)
            | Mandat.poste.ilike(motif)
        )
    if en_cours:
        stmt = stmt.where(Mandat.date_fin.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = (
        stmt.order_by(Mandat.date_debut.desc().nulls_last(), Mandat.id.desc())
        .offset((page - 1) * par_page)
        .limit(par_page)
    )
    resultats = []
    for m in db.scalars(stmt).all():
        doc = m.nomination_debut_id and db.get(Nomination, m.nomination_debut_id)
        resultats.append(
            MandatOut(
                id=m.id,
                personne_id=m.personne_id,
                personne=m.personne.nom_complet,
                matricule=m.personne.matricule,
                poste=m.poste,
                structure=str(m.structure) if m.structure else None,
                date_debut=m.date_debut,
                date_fin=m.date_fin,
                document_url=doc.document.url if doc else None,
            )
        )
    return AnnuairePage(total=int(total or 0), mandats=resultats)


class InstitutionOut(BaseModel):
    id: int
    nom: str
    sigle: str | None
    type: str
    groupe: str
    nb_agents: int
    # intitulés successifs regroupés sous ce portefeuille, du plus récent au
    # plus ancien ; `nom` reprend le premier. Un seul élément = pas de renommage.
    intitules: list[str] = []
    # vrai si `nom` vient du gouvernement en vigueur, faux s'il est seulement
    # le dernier intitulé attesté en nomination
    intitule_officiel: bool = False


class InstitutionsPage(BaseModel):
    total_institutions: int
    total_agents: int
    institutions: list[InstitutionOut]


def _intitules_courants(db: Session) -> dict[str, str]:
    """Intitulé en vigueur de chaque portefeuille, d'après le trombinoscope
    officiel du gouvernement - les noms reconstitués depuis les nominations
    retardent d'un remaniement (« Défense et Anciens Combattants » pour ce qui
    est aujourd'hui le ministère de la Guerre et de la Défense patriotique)."""
    from app.annuaire_taxonomie import intitule_officiel, portefeuille
    from app.models import MembreGouvernement

    courants: dict[str, str] = {}
    postes = db.execute(
        select(MembreGouvernement.poste).where(
            MembreGouvernement.actif.is_(True),
            MembreGouvernement.statut_validation == "valide",
        )
    ).scalars()
    for poste in postes:
        nom = intitule_officiel(poste)
        if not nom:
            continue
        cle = portefeuille(nom, "ministere")
        if cle:
            courants[cle] = nom
    return courants


def _part_conseil_administration(db: Session) -> dict[int, float]:
    """Pour chaque structure canonique nommée « Ministère … » mais portant un
    sigle, la part de ses mandats qui sont des sièges au conseil
    d'administration de l'entité du sigle. À 100 %, la structure EST cette
    entité et non le ministère - voir `annuaire_taxonomie.type_institution`.

    Le ratio porte sur le groupe canonique, puisque c'est lui que l'annuaire
    affiche : le mesurer sur une variante fusionnée le rendrait aveugle."""
    from sqlalchemy.orm import aliased

    canon = aliased(Structure)
    cid = func.coalesce(Structure.canonique_id, Structure.id)
    est_ca = or_(
        Mandat.poste.ilike("%conseil d%administration%"),
        Mandat.poste.ilike(func.concat("%", canon.sigle, "%")),
    )
    rows = db.execute(
        select(
            canon.id,
            func.count().label("n"),
            func.sum(case((est_ca, 1), else_=0)).label("ca"),
        )
        .select_from(Mandat)
        .join(Structure, Structure.id == Mandat.structure_id)
        .join(canon, canon.id == cid)
        .where(canon.sigle.is_not(None), canon.nom.ilike("minist%"))
        .group_by(canon.id)
    ).all()
    return {r.id: (r.ca or 0) / r.n for r in rows if r.n}


@router.get("/annuaire/institutions", response_model=InstitutionsPage)
def annuaire_institutions(
    db: Session = Depends(get_db),
    q: str | None = Query(None, min_length=2, description="Nom ou sigle d'institution"),
):
    """Index des institutions de l'État (structures canoniques ayant au moins un
    agent recensé), avec type déduit et effectif - pour naviguer l'annuaire par
    institution plutôt qu'en liste plate.

    Les intitulés successifs d'un même ministère (renommages de remaniement)
    sont regroupés sous une seule entrée, celle du dernier intitulé en date.
    """
    from sqlalchemy.orm import aliased

    from app.annuaire_taxonomie import (
        GROUPES_INSTITUTION,
        meme_intitule,
        nom_region_affiche,
        portefeuille,
        region_officielle,
        sigle_fiable,
        type_institution,
    )

    canon = aliased(Structure)
    cid = func.coalesce(Structure.canonique_id, Structure.id)
    rows = db.execute(
        select(
            canon.id,
            canon.nom,
            canon.sigle,
            # effectif = personnes DISTINCTES actuellement en fonction ici
            func.count(func.distinct(
                case((Mandat.date_fin.is_(None), Mandat.personne_id))
            )).label("n"),
            func.max(Mandat.date_debut).label("dernier"),
        )
        .select_from(Mandat)
        .join(Structure, Structure.id == Mandat.structure_id)
        .join(canon, canon.id == cid)
        .group_by(canon.id, canon.nom, canon.sigle)
    ).all()

    # regroupement des intitulés successifs ; hors ministère, une structure =
    # une entrée (clé propre à son id)
    part_ca = _part_conseil_administration(db)
    types = {r.id: type_institution(r.nom, r.sigle, part_ca.get(r.id)) for r in rows}
    groupes: dict[str, list] = {}
    for r in rows:
        cle = portefeuille(r.nom, types[r.id]) or f"#{r.id}"
        groupes.setdefault(cle, []).append(r)

    # effectifs par portefeuille : une même personne peut servir sous deux
    # intitulés successifs, la somme des effectifs la compterait deux fois
    agents_par_struct: dict[int, set[int]] = {}
    if any(len(v) > 1 for v in groupes.values()):
        for sid, pid in db.execute(
            select(cid, Mandat.personne_id)
            .distinct()
            .select_from(Mandat)
            .join(Structure, Structure.id == Mandat.structure_id)
            .join(canon, canon.id == cid)
            .where(canon.nom.ilike("minist%"), Mandat.date_fin.is_(None))
        ).all():
            agents_par_struct.setdefault(sid, set()).add(pid)

    libelles = dict(GROUPES_INSTITUTION)
    courants = _intitules_courants(db)
    institutions = []
    for cle, variantes in groupes.items():
        # à défaut d'intitulé officiel, le plus récemment attesté en nomination
        variantes.sort(key=lambda r: (r.dernier or date.min, r.n), reverse=True)
        principal = variantes[0]
        t = types[principal.id]
        intitules = [v.nom for v in variantes]
        officiel = courants.get(cle)
        if officiel:
            intitules = [officiel] + [
                n for n in intitules if not meme_intitule(n, officiel)
            ]
        # région renommée par la réforme 2025 : afficher le nom officiel actuel
        # avec l'ancien en rappel (« Région Liptako (ex-Sahel) »)
        if t == "territoriale" and region_officielle(principal.nom):
            intitules = [nom_region_affiche(principal.nom)]
        if len(variantes) > 1:
            agents = set()
            for v in variantes:
                agents |= agents_par_struct.get(v.id, set())
            nb = len(agents)
        else:
            nb = int(principal.n)
        institutions.append(
            InstitutionOut(
                id=principal.id,
                nom=intitules[0],
                sigle=(
                    principal.sigle
                    if sigle_fiable(principal.nom, principal.sigle, part_ca.get(principal.id))
                    else None
                ),
                type=t,
                groupe=libelles.get(t, "Autres"),
                nb_agents=nb,
                intitules=intitules,
                intitule_officiel=bool(officiel),
            )
        )
    if q:
        terme = q.lower()
        institutions = [
            i for i in institutions
            if any(terme in n.lower() for n in i.intitules)
            or (i.sigle and terme in i.sigle.lower())
        ]
    # tri : effectif décroissant, puis nom
    institutions.sort(key=lambda i: (-i.nb_agents, i.nom.lower()))
    return InstitutionsPage(
        total_institutions=len(institutions),
        total_agents=sum(i.nb_agents for i in institutions),
        institutions=institutions,
    )


class AgentOut(BaseModel):
    personne_id: int
    personne: str
    matricule: str | None
    poste: str | None
    date_debut: date | None
    date_fin: date | None = None
    en_fonction: bool = True
    document_url: str | None


class CategorieAgents(BaseModel):
    categorie: str
    agents: list[AgentOut]


class InstitutionDetail(BaseModel):
    id: int
    nom: str
    sigle: str | None
    type: str
    nb_agents: int  # personnes distinctes actuellement en fonction
    nb_anciens: int = 0  # personnes distinctes n'ayant plus de mandat en cours ici
    categories: list[CategorieAgents]
    intitules: list[str] = []
    intitule_officiel: bool = False


@router.get("/annuaire/institutions/{struct_id}", response_model=InstitutionDetail)
def annuaire_institution(struct_id: int, db: Session = Depends(get_db)):
    """Agents d'une institution (structure canonique), regroupés par catégorie
    de fonction."""
    from app.annuaire_taxonomie import (
        CATEGORIES_FONCTION,
        categorie_fonction,
        meme_intitule,
        nom_region_affiche,
        portefeuille,
        region_officielle,
        sigle_fiable,
        type_institution,
    )

    inst = db.get(Structure, struct_id)
    if inst is None:
        raise HTTPException(status_code=404, detail="Institution inconnue")
    # la structure de référence est la canonique (si struct_id en est une variante)
    if inst.canonique_id:
        inst = db.get(Structure, inst.canonique_id) or inst

    cid = func.coalesce(Structure.canonique_id, Structure.id)
    # un ministère renommé s'étale sur plusieurs structures : on réunit tous les
    # intitulés du portefeuille, le plus récent servant de titre
    ids = [inst.id]
    intitules = [inst.nom]
    officiel = None
    part_ca = _part_conseil_administration(db)
    # région renommée (réforme 2025) : afficher le nom officiel actuel
    if region_officielle(inst.nom):
        intitules = [nom_region_affiche(inst.nom)]
    cle = portefeuille(inst.nom, type_institution(inst.nom, inst.sigle, part_ca.get(inst.id)))
    if cle:
        variantes = db.execute(
            select(
                Structure.id,
                Structure.nom,
                Structure.sigle,
                func.max(Mandat.date_debut).label("dernier"),
                func.count(Mandat.id).label("n"),
            )
            .select_from(Structure)
            .join(Mandat, Mandat.structure_id == Structure.id)
            .where(Structure.canonique_id.is_(None), Structure.nom.ilike("minist%"))
            .group_by(Structure.id, Structure.nom, Structure.sigle)
        ).all()
        fratrie = [
            v for v in variantes
            if portefeuille(v.nom, type_institution(v.nom, v.sigle, part_ca.get(v.id))) == cle
        ]
        if len(fratrie) > 1:
            fratrie.sort(key=lambda v: (v.dernier or date.min, v.n), reverse=True)
            ids = [v.id for v in fratrie]
            intitules = [v.nom for v in fratrie]
            inst = db.get(Structure, fratrie[0].id) or inst
        # le trombinoscope officiel prime sur le nom reconstitué des nominations
        officiel = _intitules_courants(db).get(cle)
        if officiel:
            intitules = [officiel] + [
                n for n in intitules if not meme_intitule(n, officiel)
            ]

    rows = db.execute(
        select(
            Mandat.personne_id,
            Personne.nom_complet,
            Personne.matricule,
            Mandat.poste,
            Mandat.date_debut,
            Mandat.date_fin,
            Document.url,
        )
        .select_from(Mandat)
        .join(Personne, Personne.id == Mandat.personne_id)
        .join(Structure, Structure.id == Mandat.structure_id)
        .outerjoin(Nomination, Nomination.id == Mandat.nomination_debut_id)
        .outerjoin(Document, Document.id == Nomination.document_id)
        .where(cid.in_(ids))
        # en poste d'abord, puis du plus récent au plus ancien
        .order_by(
            Mandat.date_fin.is_(None).desc(),
            Mandat.date_debut.desc().nulls_last(),
            Personne.nom_complet,
        )
    ).all()

    groupes: dict[str, list[AgentOut]] = {}
    en_poste: set[int] = set()
    anciens: set[int] = set()
    for r in rows:
        if r.date_fin is None:
            en_poste.add(r.personne_id)
        else:
            anciens.add(r.personne_id)
        cat = categorie_fonction(r.poste)
        groupes.setdefault(cat, []).append(
            AgentOut(
                personne_id=r.personne_id,
                personne=r.nom_complet,
                matricule=r.matricule,
                poste=r.poste,
                date_debut=r.date_debut,
                date_fin=r.date_fin,
                en_fonction=r.date_fin is None,
                document_url=r.url,
            )
        )
    categories = [
        CategorieAgents(categorie=c, agents=groupes[c])
        for c in CATEGORIES_FONCTION
        if c in groupes
    ]
    # « ancien » = plus aucun mandat en cours dans l'institution
    anciens -= en_poste
    return InstitutionDetail(
        id=inst.id,
        nom=intitules[0],
        sigle=inst.sigle if sigle_fiable(inst.nom, inst.sigle, part_ca.get(inst.id)) else None,
        type=type_institution(inst.nom, inst.sigle, part_ca.get(inst.id)),
        nb_agents=len(en_poste),
        nb_anciens=len(anciens),
        categories=categories,
        intitules=intitules,
        intitule_officiel=bool(officiel),
    )


class FichePersonne(BaseModel):
    id: int
    nom_complet: str
    matricule: str | None
    en_fonction: bool
    fonctions: list[dict]
    homonymes: list[dict]


@router.get("/personnes/{personne_id}", response_model=FichePersonne)
def fiche_personne(personne_id: int, db: Session = Depends(get_db)):
    """Fiche d'une personnalité publique : son parcours de fonctions, chaque
    entrée reliée au compte rendu de nomination."""
    p = db.get(Personne, personne_id)
    if p is None:
        raise HTTPException(404, "Personne introuvable")
    homonymes = [
        {"id": h.id, "matricule": h.matricule}
        for h in db.scalars(
            select(Personne).where(
                Personne.nom_normalise == p.nom_normalise, Personne.id != p.id
            )
        ).all()
    ]
    mandats = db.scalars(
        select(Mandat)
        .where(Mandat.personne_id == personne_id)
        .order_by(Mandat.date_fin.is_(None).desc(), Mandat.date_debut.desc().nulls_last())
    ).all()
    fonctions = []
    for m in mandats:
        nom_deb = m.nomination_debut_id and db.get(Nomination, m.nomination_debut_id)
        doc = nom_deb.document if nom_deb else None
        fonctions.append(
            {
                "poste": m.poste,
                "structure": str(m.structure) if m.structure else None,
                "date_debut": m.date_debut.isoformat() if m.date_debut else None,
                "date_fin": m.date_fin.isoformat() if m.date_fin else None,
                "nomination_id": m.nomination_debut_id,
                "source_titre": doc.titre if doc else None,
                "source_url": doc.url if doc else None,
                "source_id": doc.id if doc and doc.type_doc == "cr_conseil" else None,
            }
        )
    return FichePersonne(
        id=p.id,
        nom_complet=p.nom_complet,
        matricule=p.matricule,
        en_fonction=any(m.date_fin is None for m in mandats),
        fonctions=fonctions,
        homonymes=homonymes,
    )


class SourceOut(BaseModel):
    slug: str
    nom: str
    url_base: str
    type: str
    cadence: str
    actif: bool

    model_config = {"from_attributes": True}


@router.get("/sources", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    return db.scalars(select(Source).order_by(Source.slug)).all()


@router.get("/sources/etat")
def sources_etat(db: Session = Depends(get_db)) -> dict:
    """Fraîcheur des collectes, sur deux axes distincts :

    - `muettes` : le collecteur ne passe plus (dernier run réussi trop ancien) ;
    - `taries` : il passe et réussit, mais la source ne publie plus rien de neuf.

    La seconde est celle qui échappe à un tableau de bord classique : tous les
    voyants sont verts et le contenu a pourtant des semaines.
    """
    from app.ingestion.surveillance import etat_sources

    etats = etat_sources(db)
    return {
        "muettes": sum(1 for e in etats if e["muette"]),
        "taries": sum(1 for e in etats if e["tarie"]),
        "sources": etats,
    }


class DocumentOut(BaseModel):
    id: int
    source: str
    source_nom: str | None = None
    url: str
    titre: str | None
    type_doc: str
    date_publication: date | None
    date_collecte: datetime
    pdf: bool = False

    @classmethod
    def from_row(cls, d: Document) -> "DocumentOut":
        return cls(
            id=d.id,
            source=d.source.slug,
            source_nom=d.source.nom,
            url=d.url,
            titre=d.titre,
            type_doc=d.type_doc,
            date_publication=d.date_publication,
            date_collecte=d.date_collecte,
            pdf=bool(d.fichier and d.mime == "application/pdf"),
        )


class DocumentsPage(BaseModel):
    total: int
    documents: list[DocumentOut]
    types: list[dict]
    sources: list[dict]


# La bibliothèque « Documents » ne montre que des documents officiels : on
# écarte les actualités (articles de presse, communiqués - elles ont leur
# propre page), les traductions de CR en langues nationales (doublons/junk)
# et les Quotidiens des Marchés Publics (bulletins-source, exposés via /marches ;
# le PDF reste accessible par lien direct depuis chaque marché).
TYPES_HORS_DOCUMENTS = ("article_presse", "communique", "cr_conseil_traduction", "marche_public")


@router.get("/documents", response_model=DocumentsPage)
def list_documents(
    db: Session = Depends(get_db),
    source: str | None = None,
    type_doc: str | None = None,
    q: str | None = Query(None, min_length=2, description="Recherche plein texte (français)"),
    page: int = Query(1, ge=1),
    par_page: int = Query(20, ge=1, le=100),
):
    """Bibliothèque des documents officiels archivés, avec facettes types/sources
    (hors actualités et traductions, cf. TYPES_HORS_DOCUMENTS)."""

    def _filtre(stmt, avec_source=True, avec_type=True):
        stmt = stmt.where(Document.type_doc.not_in(TYPES_HORS_DOCUMENTS))
        if source and avec_source:
            stmt = stmt.where(Source.slug == source)
        if type_doc and avec_type:
            stmt = stmt.where(Document.type_doc == type_doc)
        if q:
            stmt = stmt.where(
                text("document.tsv @@ websearch_to_tsquery('french', :q)")
            ).params(q=q)
        return stmt

    base = _filtre(select(Document).join(Source))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    docs = db.scalars(
        base.order_by(Document.date_publication.desc().nulls_last(), Document.id.desc())
        .offset((page - 1) * par_page)
        .limit(par_page)
    ).all()

    # facettes : chaque dimension est comptée sous les AUTRES filtres actifs
    types = db.execute(
        _filtre(
            select(Document.type_doc, func.count()).join(Source), avec_type=False
        ).group_by(Document.type_doc).order_by(func.count().desc())
    ).all()
    sources = db.execute(
        _filtre(
            select(Source.slug, Source.nom, func.count()).join_from(Document, Source),
            avec_source=False,
        ).group_by(Source.slug, Source.nom).order_by(func.count().desc())
    ).all()

    return DocumentsPage(
        total=int(total or 0),
        documents=[DocumentOut.from_row(d) for d in docs],
        types=[{"type_doc": t, "n": int(n)} for t, n in types],
        sources=[{"slug": s, "nom": nom, "n": int(n)} for s, nom, n in sources],
    )


class DocumentDetail(DocumentOut):
    texte_extrait: str | None
    statut_extraction: str
    meta: dict | None


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(Document, doc_id)
    if d is None:
        raise HTTPException(404, "Document introuvable")
    base = DocumentOut.from_row(d).model_dump()
    return DocumentDetail(
        **base,
        texte_extrait=d.texte_extrait,
        statut_extraction=d.statut_extraction,
        meta=d.meta,
    )


@router.get("/contexte/{genre}/{entite_id}")
def contexte(genre: str, entite_id: int, db: Session = Depends(get_db)) -> dict:
    """« La source en contexte » : la phrase du compte rendu d'où provient une
    nomination ou un engagement, avec les ancres surlignées (<mark>)."""
    from app.extraction.contexte import localiser

    if genre == "nomination":
        n = db.get(Nomination, entite_id)
        if n is None:
            raise HTTPException(404, "Nomination introuvable")
        doc = n.document
        ancres = [(n.matricule or "", True), (n.personne.nom_complet, False)]
    elif genre == "engagement":
        e = db.get(EngagementFinancier, entite_id)
        if e is None:
            raise HTTPException(404, "Engagement introuvable")
        doc = e.document
        ancres = [(e.beneficiaire or "", False)]
    elif genre == "marche":
        from app.models import Marche

        m = db.get(Marche, entite_id)
        if m is None:
            raise HTTPException(404, "Marché introuvable")
        doc = m.document
        ancres = [(m.attributaire or "", False)]
    else:
        raise HTTPException(404, "Type de contexte inconnu")

    return {
        "passage": localiser(doc.texte_extrait, ancres),
        "document": {"id": doc.id, "titre": doc.titre, "url": doc.url},
    }


@router.get("/documents/{doc_id}/fichier")
def get_document_fichier(doc_id: int, db: Session = Depends(get_db)):
    """Sert le fichier archivé d'un document (PDF officiel téléchargé à la collecte).

    En stockage objet, on **redirige** vers une URL présignée plutôt que de
    faire transiter les octets : le corpus pèse plusieurs gigaoctets et l'API
    n'a pas à devenir un serveur de fichiers.
    """
    from fastapi.responses import FileResponse, RedirectResponse

    from app.stockage import CleInvalide, stockage

    d = db.get(Document, doc_id)
    if d is None or not d.fichier:
        raise HTTPException(404, "Fichier introuvable")
    try:
        if not stockage.existe(d.fichier):
            raise HTTPException(404, "Fichier absent de l'archive")
        genre, valeur = stockage.url_ou_chemin(d.fichier)
    except CleInvalide:
        raise HTTPException(404, "Fichier introuvable") from None

    if genre == "url":
        return RedirectResponse(valeur, status_code=307)
    nom = (
        f"{(d.titre or 'document').strip()[:80]}.pdf"
        if d.mime == "application/pdf"
        else valeur.name
    )
    return FileResponse(valeur, media_type=d.mime or "application/octet-stream", filename=nom)


TYPES_TEXTES = ("decret", "loi", "arrete", "ordonnance", "charte", "constitution", "texte_juridique")


class TexteOut(BaseModel):
    id: int
    type_doc: str
    titre: str | None
    reference: str | None
    date_publication: date | None
    secteur: str | None
    description: str | None
    url_pdf: str
    jo_numero: str | None
    jo_url: str | None


class TextesPage(BaseModel):
    total: int
    textes: list[TexteOut]


@router.get("/textes", response_model=TextesPage)
def list_textes(
    db: Session = Depends(get_db),
    q: str | None = Query(None, min_length=2, description="Recherche plein texte (français)"),
    type: str | None = Query(None, description="decret | loi | arrete | ordonnance | charte | constitution"),
    page: int = Query(1, ge=1),
    par_page: int = Query(20, ge=1, le=100),
):
    """Textes juridiques (Légiburkina) : décrets, lois, arrêtés… avec lien PDF et Journal officiel."""
    stmt = select(Document).where(Document.type_doc.in_(TYPES_TEXTES))
    if type:
        stmt = stmt.where(Document.type_doc == type)
    if q:
        stmt = stmt.where(text("document.tsv @@ websearch_to_tsquery('french', :q)")).params(q=q)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = (
        stmt.order_by(Document.date_publication.desc().nulls_last(), Document.id.desc())
        .offset((page - 1) * par_page)
        .limit(par_page)
    )
    resultats = []
    for d in db.scalars(stmt).all():
        meta = d.meta or {}
        # après téléchargement du PDF, texte_extrait contient le texte intégral ;
        # la description courte d'origine est préservée dans meta['description']
        description = meta.get("description") or d.texte_extrait
        resultats.append(
            TexteOut(
                id=d.id,
                type_doc=d.type_doc,
                titre=d.titre,
                reference=meta.get("reference"),
                date_publication=d.date_publication,
                secteur=meta.get("secteur"),
                description=(description[:600] if description else None),
                url_pdf=d.url,
                jo_numero=meta.get("jo_numero"),
                jo_url=meta.get("jo_url"),
            )
        )
    return TextesPage(total=int(total or 0), textes=resultats)


class DecisionOut(BaseModel):
    id: int
    document_id: int
    document_url: str
    date_conseil: date | None
    ministere: str | None
    type: str
    objet: str


@router.get("/decisions", response_model=list[DecisionOut])
def list_decisions(
    db: Session = Depends(get_db),
    ministere: str | None = Query(None, description="Filtre contient, insensible à la casse"),
    type: str | None = None,
    page: int = Query(1, ge=1),
    par_page: int = Query(20, ge=1, le=100),
):
    """Décisions du Conseil des ministres - contenus validés uniquement."""
    stmt = (
        select(Decision)
        .join(Document)
        .where(Decision.statut_validation == "valide")
    )
    if ministere:
        stmt = stmt.where(Decision.ministere.ilike(f"%{ministere}%"))
    if type:
        stmt = stmt.where(Decision.type == type)
    stmt = (
        stmt.order_by(Document.date_publication.desc().nulls_last(), Decision.id.desc())
        .offset((page - 1) * par_page)
        .limit(par_page)
    )
    return [
        DecisionOut(
            id=d.id,
            document_id=d.document_id,
            document_url=d.document.url,
            date_conseil=d.document.date_publication,
            ministere=d.ministere,
            type=d.type,
            objet=d.objet,
        )
        for d in db.scalars(stmt).all()
    ]


class NominationOut(BaseModel):
    id: int
    document_id: int
    document_url: str
    date_conseil: date | None
    personne_id: int
    personne: str
    poste: str
    structure: str | None
    date_effet: date | None
    type: str


class NominationsPage(BaseModel):
    total: int
    nominations: list[NominationOut]


@router.get("/nominations", response_model=NominationsPage)
def list_nominations(
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Recherche sur le nom de la personne"),
    page: int = Query(1, ge=1),
    par_page: int = Query(20, ge=1, le=100),
):
    """Nominations en Conseil des ministres - contenus validés uniquement."""
    stmt = (
        select(Nomination)
        .join(Document)
        .where(Nomination.statut_validation == "valide")
    )
    if q:
        from app.models import Personne

        stmt = stmt.join(Personne).where(Personne.nom_complet.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = (
        stmt.order_by(Document.date_publication.desc().nulls_last(), Nomination.id.desc())
        .offset((page - 1) * par_page)
        .limit(par_page)
    )
    return NominationsPage(
        total=int(total or 0),
        nominations=[
            NominationOut(
                id=n.id,
                document_id=n.document_id,
                document_url=n.document.url,
                date_conseil=n.document.date_publication,
                personne_id=n.personne_id,
                personne=n.personne.nom_complet,
                poste=n.poste,
                structure=str(n.structure) if n.structure else None,
                date_effet=n.date_effet,
                type=n.type,
            )
            for n in db.scalars(stmt).all()
        ],
    )


# ── Export open data (CSV) ────────────────────────────────────────────────
# Les jeux de données validés, téléchargeables en CSV pour réutilisation
# (journalistes, chercheurs, société civile). Une ligne = un fait sourcé.

def _csv(colonnes: list[str], lignes) -> "StreamingResponse":
    import csv
    import io

    from fastapi.responses import StreamingResponse

    def flux():
        tampon = io.StringIO()
        w = csv.writer(tampon)
        w.writerow(colonnes)
        yield tampon.getvalue()
        for ligne in lignes:
            tampon.seek(0)
            tampon.truncate(0)
            w.writerow(ligne)
            yield tampon.getvalue()

    return StreamingResponse(flux(), media_type="text/csv; charset=utf-8")


@router.get("/export/nominations.csv")
def export_nominations(db: Session = Depends(get_db)):
    """Toutes les nominations validées, avec leur compte rendu source."""
    stmt = (
        select(Nomination)
        .join(Document)
        .where(Nomination.statut_validation == "valide")
        .order_by(Document.date_publication.desc().nulls_last(), Nomination.id.desc())
    )
    lignes = (
        (
            n.id,
            n.personne.nom_complet,
            n.personne.matricule or "",
            n.poste,
            str(n.structure) if n.structure else "",
            "fin de fonction" if n.type == "fin_fonction" else "nomination",
            n.document.date_publication.isoformat() if n.document.date_publication else "",
            n.document.url,
        )
        for n in db.scalars(stmt).all()
    )
    return _csv(
        ["id", "personne", "matricule", "poste", "structure", "type", "date_conseil", "source_url"],
        lignes,
    )


@router.get("/export/engagements.csv")
def export_engagements(db: Session = Depends(get_db)):
    """Engagements financiers validés du Conseil des ministres."""
    stmt = (
        select(EngagementFinancier)
        .join(Document)
        .where(EngagementFinancier.statut_validation == "valide")
        .order_by(EngagementFinancier.montant_fcfa.desc().nulls_last())
    )
    lignes = (
        (
            e.id,
            e.type,
            e.objet,
            e.beneficiaire or "",
            e.ministere or "",
            e.montant_fcfa if e.montant_fcfa is not None else "",
            e.document.date_publication.isoformat() if e.document.date_publication else "",
            e.document.url,
        )
        for e in db.scalars(stmt).all()
    )
    return _csv(
        ["id", "type", "objet", "beneficiaire", "ministere", "montant_fcfa", "date_conseil", "source_url"],
        lignes,
    )


@router.get("/export/decisions.csv")
def export_decisions(db: Session = Depends(get_db)):
    """Décisions validées du Conseil des ministres."""
    stmt = (
        select(Decision)
        .join(Document)
        .where(Decision.statut_validation == "valide")
        .order_by(Document.date_publication.desc().nulls_last(), Decision.id.desc())
    )
    lignes = (
        (
            d.id,
            d.type,
            d.ministere or "",
            d.objet,
            d.document.date_publication.isoformat() if d.document.date_publication else "",
            d.document.url,
        )
        for d in db.scalars(stmt).all()
    )
    return _csv(["id", "type", "ministere", "objet", "date_conseil", "source_url"], lignes)


@router.get("/export/textes.csv")
def export_textes(db: Session = Depends(get_db)):
    """Textes juridiques (Légiburkina) : décrets, lois, arrêtés…"""
    stmt = (
        select(Document)
        .where(Document.type_doc.in_(TYPES_TEXTES))
        .order_by(Document.date_publication.desc().nulls_last(), Document.id.desc())
    )
    lignes = (
        (
            d.id,
            d.type_doc,
            (d.meta or {}).get("reference", ""),
            d.titre or "",
            d.date_publication.isoformat() if d.date_publication else "",
            (d.meta or {}).get("jo_numero", ""),
            d.url,
        )
        for d in db.scalars(stmt).all()
    )
    return _csv(["id", "type", "reference", "titre", "date", "journal_officiel", "url_pdf"], lignes)


@router.get("/export/annuaire.csv")
def export_annuaire(db: Session = Depends(get_db)):
    """Annuaire de l'État : mandats consolidés."""
    stmt = select(Mandat).join(Personne).outerjoin(Structure).order_by(
        Mandat.date_debut.desc().nulls_last(), Mandat.id.desc()
    )
    lignes = (
        (
            m.id,
            m.personne.nom_complet,
            m.personne.matricule or "",
            m.poste,
            str(m.structure) if m.structure else "",
            m.date_debut.isoformat() if m.date_debut else "",
            m.date_fin.isoformat() if m.date_fin else "",
            "en cours" if m.date_fin is None else "terminé",
        )
        for m in db.scalars(stmt).all()
    )
    return _csv(
        ["id", "personne", "matricule", "poste", "structure", "date_debut", "date_fin", "statut"],
        lignes,
    )


# ── Flux RSS ──────────────────────────────────────────────────────────────
# Suivre les nouvelles publications dans un lecteur de flux, sans compte.

@router.get("/rss/conseils.xml")
def rss_conseils(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import Response

    from app.api.rss import flux_rss

    base = str(request.base_url).rstrip("/").removesuffix("/api")
    docs = db.scalars(
        select(Document)
        .where(Document.type_doc == "cr_conseil")
        .order_by(Document.date_publication.desc().nulls_last(), Document.id.desc())
        .limit(30)
    ).all()
    items = [
        {
            "titre": d.titre or "Conseil des ministres",
            "lien": f"{base}/conseils/{d.id}",
            "guid": f"conseil-{d.id}",
            "date": d.date_publication,
        }
        for d in docs
    ]
    xml = flux_rss(
        request,
        titre="Faso Données Publiques - Conseils des ministres",
        description="Les comptes rendus du Conseil des ministres du Burkina Faso.",
        chemin="/rss/conseils.xml",
        items=items,
    )
    return Response(xml, media_type="application/rss+xml; charset=utf-8")


@router.get("/rss/actualites.xml")
def rss_actualites(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import Response

    from app.api.rss import flux_rss
    from app.extraction.texte import html_vers_texte

    docs = db.scalars(
        select(Document)
        .where(Document.type_doc.in_(("article_presse", "communique")))
        .order_by(Document.date_publication.desc().nulls_last(), Document.id.desc())
        .limit(40)
    ).all()
    items = []
    for d in docs:
        resume = (d.meta or {}).get("resume")
        items.append(
            {
                "titre": d.titre or d.source.nom,
                "lien": d.url,  # l'article renvoie à sa source d'origine
                "guid": f"actu-{d.id}",
                "description": (html_vers_texte(resume)[:280] if resume else None),
                "date": d.date_publication,
            }
        )
    xml = flux_rss(
        request,
        titre="Faso Données Publiques - Actualités",
        description="Le fil d'actualités agrégé : médias burkinabè et communiqués officiels.",
        chemin="/rss/actualites.xml",
        items=items,
    )
    return Response(xml, media_type="application/rss+xml; charset=utf-8")


@router.get("/rss/textes.xml")
def rss_textes(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import Response

    from app.api.rss import flux_rss

    docs = db.scalars(
        select(Document)
        .where(Document.type_doc.in_(TYPES_TEXTES))
        .order_by(Document.date_publication.desc().nulls_last(), Document.id.desc())
        .limit(30)
    ).all()
    items = [
        {
            "titre": ((d.meta or {}).get("reference") or d.titre or "Texte juridique"),
            "lien": d.url,
            "guid": f"texte-{d.id}",
            "description": ((d.meta or {}).get("description") or None),
            "date": d.date_publication,
        }
        for d in docs
    ]
    xml = flux_rss(
        request,
        titre="Faso Données Publiques - Lois & décrets",
        description="Les nouveaux textes juridiques publiés (Légiburkina).",
        chemin="/rss/textes.xml",
        items=items,
    )
    return Response(xml, media_type="application/rss+xml; charset=utf-8")


# ── Pages de partage (Open Graph) ─────────────────────────────────────────
# Ce que voient les robots de Facebook, X et Telegram quand un lien du site est
# posté. Sans elles, tous les posts porteraient la même vignette générique -
# cf. app/api/partage.py.

def _site_public(request: Request) -> str:
    return str(request.base_url).rstrip("/").removesuffix("/api")


@router.get("/partage/conseils/{doc_id}", include_in_schema=False)
def partage_conseil(doc_id: int, request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse

    from app.api.partage import html_partage

    doc = db.get(Document, doc_id)
    if doc is None or doc.type_doc != "cr_conseil":
        raise HTTPException(status_code=404, detail="Compte rendu introuvable")
    base = _site_public(request)
    nb_decisions = db.scalar(
        select(func.count()).select_from(Decision).where(
            Decision.document_id == doc.id, Decision.statut_validation == "valide"
        )
    ) or 0
    nb_nominations = db.scalar(
        select(func.count()).select_from(Nomination).where(
            Nomination.document_id == doc.id, Nomination.statut_validation == "valide"
        )
    ) or 0
    # Le décompte tient lieu de résumé : il dit ce que la page apporte de plus
    # que le PDF officiel, sans rien interpréter du contenu des décisions.
    morceaux = []
    if nb_decisions:
        morceaux.append(f"{nb_decisions} décision{'s' if nb_decisions > 1 else ''}")
    if nb_nominations:
        morceaux.append(f"{nb_nominations} nomination{'s' if nb_nominations > 1 else ''}")
    description = (
        (" et ".join(morceaux) + ", reliées au compte rendu officiel.")
        if morceaux
        else "Compte rendu du Conseil des ministres, relié à sa source officielle."
    )
    return HTMLResponse(
        html_partage(
            titre=doc.titre or "Compte rendu du Conseil des ministres",
            description=description,
            url=f"{base}/conseils/{doc.id}",
            image=settings.og_image_url,
        )
    )


@router.get("/partage/documents/{doc_id}", include_in_schema=False)
def partage_document(doc_id: int, request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse

    from app.api.partage import html_partage
    from app.extraction.texte import html_vers_texte

    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document introuvable")
    base = _site_public(request)
    resume = (doc.meta or {}).get("resume")
    description = html_vers_texte(resume)[:280] if resume else ""
    if not description:
        elements = [doc.source.nom if doc.source else None]
        if doc.date_publication:
            elements.append(f"publié le {doc.date_publication:%d/%m/%Y}")
        description = "Document archivé - " + ", ".join(e for e in elements if e)
    return HTMLResponse(
        html_partage(
            titre=doc.titre or doc.url,
            description=description,
            url=f"{base}/documents/{doc.id}",
            image=settings.og_image_url,
        )
    )



# ── Marchés publics (attributions) ────────────────────────────────────────
class MarcheOut(BaseModel):
    id: int
    # attribution | preselection - le second n'est pas un marché remporté
    nature: str
    attributaire: str | None  # la graphie exacte du document source
    attributaire_id: int | None  # l'entité consolidée (fiche entreprise)
    montant_fcfa: int | None
    autorite: str | None
    objet: str
    secteur: str | None
    reference: str | None
    date: date | None
    document_id: int


class MarchesPage(BaseModel):
    total: int
    montant_total_fcfa: int
    marches: list[MarcheOut]


class CategorieStat(BaseModel):
    cle: str  # secteur, entreprise, autorité contractante ou année
    montant_fcfa: int
    nombre: int
    id: int | None = None  # renseigné quand la clé désigne une entité liable


class MarchesStats(BaseModel):
    total: int
    montant_total_fcfa: int
    nb_entreprises: int
    annees: list[int]  # années disponibles (pour le filtre)
    secteurs_dispo: list[str]  # secteurs disponibles (pour le filtre)
    par_secteur: list[CategorieStat]
    par_annee: list[CategorieStat]
    top_entreprises: list[CategorieStat]


class AttributaireOut(BaseModel):
    id: int
    nom: str
    nb_marches: int
    montant_fcfa: int


class AttributairesPage(BaseModel):
    total: int
    attributaires: list[AttributaireOut]


class AttributaireDetail(BaseModel):
    id: int
    nom: str
    # toutes les graphies rencontrées dans les Quotidiens, pour que le lecteur
    # puisse vérifier ce que le regroupement a réuni
    variantes: list[str]
    nb_marches: int
    montant_fcfa: int
    # candidats retenus après manifestation d'intérêt : hors des totaux
    # ci-dessus, mais tus complètement ils donneraient une image incomplète
    nb_preselections: int
    premiere_attribution: date | None
    derniere_attribution: date | None
    par_secteur: list[CategorieStat]
    par_annee: list[CategorieStat]
    par_autorite: list[CategorieStat]
    marches: list[MarcheOut]


def _ids_du_groupe(db: Session, attributaire_id: int) -> list[int]:
    """Identifiants de l'entité consolidée : la racine et ses variantes fusionnées.

    Accepte indifféremment l'id de la racine ou celui d'une variante - une
    URL déjà partagée reste valable après une fusion.
    """
    racine = db.scalar(
        select(func.coalesce(Attributaire.canonique_id, Attributaire.id)).where(
            Attributaire.id == attributaire_id
        )
    )
    if racine is None:
        return []
    membres = list(
        db.scalars(select(Attributaire.id).where(Attributaire.canonique_id == racine))
    )
    return [racine, *membres]


@router.get("/attributaires", response_model=AttributairesPage)
def list_attributaires(
    db: Session = Depends(get_db),
    q: str | None = Query(None, min_length=2, description="Raison sociale"),
    tri: str = Query("montant", description="montant | nombre | nom"),
    page: int = Query(1, ge=1),
    par_page: int = Query(20, ge=1, le=100),
):
    """Entreprises attributaires de marchés publics, consolidées.

    Chaque entrée regroupe les graphies d'une même raison sociale rencontrées
    dans les Quotidiens de la DGCMEF (cf. `app/attributaires.py`). Les montants
    ne portent que sur les marchés **validés**.
    """
    montant = func.coalesce(func.sum(Marche.montant_fcfa), 0)
    racine = func.coalesce(Attributaire.canonique_id, Attributaire.id)
    agg = (
        select(
            racine.label("gid"),
            func.count().label("nb"),
            montant.label("montant"),
        )
        .select_from(Marche)
        .join(Attributaire, Marche.attributaire_id == Attributaire.id)
        # les présélections n'ont pas de montant : les compter ici gonflerait le
        # nombre de marchés d'une entreprise sans rien ajouter à son total
        .where(Marche.statut_validation == "valide", Marche.nature == "attribution")
        .group_by(racine)
        .subquery()
    )
    base = select(Attributaire, agg.c.nb, agg.c.montant).join(
        agg, agg.c.gid == Attributaire.id
    )
    if q:
        base = base.where(Attributaire.nom.ilike(f"%{q}%"))
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    if tri == "nombre":
        base = base.order_by(agg.c.nb.desc())
    elif tri == "nom":
        base = base.order_by(Attributaire.nom)
    else:
        base = base.order_by(agg.c.montant.desc())
    lignes = db.execute(base.offset((page - 1) * par_page).limit(par_page)).all()
    return AttributairesPage(
        total=total,
        attributaires=[
            AttributaireOut(
                id=a.id, nom=a.nom, nb_marches=int(nb), montant_fcfa=int(m or 0)
            )
            for a, nb, m in lignes
        ],
    )


@router.get("/attributaires/{attributaire_id}", response_model=AttributaireDetail)
def fiche_attributaire(
    attributaire_id: int,
    db: Session = Depends(get_db),
    par_page: int = Query(50, ge=1, le=200, description="Marchés listés dans la fiche"),
):
    """Fiche d'une entreprise attributaire : ce qu'elle a remporté, auprès de
    qui, dans quels secteurs - uniquement à partir de marchés validés et
    sourcés."""
    ids = _ids_du_groupe(db, attributaire_id)
    if not ids:
        raise HTTPException(status_code=404, detail="Attributaire inconnu")
    racine = db.get(Attributaire, ids[0])

    marches_valides = select(Marche).where(
        Marche.attributaire_id.in_(ids),
        Marche.statut_validation == "valide",
        Marche.nature == "attribution",
    )
    montant = func.coalesce(func.sum(Marche.montant_fcfa), 0)
    an = func.extract("year", Marche.date_attribution)

    def agrege(colonne, limite=None):
        s = (
            marches_valides.with_only_columns(
                colonne.label("cle"), montant.label("m"), func.count().label("n")
            )
            .where(colonne.is_not(None))
            .group_by(colonne)
            .order_by(montant.desc())
        )
        if limite:
            s = s.limit(limite)
        from numbers import Number  # l'année sort en Decimal de PostgreSQL

        return [
            CategorieStat(
                cle=str(int(r.cle)) if isinstance(r.cle, Number) else str(r.cle),
                montant_fcfa=int(r.m or 0),
                nombre=int(r.n),
            )
            for r in db.execute(s)
        ]

    bornes = db.execute(
        marches_valides.with_only_columns(
            func.count(),
            montant,
            func.min(Marche.date_attribution),
            func.max(Marche.date_attribution),
        )
    ).one()
    variantes = sorted(
        v for v in db.scalars(
            marches_valides.with_only_columns(Marche.attributaire).distinct()
        ) if v
    )
    marches = db.scalars(
        marches_valides.order_by(Marche.montant_fcfa.desc().nulls_last()).limit(par_page)
    ).all()
    nb_preselections = db.scalar(
        select(func.count())
        .select_from(Marche)
        .where(
            Marche.attributaire_id.in_(ids),
            Marche.statut_validation == "valide",
            Marche.nature == "preselection",
        )
    )

    return AttributaireDetail(
        id=racine.id,
        nom=racine.nom,
        variantes=variantes,
        nb_marches=int(bornes[0] or 0),
        montant_fcfa=int(bornes[1] or 0),
        nb_preselections=int(nb_preselections or 0),
        premiere_attribution=bornes[2],
        derniere_attribution=bornes[3],
        par_secteur=agrege(Marche.secteur),
        par_annee=sorted(agrege(an.label("annee")), key=lambda c: c.cle),
        par_autorite=agrege(Marche.autorite, limite=15),
        marches=[
            MarcheOut(
                id=m.id,
                nature=m.nature,
                attributaire=m.attributaire,
                attributaire_id=m.attributaire_id,
                montant_fcfa=m.montant_fcfa,
                autorite=m.autorite,
                objet=m.objet,
                secteur=m.secteur,
                reference=m.reference,
                date=m.date_attribution,
                document_id=m.document_id,
            )
            for m in marches
        ],
    )


@router.get("/marches", response_model=MarchesPage)
def list_marches(
    db: Session = Depends(get_db),
    q: str | None = Query(None, min_length=2, description="Attributaire, autorité ou objet"),
    secteur: str | None = Query(None, description="Filtrer par secteur déduit"),
    annee: int | None = Query(None, description="Filtrer par année d'attribution"),
    attributaire_id: int | None = Query(
        None, description="Restreindre à une entreprise consolidée (variantes incluses)"
    ),
    nature: Literal["attribution", "preselection", "toutes"] | None = Query(
        None,
        description="attribution (défaut) | preselection | toutes - une "
        "manifestation d'intérêt retient un candidat pour la suite de la "
        "procédure, sans lui attribuer de contrat ni de montant",
    ),
    tri: str = Query("montant", description="montant | date"),
    page: int = Query(1, ge=1),
    par_page: int = Query(20, ge=1, le=100),
):
    """Marchés publics attribués (Quotidien DGCMEF) - validés uniquement."""
    from app.models import Marche

    base = select(Marche).where(Marche.statut_validation == "valide")
    # Par défaut on ne sert que les attributions : mêlées aux présélections, les
    # chiffres de la liste ne correspondraient plus à ceux des statistiques.
    # `nature=preselection` ouvre l'autre volet, `toutes` les réunit.
    if nature != "toutes":
        base = base.where(Marche.nature == (nature or "attribution"))
    if q:
        motif = f"%{q}%"
        base = base.where(
            Marche.attributaire.ilike(motif)
            | Marche.autorite.ilike(motif)
            | Marche.objet.ilike(motif)
        )
    if secteur:
        base = base.where(Marche.secteur == secteur)
    if annee:
        base = base.where(func.extract("year", Marche.date_attribution) == annee)
    if attributaire_id:
        base = base.where(Marche.attributaire_id.in_(_ids_du_groupe(db, attributaire_id)))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    # somme sur la même sélection filtrée (pas select_from(subquery) : la colonne
    # de l'entité y provoquerait un produit cartésien)
    montant_total = db.scalar(
        base.with_only_columns(func.coalesce(func.sum(Marche.montant_fcfa), 0)).order_by(None)
    )
    if tri == "date":
        base = base.order_by(Marche.date_attribution.desc().nulls_last(), Marche.id.desc())
    else:
        base = base.order_by(Marche.montant_fcfa.desc().nulls_last())
    marches = db.scalars(base.offset((page - 1) * par_page).limit(par_page)).all()
    return MarchesPage(
        total=int(total or 0),
        montant_total_fcfa=int(montant_total or 0),
        marches=[
            MarcheOut(
                id=m.id,
                nature=m.nature,
                attributaire=m.attributaire,
                attributaire_id=m.attributaire_id,
                montant_fcfa=m.montant_fcfa,
                autorite=m.autorite,
                objet=m.objet,
                secteur=m.secteur,
                reference=m.reference,
                date=m.date_attribution,
                document_id=m.document_id,
            )
            for m in marches
        ],
    )


@router.get("/marches/stats", response_model=MarchesStats)
def marches_stats(
    db: Session = Depends(get_db),
    secteur: str | None = Query(None, description="Restreindre à un secteur"),
    annee: int | None = Query(None, description="Restreindre à une année"),
):
    """Statistiques agrégées des marchés attribués (validés) : par secteur,
    par année, top entreprises. Les filtres secteur/année se combinent."""
    from app.models import Marche

    an = func.extract("year", Marche.date_attribution)
    montant = func.coalesce(func.sum(Marche.montant_fcfa), 0)

    def filtree(*colonnes):
        s = select(*colonnes).where(
            Marche.statut_validation == "valide", Marche.nature == "attribution"
        )
        if secteur:
            s = s.where(Marche.secteur == secteur)
        if annee:
            s = s.where(an == annee)
        return s

    # Une entreprise = son entité consolidée (app/attributaires.py) si le marché
    # y est rattaché, sinon la graphie brute du document. Le `outerjoin` fait
    # donc tenir les deux mondes dans la même agrégation : la page reste juste
    # avant le premier `consolider`, et se regroupe d'elle-même après.
    Canon = aliased(Attributaire)
    cle_entreprise = func.coalesce(Canon.nom, Marche.attributaire)

    def par_entreprise(*colonnes):
        return (
            filtree(*colonnes)
            .select_from(Marche)
            .outerjoin(Attributaire, Marche.attributaire_id == Attributaire.id)
            .outerjoin(Canon, Canon.id == func.coalesce(Attributaire.canonique_id, Attributaire.id))
        )

    total = int(db.scalar(filtree(func.count()).order_by(None)) or 0)
    montant_total = int(db.scalar(filtree(montant).order_by(None)) or 0)
    nb_entreprises = int(
        db.scalar(par_entreprise(func.count(func.distinct(cle_entreprise))).order_by(None)) or 0
    )

    # options de filtre : toujours calculées sur l'ensemble validé (pas restreint)
    base_all = select(Marche).where(
        Marche.statut_validation == "valide", Marche.nature == "attribution"
    )
    annees = sorted(
        {int(a) for a in db.scalars(base_all.with_only_columns(an.distinct()).order_by(None)) if a is not None},
        reverse=True,
    )
    secteurs_dispo = sorted(
        x for x in db.scalars(
            base_all.with_only_columns(Marche.secteur).distinct().order_by(None)
        ) if x
    )

    def agrege(colonne, limite=None):
        s = (
            filtree(colonne.label("cle"), montant.label("m"), func.count().label("n"))
            .where(colonne.is_not(None))
            .group_by(colonne)
            .order_by(montant.desc())
        )
        if limite:
            s = s.limit(limite)
        from numbers import Number

        def _cle(v):
            return str(int(v)) if isinstance(v, Number) else str(v)

        return [
            CategorieStat(cle=_cle(r.cle), montant_fcfa=int(r.m or 0), nombre=int(r.n))
            for r in db.execute(s)
        ]

    par_secteur = agrege(Marche.secteur)
    par_annee = sorted(
        agrege(an.label("annee")), key=lambda c: c.cle
    )

    top_entreprises = [
        CategorieStat(
            cle=str(r.cle), montant_fcfa=int(r.m or 0), nombre=int(r.n), id=r.gid
        )
        for r in db.execute(
            par_entreprise(
                cle_entreprise.label("cle"),
                Canon.id.label("gid"),
                montant.label("m"),
                func.count().label("n"),
            )
            .where(cle_entreprise.is_not(None))
            .group_by(cle_entreprise, Canon.id)
            .order_by(montant.desc())
            .limit(15)
        )
    ]

    return MarchesStats(
        total=total,
        montant_total_fcfa=montant_total,
        nb_entreprises=nb_entreprises,
        annees=annees,
        secteurs_dispo=secteurs_dispo,
        par_secteur=par_secteur,
        par_annee=par_annee,
        top_entreprises=top_entreprises,
    )


# --- Infrastructures & inaugurations -----------------------------------------

class RealisationOut(BaseModel):
    id: int
    type: str
    titre: str
    description: str | None
    statut: str
    date_evenement: date | None
    region: str | None
    localisation_nom: str | None
    latitude: float | None
    longitude: float | None
    localisation_nom_arr: str | None
    latitude_arr: float | None
    longitude_arr: float | None
    secteur: str | None
    maitre_ouvrage: str | None
    montant_fcfa: int | None
    source_url: str | None


class RealisationsPage(BaseModel):
    total: int
    realisations: list[RealisationOut]


def _realisations_filtrees(type_: str | None, region: str | None, statut: str | None,
                           secteur: str | None, annee: int | None, q: str | None):
    from app.models import Realisation

    stmt = select(Realisation).where(Realisation.statut_validation == "valide")
    if type_:
        stmt = stmt.where(Realisation.type == type_)
    if region:
        stmt = stmt.where(Realisation.region == region)
    if statut:
        stmt = stmt.where(Realisation.statut == statut)
    if secteur:
        stmt = stmt.where(Realisation.secteur == secteur)
    if annee:
        stmt = stmt.where(func.extract("year", Realisation.date_evenement) == annee)
    if q:
        motif = f"%{q}%"
        stmt = stmt.where(
            Realisation.titre.ilike(motif) | Realisation.localisation_nom.ilike(motif)
        )
    return stmt


@router.get("/realisations", response_model=RealisationsPage)
def list_realisations(
    db: Session = Depends(get_db),
    type: str | None = Query(None),
    region: str | None = Query(None),
    statut: str | None = Query(None),
    secteur: str | None = Query(None),
    annee: int | None = Query(None),
    q: str | None = Query(None),
    limite: int = Query(3000, ge=1, le=5000),
):
    """Registre des inaugurations/infrastructures (validées) : liste + points
    pour la carte. Filtres type/région/statut/secteur/année/recherche."""
    from app.models import Realisation

    stmt = _realisations_filtrees(type, region, statut, secteur, annee, q)
    total = db.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )
    rows = db.scalars(
        stmt.order_by(Realisation.date_evenement.desc().nulls_last(), Realisation.id.desc())
        .limit(limite)
    ).all()
    return RealisationsPage(
        total=int(total or 0),
        realisations=[
            RealisationOut(
                id=r.id, type=r.type, titre=r.titre, description=r.description,
                statut=r.statut, date_evenement=r.date_evenement, region=r.region,
                localisation_nom=r.localisation_nom, latitude=r.latitude,
                longitude=r.longitude, localisation_nom_arr=r.localisation_nom_arr,
                latitude_arr=r.latitude_arr, longitude_arr=r.longitude_arr,
                secteur=r.secteur, maitre_ouvrage=r.maitre_ouvrage,
                montant_fcfa=r.montant_fcfa, source_url=r.source_url,
            )
            for r in rows
        ],
    )


class RealisationsStats(BaseModel):
    total: int
    montant_total: int
    par_type: list[dict]
    par_region: list[dict]
    par_annee: list[dict]
    par_statut: list[dict]
    types_dispo: list[str]
    regions_dispo: list[str]
    annees_dispo: list[int]


@router.get("/realisations/stats", response_model=RealisationsStats)
def realisations_stats(
    db: Session = Depends(get_db),
    type: str | None = Query(None),
    region: str | None = Query(None),
    statut: str | None = Query(None),
    secteur: str | None = Query(None),
    annee: int | None = Query(None),
):
    """Agrégats du registre (validé) : par type, région, année, statut."""
    from app.models import Realisation

    an = func.extract("year", Realisation.date_evenement)
    montant = func.coalesce(func.sum(Realisation.montant_fcfa), 0)

    def filtree(*cols):
        s = select(*cols).where(Realisation.statut_validation == "valide")
        if type:
            s = s.where(Realisation.type == type)
        if region:
            s = s.where(Realisation.region == region)
        if statut:
            s = s.where(Realisation.statut == statut)
        if secteur:
            s = s.where(Realisation.secteur == secteur)
        if annee:
            s = s.where(an == annee)
        return s

    total = int(db.scalar(filtree(func.count()).order_by(None)) or 0)
    montant_total = int(db.scalar(filtree(montant).order_by(None)) or 0)

    def agrege(colonne):
        rows = db.execute(
            filtree(colonne.label("cle"), func.count().label("n"))
            .where(colonne.is_not(None)).group_by(colonne).order_by(func.count().desc())
        ).all()
        return [{"cle": str(r.cle), "n": int(r.n)} for r in rows]

    par_annee = [
        {"cle": str(int(r.cle)), "n": int(r.n)}
        for r in db.execute(
            filtree(an.label("cle"), func.count().label("n"))
            .where(an.is_not(None)).group_by(an).order_by(an)
        ).all()
    ]

    base_all = select(Realisation).where(Realisation.statut_validation == "valide")
    types_dispo = sorted(
        x for x in db.scalars(base_all.with_only_columns(Realisation.type).distinct().order_by(None)) if x
    )
    regions_dispo = sorted(
        x for x in db.scalars(base_all.with_only_columns(Realisation.region).distinct().order_by(None)) if x
    )
    annees_dispo = sorted(
        {int(a) for a in db.scalars(base_all.with_only_columns(an.distinct()).order_by(None)) if a is not None},
        reverse=True,
    )

    return RealisationsStats(
        total=total, montant_total=montant_total,
        par_type=agrege(Realisation.type),
        par_region=agrege(Realisation.region),
        par_annee=par_annee,
        par_statut=agrege(Realisation.statut),
        types_dispo=types_dispo, regions_dispo=regions_dispo, annees_dispo=annees_dispo,
    )
