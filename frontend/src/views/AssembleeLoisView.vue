<template>
  <h1>L'Assemblée législative</h1>
  <p class="sous-titre">
    Les lois votées par l'Assemblée, des plus récentes aux plus anciennes - textes issus de Légiburkina.
  </p>

  <nav class="onglets">
    <router-link to="/assemblee">Composition</router-link>
    <router-link to="/assemblee/lois" class="actif">Lois votées</router-link>
  </nav>

  <div class="filtres entete-recherche">
    <input
      v-model="q"
      type="search"
      placeholder="Rechercher une loi (ex : budget, minier, santé…)"
      @input="rechercherDebounce"
    />
    <span class="compteur" v-if="total !== null">{{ total.toLocaleString("fr-FR") }} lois</span>
  </div>

  <div class="liste">
    <article v-for="t in lois" :key="t.id" class="item">
      <div class="meta">
        <span class="badge">Loi</span>
        <span v-if="t.date_publication">{{ formatDate(t.date_publication) }}</span>
        <span v-if="t.secteur">{{ t.secteur }}</span>
      </div>
      <div class="titre">{{ t.reference ? `N° ${t.reference.replace(/^N°\s*/, "")}` : t.titre }}</div>
      <div v-if="t.description" class="detail">{{ majuscule(t.description) }}</div>
      <div class="meta" style="margin-top: 6px">
        <a class="source" :href="t.url_pdf" target="_blank" rel="noopener">Texte intégral (PDF) →</a>
        <a v-if="t.jo_url" class="source" :href="t.jo_url" target="_blank" rel="noopener">
          Journal officiel {{ t.jo_numero }} →
        </a>
      </div>
    </article>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!lois.length" class="vide">Aucune loi ne correspond à cette recherche.</p>

  <div class="pagination">
    <button :disabled="page <= 1" @click="page--; recharger()">← Précédent</button>
    <span>Page {{ page }}<template v-if="pages"> / {{ pages }}</template></span>
    <button :disabled="page >= pages" @click="page++; recharger()">Suivant →</button>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../api";

const PAR_PAGE = 20;
const lois = ref([]);
const total = ref(null);
const q = ref("");
const page = ref(1);
const chargement = ref(false);
let minuterie = null;

const pages = computed(() => (total.value ? Math.ceil(total.value / PAR_PAGE) : 0));

function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}
function majuscule(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

async function recharger() {
  chargement.value = true;
  try {
    const r = await apiGet("/textes", {
      q: q.value.length >= 2 ? q.value : undefined,
      type: "loi",
      page: page.value,
      par_page: PAR_PAGE,
    });
    lois.value = r.textes;
    total.value = r.total;
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
.entete-recherche input { flex: 1; max-width: 420px; }
.compteur { margin-left: auto; color: var(--text-muted); font-size: 0.88rem; }
</style>
