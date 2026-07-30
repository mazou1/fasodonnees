<template>
  <section class="hero">
    <h1 class="hero-titre">L'information publique du Burkina&nbsp;Faso, en clair</h1>
    <p class="hero-sous">
      Décisions du Conseil des ministres, nominations, lois, budget, marchés et
      infrastructures - extraits des sources officielles et reliés à leur document d'origine.
    </p>
    <form class="hero-recherche" @submit.prevent="lancerRecherche">
      <span class="loupe" aria-hidden="true">🔍</span>
      <input v-model="q" type="search" placeholder="Rechercher une personne, une décision, un texte…" />
      <button type="submit">Rechercher</button>
    </form>
    <nav class="hero-acces">
      <router-link v-for="a in ACCES" :key="a.to" :to="a.to" class="acces-pill">
        <span class="ico" aria-hidden="true">{{ a.ico }}</span>{{ a.lib }}
      </router-link>
    </nav>
  </section>

  <div class="grille-une" v-if="dernierConseil || actualites.length">
    <router-link v-if="dernierConseil" :to="`/conseils/${dernierConseil.id}`" class="carte-cm">
      <div class="bandeau">
        <div class="sur-titre">Dernier Conseil des ministres</div>
        <div class="grande-date" v-if="dernierConseil.date_conseil">
          <span class="jour">{{ jour(dernierConseil.date_conseil) }}</span>
          <span class="mois">{{ moisAnnee(dernierConseil.date_conseil) }}</span>
        </div>
      </div>
      <div class="corps">
        <div class="titre-carte">
          {{ dernierConseil.decisions }} décision{{ dernierConseil.decisions > 1 ? "s" : "" }} ·
          {{ dernierConseil.nominations }} nomination{{ dernierConseil.nominations > 1 ? "s" : "" }}
          <template v-if="dernierConseil.engagements">
            · {{ dernierConseil.engagements }} engagement{{ dernierConseil.engagements > 1 ? "s" : "" }}
          </template>
        </div>
        <div class="detail">Lire l'essentiel et le compte rendu intégral →</div>
      </div>
    </router-link>

    <section class="carte actus" v-if="actualites.length">
      <h2>Dernières actualités</h2>
      <article v-for="a in actualites" :key="a.id" class="actu">
        <div class="meta">
          <span class="badge">{{ a.source_nom }}</span>
          <span v-if="a.date_publication">{{ jour(a.date_publication) }} {{ moisAnnee(a.date_publication) }}</span>
        </div>
        <a :href="a.url" target="_blank" rel="noopener" class="titre-actu">{{ a.titre }}</a>
      </article>
      <router-link to="/actualites" class="tout">Toutes les actualités →</router-link>
    </section>
  </div>

  <div v-if="stats" class="grille-tuiles">
    <div class="carte tuile" v-for="t in tuiles" :key="t.libelle">
      <div class="valeur">{{ t.valeur.toLocaleString("fr-FR") }}</div>
      <div class="libelle">{{ t.libelle }}</div>
    </div>
  </div>

  <div class="grille-graphes">
    <div class="carte graphe-large">
      <h2>Décisions et nominations par année</h2>
      <div ref="elAnnees" class="graphe" style="height: 260px"></div>
    </div>
    <div class="carte">
      <h2>Décisions par nature</h2>
      <div ref="elTypes" class="graphe" style="height: 260px"></div>
    </div>
    <div class="carte">
      <h2>Structures les plus concernées par les nominations</h2>
      <div ref="elStructures" class="graphe" style="height: 260px"></div>
    </div>
  </div>
  <p v-if="!stats" class="chargement">Chargement…</p>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { apiGet } from "../api";
import { baseOptions, monter, roles } from "../charts";

const router = useRouter();
const q = ref("");
function lancerRecherche() {
  const terme = q.value.trim();
  if (terme.length >= 2) router.push({ path: "/recherche", query: { q: terme } });
}
const ACCES = [
  { to: "/conseils", ico: "🏛️", lib: "Conseil des ministres" },
  { to: "/annuaire", ico: "👥", lib: "Annuaire de l'État" },
  { to: "/finances", ico: "💰", lib: "Finances" },
  { to: "/infrastructures", ico: "🛠️", lib: "Infrastructures" },
  { to: "/textes", ico: "📜", lib: "Lois & décrets" },
  { to: "/marches", ico: "🧾", lib: "Marchés publics" },
  { to: "/documents", ico: "📄", lib: "Documents" },
];

const LIBELLES_TYPE = {
  adoption_decret: "Décrets adoptés",
  adoption_loi: "Projets de loi",
  rapport: "Rapports",
  communication: "Communications",
  autorisation: "Autorisations",
  autre: "Autres",
};

const stats = ref(null);
const dernierConseil = ref(null);
const actualites = ref([]);
const elAnnees = ref(null);
const elTypes = ref(null);
const elStructures = ref(null);
const nettoyages = [];

function jour(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric" });
}
function moisAnnee(d) {
  return new Date(d).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
}

const tuiles = computed(() => {
  const t = stats.value?.totaux ?? {};
  return [
    { libelle: "décisions", valeur: t.decisions ?? 0 },
    { libelle: "nominations", valeur: t.nominations ?? 0 },
    { libelle: "personnes nommées", valeur: t.personnes ?? 0 },
    { libelle: "comptes rendus couverts", valeur: t.comptes_rendus ?? 0 },
  ];
});

function barreH(c, categories, valeurs) {
  // Barres horizontales, une seule série : pas de boîte de légende (le titre nomme la série).
  return {
    ...baseOptions(c),
    xAxis: { type: "value", splitLine: { lineStyle: { color: c.grille } }, axisLabel: { color: c.texteSecondaire } },
    yAxis: {
      type: "category",
      data: categories,
      inverse: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: c.texte, width: 180, overflow: "truncate" },
    },
    series: [
      {
        type: "bar",
        data: valeurs,
        barWidth: 14,
        itemStyle: { color: c.serie1, borderRadius: [0, 4, 4, 0] },
      },
    ],
  };
}

onMounted(async () => {
  const [s, conseils, actus] = await Promise.all([
    apiGet("/stats"),
    apiGet("/conseils", { par_page: 1 }),
    apiGet("/actualites", { par_page: 3 }),
  ]);
  stats.value = s;
  dernierConseil.value = conseils.conseils[0] ?? null;
  actualites.value = actus;
  const c = roles();

  nettoyages.push(
    monter(elAnnees.value, {
      ...baseOptions(c),
      legend: { top: 0, right: 0, textStyle: { color: c.texteSecondaire }, itemWidth: 14, itemHeight: 10 },
      xAxis: {
        type: "category",
        data: s.par_annee.map((a) => a.annee),
        axisLine: { lineStyle: { color: c.grille } },
        axisTick: { show: false },
        axisLabel: { color: c.texte },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: c.grille } }, axisLabel: { color: c.texteSecondaire } },
      series: [
        {
          name: "Nominations",
          type: "bar",
          data: s.par_annee.map((a) => a.nominations),
          barWidth: 22,
          itemStyle: { color: c.serie1, borderRadius: [4, 4, 0, 0] },
        },
        {
          name: "Décisions",
          type: "bar",
          data: s.par_annee.map((a) => a.decisions),
          barWidth: 22,
          itemStyle: { color: c.serie2, borderRadius: [4, 4, 0, 0] },
        },
      ],
    }),
    monter(
      elTypes.value,
      barreH(
        c,
        s.decisions_par_type.map((d) => LIBELLES_TYPE[d.type] ?? d.type),
        s.decisions_par_type.map((d) => d.n),
      ),
    ),
    monter(
      elStructures.value,
      barreH(
        c,
        s.top_structures.map((d) => d.structure),
        s.top_structures.map((d) => d.mandats),
      ),
    ),
  );
});

onBeforeUnmount(() => nettoyages.forEach((fn) => fn()));
</script>

<style scoped>
/* Hero - accès à l'information, inspiré de vie-publique.sn */
.hero { text-align: center; padding: 18px 0 34px; }
.hero-titre {
  font-size: clamp(1.9rem, 4.5vw, 3rem); font-weight: 800; letter-spacing: -0.02em;
  line-height: 1.12; margin: 0 auto 14px; max-width: 780px;
}
.hero-sous {
  color: var(--text-secondary); font-size: 1.05rem; line-height: 1.55;
  max-width: 640px; margin: 0 auto 26px;
}
.hero-recherche {
  display: flex; align-items: center; gap: 8px; max-width: 620px; margin: 0 auto;
  background: var(--surface-1); border: 1px solid var(--border); border-radius: 999px;
  padding: 6px 6px 6px 18px; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
}
.hero-recherche .loupe { font-size: 1rem; opacity: 0.7; }
.hero-recherche input {
  flex: 1; border: none; background: none; color: var(--text-primary);
  font-size: 1rem; padding: 12px 4px; min-width: 0; outline: none;
}
.hero-recherche button {
  flex: none; border: none; background: var(--accent); color: #fff;
  border-radius: 999px; padding: 11px 20px; font-size: 0.95rem; font-weight: 600; cursor: pointer;
}
.hero-recherche button:hover { filter: brightness(1.06); }
.hero-acces { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-top: 22px; }
.acces-pill {
  display: inline-flex; align-items: center; gap: 8px; padding: 9px 16px;
  border: 1px solid var(--border); border-radius: 999px; background: var(--surface-1);
  color: var(--text-primary); font-size: 0.92rem; font-weight: 500;
  transition: border-color 0.15s, transform 0.05s;
}
.acces-pill:hover { border-color: var(--accent); color: var(--accent); text-decoration: none; transform: translateY(-1px); }
.acces-pill .ico { font-size: 1.05rem; }
@media (max-width: 640px) {
  .hero { padding: 8px 0 24px; }
  .hero-recherche button { padding: 11px 14px; }
}

.grille-une { display: grid; grid-template-columns: 1fr 1.4fr; gap: 14px; margin-bottom: 18px; }
@media (max-width: 760px) { .grille-une { grid-template-columns: 1fr; } }

.carte-cm {
  display: block; border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
  background: var(--surface-1); text-decoration: none; color: inherit;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.carte-cm:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08); }
.bandeau {
  padding: 18px 18px 14px; color: #fff; min-height: 96px;
  background:
    radial-gradient(120% 160% at 100% 0%, rgba(255, 255, 255, 0.16), transparent 55%),
    linear-gradient(135deg, var(--series-1-fonce), var(--series-1));
  border-bottom: 3px solid;
  border-image: linear-gradient(90deg, #ce1126 50%, #009e49 50%) 1;
}
.sur-titre { font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.85; }
.grande-date { display: flex; align-items: baseline; gap: 8px; margin-top: 8px; }
.grande-date .jour { font-size: 2.1rem; font-weight: 800; line-height: 1; }
.grande-date .mois { font-size: 1.02rem; font-weight: 600; text-transform: capitalize; }
.corps { padding: 12px 18px 14px; }
.titre-carte { font-weight: 700; }
.corps .detail { color: var(--text-secondary); font-size: 0.88rem; margin-top: 4px; }

.actus h2 { margin: 0 0 10px; }
.actu { padding: 8px 0; border-top: 1px solid var(--border); }
.actu .meta { color: var(--text-muted); font-size: 0.8rem; display: flex; gap: 8px; margin-bottom: 2px; }
.titre-actu { font-weight: 600; text-decoration: none; color: inherit; }
.titre-actu:hover { color: var(--accent); }
.tout { display: inline-block; margin-top: 10px; font-size: 0.9rem; }
</style>
