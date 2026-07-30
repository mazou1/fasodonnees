<template>
  <h1>Marchés publics</h1>
  <p class="sous-titre">
    Qui décroche les marchés de l'État, par secteur et par année — statistiques agrégées
    des attributions du <a href="https://www.dgcmef.gov.bf" target="_blank" rel="noopener">Quotidien des Marchés Publics</a> (DGCMEF).
  </p>

  <nav class="onglets">
    <router-link to="/marches">Liste</router-link>
    <router-link to="/marches/statistiques" class="actif">Statistiques</router-link>
  </nav>

  <div class="filtres entete-recherche">
    <label>Secteur
      <select v-model="secteur" @change="charger">
        <option value="">Tous les secteurs</option>
        <option v-for="s in secteursDispo" :key="s" :value="s">{{ s }}</option>
      </select>
    </label>
    <label>Année
      <select v-model="annee" @change="charger">
        <option value="">Toutes les années</option>
        <option v-for="a in annees" :key="a" :value="a">{{ a }}</option>
      </select>
    </label>
    <button v-if="secteur || annee" class="raz" @click="secteur = ''; annee = ''; charger()">Réinitialiser</button>
    <a class="export" :href="lienApi" title="Données via l'API">API</a>
  </div>

  <div v-if="stats" class="grille-tuiles">
    <div class="carte tuile">
      <div class="valeur">{{ fmtFCFA(stats.montant_total_fcfa) }}</div>
      <div class="libelle">montant total attribué</div>
    </div>
    <div class="carte tuile">
      <div class="valeur">{{ stats.total.toLocaleString("fr-FR") }}</div>
      <div class="libelle">marchés</div>
    </div>
    <div class="carte tuile">
      <div class="valeur">{{ stats.nb_entreprises.toLocaleString("fr-FR") }}</div>
      <div class="libelle">entreprises attributaires</div>
    </div>
  </div>

  <div v-if="stats" class="grille-graphes">
    <section class="carte bloc-graphe">
      <h2>Montant attribué par secteur</h2>
      <div ref="elSecteurs" class="canvas" :style="hauteur(stats.par_secteur.length)"></div>
    </section>
    <section class="carte bloc-graphe">
      <h2>Attributions par année</h2>
      <div ref="elAnnees" class="canvas" style="height: 260px"></div>
    </section>
    <section class="carte bloc-graphe">
      <h2>Top 15 des entreprises{{ secteur ? " — " + secteur : "" }}</h2>
      <div ref="elEntreprises" class="canvas" :style="hauteur(stats.top_entreprises.length)"></div>
    </section>
  </div>

  <section v-if="stats" class="carte">
    <h2>Détail par secteur</h2>
    <table class="tableau">
      <thead>
        <tr><th>Secteur</th><th class="num">Marchés</th><th class="num">Montant</th><th class="num">Part</th></tr>
      </thead>
      <tbody>
        <tr v-for="s in stats.par_secteur" :key="s.cle" class="cliquable" @click="secteur = s.cle; annee = ''; charger()">
          <td>{{ s.cle }}</td>
          <td class="num">{{ s.nombre }}</td>
          <td class="num">{{ fmtFCFA(s.montant_fcfa) }}</td>
          <td class="num">{{ part(s.montant_fcfa) }}</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section v-if="stats && stats.top_entreprises.length" class="carte">
    <h2>Top 15 des entreprises attributaires{{ secteur ? " — " + secteur : "" }}</h2>
    <table class="tableau">
      <thead>
        <tr><th>Entreprise</th><th class="num">Marchés</th><th class="num">Montant</th><th class="num">Part</th></tr>
      </thead>
      <tbody>
        <tr v-for="e in stats.top_entreprises" :key="e.cle">
          <td>
            <router-link v-if="e.id" :to="`/marches/entreprises/${e.id}`">{{ e.cle }}</router-link>
            <template v-else>{{ e.cle }}</template>
          </td>
          <td class="num">{{ e.nombre }}</td>
          <td class="num">{{ fmtFCFA(e.montant_fcfa) }}</td>
          <td class="num">{{ part(e.montant_fcfa) }}</td>
        </tr>
      </tbody>
    </table>
  </section>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="stats && !stats.total" class="vide">Aucun marché pour ce filtre.</p>

  <p class="note-methode">
    Secteur déduit automatiquement de l'objet du marché (heuristique par mots-clés) ;
    en cas de doute, le journal officiel fait foi. Les entreprises sont regroupées à partir
    des graphies des Quotidiens (casse, accents, forme juridique) : une même société y est
    souvent écrite de plusieurs façons.
  </p>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { apiGet } from "../api";
import { baseOptions, monter, roles } from "../charts";

const stats = ref(null);
const secteursDispo = ref([]);
const annees = ref([]);
const secteur = ref("");
const annee = ref("");
const chargement = ref(false);
const elSecteurs = ref(null);
const elAnnees = ref(null);
const elEntreprises = ref(null);
let nettoyages = [];

const lienApi = computed(() => {
  const p = new URLSearchParams();
  if (secteur.value) p.set("secteur", secteur.value);
  if (annee.value) p.set("annee", annee.value);
  return "/api/marches/stats" + (p.toString() ? "?" + p : "");
});

function fmtFCFA(n) {
  if (n == null) return "—";
  if (n >= 1e9) return `${(n / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mds FCFA`;
  if (n >= 1e6) return `${(n / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M FCFA`;
  return `${n.toLocaleString("fr-FR")} FCFA`;
}
function part(m) {
  const t = stats.value?.montant_total_fcfa || 0;
  return t ? `${((100 * m) / t).toFixed(1)} %` : "—";
}
function hauteur(n) {
  return `height: ${Math.max(160, n * 30 + 60)}px`;
}

function purger() {
  nettoyages.forEach((fn) => fn());
  nettoyages = [];
}

function barreH(el, items, couleur) {
  if (!el || !items.length) return;
  const c = roles();
  const cats = items.map((i) => i.cle);
  const vals = items.map((i) => i.montant_fcfa);
  nettoyages.push(
    monter(el, {
      ...baseOptions(c),
      grid: { left: 8, right: 70, top: 8, bottom: 8, containLabel: true },
      xAxis: { type: "value", splitLine: { lineStyle: { color: c.grille } }, axisLabel: { show: false } },
      yAxis: {
        type: "category",
        inverse: true,
        data: cats,
        axisLabel: { color: c.texteSecondaire, width: 180, overflow: "truncate" },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      tooltip: {
        ...baseOptions(c).tooltip,
        formatter: (p) => `${p[0].name}<br/><b>${fmtFCFA(p[0].value)}</b> — ${items[p[0].dataIndex].nombre} marché(s)`,
      },
      series: [
        {
          type: "bar",
          data: vals,
          itemStyle: { color: couleur, borderRadius: [0, 4, 4, 0] },
          barMaxWidth: 18,
          label: { show: true, position: "right", color: c.texteSecondaire, formatter: (p) => fmtFCFA(p.value) },
        },
      ],
    })
  );
}

function barreV(el, items) {
  if (!el || !items.length) return;
  const c = roles();
  nettoyages.push(
    monter(el, {
      ...baseOptions(c),
      xAxis: {
        type: "category",
        data: items.map((i) => i.cle),
        axisLabel: { color: c.texteSecondaire },
        axisTick: { show: false },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: c.grille } }, axisLabel: { show: false } },
      tooltip: {
        ...baseOptions(c).tooltip,
        formatter: (p) => `${p[0].name}<br/><b>${fmtFCFA(p[0].value)}</b> — ${items[p[0].dataIndex].nombre} marché(s)`,
      },
      series: [
        {
          type: "bar",
          data: items.map((i) => i.montant_fcfa),
          itemStyle: { color: roles().serie1, borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 46,
        },
      ],
    })
  );
}

async function charger() {
  chargement.value = true;
  purger();
  try {
    const r = await apiGet("/marches/stats", {
      secteur: secteur.value || undefined,
      annee: annee.value || undefined,
    });
    stats.value = r;
    if (!secteur.value) secteursDispo.value = r.secteurs_dispo;
    if (!annee.value) annees.value = r.annees;
    await nextTick();
    const c = roles();
    barreH(elSecteurs.value, r.par_secteur, c.serie1);
    barreV(elAnnees.value, r.par_annee);
    barreH(elEntreprises.value, r.top_entreprises, c.serie2);
  } finally {
    chargement.value = false;
  }
}

onMounted(charger);
onBeforeUnmount(purger);
</script>

<style scoped>
.entete-recherche { align-items: flex-end; flex-wrap: wrap; gap: 12px; }
.entete-recherche label { display: flex; flex-direction: column; font-size: 0.82rem; color: var(--text-secondary); gap: 4px; }
.entete-recherche select { min-width: 180px; }
.raz { align-self: flex-end; }
/* pas de grid : les canvas ECharts ont une largeur intrinsèque qui casse les
   pistes 1fr — on empile en pleine largeur, chaque carte grandit avec son canvas */
.grille-graphes { display: flex; flex-direction: column; gap: 16px; margin: 16px 0; }
.bloc-graphe h2, .carte > h2 { font-size: 0.95rem; margin: 0 0 10px; }
.canvas { width: 100%; }
.tableau { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.tableau th, .tableau td { padding: 7px 10px; border-bottom: 1px solid var(--border); text-align: left; }
.tableau .num { text-align: right; font-variant-numeric: tabular-nums; }
.tableau tbody tr.cliquable { cursor: pointer; }
.tableau tbody tr.cliquable:hover { background: var(--surface-2, rgba(127, 127, 127, 0.08)); }
.note-methode { color: var(--text-muted); font-size: 0.82rem; margin-top: 16px; }
@media (max-width: 760px) {
  .grille-graphes { grid-template-columns: 1fr; }
}
</style>
