<template>
  <template v-if="fiche">
    <p style="margin: 0"><router-link to="/annuaire">← Annuaire de l'État</router-link></p>

    <header class="carte entete-fiche">
      <div class="avatar-grand">{{ initiales(fiche.nom_complet) }}</div>
      <div class="identite">
        <div class="ligne-nom">
          <h1>{{ fiche.nom_complet }}</h1>
          <span class="badge" :class="{ actif: fiche.en_fonction }">
            {{ fiche.en_fonction ? "● En fonction" : "Plus en fonction" }}
          </span>
          <span class="badge" v-if="fiche.matricule" title="Matricule de la fonction publique - identifie la personne dans les comptes rendus">
            Mle {{ fiche.matricule }}
          </span>
        </div>
        <div class="fonction-actuelle" v-if="actuelle">
          {{ actuelle.poste }}<template v-if="actuelle.structure"> - {{ actuelle.structure }}</template>
          <span class="depuis" v-if="actuelle.date_debut"> · depuis le {{ formatDate(actuelle.date_debut) }}</span>
        </div>
      </div>
    </header>

    <p class="note-homonymes" v-if="fiche.homonymes.length">
      {{ fiche.homonymes.length }} autre{{ fiche.homonymes.length > 1 ? "s" : "" }} personne{{ fiche.homonymes.length > 1 ? "s" : "" }}
      porte{{ fiche.homonymes.length > 1 ? "nt" : "" }} ce nom (distinguées par matricule) :
      <template v-for="(h, i) in fiche.homonymes" :key="h.id">
        <router-link :to="`/personnes/${h.id}`">{{ h.matricule ? `Mle ${h.matricule}` : "sans matricule" }}</router-link><template v-if="i < fiche.homonymes.length - 1"> · </template>
      </template>
    </p>

    <h2 class="titre-section">Historique des fonctions <span class="compte">({{ fiche.fonctions.length }})</span></h2>
    <p class="note-homonymes" v-if="fiche.homonymes.length || (!fiche.matricule && fiche.fonctions.length > 4)">
      Les fonctions sont rattachées par matricule quand le compte rendu le cite ; celles qui ne le
      citent pas restent sur cette fiche et peuvent concerner un homonyme.
    </p>
    <div class="chronologie">
      <article v-for="(f, i) in fiche.fonctions" :key="i" class="etape" :class="{ encours: !f.date_fin }">
        <div class="puce">{{ f.date_fin ? "○" : "●" }}</div>
        <div class="contenu">
          <div class="poste">{{ f.poste }}</div>
          <div class="structure" v-if="f.structure">{{ f.structure }}</div>
          <div class="dates">
            <template v-if="f.date_debut">{{ formatDate(f.date_debut) }}</template>
            <template v-else>Date inconnue</template>
            -
            <template v-if="f.date_fin">{{ formatDate(f.date_fin) }}</template>
            <strong v-else>en cours</strong>
          </div>
          <div class="source" v-if="f.source_url">
            Source :
            <router-link v-if="f.source_id" :to="`/conseils/${f.source_id}`">{{ sourceCourte(f) }}</router-link>
            <a v-else :href="f.source_url" target="_blank" rel="noopener">{{ sourceCourte(f) }}</a>
          </div>
          <ContexteSource v-if="f.nomination_id" genre="nomination" :id="f.nomination_id" />
        </div>
      </article>
    </div>
  </template>
  <p v-else class="chargement">Chargement…</p>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../api";
import ContexteSource from "../components/ContexteSource.vue";

const route = useRoute();
const fiche = ref(null);

const actuelle = computed(() => fiche.value?.fonctions.find((f) => !f.date_fin) ?? null);

function initiales(nom) {
  return nom
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();
}
function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}
function sourceCourte(f) {
  return (f.source_titre || "compte rendu officiel").replace(
    /^CONSEIL DES MINISTRES\s*/i,
    "Conseil des ministres ",
  );
}

onMounted(async () => {
  fiche.value = await apiGet(`/personnes/${route.params.id}`);
});
</script>

<style scoped>
.entete-fiche { display: flex; gap: 20px; align-items: center; margin-top: 14px; }
.avatar-grand {
  flex: none; width: 84px; height: 84px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent); font-weight: 800; font-size: 1.6rem;
}
.ligne-nom { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.ligne-nom h1 { margin: 0; }
.badge.actif { background: color-mix(in srgb, #009e49 16%, transparent); color: #007a38; }
@media (prefers-color-scheme: dark) { .badge.actif { color: #4ade80; } }
.fonction-actuelle { color: var(--text-secondary); margin-top: 6px; }
.depuis { color: var(--text-muted); }

.titre-section { margin-top: 28px; }
.titre-section .compte { color: var(--text-muted); font-weight: 400; }

.note-homonymes { color: var(--text-muted); font-size: 0.85rem; margin: 10px 0; }

.chronologie { display: flex; flex-direction: column; }
.etape { display: flex; gap: 14px; padding: 14px 0; border-bottom: 1px solid var(--border); }
.etape:last-child { border-bottom: none; }
.puce { flex: none; width: 22px; text-align: center; color: var(--text-muted); }
.etape.encours .puce { color: #009e49; }
.contenu { min-width: 0; }
.poste { font-weight: 700; }
.etape.encours .poste { color: var(--accent); }
.structure { color: var(--text-secondary); font-size: 0.92rem; }
.dates { color: var(--text-muted); font-size: 0.85rem; margin-top: 4px; }
.source { font-size: 0.85rem; margin-top: 4px; }
</style>
