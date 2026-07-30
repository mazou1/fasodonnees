<template>
  <h1>Documents</h1>
  <p class="sous-titre">
    Les documents officiels collectés et archivés par la plateforme : comptes rendus du Conseil
    des ministres, lois et décrets, marchés publics et autres textes — chacun relié à sa source
    d'origine. Les articles de presse et communiqués sont dans les <router-link to="/actualites">Actualités</router-link>.
  </p>

  <div class="filtres entete-recherche">
    <input
      v-model="q"
      type="search"
      placeholder="Recherche plein texte…"
      @input="rechercherDebounce"
    />
    <select v-model="type" @change="page = 1; recharger()">
      <option value="">Tous les types</option>
      <option v-for="t in facettesTypes" :key="t.type_doc" :value="t.type_doc">
        {{ LIBELLES[t.type_doc] ?? t.type_doc }} ({{ t.n.toLocaleString("fr-FR") }})
      </option>
    </select>
    <select v-model="source" @change="page = 1; recharger()">
      <option value="">Toutes les sources</option>
      <option v-for="s in facettesSources" :key="s.slug" :value="s.slug">
        {{ s.nom }} ({{ s.n.toLocaleString("fr-FR") }})
      </option>
    </select>
    <span class="compteur" v-if="total !== null">{{ total.toLocaleString("fr-FR") }} documents</span>
  </div>

  <div class="liste">
    <article v-for="d in documents" :key="d.id" class="item">
      <div class="meta">
        <span class="badge">{{ LIBELLES[d.type_doc] ?? d.type_doc }}</span>
        <span v-if="d.date_publication">{{ formatDate(d.date_publication) }}</span>
        <span>{{ d.source_nom }}</span>
      </div>
      <div class="titre">{{ d.titre || d.url }}</div>
      <div class="meta" style="margin-top: 6px">
        <router-link v-if="d.type_doc === 'cr_conseil'" class="source" :to="`/conseils/${d.id}`">
          Voir sur Faso Données Publiques →
        </router-link>
        <a v-if="d.pdf" class="source" :href="`/api/documents/${d.id}/fichier`" target="_blank" rel="noopener">
          📄 PDF archivé →
        </a>
        <a class="source" :href="d.url" target="_blank" rel="noopener">Source d'origine →</a>
      </div>
    </article>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!documents.length" class="vide">Aucun document ne correspond à ces filtres.</p>

  <div class="pagination">
    <button :disabled="page <= 1" @click="page--; recharger()">← Précédent</button>
    <span>Page {{ page }}<template v-if="pages"> / {{ pages.toLocaleString("fr-FR") }}</template></span>
    <button :disabled="page >= pages" @click="page++; recharger()">Suivant →</button>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../api";

const LIBELLES = {
  cr_conseil: "Compte rendu CM",
  cr_conseil_traduction: "CR (langue nationale)",
  decret: "Décret",
  loi: "Loi",
  arrete: "Arrêté",
  ordonnance: "Ordonnance",
  charte: "Charte",
  constitution: "Constitution",
  texte_juridique: "Texte juridique",
  article_presse: "Article de presse",
  communique: "Communiqué",
  rapport: "Rapport",
  page_officielle: "Page officielle",
  marche_public: "Marchés publics (Quotidien)",
  decision_constitutionnelle: "Décision du Conseil constitutionnel",
  avis_constitutionnel: "Avis du Conseil constitutionnel",
  ordonnance_constitutionnelle: "Ordonnance du Conseil constitutionnel",
  rapport_controle: "Rapport de contrôle (ASCE-LC)",
  affaire_anticorruption: "Affaire anticorruption (ASCE-LC)",
  declaration_patrimoine: "Déclaration de patrimoine",
  plainte_denonciation: "Plaintes & dénonciations",
};
const PAR_PAGE = 20;

const documents = ref([]);
const total = ref(null);
const facettesTypes = ref([]);
const facettesSources = ref([]);
const q = ref("");
const type = ref("");
const source = ref("");
const page = ref(1);
const chargement = ref(false);
let minuterie = null;

const pages = computed(() => (total.value ? Math.ceil(total.value / PAR_PAGE) : 0));

function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

async function recharger() {
  chargement.value = true;
  try {
    const r = await apiGet("/documents", {
      q: q.value.length >= 2 ? q.value : undefined,
      type_doc: type.value,
      source: source.value,
      page: page.value,
      par_page: PAR_PAGE,
    });
    documents.value = r.documents;
    total.value = r.total;
    facettesTypes.value = r.types;
    facettesSources.value = r.sources;
  } finally {
    chargement.value = false;
  }
}

function rechercherDebounce() {
  clearTimeout(minuterie);
  minuterie = setTimeout(() => {
    page.value = 1;
    recharger();
  }, 350);
}

onMounted(recharger);
</script>

<style scoped>
.entete-recherche { align-items: center; }
.entete-recherche input[type="search"] { flex: 1; max-width: 340px; }
.compteur { margin-left: auto; color: var(--text-muted); font-size: 0.88rem; }
</style>
