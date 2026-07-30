<template>
  <template v-if="conseil">
    <p style="margin: 0"><router-link to="/conseils">← Tous les conseils</router-link></p>

    <header class="hero">
      <div class="sur-titre">Communiqué · Conseil des ministres</div>
      <h1>{{ titreCourt }}</h1>
      <div class="hero-meta">
        <span v-if="conseil.date_conseil">{{ formatDate(conseil.date_conseil) }}</span>
        <span class="sep">·</span>
        <a :href="conseil.url" target="_blank" rel="noopener">source officielle →</a>
        <a v-if="conseil.pdf" class="bouton-pdf" :href="`/api/documents/${conseil.id}/fichier`" target="_blank" rel="noopener">
          📄 PDF officiel
        </a>
      </div>
    </header>

    <nav class="onglets">
      <a :class="{ actif: onglet === 'essentiel' }" href="#" @click.prevent="onglet = 'essentiel'">L'essentiel</a>
      <a :class="{ actif: onglet === 'integral' }" href="#" @click.prevent="onglet = 'integral'">Compte rendu intégral</a>
    </nav>

    <template v-if="onglet === 'essentiel'">
      <section v-if="conseil.decisions.length">
        <h2>Décisions ({{ conseil.decisions.length }})</h2>
        <div class="liste">
          <article v-for="d in conseil.decisions" :key="d.id" class="item">
            <div class="meta">
              <span class="badge">{{ LIBELLES_DECISION[d.type] ?? d.type }}</span>
              <span v-if="d.ministere">{{ d.ministere }}</span>
            </div>
            <div class="detail">{{ d.objet }}</div>
          </article>
        </div>
      </section>

      <section v-if="conseil.engagements.length" style="margin-top: 24px">
        <h2>Engagements financiers ({{ conseil.engagements.length }})</h2>
        <div class="liste">
          <article v-for="e in conseil.engagements" :key="e.id" class="item">
            <div class="meta"><span class="badge">{{ LIBELLES_ENGAGEMENT[e.type] ?? e.type }}</span></div>
            <div class="titre">
              {{ fmtFCFA(e.montant_fcfa) }}<template v-if="e.beneficiaire"> - {{ e.beneficiaire }}</template>
            </div>
            <div class="detail">{{ e.objet }}</div>
            <ContexteSource v-if="e.beneficiaire" genre="engagement" :id="e.id" />
          </article>
        </div>
      </section>

      <section v-if="conseil.nominations.length" style="margin-top: 24px">
        <h2>Nominations ({{ conseil.nominations.length }})</h2>
        <div class="liste">
          <article v-for="n in conseil.nominations" :key="n.id" class="item">
            <div class="meta">
              <span class="badge">{{ n.type === "fin_fonction" ? "Fin de fonction" : "Nomination" }}</span>
            </div>
            <div class="titre">{{ n.personne }}</div>
            <div class="detail">{{ n.poste }}<template v-if="n.structure"> - {{ n.structure }}</template></div>
            <ContexteSource genre="nomination" :id="n.id" />
          </article>
        </div>
      </section>
    </template>

    <template v-else>
      <article v-if="conseil.texte" class="carte texte-integral">
        <p v-for="(par, i) in paragraphes" :key="i" :class="{ 'titre-section': estTitre(par) }">{{ par }}</p>
      </article>
      <p v-else class="vide">
        Le texte de ce compte rendu n'a pas encore été extrait -
        <a :href="conseil.url" target="_blank" rel="noopener">consulter la source officielle</a>.
      </p>
    </template>
  </template>
  <p v-else class="chargement">Chargement…</p>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../api";
import ContexteSource from "../components/ContexteSource.vue";

const LIBELLES_DECISION = {
  adoption_decret: "Décret",
  adoption_loi: "Projet de loi",
  rapport: "Rapport",
  communication: "Communication",
  autorisation: "Autorisation",
  autre: "Autre",
};
const LIBELLES_ENGAGEMENT = {
  marche: "Marché public",
  convention: "Convention",
  pret: "Prêt",
  subvention: "Subvention",
  garantie: "Garantie",
  decaissement: "Décaissement",
  autre: "Autre",
};

const route = useRoute();
const conseil = ref(null);
const onglet = ref("essentiel");

const titreCourt = computed(() =>
  (conseil.value?.titre || "Conseil des ministres").replace(
    /^CONSEIL DES MINISTRES\s*/i,
    "Conseil des ministres ",
  ),
);

// blocs séparés par ligne vide ; les \n simples (autour des passages en gras
// dans le HTML source) sont des coupures d'affichage, pas des paragraphes
const paragraphes = computed(() =>
  (conseil.value?.texte || "")
    .split(/\n{2,}/)
    .map((p) => p.replace(/\s*\n\s*/g, " ").trim())
    .filter(Boolean),
);

// intertitres du communiqué : lignes courtes tout en majuscules (I. AU TITRE DE…)
function estTitre(par) {
  return par.length < 120 && par === par.toUpperCase() && /[A-ZÀ-Ü]/.test(par);
}

function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}
function fmtFCFA(n) {
  if (n == null) return "-";
  if (n >= 1e9) return `${(n / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mds FCFA`;
  if (n >= 1e6) return `${(n / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M FCFA`;
  return `${n.toLocaleString("fr-FR")} FCFA`;
}

onMounted(async () => {
  conseil.value = await apiGet(`/conseils/${route.params.id}`);
});
</script>

<style scoped>
.hero {
  margin-top: 14px; padding: 22px 24px; border-radius: 12px; color: #fff;
  background:
    radial-gradient(120% 160% at 100% 0%, rgba(255, 255, 255, 0.16), transparent 55%),
    linear-gradient(135deg, var(--series-1-fonce), var(--series-1));
  border-bottom: 3px solid;
  border-image: linear-gradient(90deg, #ce1126 50%, #009e49 50%) 1;
}
.hero .sur-titre { font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.85; }
.hero h1 { margin: 6px 0 8px; color: #fff; }
.hero-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 0.92rem; }
.hero-meta a { color: #fff; text-decoration: underline; }
.hero-meta .sep { opacity: 0.6; }
.bouton-pdf {
  margin-left: auto; background: rgba(255, 255, 255, 0.18); padding: 5px 12px;
  border-radius: 999px; font-weight: 600; text-decoration: none !important;
}
.bouton-pdf:hover { background: rgba(255, 255, 255, 0.3); }

.texte-integral { max-width: 820px; line-height: 1.7; }
.texte-integral p { margin: 0 0 12px; }
.texte-integral .titre-section { font-weight: 700; margin-top: 20px; }
</style>
