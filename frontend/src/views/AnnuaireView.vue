<template>
  <h1>Annuaire de l'État</h1>
  <p class="sous-titre">
    Qui occupe quel poste, dans quelle institution - reconstitué à partir des nominations
    officielles en Conseil des ministres. Parcourez par institution ou cherchez une personne.
  </p>

  <nav class="onglets">
    <router-link to="/annuaire" class="actif">Annuaire</router-link>
    <router-link to="/annuaire/nominations">Nominations</router-link>
  </nav>

  <div class="filtres entete-recherche">
    <input v-model="q" type="search" placeholder="Une institution ou une personne…" @input="chercherDebounce" />
    <span class="compteur" v-if="!recherche && apercu">
      {{ apercu.total_institutions.toLocaleString("fr-FR") }} institutions ·
      {{ apercu.total_agents.toLocaleString("fr-FR") }} agents
    </span>
  </div>

  <!-- résultats de recherche -->
  <div v-if="recherche">
    <section v-if="instMatch.length">
      <h2 class="titre-groupe">Institutions</h2>
      <div class="grille-inst">
        <router-link
          v-for="i in instMatch" :key="i.id" class="carte inst"
          :to="`/annuaire/institutions/${i.id}`"
        >
          <span class="inst-nom">{{ i.sigle || i.nom }}</span>
          <span v-if="i.sigle" class="inst-sous">{{ i.nom }}</span>
          <span class="inst-n">
            {{ i.nb_agents }} agent{{ i.nb_agents > 1 ? "s" : "" }}
            <span v-if="i.intitules && i.intitules.length > 1" class="inst-renom"
              :title="i.intitules.join(' · ')">
              · {{ i.intitules.length }} intitulés
            </span>
          </span>
        </router-link>
      </div>
    </section>
    <section v-if="personnes.length">
      <h2 class="titre-groupe">Personnes</h2>
      <div class="grille-mandats">
        <article v-for="m in personnes" :key="m.id" class="carte mandat">
          <div class="avatar">{{ initiales(m.personne) }}</div>
          <div class="corps">
            <router-link class="nom" :to="`/personnes/${m.personne_id}`">{{ m.personne }}</router-link>
            <span class="matricule" v-if="m.matricule">Mle {{ m.matricule }}</span>
            <div class="poste">{{ m.poste }}<template v-if="m.structure"> - {{ m.structure }}</template></div>
          </div>
        </article>
      </div>
    </section>
    <p v-if="!chargement && !instMatch.length && !personnes.length" class="vide">
      Aucune institution ni personne pour « {{ q }} ».
    </p>
  </div>

  <!-- index par institution -->
  <div v-else-if="apercu">
    <section v-for="g in groupes" :key="g.libelle" v-show="g.items.length">
      <h2 class="titre-groupe">{{ g.libelle }} <span class="n-groupe">{{ g.items.length }}</span></h2>
      <div class="grille-inst">
        <router-link
          v-for="i in g.items" :key="i.id" class="carte inst"
          :to="`/annuaire/institutions/${i.id}`"
        >
          <span class="inst-nom">{{ i.sigle || i.nom }}</span>
          <span v-if="i.sigle" class="inst-sous">{{ i.nom }}</span>
          <span class="inst-n">
            {{ i.nb_agents }} agent{{ i.nb_agents > 1 ? "s" : "" }}
            <span v-if="i.intitules && i.intitules.length > 1" class="inst-renom"
              :title="i.intitules.join(' · ')">
              · {{ i.intitules.length }} intitulés
            </span>
          </span>
        </router-link>
      </div>
    </section>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../api";

const ORDRE_GROUPES = [
  "Ministères",
  "Présidence, Primature & institutions",
  "Justice & juridictions",
  "Régions, provinces & communes",
  "Directions territoriales de la police",
  "Représentations diplomatiques",
  "Établissements publics & sociétés d'État",
];

const apercu = ref(null);
const q = ref("");
const recherche = ref(false);
const instMatch = ref([]);
const personnes = ref([]);
const chargement = ref(false);
let minuterie = null;

const groupes = computed(() => {
  if (!apercu.value) return [];
  return ORDRE_GROUPES.map((libelle) => ({
    libelle,
    items: apercu.value.institutions.filter((i) => i.groupe === libelle),
  }));
});

function initiales(nom) {
  return (nom || "")
    .split(/\s+/).filter(Boolean).slice(0, 2)
    .map((x) => x[0]).join("").toUpperCase();
}

async function chargerIndex() {
  chargement.value = true;
  try {
    apercu.value = await apiGet("/annuaire/institutions");
  } finally {
    chargement.value = false;
  }
}

async function chercher() {
  const terme = q.value.trim();
  if (terme.length < 2) {
    recherche.value = false;
    instMatch.value = [];
    personnes.value = [];
    return;
  }
  recherche.value = true;
  chargement.value = true;
  try {
    const [inst, gens] = await Promise.all([
      apiGet("/annuaire/institutions", { q: terme }),
      apiGet("/annuaire", { q: terme, par_page: 30 }),
    ]);
    instMatch.value = inst.institutions;
    personnes.value = gens.mandats;
  } finally {
    chargement.value = false;
  }
}

function chercherDebounce() {
  clearTimeout(minuterie);
  minuterie = setTimeout(chercher, 300);
}

onMounted(chargerIndex);
</script>

<style scoped>
.entete-recherche { align-items: center; }
.entete-recherche input[type="search"] { flex: 1; max-width: 420px; }
.compteur { margin-left: auto; color: var(--text-muted); font-size: 0.88rem; }
.titre-groupe { font-size: 1rem; margin: 22px 0 12px; display: flex; align-items: baseline; gap: 8px; }
.n-groupe { color: var(--text-muted); font-size: 0.82rem; font-weight: 400; }
.grille-inst { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 12px; }
.carte.inst {
  display: flex; flex-direction: column; gap: 3px; padding: 14px 16px; text-decoration: none;
  border-left: 3px solid var(--series-1); transition: border-color 0.15s, transform 0.05s;
}
.carte.inst:hover { border-left-color: var(--accent); transform: translateY(-1px); }
.inst-nom { font-weight: 600; color: var(--text-primary); }
.inst-sous { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.3; }
.inst-n { font-size: 0.8rem; color: var(--accent); margin-top: 2px; }
.inst-renom { color: var(--text-muted); }
.grille-mandats { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.mandat { display: flex; gap: 14px; align-items: flex-start; padding: 14px 16px; }
.avatar {
  flex: none; width: 44px; height: 44px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent); font-weight: 700;
}
.corps { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.corps .nom { font-weight: 700; color: inherit; text-decoration: none; }
.corps .nom:hover { color: var(--accent); }
.matricule { font-size: 0.75rem; color: var(--text-muted); }
.poste { color: var(--text-secondary); font-size: 0.9rem; }
</style>
