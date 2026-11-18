"""Alertes personnalisées par Telegram.

Un lecteur écrit au bot de la plateforme pour suivre un mot-clé, une personne
ou une institution ; il reçoit un message quand une nomination, une décision,
un texte ou un vote validé y correspond.

- `bot.py` : la conversation (s'abonner, lister, arrêter).
- `envoi.py` : ce qui est nouveau, à qui l'envoyer, et le journal qui évite de
  l'envoyer deux fois.

Le courriel n'est pas proposé : la plateforme n'a pas de service d'envoi, et
une adresse est une donnée personnelle autrement plus lourde à garder qu'un
identifiant de conversation que l'abonné efface d'un `/arreter tout`.
"""
