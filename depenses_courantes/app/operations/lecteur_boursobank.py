"""
Lecteur d'exports Boursobank, au format CSV.

Contrairement au Crédit Agricole, Boursobank fournit déjà une
catégorisation de chaque opération (colonne "category"), ainsi qu'un
nom de compte assez parlant (colonne "accountLabel", ex: "Perso -
compte courant") qu'on utilise comme suggestion de nom par défaut si
le compte est nouveau.

Le fichier n'a en revanche pas d'identifiant unique fourni par la
banque : on en fabrique un nous-mêmes à partir d'informations qui,
combinées, désignent une opération de façon quasiment certaine
(compte + date + libellé + montant + solde du compte après
l'opération).

Un même fichier peut contenir les opérations de plusieurs comptes
mélangées (chaque ligne précise son propre numéro de compte via la
colonne accountNum) : chaque ligne est donc traitée indépendamment.
"""

import csv
import re
from datetime import datetime

from app.operations.modele_operation import Operation
from app.operations.resultat_lecture import ResultatLecture

NOM_BANQUE = "Boursobank"


def _convertir_montant_boursobank(montant_brut: str) -> float:
    """
    Convertit un montant écrit à la française en nombre. Boursobank
    utilise une virgule comme séparateur décimal (ex: "-9,00"), et,
    pour les montants à partir de 1000, un espace comme séparateur de
    milliers (ex: "1 000,00") : les deux doivent être gérés.
    """
    montant_sans_espaces = re.sub(r"\s", "", montant_brut)
    return float(montant_sans_espaces.replace(",", "."))


def lire_fichier_csv(chemin_fichier: str) -> ResultatLecture:
    """
    Lit un export CSV Boursobank (un ou plusieurs comptes mélangés) et
    renvoie toutes les opérations qu'il contient.

    :param chemin_fichier: chemin vers le fichier .csv exporté
    """
    resultat = ResultatLecture()

    with open(chemin_fichier, encoding="utf-8-sig", newline="") as fichier:
        lignes = csv.DictReader(fichier, delimiter=";")

        for ligne in lignes:
            date_operation = datetime.strptime(ligne["dateOp"], "%Y-%m-%d").date()
            montant = _convertir_montant_boursobank(ligne["amount"])
            categorie_banque = ligne["category"].strip()

            nom_suggere = ligne.get("accountLabel", "").strip()
            nom_suggere = f"{NOM_BANQUE} - {nom_suggere}" if nom_suggere else None

            identifiant_unique = (
                f"BB-{ligne['accountNum']}-{ligne['dateOp']}-"
                f"{ligne['amount']}-{ligne['accountbalance']}"
            )

            resultat.operations.append(
                Operation(
                    date_operation=date_operation,
                    montant=montant,
                    identifiant_compte_brut=ligne["accountNum"],
                    banque=NOM_BANQUE,
                    libelle=ligne["label"].strip(),
                    categorie_banque=categorie_banque,
                    nom_compte_suggere=nom_suggere,
                    identifiant_unique=identifiant_unique,
                )
            )

    return resultat
