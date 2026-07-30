import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import "./styles.css";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "accueil", component: () => import("./views/AccueilView.vue") },
    { path: "/recherche", name: "recherche", component: () => import("./views/RechercheView.vue") },
    { path: "/documents", name: "documents", component: () => import("./views/DocumentsView.vue") },
    { path: "/documents/:id", name: "document", component: () => import("./views/DocumentLectureView.vue") },
    { path: "/dossiers", name: "dossiers", component: () => import("./views/DossiersView.vue") },
    { path: "/dossiers/plan-relance", name: "dossier-plan-relance", component: () => import("./views/PlanRelanceView.vue") },
    { path: "/glossaire", name: "glossaire", component: () => import("./views/GlossaireView.vue") },
    { path: "/textes", name: "textes", component: () => import("./views/TextesView.vue") },
    { path: "/controle", name: "controle", component: () => import("./views/ControleView.vue") },
    { path: "/finances", name: "finances", component: () => import("./views/FinancesView.vue") },
    { path: "/infrastructures", name: "infrastructures", component: () => import("./views/InfrastructuresView.vue") },
    { path: "/marches", name: "marches", component: () => import("./views/MarchesView.vue") },
    { path: "/marches/statistiques", name: "marches-stats", component: () => import("./views/MarchesStatsView.vue") },
    { path: "/marches/entreprises/:id(\\d+)", name: "attributaire", component: () => import("./views/AttributaireView.vue") },
    { path: "/conseils", name: "conseils", component: () => import("./views/ConseilsView.vue") },
    { path: "/conseils/decisions", name: "decisions", component: () => import("./views/DecisionsView.vue") },
    { path: "/conseils/:id(\\d+)", name: "conseil", component: () => import("./views/ConseilDetailView.vue") },
    { path: "/decisions", redirect: "/conseils/decisions" },
    { path: "/actualites", name: "actualites", component: () => import("./views/ActualitesView.vue") },
    { path: "/gouvernement", name: "gouvernement", component: () => import("./views/GouvernementView.vue") },
    { path: "/assemblee", name: "assemblee", component: () => import("./views/AssembleeView.vue") },
    { path: "/assemblee/lois", name: "assemblee-lois", component: () => import("./views/AssembleeLoisView.vue") },
    { path: "/a-propos", name: "a-propos", component: () => import("./views/AProposView.vue") },
    { path: "/annuaire", name: "annuaire", component: () => import("./views/AnnuaireView.vue") },
    { path: "/annuaire/institutions/:id(\\d+)", name: "institution", component: () => import("./views/InstitutionView.vue") },
    { path: "/personnes/:id(\\d+)", name: "personne", component: () => import("./views/PersonneView.vue") },
    { path: "/annuaire/nominations", name: "nominations", component: () => import("./views/NominationsView.vue") },
    { path: "/nominations", redirect: "/annuaire/nominations" },
    { path: "/services-numeriques", name: "services-numeriques", component: () => import("./views/ServicesNumeriquesView.vue") },
  ],
  scrollBehavior: () => ({ top: 0 }),
});

createApp(App).use(router).mount("#app");
