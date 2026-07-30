<template>
  <h1>Actualités</h1>
  <p class="sous-titre">
    Le fil agrégé des médias burkinabè et des communiqués officiels - chaque article renvoie
    à sa source d'origine.
  </p>

  <div class="filtres">
    <select v-model="source" @change="page = 1; recharger()">
      <option value="">Toutes les sources</option>
      <option v-for="s in sources" :key="s.slug" :value="s.slug">{{ s.nom }}</option>
    </select>
  </div>

  <div class="liste">
    <article v-for="a in actualites" :key="a.id" class="item">
      <div class="meta">
        <span class="badge">{{ a.source_nom }}</span>
        <span v-if="a.type_doc === 'communique'">Communiqué officiel</span>
        <span v-if="a.date_publication">{{ formatDate(a.date_publication) }}</span>
      </div>
      <a class="titre" :href="a.url" target="_blank" rel="noopener" style="display: block">
        {{ a.titre }}
      </a>
      <div v-if="a.resume" class="detail">{{ a.resume }}</div>
    </article>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!actualites.length" class="vide">Aucun article pour cette source.</p>

  <div class="pagination">
    <button :disabled="page <= 1" @click="page--; recharger()">← Précédent</button>
    <span>Page {{ page }}</span>
    <button :disabled="actualites.length < PAR_PAGE" @click="page++; recharger()">Suivant →</button>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGet } from "../api";

const PAR_PAGE = 20;
const actualites = ref([]);
const sources = ref([]);
const source = ref("");
const page = ref(1);
const chargement = ref(false);

function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

async function recharger() {
  chargement.value = true;
  try {
    actualites.value = await apiGet("/actualites", {
      source: source.value,
      page: page.value,
      par_page: PAR_PAGE,
    });
  } finally {
    chargement.value = false;
  }
}

onMounted(async () => {
  const toutes = await apiGet("/sources");
  sources.value = toutes.filter((s) => s.type === "media" || s.slug === "presidence");
  await recharger();
});
</script>
