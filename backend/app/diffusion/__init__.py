"""Diffusion automatique des publications du site sur les réseaux sociaux.

Le site expose déjà ses flux RSS (`/api/rss/*.xml`), mais un flux ne touche que
les lecteurs équipés d'un agrégateur. Au Burkina Faso l'information circule sur
Facebook, et pour les journalistes sur X et Telegram : ce module poste
lui-même, depuis le worker, plutôt que de confier les pages à un service tiers.

Trois couches, séparées pour rester testables sans jamais appeler une API :

- `messages` : le texte du post, à partir d'un item du site (pur, testé) ;
- `selection` : ce qui reste à publier, par réseau (SQL + priorités) ;
- `reseaux`   : les clients Telegram, Facebook et X ;
- `run`       : l'orchestration, le quota et le journal `publication`.
"""
