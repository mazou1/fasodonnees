<template>
  <h1>Conseil des ministres</h1>
  <p class="sous-titre">
    Chaque conseil, avec son compte rendu intégral et ce qui y a été décidé :
    délibérations, nominations et engagements financiers.
  </p>

  <nav class="onglets">
    <router-link to="/conseils" class="actif">Comptes rendus</router-link>
    <router-link to="/conseils/decisions">Décisions</router-link>
  </nav>

  <div class="filtres entete-recherche">
    <input v-model="q" type="search" placeholder="Rechercher un compte rendu…" @input="rechercherDebounce" />
    <span class="compteur" v-if="total !== null">{{ total.toLocaleString("fr-FR") }} communiqués</span>
  </div>

  <div class="grille-cm">
    <router-link v-for="c in conseils" :key="c.id" :to="`/conseils/${c.id}`" class="carte-cm">
      <div class="bandeau">
        <div class="sur-titre">Compte rendu · Conseil des ministres</div>
        <div class="grande-date" v-if="c.date_conseil">
          <span class="jour">{{ jour(c.date_conseil) }}</span>
          <span class="mois">{{ moisAnnee(c.date_conseil) }}</span>
        </div>
        <span class="numero" v-if="numero(c)">{{ numero(c) }}</span>
      </div>
      <div class="corps">
        <div class="titre">{{ titreCourt(c) }}</div>
        <div class="detail">
          <template v-if="c.decisions || c.nominations">
            {{ c.decisions }} décision{{ c.decisions > 1 ? "s" : "" }} ·
            {{ c.nominations }} nomination{{ c.nominations > 1 ? "s" : "" }}
            <template v-if="c.engagements"> · {{ c.engagements }} engagement{{ c.engagements > 1 ? "s" : "" }}</template>
          </template>
          <span v-else class="en-attente">Extraction en cours de relecture</span>
        </div>
        <!-- La source réécrit ses comptes rendus après publication : on le dit
             plutôt que de servir la dernière version comme si rien n'avait
             bougé. La date est celle du CONSTAT, pas de la retouche. -->
        <div v-if="c.nb_versions > 1" class="reecriture" :title="`${c.nb_versions} versions de ce compte rendu sont archivées`">
          ✎ Réécrit par la source — constaté le {{ formatDate(c.modification_constatee_le) }}
        </div>
      </div>
    </router-link>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!conseils.length" class="vide">Aucun conseil à afficher.</p>

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
const conseils = ref([]);
const total = ref(null);
const q = ref("");
const page = ref(1);
const chargement = ref(false);
let minuterie = null;

const pages = computed(() => (total.value ? Math.ceil(total.value / PAR_PAGE) : 0));

function jour(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric" });
}
function moisAnnee(d) {
  return new Date(d).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
}
function formatDate(d) {
  return d
    ? new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })
    : "";
}
function numero(c) {
  const m = (c.titre || "").match(/N[°o]\s*0*(\d+)/i);
  return m ? `N° ${m[1]}` : "";
}
function titreCourt(c) {
  return (c.titre || "Conseil des ministres").replace(/^CONSEIL DES MINISTRES\s*/i, "Conseil des ministres ");
}

async function recharger() {
  chargement.value = true;
  try {
    const r = await apiGet("/conseils", {
      q: q.value.length >= 2 ? q.value : undefined,
      page: page.value,
      par_page: PAR_PAGE,
    });
    conseils.value = r.conseils;
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
.entete-recherche input { flex: 1; max-width: 480px; }
.compteur { color: var(--text-muted); font-size: 0.88rem; }

.grille-cm { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.carte-cm {
  display: block; border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
  background: var(--surface-1); text-decoration: none; color: inherit;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.carte-cm:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08); }

.bandeau {
  position: relative; padding: 18px 18px 14px; color: #fff; min-height: 96px;
  background:
    radial-gradient(120% 160% at 100% 0%, rgba(255, 255, 255, 0.16), transparent 55%),
    linear-gradient(135deg, var(--series-1-fonce), var(--series-1));
  /* clin d'œil au drapeau : liseré rouge → vert */
  border-bottom: 3px solid;
  border-image: linear-gradient(90deg, #ce1126 50%, #009e49 50%) 1;
}
.sur-titre { font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.85; }
.grande-date { display: flex; align-items: baseline; gap: 8px; margin-top: 8px; }
.grande-date .jour { font-size: 2.1rem; font-weight: 800; line-height: 1; }
.grande-date .mois { font-size: 1.02rem; font-weight: 600; text-transform: capitalize; }
.numero {
  position: absolute; top: 14px; right: 14px; font-size: 0.78rem; font-weight: 700;
  background: rgba(255, 255, 255, 0.18); padding: 2px 9px; border-radius: 999px;
}
.corps { padding: 12px 18px 14px; }
.corps .titre { font-weight: 600; line-height: 1.3; }
.corps .detail { color: var(--text-secondary); font-size: 0.88rem; margin-top: 4px; }
.corps .en-attente { font-style: italic; }
.corps .reecriture {
  margin-top: 6px; font-size: 0.78rem; color: var(--text-muted);
  display: flex; align-items: baseline; gap: 5px;
}
</style>
