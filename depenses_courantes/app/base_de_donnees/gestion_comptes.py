"""
Gestion des comptes bancaires suivis par le projet.

Aucun numéro de compte n'est écrit dans le code : chaque compte est
détecté automatiquement au moment d'un import, puis stocké en base de
données, immédiatement suivi. L'utilisateur peut choisir de l'ignorer
depuis la page "Comptes" s'il ne souhaite pas le suivre (ex: une
épargne) : ses opérations déjà importées sont alors supprimées, et
plus aucune de ses opérations ne sera importée tant qu'il reste ignoré.

Statuts possibles d'un compte :
  - "suivi"  : ses opérations sont importées normalement
  - "ignore" : mis de côté par l'utilisateur, jamais importé (et ses
               opérations déjà importées ont été supprimées)

Grâce à cette approche, n'importe qui peut installer cet add-on et
l'utiliser avec ses propres comptes Crédit Agricole ou Boursobank,
sans jamais avoir à modifier le code.
"""

import sqlite3

STATUTS_VALIDES = ("suivi", "ignore")

# Couleur par défaut attribuée à un compte selon sa banque, la première
# fois qu'il est détecté. Purement indicative : modifiable à tout moment
# depuis la page "Comptes".
COULEURS_PAR_DEFAUT_SELON_BANQUE = {
    "Crédit Agricole": "#1a8a4c",
    "Boursobank": "#0d3b73",
}
COULEUR_PAR_DEFAUT_GENERIQUE = "#6a2c91"

# Palette de couleurs proposées pour l'identité visuelle d'un compte.
# Volontairement limitée à un jeu de couleurs franches et bien
# distinctes entre elles, plutôt qu'un sélecteur de couleur libre.
PALETTE_COULEURS_COMPTES = [
    ("Vert", "#1a8a4c"),
    ("Bleu", "#0d3b73"),
    ("Violet", "#6a2c91"),
    ("Rouge", "#b3452f"),
    ("Orange", "#c9781c"),
    ("Jaune", "#b8960c"),
    ("Turquoise", "#0f8a8a"),
    ("Rose", "#c23a72"),
    ("Bleu clair", "#2f9bd6"),
    ("Vert clair", "#5cab5c"),
    ("Marron", "#8a5a3c"),
    ("Gris bleu", "#5b6b8c"),
    ("Indigo", "#4a3f9e"),
    ("Corail", "#d1615d"),
    ("Olive", "#8a8a3c"),
    ("Gris", "#6b6272"),
]


def obtenir_ou_creer_compte(
    connexion: sqlite3.Connection, banque: str, identifiant_brut: str, nom_suggere: str | None
) -> tuple[sqlite3.Row, bool]:
    """
    Renvoie la ligne du compte correspondant à (banque, identifiant_brut),
    et un booléen indiquant s'il vient d'être créé à l'instant. S'il
    n'existait pas encore, il est créé directement avec le statut
    "suivi", une couleur par défaut selon la banque, et une lettre
    reprise de la première lettre du nom.
    """
    ligne = connexion.execute(
        "SELECT * FROM comptes WHERE banque = ? AND identifiant_brut = ?",
        (banque, identifiant_brut),
    ).fetchone()

    if ligne is not None:
        return ligne, False

    nom_par_defaut = nom_suggere or f"{banque} - Compte {identifiant_brut}"
    couleur_par_defaut = COULEURS_PAR_DEFAUT_SELON_BANQUE.get(banque, COULEUR_PAR_DEFAUT_GENERIQUE)
    lettre_par_defaut = nom_par_defaut[0].upper()

    curseur = connexion.execute(
        """
        INSERT INTO comptes (identifiant_brut, banque, nom_affiche, statut, couleur, lettre)
        VALUES (?, ?, ?, 'suivi', ?, ?)
        """,
        (identifiant_brut, banque, nom_par_defaut, couleur_par_defaut, lettre_par_defaut),
    )
    connexion.commit()

    nouvelle_ligne = connexion.execute(
        "SELECT * FROM comptes WHERE id = ?", (curseur.lastrowid,)
    ).fetchone()
    return nouvelle_ligne, True


def lister_comptes(connexion: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Renvoie tous les comptes avec, pour chacun, son nombre actuel
    d'opérations enregistrées (utile par exemple pour prévenir avant de
    les supprimer en ignorant le compte).
    """
    return connexion.execute(
        """
        SELECT
            comptes.*,
            (SELECT COUNT(*) FROM operations WHERE operations.compte_id = comptes.id) AS nb_operations
        FROM comptes
        ORDER BY
            CASE statut WHEN 'suivi' THEN 0 ELSE 1 END,
            nom_affiche
        """
    ).fetchall()


def modifier_compte(
    connexion: sqlite3.Connection, compte_id: int, nouveau_nom: str, nouvelle_couleur: str, nouvelle_lettre: str
) -> None:
    """Met à jour en une fois le nom, la couleur et la lettre d'un compte (le numéro, lui, ne change jamais)."""
    connexion.execute(
        "UPDATE comptes SET nom_affiche = ?, couleur = ?, lettre = ? WHERE id = ?",
        (nouveau_nom, nouvelle_couleur, nouvelle_lettre.upper()[:1], compte_id),
    )
    connexion.commit()


def ignorer_compte(connexion: sqlite3.Connection, compte_id: int) -> int:
    """
    Met un compte de côté : supprime toutes ses opérations déjà
    importées, puis passe son statut à "ignore". Renvoie le nombre
    d'opérations supprimées.
    """
    curseur = connexion.execute("DELETE FROM operations WHERE compte_id = ?", (compte_id,))
    nb_operations_supprimees = curseur.rowcount

    connexion.execute("UPDATE comptes SET statut = 'ignore' WHERE id = ?", (compte_id,))
    connexion.commit()

    return nb_operations_supprimees


def reprendre_suivi_compte(connexion: sqlite3.Connection, compte_id: int) -> None:
    """
    Remet un compte ignoré en statut "suivi". Ne restaure aucune
    opération (elles ont été supprimées quand le compte a été ignoré) :
    il faudra réimporter un fichier si on veut à nouveau ses données.
    """
    connexion.execute("UPDATE comptes SET statut = 'suivi' WHERE id = ?", (compte_id,))
    connexion.commit()
