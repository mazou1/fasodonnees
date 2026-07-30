<template>
  <template v-if="dossier">
    <p style="margin: 0"><router-link to="/suivi">← Suivi des annonces</router-link></p>

    <header class="carte entete-fiche">
      <div class="ligne-titre">
        <h1>{{ dossier.titre }}</h1>
        <span class="badge" :class="`stade-${dossier.stade}`">{{ libelleStade(dossier.stade) }}</span>
      </div>
      <div class="contexte">
        <span v-if="dossier.secteur">{{ dossier.secteur }}</span>
        <span v-if="dossier.region">{{ dossier.region }}</span>
      </div>

      <ol class="chaine" :aria-label="`Stade : ${libelleStade(dossier.stade)}`">
        <li
          v-for="s in STADES"
          :key="s.cle"
          :class="{ atteint: dossier.etapes_constatees.includes(s.cle) }"
          :title="dossier.etapes_constatees.includes(s.cle) ? `${s.libelle} — documenté` : `${s.libelle} — aucune pièce au dossier`"
        >
          <span class="puce" aria-hidden="true"></span>{{ s.libelle }}
        </li>
      </ol>
      <p class="note-chaine">
        Une étape éteinte signifie qu'<strong>aucune pièce du dossier ne l'atteste</strong> —
        pas nécessairement qu'elle n'a pas eu lieu.
      </p>
    </header>

    <div class="grille-tuiles">
      <div class="carte tuile">
        <div class="valeur">{{ fmtFCFA(dossier.montant_annonce_fcfa) }}</div>
        <div class="libelle">montant annoncé en Conseil des ministres</div>
      </div>
      <div class="carte tuile">
        <div class="valeur">{{ fmtFCFA(dossier.montant_attribue_fcfa) }}</div>
        <div class="libelle">montant attribué en marchés publics</div>
      </div>
      <div class="carte tuile">
        <div class="valeur">{{ dossier.maillons.length }}</div>
        <div class="libelle">pièces au dossier</div>
      </div>
    </div>

    <h2 class="titre-section">La chaîne, pièce par pièce</h2>
    <div class="chronologie">
      <article v-for="m in dossier.maillons" :key="`${m.genre}-${m.id}`" class="etape">
        <div class="puce-etape" :class="m.genre" aria-hidden="true"></div>
        <div class="contenu">
          <div class="meta">
            <span class="badge">{{ libelleGenre(m.genre) }}</span>
            <span v-if="m.date">{{ formatDate(m.date) }}</span>
            <span v-if="m.genre === 'realisation' && m.detail" class="badge-statut">
              {{ libelleStatutRealisation(m.detail) }}
            </span>
          </div>
          <div class="libelle-maillon">{{ m.libelle }}</div>
          <div class="details">
            <span v-if="m.montant_fcfa" class="montant">{{ fmtFCFA(m.montant_fcfa) }}</span>
            <span v-if="m.genre !== 'realisation' && m.detail">{{ m.detail }}</span>
          </div>
          <div class="liens">
            <router-link v-if="m.genre === 'marche'" :to="`/marches?q=${encodeURIComponent(m.libelle.slice(0, 40))}`">
              Voir dans les marchés →
            </router-link>
            <a v-if="m.document_id" :href="`/api/documents/${m.document_id}/fichier`" target="_blank" rel="noopener">
              Document officiel →
            </a>
            <a v-else-if="m.document_url" :href="m.document_url" target="_blank" rel="noopener">
              Source →
            </a>
          </div>
        </div>
      </article>
    </div>

    <p v-if="dossier.notes" class="notes carte">{{ dossier.notes }}</p>

    <p class="note-methode">
      Ce dossier réunit des pièces issues de trois corpus qui ne partagent aucun identifiant de
      projet : le rapprochement a été proposé automatiquement, puis <strong>accepté par un
      relecteur</strong>. Il ne prétend pas être exhaustif — d'autres marchés ou décisions
      peuvent concerner ce projet sans figurer ici. L'écart entre le montant annoncé et le
      montant attribué ne se lit pas comme un écart d'exécution : un marché ne couvre souvent
      qu'un lot de l'annonce. En cas de doute, les documents officiels liés ci-dessus font foi.
    </p>
  </template>
  <p v-else-if="erreur" class="vide">Ce dossier de suivi n'existe pas.</p>
  <p v-else class="chargement">Chargement…</p>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../api";

const STADES = [
  { cle: "annonce", libelle: "Annoncé" },
  { cle: "attribue", libelle: "Attribué" },
  { cle: "en_travaux", libelle: "En travaux" },
  { cle: "livre", libelle: "Livré" },
];
const GENRES = {
  engagement: "Annonce en Conseil des ministres",
  marche: "Marché attribué",
  realisation: "Réalisation constatée",
};
const STATUTS_REALISATION = {
  annonce: "Annoncée",
  premiere_pierre: "Première pierre",
  inauguration: "Inaugurée",
  mise_en_service: "Mise en service",
};

const route = useRoute();
const dossier = ref(null);
const erreur = ref(false);

function libelleStade(cle) {
  return STADES.find((s) => s.cle === cle)?.libelle ?? cle;
}
function libelleGenre(g) {
  return GENRES[g] ?? g;
}
function libelleStatutRealisation(s) {
  return STATUTS_REALISATION[s] ?? s;
}
function fmtFCFA(n) {
  if (n == null) return "—";
  if (n >= 1e9) return `${(n / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mds FCFA`;
  if (n >= 1e6) return `${(n / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M FCFA`;
  return `${n.toLocaleString("fr-FR")} FCFA`;
}
function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

async function charger() {
  dossier.value = null;
  erreur.value = false;
  try {
    dossier.value = await apiGet(`/projets/${route.params.id}`);
  } catch {
    erreur.value = true;
  }
}

onMounted(charger);
watch(() => route.params.id, charger);
</script>

<style scoped>
.entete-fiche { margin-top: 14px; }
.ligne-titre { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.ligne-titre h1 { margin: 0; font-size: 1.35rem; line-height: 1.3; }
.contexte { display: flex; gap: 12px; color: var(--text-secondary); font-size: 0.88rem; margin-top: 6px; }
.badge.stade-livre { background: color-mix(in srgb, #009e49 16%, transparent); color: #007a38; }
.badge.stade-en_travaux { background: color-mix(in srgb, #b8860b 18%, transparent); color: #8a6508; }
@media (prefers-color-scheme: dark) {
  .badge.stade-livre { color: #4ade80; }
  .badge.stade-en_travaux { color: #e3b341; }
}

.chaine { display: flex; flex-wrap: wrap; gap: 16px; list-style: none; padding: 0; margin: 14px 0 0; }
.chaine li { display: flex; align-items: center; gap: 6px; font-size: 0.82rem; color: var(--text-muted); }
.chaine .puce { width: 10px; height: 10px; border-radius: 50%; border: 1.5px solid currentColor; }
.chaine li.atteint { color: var(--accent); font-weight: 600; }
.chaine li.atteint .puce { background: currentColor; }
.note-chaine { color: var(--text-muted); font-size: 0.78rem; margin: 10px 0 0; }

.titre-section { margin-top: 28px; }
.chronologie { display: flex; flex-direction: column; }
.etape { display: flex; gap: 14px; padding: 14px 0; border-bottom: 1px solid var(--border); }
.etape:last-child { border-bottom: none; }
.puce-etape { flex: none; width: 11px; height: 11px; border-radius: 50%; margin-top: 6px; background: var(--text-muted); }
.puce-etape.engagement { background: #b8860b; }
.puce-etape.marche { background: #0a6b3c; }
.puce-etape.realisation { background: #ce1126; }
.contenu { min-width: 0; flex: 1; }
.libelle-maillon { font-weight: 600; margin: 4px 0; }
.details { display: flex; flex-wrap: wrap; gap: 12px; color: var(--text-secondary); font-size: 0.88rem; }
.details .montant { font-variant-numeric: tabular-nums; font-weight: 600; }
.badge-statut { background: var(--surface-2, rgba(127, 127, 127, 0.12)); padding: 1px 8px; border-radius: 999px; font-size: 0.72rem; }
.liens { display: flex; gap: 14px; font-size: 0.85rem; margin-top: 6px; flex-wrap: wrap; }
.notes { margin-top: 16px; font-size: 0.9rem; }
.note-methode { color: var(--text-muted); font-size: 0.82rem; margin-top: 20px; line-height: 1.6; }
</style>
