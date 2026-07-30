<template>
  <!-- immersion totale : l'en-tête, le pied de page et la barre mobile sont
       masqués par App.vue sur cette route ; le retour passe par le bouton
       « ← Faso Données Publiques » du dossier (target _top) -->
  <iframe
    class="cadre-dossier"
    src="/plan-relance/"
    title="Plan de relance - PND R.E.L.A.N.C.E. 2026-2030"
  ></iframe>
</template>

<style scoped>
.cadre-dossier {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100dvh; /* un iframe est un élément remplacé : hauteur explicite obligatoire */
  border: 0;
  background: #0b0e14;
  z-index: 90;
}
</style>
