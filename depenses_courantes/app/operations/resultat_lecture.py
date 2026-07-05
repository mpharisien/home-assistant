"""
Résultat renvoyé par un lecteur de banque (voir lecteur_credit_agricole.py
et lecteur_boursobank.py) : simplement la liste des opérations lues. Le
lecteur ne trie jamais les comptes lui-même (suivi/ignoré/inconnu) :
cette décision est prise plus tard, au moment de l'enregistrement en
base de données (voir app/base_de_donnees/gestion_comptes.py).
"""

from dataclasses import dataclass, field

from app.operations.modele_operation import Operation


@dataclass
class ResultatLecture:
    operations: list[Operation] = field(default_factory=list)
