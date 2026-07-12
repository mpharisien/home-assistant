"""
Palette de couleurs partagée, utilisée pour l'identité visuelle des
comptes (app/base_de_donnees/gestion_comptes.py) et des catégories
(app/base_de_donnees/gestion_categories.py). Volontairement limitée à
un jeu de couleurs franches et bien distinctes entre elles (16 pour
l'instant - on pourra l'étendre si le besoin s'en fait sentir).
"""

PALETTE_COULEURS = [
    ("Vert", "#1a8a4c"),
    ("Bleu", "#0d3b73"),
    ("Violet", "#6a2c91"),
    ("Rouge", "#b3452f"),
    ("Orange", "#c9781c"),
    ("Jaune", "#b8960c"),
    ("Turquoise", "#0f8a8a"),
    ("Rose", "#c23a72"),
    ("Bleu clair", "#2f9bd6"),
    ("Vert clair", "#5cab5c"),
    ("Marron", "#8a5a3c"),
    ("Gris bleu", "#5b6b8c"),
    ("Indigo", "#4a3f9e"),
    ("Corail", "#d1615d"),
    ("Olive", "#8a8a3c"),
    ("Gris", "#6b6272"),
]


def obtenir_couleur_par_rang(rang: int) -> str:
    """
    Renvoie une couleur de la palette selon un rang (0, 1, 2, ...), en
    tournant dans la liste une fois arrivé au bout (rang 16 reprend la
    couleur du rang 0). Utile pour attribuer automatiquement une
    couleur différente à chaque nouvelle catégorie ou nouveau compte.
    """
    return PALETTE_COULEURS[rang % len(PALETTE_COULEURS)][1]
