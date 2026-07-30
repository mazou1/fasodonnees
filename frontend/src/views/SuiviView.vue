<template>
  <h1>Suivi des annonces</h1>
  <p class="sous-titre">
    Ce que l'État annonce en Conseil des ministres, ce qu'il attribue dans le Quotidien des
    marchés publics, et ce qui est finalement livré - les trois réunis dans un même dossier.
    Aucune de ces sources ne porte d'identifiant de projet commun : chaque rapprochement a été
    relu à la main, et chaque maillon renvoie à son document officiel.
  </p>

  <div class="filtres entete-recherche">
    <input v-model="q" type="search" placeholder="Rechercher un dossier…" @input="rechercherDebounce" />
    <label>Stade
      <select v-model="stade" @change="charger">
        <option value="">Tous les stades</option>
        <option v-for="s in STADES" :key="s.cle" :value="s.cle">{{ s.libelle }}</option>
      </select>
    </label>
    <a class="export" :href="lienApi" title="Données via l'API">API</a>
  </div>

  <div v-if="projets.length" class="liste">
    <router-link v-for="p in projets" :key="p.id" :to="`/suivi/${p.id}`" class="item carte-projet">
      <div class="meta">
        <span class="badge" :class="`stade-${p.stade}`">{{ libelleStade(p.stade) }}</span>
        <span v-if="p.secteur" class="badge-secteur">{{ p.secteur }}</span>
        <span v-if="p.region">{{ p.region }}</span>
      </div>
      <div class="titre">{{ p.titre }}</div>

      <ol class="chaine" :aria-label="`Stade : ${libelleStade(p.stade)}`">
        <li
          v-for="s in STADES"
          :key="s.cle"
          :class="{ atteint: p.etapes_constatees.includes(s.cle) }"
          :title="p.etapes_constatees.includes(s.cle) ? `${s.libelle} - documenté` : `${s.libelle} - aucune pièce au dossier`"
        >
          <span class="puce" aria-hidden="true"></span>{{ s.libelle }}
        </li>
      </ol>

      <div class="montants">
        <span v-if="p.montant_annonce_fcfa">
          Annoncé : <strong>{{ fmtFCFA(p.montant_annonce_fcfa) }}</strong>
        </span>
        <span v-if="p.montant_attribue_fcfa">
          Attribué : <strong>{{ fmtFCFA(p.montant_attribue_fcfa) }}</strong>
        </span>
        <span class="pieces">
          {{ p.nb_annonces }} annonce{{ p.nb_annonces > 1 ? "s" : "" }} ·
          {{ p.nb_marches }} marché{{ p.nb_marches > 1 ? "s" : "" }} ·
          {{ p.nb_realisations }} réalisation{{ p.nb_realisations > 1 ? "s" : "" }}
        </span>
      </div>
    </router-link>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!projets.length" class="vide">
    Aucun dossier de suivi pour ce filtre.
  </p>

  <div v-if="pages > 1" class="pagination">
    <button :disabled="page <= 1" @click="page--; charger()">← Précédent</button>
    <span>Page {{ page }} / {{ pages }}</span>
    <button :disabled="page >= pages" @click="page++; charger()">Suivant →</button>
  </div>

  <p class="note-methode">
    Un dossier réunit des pièces venues de trois corpus distincts, sans identifiant partagé :
    le rapprochement est une <strong>interprétation</strong>, proposée automatiquement puis
    acceptée par un relecteur, jamais publiée d'office. Le stade affiché se déduit des pièces
    rattachées - une <em>première pierre</em> indique un chantier engagé, pas un ouvrage livré.
    Un dossier ne prétend pas retracer l'intégralité d'un projet : seuls y figurent les
    documents que la plateforme a collectés et validés.
  </p>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../api";

const PAR_PAGE = 20;
const STADES = [
  { cle: "annonce", libelle: "Annoncé" },
  { cle: "attribue", libelle: "Attribué" },
  { cle: "en_travaux", libelle: "En travaux" },
  { cle: "livre", libelle: "Livré" },
];

const projets = ref([]);
const total = ref(0);
const q = ref("");
const stade = ref("");
const page = ref(1);
const chargement = ref(false);
let minuterie = null;

const pages = computed(() => Math.ceil(total.value / PAR_PAGE));
const lienApi = computed(() => {
  const p = new URLSearchParams();
  if (stade.value) p.set("stade", stade.value);
  return "/api/projets" + (p.toString() ? "?" + p : "");
});

function libelleStade(cle) {
  return STADES.find((s) => s.cle === cle)?.libelle ?? cle;
}
function fmtFCFA(n) {
  if (n == null) return "-";
  if (n >= 1e9) return `${(n / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mds FCFA`;
  if (n >= 1e6) return `${(n / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M FCFA`;
  return `${n.toLocaleString("fr-FR")} FCFA`;
}

async function charger() {
  chargement.value = true;
  try {
    const r = await apiGet("/projets", {
      stade: stade.value || undefined,
      q: q.value.length >= 2 ? q.value : undefined,
      page: page.value,
      par_page: PAR_PAGE,
    });
    projets.value = r.projets;
    total.value = r.total;
  } finally {
    chargement.value = false;
  }
}

function rechercherDebounce() {
  clearTimeout(minuterie);
  minuterie = setTimeout(() => {
    page.value = 1;
    charger();
  }, 350);
}

onMounted(charger);
</script>

<style scoped>
.entete-recherche { align-items: flex-end; flex-wrap: wrap; gap: 12px; }
.entete-recherche input[type="search"] { flex: 1; max-width: 380px; }
.entete-recherche label { display: flex; flex-direction: column; font-size: 0.82rem; color: var(--text-secondary); gap: 4px; }

.carte-projet { display: block; text-decoration: none; color: inherit; }
.carte-projet:hover .titre { color: var(--accent); }
.badge-secteur { background: var(--series-1-fonce, #0a6b3c); color: #fff; padding: 1px 8px; border-radius: 999px; font-size: 0.72rem; }
.badge.stade-livre { background: color-mix(in srgb, #009e49 16%, transparent); color: #007a38; }
.badge.stade-en_travaux { background: color-mix(in srgb, #b8860b 18%, transparent); color: #8a6508; }
@media (prefers-color-scheme: dark) {
  .badge.stade-livre { color: #4ade80; }
  .badge.stade-en_travaux { color: #e3b341; }
}

.chaine { display: flex; flex-wrap: wrap; gap: 14px; list-style: none; padding: 0; margin: 10px 0 8px; }
.chaine li { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; color: var(--text-muted); }
.chaine .puce { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid currentColor; }
.chaine li.atteint { color: var(--accent); font-weight: 600; }
.chaine li.atteint .puce { background: currentColor; }

.montants { display: flex; flex-wrap: wrap; gap: 14px; font-size: 0.85rem; color: var(--text-secondary); }
.montants .pieces { color: var(--text-muted); }
.note-methode { color: var(--text-muted); font-size: 0.82rem; margin-top: 20px; line-height: 1.6; }
</style>
