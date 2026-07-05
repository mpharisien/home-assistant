"""
Association entre l'identifiant brut d'un compte (tel qu'il apparaît dans
les exports bancaires : ACCTID pour un OFX, accountNum pour un CSV
Boursobank) et le nom clair utilisé partout ailleurs dans le projet.

Pour suivre un nouveau compte : trouver son identifiant dans un export
(généralement visible tel quel dans le fichier), puis ajouter une ligne
ci-dessous. C'est la seule modification nécessaire.
"""

COMPTES_CONNUS = {
    "65032603216": "Crédit Agricole - Compte courant perso",
    "00040599852": "Boursobank - Perso courant",
}


def obtenir_nom_compte(identifiant_brut: str) -> str:
    """
    Renvoie le nom clair du compte correspondant à un identifiant brut.
    Lève une erreur explicite si ce compte n'est pas encore connu, pour
    éviter d'importer silencieusement des opérations dans un compte mal
    identifié.
    """
    if identifiant_brut not in COMPTES_CONNUS:
        raise ValueError(
            f"Compte inconnu (identifiant '{identifiant_brut}'). "
            "Ajoute-le dans app/comptes/configuration_comptes.py pour "
            "pouvoir importer ses opérations."
        )
    return COMPTES_CONNUS[identifiant_brut]
