<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

const router = useRouter();
const route = useRoute();
// routes en immersion totale : aucun habillage du site (dossiers plein écran)
const immersif = computed(() => route.name === "dossier-plan-relance");
const q = ref("");
const menuOuvert = ref(false);
const theme = ref(document.documentElement.dataset.theme || "");

function chercher() {
  if (q.value.trim().length >= 2) {
    router.push({ path: "/recherche", query: { q: q.value.trim() } });
    q.value = "";
  }
}

function basculerTheme() {
  const sombreSysteme = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const effectif = theme.value || (sombreSysteme ? "dark" : "light");
  theme.value = effectif === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = theme.value;
  localStorage.setItem("theme", theme.value);
}

// fermer la feuille de menu ET le déroulant à chaque navigation
watch(() => route.fullPath, () => {
  menuOuvert.value = false;
  groupeOuvert.value = null;
});

// Navigation à deux niveaux : 14 rubriques à plat débordaient sur trois lignes
// dans un en-tête collant, soit un tiers de l'écran occupé en permanence sur un
// portable. Les groupes suivent des familles de sens, pas des commodités de
// rangement - « Budget & exécution » raconte d'ailleurs la chaîne budget →
// marché → ouvrage livré, celle-là même que suivent les dossiers.
const NAVIGATION = [
  { chemin: "/", libelle: "Tableau de bord" },
  { chemin: "/actualites", libelle: "Actualités" },
  {
    libelle: "Institutions",
    enfants: [
      ["/gouvernement", "Gouvernement"],
      ["/assemblee", "Assemblée"],
      ["/annuaire", "Annuaire de l'État"],
    ],
  },
  {
    libelle: "Décisions & textes",
    enfants: [
      ["/conseils", "Conseil des ministres"],
      ["/textes", "Lois & décrets"],
      ["/controle", "Justice & contrôle"],
    ],
  },
  {
    // « exécution » au sens budgétaire : ce qui advient du budget une fois voté
    // - marchés passés, ouvrages livrés, écart entre l'annonce et la livraison.
    libelle: "Budget & exécution",
    enfants: [
      ["/finances", "Budget de l'État"],
      ["/marches", "Marchés publics"],
      ["/infrastructures", "Infrastructures"],
      ["/suivi", "Suivi des annonces"],
    ],
  },
  {
    libelle: "Ressources",
    enfants: [
      ["/documents", "Documents"],
      ["/dossiers", "Dossiers"],
      ["/services-numeriques", "Services en ligne"],
    ],
  },
];

// liste à plat : la feuille mobile et les tests s'appuient dessus
const LIENS = NAVIGATION.flatMap((e) =>
  e.enfants ? e.enfants : [[e.chemin, e.libelle]]
);

const groupeOuvert = ref(null);

/** Un groupe s'affiche actif quand la page courante est l'un de ses enfants. */
function groupeActif(entree) {
  return !!entree.enfants?.some(([chemin]) => route.path.startsWith(chemin));
}

function basculerGroupe(libelle) {
  groupeOuvert.value = groupeOuvert.value === libelle ? null : libelle;
}

// Fermeture au clic extérieur et à la touche Échap - un menu déroulant qui
// reste ouvert quand on clique ailleurs donne l'impression d'une page figée.
function fermerGroupe(evenement) {
  if (!evenement || !evenement.target.closest?.(".nav-groupe")) {
    groupeOuvert.value = null;
  }
}
function surEchap(e) {
  if (e.key === "Escape") fermerGroupe();
}
onMounted(() => {
  document.addEventListener("click", fermerGroupe);
  document.addEventListener("keydown", surEchap);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", fermerGroupe);
  document.removeEventListener("keydown", surEchap);
});
</script>

<template>
  <header v-if="!immersif" class="entete">
    <div class="entete-inner">
      <router-link to="/" class="marque">Faso <span>Données Publiques</span></router-link>
      <nav class="nav">
        <template v-for="entree in NAVIGATION" :key="entree.libelle">
          <router-link v-if="entree.chemin" :to="entree.chemin">{{ entree.libelle }}</router-link>
          <div v-else class="nav-groupe">
            <button
              :class="{ actif: groupeActif(entree), ouvert: groupeOuvert === entree.libelle }"
              :aria-expanded="groupeOuvert === entree.libelle"
              aria-haspopup="true"
              @click.stop="basculerGroupe(entree.libelle)"
            >
              {{ entree.libelle }}<span class="chevron" aria-hidden="true">▾</span>
            </button>
            <div v-if="groupeOuvert === entree.libelle" class="sous-menu">
              <router-link v-for="[chemin, libelle] in entree.enfants" :key="chemin" :to="chemin">
                {{ libelle }}
              </router-link>
            </div>
          </div>
        </template>
      </nav>
      <input
        v-model="q"
        class="recherche-globale"
        type="search"
        placeholder="Rechercher…"
        aria-label="Recherche globale"
        @keyup.enter="chercher"
      />
      <button
        class="btn-theme"
        :title="theme === 'dark' ? 'Passer en clair' : 'Passer en sombre'"
        aria-label="Basculer le thème clair/sombre"
        @click="basculerTheme"
      >
        {{ theme === "dark" ? "☀️" : "🌙" }}
      </button>
    </div>
  </header>

  <main>
    <div class="conteneur">
      <router-view v-slot="{ Component }">
        <!-- la clé inclut le thème : les graphiques relisent leurs couleurs au
             remontage ; le wrapper mono-racine porte l'animation d'entrée
             (les vues sont multi-racines, incompatibles avec <transition>) -->
        <div :key="route.fullPath + theme" class="vue-page">
          <component :is="Component" />
        </div>
      </router-view>
    </div>
  </main>

  <footer v-if="!immersif" class="pied">
    <div class="conteneur">
      <span>Plateforme citoyenne indépendante - données issues des sources officielles, chaque entrée liée à son document d'origine.</span>
      <router-link to="/glossaire">Glossaire</router-link>
      <router-link to="/a-propos">À propos & méthodologie</router-link>
      <a href="/api/docs" target="_blank" rel="noopener">API ouverte</a>
      <a href="/api/rss/conseils.xml" target="_blank" rel="noopener" title="Suivre les conseils des ministres">RSS ⓘ</a>
    </div>
  </footer>

  <nav v-if="!immersif" class="nav-mobile">
    <router-link to="/"><span class="icone">🏠</span><span>Accueil</span></router-link>
    <router-link to="/actualites"><span class="icone">📰</span><span>Actus</span></router-link>
    <router-link to="/conseils"><span class="icone">🏛️</span><span>Conseil</span></router-link>
    <router-link to="/finances"><span class="icone">💰</span><span>Finances</span></router-link>
    <button aria-label="Ouvrir le menu" @click="menuOuvert = !menuOuvert">
      <span class="icone">☰</span><span>Menu</span>
    </button>
  </nav>

  <div v-if="menuOuvert" class="voile-menu" @click="menuOuvert = false">
    <nav class="feuille-menu" @click.stop>
      <template v-for="entree in NAVIGATION" :key="entree.libelle">
        <router-link v-if="entree.chemin" :to="entree.chemin">{{ entree.libelle }}</router-link>
        <template v-else>
          <div class="titre-groupe">{{ entree.libelle }}</div>
          <router-link v-for="[chemin, libelle] in entree.enfants" :key="chemin" :to="chemin">
            {{ libelle }}
          </router-link>
        </template>
      </template>
      <div class="titre-groupe">Aller plus loin</div>
      <router-link to="/dossiers/plan-relance">Plan de relance</router-link>
      <router-link to="/glossaire">Glossaire</router-link>
    </nav>
  </div>
</template>
