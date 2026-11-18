<template>
  <h1>L'Assemblée législative</h1>
  <p class="sous-titre">
    Les textes soumis au vote des députés en séance plénière, des plus récents aux plus anciens -
    tirés des comptes rendus de séance de l'Assemblée.
  </p>

  <nav class="onglets">
    <router-link to="/assemblee">Composition</router-link>
    <router-link to="/assemblee/votes" class="actif">Votes en plénière</router-link>
    <router-link to="/assemblee/lois">Lois votées</router-link>
  </nav>

  <div class="filtres entete-recherche">
    <input
      v-model="q"
      type="search"
      placeholder="Rechercher un texte (ex : finances, ratification, mines…)"
      @input="rechercherDebounce"
    />
    <select v-model="annee" @change="page = 1; recharger()">
      <option value="">Toutes les années</option>
      <option v-for="a in annees" :key="a.annee" :value="a.annee">{{ a.annee }} ({{ a.nombre }})</option>
    </select>
    <select v-model="nature" @change="page = 1; recharger()">
      <option value="">Toutes les natures</option>
      <option v-for="n in natures" :key="n.code" :value="n.code">{{ n.libelle }} ({{ n.nombre }})</option>
    </select>
    <span class="compteur" v-if="total !== null">{{ total.toLocaleString("fr-FR") }} texte{{ total > 1 ? "s" : "" }}</span>
  </div>

  <div class="liste">
    <article v-for="v in votes" :key="v.id" class="item">
      <div class="meta">
        <span class="badge">{{ v.nature_libelle }}</span>
        <span v-if="v.date_seance">Séance du {{ formatDate(v.date_seance) }}</span>
        <span class="resultat" :class="v.resultat">{{ v.resultat === "rejete" ? "Rejeté" : "Adopté" }}</span>
      </div>
      <div class="titre">{{ titre(v) }}</div>
      <div v-if="v.resume" class="detail">{{ v.resume }}</div>
      <div class="scrutin" v-if="scrutin(v)">{{ scrutin(v) }}</div>
      <div class="meta" style="margin-top: 6px">
        <span v-if="v.commission">Commission : {{ v.commission }}</span>
        <span v-if="v.presente_par">Défendu par {{ v.presente_par }}</span>
        <a class="source" :href="v.source_url" target="_blank" rel="noopener">Compte rendu de séance →</a>
      </div>
    </article>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!votes.length" class="vide">Aucun texte ne correspond à cette recherche.</p>

  <div class="pagination" v-if="pages > 1">
    <button :disabled="page <= 1" @click="page--; recharger()">← Précédent</button>
    <span>Page {{ page }} / {{ pages }}</span>
    <button :disabled="page >= pages" @click="page++; recharger()">Suivant →</button>
  </div>

  <p class="note-methode">
    Ces votes sont extraits automatiquement des comptes rendus publiés par l'Assemblée, puis
    relus avant publication. Le décompte des voix n'apparaît que lorsque le compte rendu le
    donne : « adopté à l'unanimité » sans chiffre reste sans chiffre. Pour le texte promulgué,
    voir l'onglet « Lois votées ».
  </p>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../api";

const PAR_PAGE = 20;
const votes = ref([]);
const annees = ref([]);
const natures = ref([]);
const total = ref(null);
const q = ref("");
const annee = ref("");
const nature = ref("");
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

/** Certains comptes rendus ne nomment le texte que par « portant… » : on lui
    rend alors sa nature, sans quoi le titre commence au milieu d'une phrase. */
function titre(v) {
  return /^(portant|relatif|relative)\b/i.test(v.intitule)
    ? `${v.nature_libelle} ${v.intitule}`
    : majuscule(v.intitule);
}

/** Ce que le compte rendu dit du scrutin, sans rien compléter. */
function scrutin(v) {
  const morceaux = [];
  if (v.unanimite) morceaux.push(v.votants ? `À l'unanimité des ${v.votants} votants` : "À l'unanimité");
  else if (v.votants) morceaux.push(`${v.votants} votants`);
  if (!v.unanimite) {
    if (v.pour !== null) morceaux.push(`${v.pour} pour`);
    if (v.contre !== null) morceaux.push(`${v.contre} contre`);
    if (v.abstentions !== null) morceaux.push(`${v.abstentions} abstention${v.abstentions > 1 ? "s" : ""}`);
  }
  return morceaux.join(" · ");
}

async function recharger() {
  chargement.value = true;
  try {
    const r = await apiGet("/assemblee/votes", {
      q: q.value.length >= 2 ? q.value : undefined,
      annee: annee.value || undefined,
      nature: nature.value || undefined,
      page: page.value,
      par_page: PAR_PAGE,
    });
    votes.value = r.votes;
    total.value = r.total;
    annees.value = r.annees;
    natures.value = r.natures;
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
.resultat { font-weight: 600; }
.resultat.adopte { color: #00713a; }
.resultat.rejete { color: #b3261e; }
.scrutin { margin-top: 6px; font-weight: 600; font-size: 0.92rem; font-variant-numeric: tabular-nums; }
.note-methode {
  margin-top: 30px; color: var(--text-muted); font-size: 0.86rem;
  border-top: 1px solid var(--border); padding-top: 16px; line-height: 1.55;
}
</style>
