<template>
  <h1>Alertes</h1>
  <p class="sous-titre">
    Soyez prévenu sur Telegram quand une nomination, une décision du Conseil des ministres,
    un texte de loi ou un vote de l'Assemblée correspond à ce qui vous intéresse.
  </p>

  <div v-if="botAlertes" class="carte bloc">
    <h2>Suivre un mot-clé ou un nom</h2>
    <form class="saisie" @submit.prevent="ouvrir">
      <input v-model="mot" type="search" placeholder="ex : budget, mines, Ouédraogo, université…" maxlength="60" />
      <a v-if="lienMot" class="bouton" :href="lienMot" target="_blank" rel="noopener">Recevoir l'alerte sur Telegram →</a>
      <span v-else class="bouton inactif">Recevoir l'alerte sur Telegram →</span>
    </form>
    <p v-if="mot.trim().length >= 3 && !lienMot" class="aide">
      Ce mot-clé est trop long pour un lien : ouvrez
      <a :href="`https://t.me/${botAlertes}`" target="_blank" rel="noopener">@{{ botAlertes }}</a>
      et envoyez <code>/suivre {{ mot.trim() }}</code>.
    </p>
    <p class="aide">
      Telegram s'ouvre sur notre bot <a :href="`https://t.me/${botAlertes}`" target="_blank" rel="noopener">@{{ botAlertes }}</a> :
      touchez « Démarrer » et l'alerte est enregistrée. Aucun compte à créer ici.
    </p>
  </div>
  <p v-else-if="charge" class="vide">Les alertes ne sont pas disponibles pour le moment.</p>

  <div class="carte bloc">
    <h2>Suivre une personne ou une institution</h2>
    <p>
      Ouvrez sa fiche dans l'<router-link to="/annuaire">annuaire de l'État</router-link> et touchez
      « 🔔 Recevoir une alerte ». Vous serez prévenu de chaque nomination ou fin de fonction qui la concerne.
    </p>
  </div>

  <div class="carte bloc">
    <h2>Comment ça marche</h2>
    <ul>
      <li>Une alerte part seulement pour une information <strong>validée</strong> et publiée sur ce site.</li>
      <li>Vous recevez au plus <strong>un message par alerte et par heure</strong>, qui regroupe toutes les nouveautés.</li>
      <li>Un mot-clé est cherché en mots entiers, sans tenir compte des accents ni des majuscules.</li>
      <li>Dans Telegram : <code>/liste</code> pour voir vos alertes, <code>/arreter 1</code> pour en retirer une.</li>
    </ul>
    <p class="aide">
      Vos données : nous ne conservons que l'identifiant de votre conversation Telegram et la liste de
      vos alertes. <code>/arreter tout</code> les efface immédiatement. Pour suivre toutes les annonces
      officielles sans alerte personnelle, le <a href="https://t.me/fasodonnees" target="_blank" rel="noopener">canal Telegram</a> reste ouvert.
    </p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { botAlertes, chargerAlertes, lienAlerteMot } from "../alertes";

const mot = ref("");
const charge = ref(false);
const lienMot = computed(() => (mot.value.trim().length >= 3 ? lienAlerteMot(mot.value) : null));

function ouvrir() {
  if (lienMot.value) window.open(lienMot.value, "_blank", "noopener");
}

onMounted(async () => {
  await chargerAlertes();
  charge.value = true;
});
</script>

<style scoped>
.bloc { max-width: 780px; margin-bottom: 14px; }
.bloc h2 { margin-top: 0; }
.saisie { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.saisie input { flex: 1; min-width: 220px; }
.bouton {
  display: inline-block; padding: 9px 16px; border-radius: 8px; font-weight: 600;
  background: var(--accent); color: #fff; text-decoration: none; white-space: nowrap;
}
.bouton:hover { filter: brightness(1.06); text-decoration: none; }
.bouton.inactif { opacity: 0.45; cursor: default; }
.aide { color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0; }
code { background: var(--surface-2, rgba(127, 127, 127, 0.15)); padding: 1px 5px; border-radius: 4px; }
</style>
