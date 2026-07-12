"""
Petit utilitaire partagé : noms de mois en français, utilisés pour regrouper et afficher les opérations par mois (page Opérations) et pour les libellés des graphiques (page Dashboard).
"""

NOMS_MOIS = {
    1: "Janvier",
    2: "Février",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Août",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Décembre",
}


def obtenir_libelle_mois_annee(annee: int, mois: int) -> str:
    """Renvoie un libellé du type "Juillet 2026" à partir d'une année et d'un numéro de mois (1-12)."""
    return f"{NOMS_MOIS[mois]} {annee}"
