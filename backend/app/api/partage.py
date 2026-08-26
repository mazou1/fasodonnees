"""Pages de partage : les métadonnées Open Graph que lisent les réseaux.

Le site est une application Vue rendue dans le navigateur : son `index.html`
porte un titre et une description uniques pour TOUTES les pages, et les robots
de Facebook, X ou Telegram n'exécutent pas de JavaScript. Partagé tel quel, un
compte rendu du Conseil des ministres du 21 août s'affiche donc avec la même
vignette générique qu'un texte de loi - et tous les posts de la page se
ressemblent.

Ces pages, servies par l'API, rendent le titre et le résumé réels de l'entité.
Caddy y route les robots sociaux (cf. deploy/Caddyfile) ; un visiteur qui
tombe dessus est redirigé vers la vraie page du site.
"""

from __future__ import annotations

import json
from xml.sax.saxutils import escape, quoteattr

GABARIT = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{titre}</title>
<meta name="description" content={description_attr}>
<link rel="canonical" href={url_attr}>
<meta property="og:type" content="article">
<meta property="og:site_name" content="Faso Données Publiques">
<meta property="og:locale" content="fr_FR">
<meta property="og:title" content={titre_attr}>
<meta property="og:description" content={description_attr}>
<meta property="og:url" content={url_attr}>
{image}<meta name="twitter:card" content="{carte}">
<meta name="twitter:title" content={titre_attr}>
<meta name="twitter:description" content={description_attr}>
<meta http-equiv="refresh" content={refresh_attr}>
</head>
<body>
<p><a href={url_attr}>{titre}</a></p>
<script>location.replace({url_js});</script>
</body>
</html>
"""


def html_partage(*, titre: str, description: str, url: str, image: str = "") -> str:
    """Page minimale : métadonnées pour les robots, redirection pour les humains.

    La redirection est faite par `meta refresh` ET par script, pas par un code
    HTTP 3xx : plusieurs robots sociaux suivent les redirections et vont lire
    les métadonnées de la page d'arrivée - c'est-à-dire, ici, celles de la SPA,
    exactement ce qu'on cherche à éviter.
    """
    balise_image = (
        f'<meta property="og:image" content={quoteattr(image)}>\n' if image else ""
    )
    return GABARIT.format(
        titre=escape(titre),
        titre_attr=quoteattr(titre),
        description_attr=quoteattr(description),
        url_attr=quoteattr(url),
        # littéral JavaScript : json.dumps échappe guillemets et non-ASCII,
        # là où quoteattr produit une syntaxe HTML, pas JS
        url_js=json.dumps(url),
        image=balise_image,
        carte="summary_large_image" if image else "summary",
        refresh_attr=quoteattr(f"0; url={url}"),
    )
