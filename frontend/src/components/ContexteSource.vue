<template>
  <div class="contexte">
    <button class="bascule" @click="basculer">
      {{ ouvert ? "▾" : "▸" }} Voir dans {{ libelle }}
    </button>
    <blockquote v-if="ouvert && passage" class="passage" v-html="passage"></blockquote>
    <p v-else-if="ouvert && chargement" class="etat">Recherche du passage…</p>
    <p v-else-if="ouvert" class="etat">
      Passage non localisé automatiquement -
      <a v-if="doc" :href="doc.url" target="_blank" rel="noopener">consulter le compte rendu</a>.
    </p>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { apiGet } from "../api";

const props = defineProps({
  genre: String,
  id: Number,
  libelle: { type: String, default: "le compte rendu officiel" },
});

const ouvert = ref(false);
const chargement = ref(false);
const passage = ref(null);
const doc = ref(null);
let charge = false;

async function basculer() {
  ouvert.value = !ouvert.value;
  if (ouvert.value && !charge) {
    charge = true;
    chargement.value = true;
    try {
      const r = await apiGet(`/contexte/${props.genre}/${props.id}`);
      passage.value = r.passage;
      doc.value = r.document;
    } finally {
      chargement.value = false;
    }
  }
}
</script>

<style scoped>
.contexte { margin-top: 8px; }
.bascule {
  border: none; background: none; padding: 0; cursor: pointer;
  color: var(--accent); font-size: 0.82rem; font-weight: 600;
}
.bascule:hover { text-decoration: underline; }
.passage {
  margin: 8px 0 0; padding: 10px 14px; border-left: 3px solid var(--series-1);
  background: color-mix(in srgb, var(--series-1) 6%, transparent);
  border-radius: 0 8px 8px 0; font-size: 0.9rem; line-height: 1.6; color: var(--text-secondary);
}
.passage :deep(mark) {
  background: color-mix(in srgb, var(--series-2) 30%, transparent);
  color: var(--text-primary); font-weight: 600; padding: 0 2px; border-radius: 3px;
}
.etat { margin: 8px 0 0; font-size: 0.85rem; color: var(--text-muted); }
</style>
