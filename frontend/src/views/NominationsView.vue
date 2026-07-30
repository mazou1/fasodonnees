<template>
  <h1>Annuaire de l'État</h1>
  <p class="sous-titre">
    Le flux des nominations officielles en Conseil des ministres, chacune reliée à son compte rendu.
  </p>

  <nav class="onglets">
    <router-link to="/annuaire">Annuaire</router-link>
    <router-link to="/annuaire/nominations" class="actif">Nominations</router-link>
  </nav>

  <div class="filtres entete-recherche">
    <input
      v-model="q"
      type="search"
      placeholder="Rechercher une personne (ex : SABO, OUEDRAOGO…)"
      @input="rechercherDebounce"
    />
    <span class="compteur" v-if="total !== null">
      {{ total.toLocaleString("fr-FR") }} nominations
      <a class="export" href="/api/export/nominations.csv" title="Télécharger toutes les nominations (CSV)">⬇ CSV</a>
    </span>
  </div>

  <div class="liste">
    <article v-for="n in nominations" :key="n.id" class="item">
      <div class="meta">
        <span class="badge">{{ n.type === "fin_fonction" ? "Fin de fonction" : "Nomination" }}</span>
        <span v-if="n.date_conseil">Conseil du {{ formatDate(n.date_conseil) }}</span>
      </div>
      <div class="titre">
        <router-link class="lien-personne" :to="`/personnes/${n.personne_id}`">{{ n.personne }}</router-link>
      </div>
      <div class="detail">
        {{ n.poste }}<template v-if="n.structure"> - {{ n.structure }}</template>
      </div>
      <a class="source" :href="n.document_url" target="_blank" rel="noopener">Voir le compte rendu officiel →</a>
    </article>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!nominations.length" class="vide">Aucune nomination trouvée.</p>

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
const nominations = ref([]);
const total = ref(null);
const q = ref("");
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
    const r = await apiGet("/nominations", { q: q.value, page: page.value, par_page: PAR_PAGE });
    nominations.value = r.nominations;
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
.lien-personne { color: inherit; text-decoration: none; }
.lien-personne:hover { color: var(--accent); }
</style>
