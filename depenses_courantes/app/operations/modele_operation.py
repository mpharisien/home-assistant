"""
Structure commune utilisée pour représenter une opération bancaire
(une ligne de relevé), une fois uniformisée quelle que soit la banque
et le format d'export d'origine (OFX, CSV, ...).

Chaque "lecteur" (un par banque) a pour seul rôle de transformer son
format d'origine en une liste d'objets Operation. Il ne décide jamais
si un compte doit être suivi ou non : il se contente de rapporter
l'identifiant brut du compte tel qu'il apparaît dans le fichier. C'est
la base de données (voir app/base_de_donnees/gestion_comptes.py) qui
détermine ensuite si ce compte est suivi, en attente, ou ignoré.
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

    # Identifiant du compte tel qu'il apparaît dans le fichier bancaire
    # (ACCTID pour un OFX, accountNum pour un CSV Boursobank). Ce n'est
    # pas encore un nom "propre" : juste le numéro brut.
    identifiant_compte_brut: str

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

    # Nom suggéré pour ce compte s'il est nouveau (ex: Boursobank fournit
    # un nom de compte assez parlant). Utilisé uniquement comme proposition
    # par défaut la première fois qu'un compte est détecté - l'utilisateur
    # peut le renommer librement ensuite sur la page "Comptes".
    nom_compte_suggere: Optional[str] = None

    # Identifiant unique et stable de l'opération, utilisé pour éviter
    # de compter deux fois la même opération si on réimporte une période
    # qui se chevauche avec un import précédent.
    identifiant_unique: str = ""
