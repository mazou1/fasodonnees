"""Classement d'un marché dans un secteur d'activité, déduit de son objet.

Heuristique déterministe (pas de LLM) : le modèle `Marche` n'a pas de champ
secteur dans le Quotidien ; on le déduit par mots-clés de l'objet (repli sur
l'autorité). Liste ordonnée du plus spécifique au plus générique - la première
règle qui matche gagne. Approche transparente, affichée comme « secteur déduit »
sur le site.
"""

from __future__ import annotations

import re

AUTRES = "Autres"

# (secteur, motif) - ordre = priorité (spécifique avant générique)
_REGLES: list[tuple[str, re.Pattern]] = [
    ("Santé", re.compile(
        r"m[ée]dic|m[ée]dico|pharmac|hospital|ambulanc|\bcsps\b|\bchr\b|\bchu"
        r"|sanitaire|\bsamu\b|dispensaire|infirm|chirurg|laboratoire|r[ée]actif"
        r"|d[ée]parasit|vaccin", re.I)),
    ("Eau & assainissement", re.compile(
        r"forage|adduction|eau potable|\beau\b|assainissement|ch[âa]teau d.eau"
        r"|\bpmh\b|\bpea\b|\bonea\b|latrin|hydraulique|\bpuits\b|caniveau"
        r"|\baep\b|\baeps\b|for[ée]e?s?\b", re.I)),
    ("Énergie", re.compile(
        r"solaire|[ée]lectrif|[ée]clairage|[ée]nergie|[ée]lectrique|groupe [ée]lectrog"
        r"|[ée]thanol|\bsonabhy\b|panneaux|lampadaire|photovolt|\bgaz\b|carburant"
        r"|hydrocarbure|p[ée]trolier", re.I)),
    ("Éducation & formation", re.compile(
        r"scolaire|\b[ée]coles?\b|[ée]ducation|universit|pr[ée]scolaire|p[ée]dagog"
        r"|\bceep\b|kits? scolaires?|manuels?\b|enseign|lyc[ée]e|\bcollege|formation"
        r"|table-?bancs?|\bedi\b|\bpdi\b", re.I)),
    ("Agriculture & élevage", re.compile(
        r"agricole|semences?|motoculteur|motopompe|phytosanitaire|[ée]leveur|fourrag"
        r"|intrant|charrue|batteuse|\bpfnl\b|coop[ée]rative|b[ée]tail|mara[îi]ch"
        r"|engrais|\bvivres?\b|c[ée]r[ée]al|pisci|semenc", re.I)),
    ("Informatique & numérique", re.compile(
        r"informatique|logiciel|serveur|licence|oracle|datacenter|r[ée]seau informatique"
        r"|num[ée]rique|\bwaf\b|ordinateur|imprimante|application|\bit\b|syst[èe]me d.info"
        r"|progiciel|\berp\b|c[âa]blage|t[ée]l[ée]com", re.I)),
    ("Transport & véhicules", re.compile(
        r"v[ée]hicule|\bmotos?\b|tricycle|\bengins?\b|camion|automobile|\bpneus?\b"
        r"|\bbus\b|mobilit[ée]", re.I)),
    ("Bâtiment & travaux publics", re.compile(
        r"travaux|construction|r[ée]habilit|r[ée]fection|b[âa]timent|\bhall\b|cl[ôo]ture"
        r"|\bmurs?\b|\broute|bitumage|voirie|magasin|r[ée]fectoire|am[ée]nagement|pavage"
        r"|dallage|toiture|extension|\bblocs?\b|\bpont\b|g[ée]nie civil|b[ée]ton", re.I)),
    ("Fournitures & équipements", re.compile(
        r"fourniture|mobilier|\bmat[ée]riel|[ée]quipement|imprim[ée]s|consommable"
        r"|acquisition|achat|bureau|drap|habillement|tenue|effets", re.I)),
    ("Services & prestations", re.compile(
        r"prestation|\bservices?\b|entretien|maintenance|restauration|location"
        r"|gardiennage|nettoyage|communication|\b[ée]tudes?\b|consultant|assurance"
        r"|audit|pause-?caf[ée]|nettoiement|surveillance|convoyage", re.I)),
]


def secteur_de(objet: str | None, autorite: str | None = None) -> str:
    """Secteur d'un marché, déduit de l'objet (repli sur l'autorité)."""
    texte = f"{objet or ''} {autorite or ''}"
    for secteur, motif in _REGLES:
        if motif.search(texte):
            return secteur
    return AUTRES
