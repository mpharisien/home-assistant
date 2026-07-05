"""
Fonctions de consultation (lecture seule) de la base de données,
utilisées par l'interface web pour afficher les opérations.
"""

import sqlite3


def lister_operations(connexion: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Renvoie toutes les opérations enregistrées, les plus récentes en
    premier, accompagnées du nom de leur catégorie (si elles en ont une).
    """
    return connexion.execute(
        """
        SELECT
            operations.date_operation,
            operations.compte,
            operations.libelle,
            operations.montant,
            categories.nom AS categorie
        FROM operations
        LEFT JOIN categories ON operations.categorie_id = categories.id
        ORDER BY operations.date_operation DESC
        """
    ).fetchall()
