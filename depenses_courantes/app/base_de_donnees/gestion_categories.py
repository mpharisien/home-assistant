"""
Gestion des catégories du projet : identité visuelle (nom, couleur),
correspondances avec les catégories brutes fournies par les banques,
règles d'attribution automatique par mot-clé, fusion et suppression.

Priorité d'attribution d'une catégorie à une opération, au moment d'un
import (voir app/base_de_donnees/enregistrement_operations.py) :
  1. Une règle par mot-clé, si le libellé de l'opération contient un des
     mots-clés définis (recherche insensible à la casse). Volontairement
     prioritaire sur la catégorie fournie par la banque : ces règles
     servent justement à corriger une catégorisation bancaire jugée
     incorrecte.
  2. À défaut, la catégorie fournie par la banque (via la table de
     correspondance).
  3. À défaut, aucune catégorie ("Sans catégorie").

Un mot-clé ne peut être utilisé que par une seule catégorie à la fois
(contrainte d'unicité en base) : il ne peut donc jamais y avoir
d'ambiguïté entre deux catégories sur un même mot-clé.

Une modification des catégories ou des règles ne touche jamais aux
opérations déjà importées (sauf action explicite : fusion, suppression) -
elle ne concerne que les prochains imports.
"""

import sqlite3


def creer_categorie(connexion: sqlite3.Connection, nom: str, couleur: str) -> int:
    """
    Crée une nouvelle catégorie manuellement (indépendamment de tout import).

    :raises ValueError: si une catégorie porte déjà ce nom
    """
    existe_deja = connexion.execute("SELECT id FROM categories WHERE nom = ?", (nom,)).fetchone()
    if existe_deja is not None:
        raise ValueError(f'Une catégorie nommée "{nom}" existe déjà.')

    curseur = connexion.execute("INSERT INTO categories (nom, couleur) VALUES (?, ?)", (nom, couleur))
    connexion.commit()
    return curseur.lastrowid


def definir_categorie_operation(
    connexion: sqlite3.Connection, operation_id: int, nouvelle_categorie_id: int | None
) -> None:
    """
    Change manuellement la catégorie d'une opération précise (depuis la
    page Opérations). L'opération est marquée "modifiée manuellement" :
    une future règle automatique, même modifiée après coup, ne
    l'écrasera jamais (voir app/base_de_donnees/enregistrement_operations.py).
    """
    connexion.execute(
        "UPDATE operations SET categorie_id = ?, categorie_modifiee_manuellement = 1 WHERE id = ?",
        (nouvelle_categorie_id, operation_id),
    )
    connexion.commit()


def lister_categories(connexion: sqlite3.Connection) -> list[sqlite3.Row]:
    """Renvoie toutes les catégories avec leur nombre actuel d'opérations."""
    return connexion.execute(
        """
        SELECT
            categories.*,
            (SELECT COUNT(*) FROM operations WHERE operations.categorie_id = categories.id) AS nb_operations
        FROM categories
        ORDER BY nom
        """
    ).fetchall()


def obtenir_correspondances(connexion: sqlite3.Connection, categorie_id: int) -> list[sqlite3.Row]:
    """Renvoie les correspondances bancaires (banque + catégorie brute) qui pointent vers cette catégorie."""
    return connexion.execute(
        """
        SELECT banque, categorie_source
        FROM correspondances_categories_bancaires
        WHERE categorie_id = ?
        ORDER BY banque, categorie_source
        """,
        (categorie_id,),
    ).fetchall()


def obtenir_mots_cles(connexion: sqlite3.Connection, categorie_id: int) -> list[sqlite3.Row]:
    """Renvoie les mots-clés de règle automatique associés à cette catégorie."""
    return connexion.execute(
        "SELECT id, mot_cle FROM regles_attribution_automatique WHERE categorie_id = ? ORDER BY mot_cle",
        (categorie_id,),
    ).fetchall()


def modifier_categorie(
    connexion: sqlite3.Connection,
    categorie_id: int,
    nouveau_nom: str,
    nouvelle_couleur: str,
    exclu_des_statistiques: bool,
) -> None:
    """Met à jour le nom, la couleur, et le réglage "exclu des statistiques" d'une catégorie."""
    connexion.execute(
        "UPDATE categories SET nom = ?, couleur = ?, exclu_des_statistiques = ? WHERE id = ?",
        (nouveau_nom, nouvelle_couleur, 1 if exclu_des_statistiques else 0, categorie_id),
    )
    connexion.commit()


def ajouter_mot_cle(connexion: sqlite3.Connection, categorie_id: int, mot_cle: str) -> None:
    """
    Ajoute un mot-clé de règle automatique à une catégorie. Le mot-clé
    est normalisé en minuscules avant d'être stocké, pour que l'unicité
    et la recherche restent cohérentes quelle que soit la casse saisie.

    :raises ValueError: si ce mot-clé est déjà utilisé par une autre catégorie
    """
    mot_cle_normalise = mot_cle.strip().lower()

    ligne_existante = connexion.execute(
        """
        SELECT categories.nom FROM regles_attribution_automatique
        JOIN categories ON regles_attribution_automatique.categorie_id = categories.id
        WHERE regles_attribution_automatique.mot_cle = ?
        """,
        (mot_cle_normalise,),
    ).fetchone()

    if ligne_existante is not None:
        raise ValueError(
            f'Le mot-clé "{mot_cle_normalise}" est déjà utilisé par la catégorie "{ligne_existante["nom"]}".'
        )

    connexion.execute(
        "INSERT INTO regles_attribution_automatique (mot_cle, categorie_id) VALUES (?, ?)",
        (mot_cle_normalise, categorie_id),
    )
    connexion.commit()


def supprimer_mot_cle(connexion: sqlite3.Connection, mot_cle_id: int) -> None:
    """Supprime un mot-clé de règle automatique."""
    connexion.execute("DELETE FROM regles_attribution_automatique WHERE id = ?", (mot_cle_id,))
    connexion.commit()


def fusionner_categories(connexion: sqlite3.Connection, categorie_source_id: int, categorie_cible_id: int) -> int:
    """
    Fusionne une catégorie dans une autre : toutes les opérations, les
    correspondances bancaires et les règles par mot-clé de la catégorie
    source basculent vers la catégorie cible, puis la source est
    supprimée. Renvoie le nombre d'opérations concernées.
    """
    curseur = connexion.execute(
        "UPDATE operations SET categorie_id = ? WHERE categorie_id = ?",
        (categorie_cible_id, categorie_source_id),
    )
    nb_operations = curseur.rowcount

    connexion.execute(
        "UPDATE correspondances_categories_bancaires SET categorie_id = ? WHERE categorie_id = ?",
        (categorie_cible_id, categorie_source_id),
    )
    connexion.execute(
        "UPDATE regles_attribution_automatique SET categorie_id = ? WHERE categorie_id = ?",
        (categorie_cible_id, categorie_source_id),
    )
    connexion.execute("DELETE FROM categories WHERE id = ?", (categorie_source_id,))
    connexion.commit()

    return nb_operations


def supprimer_categorie(connexion: sqlite3.Connection, categorie_id: int) -> int:
    """
    Supprime une catégorie. Ses opérations repassent "Sans catégorie"
    (elles ne sont jamais supprimées). Renvoie le nombre d'opérations
    concernées.
    """
    curseur = connexion.execute(
        "UPDATE operations SET categorie_id = NULL WHERE categorie_id = ?", (categorie_id,)
    )
    nb_operations = curseur.rowcount

    connexion.execute("DELETE FROM correspondances_categories_bancaires WHERE categorie_id = ?", (categorie_id,))
    connexion.execute("DELETE FROM regles_attribution_automatique WHERE categorie_id = ?", (categorie_id,))
    connexion.execute("DELETE FROM categories WHERE id = ?", (categorie_id,))
    connexion.commit()

    return nb_operations


def trouver_categorie_id_par_regle(connexion: sqlite3.Connection, libelle: str) -> int | None:
    """
    Cherche si un mot-clé de règle automatique correspond au libellé
    fourni (recherche insensible à la casse). Si plusieurs mots-clés
    correspondent à la fois, le plus long (donc le plus précis) est
    préféré. Renvoie l'identifiant de la catégorie correspondante, ou
    None si aucun mot-clé ne correspond.
    """
    libelle_minuscule = libelle.lower()

    regles = connexion.execute(
        "SELECT mot_cle, categorie_id FROM regles_attribution_automatique"
    ).fetchall()
    regles_triees = sorted(regles, key=lambda regle: len(regle["mot_cle"]), reverse=True)

    for regle in regles_triees:
        if regle["mot_cle"].lower() in libelle_minuscule:
            return regle["categorie_id"]

    return None
