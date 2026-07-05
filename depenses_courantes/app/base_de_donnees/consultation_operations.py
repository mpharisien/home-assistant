"""
Fonctions de consultation (lecture seule) de la base de données,
utilisées par l'interface web pour afficher les opérations.
"""

import sqlite3


def lister_operations(connexion: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Renvoie toutes les opérations enregistrées, les plus récentes en
    premier, avec le nom actuel de leur compte (toujours à jour même si
    l'utilisateur l'a renommé depuis) et de leur catégorie.
    """
    return connexion.execute(
        """
        SELECT
            operations.date_operation,
            comptes.nom_affiche AS compte,
            operations.libelle,
            operations.montant,
            categories.nom AS categorie
        FROM operations
        JOIN comptes ON operations.compte_id = comptes.id
        LEFT JOIN categories ON operations.categorie_id = categories.id
        ORDER BY operations.date_operation DESC
        """
    ).fetchall()
