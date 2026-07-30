<template>
  <h1>L'Assemblée législative</h1>
  <p class="sous-titre">
    Composition de l'Assemblée législative du peuple, synchronisée depuis le
    <a href="https://www.assembleenationale.bf" target="_blank" rel="noopener">site officiel</a>.
  </p>

  <nav class="onglets">
    <router-link to="/assemblee" class="actif">Composition</router-link>
    <router-link to="/assemblee/lois">Lois votées</router-link>
  </nav>

  <div v-if="data" class="grille-tuiles">
    <div class="carte tuile">
      <div class="valeur">{{ data.stats.deputes }}</div>
      <div class="libelle">députés</div>
    </div>
    <div class="carte tuile" v-if="data.stats.legislature">
      <div class="valeur">{{ data.stats.legislature }}</div>
      <div class="libelle">législature</div>
    </div>
  </div>

  <template v-if="data?.president">
    <h2 class="titre-section">Président de l'Assemblée</h2>
    <article class="carte vedette">
      <img class="vedette-photo" :src="data.president.photo_url" :alt="data.president.nom_complet" />
      <div class="vedette-texte">
        <span class="badge">{{ data.president.role }}</span>
        <div class="vedette-nom">Dr {{ data.president.nom_complet }}</div>
        <div class="vedette-poste">
          Préside les travaux de l'Assemblée législative du peuple - 71 députés.
        </div>
      </div>
    </article>
  </template>

  <h2 class="titre-section" v-if="data">Les députés ({{ deputesFiltres.length }})</h2>
  <div class="filtres">
    <input v-model="q" type="search" placeholder="Rechercher un député…" />
  </div>
  <div v-if="data" class="grille-deputes">
    <article v-for="d in deputesFiltres" :key="d.nom_complet" class="carte depute">
      <img
        v-if="d.photo_url"
        :src="d.photo_url"
        :alt="d.nom_complet"
        loading="lazy"
        @error="(e) => (e.target.style.display = 'none')"
      />
      <div class="detail">{{ d.nom_complet }}</div>
      <div v-if="d.role" class="role">{{ d.role }}</div>
    </article>
  </div>
  <p v-else class="chargement">Chargement…</p>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../api";

const data = ref(null);
const q = ref("");

const deputesFiltres = computed(() => {
  const motif = q.value.trim().toLowerCase();
  const tous = data.value?.deputes ?? [];
  return motif ? tous.filter((d) => d.nom_complet.toLowerCase().includes(motif)) : tous;
});

onMounted(async () => {
  data.value = await apiGet("/assemblee");
});
</script>

<style scoped>
.titre-section { margin-top: 28px; }

.vedette { display: flex; gap: 24px; padding: 0; overflow: hidden; align-items: stretch; }
.vedette-photo { width: 240px; flex: none; aspect-ratio: 1 / 1.05; object-fit: cover; object-position: 50% 18%; }
.vedette-texte { display: flex; flex-direction: column; justify-content: center; gap: 10px; padding: 22px 22px 22px 0; }
.vedette .badge { align-self: flex-start; }
.vedette-nom { font-size: 1.5rem; font-weight: 800; line-height: 1.2; }
.vedette-poste { color: var(--text-secondary); }
@media (max-width: 640px) {
  .vedette { flex-direction: column; }
  .vedette-photo { width: 100%; max-height: 340px; }
  .vedette-texte { padding: 0 18px 18px; }
}

.grille-deputes { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.depute { text-align: center; padding: 12px; }
.depute img { width: 100%; height: 150px; object-fit: cover; border-radius: 8px; margin-bottom: 8px; }
.depute .role { color: var(--accent); font-size: 0.78rem; font-weight: 600; margin-top: 2px; }
</style>
