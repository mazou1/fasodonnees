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
// Comptes officiels de la plateforme. Ils republient les annonces déjà
// présentes sur le site : le lien est donc une porte de sortie assumée, pas un
// bouton de partage - la plateforme ne demande rien au lecteur, elle lui dit où
// la retrouver. Les icônes sont dessinées ici (chemins SVG) plutôt que
// chargées : aucun appel vers un serveur de Meta ou de Telegram depuis une page
// consultée, donc aucun traçage à l'insu du lecteur.
const RESEAUX = [
  {
    nom: "Telegram",
    // « fasodonnees » est le NOM D'UTILISATEUR du canal, seul à faire une URL
    // valide. Son titre affiché est « @faso_donnees », avec un tiret bas : une
    // chaîne saisie à la main qui ressemble à une adresse sans en être une, et
    // qui mène à un canal inexistant si on la recopie.
    url: "https://t.me/fasodonnees",
    titre: "Canal Telegram : les annonces officielles, dès leur publication",
    icone: "M9.8 15.6 9.6 19.4c.4 0 .6-.2.8-.4l1.9-1.8 3.9 2.9c.7.4 1.2.2 1.4-.7l2.6-12.1c.2-1-.4-1.4-1.1-1.2L2.6 10.4c-1 .4-1 .9-.2 1.2l4.4 1.4 10.2-6.4c.5-.3.9-.1.6.2z",
  },
  {
    nom: "Facebook",
    url: "https://www.facebook.com/1309210855614853",
    titre: "Page Facebook : le fil complet, actualités des médias comprises",
    icone: "M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5h1.65V3.6c-.3 0-1.3-.1-2.4-.1-2.4 0-4.05 1.45-4.05 4.15V9.9H7.5V13h2.75v8z",
  },
];

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
    // - marchés passés, ouvrages livrés.
    libelle: "Budget & exécution",
    enfants: [
      ["/finances", "Budget de l'État"],
      ["/marches", "Marchés publics"],
      ["/infrastructures", "Infrastructures"],
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
      <span class="suivre">
        <span>Suivre&nbsp;:</span>
        <a v-for="reseau in RESEAUX" :key="reseau.nom" :href="reseau.url"
           target="_blank" rel="noopener me" :title="reseau.titre">
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path :d="reseau.icone" /></svg>
          {{ reseau.nom }}
        </a>
      </span>
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
      <div class="titre-groupe">Suivre la plateforme</div>
      <a v-for="reseau in RESEAUX" :key="reseau.nom" :href="reseau.url"
         target="_blank" rel="noopener me">{{ reseau.nom }}</a>
    </nav>
  </div>
</template>
