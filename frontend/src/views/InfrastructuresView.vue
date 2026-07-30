<template>
  <h1>Infrastructures &amp; inaugurations</h1>
  <p class="sous-titre">
    Registre factuel des inaugurations, poses de première pierre et mises en service
    d'infrastructures publiques, tel que rapporté par les sources officielles. Chaque
    entrée renvoie à son document d'origine.
  </p>

  <details class="note-methode">
    <summary>Méthode &amp; limites</summary>
    <p>
      Ce registre recense ce qui est <strong>rapporté</strong> par les sources officielles
      (gouvernement.gov.bf), avec pour chaque ouvrage un <strong>statut</strong> -
      annonce, pose de première pierre, inauguration ou mise en service - afin de ne pas
      présenter une annonce comme un ouvrage livré. La présence d'un élément ne vaut pas
      vérification indépendante de son achèvement ou de son fonctionnement. Les points sont
      localisés à la commune (source&nbsp;: GeoNames).
    </p>
    <p>
      <strong>Disponibilité des données selon la période&nbsp;:</strong> la couverture
      n'est pas uniforme dans le temps. Le fil officiel collecté automatiquement
      (gouvernement.gov.bf) ne remonte qu'à <strong>2022</strong> ; les entrées
      antérieures proviennent d'un <strong>jeu de référence saisi à la main</strong>
      (grandes infrastructures documentées : barrages, échangeurs, centrales…), non
      exhaustif. Le point de départ d'une période <em>ne signifie donc pas</em> qu'aucune
      infrastructure n'existait avant - seulement que la source ne la couvre pas encore.
    </p>
  </details>

  <div class="filtres">
    <select v-model="f.annee" @change="recharger">
      <option value="">Toutes les années</option>
      <option v-for="a in opts.annees" :key="a" :value="a">{{ a }}</option>
    </select>
    <select v-model="f.type" @change="recharger">
      <option value="">Tous les types</option>
      <option v-for="t in opts.types" :key="t" :value="t">{{ libelleType(t) }}</option>
    </select>
    <select v-model="f.region" @change="recharger">
      <option value="">Toutes les régions</option>
      <option v-for="r in opts.regions" :key="r" :value="r">{{ r }}</option>
    </select>
    <select v-model="f.statut" @change="recharger">
      <option value="">Tous les statuts</option>
      <option v-for="s in STATUTS" :key="s.v" :value="s.v">{{ s.l }}</option>
    </select>
  </div>

  <nav class="onglets">
    <a :class="{ actif: onglet === 'carte' }" @click="onglet = 'carte'">Carte</a>
    <a :class="{ actif: onglet === 'stats' }" @click="onglet = 'stats'">Statistiques</a>
  </nav>

  <p v-if="total === 0 && !chargement" class="vide">
    Aucune infrastructure validée pour ces critères pour l'instant.
  </p>

  <!-- CARTE -->
  <div v-show="onglet === 'carte'">
    <div class="chrono" v-if="anneeMin != null && anneeMax > anneeMin">
      <button class="btn-lire" @click="enLecture ? stopLecture() : lireChronologie()"
        :title="enLecture ? 'Pause' : 'Lire la chronologie'">
        {{ enLecture ? "⏸" : "▶" }}
      </button>
      <div class="dual">
        <div class="dual-track"><div class="dual-fill" :style="fillStyle"></div></div>
        <input type="range" class="dual-in" :min="anneeMin" :max="anneeMax" step="1"
          :value="anneeDebut" @input="majDebut" aria-label="Année de début" />
        <input type="range" class="dual-in" :min="anneeMin" :max="anneeMax" step="1"
          :value="anneeFin" @input="majFin" aria-label="Année de fin" />
      </div>
      <span class="chrono-an">{{ plein ? "toutes les années" : anneeDebut + " - " + anneeFin }}</span>
      <button v-if="!plein" class="btn-tout" @click="toutAfficher">tout</button>
    </div>
    <div class="carte-wrap">
      <div ref="mapEl" class="carte-mlg"></div>
    </div>
    <div class="legende">
      <span v-for="[t, emo] in Object.entries(TYPE_EMOJI)" :key="t" class="lg-item">
        <span class="lg-emo">{{ emo }}</span>{{ TYPES_LBL[t] }}
      </span>
    </div>
    <p class="compteur">{{ total.toLocaleString("fr-FR") }} infrastructure{{ total > 1 ? "s" : "" }} localisée{{ total > 1 ? "s" : "" }}</p>
  </div>

  <!-- STATISTIQUES -->
  <div v-show="onglet === 'stats'" class="stats">
    <div class="kpis" v-if="stats">
      <div class="kpi"><div class="v">{{ stats.total.toLocaleString("fr-FR") }}</div><div class="l">infrastructures</div></div>
      <div class="kpi"><div class="v">{{ opts.types.length }}</div><div class="l">types d'ouvrage</div></div>
      <div class="kpi"><div class="v">{{ (stats.par_region || []).length }}</div><div class="l">régions couvertes</div></div>
      <div class="kpi" v-if="stats.montant_total"><div class="v">{{ mds(stats.montant_total) }}</div><div class="l">Mds FCFA (montants connus)</div></div>
    </div>
    <div class="grille-graphes">
      <div class="carte bloc-graphe"><h3>Par année</h3><div ref="gAnnee" class="graphe-inf"></div></div>
      <div class="carte bloc-graphe"><h3>Par type d'ouvrage</h3><div ref="gType" class="graphe-inf"></div></div>
      <div class="carte bloc-graphe"><h3>Par région</h3><div ref="gRegion" class="graphe-inf"></div></div>
      <div class="carte bloc-graphe"><h3>Par statut</h3><div ref="gStatut" class="graphe-inf"></div></div>
    </div>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { apiGet } from "../api";
import { roles, baseOptions, monter } from "../charts";

// couleur par secteur (peu de catégories → légende lisible)
const COULEURS = {
  "Santé": "#e4572e",
  "Éducation & formation": "#1b9e77",
  "Eau & assainissement": "#2b7bba",
  "Énergie": "#e6a817",
  "Transport & mobilité": "#7b5ea7",
  "Industrie": "#8c6d31",
  "Habitat & urbanisme": "#d081c4",
  "Bâtiments publics": "#5b8c5a",
  "Commerce": "#c0504d",
  "Autres": "#8a8a8a",
};
const STATUTS = [
  { v: "annonce", l: "Annonce" },
  { v: "premiere_pierre", l: "Pose de première pierre" },
  { v: "inauguration", l: "Inauguration" },
  { v: "mise_en_service", l: "Mise en service" },
];
const TYPES_LBL = {
  route: "Route", pont: "Pont", usine: "Usine", hopital: "Hôpital",
  centre_sante: "Centre de santé", ecole: "École", universite: "Université",
  barrage: "Barrage", adduction_eau: "Adduction d'eau", electrification: "Électrification",
  energie: "Énergie", logement: "Logement", marche_infrastructure: "Marché",
  aeroport: "Aéroport", batiment_public: "Bâtiment public", autre: "Autre",
};
// pictogramme par type d'ouvrage
const TYPE_EMOJI = {
  route: "🛣️", pont: "🌉", usine: "🏭", hopital: "🏥", centre_sante: "⚕️",
  ecole: "🏫", universite: "🎓", barrage: "🌊", adduction_eau: "💧",
  electrification: "⚡", energie: "⚡", logement: "🏘️", marche_infrastructure: "🏪",
  aeroport: "✈️", batiment_public: "🏛️", autre: "📍",
};
const TYPE_SECTEUR = {
  route: "Transport & mobilité", pont: "Transport & mobilité", aeroport: "Transport & mobilité",
  usine: "Industrie", hopital: "Santé", centre_sante: "Santé",
  ecole: "Éducation & formation", universite: "Éducation & formation",
  barrage: "Eau & assainissement", adduction_eau: "Eau & assainissement",
  electrification: "Énergie", energie: "Énergie", logement: "Habitat & urbanisme",
  batiment_public: "Bâtiments publics", marche_infrastructure: "Commerce", autre: "Autres",
};
const libelleType = (t) => TYPES_LBL[t] || t;
const libelleStatut = (s) => (STATUTS.find((x) => x.v === s) || {}).l || s;
const mds = (n) => (n / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 1 });

const onglet = ref("carte");
const total = ref(0);
const stats = ref(null);
const chargement = ref(false);
const opts = ref({ annees: [], types: [], regions: [] });
const f = ref({ annee: "", type: "", region: "", statut: "" });

const mapEl = ref(null);
const gAnnee = ref(null), gType = ref(null), gRegion = ref(null), gStatut = ref(null);
let map = null;
let mapPrete = false;
const nettoyeurs = [];

// chronologie : sélection d'une période [début, fin] + lecture animée
const anneeMin = ref(null), anneeMax = ref(null);
const anneeDebut = ref(null), anneeFin = ref(null);
const enLecture = ref(false);
let minuterie = null;

const plein = computed(
  () => anneeDebut.value <= anneeMin.value && anneeFin.value >= anneeMax.value
);
const fillStyle = computed(() => {
  const etendue = anneeMax.value - anneeMin.value || 1;
  const g = ((anneeDebut.value - anneeMin.value) / etendue) * 100;
  const d = ((anneeMax.value - anneeFin.value) / etendue) * 100;
  return { left: g + "%", right: d + "%" };
});

function stopLecture() {
  enLecture.value = false;
  if (minuterie) { clearInterval(minuterie); minuterie = null; }
}
function majDebut(e) {
  stopLecture();
  anneeDebut.value = Math.min(Number(e.target.value), anneeFin.value);
  rafraichirCarte();
}
function majFin(e) {
  stopLecture();
  anneeFin.value = Math.max(Number(e.target.value), anneeDebut.value);
  rafraichirCarte();
}
function lireChronologie() {
  if (anneeMin.value == null) return;
  stopLecture();
  anneeFin.value = anneeDebut.value;   // révèle depuis le début de la période
  rafraichirCarte();
  enLecture.value = true;
  minuterie = setInterval(() => {
    if (anneeFin.value >= anneeMax.value) { stopLecture(); return; }
    anneeFin.value += 1;
    rafraichirCarte();
  }, 1300);
}
function toutAfficher() {
  stopLecture();
  anneeDebut.value = anneeMin.value;
  anneeFin.value = anneeMax.value;
  rafraichirCarte();
}

function couleurExpr() {
  const expr = ["match", ["get", "secteur"]];
  for (const [sec, col] of Object.entries(COULEURS)) expr.push(sec, col);
  expr.push("#8a8a8a");
  return expr;
}

function propsDe(r) {
  return {
    secteur: r.secteur || "Autres",
    titre: r.titre,
    type: libelleType(r.type),
    statut: libelleStatut(r.statut),
    typeCle: r.type,
    lieu: r.localisation_nom || r.region || "",
    arr: r.localisation_nom_arr || "",
    date: r.date_evenement || "",
    montant: r.montant_fcfa || 0,
    url: r.source_url || "",
  };
}

function popupHTML(p) {
  const lieu = p.arr ? `${p.lieu} → ${p.arr}` : p.lieu;
  const montant = p.montant ? `<br><b>${mds(p.montant)} Mds FCFA</b>` : "";
  const lien = p.url
    ? `<br><a href="${p.url}" target="_blank" rel="noopener">source →</a>` : "";
  return (
    `<div class="popup-inf"><strong>${p.titre}</strong><br>` +
    `${p.type} · <span class="pstatut">${p.statut}</span>` +
    `${lieu ? "<br>" + lieu : ""}${p.date ? " · " + p.date : ""}${montant}${lien}</div>`
  );
}

function ouvrirPopup(e) {
  new maplibregl.Popup({ closeButton: true, maxWidth: "300px" })
    .setLngLat(e.lngLat)
    .setHTML(popupHTML(e.features[0].properties))
    .addTo(map);
}

function geojson(list) {
  return {
    type: "FeatureCollection",
    features: list
      .filter((r) => r.latitude != null && r.longitude != null)
      .map((r) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [r.longitude, r.latitude] },
        properties: propsDe(r),
      })),
  };
}

function initCarte() {
  const sombre = document.documentElement.getAttribute("data-theme") === "dark";
  const base = sombre ? "dark_all" : "light_all";
  map = new maplibregl.Map({
    container: mapEl.value,
    style: {
      version: 8,
      sources: {
        carto: {
          type: "raster",
          tiles: [`https://basemaps.cartocdn.com/${base}/{z}/{x}/{y}.png`],
          tileSize: 256,
          attribution: "© OpenStreetMap © CARTO",
        },
      },
      layers: [{ id: "carto", type: "raster", source: "carto" }],
    },
    center: [-1.7, 12.3],
    zoom: 5.4,
    attributionControl: true,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.on("load", () => {
    // liaisons (routes) sous les points
    map.addSource("liaisons", { type: "geojson", data: geojsonLignes([]) });
    map.addLayer({
      id: "infra-lignes",
      type: "line",
      source: "liaisons",
      layout: { "line-cap": "round" },
      paint: {
        "line-color": couleurExpr(),
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, 2, 10, 4],
        "line-opacity": 0.75,
      },
    });
    // couche transparente large : zone de clic confortable sur la liaison
    map.addLayer({
      id: "infra-lignes-hit",
      type: "line",
      source: "liaisons",
      paint: { "line-color": "#000", "line-opacity": 0, "line-width": 14 },
    });
    // une image par type (pictogramme sur pastille colorée par secteur)
    const dpr = 2, S = 30;
    for (const [type, emoji] of Object.entries(TYPE_EMOJI)) {
      const cv = document.createElement("canvas");
      cv.width = cv.height = S * dpr;
      const ctx = cv.getContext("2d");
      ctx.scale(dpr, dpr);
      ctx.beginPath();
      ctx.arc(S / 2, S / 2, 12, 0, 2 * Math.PI);
      ctx.fillStyle = "#fff";
      ctx.fill();
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = COULEURS[TYPE_SECTEUR[type]] || "#888";
      ctx.stroke();
      ctx.font = '15px "Noto Color Emoji","Apple Color Emoji","Segoe UI Emoji",system-ui';
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(emoji, S / 2, S / 2 + 1);
      const img = ctx.getImageData(0, 0, S * dpr, S * dpr);
      if (!map.hasImage("ic-" + type)) map.addImage("ic-" + type, img, { pixelRatio: dpr });
    }
    map.addSource("infra", { type: "geojson", data: geojson([]) });
    map.addLayer({
      id: "infra-pts",
      type: "symbol",
      source: "infra",
      layout: {
        "icon-image": ["concat", "ic-", ["get", "typeCle"]],
        "icon-size": ["interpolate", ["linear"], ["zoom"], 5, 0.7, 10, 1.05],
        "icon-allow-overlap": true,
      },
    });
    for (const couche of ["infra-pts", "infra-lignes-hit"]) {
      map.on("click", couche, ouvrirPopup);
      map.on("mouseenter", couche, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", couche, () => (map.getCanvas().style.cursor = ""));
    }
    mapPrete = true;
    rafraichirCarte();
  });
}

function geojsonLignes(list) {
  return {
    type: "FeatureCollection",
    features: list
      .filter((r) => r.latitude != null && r.latitude_arr != null)
      .map((r) => ({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [[r.longitude, r.latitude], [r.longitude_arr, r.latitude_arr]],
        },
        properties: propsDe(r),
      })),
  };
}

let dernier = [];
function pointsAffiches() {
  if (anneeDebut.value == null || plein.value) return dernier;
  const a = anneeDebut.value, b = anneeFin.value;
  return dernier.filter((r) => {
    if (!r.date_evenement) return false;
    const y = Number(r.date_evenement.slice(0, 4));
    return y >= a && y <= b;
  });
}
function rafraichirCarte() {
  if (!mapPrete) return;
  const list = pointsAffiches();
  if (map.getSource("infra")) map.getSource("infra").setData(geojson(list));
  if (map.getSource("liaisons")) map.getSource("liaisons").setData(geojsonLignes(list));
}
function majSource(list) {
  dernier = list;
  rafraichirCarte();
}

async function recharger() {
  chargement.value = true;
  try {
    const params = { ...f.value };
    const [liste, st] = await Promise.all([
      apiGet("/realisations", params),
      apiGet("/realisations/stats", params),
    ]);
    total.value = liste.total;
    dernier = liste.realisations;
    stats.value = st;
    // options de filtre (calculées côté API sur l'ensemble validé)
    opts.value = { annees: st.annees_dispo, types: st.types_dispo, regions: st.regions_dispo };
    // bornes de la chronologie
    const ans = (st.par_annee || []).map((d) => Number(d.cle)).filter((n) => !isNaN(n));
    if (ans.length) {
      anneeMin.value = Math.min(...ans);
      anneeMax.value = Math.max(...ans);
      if (anneeDebut.value == null || anneeDebut.value < anneeMin.value)
        anneeDebut.value = anneeMin.value;
      if (anneeFin.value == null || anneeFin.value > anneeMax.value)
        anneeFin.value = anneeMax.value;
    }
    rafraichirCarte();
    dessinerStats();
  } finally {
    chargement.value = false;
  }
}

function barres(el, data, horizontal) {
  if (!el) return;
  const c = roles();
  const cats = data.map((d) => d.cle);
  const vals = data.map((d) => d.n);
  const catAxis = { type: "category", data: cats, axisLine: { show: false }, axisTick: { show: false } };
  const valAxis = { type: "value", splitLine: { lineStyle: { color: c.grille } } };
  const opt = {
    ...baseOptions(c),
    grid: { left: 8, right: 16, top: 12, bottom: 8, containLabel: true },
    xAxis: horizontal ? valAxis : catAxis,
    yAxis: horizontal ? { ...catAxis, inverse: true } : valAxis,
    series: [{
      type: "bar",
      data: vals,
      itemStyle: { color: c.serie1, borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
      barMaxWidth: 22,
    }],
  };
  nettoyeurs.push(monter(el, opt));
}

function dessinerStats() {
  nettoyeurs.splice(0).forEach((f) => f());
  if (!stats.value) return;
  barres(gAnnee.value, stats.value.par_annee, false);
  barres(gType.value, stats.value.par_type.map((d) => ({ cle: libelleType(d.cle), n: d.n })), true);
  barres(gRegion.value, stats.value.par_region, true);
  barres(gStatut.value, stats.value.par_statut.map((d) => ({ cle: libelleStatut(d.cle), n: d.n })), true);
}

onMounted(async () => {
  initCarte();
  await recharger();
});
onBeforeUnmount(() => {
  stopLecture();
  nettoyeurs.splice(0).forEach((f) => f());
  if (map) map.remove();
});
</script>

<style scoped>
.note-methode { margin: 4px 0 14px; font-size: 0.9rem; color: var(--text-secondary); }
.note-methode summary { cursor: pointer; color: var(--accent); }
.note-methode p { margin: 8px 0 0; }
.filtres { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.filtres select { padding: 7px 10px; }
.onglets a { cursor: pointer; }
.chrono { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.btn-lire {
  width: 34px; height: 34px; border-radius: 50%; border: none; cursor: pointer;
  background: var(--accent); color: #fff; font-size: 0.9rem; flex: none;
}
/* double curseur : deux poignées pour sélectionner une période */
.dual { position: relative; flex: 1; min-width: 180px; max-width: 440px; height: 34px; }
.dual-track {
  position: absolute; top: 50%; left: 0; right: 0; transform: translateY(-50%);
  height: 4px; background: var(--border); border-radius: 2px;
}
.dual-fill { position: absolute; top: 0; bottom: 0; background: var(--accent); border-radius: 2px; }
.dual-in {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%; margin: 0;
  background: none; pointer-events: none; -webkit-appearance: none; appearance: none;
}
.dual-in::-webkit-slider-thumb {
  pointer-events: auto; -webkit-appearance: none; appearance: none;
  width: 18px; height: 18px; border-radius: 50%; background: var(--accent);
  border: 2px solid var(--surface-1); box-shadow: 0 0 0 1px var(--border); cursor: pointer;
}
.dual-in::-moz-range-thumb {
  pointer-events: auto; width: 18px; height: 18px; border-radius: 50%;
  background: var(--accent); border: 2px solid var(--surface-1); cursor: pointer;
}
.chrono-an { color: var(--text-secondary); font-size: 0.88rem; min-width: 110px; }
.btn-tout {
  background: none; border: 1px solid var(--border); border-radius: 6px;
  padding: 3px 8px; font-size: 0.8rem; color: var(--text-secondary); cursor: pointer;
}
.carte-wrap { border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.carte-mlg { height: min(72vh, 720px); width: 100%; }
@media (max-width: 768px) { .carte-mlg { height: 68vh; } }
.legende { display: flex; flex-wrap: wrap; gap: 12px; margin: 10px 0; font-size: 0.82rem; color: var(--text-secondary); }
.lg-item { display: inline-flex; align-items: center; gap: 5px; }
.lg-emo { font-size: 1rem; line-height: 1; }
.compteur { color: var(--text-muted); font-size: 0.9rem; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.kpi { padding: 14px 16px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-1); }
.kpi .v { font-size: 1.6rem; font-weight: 700; }
.kpi .l { color: var(--text-secondary); font-size: 0.85rem; }
.grille-graphes { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }
.bloc-graphe { padding: 14px 16px; }
.bloc-graphe h3 { font-size: 0.95rem; margin: 0 0 8px; }
.graphe-inf { height: 260px; width: 100%; }
:deep(.popup-inf) { font-size: 0.85rem; line-height: 1.5; }
:deep(.popup-inf .pstatut) { font-weight: 600; color: var(--accent); }
:deep(.maplibregl-popup-content) { background: var(--surface-1); color: var(--text-primary); }
:deep(.maplibregl-popup-content a) { color: var(--accent); }
</style>
