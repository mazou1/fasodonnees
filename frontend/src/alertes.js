// Liens vers le bot d'alertes Telegram. Le nom du bot vient de l'API, lu une
// seule fois ; tant qu'il n'est pas connu (ou si les alertes sont coupées), les
// boutons ne s'affichent pas plutôt que de mener nulle part.
import { ref } from "vue";
import { apiGet } from "./api";

export const botAlertes = ref(null);
let demande = null;

export function chargerAlertes() {
  if (!demande) {
    demande = apiGet("/alertes")
      .then((r) => {
        botAlertes.value = r.actif ? r.bot : null;
      })
      .catch(() => {
        botAlertes.value = null;
      });
  }
  return demande;
}

function lien(charge) {
  return botAlertes.value ? `https://t.me/${botAlertes.value}?start=${charge}` : null;
}

export const lienAlertePersonne = (id) => lien(`p${id}`);
export const lienAlerteInstitution = (id) => lien(`s${id}`);

/** Telegram n'accepte que 64 caractères [A-Za-z0-9_-] : le mot-clé voyage en
    base64 « URL ». Trop long, il renvoie null et la page explique la commande. */
export function lienAlerteMot(mot) {
  const octets = new TextEncoder().encode(mot.trim());
  let binaire = "";
  octets.forEach((o) => (binaire += String.fromCharCode(o)));
  const charge = "m" + btoa(binaire).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return charge.length <= 64 ? lien(charge) : null;
}
