<template>
  <h1>Dossiers</h1>
  <p class="sous-titre">
    Les grands sujets de la vie publique burkinabè, rassemblés : données, documents officiels
    et visualisations sur une même thématique.
  </p>

  <div class="grille-dossiers">
    <component
      :is="d.externe ? 'a' : 'router-link'"
      v-for="d in DOSSIERS"
      :key="d.titre"
      v-bind="d.externe ? { href: d.lien } : { to: d.lien }"
      class="carte-dossier"
    >
      <div class="bandeau" :style="{ '--teinte': d.couleur }">
        <div class="sur-titre">{{ d.categorie }}</div>
        <div class="grand-titre">{{ d.titre }}</div>
      </div>
      <div class="corps">
        <p class="description">{{ d.description }}</p>
        <div class="etiquettes">
          <span v-for="t in d.etiquettes" :key="t" class="badge">{{ t }}</span>
        </div>
      </div>
    </component>
  </div>
</template>

<script setup>
const DOSSIERS = [
  {
    categorie: "Développement · 2026-2030",
    titre: "Plan de relance - PND R.E.L.A.N.C.E.",
    description:
      "Le Plan national de développement 2026-2030 décortiqué : 36 191 milliards FCFA, "
      + "4 piliers, trajectoire de croissance, pauvreté par région, financement et risques - "
      + "un dossier interactif complet.",
    etiquettes: ["36 191 Mds FCFA", "4 piliers", "Interactif"],
    lien: "/dossiers/plan-relance",
    externe: false,
    couleur: "#b8860b",
  },
  {
    categorie: "Finances publiques · 2026",
    titre: "Le budget de l'État",
    description:
      "D'où vient l'argent public et où va-t-il : recettes par catégorie, dépenses par nature, "
      + "allocations sectorielles et engagements du Conseil des ministres, sourcés depuis les "
      + "lois de finances officielles.",
    etiquettes: ["3 918 Mds de dépenses", "Répartitions", "Sources officielles"],
    lien: "/finances",
    externe: false,
    couleur: "#0a6b3c",
  },
  {
    categorie: "Institutions · janvier 2026",
    titre: "Le gouvernement remanié",
    description:
      "La composition officielle issue du remaniement de janvier 2026 : 25 membres, "
      + "nouveaux intitulés ministériels, portraits officiels de la Présidence du Faso.",
    etiquettes: ["25 membres", "Trombinoscope", "Présidence"],
    lien: "/gouvernement",
    externe: false,
    couleur: "#9c4a1f",
  },
];
</script>

<style scoped>
.grille-dossiers { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.carte-dossier {
  display: block; border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
  background: var(--surface-1); text-decoration: none; color: inherit;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.carte-dossier:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08); }
.bandeau {
  padding: 22px 18px; color: #fff; min-height: 120px;
  display: flex; flex-direction: column; justify-content: flex-end; gap: 6px;
  background:
    radial-gradient(120% 160% at 100% 0%, rgba(255, 255, 255, 0.18), transparent 55%),
    linear-gradient(135deg, color-mix(in srgb, var(--teinte) 80%, #000), var(--teinte));
  border-bottom: 3px solid;
  border-image: linear-gradient(90deg, #ce1126 50%, #009e49 50%) 1;
}
.sur-titre { font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.85; }
.grand-titre { font-size: 1.25rem; font-weight: 800; line-height: 1.2; }
.corps { padding: 14px 18px 16px; }
.description { color: var(--text-secondary); font-size: 0.92rem; line-height: 1.55; margin: 0 0 12px; }
.etiquettes { display: flex; gap: 6px; flex-wrap: wrap; }
</style>
