<template>
  <h1>Services numériques de l'État</h1>
  <p class="sous-titre">
    L'annuaire des sites et téléservices officiels du Burkina Faso, regroupés au même endroit -
    état civil, justice, diaspora, impôts, entreprises, foncier, concours, santé et services aux usagers.
    Chaque lien pointe vers un site public officiel.
  </p>

  <p v-if="annuaire && annuaire.verifie_le" class="bilan">
    <span class="pastille en_ligne"></span>
    <strong>{{ annuaire.en_ligne }} services sur {{ annuaire.total }} en ligne</strong>
    <span class="quand">- état vérifié automatiquement {{ quand(annuaire.verifie_le) }}</span>
  </p>

  <component
    :is="lien(annuaire.phare) ? 'a' : 'div'"
    v-if="annuaire && !q.trim()"
    class="portail-phare"
    :href="lien(annuaire.phare)"
    target="_blank"
    rel="noopener"
  >
    <span class="pf-ico" aria-hidden="true">🪪</span>
    <span class="pf-txt">
      <span class="pf-titre">{{ annuaire.phare.nom }}</span>
      <span class="pf-desc">{{ annuaire.phare.desc }}</span>
      <span class="pf-dom">
        {{ domaine(annuaire.phare.url) }} ↗
        <span v-if="annuaire.phare.etat" class="etat" :class="annuaire.phare.etat.statut">
          <span class="pastille" :class="annuaire.phare.etat.statut"></span>{{ libelleEtat(annuaire.phare.etat) }}
        </span>
      </span>
    </span>
  </component>

  <div class="filtres">
    <input v-model="q" type="search" placeholder="Chercher un service (ex : casier, timbre, diaspora, visa…)" />
    <label v-if="annuaire && annuaire.verifie_le" class="case">
      <input v-model="seulementEnLigne" type="checkbox" /> Seulement les services en ligne
    </label>
  </div>

  <template v-for="section in sectionsFiltrees" :key="section.titre">
    <h2 class="titre-section">
      <span class="ico" aria-hidden="true">{{ section.emoji }}</span> {{ section.titre }}
    </h2>
    <div class="grille-services">
      <component
        :is="lien(s) ? 'a' : 'div'"
        v-for="s in section.services"
        :key="s.url"
        class="item service"
        :class="{ 'item-lien': lien(s), indisponible: s.etat && s.etat.statut !== 'en_ligne' && s.etat.statut !== 'inconnu' }"
        :href="lien(s)"
        target="_blank"
        rel="noopener"
      >
        <div class="tete">
          <span class="titre">{{ s.nom }}</span>
          <span v-if="s.sigle" class="badge">{{ s.sigle }}</span>
        </div>
        <div class="detail">{{ s.desc }}</div>
        <div class="bas">
          <span class="dom">{{ domaine(s.url) }}<template v-if="lien(s)"> ↗</template></span>
          <span v-if="s.etat" class="etat" :class="s.etat.statut">
            <span class="pastille" :class="s.etat.statut"></span>{{ libelleEtat(s.etat) }}
          </span>
        </div>
      </component>
    </div>
  </template>
  <p v-if="chargement" class="chargement">Chargement…</p>
  <p v-else-if="erreur" class="vide">L'annuaire n'a pas pu être chargé. Réessayez dans un instant.</p>
  <p v-else-if="!sectionsFiltrees.length" class="vide">Aucun service ne correspond.</p>

  <p class="note-methode">
    Nous ne référençons que des sites officiels. L'état de chacun est vérifié automatiquement deux
    fois par jour depuis notre serveur, comme le verrait un visiteur : le site répond-il, son
    certificat de sécurité est-il valide, sert-il autre chose qu'une page de maintenance&nbsp;?
    Un site signalé en panne peut être revenu depuis le dernier passage, et un site vu en ligne
    d'ici peut être inaccessible de chez vous. Quand le certificat d'un site est invalide, nous
    n'affichons pas de lien cliquable. Un site manque&nbsp;? Signalez-le sur le dépôt du projet.
  </p>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet } from "../api";

const annuaire = ref(null);
const chargement = ref(true);
const erreur = ref(false);
const q = ref("");
const seulementEnLigne = ref(false);

const LIBELLES = {
  en_ligne: "En ligne",
  maintenance: "En maintenance",
  en_panne: "En panne",
  certificat: "Certificat invalide",
  injoignable: "Injoignable",
  inconnu: "État non vérifiable",
};

function domaine(url) {
  return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
}

/** Pas de lien vers un site dont le certificat est invalide : le navigateur
    afficherait une alerte de sécurité, et nous n'y envoyons personne. */
function lien(service) {
  return service.etat && service.etat.statut === "certificat" ? undefined : service.url;
}

function libelleEtat(etat) {
  const libelle = LIBELLES[etat.statut] ?? etat.statut;
  if (etat.statut === "en_ligne" || etat.statut === "inconnu" || !etat.depuis) return libelle;
  const depuis = new Date(etat.depuis).toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
  return `${libelle} depuis le ${depuis}`;
}

function quand(iso) {
  const d = new Date(iso);
  const heure = d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  const jour = d.toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
  return d.toDateString() === new Date().toDateString() ? `aujourd'hui à ${heure}` : `le ${jour} à ${heure}`;
}

const sectionsFiltrees = computed(() => {
  if (!annuaire.value) return [];
  const motif = q.value.trim().toLowerCase();
  return annuaire.value.sections
    .map((s) => ({
      ...s,
      services: s.services.filter(
        (x) =>
          (!seulementEnLigne.value || (x.etat && x.etat.statut === "en_ligne")) &&
          (!motif ||
            x.nom.toLowerCase().includes(motif) ||
            x.desc.toLowerCase().includes(motif) ||
            (x.sigle || "").toLowerCase().includes(motif) ||
            domaine(x.url).includes(motif)),
      ),
    }))
    .filter((s) => s.services.length);
});

onMounted(async () => {
  try {
    annuaire.value = await apiGet("/services-numeriques");
  } catch {
    erreur.value = true;
  } finally {
    chargement.value = false;
  }
});
</script>

<style scoped>
.portail-phare {
  display: flex; align-items: center; gap: 16px; margin: 4px 0 22px;
  padding: 18px 20px; border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--border));
  background: color-mix(in srgb, var(--accent) 8%, var(--surface-1));
  color: inherit;
}
.portail-phare:hover { text-decoration: none; border-color: var(--accent); }
.portail-phare .pf-ico { font-size: 2rem; line-height: 1; flex: none; }
.portail-phare .pf-txt { display: flex; flex-direction: column; gap: 3px; }
.portail-phare .pf-titre { font-weight: 700; font-size: 1.05rem; }
.portail-phare .pf-desc { color: var(--text-secondary); font-size: 0.92rem; }
.portail-phare .pf-dom { color: var(--accent); font-size: 0.84rem; font-weight: 600; }

.titre-section { margin-top: 28px; display: flex; align-items: center; gap: 8px; }
.titre-section .ico { font-size: 1.1em; }
.grille-services {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.service { display: flex; flex-direction: column; gap: 6px; height: 100%; }
.service .tete { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.service .titre { font-weight: 600; }
.service .detail { color: var(--text-secondary); font-size: 0.92rem; flex: 1; }
.service .dom { color: var(--text-muted); font-size: 0.82rem; font-variant-numeric: tabular-nums; }
.service .bas { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.service.indisponible .titre, .service.indisponible .detail { opacity: 0.7; }
.bilan { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0 0 16px; }
.bilan .quand { color: var(--text-muted); font-size: 0.9rem; }
.case { display: inline-flex; align-items: center; gap: 6px; font-size: 0.9rem; color: var(--text-secondary); }
/* L'état se lit au libellé ; la couleur ne fait que l'appuyer. */
.etat { display: inline-flex; align-items: center; gap: 5px; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); white-space: nowrap; }
.etat.en_panne, .etat.injoignable, .etat.certificat { color: #b3261e; }
.etat.maintenance { color: #9a5b00; }
.etat.inconnu { color: var(--text-muted); font-weight: 400; }
.pastille { flex: none; width: 9px; height: 9px; border-radius: 50%; background: var(--text-muted); }
.pastille.en_ligne { background: #009e49; }
.pastille.maintenance { background: #e08a00; }
.pastille.en_panne, .pastille.injoignable, .pastille.certificat { background: #ce1126; }
.portail-phare .etat { margin-left: 10px; }
.note-methode {
  margin-top: 30px; color: var(--text-muted); font-size: 0.86rem;
  border-top: 1px solid var(--border); padding-top: 16px; line-height: 1.55;
}
</style>
