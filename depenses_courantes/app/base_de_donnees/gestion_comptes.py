"""
Gestion des comptes bancaires suivis par le projet.

Aucun numéro de compte n'est écrit dans le code : chaque compte est
détecté automatiquement au moment d'un import, puis stocké en base de
données. Un compte nouvellement détecté est mis "en_attente" : ses
opérations ne sont importées qu'une fois que l'utilisateur l'a validé
sur la page "Comptes" de l'interface web - ça évite d'importer par
erreur un compte qu'on ne voulait pas suivre (ex: une épargne).

Statuts possibles d'un compte :
  - "en_attente" : détecté, mais pas encore validé par l'utilisateur
  - "suivi"      : validé, ses opérations sont importées normalement
  - "ignore"     : mis de côté par l'utilisateur, jamais importé

Grâce à cette approche, n'importe qui peut installer cet add-on et
l'utiliser avec ses propres comptes Crédit Agricole ou Boursobank,
sans jamais avoir à modifier le code.
"""

import sqlite3

STATUTS_VALIDES = ("en_attente", "suivi", "ignore")


def obtenir_ou_creer_compte(
    connexion: sqlite3.Connection, banque: str, identifiant_brut: str, nom_suggere: str | None
) -> sqlite3.Row:
    """
    Renvoie la ligne du compte correspondant à (banque, identifiant_brut).
    S'il n'existait pas encore, il est créé avec le statut "en_attente"
    et le nom fourni en suggestion (ou un nom générique à défaut).
    """
    ligne = connexion.execute(
        "SELECT * FROM comptes WHERE banque = ? AND identifiant_brut = ?",
        (banque, identifiant_brut),
    ).fetchone()

    if ligne is not None:
        return ligne

    nom_par_defaut = nom_suggere or f"{banque} - Compte {identifiant_brut}"

    curseur = connexion.execute(
        """
        INSERT INTO comptes (identifiant_brut, banque, nom_affiche, statut)
        VALUES (?, ?, ?, 'en_attente')
        """,
        (identifiant_brut, banque, nom_par_defaut),
    )
    connexion.commit()

    return connexion.execute(
        "SELECT * FROM comptes WHERE id = ?", (curseur.lastrowid,)
    ).fetchone()


def lister_comptes(connexion: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Renvoie tous les comptes, les comptes en attente de validation
    d'abord (ce sont ceux qui demandent une action), puis les suivis,
    puis les ignorés.
    """
    return connexion.execute(
        """
        SELECT * FROM comptes
        ORDER BY
            CASE statut WHEN 'en_attente' THEN 0 WHEN 'suivi' THEN 1 ELSE 2 END,
            nom_affiche
        """
    ).fetchall()


def renommer_compte(connexion: sqlite3.Connection, compte_id: int, nouveau_nom: str) -> None:
    """Change le nom affiché d'un compte (le numéro de compte, lui, ne change jamais)."""
    connexion.execute("UPDATE comptes SET nom_affiche = ? WHERE id = ?", (nouveau_nom, compte_id))
    connexion.commit()


def definir_statut_compte(connexion: sqlite3.Connection, compte_id: int, nouveau_statut: str) -> None:
    """Change le statut d'un compte (ex: valider un compte en attente, ou en ignorer un)."""
    if nouveau_statut not in STATUTS_VALIDES:
        raise ValueError(f"Statut de compte invalide : '{nouveau_statut}'")
    connexion.execute("UPDATE comptes SET statut = ? WHERE id = ?", (nouveau_statut, compte_id))
    connexion.commit()
