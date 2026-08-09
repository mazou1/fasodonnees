"""Back-office SQLAdmin : CRUD + file de validation des extractions.

Remplace le rôle de Directus dans vie-publique.sn, sans service supplémentaire.
"""

import secrets

from fastapi import FastAPI
from sqladmin import Admin, BaseView, ModelView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import update
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.config import settings
from app.db import SessionLocal, engine
from app.models import (
    Attributaire,
    BudgetExercice,
    Decision,
    Document,
    DotationBudgetaire,
    EngagementFinancier,
    Localite,
    Mandat,
    Marche,
    MembreGouvernement,
    Nomination,
    Personne,
    Projet,
    Realisation,
    RepartitionBudgetaire,
    Run,
    Source,
    Structure,
)
from app.validation import SEUIL_DEFAUT, compter_a_valider, valider_par_seuil


def _pks(request: Request) -> list[int]:
    brut = request.query_params.get("pks", "")
    return [int(pk) for pk in brut.split(",") if pk]


def _retour(request: Request, defaut: str) -> RedirectResponse:
    return RedirectResponse(request.headers.get("Referer", defaut), status_code=302)


def _reconstruire_annuaire_si_besoin(db, modele: type, valides: int) -> None:
    """Valider une nomination doit la faire apparaître dans l'annuaire.

    Les mandats sont une vue dérivée des nominations validées, reconstruite
    entièrement à chaque passage (≈2 s sur le corpus complet). Sans cet appel,
    une nomination validée dans /admin restait invisible dans l'annuaire et sur
    la fiche de la personne jusqu'à ce que quelqu'un lance `python -m
    app.annuaire` à la main.
    """
    if not valides or modele is not Nomination:
        return
    from app.annuaire import consolider

    consolider(db)


class ValidationActionsMixin:
    """File de validation : la liste n'affiche QUE les éléments « à valider »
    par défaut (le back-office devient une file de tâches claire), avec cases à
    cocher pour valider/rejeter en masse. `?statut=valide|rejete|tous` pour voir
    les autres."""

    modele: type  # Decision ou Nomination
    # les vues de SAISIE manuelle (dotations, gouvernement) ne filtrent pas :
    # on y crée des lignes directement valides
    defaut_a_valider: bool = True

    def _filtre_statut(self, request: Request, stmt):
        if not self.defaut_a_valider:
            return stmt
        statut = request.query_params.get("statut", "a_valider")
        if statut and statut != "tous":
            stmt = stmt.where(self.model.statut_validation == statut)
        return stmt

    def list_query(self, request: Request):
        return self._filtre_statut(request, super().list_query(request))

    def count_query(self, request: Request):
        return self._filtre_statut(request, super().count_query(request))

    @action(
        name="valider",
        label="✓ Valider la sélection",
        confirmation_message="Valider les éléments sélectionnés ? Ils deviendront publics via l'API.",
        add_in_detail=True,
        add_in_list=True,
    )
    async def valider(self, request: Request):
        with SessionLocal() as db:
            n = db.execute(
                update(self.modele)
                .where(self.modele.id.in_(_pks(request)))
                .values(statut_validation="valide")
            ).rowcount
            db.commit()
            _reconstruire_annuaire_si_besoin(db, self.modele, n)
        return _retour(request, request.url_for("admin:list", identity=self.identity))

    @action(
        name="rejeter",
        label="✗ Rejeter la sélection",
        confirmation_message="Rejeter les éléments sélectionnés ?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def rejeter(self, request: Request):
        with SessionLocal() as db:
            db.execute(
                update(self.modele)
                .where(self.modele.id.in_(_pks(request)))
                .values(statut_validation="rejete")
            )
            db.commit()
        return _retour(request, request.url_for("admin:list", identity=self.identity))


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        user = str(form.get("username", ""))
        password = str(form.get("password", ""))
        ok = secrets.compare_digest(user, settings.admin_user) and secrets.compare_digest(
            password, settings.admin_password
        )
        if ok:
            request.session.update({"user": user})
        return ok

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("user") == settings.admin_user


class SourceAdmin(ModelView, model=Source):
    column_list = [Source.slug, Source.nom, Source.type, Source.cadence, Source.actif]
    icon = "fa-solid fa-database"


class DocumentAdmin(ModelView, model=Document):
    column_list = [
        Document.id,
        Document.source,
        Document.type_doc,
        Document.titre,
        Document.date_publication,
        Document.statut_extraction,
    ]
    column_searchable_list = [Document.titre, Document.url]
    column_default_sort = ("id", True)
    page_size = 100
    icon = "fa-solid fa-file-lines"

    @action(
        name="valider_contenu",
        label="✓ Valider décisions + nominations de ces CR",
        confirmation_message=(
            "Valider TOUTES les décisions et nominations extraites des documents "
            "sélectionnés ? Elles deviendront publiques via l'API."
        ),
        add_in_detail=True,
        add_in_list=True,
    )
    async def valider_contenu(self, request: Request):
        pks = _pks(request)
        with SessionLocal() as db:
            for modele in (Decision, Nomination):
                db.execute(
                    update(modele)
                    .where(
                        modele.document_id.in_(pks),
                        modele.statut_validation == "a_valider",
                    )
                    .values(statut_validation="valide")
                )
            db.commit()
        return _retour(request, request.url_for("admin:list", identity=self.identity))


class NominationAdmin(ValidationActionsMixin, ModelView, model=Nomination):
    modele = Nomination
    name_plural = "Nominations (validation)"
    page_size = 100
    column_sortable_list = [Nomination.id, Nomination.statut_validation, Nomination.score_confiance]
    column_list = [
        Nomination.id,
        Nomination.personne,
        Nomination.poste,
        Nomination.structure,
        Nomination.date_effet,
        Nomination.score_confiance,
        Nomination.statut_validation,
    ]
    column_default_sort = ("id", True)
    icon = "fa-solid fa-user-check"


class DecisionAdmin(ValidationActionsMixin, ModelView, model=Decision):
    modele = Decision
    name_plural = "Décisions (validation)"
    page_size = 100
    column_sortable_list = [Decision.id, Decision.type, Decision.statut_validation]
    column_list = [
        Decision.id,
        Decision.document,
        Decision.ministere,
        Decision.type,
        Decision.objet,
        Decision.score_confiance,
        Decision.statut_validation,
    ]
    column_searchable_list = [Decision.objet, Decision.ministere]
    column_default_sort = ("id", True)
    icon = "fa-solid fa-gavel"


class EngagementAdmin(ValidationActionsMixin, ModelView, model=EngagementFinancier):
    modele = EngagementFinancier
    name_plural = "Engagements financiers (validation)"
    page_size = 100
    column_sortable_list = [
        EngagementFinancier.id,
        EngagementFinancier.montant_fcfa,
        EngagementFinancier.statut_validation,
    ]
    column_list = [
        EngagementFinancier.id,
        EngagementFinancier.document,
        EngagementFinancier.type,
        EngagementFinancier.objet,
        EngagementFinancier.beneficiaire,
        EngagementFinancier.montant_fcfa,
        EngagementFinancier.score_confiance,
        EngagementFinancier.statut_validation,
    ]
    column_searchable_list = [EngagementFinancier.objet, EngagementFinancier.beneficiaire]
    column_default_sort = ("montant_fcfa", True)
    icon = "fa-solid fa-coins"


class BudgetAdmin(ValidationActionsMixin, ModelView, model=BudgetExercice):
    modele = BudgetExercice
    name_plural = "Budgets d'exercice (validation)"
    column_list = [
        BudgetExercice.id,
        BudgetExercice.exercice,
        BudgetExercice.type_loi,
        BudgetExercice.recettes_fcfa,
        BudgetExercice.depenses_fcfa,
        BudgetExercice.score_confiance,
        BudgetExercice.statut_validation,
    ]
    column_default_sort = ("exercice", True)
    icon = "fa-solid fa-scale-balanced"


class MarcheAdmin(ValidationActionsMixin, ModelView, model=Marche):
    modele = Marche
    name_plural = "Marchés publics (validation)"
    page_size = 100
    column_list = [
        Marche.id,
        # visible dès la liste : le valideur doit voir qu'une ligne sans montant
        # est une présélection et non une attribution incomplète
        Marche.nature,
        Marche.attributaire,
        Marche.montant_fcfa,
        Marche.autorite,
        Marche.objet,
        Marche.date_attribution,
        Marche.score_confiance,
        Marche.statut_validation,
    ]
    column_searchable_list = [Marche.attributaire, Marche.autorite, Marche.objet]
    column_sortable_list = [
        Marche.montant_fcfa,
        Marche.date_attribution,
        Marche.statut_validation,
        Marche.nature,
    ]
    column_default_sort = ("montant_fcfa", True)
    icon = "fa-solid fa-file-signature"


class RealisationAdmin(ValidationActionsMixin, ModelView, model=Realisation):
    modele = Realisation
    name_plural = "Infrastructures & inaugurations (validation)"
    page_size = 100
    column_list = [
        Realisation.id,
        Realisation.type,
        Realisation.titre,
        Realisation.statut,
        Realisation.date_evenement,
        Realisation.localisation_nom,
        Realisation.region,
        Realisation.secteur,
        Realisation.score_confiance,
        Realisation.statut_validation,
    ]
    form_columns = [
        Realisation.type,
        Realisation.titre,
        Realisation.description,
        Realisation.statut,
        Realisation.date_evenement,
        Realisation.localite,
        Realisation.localisation_nom,
        Realisation.region,
        Realisation.latitude,
        Realisation.longitude,
        Realisation.precision_geo,
        Realisation.secteur,
        Realisation.maitre_ouvrage,
        Realisation.montant_fcfa,
        Realisation.source_url,
        Realisation.photo_url,
        Realisation.document,
        Realisation.projet,  # rattachement au dossier de suivi
        Realisation.statut_validation,
    ]
    column_searchable_list = [Realisation.titre, Realisation.localisation_nom]
    column_sortable_list = [Realisation.date_evenement, Realisation.type, Realisation.statut_validation]
    column_default_sort = ("date_evenement", True)
    icon = "fa-solid fa-helmet-safety"


class ProjetAdmin(ValidationActionsMixin, ModelView, model=Projet):
    """Dossiers de suivi : annonce → attribution → livraison.

    Créés par `python -m app.projets appliquer` (les propositions relues), ou à
    la main ici. Le rattachement d'une pièce se fait depuis la pièce elle-même
    (champ `projet` des vues Marchés, Engagements et Infrastructures) : c'est
    là qu'on a le libellé sous les yeux pour juger.

    `defaut_a_valider = False` : un dossier n'est pas une extraction
    automatique, il naît d'une décision humaine - la liste les montre tous.
    """

    modele = Projet
    defaut_a_valider = False
    name = "Dossier de suivi"
    name_plural = "Dossiers de suivi (annonce → livraison)"
    page_size = 100
    column_list = [
        Projet.id,
        Projet.titre,
        Projet.secteur,
        Projet.region,
        Projet.statut_validation,
    ]
    form_columns = [
        Projet.titre,
        Projet.secteur,
        Projet.region,
        Projet.notes,
        Projet.statut_validation,
    ]
    column_searchable_list = [Projet.titre]
    column_sortable_list = [Projet.id, Projet.secteur, Projet.statut_validation]
    column_default_sort = ("id", True)
    icon = "fa-solid fa-diagram-project"


class AttributaireAdmin(ModelView, model=Attributaire):
    """Entités consolidées derrière les raisons sociales des marchés.

    Vue de CORRECTION, pas de validation : ces lignes sont dérivées, pas
    extraites (cf. app/attributaires.py). On y corrige une graphie retenue
    - cocher alors `nom_fige` pour que la consolidation ne la réécrive pas -
    et on rattache une variante à sa canonique via `canonique`.
    """

    name = "Attributaire"
    name_plural = "Attributaires (entreprises consolidées)"
    page_size = 100
    column_list = [
        Attributaire.id,
        Attributaire.nom,
        Attributaire.nom_normalise,
        Attributaire.canonique,
        Attributaire.nom_fige,
        Attributaire.notes,
    ]
    form_columns = [
        Attributaire.nom,
        Attributaire.canonique,
        Attributaire.nom_fige,
        Attributaire.notes,
    ]
    column_searchable_list = [Attributaire.nom, Attributaire.nom_normalise]
    column_sortable_list = [Attributaire.nom, Attributaire.id]
    column_default_sort = ("nom", False)
    can_create = False  # créées par la consolidation, jamais à la main
    can_delete = False  # supprimer délierait des marchés : fusionner à la place
    icon = "fa-solid fa-building"


class LocaliteAdmin(ModelView, model=Localite):
    name_plural = "Localités (référentiel géo)"
    page_size = 100
    column_list = [
        Localite.id,
        Localite.nom,
        Localite.type,
        Localite.region,
        Localite.province,
        Localite.latitude,
        Localite.longitude,
        Localite.population,
    ]
    column_searchable_list = [Localite.nom, Localite.region]
    column_sortable_list = [Localite.nom, Localite.type, Localite.population]
    column_default_sort = [("type", False), ("population", True)]
    can_create = False
    icon = "fa-solid fa-location-dot"


class DotationAdmin(ValidationActionsMixin, ModelView, model=DotationBudgetaire):
    modele = DotationBudgetaire
    defaut_a_valider = False  # saisie manuelle : on voit toutes les lignes
    name_plural = "Dotations budgétaires (saisie)"
    column_list = [
        DotationBudgetaire.exercice,
        DotationBudgetaire.ministere,
        DotationBudgetaire.montant_fcfa,
        DotationBudgetaire.source_libre,
        DotationBudgetaire.statut_validation,
    ]
    form_columns = [
        DotationBudgetaire.exercice,
        DotationBudgetaire.ministere,
        DotationBudgetaire.montant_fcfa,
        DotationBudgetaire.document,
        DotationBudgetaire.source_libre,
        DotationBudgetaire.statut_validation,
    ]
    column_sortable_list = [DotationBudgetaire.exercice, DotationBudgetaire.montant_fcfa]
    column_default_sort = [("exercice", True), ("montant_fcfa", True)]
    icon = "fa-solid fa-sack-dollar"


class RepartitionAdmin(ValidationActionsMixin, ModelView, model=RepartitionBudgetaire):
    modele = RepartitionBudgetaire
    defaut_a_valider = False  # saisie manuelle
    name_plural = "Répartitions budgétaires (saisie)"
    column_list = [
        RepartitionBudgetaire.exercice,
        RepartitionBudgetaire.sens,
        RepartitionBudgetaire.libelle,
        RepartitionBudgetaire.montant_fcfa,
        RepartitionBudgetaire.source_libre,
        RepartitionBudgetaire.statut_validation,
    ]
    form_columns = [
        RepartitionBudgetaire.exercice,
        RepartitionBudgetaire.sens,
        RepartitionBudgetaire.libelle,
        RepartitionBudgetaire.montant_fcfa,
        RepartitionBudgetaire.document,
        RepartitionBudgetaire.source_libre,
        RepartitionBudgetaire.statut_validation,
    ]
    column_sortable_list = [RepartitionBudgetaire.exercice, RepartitionBudgetaire.montant_fcfa]
    column_default_sort = [("exercice", True), ("montant_fcfa", True)]
    icon = "fa-solid fa-chart-pie"


class MembreGouvernementAdmin(ValidationActionsMixin, ModelView, model=MembreGouvernement):
    modele = MembreGouvernement
    defaut_a_valider = False  # composition gérée à la main : tout afficher
    name_plural = "Gouvernement (composition)"
    column_list = [
        MembreGouvernement.ordre,
        MembreGouvernement.civilite,
        MembreGouvernement.nom_complet,
        MembreGouvernement.poste,
        MembreGouvernement.actif,
        MembreGouvernement.statut_validation,
    ]
    column_default_sort = ("ordre", False)
    icon = "fa-solid fa-landmark"


class PersonneAdmin(ModelView, model=Personne):
    column_list = [Personne.id, Personne.nom_complet, Personne.matricule, Personne.nom_normalise]
    column_searchable_list = [Personne.nom_complet, Personne.matricule]
    icon = "fa-solid fa-user"


class StructureAdmin(ModelView, model=Structure):
    column_list = [Structure.id, Structure.sigle, Structure.nom, Structure.type, Structure.canonique]
    column_searchable_list = [Structure.nom, Structure.sigle]
    form_columns = [Structure.nom, Structure.sigle, Structure.type, Structure.canonique]
    icon = "fa-solid fa-building-columns"


class MandatAdmin(ModelView, model=Mandat):
    column_list = [
        Mandat.id,
        Mandat.personne,
        Mandat.poste,
        Mandat.structure,
        Mandat.date_debut,
        Mandat.date_fin,
    ]
    icon = "fa-solid fa-id-badge"


class RunAdmin(ModelView, model=Run):
    name_plural = "Runs (journal d'ingestion)"
    column_list = [Run.id, Run.source, Run.debut, Run.fin, Run.statut, Run.nb_nouveaux, Run.nb_vus]
    column_default_sort = ("id", True)
    can_create = False
    can_edit = False
    icon = "fa-solid fa-clock-rotate-left"


# file de validation → (modèle, libellé, identity de la vue liste)
_FILES_VALIDATION = [
    (Nomination, "Nominations", "nomination"),
    (Decision, "Décisions", "decision"),
    (EngagementFinancier, "Engagements financiers", "engagement-financier"),
    (Marche, "Marchés publics", "marche"),
    (Realisation, "Infrastructures & inaugurations", "realisation"),
    (BudgetExercice, "Budgets d'exercice", "budget-exercice"),
]


_MODELES_PAR_CLE = {modele.__tablename__: modele for modele, _, _ in _FILES_VALIDATION}


def _seuil_demande(valeur: str | None) -> float:
    """Un seuil hors de [0, 1] n'a pas de sens : on le ramène plutôt que de
    renvoyer une erreur au milieu d'une file de validation."""
    try:
        seuil = float(str(valeur).replace(",", "."))
    except (TypeError, ValueError):
        return SEUIL_DEFAUT
    return min(max(seuil, 0.0), 1.0)


class AValiderView(BaseView):
    """Tableau de bord : ce qui attend une validation, par type, avec le
    nombre en attente, un accès direct à chaque file, et la validation en masse
    au-dessus d'un seuil de confiance.

    Le seuil existe parce que relire 8 000 nominations une par une n'est pas
    tenable : l'extraction note sa propre confiance, et au-dessus d'un seuil que
    l'administrateur choisit (et dont il voit l'effet AVANT de cliquer), le
    verdict humain n'apporte plus rien. Ce qui reste sous le seuil est
    exactement ce qui mérite un œil.
    """

    name = "① À valider"
    icon = "fa-solid fa-clipboard-check"

    @expose("/a-valider", methods=["GET", "POST"])
    async def page(self, request: Request):
        message = None
        if request.method == "POST":
            form = await request.form()
            seuil = _seuil_demande(form.get("seuil"))
            cles = [c for c in form.getlist("types") if c in _MODELES_PAR_CLE]
            sans_score = bool(form.get("sans_score"))
            if not cles:
                message = {
                    "niveau": "warning",
                    "texte": "Aucun type coché : rien n'a été validé.",
                }
            else:
                with SessionLocal() as db:
                    rapport = valider_par_seuil(
                        db,
                        seuil,
                        modeles=[_MODELES_PAR_CLE[c] for c in cles],
                        inclure_sans_score=sans_score,
                    )
                detail = ", ".join(
                    f"{ligne['valides']} {ligne['nom']}"
                    for ligne in rapport["lignes"]
                    if ligne["valides"]
                )
                texte = f"{rapport['total']} entité(s) validée(s) au seuil {seuil:g}"
                texte += f" ({detail})." if detail else "."
                if rapport["mandats"] is not None:
                    texte += f" Annuaire reconstruit : {rapport['mandats']} mandat(s)."
                message = {
                    "niveau": "success" if rapport["total"] else "info",
                    "texte": texte,
                }
        else:
            seuil = _seuil_demande(request.query_params.get("seuil"))
            sans_score = bool(request.query_params.get("sans_score"))
            cles = [c for c in request.query_params.getlist("types") if c in _MODELES_PAR_CLE]
            if not request.query_params.get("applique"):
                cles = list(_MODELES_PAR_CLE)

        lignes = []
        total = au_seuil = 0
        with SessionLocal() as db:
            for modele, libelle, identity in _FILES_VALIDATION:
                compte = compter_a_valider(db, modele, seuil)
                cle = modele.__tablename__
                coche = cle in cles
                total += compte["total"]
                if coche:
                    au_seuil += compte["au_seuil"] + (compte["sans_score"] if sans_score else 0)
                lignes.append(
                    {
                        "cle": cle,
                        "libelle": libelle,
                        "compte": compte["total"],
                        "au_seuil": compte["au_seuil"],
                        "sans_score": compte["sans_score"],
                        "coche": coche,
                        "url": request.url_for("admin:list", identity=identity),
                    }
                )
        return await self.templates.TemplateResponse(
            request,
            "a_valider.html",
            {
                "lignes": lignes,
                "total": total,
                "seuil": seuil,
                "sans_score": sans_score,
                "au_seuil": au_seuil,
                "message": message,
                "title": "À valider",
            },
        )


def mount_admin(app: FastAPI) -> None:
    admin = Admin(
        app,
        engine,
        title="Faso Données Publiques - Admin",
        authentication_backend=AdminAuth(secret_key=settings.secret_key),
    )
    admin.add_view(AValiderView)
    for view in (
        SourceAdmin,
        DocumentAdmin,
        DecisionAdmin,
        NominationAdmin,
        EngagementAdmin,
        BudgetAdmin,
        MarcheAdmin,
        AttributaireAdmin,
        RealisationAdmin,
        ProjetAdmin,
        DotationAdmin,
        RepartitionAdmin,
        MembreGouvernementAdmin,
        PersonneAdmin,
        StructureAdmin,
        MandatAdmin,
        LocaliteAdmin,
        RunAdmin,
    ):
        admin.add_view(view)
