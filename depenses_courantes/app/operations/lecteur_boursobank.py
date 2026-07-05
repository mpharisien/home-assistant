"""
Lecteur d'exports Boursobank, au format CSV.

Contrairement au Crédit Agricole, Boursobank fournit déjà une
catégorisation de chaque opération (colonne "category"). On la
récupère directement plutôt que de la redeviner nous-mêmes.

Le fichier n'a en revanche pas d'identifiant unique fourni par la
banque : on en fabrique un nous-mêmes à partir d'informations qui,
combinées, désignent une opération de façon quasiment certaine
(compte + date + libellé + montant + solde du compte après
l'opération).
"""

import csv
from datetime import datetime

from app.comptes.configuration_comptes import obtenir_nom_compte
from app.operations.modele_operation import Operation

NOM_BANQUE = "Boursobank"


def lire_fichier_csv(chemin_fichier: str) -> list[Operation]:
    """
    Lit un export CSV Boursobank et renvoie la liste des opérations
    qu'il contient, sous forme d'objets Operation.
    Le compte concerné est détecté automatiquement à partir du fichier
    (voir app/comptes/configuration_comptes.py).

    :param chemin_fichier: chemin vers le fichier .csv exporté
    """
    operations = []

    # encoding="utf-8-sig" retire proprement le "BOM" (un petit marqueur
    # invisible que certains exports Boursobank ajoutent en début de fichier)
    with open(chemin_fichier, encoding="utf-8-sig", newline="") as fichier:
        lignes = csv.DictReader(fichier, delimiter=";")

        for ligne in lignes:
            nom_compte = obtenir_nom_compte(ligne["accountNum"])

            date_operation = datetime.strptime(ligne["dateOp"], "%Y-%m-%d").date()

            # Le montant est écrit à la française ("-9,00") : on remplace
            # la virgule par un point pour pouvoir le convertir en nombre.
            montant = float(ligne["amount"].replace(",", "."))

            # On ne garde qu'un seul niveau de catégorie : la colonne
            # "category" de Boursobank (la plus précise). La colonne
            # "categoryParent", plus générale, n'est volontairement pas
            # utilisée pour garder les choses simples.
            categorie_banque = ligne["category"].strip()

            identifiant_unique = (
                f"BB-{ligne['accountNum']}-{ligne['dateOp']}-"
                f"{ligne['amount']}-{ligne['accountbalance']}"
            )

            operations.append(
                Operation(
                    date_operation=date_operation,
                    montant=montant,
                    compte=nom_compte,
                    banque=NOM_BANQUE,
                    libelle=ligne["label"].strip(),
                    categorie_banque=categorie_banque,
                    identifiant_unique=identifiant_unique,
                )
            )

    return operations
