<template>
  <h1>Justice &amp; contrôle</h1>
  <p class="sous-titre">
    Qui contrôle l'État burkinabè, et ce que ce contrôle produit : la jurisprudence du
    <a href="https://www.conseil-constitutionnel.gov.bf" target="_blank" rel="noopener">Conseil
    constitutionnel</a> et les rapports d'audit de l'<a href="https://www.asce-lc.bf"
    target="_blank" rel="noopener">ASCE-LC</a>, l'autorité de contrôle d'État et de lutte
    contre la corruption. Chaque pièce est archivée en propre et renvoie à sa publication
    officielle.
  </p>

  <nav class="onglets">
    <button
      v-for="o in ONGLETS"
      :key="o.cle"
      :class="{ actif: onglet === o.cle }"
      @click="changerOnglet(o.cle)"
    >
      {{ o.libelle }}
      <span v-if="compteurs[o.cle] != null" class="compte">{{ compteurs[o.cle] }}</span>
    </button>
  </nav>

  <div class="filtres entete-recherche">
    <input v-model="q" type="search" placeholder="Recherche plein texte…" @input="rechercherDebounce" />
    <select v-model="type" @change="page = 1; recharger()">
      <option value="">Tous les types</option>
      <option v-for="t in facettes" :key="t.type_doc" :value="t.type_doc">
        {{ LIBELLES[t.type_doc] ?? t.type_doc }} ({{ t.n }})
      </option>
    </select>
    <a class="export" :href="lienApi" title="Données via l'API">API</a>
  </div>

  <div class="liste">
    <article v-for="d in documents" :key="d.id" class="item">
      <div class="meta">
        <span class="badge">{{ LIBELLES[d.type_doc] ?? d.type_doc }}</span>
        <span v-if="d.date_publication">{{ formatDate(d.date_publication) }}</span>
        <span>{{ d.source_nom }}</span>
      </div>
      <div class="titre">{{ d.titre || d.url }}</div>
      <div class="meta" style="margin-top: 6px">
        <a v-if="d.pdf" class="source" :href="`/api/documents/${d.id}/fichier`" target="_blank" rel="noopener">
          📄 PDF archivé →
        </a>
        <a class="source" :href="d.url" target="_blank" rel="noopener">Source d'origine →</a>
      </div>
    </article>
  </div>

  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="!documents.length" class="vide">Aucun document ne correspond à ces filtres.</p>

  <div class="pagination" v-if="pages > 1">
    <button :disabled="page <= 1" @click="page--; recharger()">← Précédent</button>
    <span>Page {{ page }} / {{ pages }}</span>
    <button :disabled="page >= pages" @click="page++; recharger()">Suivant →</button>
  </div>

  <section class="carte manque">
    <h2>Ce qui manque : la Cour des comptes</h2>
    <p>
      La Cour des comptes est la juridiction financière du Burkina Faso : elle juge les comptes
      des comptables publics et contrôle l'exécution des lois de finances. Ses rapports sont,
      avec ceux de l'ASCE-LC, les documents de redevabilité les plus importants du pays.
    </p>
    <p>
      <strong>Elle n'a aujourd'hui aucun site accessible</strong> — aucun des domaines connus ne
      répond (vérifié le 29 juillet 2026). Ses rapports ne sont donc pas collectables, et cette
      page en est amputée. Nous l'écrivons plutôt que de laisser croire à une couverture
      complète du contrôle de l'État.
    </p>
    <p class="appel">
      Vous connaissez une source officielle publiant ces rapports ?
      <a href="https://github.com/mazou1/fasodonnees/issues" target="_blank" rel="noopener">Signalez-la</a> —
      c'est la contribution la plus utile que l'on puisse apporter à cette page.
    </p>
  </section>

  <p class="note-methode">
    Corpus archivé tel que publié par les institutions : la plateforme ne commente ni ne résume
    les décisions et les rapports. Le Conseil constitutionnel publie ses décisions, avis et
    ordonnances par année — ils sont ici distingués, un avis n'ayant pas la portée d'une
    décision. Côté ASCE-LC, l'article d'annonce et le rapport lui-même sont archivés séparément :
    c'est le PDF qui porte le contenu de l'audit.
  </p>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../api";

const PAR_PAGE = 20;
const ONGLETS = [
  { cle: "conseil_constitutionnel", libelle: "Conseil constitutionnel" },
  { cle: "asce_lc", libelle: "Contrôle & anticorruption (ASCE-LC)" },
];
const LIBELLES = {
  decision_constitutionnelle: "Décision",
  avis_constitutionnel: "Avis",
  ordonnance_constitutionnelle: "Ordonnance",
  rapport_controle: "Rapport de contrôle",
  affaire_anticorruption: "Affaire anticorruption",
  declaration_patrimoine: "Déclaration de patrimoine",
  plainte_denonciation: "Plaintes & dénonciations",
  communique: "Communiqué",
};

const onglet = ref(ONGLETS[0].cle);
const documents = ref([]);
const facettes = ref([]);
const compteurs = ref({});
const total = ref(0);
const q = ref("");
const type = ref("");
const page = ref(1);
const chargement = ref(false);
let minuterie = null;

const pages = computed(() => Math.ceil(total.value / PAR_PAGE));
const lienApi = computed(() => {
  const p = new URLSearchParams({ source: onglet.value });
  if (type.value) p.set("type_doc", type.value);
  return "/api/documents?" + p;
});

function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

function changerOnglet(cle) {
  onglet.value = cle;
  type.value = "";
  page.value = 1;
  recharger();
}

async function recharger() {
  chargement.value = true;
  try {
    const r = await apiGet("/documents", {
      source: onglet.value,
      type_doc: type.value || undefined,
      q: q.value.length >= 2 ? q.value : undefined,
      page: page.value,
      par_page: PAR_PAGE,
    });
    documents.value = r.documents;
    total.value = r.total;
    if (!type.value) facettes.value = r.types;
    compteurs.value = { ...compteurs.value, [onglet.value]: r.total };
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
  await recharger();
  // compteur de l'autre onglet, pour que les deux volumes soient lisibles d'emblée
  const autre = ONGLETS.find((o) => o.cle !== onglet.value);
  const r = await apiGet("/documents", { source: autre.cle, par_page: 1 });
  compteurs.value = { ...compteurs.value, [autre.cle]: r.total };
});
</script>

<style scoped>
.onglets { display: flex; gap: 8px; flex-wrap: wrap; margin: 16px 0; }
.onglets button {
  border: 1px solid var(--border); background: var(--surface-1); color: inherit;
  padding: 7px 14px; border-radius: 999px; cursor: pointer; font-size: 0.9rem;
}
.onglets button.actif { background: var(--accent); color: #fff; border-color: var(--accent); }
.onglets .compte { opacity: 0.7; margin-left: 6px; font-variant-numeric: tabular-nums; }
.entete-recherche { align-items: center; flex-wrap: wrap; gap: 12px; }
.entete-recherche input[type="search"] { flex: 1; max-width: 340px; }

.manque { margin-top: 28px; border-left: 3px solid #ce1126; }
.manque h2 { font-size: 1rem; margin: 0 0 10px; }
.manque p { color: var(--text-secondary); font-size: 0.9rem; line-height: 1.6; margin: 0 0 10px; }
.manque .appel { color: var(--text-muted); font-size: 0.85rem; margin-bottom: 0; }
.note-methode { color: var(--text-muted); font-size: 0.82rem; margin-top: 20px; line-height: 1.6; }
</style>
