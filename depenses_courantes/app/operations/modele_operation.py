"""
Structure commune utilisée pour représenter une opération bancaire
(une ligne de relevé), une fois uniformisée quelle que soit la banque
et le format d'export d'origine (OFX, CSV, ...).

Chaque "lecteur" (un par banque) a pour seul rôle de transformer son
format d'origine en une liste d'objets Operation. Tout le reste du
programme (stockage, analyses, affichage) ne travaille qu'avec cette
structure commune et n'a pas besoin de savoir d'où vient l'opération.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Operation:
    # Date à laquelle l'opération a eu lieu
    date_operation: date

    # Montant signé : négatif = dépense, positif = rentrée d'argent
    montant: float

    # Nom du compte, ex: "Boursobank - Perso courant"
    compte: str

    # Nom de la banque, ex: "Boursobank", "Crédit Agricole"
    banque: str

    # Description de l'opération, nettoyée pour être lisible
    libelle: str

    # Catégorie telle que fournie par la banque, si elle en fournit une
    # (ex: "Alimentation" pour Boursobank). None si la banque n'en fournit
    # pas (ex: Crédit Agricole). Cette valeur brute sera ensuite transformée
    # en une de nos propres catégories du projet au moment de l'enregistrement
    # en base de données (voir app/base_de_donnees/enregistrement_operations.py).
    categorie_banque: Optional[str] = None

    # Identifiant unique et stable de l'opération, utilisé pour éviter
    # de compter deux fois la même opération si on réimporte une période
    # qui se chevauche avec un import précédent.
    identifiant_unique: str = ""
