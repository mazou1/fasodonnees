<template>
  <h1>Glossaire</h1>
  <p class="sous-titre">
    Les termes des finances publiques et des institutions burkinabè, expliqués simplement -
    ceux que vous croisez partout sur Faso Données Publiques.
  </p>

  <div class="filtres">
    <input v-model="q" type="search" placeholder="Chercher un terme (ex : LFI, décret, mandat…)" />
  </div>

  <template v-for="section in sectionsFiltrees" :key="section.titre">
    <h2 class="titre-section">{{ section.titre }}</h2>
    <div class="liste">
      <article v-for="t in section.termes" :key="t.terme" class="item">
        <div class="titre">{{ t.terme }}</div>
        <div class="detail">{{ t.definition }}</div>
      </article>
    </div>
  </template>
  <p v-if="!sectionsFiltrees.length" class="vide">Aucun terme ne correspond.</p>
</template>

<script setup>
import { computed, ref } from "vue";

const SECTIONS = [
  {
    titre: "Le budget de l'État",
    termes: [
      { terme: "Loi de finances initiale (LFI)", definition: "La loi votée par l'Assemblée en fin d'année qui autorise les recettes et les dépenses de l'État pour l'année suivante. C'est « le budget » au sens strict." },
      { terme: "Loi de finances rectificative (LFR)", definition: "Une loi votée en cours d'année pour corriger la LFI quand la situation change : nouvelles recettes, dépenses imprévues, chocs économiques." },
      { terme: "Loi de règlement", definition: "La loi qui constate, après coup, ce qui a réellement été encaissé et dépensé pendant l'exercice. C'est la photographie de l'exécution du budget." },
      { terme: "Exercice budgétaire", definition: "L'année civile couverte par un budget (l'exercice 2026 va du 1er janvier au 31 décembre 2026)." },
      { terme: "Recettes fiscales", definition: "L'argent des impôts et taxes : TVA, impôts sur les revenus et les bénéfices, droits de douane… C'est l'essentiel des ressources de l'État (environ 84 % en 2026)." },
      { terme: "Recettes non fiscales", definition: "Les ressources hors impôts : revenus du domaine et des entreprises publiques, droits et frais administratifs, amendes." },
      { terme: "Dons-projets", definition: "Les financements accordés par des partenaires extérieurs (institutions internationales, États) pour des projets précis, sans remboursement." },
      { terme: "Dépenses de personnel", definition: "Les salaires et cotisations des agents publics - le premier poste de dépenses de l'État (plus du tiers du budget)." },
      { terme: "Dépenses en capital (investissement)", definition: "Les dépenses qui construisent l'avenir : routes, écoles, hôpitaux, barrages, équipements. Par opposition aux dépenses courantes de fonctionnement." },
      { terme: "Charge de la dette", definition: "Les intérêts payés chaque année sur l'argent que l'État a emprunté. À distinguer de l'amortissement, qui est le remboursement du capital." },
      { terme: "Transferts courants", definition: "Les sommes versées sans contrepartie directe : bourses, subventions aux établissements publics, appuis sociaux." },
      { terme: "Déficit budgétaire", definition: "L'écart entre les dépenses et les recettes quand les dépenses sont supérieures. Il est financé par l'emprunt." },
      { terme: "Dotation budgétaire", definition: "L'enveloppe allouée à un ministère, une institution ou un secteur dans la loi de finances." },
      { terme: "Pression fiscale", definition: "Le poids des impôts dans l'économie : recettes fiscales rapportées au PIB. Le PND vise 20,6 % en 2030." },
    ],
  },
  {
    titre: "Le Conseil des ministres",
    termes: [
      { terme: "Conseil des ministres", definition: "La réunion hebdomadaire (le jeudi) du gouvernement sous la présidence du Chef de l'État. C'est là que sont adoptés décrets, projets de loi et nominations." },
      { terme: "Compte rendu (CR)", definition: "Le document officiel publié après chaque Conseil, qui relate les délibérations, communications et nominations. La matière première de Faso Données Publiques." },
      { terme: "Engagement financier", definition: "Sur Faso Données Publiques : toute dépense chiffrée décidée en Conseil des ministres - marché public, convention, prêt, subvention ou garantie." },
      { terme: "Marché public", definition: "Un contrat par lequel l'État achète des travaux, des fournitures ou des services à une entreprise, normalement après mise en concurrence." },
      { terme: "Nomination", definition: "La désignation officielle d'une personne à un poste public, prononcée en Conseil des ministres et publiée au compte rendu." },
      { terme: "Matricule (Mle)", definition: "L'identifiant unique d'un agent de la fonction publique (ex. « Mle 39 652 W »). Faso Données Publiques l'utilise pour distinguer les homonymes dans l'annuaire." },
      { terme: "Mandat", definition: "Sur Faso Données Publiques : la période pendant laquelle une personne occupe un poste, reconstituée entre sa nomination et son éventuelle fin de fonction." },
    ],
  },
  {
    titre: "Les textes et institutions",
    termes: [
      { terme: "Loi", definition: "Un texte voté par l'Assemblée législative. Elle prime sur les décrets et arrêtés." },
      { terme: "Décret", definition: "Un texte signé par le Président du Faso ou le Premier ministre, souvent adopté en Conseil des ministres, pour appliquer une loi ou organiser l'État." },
      { terme: "Arrêté", definition: "Une décision prise par un ministre ou une autorité locale, d'une portée plus limitée qu'un décret." },
      { terme: "Ordonnance", definition: "Un texte pris par l'exécutif dans le domaine normalement réservé à la loi, sur habilitation ou en période d'exception." },
      { terme: "Journal officiel (JO)", definition: "La publication officielle où paraissent lois, décrets et arrêtés. Un texte n'est opposable qu'une fois publié au JO." },
      { terme: "Assemblée législative du peuple (ALP)", definition: "L'organe législatif : 71 députés qui votent les lois et contrôlent l'action du gouvernement. Dénomination en vigueur depuis l'adoption de la Charte de la Révolution le 27 mars 2026, qui a remplacé l'Assemblée législative de Transition (ALT)." },
      { terme: "Légiburkina", definition: "La base de données juridique officielle du Secrétariat général du Gouvernement - la source des 4 900 textes de Faso Données Publiques." },
      { terme: "PND R.E.L.A.N.C.E.", definition: "Le Plan national de développement 2026-2030 : 36 191 milliards FCFA sur 5 ans, 4 piliers stratégiques. Voir le dossier dédié." },
    ],
  },
];

const q = ref("");

const sectionsFiltrees = computed(() => {
  const motif = q.value.trim().toLowerCase();
  if (!motif) return SECTIONS;
  return SECTIONS.map((s) => ({
    ...s,
    termes: s.termes.filter(
      (t) => t.terme.toLowerCase().includes(motif) || t.definition.toLowerCase().includes(motif),
    ),
  })).filter((s) => s.termes.length);
});
</script>

<style scoped>
.titre-section { margin-top: 26px; }
</style>
