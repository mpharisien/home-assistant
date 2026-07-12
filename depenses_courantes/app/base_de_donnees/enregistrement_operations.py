"""
Enregistrement des opérations importées dans la base de données.

Trois règles importantes sont appliquées ici :

1. Résolution du compte : chaque opération est rattachée à un compte
   (créé automatiquement, immédiatement suivi, s'il est nouveau - voir
   gestion_comptes.py). Seules les opérations d'un compte "ignore" sont
   écartées (comptabilisées à part, pour en informer l'utilisateur).

2. Anti-doublon : chaque opération a un "identifiant_unique" (voir
   app/operations/modele_operation.py). Si cet identifiant existe déjà
   en base, l'opération est ignorée - elle n'écrase jamais une opération
   déjà enregistrée (donc ne touche pas non plus à sa catégorie, même si
   elle a été modifiée à la main entre-temps).

3. Correspondance des catégories : la catégorie brute fournie par la
   banque (ex: "Alimentation") est traduite vers une catégorie du projet
   via la table "correspondances_categories_bancaires". Si c'est la
   première fois qu'on voit cette catégorie pour cette banque, une
   nouvelle catégorie du projet est créée automatiquement avec le même
   nom, et la correspondance est mémorisée pour la suite.
"""

import sqlite3
from dataclasses import dataclass, field

from app.base_de_donnees.gestion_comptes import obtenir_ou_creer_compte
from app.operations.modele_operation import Operation


@dataclass
class RapportImport:
    """Compte-rendu complet d'un import, destiné à être affiché à l'utilisateur."""

    nb_operations_ajoutees: int = 0
    nb_operations_deja_connues: int = 0

    # Noms des comptes tout juste découverts pendant cet import (informatif :
    # ils sont déjà suivis, l'utilisateur peut simplement vouloir les
    # renommer ou personnaliser leur couleur sur la page "Comptes")
    comptes_nouveaux: set[str] = field(default_factory=set)

    # Noms des comptes que l'utilisateur a choisi d'ignorer
    comptes_ignores: set[str] = field(default_factory=set)


def obtenir_ou_creer_categorie(connexion: sqlite3.Connection, banque: str, categorie_source: str) -> int:
    """
    Renvoie l'identifiant de la catégorie du projet correspondant à une
    catégorie brute donnée par une banque. La crée si besoin, ainsi que
    la correspondance associée.
    """
    curseur = connexion.cursor()

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

    curseur.execute("SELECT id FROM categories WHERE nom = ?", (categorie_source,))
    ligne_trouvee = curseur.fetchone()
    if ligne_trouvee is not None:
        categorie_id = ligne_trouvee["id"]
    else:
        curseur.execute("INSERT INTO categories (nom) VALUES (?)", (categorie_source,))
        categorie_id = curseur.lastrowid

    curseur.execute(
        """
        INSERT INTO correspondances_categories_bancaires (banque, categorie_source, categorie_id)
        VALUES (?, ?, ?)
        """,
        (banque, categorie_source, categorie_id),
    )

    return categorie_id


def enregistrer_operations(connexion: sqlite3.Connection, operations: list[Operation]) -> RapportImport:
    """
    Enregistre une liste d'opérations (issues d'un lecteur de banque) en
    base de données. Renvoie un compte-rendu complet de ce qui s'est passé.
    """
    rapport = RapportImport()

    for operation in operations:
        compte, vient_detre_cree = obtenir_ou_creer_compte(
            connexion, operation.banque, operation.identifiant_compte_brut, operation.nom_compte_suggere
        )

        if vient_detre_cree:
            rapport.comptes_nouveaux.add(compte["nom_affiche"])

        if compte["statut"] == "ignore":
            rapport.comptes_ignores.add(compte["nom_affiche"])
            continue

        # statut == "suivi" : on enregistre réellement cette opération
        categorie_id = None
        if operation.categorie_banque:
            categorie_id = obtenir_ou_creer_categorie(
                connexion, operation.banque, operation.categorie_banque
            )

        curseur = connexion.execute(
            """
            INSERT OR IGNORE INTO operations
                (identifiant_unique, date_operation, montant, compte_id, libelle, categorie_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                operation.identifiant_unique,
                operation.date_operation.isoformat(),
                operation.montant,
                compte["id"],
                operation.libelle,
                categorie_id,
            ),
        )

        if curseur.rowcount == 1:
            rapport.nb_operations_ajoutees += 1
        else:
            rapport.nb_operations_deja_connues += 1

    connexion.commit()

    return rapport
