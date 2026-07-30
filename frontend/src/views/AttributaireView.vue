<template>
  <template v-if="fiche">
    <p style="margin: 0"><router-link to="/marches">← Marchés publics</router-link></p>

    <header class="carte entete-fiche">
      <div class="avatar-grand">{{ initiales(fiche.nom) }}</div>
      <div class="identite">
        <div class="ligne-nom">
          <h1>{{ fiche.nom }}</h1>
          <span class="badge">Entreprise attributaire</span>
        </div>
        <div class="resume" v-if="fiche.premiere_attribution">
          Attributaire de {{ fiche.nb_marches }} marché{{ fiche.nb_marches > 1 ? "s" : "" }} publics
          entre {{ annee(fiche.premiere_attribution) }} et {{ annee(fiche.derniere_attribution) }}.
        </div>
      </div>
    </header>

    <div class="grille-tuiles">
      <div class="carte tuile">
        <div class="valeur">{{ fmtFCFA(fiche.montant_fcfa) }}</div>
        <div class="libelle">total remporté</div>
      </div>
      <div class="carte tuile">
        <div class="valeur">{{ fiche.nb_marches.toLocaleString("fr-FR") }}</div>
        <div class="libelle">marchés attribués</div>
      </div>
      <div class="carte tuile">
        <div class="valeur">{{ fiche.par_autorite.length.toLocaleString("fr-FR") }}</div>
        <div class="libelle">autorités contractantes</div>
      </div>
    </div>

    <div class="grille-tableaux">
      <section class="carte" v-if="fiche.par_autorite.length">
        <h2>Auprès de quelles autorités contractantes</h2>
        <div class="table-defilante">
          <table class="tableau">
            <thead>
              <tr><th>Autorité</th><th class="num">Marchés</th><th class="num">Montant</th></tr>
            </thead>
            <tbody>
              <tr v-for="a in fiche.par_autorite" :key="a.cle">
                <td>{{ a.cle }}</td>
                <td class="num">{{ a.nombre }}</td>
                <td class="num">{{ fmtFCFA(a.montant_fcfa) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="carte" v-if="fiche.par_secteur.length">
        <h2>Par secteur</h2>
        <div class="table-defilante">
          <table class="tableau">
            <thead>
              <tr><th>Secteur</th><th class="num">Marchés</th><th class="num">Montant</th><th class="num">Part</th></tr>
            </thead>
            <tbody>
              <tr v-for="s in fiche.par_secteur" :key="s.cle">
                <td>{{ s.cle }}</td>
                <td class="num">{{ s.nombre }}</td>
                <td class="num">{{ fmtFCFA(s.montant_fcfa) }}</td>
                <td class="num">{{ part(s.montant_fcfa) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="carte" v-if="fiche.par_annee.length > 1">
        <h2>Par année</h2>
        <div class="table-defilante">
          <table class="tableau">
            <thead>
              <tr><th>Année</th><th class="num">Marchés</th><th class="num">Montant</th></tr>
            </thead>
            <tbody>
              <tr v-for="a in fiche.par_annee" :key="a.cle">
                <td>{{ a.cle }}</td>
                <td class="num">{{ a.nombre }}</td>
                <td class="num">{{ fmtFCFA(a.montant_fcfa) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <h2 class="titre-section">
      Marchés remportés <span class="compte">({{ fiche.nb_marches }})</span>
    </h2>
    <div class="liste">
      <article v-for="m in fiche.marches" :key="m.id" class="item">
        <div class="meta">
          <span class="badge">Marché attribué</span>
          <span v-if="m.secteur" class="badge-secteur">{{ m.secteur }}</span>
          <span v-if="m.date">Quotidien du {{ formatDate(m.date) }}</span>
          <span v-if="m.autorite">{{ m.autorite }}</span>
        </div>
        <div class="titre">{{ fmtFCFA(m.montant_fcfa) }}</div>
        <div class="detail">{{ m.objet }}</div>
        <ContexteSource genre="marche" :id="m.id" libelle="le Quotidien officiel" />
        <div class="meta" style="margin-top: 4px">
          <span v-if="m.reference" class="ref">{{ m.reference }}</span>
          <span v-if="m.attributaire && m.attributaire !== fiche.nom" class="graphie">
            écrit « {{ m.attributaire }} » dans ce Quotidien
          </span>
          <a class="source" :href="`/api/documents/${m.document_id}/fichier`" target="_blank" rel="noopener">
            Quotidien officiel (PDF) →
          </a>
        </div>
      </article>
    </div>
    <p v-if="fiche.marches.length < fiche.nb_marches" class="note-methode">
      Les {{ fiche.marches.length }} plus gros marchés sont affichés ici -
      <a :href="`/api/marches?attributaire_id=${fiche.id}&par_page=100`">les voir tous via l'API</a>.
    </p>

    <p v-if="fiche.nb_preselections" class="note-methode">
      Cette entreprise figure en outre parmi les candidats présélectionnés de
      {{ fiche.nb_preselections }} avis à manifestation d'intérêt. Une présélection
      n'attribue ni marché ni montant : elle n'entre donc dans aucun des chiffres
      ci-dessus -
      <router-link :to="`/marches?nature=preselection&q=${encodeURIComponent(fiche.nom)}`">les consulter</router-link>.
    </p>

    <p class="note-methode">
      Cette fiche regroupe les marchés attribués sous
      {{ fiche.variantes.length > 1 ? fiche.variantes.length + " graphies" : "une graphie" }}
      dans les Quotidiens de la DGCMEF<template v-if="fiche.variantes.length > 1">
        (<template v-for="(v, i) in fiche.variantes" :key="v">« {{ v }} »<template v-if="i < fiche.variantes.length - 1">, </template></template>)</template>.
      Le regroupement est automatique et strictement typographique (casse, accents, forme
      juridique) ; deux raisons sociales différentes ne sont jamais réunies sans relecture
      humaine. Seuls les marchés validés sont comptés - en cas de doute, le journal officiel
      fait foi.
    </p>
  </template>
  <p v-else-if="erreur" class="vide">Cette entreprise n'existe pas dans nos données.</p>
  <p v-else class="chargement">Chargement…</p>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../api";
import ContexteSource from "../components/ContexteSource.vue";

const route = useRoute();
const fiche = ref(null);
const erreur = ref(false);

function fmtFCFA(n) {
  if (n == null) return "-";
  if (n >= 1e9) return `${(n / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mds FCFA`;
  if (n >= 1e6) return `${(n / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M FCFA`;
  return `${n.toLocaleString("fr-FR")} FCFA`;
}
function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}
function annee(d) {
  return d ? new Date(d).getFullYear() : "";
}
function part(m) {
  const t = fiche.value?.montant_fcfa || 0;
  return t ? `${((100 * m) / t).toFixed(1)} %` : "-";
}
function initiales(nom) {
  return nom
    .split(/[\s-]+/)
    .filter((p) => /[a-zA-ZÀ-ÿ0-9]/.test(p))
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();
}

async function charger() {
  fiche.value = null;
  erreur.value = false;
  try {
    fiche.value = await apiGet(`/attributaires/${route.params.id}`);
  } catch {
    erreur.value = true;
  }
}

onMounted(charger);
watch(() => route.params.id, charger);
</script>

<style scoped>
.entete-fiche { display: flex; gap: 20px; align-items: center; margin-top: 14px; }
.avatar-grand {
  flex: none; width: 84px; height: 84px; border-radius: 16px;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent); font-weight: 800; font-size: 1.5rem;
}
.ligne-nom { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.ligne-nom h1 { margin: 0; }
.resume { color: var(--text-secondary); margin-top: 6px; }

.grille-tableaux { display: flex; flex-direction: column; gap: 16px; margin: 16px 0; }
.carte > h2 { font-size: 0.95rem; margin: 0 0 10px; }
.tableau { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.tableau th, .tableau td { padding: 7px 10px; border-bottom: 1px solid var(--border); text-align: left; }
.tableau .num { text-align: right; font-variant-numeric: tabular-nums; }

.titre-section { margin-top: 28px; }
.titre-section .compte { color: var(--text-muted); font-weight: 400; }
.badge-secteur { background: var(--series-1-fonce, #0a6b3c); color: #fff; padding: 1px 8px; border-radius: 999px; font-size: 0.72rem; }
.ref { font-variant-numeric: tabular-nums; }
.graphie { color: var(--text-muted); font-style: italic; }
.note-methode { color: var(--text-muted); font-size: 0.82rem; margin-top: 16px; }
</style>
