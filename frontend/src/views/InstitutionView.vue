<template>
  <p class="fil"><router-link to="/annuaire">← Annuaire de l'État</router-link></p>

  <div v-if="inst">
    <h1>{{ inst.sigle || inst.nom }}</h1>
    <p class="sous-titre">
      <span class="badge-type">{{ libelleType(inst.type) }}</span>
      <span v-if="inst.sigle" class="sigle">{{ inst.nom }}</span>
      · {{ inst.nb_agents.toLocaleString("fr-FR") }} en fonction<template v-if="inst.nb_anciens">
        · {{ inst.nb_anciens.toLocaleString("fr-FR") }} ancien{{ inst.nb_anciens > 1 ? "s" : "" }}</template>
    </p>
    <p v-if="lienAlerteInstitution(inst.id)" style="margin: -6px 0 14px">
      <a class="alerte" :href="lienAlerteInstitution(inst.id)" target="_blank" rel="noopener"
         title="Être prévenu sur Telegram des nominations dans cette institution">🔔 Recevoir une alerte</a>
    </p>

    <label v-if="inst.nb_anciens" class="bascule-anciens">
      <input type="checkbox" v-model="montrerAnciens" />
      Afficher les anciens titulaires
    </label>

    <aside v-if="inst.intitules && inst.intitules.length > 1" class="carte intitules">
      <h2>Intitulés successifs</h2>
      <p class="note">
        Ce portefeuille a été renommé au fil des remaniements. Les agents ci-dessous
        sont regroupés à travers tous ses intitulés, du plus récent au plus ancien.
        <template v-if="inst.intitule_officiel">
          L'intitulé en tête est celui du gouvernement en fonction ; les suivants sont
          ceux sous lesquels les nominations ont été publiées.
        </template>
        <template v-else>
          Ce portefeuille n'apparaît pas dans le gouvernement en fonction : l'intitulé
          en tête est le dernier attesté par une nomination.
        </template>
      </p>
      <ol>
        <li v-for="(n, idx) in inst.intitules" :key="n">
          {{ n }}
          <span v-if="idx === 0" class="courant">
            {{ inst.intitule_officiel ? "intitulé en vigueur" : "dernier intitulé attesté" }}
          </span>
        </li>
      </ol>
    </aside>

    <section v-for="c in categoriesAffichees" :key="c.categorie" class="carte cat">
      <h2>{{ c.categorie }} <span class="n-cat">{{ c.agents.length }}</span></h2>
      <ul class="agents">
        <li v-for="(a, idx) in c.agents" :key="a.personne_id + '-' + idx" :class="{ ancien: !a.en_fonction }">
          <div class="avatar">{{ initiales(a.personne) }}</div>
          <div class="corps">
            <router-link class="nom" :to="`/personnes/${a.personne_id}`">{{ a.personne }}</router-link>
            <span v-if="a.matricule" class="matricule">Mle {{ a.matricule }}</span>
            <span v-if="!a.en_fonction" class="badge-ancien">Ancien</span>
            <div class="poste">{{ a.poste }}</div>
            <div class="dates" v-if="a.date_debut">
              <template v-if="a.en_fonction">En poste depuis le {{ formatDate(a.date_debut) }}</template>
              <template v-else>En poste du {{ formatDate(a.date_debut) }} au {{ formatDate(a.date_fin) }}</template>
              <a v-if="a.document_url" :href="a.document_url" target="_blank" rel="noopener"> · compte rendu →</a>
            </div>
          </div>
        </li>
      </ul>
    </section>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!inst" class="vide">Institution introuvable.</p>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../api";
import { chargerAlertes, lienAlerteInstitution } from "../alertes";

const route = useRoute();
chargerAlertes(); // nom du bot Telegram, pour le lien « Recevoir une alerte »
const inst = ref(null);
const chargement = ref(false);
const montrerAnciens = ref(false);

// masque les anciens titulaires par défaut ; retire les catégories vidées
const categoriesAffichees = computed(() => {
  if (!inst.value) return [];
  if (montrerAnciens.value) return inst.value.categories;
  return inst.value.categories
    .map((c) => ({ categorie: c.categorie, agents: c.agents.filter((a) => a.en_fonction) }))
    .filter((c) => c.agents.length);
});

const TYPES = {
  ministere: "Ministère",
  institution: "Institution",
  juridiction: "Juridiction",
  territoriale: "Région / province / commune",
  police: "Direction territoriale de la police",
  diplomatique: "Représentation diplomatique",
  etablissement: "Établissement / société d'État",
};
function libelleType(t) {
  return TYPES[t] || "Institution";
}
function initiales(nom) {
  return (nom || "").split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0]).join("").toUpperCase();
}
function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

async function charger() {
  chargement.value = true;
  inst.value = null;
  try {
    inst.value = await apiGet(`/annuaire/institutions/${route.params.id}`);
  } catch {
    inst.value = null;
  } finally {
    chargement.value = false;
  }
}

onMounted(charger);
watch(() => route.params.id, charger);
</script>

<style scoped>
.fil { margin-bottom: 6px; }
.fil a { color: var(--text-secondary); text-decoration: none; font-size: 0.9rem; }
.fil a:hover { color: var(--accent); }
.badge-type { background: var(--series-1-fonce, #0a6b3c); color: #fff; padding: 1px 8px; border-radius: 999px; font-size: 0.74rem; }
.sigle { font-weight: 600; }
.bascule-anciens {
  display: inline-flex; align-items: center; gap: 6px; margin-bottom: 14px;
  font-size: 0.85rem; color: var(--text-secondary); cursor: pointer;
}
.badge-ancien {
  align-self: flex-start; margin: 1px 0; padding: 0 7px; border-radius: 999px;
  font-size: 0.68rem; background: color-mix(in srgb, var(--text-muted) 22%, transparent);
  color: var(--text-secondary);
}
.agents li.ancien { opacity: 0.62; }
.intitules { margin-bottom: 16px; }
.intitules h2 { font-size: 0.95rem; margin: 0 0 6px; }
.intitules .note { color: var(--text-secondary); font-size: 0.85rem; margin: 0 0 8px; }
.intitules ol { margin: 0; padding-left: 20px; font-size: 0.9rem; }
.intitules li { margin-bottom: 3px; }
.courant {
  margin-left: 8px; padding: 1px 7px; border-radius: 999px; font-size: 0.72rem;
  background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent);
}
.cat { margin-bottom: 16px; }
.cat h2 { font-size: 1rem; margin: 0 0 12px; display: flex; align-items: baseline; gap: 8px; }
.n-cat { color: var(--text-muted); font-size: 0.82rem; font-weight: 400; }
.agents { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px 18px; }
.agents li { display: flex; gap: 12px; align-items: flex-start; }
.avatar {
  flex: none; width: 38px; height: 38px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent); font-weight: 700; font-size: 0.85rem;
}
.corps { min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.corps .nom { font-weight: 600; color: inherit; text-decoration: none; }
.corps .nom:hover { color: var(--accent); }
.matricule { font-size: 0.72rem; color: var(--text-muted); }
.poste { font-size: 0.86rem; color: var(--text-secondary); }
.dates { font-size: 0.78rem; color: var(--text-muted); }
</style>
