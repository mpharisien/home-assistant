"""
Point d'accès unique à la base de données.

Le chemin du fichier peut être personnalisé via la variable
d'environnement CHEMIN_BASE_DE_DONNEES (c'est ce que fait le script de
démarrage de l'add-on, run.sh, pour que les données soient stockées
dans /data - le dossier de l'add-on qui survit aux mises à jour et
redémarrages). En local sur un PC, sans cette variable définie, un
simple fichier "depenses.db" est créé dans le dossier courant.
"""

import os
import sqlite3

from app.base_de_donnees.schema import initialiser_base_de_donnees

CHEMIN_BASE_DE_DONNEES = os.environ.get("CHEMIN_BASE_DE_DONNEES", "depenses.db")


def obtenir_connexion() -> sqlite3.Connection:
    """
    Ouvre une connexion à la base de données, crée les tables si besoin,
    et renvoie la connexion prête à l'emploi.
    """
    connexion = sqlite3.connect(CHEMIN_BASE_DE_DONNEES)

    # Permet d'accéder aux colonnes d'un résultat par leur nom
    # (ex: ligne["nom"]) plutôt que par leur position (ligne[0]).
    connexion.row_factory = sqlite3.Row

    # SQLite n'active pas les clés étrangères par défaut : on l'active
    # explicitement pour que les erreurs de cohérence soient détectées.
    connexion.execute("PRAGMA foreign_keys = ON")

    initialiser_base_de_donnees(connexion)

    return connexion
