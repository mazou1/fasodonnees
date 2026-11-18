<template>
  <h1>Lois & décrets</h1>
  <p class="sous-titre">
    Le droit burkinabè publié : décrets, lois, arrêtés et autres textes, avec leur PDF officiel
    et le Journal officiel de publication.
  </p>

  <div class="filtres entete-recherche">
    <input
      v-model="q"
      type="search"
      placeholder="Rechercher (ex : mine d'or, éducation, état d'urgence…)"
      @input="rechercherDebounce"
    />
    <select v-model="type" @change="page = 1; recharger()">
      <option value="">Tous les textes</option>
      <option value="decret">Décrets</option>
      <option value="loi">Lois</option>
      <option value="arrete">Arrêtés</option>
      <option value="ordonnance">Ordonnances</option>
      <option value="charte">Chartes</option>
      <option value="constitution">Constitution</option>
    </select>
    <span class="compteur" v-if="total !== null">{{ total.toLocaleString("fr-FR") }} textes</span>
  </div>

  <div class="grille-textes">
    <article v-for="t in textes" :key="t.id" class="carte-texte">
      <div class="bande">
        <span class="type">{{ LIBELLES[t.type_doc] ?? t.type_doc }}</span>
        <span class="date" v-if="t.date_publication">{{ formatDate(t.date_publication) }}</span>
      </div>
      <div class="corps">
        <div class="titre">{{ t.reference ? `N° ${t.reference.replace(/^N°\s*/, "")}` : t.titre }}</div>
        <div v-if="t.secteur" class="secteur">{{ t.secteur }}</div>
        <div v-if="t.description" class="description">{{ majuscule(t.description) }}</div>
        <div class="pied">
          <a v-if="t.url_pdf" :href="t.url_pdf" target="_blank" rel="noopener">{{ t.archive ? "Texte intégral (copie archivée)" : "Texte intégral (PDF)" }} →</a>
          <span v-else class="retire">Texte retiré de Légiburkina, non archivé</span>
          <a v-if="t.jo_url" :href="t.jo_url" target="_blank" rel="noopener">JO {{ t.jo_numero }} →</a>
        </div>
      </div>
    </article>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!textes.length" class="vide">Aucun texte ne correspond à cette recherche.</p>

  <div class="pagination">
    <button :disabled="page <= 1" @click="page--; recharger()">← Précédent</button>
    <span>Page {{ page }}<template v-if="pages"> / {{ pages }}</template></span>
    <button :disabled="page >= pages" @click="page++; recharger()">Suivant →</button>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../api";

const LIBELLES = {
  decret: "Décret",
  loi: "Loi",
  arrete: "Arrêté",
  ordonnance: "Ordonnance",
  charte: "Charte",
  constitution: "Constitution",
  texte_juridique: "Texte",
};
const PAR_PAGE = 20;

const textes = ref([]);
const total = ref(null);
const q = ref("");
const type = ref("");
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
      type: type.value,
      page: page.value,
      par_page: PAR_PAGE,
    });
    textes.value = r.textes;
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
.entete-recherche input[type="search"] { flex: 1; max-width: 420px; }
.compteur { margin-left: auto; color: var(--text-muted); font-size: 0.88rem; }

.grille-textes { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 12px; }
@media (max-width: 480px) { .grille-textes { grid-template-columns: 1fr; } }
.carte-texte {
  border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
  background: var(--surface-1); display: flex; flex-direction: column;
}
.bande {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 16px; color: #fff; font-size: 0.8rem;
  background: linear-gradient(135deg, var(--series-1-fonce), var(--series-1));
  border-bottom: 2px solid;
  border-image: linear-gradient(90deg, #ce1126 50%, #009e49 50%) 1;
}
.bande .type { font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }
.bande .date { opacity: 0.9; }
.corps { padding: 12px 16px 14px; display: flex; flex-direction: column; flex: 1; }
.corps .titre { font-weight: 700; }
.secteur { color: var(--text-muted); font-size: 0.8rem; margin-top: 2px; }
.description {
  color: var(--text-secondary); font-size: 0.9rem; margin-top: 6px;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.pied { display: flex; gap: 14px; margin-top: auto; padding-top: 10px; font-size: 0.88rem; }
</style>
