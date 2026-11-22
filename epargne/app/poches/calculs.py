"""
Calculs d'une poche simple (Epsor, Enerfip...) à partir de ses mouvements
et de ses valorisations.

VALEUR ESTIMÉE DE LA POCHE :
  - si une valorisation a été saisie : dernière valorisation + versements
    - retraits effectués depuis cette date ;
  - sinon : capital net versé (versements - retraits).
"""

import sqlite3
from dataclasses import dataclass

from app.reglages import POCHES


@dataclass
class ResumePoche:
    code: str
    definition: dict
    mouvements: list[sqlite3.Row]       # du plus récent au plus ancien
    valorisations: list[sqlite3.Row]    # du plus récent au plus ancien
    capital_net: float                  # apports - retraits
    revenus: float
    charges: float
    derniere_valorisation: sqlite3.Row | None
    valeur: float                       # valeur estimée (voir en haut du fichier)


def effet_mouvement(code_poche: str, type_mouvement: str) -> str:
    """Effet d'un type de mouvement ("apport", "retrait"...), "neutre" s'il est inconnu."""
    type_defini = POCHES[code_poche]["types"].get(type_mouvement)
    return type_defini["effet"] if type_defini else "neutre"


def flux_de_capital(code_poche: str, mouvement) -> float:
    """Variation du capital investi due à un mouvement (+ apport, - retrait, 0 sinon)."""
    effet = effet_mouvement(code_poche, mouvement["type"])
    if effet == "apport":
        return mouvement["montant"]
    if effet == "retrait":
        return -mouvement["montant"]
    return 0.0


def resumer_poche(connexion: sqlite3.Connection, code: str) -> ResumePoche:
    mouvements = connexion.execute(
        "SELECT * FROM poche_mouvements WHERE poche = ? ORDER BY date, id", (code,)
    ).fetchall()
    valorisations = connexion.execute(
        "SELECT * FROM poche_valorisations WHERE poche = ? ORDER BY date", (code,)
    ).fetchall()

    capital_net = sum(flux_de_capital(code, m) for m in mouvements)
    revenus = sum(m["montant"] for m in mouvements if effet_mouvement(code, m["type"]) == "revenu")
    charges = sum(m["montant"] for m in mouvements if effet_mouvement(code, m["type"]) == "charge")

    derniere = valorisations[-1] if valorisations else None
    if derniere is not None:
        valeur = derniere["valeur"] + sum(
            flux_de_capital(code, m) for m in mouvements if m["date"] > derniere["date"]
        )
    else:
        valeur = capital_net

    return ResumePoche(
        code=code,
        definition=POCHES[code],
        mouvements=list(reversed(mouvements)),
        valorisations=list(reversed(valorisations)),
        capital_net=capital_net,
        revenus=revenus,
        charges=charges,
        derniere_valorisation=derniere,
        valeur=valeur,
    )
