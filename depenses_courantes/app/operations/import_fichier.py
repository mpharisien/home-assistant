"""
Point d'entrée unique pour importer un fichier d'export bancaire, quel
que soit son origine. Le bon lecteur est choisi automatiquement d'après
l'extension du fichier :
  - .ofx  -> Crédit Agricole
  - .csv  -> Boursobank

Pour prendre en charge une nouvelle banque plus tard, il suffira
d'ajouter son lecteur dans app/operations/, puis une ligne dans
EXTENSIONS_VERS_LECTEUR ci-dessous.
"""

import os
import sqlite3

from app.base_de_donnees.enregistrement_operations import ResultatImport, enregistrer_operations
from app.operations.lecteur_boursobank import lire_fichier_csv
from app.operations.lecteur_credit_agricole import lire_fichier_ofx

EXTENSIONS_VERS_LECTEUR = {
    ".ofx": lire_fichier_ofx,
    ".csv": lire_fichier_csv,
}


def importer_fichier_operations(
    connexion: sqlite3.Connection, chemin_fichier: str, nom_fichier_original: str
) -> ResultatImport:
    """
    Lit un fichier d'export bancaire et enregistre ses opérations en
    base de données.

    :param connexion: connexion à la base de données
    :param chemin_fichier: chemin du fichier sur le disque (peut être
                            un nom temporaire, peu importe)
    :param nom_fichier_original: nom du fichier tel que déposé par
                                  l'utilisateur, utilisé uniquement pour
                                  déterminer son format via l'extension
    :raises ValueError: si l'extension du fichier n'est pas reconnue,
                         ou si le compte qu'il contient n'est pas
                         encore configuré
    """
    extension = os.path.splitext(nom_fichier_original)[1].lower()
    lire_le_fichier = EXTENSIONS_VERS_LECTEUR.get(extension)

    if lire_le_fichier is None:
        raise ValueError(
            f"Format de fichier non pris en charge : '{extension}'. "
            f"Formats acceptés : {', '.join(EXTENSIONS_VERS_LECTEUR)}"
        )

    operations = lire_le_fichier(chemin_fichier)
    return enregistrer_operations(connexion, operations)
