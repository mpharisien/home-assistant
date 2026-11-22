"""
Lecture et écriture des données du PEA dans la base.

Toutes les requêtes SQL du module PEA sont regroupées ici : les pages (routes.py)
et les calculs (calculs.py) n'ont pas besoin de connaître la structure des tables.
"""

import sqlite3

# ----------------------------------------------------------------------------
# Actions
# ----------------------------------------------------------------------------

def lister_actions(connexion: sqlite3.Connection) -> list[sqlite3.Row]:
    return connexion.execute("SELECT * FROM actions ORDER BY nom COLLATE NOCASE").fetchall()


def obtenir_action(connexion: sqlite3.Connection, action_id: int) -> sqlite3.Row | None:
    return connexion.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()


def trouver_action_par_nom(connexion: sqlite3.Connection, nom: str) -> sqlite3.Row | None:
    """Recherche sans tenir compte des majuscules (la colonne est en COLLATE NOCASE)."""
    return connexion.execute("SELECT * FROM actions WHERE nom = ?", (nom.strip(),)).fetchone()


def creer_action(connexion: sqlite3.Connection, nom: str, ticker: str | None = None,
                 suivie: bool = True, en_evidence: bool = False, notes: str | None = None) -> int:
    """Crée une action et renvoie son identifiant (sans valider la transaction)."""
    curseur = connexion.execute(
        "INSERT INTO actions (nom, ticker, suivie, en_evidence, notes) VALUES (?, ?, ?, ?, ?)",
        (nom.strip(), ticker or None, int(suivie), int(en_evidence), notes or None),
    )
    return curseur.lastrowid


def modifier_action(connexion: sqlite3.Connection, action_id: int, nom: str, ticker: str | None,
                    suivie: bool, en_evidence: bool, notes: str | None) -> None:
    connexion.execute(
        "UPDATE actions SET nom = ?, ticker = ?, suivie = ?, en_evidence = ?, notes = ? WHERE id = ?",
        (nom.strip(), ticker or None, int(suivie), int(en_evidence), notes or None, action_id),
    )


def compter_mouvements_action(connexion: sqlite3.Connection, action_id: int) -> int:
    return connexion.execute(
        "SELECT COUNT(*) FROM pea_mouvements WHERE action_id = ?", (action_id,)
    ).fetchone()[0]


def supprimer_action(connexion: sqlite3.Connection, action_id: int) -> None:
    """Supprime une action (ses dividendes et données de bourse sont supprimés avec elle)."""
    connexion.execute("DELETE FROM actions WHERE id = ?", (action_id,))


# ----------------------------------------------------------------------------
# Dividendes par exercice (saisis) et détachés (Yahoo)
# ----------------------------------------------------------------------------

def lire_dividendes_exercice(connexion: sqlite3.Connection) -> dict[int, dict[int, float]]:
    """Renvoie {action_id: {annee: montant}} pour toutes les actions."""
    resultat: dict[int, dict[int, float]] = {}
    for ligne in connexion.execute("SELECT action_id, annee, montant FROM dividendes_exercice"):
        resultat.setdefault(ligne["action_id"], {})[ligne["annee"]] = ligne["montant"]
    return resultat


def enregistrer_dividende_exercice(connexion: sqlite3.Connection, action_id: int,
                                   annee: int, montant: float | None) -> None:
    """Enregistre le dividende d'une année, ou le supprime si `montant` est None."""
    if montant is None:
        connexion.execute(
            "DELETE FROM dividendes_exercice WHERE action_id = ? AND annee = ?", (action_id, annee)
        )
    else:
        connexion.execute(
            "INSERT INTO dividendes_exercice (action_id, annee, montant) VALUES (?, ?, ?) "
            "ON CONFLICT (action_id, annee) DO UPDATE SET montant = excluded.montant",
            (action_id, annee, montant),
        )


def lire_dividendes_detaches(connexion: sqlite3.Connection, action_id: int) -> list[sqlite3.Row]:
    return connexion.execute(
        "SELECT date, montant FROM dividendes_detaches WHERE action_id = ? ORDER BY date DESC",
        (action_id,),
    ).fetchall()


# ----------------------------------------------------------------------------
# Données de bourse
# ----------------------------------------------------------------------------

def lire_cours(connexion: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    """Renvoie {action_id: ligne de la table cours_bourse}."""
    return {
        ligne["action_id"]: ligne
        for ligne in connexion.execute("SELECT * FROM cours_bourse")
    }


# ----------------------------------------------------------------------------
# Mouvements
# ----------------------------------------------------------------------------

def lister_mouvements(connexion: sqlite3.Connection) -> list[sqlite3.Row]:
    """Tous les mouvements, du plus ancien au plus récent, avec le nom de l'action."""
    return connexion.execute(
        """
        SELECT m.*, a.nom AS nom_action
        FROM pea_mouvements m
        LEFT JOIN actions a ON a.id = m.action_id
        ORDER BY m.date, m.id
        """
    ).fetchall()


def obtenir_mouvement(connexion: sqlite3.Connection, mouvement_id: int) -> sqlite3.Row | None:
    return connexion.execute(
        """
        SELECT m.*, a.nom AS nom_action
        FROM pea_mouvements m
        LEFT JOIN actions a ON a.id = m.action_id
        WHERE m.id = ?
        """,
        (mouvement_id,),
    ).fetchone()


_COLONNES_MOUVEMENT = ("date", "type", "action_id", "quantite", "cours", "frais", "montant", "commentaire")


def inserer_mouvement(connexion: sqlite3.Connection, mouvement: dict) -> int:
    """Ajoute un mouvement (sans valider la transaction). `mouvement` contient les colonnes ci-dessus."""
    curseur = connexion.execute(
        f"INSERT INTO pea_mouvements ({', '.join(_COLONNES_MOUVEMENT)}) "
        f"VALUES ({', '.join('?' for _ in _COLONNES_MOUVEMENT)})",
        tuple(mouvement[colonne] for colonne in _COLONNES_MOUVEMENT),
    )
    return curseur.lastrowid


def modifier_mouvement(connexion: sqlite3.Connection, mouvement_id: int, mouvement: dict) -> None:
    connexion.execute(
        f"UPDATE pea_mouvements SET {', '.join(f'{colonne} = ?' for colonne in _COLONNES_MOUVEMENT)} "
        "WHERE id = ?",
        tuple(mouvement[colonne] for colonne in _COLONNES_MOUVEMENT) + (mouvement_id,),
    )


def supprimer_mouvement(connexion: sqlite3.Connection, mouvement_id: int) -> None:
    connexion.execute("DELETE FROM pea_mouvements WHERE id = ?", (mouvement_id,))


def supprimer_tous_les_mouvements(connexion: sqlite3.Connection) -> None:
    connexion.execute("DELETE FROM pea_mouvements")
