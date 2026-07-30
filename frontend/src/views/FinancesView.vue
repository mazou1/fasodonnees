<template>
  <h1>Finances publiques</h1>
  <p class="sous-titre">
    Les dépenses décidées en Conseil des ministres (marchés, conventions, prêts, subventions)
    et les budgets de l'État adoptés - chaque chiffre relié à son compte rendu source.
  </p>

  <div v-if="stats" class="grille-tuiles">
    <div class="carte tuile">
      <div class="valeur">{{ fmtFCFA(stats.totaux.montant_total_fcfa) }}</div>
      <div class="libelle">engagés en Conseil des ministres</div>
    </div>
    <div class="carte tuile">
      <div class="valeur">{{ stats.totaux.engagements.toLocaleString("fr-FR") }}</div>
      <div class="libelle">engagements chiffrés</div>
    </div>
    <div class="carte tuile" v-if="plusGros">
      <div class="valeur">{{ fmtFCFA(plusGros.montant_fcfa) }}</div>
      <div class="libelle">plus gros engagement ({{ plusGros.beneficiaire ?? plusGros.ministere ?? "-" }})</div>
    </div>
    <div class="carte tuile" v-if="stats.budgets.length">
      <div class="valeur">{{ exercices }}</div>
      <div class="libelle">exercices budgétaires documentés</div>
    </div>
  </div>

  <template v-if="budgetActuel">
    <h2 style="margin-top: 28px">
      Budget de l'État {{ budgetActuel.exercice }}
      <span class="badge">{{ LOIS[budgetActuel.type_loi] ?? budgetActuel.type_loi }}</span>
    </h2>
    <div class="grille-tuiles">
      <div class="carte tuile" v-if="budgetActuel.depenses_fcfa">
        <div class="valeur">{{ fmtFCFA(budgetActuel.depenses_fcfa) }}</div>
        <div class="libelle">dépenses{{ fmtVariation(variation("depenses_fcfa")) }}</div>
      </div>
      <div class="carte tuile" v-if="budgetActuel.recettes_fcfa">
        <div class="valeur">{{ fmtFCFA(budgetActuel.recettes_fcfa) }}</div>
        <div class="libelle">recettes{{ fmtVariation(variation("recettes_fcfa")) }}</div>
      </div>
      <div class="carte tuile" v-if="solde != null">
        <div class="valeur">{{ fmtFCFA(Math.abs(solde)) }}</div>
        <div class="libelle">{{ solde < 0 ? "déficit" : "excédent" }} prévisionnel</div>
      </div>
    </div>
  </template>

  <template v-if="exercicesDetail.length">
    <h2 style="margin-top: 28px">
      Où va l'argent, d'où vient-il -
      <select v-model.number="exerciceDetail">
        <option v-for="ex in exercicesDetail" :key="ex" :value="ex">{{ ex }}</option>
      </select>
    </h2>
    <div class="grille-repartitions">
      <section class="carte repartition" v-if="recettesDetail.length">
        <h3>Répartition des recettes</h3>
        <p class="note">D'où viennent les ressources de l'État : impôts et taxes, recettes de services, dons.</p>
        <div class="ligne" v-for="r in recettesDetail" :key="r.libelle">
          <div class="entete">
            <span class="part">{{ pctLigne(r.montant_fcfa, recettesDetail) }}</span>
            <span class="lib">{{ r.libelle }}</span>
            <span class="montant">{{ fmtFCFA(r.montant_fcfa) }}</span>
          </div>
          <div class="jauge"><div class="rempli recette" :style="{ width: pctLigne(r.montant_fcfa, recettesDetail) }"></div></div>
        </div>
      </section>
      <section class="carte repartition" v-if="depensesDetail.length">
        <h3>Répartition des dépenses</h3>
        <p class="note">Où passe l'argent public : salaires, fonctionnement, investissements, dette.</p>
        <div class="ligne" v-for="r in depensesDetail" :key="r.libelle">
          <div class="entete">
            <span class="part">{{ pctLigne(r.montant_fcfa, depensesDetail) }}</span>
            <span class="lib">{{ r.libelle }}</span>
            <span class="montant">{{ fmtFCFA(r.montant_fcfa) }}</span>
          </div>
          <div class="jauge"><div class="rempli depense" :style="{ width: pctLigne(r.montant_fcfa, depensesDetail) }"></div></div>
        </div>
      </section>
    </div>
    <section class="carte repartition" v-if="dotationsDetail.length" style="margin-top: 14px">
      <h3>Allocations par secteur</h3>
      <p class="note">
        Les grandes allocations budgétaires publiées pour {{ exerciceDetail }} - en pourcentage
        des dépenses totales de l'exercice.
      </p>
      <div class="ligne" v-for="d in dotationsDetail" :key="d.ministere">
        <div class="entete">
          <span class="part">{{ pctDotation(d.montant_fcfa) }}</span>
          <span class="lib">{{ d.ministere }}</span>
          <span class="montant">{{ fmtFCFA(d.montant_fcfa) }}</span>
        </div>
        <div class="jauge"><div class="rempli ministere" :style="{ width: pctDotation(d.montant_fcfa) }"></div></div>
      </div>
    </section>
    <p class="note sources" v-if="sourcesDetail.length">
      Sources : {{ sourcesDetail.join(" · ") }}
    </p>
  </template>

  <div class="grille-graphes" v-if="stats">
    <div class="carte graphe-large" v-if="stats.budgets.length">
      <h2>Budget de l'État par exercice - recettes et dépenses</h2>
      <div ref="elBudgets" class="graphe" style="height: 260px"></div>
    </div>
    <div class="carte">
      <h2>Montants engagés par année de conseil</h2>
      <div ref="elAnnees" class="graphe" style="height: 260px"></div>
    </div>
    <div class="carte">
      <h2>Ministères aux plus gros engagements</h2>
      <div ref="elMinisteres" class="graphe" style="height: 260px"></div>
    </div>
  </div>

  <h2 style="margin-top: 28px">Les engagements, du plus important au plus récent</h2>
  <div class="filtres">
    <input v-model="q" type="search" placeholder="Objet, bénéficiaire, ministère…" @input="rechercherDebounce" />
    <select v-model="type" @change="page = 1; recharger()">
      <option value="">Tous types</option>
      <option value="marche">Marchés publics</option>
      <option value="convention">Conventions</option>
      <option value="pret">Prêts / financements</option>
      <option value="subvention">Subventions</option>
      <option value="garantie">Garanties</option>
      <option value="decaissement">Décaissements</option>
      <option value="autre">Autres</option>
    </select>
    <select v-model="tri" @change="page = 1; recharger()">
      <option value="montant">Par montant</option>
      <option value="date">Par date</option>
    </select>
    <a class="export" href="/api/export/engagements.csv" title="Télécharger tous les engagements (CSV)">⬇ CSV</a>
  </div>

  <div class="liste">
    <article v-for="e in engagements" :key="e.id" class="item">
      <div class="meta">
        <span class="badge">{{ LIBELLES[e.type] ?? e.type }}</span>
        <span v-if="e.date_conseil">Conseil du {{ formatDate(e.date_conseil) }}</span>
        <span v-if="e.ministere">{{ e.ministere }}</span>
      </div>
      <div class="titre">{{ fmtFCFA(e.montant_fcfa) }}<template v-if="e.beneficiaire"> - {{ e.beneficiaire }}</template></div>
      <div class="detail">{{ e.objet }}</div>
      <a class="source" :href="e.document_url" target="_blank" rel="noopener">Voir le compte rendu officiel →</a>
    </article>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!engagements.length" class="vide">
    Aucun engagement validé pour ces filtres.
  </p>

  <div class="pagination">
    <button :disabled="page <= 1" @click="page--; recharger()">← Précédent</button>
    <span>Page {{ page }}</span>
    <button :disabled="engagements.length < PAR_PAGE" @click="page++; recharger()">Suivant →</button>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { apiGet } from "../api";
import { baseOptions, monter, roles } from "../charts";

const LIBELLES = {
  marche: "Marché public",
  convention: "Convention",
  pret: "Prêt",
  subvention: "Subvention",
  garantie: "Garantie",
  decaissement: "Décaissement",
  autre: "Autre",
};
const PAR_PAGE = 20;
const LOIS = {
  initiale: "loi de finances initiale",
  rectificative: "loi de finances rectificative",
  reglement: "exécution (loi de règlement)",
};
// priorité au plus définitif : règlement (exécuté) > rectificative > initiale ;
// à égalité, la ligne la plus complète gagne
const PRIO = { reglement: 3, rectificative: 2, initiale: 1 };
function consoliderBudgets(budgets) {
  const score = (b) =>
    (PRIO[b.type_loi] ?? 0) * 10 + (b.recettes_fcfa ? 1 : 0) + (b.depenses_fcfa ? 1 : 0);
  const parExercice = new Map();
  for (const b of budgets) {
    const actuel = parExercice.get(b.exercice);
    if (!actuel || score(b) >= score(actuel)) parExercice.set(b.exercice, b);
  }
  return [...parExercice.values()].sort((a, b) => a.exercice - b.exercice);
}

const stats = ref(null);
const engagements = ref([]);
const plusGros = ref(null);
const q = ref("");
const type = ref("");
const tri = ref("montant");
const page = ref(1);
const chargement = ref(false);
const elBudgets = ref(null);
const elAnnees = ref(null);
const elMinisteres = ref(null);
const exerciceDetail = ref(null);
const nettoyages = [];
let minuterie = null;

const exercices = computed(() => {
  const ex = [...new Set((stats.value?.budgets ?? []).map((b) => b.exercice))].sort();
  return ex.length > 1 ? `${ex[0]}-${ex[ex.length - 1]}` : (ex[0] ?? "-");
});

const lignesBudget = computed(() => consoliderBudgets(stats.value?.budgets ?? []));
// bandeau : l'exercice courant (ou le dernier passé documenté), pas les programmations futures
const budgetActuel = computed(() => {
  const annee = new Date().getFullYear();
  const passes = lignesBudget.value.filter((b) => b.exercice <= annee);
  return passes[passes.length - 1] ?? null;
});
const budgetPrecedent = computed(() =>
  lignesBudget.value.find((b) => b.exercice === (budgetActuel.value?.exercice ?? 0) - 1) ?? null,
);
const solde = computed(() => {
  const b = budgetActuel.value;
  return b?.recettes_fcfa && b?.depenses_fcfa ? b.recettes_fcfa - b.depenses_fcfa : null;
});
function variation(champ) {
  const a = budgetActuel.value?.[champ];
  const p = budgetPrecedent.value?.[champ];
  return a && p ? ((a - p) / p) * 100 : null;
}
function fmtVariation(v) {
  if (v == null || !budgetPrecedent.value) return "";
  const signe = v >= 0 ? "+" : "−";
  return ` · ${signe}${Math.abs(v).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} % vs ${budgetPrecedent.value.exercice}`;
}

const exercicesDetail = computed(() =>
  [
    ...new Set([
      ...(stats.value?.dotations ?? []).map((d) => d.exercice),
      ...(stats.value?.repartitions ?? []).map((r) => r.exercice),
    ]),
  ].sort((a, b) => b - a),
);
const recettesDetail = computed(() =>
  (stats.value?.repartitions ?? []).filter(
    (r) => r.exercice === exerciceDetail.value && r.sens === "recette",
  ),
);
const depensesDetail = computed(() =>
  (stats.value?.repartitions ?? []).filter(
    (r) => r.exercice === exerciceDetail.value && r.sens === "depense",
  ),
);
const dotationsDetail = computed(() =>
  (stats.value?.dotations ?? []).filter((d) => d.exercice === exerciceDetail.value),
);
function pctLigne(montant, lignes) {
  const total = lignes.reduce((s, l) => s + l.montant_fcfa, 0);
  return total ? `${((montant / total) * 100).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %` : "0 %";
}
// part d'une allocation sectorielle dans les dépenses totales de l'exercice
function pctDotation(montant) {
  const b = lignesBudget.value.find((l) => l.exercice === exerciceDetail.value);
  const total = b?.depenses_fcfa;
  return total ? `${((montant / total) * 100).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %` : "-";
}
const sourcesDetail = computed(() => {
  const lignes = [...recettesDetail.value, ...depensesDetail.value, ...dotationsDetail.value];
  // le séparateur citation/URL est saisi à la main dans l'admin : accepter
  // les trois tirets évite qu'une URL s'affiche en clair dans « Sources »
  return [...new Set(lignes.map((l) => (l.source || "").split(/\s[-–—]\s/)[0]).filter(Boolean))];
});

function fmtFCFA(n) {
  if (n == null) return "-";
  if (n >= 1e9) return `${(n / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mds FCFA`;
  if (n >= 1e6) return `${(n / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M FCFA`;
  return `${n.toLocaleString("fr-FR")} FCFA`;
}
function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}
const enMds = (v) => `${(v / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 0 })}`;

async function recharger() {
  chargement.value = true;
  try {
    engagements.value = await apiGet("/finances/engagements", {
      q: q.value.length >= 2 ? q.value : undefined,
      type: type.value,
      tri: tri.value,
      page: page.value,
      par_page: PAR_PAGE,
    });
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
  const [s, top] = await Promise.all([
    apiGet("/finances/stats"),
    apiGet("/finances/engagements", { tri: "montant", par_page: 1 }),
  ]);
  stats.value = s;
  plusGros.value = top[0] ?? null;
  await recharger();

  const c = roles();
  const axeMds = {
    type: "value",
    splitLine: { lineStyle: { color: c.grille } },
    axisLabel: { color: c.texteSecondaire, formatter: (v) => `${enMds(v)} Mds` },
  };

  if (exercicesDetail.value.length) {
    const annee = new Date().getFullYear();
    exerciceDetail.value =
      exercicesDetail.value.find((ex) => ex <= annee) ?? exercicesDetail.value[0];
  }

  if (s.budgets.length && elBudgets.value) {
    const lignes = lignesBudget.value;
    nettoyages.push(
      monter(elBudgets.value, {
        ...baseOptions(c),
        legend: { top: 0, right: 0, textStyle: { color: c.texteSecondaire }, itemWidth: 14, itemHeight: 10 },
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          backgroundColor: c.surface,
          borderColor: c.grille,
          textStyle: { color: c.texte },
          valueFormatter: (v) => (v == null ? "-" : `${enMds(v)} Mds FCFA`),
        },
        xAxis: {
          type: "category",
          data: lignes.map((b) => b.exercice),
          axisLine: { lineStyle: { color: c.grille } },
          axisTick: { show: false },
          axisLabel: { color: c.texte },
        },
        yAxis: axeMds,
        series: [
          {
            name: "Recettes",
            type: "bar",
            data: lignes.map((b) => b.recettes_fcfa),
            barWidth: 22,
            itemStyle: { color: c.serie1, borderRadius: [4, 4, 0, 0] },
          },
          {
            name: "Dépenses",
            type: "bar",
            data: lignes.map((b) => b.depenses_fcfa),
            barWidth: 22,
            itemStyle: { color: c.serie2, borderRadius: [4, 4, 0, 0] },
          },
        ],
      }),
    );
  }

  if (elAnnees.value) {
    nettoyages.push(
      monter(elAnnees.value, {
        ...baseOptions(c),
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          backgroundColor: c.surface,
          borderColor: c.grille,
          textStyle: { color: c.texte },
          valueFormatter: (v) => `${enMds(v)} Mds FCFA`,
        },
        xAxis: {
          type: "category",
          data: s.par_annee.map((a) => a.annee),
          axisLine: { lineStyle: { color: c.grille } },
          axisTick: { show: false },
          axisLabel: { color: c.texte },
        },
        yAxis: axeMds,
        series: [
          {
            type: "bar",
            data: s.par_annee.map((a) => a.montant_fcfa),
            barWidth: 22,
            itemStyle: { color: c.serie1, borderRadius: [4, 4, 0, 0] },
          },
        ],
      }),
    );
  }

  if (elMinisteres.value) {
    nettoyages.push(
      monter(elMinisteres.value, {
        ...baseOptions(c),
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          backgroundColor: c.surface,
          borderColor: c.grille,
          textStyle: { color: c.texte },
          valueFormatter: (v) => `${enMds(v)} Mds FCFA`,
        },
        xAxis: { ...axeMds },
        yAxis: {
          type: "category",
          data: s.par_ministere.map((m) => m.ministere),
          inverse: true,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: c.texte, width: 170, overflow: "truncate" },
        },
        series: [
          {
            type: "bar",
            data: s.par_ministere.map((m) => m.montant_fcfa),
            barWidth: 14,
            itemStyle: { color: c.serie1, borderRadius: [0, 4, 4, 0] },
          },
        ],
      }),
    );
  }
});

onBeforeUnmount(() => nettoyages.forEach((fn) => fn()));
</script>

<style scoped>
.grille-repartitions { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 14px; }
.repartition h3 { margin: 0 0 4px; }
.repartition .note { color: var(--text-secondary); font-size: 0.88rem; margin: 0 0 14px; }
.ligne { margin-bottom: 12px; }
.ligne .entete { display: flex; gap: 8px; align-items: baseline; margin-bottom: 4px; }
.ligne .part { flex: none; min-width: 52px; font-weight: 700; font-variant-numeric: tabular-nums; }
.ligne .lib { flex: 1; }
.ligne .montant { flex: none; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.jauge { height: 8px; border-radius: 4px; background: color-mix(in srgb, var(--border) 55%, transparent); overflow: hidden; }
.rempli { height: 100%; border-radius: 4px; }
.rempli.recette { background: var(--series-1); }
.rempli.depense { background: var(--series-2); }
.rempli.ministere { background: var(--series-1); }
.sources { color: var(--text-secondary); font-size: 0.82rem; margin-top: 10px; }
</style>
