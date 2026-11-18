<template>
  <template v-if="doc">
    <router-link class="retour" to="/documents">← Tous les documents</router-link>
    <h1>{{ doc.titre || doc.url }}</h1>
    <p class="sous-titre">
      <span class="badge">{{ LIBELLES[doc.type_doc] ?? doc.type_doc }}</span>
      <template v-if="doc.date_publication"> · publié le {{ formatDate(doc.date_publication) }}</template>
      · {{ doc.source_nom }}
    </p>

    <nav class="onglets" v-if="doc.pdf && doc.texte_extrait">
      <button :class="{ actif: vue === 'pdf' }" @click="vue = 'pdf'">Document original</button>
      <button :class="{ actif: vue === 'texte' }" @click="vue = 'texte'">Texte</button>
    </nav>

    <div v-if="doc.fiche" class="carte fiche-lecture">
      <h2>En bref</h2>
      <p class="objet">{{ doc.fiche.objet }}</p>
      <dl>
        <template v-if="doc.fiche.issue_libelle"><dt>Décision</dt><dd><strong>{{ doc.fiche.issue_libelle }}</strong></dd></template>
        <dt>Nature</dt><dd>{{ doc.fiche.categorie_libelle }}</dd>
        <template v-if="doc.fiche.partie"><dt>{{ doc.fiche.issue ? "Saisine" : "Entité concernée" }}</dt><dd>{{ doc.fiche.partie }}</dd></template>
      </dl>
      <p>{{ doc.fiche.resume }}</p>
      <ul v-if="doc.fiche.points.length">
        <li v-for="(p, i) in doc.fiche.points" :key="i">{{ p }}</li>
      </ul>
      <p class="note-fiche">
        Fiche établie automatiquement à partir du texte, puis relue. Elle rapporte ce que le
        document énonce, sans le commenter - le document officiel fait foi.
      </p>
    </div>

    <!-- Le PDF est servi par une redirection vers l'archive : l'iframe suit la
         redirection comme un onglet le ferait. -->
    <div v-if="doc.pdf && vue === 'pdf'" class="cadre-pdf">
      <iframe :src="`/api/documents/${doc.id}/fichier`" :title="doc.titre || 'Document'"></iframe>
      <p class="repli">
        <!-- Safari iOS et plusieurs navigateurs Android n'affichent pas de PDF
             dans une iframe : sans cette porte de sortie, la page reste blanche
             et le lecteur croit le document manquant. -->
        Le document ne s'affiche pas ?
        <a :href="`/api/documents/${doc.id}/fichier`" target="_blank" rel="noopener">Ouvrir le PDF</a>
        <template v-if="doc.texte_extrait">
          ou <button class="lien" @click="vue = 'texte'">lire le texte</button>
        </template>.
      </p>
    </div>

    <div v-else-if="doc.texte_extrait" class="carte texte-document">
      <p class="avertissement">
        Texte extrait automatiquement du document. La mise en page d'origine n'est
        pas conservée, et l'extraction peut comporter des erreurs de lecture -
        le document officiel fait foi.
      </p>
      <pre>{{ doc.texte_extrait }}</pre>
    </div>

    <p v-else class="vide">
      Ce document n'a pas encore de version lisible dans la plateforme.
      <a v-if="!doc.source_retiree" :href="doc.url" target="_blank" rel="noopener">Le consulter à la source →</a>
      <template v-else>La source ne le publie plus.</template>
    </p>

    <div class="meta liens-bas">
      <a v-if="doc.pdf" class="source" :href="`/api/documents/${doc.id}/fichier`" target="_blank" rel="noopener">
        📄 Télécharger le PDF archivé
      </a>
      <a v-if="!doc.source_retiree" class="source" :href="doc.url" target="_blank" rel="noopener">Source d'origine →</a>
      <span v-else class="source">Retiré de la source - seule notre copie archivée subsiste</span>
      <router-link v-if="doc.type_doc === 'cr_conseil'" class="source" :to="`/conseils/${doc.id}`">
        Décisions et nominations extraites →
      </router-link>
    </div>
  </template>
  <p v-else-if="erreur" class="vide">Ce document n'existe pas dans nos données.</p>
  <p v-else class="chargement">Chargement…</p>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { apiGet } from "../api";

const LIBELLES = {
  cr_conseil: "Conseil des ministres",
  marche_public: "Marché public",
  journal_officiel: "Journal officiel",
  loi: "Loi",
  decret: "Décret",
  arrete: "Arrêté",
  ordonnance: "Ordonnance",
  constitution: "Constitution",
  charte: "Charte",
  communique: "Communiqué",
  article: "Article de presse",
  rapport_controle: "Rapport de contrôle",
  decision_constitutionnelle: "Décision constitutionnelle",
  avis_constitutionnel: "Avis constitutionnel",
};

const route = useRoute();
const doc = ref(null);
const erreur = ref(false);
// le PDF d'abord quand il existe : c'est la pièce qui fait foi
const vue = ref("pdf");

function formatDate(d) {
  return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

async function charger() {
  doc.value = null;
  erreur.value = false;
  try {
    doc.value = await apiGet(`/documents/${route.params.id}`);
    vue.value = doc.value.pdf ? "pdf" : "texte";
  } catch {
    erreur.value = true;
  }
}

onMounted(charger);
watch(() => route.params.id, charger);
</script>

<style scoped>
.retour { font-size: 0.85rem; }
.onglets button {
  border: none; background: none; cursor: pointer; font: inherit;
  color: var(--text-muted); padding: 8px 2px;
}
.onglets button.actif { color: var(--accent); font-weight: 600; }
.cadre-pdf iframe {
  width: 100%; height: min(80vh, 900px); border: 1px solid var(--border);
  border-radius: 8px; background: var(--surface-1);
}
.repli { color: var(--text-muted); font-size: 0.85rem; margin-top: 8px; }
.lien {
  border: none; background: none; padding: 0; font: inherit;
  color: var(--accent); cursor: pointer; text-decoration: underline;
}
.texte-document { padding: 18px; }
.avertissement { color: var(--text-muted); font-size: 0.82rem; margin: 0 0 12px; }
.texte-document pre {
  white-space: pre-wrap; word-wrap: break-word; font-family: inherit;
  font-size: 0.92rem; line-height: 1.6; margin: 0;
  max-height: 75vh; overflow-y: auto;
}
.liens-bas { margin-top: 16px; gap: 16px; flex-wrap: wrap; }
.fiche-lecture { margin-bottom: 16px; border-left: 3px solid var(--accent); }
.fiche-lecture h2 { margin: 0 0 6px; font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); }
.fiche-lecture .objet { font-weight: 600; font-size: 1.05rem; margin: 0 0 10px; }
.fiche-lecture dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 0 0 10px; font-size: 0.92rem; }
.fiche-lecture dt { color: var(--text-muted); }
.fiche-lecture dd { margin: 0; }
.fiche-lecture ul { margin: 8px 0; padding-left: 18px; line-height: 1.55; }
.note-fiche { color: var(--text-muted); font-size: 0.84rem; margin: 10px 0 0; }
</style>
