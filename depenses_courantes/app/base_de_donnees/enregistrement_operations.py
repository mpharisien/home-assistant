"""
Enregistrement des opérations importées dans la base de données.

Deux règles importantes sont appliquées ici :

1. Anti-doublon : chaque opération a un "identifiant_unique" (voir
   app/operations/modele_operation.py). Si cet identifiant existe déjà
   en base, l'opération est ignorée - elle n'écrase jamais une opération
   déjà enregistrée (donc ne touche pas non plus à sa catégorie, même si
   elle a été modifiée à la main entre-temps).

2. Correspondance des catégories : la catégorie brute fournie par la
   banque (ex: "Alimentation") est traduite vers une catégorie du projet
   via la table "correspondances_categories_bancaires". Si c'est la
   première fois qu'on voit cette catégorie pour cette banque, une
   nouvelle catégorie du projet est créée automatiquement avec le même
   nom, et la correspondance est mémorisée pour la suite. Si l'utilisateur
   renomme ensuite cette catégorie du projet, la correspondance continuera
   à pointer dessus : les prochains imports iront donc automatiquement
   dans la catégorie renommée.
"""

import sqlite3
from dataclasses import dataclass

from app.operations.modele_operation import Operation


@dataclass
class ResultatImport:
    """Petit résumé renvoyé après un import, utile à afficher à l'utilisateur."""

    nb_operations_ajoutees: int = 0
    nb_operations_deja_connues: int = 0


def obtenir_ou_creer_categorie(connexion: sqlite3.Connection, banque: str, categorie_source: str) -> int:
    """
    Renvoie l'identifiant de la catégorie du projet correspondant à une
    catégorie brute donnée par une banque. La crée si besoin, ainsi que
    la correspondance associée.
    """
    curseur = connexion.cursor()

    # 1. Cette correspondance banque -> catégorie existe-t-elle déjà ?
    curseur.execute(
        """
        SELECT categorie_id FROM correspondances_categories_bancaires
        WHERE banque = ? AND categorie_source = ?
        """,
        (banque, categorie_source),
    )
    ligne_trouvee = curseur.fetchone()
    if ligne_trouvee is not None:
        return ligne_trouvee["categorie_id"]

    # 2. Pas de correspondance : une catégorie du projet porte-t-elle déjà
    #    ce nom (ex: importée depuis une autre banque au même nom) ?
    curseur.execute("SELECT id FROM categories WHERE nom = ?", (categorie_source,))
    ligne_trouvee = curseur.fetchone()
    if ligne_trouvee is not None:
        categorie_id = ligne_trouvee["id"]
    else:
        # 3. Ni l'une ni l'autre : on crée une nouvelle catégorie du projet
        curseur.execute("INSERT INTO categories (nom) VALUES (?)", (categorie_source,))
        categorie_id = curseur.lastrowid

    # On mémorise la correspondance pour que les prochains imports la retrouvent
    curseur.execute(
        """
        INSERT INTO correspondances_categories_bancaires (banque, categorie_source, categorie_id)
        VALUES (?, ?, ?)
        """,
        (banque, categorie_source, categorie_id),
    )

    return categorie_id


def enregistrer_operations(connexion: sqlite3.Connection, operations: list[Operation]) -> ResultatImport:
    """
    Enregistre une liste d'opérations (issues d'un lecteur de banque) en
    base de données. Renvoie un résumé du nombre d'opérations ajoutées et
    ignorées (doublons déjà connus).
    """
    resultat = ResultatImport()

    for operation in operations:
        # Une opération sans catégorie fournie par la banque (ex: Crédit
        # Agricole) reste sans catégorie pour l'instant - elle sera
        # catégorisée plus tard, manuellement ou via une règle automatique
        # (fonctionnalité à venir dans une prochaine étape).
        categorie_id = None
        if operation.categorie_banque:
            categorie_id = obtenir_ou_creer_categorie(
                connexion, operation.banque, operation.categorie_banque
            )

        curseur = connexion.execute(
            """
            INSERT OR IGNORE INTO operations
                (identifiant_unique, date_operation, montant, compte, banque, libelle, categorie_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation.identifiant_unique,
                operation.date_operation.isoformat(),
                operation.montant,
                operation.compte,
                operation.banque,
                operation.libelle,
                categorie_id,
            ),
        )

        # "INSERT OR IGNORE" ne fait rien si l'identifiant_unique existait
        # déjà (contrainte UNIQUE) : rowcount vaut alors 0.
        if curseur.rowcount == 1:
            resultat.nb_operations_ajoutees += 1
        else:
            resultat.nb_operations_deja_connues += 1

    connexion.commit()

    return resultat
