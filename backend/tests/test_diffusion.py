"""Diffusion automatique sur les réseaux sociaux.

Ce module poste sur des pages publiques sans relecture humaine : ce qui en sort
n'est plus rattrapable. Les tests figent donc les garanties qui rendent cette
automatisation acceptable - pas de doublon, pas de déversement d'archives, pas
de post tronqué en plein titre, pas d'acharnement sur une API qui refuse.
"""

import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.diffusion import messages, run
from app.diffusion.messages import (
    Item,
    composer,
    lisible,
    longueur_percue,
    nettoyer_resume,
    tronquer,
)
from app.diffusion.reseaux import (
    ErreurReseau,
    MasqueSecrets,
    Telegram,
    X,
    chaine_de_signature,
    entete_oauth1,
    reseaux_incomplets,
)
from app.diffusion.selection import (
    MAX_TENTATIVES,
    cles_bloquees,
    items_a_publier,
    ordonner,
    plancher,
    racines,
)
from app.models import Base, Decision, Document, Publication, Source

_TABLES = (Source, Document, Decision, Publication)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _TABLES])
    with Session(engine) as session:
        yield session


def item(cle="conseil-1", genre="conseil", titre="Compte rendu du 21 août 2026", **kw):
    kw.setdefault("lien", "https://fasodonnees.org/conseils/1")
    return Item(cle=cle, genre=genre, titre=titre, **kw)


# --- le texte des posts ---------------------------------------------------

def test_un_post_x_ne_depasse_jamais_la_limite_du_reseau():
    """Un post trop long n'est pas raccourci par X : il est REFUSÉ. La limite
    doit tenir sur le pire cas - titre à rallonge et lien interminable."""
    long_lien = "https://fasodonnees.org/documents/" + "9" * 200
    message = composer(
        item(genre="actualite", titre="Titre de dépêche " * 40, lien=long_lien,
             contexte="Sidwaya", resume="Un résumé " * 80),
        "x",
    )
    assert longueur_percue(message, long_lien, "x") <= messages.LIMITES["x"]


def test_le_lien_survit_a_la_troncature():
    """Un post coupé reste utile si le lien tient ; l'inverse ne l'est pas."""
    lien = "https://fasodonnees.org/conseils/1"
    message = composer(item(titre="Un titre démesurément long " * 30, lien=lien), "x")
    assert message.endswith(lien)


def test_la_source_de_presse_est_creditee_dans_le_post():
    """Reprendre le titre d'un média sans le nommer dans le post lui-même
    ferait passer son travail pour celui de la plateforme."""
    message = composer(item(genre="actualite", cle="actu-9", contexte="Sidwaya"), "telegram")
    assert "via Sidwaya" in message


def test_le_resume_est_repris_la_ou_la_place_le_permet_pas_sur_x():
    resume = "Le Conseil a adopté un décret portant organisation du ministère."
    assert resume in composer(item(resume=resume), "telegram")
    assert resume not in composer(item(resume=resume), "x")


def test_un_bloc_secondaire_qui_ne_tient_pas_est_abandonne_pas_coupe():
    """Un post qui se termine par « Ministère de la… » se lit comme une panne
    d'affichage ; le même sans cette ligne reste une information complète."""
    message = composer(
        item(genre="decision", cle="decision-1", titre="Adoption d'un décret " * 15,
             contexte="Ministère de la Santé"),
        "x",
    )

    assert "Ministère" not in message


def test_le_contexte_est_garde_quand_il_tient():
    message = composer(
        item(genre="decision", cle="decision-2", titre="Adoption d'un décret",
             contexte="Ministère de la Santé"),
        "x",
    )

    assert "Ministère de la Santé" in message


def test_la_troncature_coupe_sur_un_mot_entier():
    """« …le ministre Ouédra… » se lit comme une panne, pas comme un résumé."""
    coupe = tronquer("Le ministre Ouédraogo a présenté un rapport au Conseil", 25)
    assert coupe.endswith("…")
    assert len(coupe) <= 25
    assert "Ouédra…" not in coupe


def test_un_libelle_sans_espace_est_coupe_net_plutot_que_vide():
    coupe = tronquer("A" * 60, 20)
    assert 10 < len(coupe) <= 20


# --- la sélection ---------------------------------------------------------

def test_un_item_deja_publie_ne_ressort_pas(db):
    """La garantie centrale : un worker relancé republierait sinon le compte
    rendu du Conseil des ministres à chaque cycle."""
    db.add(Publication(reseau="telegram", cle="conseil-1", statut="publie", tentatives=1))
    db.commit()

    assert cles_bloquees(db, "telegram") == {"conseil-1"}


def test_un_echec_recent_reste_a_reessayer(db):
    """Une coupure réseau ne doit pas faire perdre définitivement un post."""
    db.add(Publication(reseau="x", cle="conseil-1", statut="echec", tentatives=1))
    db.commit()

    assert cles_bloquees(db, "x") == set()


def test_apres_trop_dechecs_litem_est_abandonne(db):
    """Trois refus d'affilée signalent un jeton expiré, pas un incident :
    insister épuiserait le quota mensuel de X sans rien publier."""
    db.add(Publication(reseau="x", cle="conseil-1", statut="echec", tentatives=MAX_TENTATIVES))
    db.commit()

    assert cles_bloquees(db, "x") == {"conseil-1"}


def test_le_journal_est_cloisonne_par_reseau(db):
    """Publier sur Telegram ne doit pas empêcher de publier sur Facebook."""
    db.add(Publication(reseau="telegram", cle="conseil-1", statut="publie", tentatives=1))
    db.commit()

    assert cles_bloquees(db, "facebook") == set()


def test_le_contenu_propre_passe_avant_les_depeches():
    """Sans priorité, le volume des actualités mangerait tout le quota et le
    compte rendu du Conseil des ministres ne sortirait jamais."""
    vieux_conseil = item(cle="conseil-1", date=date(2026, 8, 1))
    actu_recente = item(cle="actu-1", genre="actualite", date=date(2026, 8, 20))

    retenus = ordonner([actu_recente, vieux_conseil], limite=1)

    assert [i.cle for i in retenus] == ["conseil-1"]


def test_a_genre_egal_le_fil_se_lit_dans_lordre_chronologique():
    a = item(cle="actu-1", genre="actualite", date=date(2026, 8, 18))
    b = item(cle="actu-2", genre="actualite", date=date(2026, 8, 20))

    assert [i.cle for i in ordonner([b, a], limite=2)] == ["actu-1", "actu-2"]


def test_la_fenetre_de_fraicheur_borne_lamorcage():
    """Activer la diffusion sur une base de 160 comptes rendus et 5 000
    documents ne doit pas déverser des années d'archives sur la page."""
    assert plancher(2, aujourdhui=date(2026, 8, 26)) == date(2026, 8, 24)


# --- le quota et le journal ----------------------------------------------

def test_le_quota_glisse_sur_24h(db):
    """Un compteur remis à zéro à minuit autoriserait deux fois le quota autour
    de minuit - et ferait dépasser le plafond mensuel de X."""
    maintenant = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    db.add_all(
        [
            Publication(reseau="x", cle="a", statut="publie",
                        date_envoi=maintenant - timedelta(hours=3)),
            Publication(reseau="x", cle="b", statut="publie",
                        date_envoi=maintenant - timedelta(hours=30)),
        ]
    )
    db.commit()

    assert run.quota_restant(db, "x", 12, maintenant=maintenant) == 11


def test_un_echec_ne_consomme_pas_le_quota(db):
    maintenant = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    db.add(Publication(reseau="x", cle="a", statut="echec", date_envoi=maintenant))
    db.commit()

    assert run.quota_restant(db, "x", 12, maintenant=maintenant) == 12


def test_le_texte_reellement_envoye_est_conserve(db):
    """Quand un post pose question, il faut pouvoir dire ce que la plateforme a
    publié sans dépendre de ce que le réseau veut bien encore afficher."""
    publication = run.journaliser(db, "telegram", item(), "Le message posté", post_id="42")

    assert (publication.statut, publication.post_id, publication.tentatives) == ("publie", "42", 1)
    assert publication.message == "Le message posté"


def test_une_nouvelle_tentative_met_a_jour_la_meme_ligne(db):
    """Une ligne par (réseau, item) : c'est la contrainte d'unicité en base qui
    porte la garantie anti-doublon, elle ne doit pas être contournée ici."""
    run.journaliser(db, "x", item(), "msg", erreur="HTTP 503")
    publication = run.journaliser(db, "x", item(), "msg", post_id="7")

    assert publication.tentatives == 2
    assert publication.statut == "publie"
    assert publication.erreur is None
    assert db.query(Publication).count() == 1


# --- l'orchestration ------------------------------------------------------

class ReseauFactice:
    nom = "telegram"
    quota_jour = 10

    def __init__(self, echoue_a=None):
        self.envoyes = []
        self.echoue_a = echoue_a

    def publier(self, message, lien):
        if self.echoue_a is not None and len(self.envoyes) == self.echoue_a:
            raise ErreurReseau("HTTP 401 : jeton expiré")
        self.envoyes.append((message, lien))
        return f"post-{len(self.envoyes)}"


@pytest.fixture
def sans_pause(monkeypatch):
    monkeypatch.setattr(run.settings, "diffusion_pause_s", 0)


def _publie_trois(db, monkeypatch, reseau):
    items = [item(cle=f"conseil-{n}", date=date(2026, 8, 20 + n)) for n in (1, 2, 3)]
    monkeypatch.setattr(run, "items_a_publier", lambda *a, **k: items)
    return run.diffuser_reseau(db, reseau)


def test_un_refus_arrete_le_reseau_sans_epuiser_la_file(db, monkeypatch, sans_pause):
    """Un jeton expiré refusera aussi les suivants : insister brûlerait une
    tentative sur chaque item en attente, et le quota mensuel avec."""
    reseau = ReseauFactice(echoue_a=1)

    bilan = _publie_trois(db, monkeypatch, reseau)

    assert bilan == {"quota": 10, "candidats": 3, "publies": 1, "echecs": 1}
    assert len(reseau.envoyes) == 1
    restants = {p.cle: p.statut for p in db.query(Publication).all()}
    assert restants == {"conseil-1": "publie", "conseil-2": "echec"}


def test_le_cycle_nominal_publie_et_journalise_tout(db, monkeypatch, sans_pause):
    reseau = ReseauFactice()

    bilan = _publie_trois(db, monkeypatch, reseau)

    assert bilan["publies"] == 3 and bilan["echecs"] == 0
    assert {p.statut for p in db.query(Publication).all()} == {"publie"}


def test_rien_ne_part_tant_que_le_coupe_circuit_est_ouvert(db, monkeypatch):
    """Une base restaurée ou un worker lancé par erreur sur un poste de
    développement ne doit pas poster sur une page publique."""
    monkeypatch.setattr(run.settings, "diffusion_active", False)
    monkeypatch.setattr(
        run, "reseaux_configures", lambda noms=None: pytest.fail("réseau contacté")
    )

    assert run.diffuser(db) == {}


# --- signature OAuth 1.0a (X) --------------------------------------------

def test_la_chaine_de_signature_suit_la_specification():
    """Assemblage vérifié à la main : c'est là que se logent les erreurs de
    signature, pas dans le HMAC lui-même. Le « / » de l'URL doit être encodé,
    les paramètres triés, le tout ré-encodé une seconde fois."""
    chaine = chaine_de_signature(
        "post", "https://api.x.com/2/tweets", {"b": "deux", "a": "un espace"}
    )

    assert chaine == (
        "POST&https%3A%2F%2Fapi.x.com%2F2%2Ftweets&a%3Dun%2520espace%26b%3Ddeux"
    )


def test_lentete_oauth_porte_tous_les_champs_obligatoires():
    entete = entete_oauth1(
        "POST", "https://api.x.com/2/tweets",
        cle_api="cle", secret_api="secret", jeton="jeton", secret_jeton="secret2",
        nonce="abc", horodatage=1756200000,
    )

    for champ in ("oauth_consumer_key", "oauth_nonce", "oauth_signature",
                  "oauth_signature_method", "oauth_timestamp", "oauth_token", "oauth_version"):
        assert f'{champ}="' in entete
    assert entete.startswith("OAuth ")


def test_la_signature_depend_du_secret():
    """Garde-fou contre une signature calculée sur une clé vide, qui produirait
    des entêtes bien formées et systématiquement rejetées."""
    commun = dict(cle_api="cle", jeton="jeton", nonce="abc", horodatage=1756200000)
    une = entete_oauth1("POST", "https://api.x.com/2/tweets",
                        secret_api="secret", secret_jeton="a", **commun)
    autre = entete_oauth1("POST", "https://api.x.com/2/tweets",
                          secret_api="secret", secret_jeton="b", **commun)

    assert une != autre


# --- réécritures de la source --------------------------------------------
# Le gouvernement republie ses pages après coup : un même compte rendu existe
# en base en plusieurs versions (cf. app/versions.py). C'est le piège principal
# de la diffusion, et la contrainte d'unicité du journal ne l'attrape pas -
# chaque version porte un `document.id` différent.

URL_CM = "https://gouvernement.gov.bf/conseil-des-ministres/cm-n22/"


def _document(doc_id, *, jour):
    """Une version du compte rendu du 2 juillet, collectée le `jour` du mois."""
    return Document(
        id=doc_id,
        source_id=1,
        url=URL_CM,
        titre="CONSEIL DES MINISTRES N°22 DU 02 JUILLET 2026",
        type_doc="cr_conseil",
        date_publication=date(2026, 7, 2),
        date_collecte=datetime(2026, 7, jour, 10, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def db_versions(db):
    """Le compte rendu du 2 juillet, réécrit deux fois par la source."""
    db.add(
        Source(id=1, slug="gouv", nom="Gouvernement",
               url_base="https://gouvernement.gov.bf", type="institutionnel")
    )
    for doc_id, jour in ((155, 10), (5721, 20), (11473, 31)):
        db.add(_document(doc_id, jour=jour))
    db.commit()
    return db


def _decisions(db, aujourdhui=date(2026, 7, 3)):
    return items_a_publier(
        db, "telegram", limite=10, fraicheur_jours=2,
        site_url="https://fasodonnees.org", genres=("decision",), aujourdhui=aujourdhui,
    )


def _conseils(db, aujourdhui=date(2026, 7, 3)):
    return items_a_publier(
        db, "telegram", limite=10, fraicheur_jours=2,
        site_url="https://fasodonnees.org", genres=("conseil",), aujourdhui=aujourdhui,
    )


def test_un_conseil_reecrit_trois_fois_ne_donne_quun_seul_post(db_versions):
    """Sans filtre sur la version de référence, la page publierait quatre fois
    le compte rendu du 2 juillet - une fois par version en base."""
    items = _conseils(db_versions)

    assert [i.cle for i in items] == ["conseil-155"]


def test_le_post_pointe_vers_la_version_a_jour(db_versions):
    """La clé suit la première version, le lien la dernière : c'est la page
    corrigée qu'un lecteur doit ouvrir."""
    assert _conseils(db_versions)[0].lien == "https://fasodonnees.org/conseils/11473"


def test_une_reecriture_survenue_apres_le_post_ne_republie_pas(db_versions):
    """Le cas qui casserait la page : le conseil est publié jeudi soir, le
    gouvernement retouche la page vendredi, une nouvelle version est collectée.
    Elle porte un autre `document.id` - et la clé, elle, ne bouge pas."""
    db_versions.add(
        Publication(reseau="telegram", cle="conseil-155", statut="publie", tentatives=1)
    )
    db_versions.commit()

    assert _conseils(db_versions) == []


def test_la_cle_dune_decision_survit_a_la_consolidation(db):
    """Après une réécriture, la consolidation rattache la décision à la nouvelle
    version de référence, sous un NOUVEL identifiant de ligne (cf.
    app/versions.py). La décision est pourtant la même : la clé se prend donc
    sur le contenu, pas sur `decision.id`."""
    db.add(
        Source(id=1, slug="gouv", nom="Gouvernement",
               url_base="https://gouvernement.gov.bf", type="institutionnel")
    )
    db.add(_document(155, jour=10))
    commun = dict(ministere="AU TITRE DU MINISTERE DE LA SANTE", type="adoption_decret",
                  objet="Adoption d'un décret portant organisation du ministère",
                  statut_validation="valide")
    db.add(Decision(id=10, document_id=155, **commun))
    db.commit()
    avant = _decisions(db)

    # le gouvernement retouche la page : nouvelle version, la consolidation y
    # déplace la décision et supprime la ligne précédente
    db.add(_document(11473, jour=31))
    db.query(Decision).delete()
    db.add(Decision(id=99, document_id=11473, **commun))
    db.commit()

    assert [i.cle for i in avant] == [i.cle for i in _decisions(db)] != []


def test_seules_les_decisions_validees_sortent(db_versions):
    """Une extraction LLM non relue publiée sur une page publique serait bien
    plus difficile à rattraper qu'une ligne fausse dans le back-office."""
    db_versions.add(
        Decision(id=11, document_id=11473, ministere=None, type="rapport",
                 objet="Décision encore à relire", statut_validation="a_valider")
    )
    db_versions.commit()

    assert _decisions(db_versions) == []


def test_les_archives_ne_sont_pas_deversees_a_lactivation(db_versions):
    """Activer la diffusion sur une base de 160 comptes rendus ne doit poster
    que ce qui vient de sortir."""
    assert _conseils(db_versions, aujourdhui=date(2026, 8, 26)) == []


# --- mise en route --------------------------------------------------------

def test_un_reseau_a_moitie_configure_dit_ce_qui_manque(monkeypatch):
    """Le cas normal pendant la mise en route : le jeton du bot est posé, le
    canal pas encore. L'ignorer en silence ferait chercher la panne ailleurs."""
    monkeypatch.setattr(run.settings, "telegram_bot_token", "123:AA")
    monkeypatch.setattr(run.settings, "telegram_chat_id", "")

    telegram = Telegram()
    assert telegram.est_configure() is False
    assert telegram.manquants() == ["FASO_TELEGRAM_CHAT_ID"]
    assert [r.nom for r in reseaux_incomplets()] == ["telegram"]


def test_un_reseau_dont_rien_nest_renseigne_nest_pas_dit_incomplet(monkeypatch):
    """Il n'est pas en panne, il n'est simplement pas encore ouvert : le
    signaler noierait le vrai manque."""
    for champ in ("x_api_key", "x_api_secret", "x_access_token", "x_access_secret"):
        monkeypatch.setattr(run.settings, champ, "")

    assert X().manquants() == [
        "FASO_X_API_KEY", "FASO_X_API_SECRET",
        "FASO_X_ACCESS_TOKEN", "FASO_X_ACCESS_SECRET",
    ]
    assert reseaux_incomplets(("x",)) == []


def test_un_reseau_complet_est_utilisable(monkeypatch):
    monkeypatch.setattr(run.settings, "telegram_bot_token", "123:AA")
    monkeypatch.setattr(run.settings, "telegram_chat_id", "@faso_donnees")

    assert Telegram().est_configure() is True
    assert reseaux_incomplets(("telegram",)) == []


# --- le jeton ne doit pas fuir dans les journaux -------------------------

def test_le_jeton_telegram_est_masque_dans_les_journaux():
    """Telegram fait voyager le jeton dans le CHEMIN de l'URL, et httpx
    journalise chaque requête. Sans masque, il part en clair dans les logs du
    worker à chaque publication - et quiconque l'a contrôle le bot."""
    import logging

    filtre = MasqueSecrets("123456:AA-secret")
    trace = logging.LogRecord(
        "httpx", logging.INFO, "", 0,
        'HTTP Request: POST https://api.telegram.org/bot%s/sendMessage "200 OK"',
        ("123456:AA-secret",), None,
    )

    filtre.filter(trace)

    assert "123456:AA-secret" not in trace.getMessage()
    assert "***" in trace.getMessage()


def test_le_masque_laisse_passer_le_reste_du_journal():
    """Les requêtes des collecteurs doivent rester lisibles telles quelles."""
    trace = logging.LogRecord(
        "httpx", logging.INFO, "", 0, "HTTP Request: GET https://lefaso.net/feed/", (), None,
    )

    assert MasqueSecrets("123456:AA-secret").filter(trace) is True
    assert trace.getMessage() == "HTTP Request: GET https://lefaso.net/feed/"


def test_verifier_controle_le_canal_pas_seulement_le_bot():
    """Un bot authentifié mais pas administrateur du canal passerait pour prêt,
    et l'échec n'apparaîtrait qu'au premier post."""
    appels = []

    class ClientFactice:
        def post(self, url, json=None, **kw):
            appels.append(url.rsplit("/", 1)[-1])
            return _ReponseFactice({"ok": True, "result": {"username": "faso_donnees_bot",
                                                           "title": "Faso Données Publiques"}})

    resultat = Telegram(token="123:AA", chat_id="@faso_donnees",
                        client=ClientFactice()).verifier()

    assert appels == ["getMe", "getChat"]
    assert "Faso Données Publiques" in resultat


class _ReponseFactice:
    status_code = 200

    def __init__(self, donnees):
        self._donnees = donnees
        self.text = str(donnees)

    def json(self):
        return self._donnees


# --- propreté du résumé repris aux flux ----------------------------------

def test_le_titre_repete_en_tete_du_resume_est_retire():
    """Les fils de l'AIB republient le titre en tête du chapô. Repris tel quel,
    le post dit deux fois la même chose et se lit comme un bogue."""
    titre = "Koulpélogo/Sangha : Route dégradée, les jeunes de Dagom-Koom passent à l'action"
    resume = titre + " Sangha, 23 août 2026 (AIB) - La jeunesse du village s'est mobilisée."

    assert nettoyer_resume(resume, titre) == "Sangha, 23 août 2026 (AIB) - La jeunesse du village s'est mobilisée."


def test_le_titre_est_reconnu_meme_retouche():
    """Les flux retouchent la typographie du titre entre le champ et le chapô."""
    titre = "SONABEL : les candidats admis sous réserve"
    resume = "SONABEL: Les candidats admis sous reserve — le communiqué suit."

    assert nettoyer_resume(resume, titre) == "le communiqué suit."


def test_le_passe_partout_wordpress_est_coupe():
    """« The post X appeared first on Y » occupe la place du texte utile et
    fait finir tous les posts de la même façon."""
    resume = "Le communiqué de la SONABEL. The post SONABEL : les candidats appeared first on Burkina24."

    assert nettoyer_resume(resume, "SONABEL") == "Le communiqué de la SONABEL."


def test_la_troncature_de_source_est_coupee():
    assert nettoyer_resume("Un chapô coupé par la source […]", "Titre") == "Un chapô coupé par la source"


def test_un_resume_qui_ne_dit_que_le_titre_disparait():
    """Mieux vaut un post à une ligne qu'un post qui se répète."""
    assert nettoyer_resume("Un titre et rien d'autre", "Un titre et rien d'autre") is None


def test_le_post_ne_repete_pas_le_titre():
    titre = "Houet : AS Dafra remporte le tournoi"
    message = composer(
        item(genre="actualite", cle="actu-1", titre=titre, contexte="AIB",
             resume=titre + " Bobo-Dioulasso, 24 août 2026 (AIB) - Victoire en finale."),
        "telegram",
    )

    assert message.count("AS Dafra remporte le tournoi") == 1
    assert "Victoire en finale." in message


# --- amorçage d'un canal neuf --------------------------------------------

def test_lamorcage_marque_sans_envoyer(db, monkeypatch):
    """Ouvrir un canal ne doit pas y déverser d'un coup tout ce que la fenêtre
    de fraîcheur laisse passer : l'historique en garderait la trace pour
    toujours, devant des abonnés qui n'étaient pas encore là."""
    reseau = ReseauFactice()
    items = [item(cle=f"actu-{n}", genre="actualite") for n in (1, 2, 3)]
    monkeypatch.setattr(run, "items_a_publier", lambda *a, **k: items)
    monkeypatch.setattr(run, "reseaux_configures", lambda noms=None: [reseau])

    bilan = run.amorcer(db)

    assert bilan == {"telegram": 3}
    assert reseau.envoyes == [], "aucun appel réseau pendant l'amorçage"
    assert {p.statut for p in db.query(Publication).all()} == {"amorce"}


def test_un_item_amorce_ne_sera_jamais_publie(db):
    """C'est tout l'intérêt : ce qui existait avant l'ouverture reste dehors."""
    db.add(Publication(reseau="telegram", cle="actu-1", statut="amorce", tentatives=0))
    db.commit()

    assert cles_bloquees(db, "telegram") == {"actu-1"}


def test_lamorcage_ne_compte_pas_comme_une_tentative(db):
    """« tentatives » sert à repérer ce qui coince dans l'admin : y compter un
    marquage qui n'a jamais rien tenté fausserait la lecture."""
    publication = run.journaliser(db, "telegram", item(), "msg", statut="amorce")

    assert (publication.tentatives, publication.post_id) == (0, None)


# --- une même annonce vue par deux chemins -------------------------------
# Le 22 août 2026, gouvernement.gov.bf est passé aux permaliens « /?p=19635 » :
# ses 1 744 actualités ont été recollectées sous une seconde URL. Sans garde,
# chaque annonce sortirait deux fois sur le canal.

def test_deux_url_pour_un_meme_article_donnent_une_seule_cle(db):
    db.add(Source(id=1, slug="actualites_gouv", nom="Gouvernement",
                  url_base="https://gouvernement.gov.bf", type="institutionnel"))
    lisibles = Document(id=32900, source_id=1, url="https://gouvernement.gov.bf/actualites/meteo/",
                        type_doc="actualite_gouv", date_publication=date(2026, 8, 24),
                        meta={"wp_id": 19635})
    court = Document(id=33270, source_id=1, url="https://gouvernement.gov.bf/?p=19635",
                     type_doc="actualite_gouv", date_publication=date(2026, 8, 24),
                     meta={"wp_id": 19635})
    db.add_all([lisibles, court])
    db.commit()

    origines = racines(db, [lisibles, court])

    assert origines[32900] == origines[33270] == 32900


def test_deux_items_de_meme_cle_ne_sortent_quune_fois():
    """Le journal l'empêcherait de sortir une seconde fois demain, mais pas
    deux fois dans la même passe : la garde doit aussi être ici."""
    doublon = [
        item(cle="actu-32900", genre="actualite", date=date(2026, 8, 24), lien="https://a/1"),
        item(cle="actu-32900", genre="actualite", date=date(2026, 8, 24), lien="https://a/2"),
    ]

    assert len(ordonner(doublon, limite=10)) == 1


def test_les_titres_en_unicode_decoratif_sont_rendus_lisibles():
    """Un lecteur d'écran épelle les « mathematical bold » caractère par
    caractère, et la recherche du réseau ne les trouve pas."""
    assert lisible("𝐒𝐨𝐮𝐯𝐞𝐫𝐚𝐢𝐧𝐞𝐭é 𝐚𝐥𝐢𝐦𝐞𝐧𝐭𝐚𝐢𝐫𝐞") == "Souveraineté alimentaire"


def test_le_post_ne_garde_pas_lunicode_decoratif():
    message = composer(
        item(genre="actualite", cle="actu-1", titre="𝐒𝐨𝐮𝐯𝐞𝐫𝐚𝐢𝐧𝐞𝐭é 𝐚𝐥𝐢𝐦𝐞𝐧𝐭𝐚𝐢𝐫𝐞",
             contexte="Gouvernement"),
        "telegram",
    )

    assert "Souveraineté alimentaire" in message
