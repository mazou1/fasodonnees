<template>
  <h1>Services numériques de l'État</h1>
  <p class="sous-titre">
    L'annuaire des sites et téléservices officiels du Burkina Faso, regroupés au même endroit -
    institutions, textes de loi, finances, statistiques, concours et services aux usagers.
    Chaque lien pointe vers un site public officiel.
  </p>

  <a v-if="!q.trim()" class="portail-phare" href="https://service-public.gov.bf" target="_blank" rel="noopener">
    <span class="pf-ico" aria-hidden="true">🪪</span>
    <span class="pf-txt">
      <span class="pf-titre">Service Public BF - le guichet unique de l'administration</span>
      <span class="pf-desc">Le portail officiel de l'État qui centralise les démarches en ligne (guides pratiques, procédures dématérialisées, institutions). Le point de départ pour toute démarche.</span>
      <span class="pf-dom">service-public.gov.bf ↗</span>
    </span>
  </a>

  <div class="filtres">
    <input v-model="q" type="search" placeholder="Chercher un service (ex : impôts, marchés, statistique…)" />
  </div>

  <template v-for="section in sectionsFiltrees" :key="section.titre">
    <h2 class="titre-section">
      <span class="ico" aria-hidden="true">{{ section.emoji }}</span> {{ section.titre }}
    </h2>
    <div class="grille-services">
      <a
        v-for="s in section.services"
        :key="s.url"
        class="item item-lien service"
        :href="s.url"
        target="_blank"
        rel="noopener"
      >
        <div class="tete">
          <span class="titre">{{ s.nom }}</span>
          <span v-if="s.sigle" class="badge">{{ s.sigle }}</span>
        </div>
        <div class="detail">{{ s.desc }}</div>
        <div class="dom">{{ domaine(s.url) }} ↗</div>
      </a>
    </div>
  </template>
  <p v-if="!sectionsFiltrees.length" class="vide">Aucun service ne correspond.</p>

  <p class="note-methode">
    Nous ne référençons que les sites officiels dont l'accès a été vérifié joignable
    (juillet 2026). Quelques services existants ont été écartés parce qu'ils étaient
    injoignables ou présentaient un certificat de sécurité invalide au moment de la
    vérification (ex. SONABEL, La Poste BF) - ils seront ajoutés dès qu'ils redeviennent
    accessibles en toute sécurité. Un site manque&nbsp;? Signalez-le sur le dépôt du projet.
  </p>
</template>

<script setup>
import { computed, ref } from "vue";

const SECTIONS = [
  {
    titre: "Institutions & pouvoirs publics",
    emoji: "🏛️",
    services: [
      { nom: "Présidence du Faso", url: "https://www.presidencedufaso.bf", desc: "Le site de la Présidence : communiqués, agenda et actes du Chef de l'État." },
      { nom: "Gouvernement du Burkina Faso", url: "https://www.gouvernement.gov.bf", desc: "Portail du Gouvernement : comptes rendus du Conseil des ministres, communiqués et action gouvernementale." },
      { nom: "Assemblée législative du peuple", sigle: "ALP", url: "https://www.assembleenationale.bf", desc: "L'organe législatif : lois votées, députés et travaux parlementaires." },
      { nom: "Conseil constitutionnel", url: "https://www.conseil-constitutionnel.gov.bf", desc: "La juridiction chargée du contrôle de constitutionnalité et de la régularité des élections." },
      { nom: "Service d'information du Gouvernement", sigle: "SIG", url: "https://sig.gov.bf", desc: "La communication institutionnelle de l'État : actualités et productions officielles." },
    ],
  },
  {
    titre: "Démarches & téléservices",
    emoji: "🪪",
    services: [
      { nom: "Service Public BF", url: "https://service-public.gov.bf", desc: "Le portail national unique des services publics en ligne : guides pratiques, procédures dématérialisées et orientation vers les téléservices officiels." },
      { nom: "eSINTAX - impôts en ligne", sigle: "DGI", url: "https://esintax.bf", desc: "La télédéclaration et le télépaiement des impôts (TVA, IS, IR…) de la Direction générale des impôts, par banque ou mobile money." },
      { nom: "Faso Arzeka", url: "https://fasoarzeka.bf", desc: "La plateforme nationale de paiements numériques à l'État (administration, collectivités, institutions). Accessible aussi au *700# et par mobile money." },
    ],
  },
  {
    titre: "Droit & textes officiels",
    emoji: "⚖️",
    services: [
      { nom: "Légiburkina", url: "https://www.legiburkina.gov.bf", desc: "La base de données juridique officielle du Secrétariat général du Gouvernement : lois, décrets, arrêtés et Journal officiel." },
    ],
  },
  {
    titre: "Finances publiques & commande publique",
    emoji: "💰",
    services: [
      { nom: "Ministère de l'Économie et des Finances", url: "https://www.finances.gov.bf", desc: "Budget de l'État, politiques économiques et fiscales, lois de finances." },
      { nom: "Direction générale du Budget", sigle: "DGB", url: "https://www.dgb.gov.bf", desc: "L'élaboration et l'exécution du budget de l'État, documents budgétaires." },
      { nom: "Marchés publics", sigle: "DGCMEF", url: "https://www.dgcmef.gov.bf", desc: "Direction générale du contrôle des marchés publics et des engagements financiers : appels d'offres et attributions." },
    ],
  },
  {
    titre: "Emploi & concours de la fonction publique",
    emoji: "🧑‍💼",
    services: [
      { nom: "Job Burkina Faso", sigle: "jobf", url: "https://jobf.gov.bf", desc: "Le portail des concours directs et professionnels de la fonction publique : calendrier, inscriptions et résultats." },
    ],
  },
  {
    titre: "Statistiques & données ouvertes",
    emoji: "📊",
    services: [
      { nom: "Institut national de la statistique et de la démographie", sigle: "INSD", url: "https://www.insd.bf", desc: "La statistique publique : recensements, enquêtes, indicateurs économiques et sociaux." },
      { nom: "Portail national des données ouvertes", url: "https://data.gov.bf", desc: "Les jeux de données publiques mis à disposition par l'administration en accès libre." },
    ],
  },
  {
    titre: "Contrôle & transparence",
    emoji: "🔍",
    services: [
      { nom: "Autorité supérieure de contrôle d'État et de lutte contre la corruption", sigle: "ASCE-LC", url: "https://www.asce-lc.bf", desc: "L'organe supérieur de contrôle de l'administration et de lutte contre la corruption : rapports et signalements." },
    ],
  },
  {
    titre: "Ministères sectoriels",
    emoji: "🏢",
    services: [
      { nom: "Ministère de la Santé", url: "https://www.sante.gov.bf", desc: "Politiques de santé, structures sanitaires et actualités du secteur." },
      { nom: "Ministère de l'Enseignement supérieur, de la Recherche et de l'Innovation", sigle: "MESRSI", url: "https://www.mesrsi.gov.bf", desc: "Universités, recherche, bourses et orientation de l'enseignement supérieur." },
    ],
  },
  {
    titre: "Protection sociale & santé",
    emoji: "🤝",
    services: [
      { nom: "Caisse nationale de sécurité sociale", sigle: "CNSS", url: "https://cnss.bf", desc: "La sécurité sociale des travailleurs du privé : immatriculation, cotisations et prestations." },
      { nom: "Caisse autonome de retraite des fonctionnaires", sigle: "CARFO", url: "https://www.carfo.bf", desc: "La retraite et les risques professionnels des agents publics : pensions et prestations." },
      { nom: "Caisse nationale d'assurance maladie universelle", sigle: "CNAMU", url: "https://cnamu.bf", desc: "Le régime d'assurance maladie universelle (RAMU) : couverture santé et affiliation." },
    ],
  },
  {
    titre: "Sociétés d'État & services aux usagers",
    emoji: "🏭",
    services: [
      { nom: "Office national de l'eau et de l'assainissement", sigle: "ONEA", url: "https://www.onea.bf", desc: "Le service public de l'eau potable et de l'assainissement en milieu urbain : abonnements et factures." },
      { nom: "Société nationale burkinabè d'hydrocarbures", sigle: "SONABHY", url: "https://www.sonabhy.bf", desc: "L'importation, le stockage et la distribution des hydrocarbures du pays." },
      { nom: "Loterie nationale burkinabè", sigle: "LONAB", url: "https://www.lonab.bf", desc: "L'opérateur public des jeux de hasard et de loterie au Burkina Faso." },
    ],
  },
];

const q = ref("");

function domaine(url) {
  return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
}

const sectionsFiltrees = computed(() => {
  const motif = q.value.trim().toLowerCase();
  if (!motif) return SECTIONS;
  return SECTIONS.map((s) => ({
    ...s,
    services: s.services.filter(
      (x) =>
        x.nom.toLowerCase().includes(motif) ||
        x.desc.toLowerCase().includes(motif) ||
        (x.sigle || "").toLowerCase().includes(motif) ||
        domaine(x.url).includes(motif),
    ),
  })).filter((s) => s.services.length);
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
.note-methode {
  margin-top: 30px; color: var(--text-muted); font-size: 0.86rem;
  border-top: 1px solid var(--border); padding-top: 16px; line-height: 1.55;
}
</style>
