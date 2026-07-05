"""
Lecteur d'exports Boursobank, au format CSV.

Contrairement au Crédit Agricole, Boursobank fournit déjà une
catégorisation de chaque opération (colonnes "category" et
"categoryParent"). On la récupère directement plutôt que de la
redeviner nous-mêmes.

Le fichier n'a en revanche pas d'identifiant unique fourni par la
banque : on en fabrique un nous-mêmes à partir d'informations qui,
combinées, désignent une opération de façon quasiment certaine
(compte + date + libellé + montant + solde du compte après
l'opération).
"""

import csv
from datetime import datetime

from app.operations.modele_operation import Operation

NOM_BANQUE = "Boursobank"


def lire_fichier_csv(chemin_fichier: str, nom_compte: str) -> list[Operation]:
    """
    Lit un export CSV Boursobank et renvoie la liste des opérations
    qu'il contient, sous forme d'objets Operation.

    :param chemin_fichier: chemin vers le fichier .csv exporté
    :param nom_compte: nom donné au compte dans notre projet,
                        ex: "Boursobank - Perso courant"
    """
    operations = []

    # encoding="utf-8-sig" retire proprement le "BOM" (un petit marqueur
    # invisible que certains exports Boursobank ajoutent en début de fichier)
    with open(chemin_fichier, encoding="utf-8-sig", newline="") as fichier:
        lignes = csv.DictReader(fichier, delimiter=";")

        for ligne in lignes:
            date_operation = datetime.strptime(ligne["dateOp"], "%Y-%m-%d").date()

            # Le montant est écrit à la française ("-9,00") : on remplace
            # la virgule par un point pour pouvoir le convertir en nombre.
            montant = float(ligne["amount"].replace(",", "."))

            # Une catégorie vaut "Non catégorisé" quand Boursobank n'a pas
            # réussi à en deviner une : on la garde telle quelle, on la
            # traitera comme une catégorie "à corriger" plus tard.
            categorie = ligne["categoryParent"].strip()
            sous_categorie = ligne["category"].strip()

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
                    categorie=categorie,
                    sous_categorie=sous_categorie,
                    identifiant_unique=identifiant_unique,
                )
            )

    return operations
