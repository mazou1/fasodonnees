<template>
  <h1>Recherche</h1>
  <p class="sous-titre">Personnalités, conseils des ministres, décisions, textes juridiques, Journal officiel et actualités.</p>

  <div class="filtres">
    <input
      v-model="q"
      type="search"
      placeholder="Rechercher sur tout le site…"
      @keyup.enter="lancer"
      autofocus
    />
    <button class="bouton" @click="lancer">Rechercher</button>
  </div>

  <template v-if="resultats">
    <p v-if="vide" class="vide">Aucun résultat pour « {{ resultats.q }} ».</p>

    <section v-if="resultats.personnes.length">
      <h2 class="titre-section">Personnalités</h2>
      <div class="grille-personnes">
        <router-link
          v-for="p in resultats.personnes"
          :key="p.id"
          :to="`/personnes/${p.id}`"
          class="carte personne"
        >
          <span class="avatar">{{ initiales(p.nom_complet) }}</span>
          <span>
            <span class="nom">{{ p.nom_complet }}</span>
            <span v-if="p.matricule" class="matricule"> · Mle {{ p.matricule }}</span>
          </span>
        </router-link>
      </div>
    </section>

    <section v-if="resultats.conseils.length">
      <h2 class="titre-section">Conseils des ministres</h2>
      <div class="liste">
        <router-link v-for="c in resultats.conseils" :key="c.id" :to="`/conseils/${c.id}`" class="item item-lien">
          <div class="meta">
            <span class="badge">Compte rendu</span>
            <span v-if="c.date">{{ formatDate(c.date) }}</span>
          </div>
          <div class="titre">{{ titreCourt(c.titre) }}</div>
          <div class="detail extrait" v-html="c.extrait"></div>
        </router-link>
      </div>
    </section>

    <section v-if="resultats.decisions.length">
      <h2 class="titre-section">Décisions</h2>
      <div class="liste">
        <router-link v-for="d in resultats.decisions" :key="d.id" :to="`/conseils/${d.document_id}`" class="item item-lien">
          <div class="meta">
            <span class="badge">Décision</span>
            <span v-if="d.date">Conseil du {{ formatDate(d.date) }}</span>
            <span v-if="d.ministere">{{ d.ministere }}</span>
          </div>
          <div class="detail">{{ d.objet }}</div>
        </router-link>
      </div>
    </section>

    <section v-if="resultats.textes.length">
      <h2 class="titre-section">Lois & décrets</h2>
      <div class="liste">
        <article v-for="t in resultats.textes" :key="t.id" class="item">
          <div class="meta">
            <span class="badge">{{ LIBELLES[t.type_doc] ?? t.type_doc }}</span>
            <span v-if="t.date">{{ formatDate(t.date) }}</span>
          </div>
          <div class="titre">{{ t.reference ? `N° ${t.reference}` : t.titre }}</div>
          <div class="detail extrait" v-html="t.extrait"></div>
          <a class="source" :href="t.url_pdf" target="_blank" rel="noopener">Texte intégral (PDF) →</a>
        </article>
      </div>
    </section>

    <section v-if="resultats.marches && resultats.marches.length">
      <h2 class="titre-section">Marchés publics</h2>
      <div class="liste">
        <article v-for="m in resultats.marches" :key="m.id" class="item">
          <div class="meta">
            <span class="badge">Quotidien des Marchés</span>
            <span v-if="m.date">{{ formatDate(m.date) }}</span>
          </div>
          <div class="titre"><a :href="m.url" target="_blank" rel="noopener">{{ m.titre }}</a></div>
          <div class="detail extrait" v-html="m.extrait"></div>
        </article>
      </div>
    </section>

    <section v-if="resultats.journaux && resultats.journaux.length">
      <h2 class="titre-section">Journal officiel</h2>
      <div class="liste">
        <article v-for="j in resultats.journaux" :key="j.id" class="item">
          <div class="meta">
            <span class="badge">Journal officiel</span>
            <span v-if="j.date">{{ formatDate(j.date) }}</span>
          </div>
          <div class="titre">
            <router-link :to="`/documents/${j.id}`">{{ j.titre }}</router-link>
          </div>
          <div class="detail extrait" v-html="j.extrait"></div>
        </article>
      </div>
    </section>

    <section v-if="resultats.actualites.length">
      <h2 class="titre-section">Actualités</h2>
      <div class="liste">
        <article v-for="a in resultats.actualites" :key="a.id" class="item">
          <div class="meta">
            <span class="badge">Article</span>
            <span v-if="a.date">{{ formatDate(a.date) }}</span>
          </div>
          <div class="titre"><a :href="a.url" target="_blank" rel="noopener">{{ a.titre }}</a></div>
          <div class="detail extrait" v-html="a.extrait"></div>
        </article>
      </div>
    </section>
  </template>
  <p v-else-if="chargement" class="chargement">Recherche…</p>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { apiGet } from "../api";

const LIBELLES = {
  decret: "Décret",
  loi: "Loi",
  arrete: "Arrêté",
  ordonnance: "Ordonnance",
  charte: "Charte",
  constitution: "Constitution",
  texte_juridique: "Texte",
};

const route = useRoute();
const router = useRouter();
const q = ref(String(route.query.q ?? ""));
const resultats = ref(null);
const chargement = ref(false);

const vide = computed(() => {
  const r = resultats.value;
  return (
    r &&
    !r.personnes.length &&
    !r.conseils.length &&
    !r.decisions.length &&
    !r.textes.length &&
    !(r.marches && r.marches.length) &&
    !(r.journaux && r.journaux.length) &&
    !r.actualites.length
  );
});

function initiales(nom) {
  return nom.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}
function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}
function titreCourt(t) {
  return (t || "Conseil des ministres").replace(/^CONSEIL DES MINISTRES\s*/i, "Conseil des ministres ");
}

function lancer() {
  if (q.value.trim().length >= 2) router.push({ path: "/recherche", query: { q: q.value.trim() } });
}

async function chercher() {
  const terme = String(route.query.q ?? "");
  if (terme.length < 2) return;
  q.value = terme;
  chargement.value = true;
  try {
    resultats.value = await apiGet("/recherche", { q: terme });
  } finally {
    chargement.value = false;
  }
}

watch(() => route.query.q, chercher);
onMounted(chercher);
</script>

<style scoped>
.titre-section { margin-top: 26px; }
.bouton {
  background: var(--accent); color: #fff; border: none; border-radius: 8px;
  padding: 8px 16px; font-weight: 600; cursor: pointer;
}
.item-lien { display: block; text-decoration: none; color: inherit; }
.item-lien:hover .titre { color: var(--accent); }
.grille-personnes { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
.personne { display: flex; gap: 10px; align-items: center; padding: 10px 14px; text-decoration: none; color: inherit; }
.personne:hover .nom { color: var(--accent); }
.personne .avatar {
  flex: none; width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; font-size: 0.8rem;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent); font-weight: 700;
}
.personne .nom { font-weight: 600; }
.personne .matricule { color: var(--text-muted); font-size: 0.8rem; }
.extrait :deep(b) { color: var(--accent); }
</style>
