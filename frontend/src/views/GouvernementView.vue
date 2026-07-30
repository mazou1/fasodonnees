<template>
  <h1>Le Gouvernement</h1>
  <p class="sous-titre" v-if="data">
    Composition officielle publiée par la
    <a :href="data.source.url" target="_blank" rel="noopener">Présidence du Faso</a>
    <template v-if="data.source.date"> (mise à jour du {{ formatDate(data.source.date) }})</template>.
  </p>

  <div v-if="data" class="grille-tuiles">
    <div class="carte tuile">
      <div class="valeur">{{ data.stats.membres }}</div>
      <div class="libelle">membres du gouvernement</div>
    </div>
    <div class="carte tuile">
      <div class="valeur">{{ data.stats.femmes }}</div>
      <div class="libelle">femmes ({{ pct(data.stats.femmes, data.stats.membres) }})</div>
    </div>
    <div class="carte tuile">
      <div class="valeur">{{ militaires }}</div>
      <div class="libelle">officiers ({{ pct(militaires, data.stats.membres) }})</div>
    </div>
  </div>

  <template v-if="data">
    <section v-for="v in vedettes" :key="v.badge">
      <h2 class="titre-section">{{ v.badge }}</h2>
      <article class="carte vedette">
        <img class="vedette-photo" :src="v.m.photo_url" :alt="v.m.nom_complet" />
        <div class="vedette-texte">
          <span class="badge">{{ v.badge }}</span>
          <div class="vedette-nom">{{ prefixeGrade(v.m) }}{{ v.m.nom_complet }}</div>
          <div class="vedette-poste">{{ v.m.poste }}</div>
        </div>
      </article>
    </section>

    <h2 class="titre-section">Les ministres ({{ data.ministres.length }})</h2>
    <div class="grille-ministres">
      <article v-for="m in data.ministres" :key="m.ordre" class="carte-ministre" :title="m.poste">
        <img :src="m.photo_url" :alt="m.nom_complet" loading="lazy" />
        <div class="voile">
          <div class="nom">{{ m.nom_complet }}</div>
          <div class="poste">{{ m.civilite && !civil(m.civilite) ? m.civilite + " - " : "" }}{{ m.poste }}</div>
        </div>
      </article>
    </div>
  </template>
  <p v-else class="chargement">Chargement…</p>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../api";

const data = ref(null);

const militaires = computed(() => {
  const tous = [data.value?.premier_ministre, ...(data.value?.ministres ?? [])].filter(Boolean);
  return tous.filter((m) => m.civilite && !civil(m.civilite)).length;
});

const vedettes = computed(() =>
  [
    data.value?.president && { badge: "Président du Faso", m: data.value.president },
    data.value?.premier_ministre && { badge: "Premier ministre", m: data.value.premier_ministre },
  ].filter(Boolean),
);

function civil(c) {
  return ["monsieur", "madame"].includes((c || "").trim().toLowerCase());
}
function prefixeGrade(m) {
  return m.civilite && !civil(m.civilite) ? `${m.civilite} ` : "";
}
function pct(n, total) {
  return total ? `${Math.round((n / total) * 100)} %` : "-";
}
function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

onMounted(async () => {
  data.value = await apiGet("/gouvernement");
});
</script>

<style scoped>
.titre-section { margin-top: 28px; }

/* Cartes vedettes (Président, Premier ministre) - photo officielle entière */
.vedette { display: flex; gap: 24px; padding: 0; overflow: hidden; align-items: stretch; }
.vedette-photo { width: 260px; flex: none; aspect-ratio: 1 / 1.05; object-fit: cover; object-position: 50% 22%; }
.vedette-texte { display: flex; flex-direction: column; justify-content: center; gap: 10px; padding: 22px 22px 22px 0; }
.vedette .badge { align-self: flex-start; }
.vedette-nom { font-size: 1.5rem; font-weight: 800; line-height: 1.2; }
.vedette-poste { color: var(--text-secondary); }
@media (max-width: 640px) {
  .vedette { flex-direction: column; }
  .vedette-photo { width: 100%; max-height: 340px; }
  .vedette-texte { padding: 0 18px 18px; }
}

/* Grille des ministres - portrait plein cadre, nom en surimpression */
.grille-ministres { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.carte-ministre {
  position: relative; aspect-ratio: 1 / 1.05; border-radius: 12px; overflow: hidden;
  border: 1px solid var(--border); background: var(--surface-1);
}
.carte-ministre img {
  width: 100%; height: 100%; object-fit: cover; object-position: 50% 22%;
}
.voile {
  position: absolute; inset: auto 0 0 0; padding: 34px 12px 10px;
  background: linear-gradient(transparent, rgba(10, 14, 20, 0.86));
  color: #fff;
}
.voile .nom { font-weight: 700; line-height: 1.2; }
.voile .poste {
  font-size: 0.78rem; opacity: 0.85; margin-top: 2px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
</style>
