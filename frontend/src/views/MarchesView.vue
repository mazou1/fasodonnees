<template>
  <h1>Marchés publics</h1>
  <p class="sous-titre">
    Qui décroche les marchés de l'État, pour quel montant - les attributions extraites du
    <a href="https://www.dgcmef.gov.bf" target="_blank" rel="noopener">Quotidien des Marchés Publics</a>
    (DGCMEF). Chaque marché renvoie au journal officiel dont il est issu.
  </p>

  <nav class="onglets">
    <router-link to="/marches" class="actif">Liste</router-link>
    <router-link to="/marches/statistiques">Statistiques</router-link>
  </nav>

  <div v-if="stats" class="grille-tuiles">
    <div class="carte tuile">
      <div class="valeur">{{ fmtFCFA(stats.montant) }}</div>
      <div class="libelle">{{ nature === "preselection" ? "total (les présélections n'ont pas de montant)" : "total des marchés attribués" }}</div>
    </div>
    <div class="carte tuile">
      <div class="valeur">{{ stats.total.toLocaleString("fr-FR") }}</div>
      <div class="libelle">{{ nature === "preselection" ? "présélections recensées" : "marchés recensés" }}</div>
    </div>
    <!-- le plus gros marché est une attribution : l'afficher à côté d'un total
         de présélections à 0 FCFA laisserait croire qu'il en fait partie -->
    <div class="carte tuile" v-if="plusGros && nature !== 'preselection'">
      <div class="valeur">{{ fmtFCFA(plusGros.montant_fcfa) }}</div>
      <div class="libelle">plus gros marché ({{ plusGros.attributaire }})</div>
    </div>
  </div>

  <div class="filtres entete-recherche">
    <input v-model="q" type="search" placeholder="Attributaire, autorité, objet…" @input="rechercherDebounce" />
    <select v-model="tri" @change="page = 1; recharger()">
      <option value="montant">Par montant</option>
      <option value="date">Par date</option>
    </select>
    <select v-model="nature" @change="page = 1; recharger()" title="Une manifestation d'intérêt présélectionne un candidat sans lui attribuer de contrat">
      <option value="attribution">Attributions</option>
      <option value="preselection">Présélections</option>
      <option value="toutes">Les deux</option>
    </select>
    <a class="export" href="/api/marches?tri=montant&par_page=100" title="Données via l'API">API</a>
  </div>

  <div class="liste">
    <article v-for="m in marches" :key="m.id" class="item">
      <div class="meta">
        <span class="badge" :class="{ 'badge-preselection': m.nature === 'preselection' }">
          {{ m.nature === "preselection" ? "Présélection" : "Marché attribué" }}
        </span>
        <span v-if="m.secteur" class="badge-secteur">{{ m.secteur }}</span>
        <span v-if="m.date">Quotidien du {{ formatDate(m.date) }}</span>
        <span v-if="m.autorite">{{ m.autorite }}</span>
      </div>
      <div class="titre">
        <!-- une présélection n'a pas de montant : afficher « - » à sa place
             laisserait croire à une donnée manquante -->
        <template v-if="m.nature !== 'preselection'">{{ fmtFCFA(m.montant_fcfa) }}<template v-if="m.attributaire"> - </template></template>
        <template v-if="m.attributaire">
          <router-link v-if="m.attributaire_id" :to="`/marches/entreprises/${m.attributaire_id}`">{{ m.attributaire }}</router-link>
          <template v-else>{{ m.attributaire }}</template>
        </template>
      </div>
      <p v-if="m.nature === 'preselection'" class="detail-preselection">
        Candidat retenu à l'issue d'un avis à manifestation d'intérêt : le marché
        n'est pas encore attribué et le montant reste à négocier.
      </p>
      <div class="detail">{{ m.objet }}</div>
      <ContexteSource genre="marche" :id="m.id" libelle="le Quotidien officiel" />
      <div class="meta" style="margin-top: 4px">
        <span v-if="m.reference" class="ref">{{ m.reference }}</span>
        <a class="source" :href="`/api/documents/${m.document_id}/fichier`" target="_blank" rel="noopener">
          Quotidien officiel (PDF) →
        </a>
      </div>
    </article>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!marches.length" class="vide">Aucun marché ne correspond à cette recherche.</p>

  <div class="pagination">
    <button :disabled="page <= 1" @click="page--; recharger()">← Précédent</button>
    <span>Page {{ page }}<template v-if="pages"> / {{ pages }}</template></span>
    <button :disabled="page >= pages" @click="page++; recharger()">Suivant →</button>
  </div>

  <p class="note-methode">
    Extraction automatique des synthèses de résultats du Quotidien des Marchés Publics ;
    en cas de doute, le journal officiel fait foi.
  </p>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../api";
import ContexteSource from "../components/ContexteSource.vue";

const PAR_PAGE = 20;
// la fiche entreprise renvoie ici avec ?nature=preselection&q=… : sans lire la
// query, le lien retomberait sur la liste des attributions
const route = useRoute();
const marches = ref([]);
const stats = ref(null);
const plusGros = ref(null);
const q = ref(route.query.q ? String(route.query.q) : "");
const tri = ref("montant");
// attribution | preselection | toutes - les statistiques du site ne comptent que
// les attributions, la liste doit s'aligner par défaut
const nature = ref(
  ["preselection", "toutes"].includes(String(route.query.nature))
    ? String(route.query.nature)
    : "attribution",
);
const page = ref(1);
const chargement = ref(false);
let minuterie = null;

const pages = computed(() => (stats.value ? Math.ceil(stats.value.total / PAR_PAGE) : 0));

function fmtFCFA(n) {
  if (n == null) return "-";
  if (n >= 1e9) return `${(n / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mds FCFA`;
  if (n >= 1e6) return `${(n / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M FCFA`;
  return `${n.toLocaleString("fr-FR")} FCFA`;
}
function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

async function recharger() {
  chargement.value = true;
  try {
    const r = await apiGet("/marches", {
      q: q.value.length >= 2 ? q.value : undefined,
      tri: tri.value,
      nature: nature.value,
      page: page.value,
      par_page: PAR_PAGE,
    });
    marches.value = r.marches;
    stats.value = { total: r.total, montant: r.montant_total_fcfa };
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

onMounted(async () => {
  const top = await apiGet("/marches", { tri: "montant", par_page: 1 });
  plusGros.value = top.marches[0] ?? null;
  await recharger();
});
</script>

<style scoped>
.entete-recherche { align-items: center; }
.entete-recherche input[type="search"] { flex: 1; max-width: 380px; }
.badge-secteur { background: var(--series-1-fonce, #0a6b3c); color: #fff; padding: 1px 8px; border-radius: 999px; font-size: 0.72rem; }
.badge-preselection { background: var(--surface-alt, #e8e4da); color: var(--text-muted, #5a5a5a); }
.detail-preselection { color: var(--text-muted); font-size: 0.85rem; margin: 4px 0 0; }
.ref { font-variant-numeric: tabular-nums; }
.note-methode { color: var(--text-muted); font-size: 0.82rem; margin-top: 16px; }
</style>
