"""
Fonctions de consultation (lecture seule) de la base de données,
utilisées par l'interface web pour afficher les opérations.

Deux façons de consulter les opérations :
  - lister_operations() : la liste brute complète, sans filtre ni tri
    particulier (utilisée par la page "Historique").
  - lister_operations_groupees_par_mois() : une version filtrable et
    triable, regroupée par mois (utilisée par la page "Opérations").
"""

import sqlite3
from collections import defaultdict
from datetime import date

from app.utilitaires.dates_francaises import obtenir_libelle_mois_annee


def lister_operations(connexion: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Renvoie toutes les opérations enregistrées, les plus récentes en
    premier, avec le nom/couleur/lettre actuels de leur compte et le
    nom/couleur actuels de leur catégorie (toujours à jour même si
    l'utilisateur les a changés depuis).
    """
    return connexion.execute(
        """
        SELECT
            operations.date_operation,
            comptes.nom_affiche AS compte,
            comptes.couleur AS compte_couleur,
            comptes.lettre AS compte_lettre,
            operations.libelle,
            operations.montant,
            categories.nom AS categorie,
            categories.couleur AS categorie_couleur
        FROM operations
        JOIN comptes ON operations.compte_id = comptes.id
        LEFT JOIN categories ON operations.categorie_id = categories.id
        ORDER BY operations.date_operation DESC
        """
    ).fetchall()


def obtenir_annees_disponibles(connexion: sqlite3.Connection) -> list[int]:
    """Renvoie la liste des années pour lesquelles il existe au moins une opération, la plus récente en premier."""
    lignes = connexion.execute(
        "SELECT DISTINCT CAST(strftime('%Y', date_operation) AS INTEGER) AS annee FROM operations ORDER BY annee DESC"
    ).fetchall()
    return [ligne["annee"] for ligne in lignes]


def _construire_filtre_comptes(comptes_ids: list[int]) -> tuple[str, list]:
    """Construit la condition SQL du filtre "Compte" (jamais vide : liste vide => aucun résultat)."""
    if not comptes_ids:
        return "1 = 0", []
    marqueurs = ",".join("?" for _ in comptes_ids)
    return f"operations.compte_id IN ({marqueurs})", list(comptes_ids)


def _construire_filtre_categories(categories_valeurs: list[str]) -> tuple[str, list]:
    """
    Construit la condition SQL du filtre "Catégorie". "categories_valeurs"
    peut contenir des identifiants de catégorie (sous forme de texte) et/ou
    la valeur spéciale "aucune" pour "Sans catégorie". Liste vide => aucun résultat.
    """
    if not categories_valeurs:
        return "1 = 0", []

    morceaux = []
    parametres = []

    identifiants = [valeur for valeur in categories_valeurs if valeur != "aucune"]
    if identifiants:
        marqueurs = ",".join("?" for _ in identifiants)
        morceaux.append(f"operations.categorie_id IN ({marqueurs})")
        parametres.extend(identifiants)

    if "aucune" in categories_valeurs:
        morceaux.append("operations.categorie_id IS NULL")

    return "(" + " OR ".join(morceaux) + ")", parametres


def lister_operations_groupees_par_mois(
    connexion: sqlite3.Connection,
    annee: str,
    mois: str,
    comptes_ids: list[int],
    categories_valeurs: list[str],
    tri: str,
) -> list[dict]:
    """
    Renvoie les opérations correspondant aux filtres donnés, regroupées
    par mois (le plus récent en premier), avec pour chaque mois le total
    de ses dépenses.

    :param annee: année à filtrer ("toutes" pour ne pas filtrer)
    :param mois: mois à filtrer, 1-12 en texte ("tous" pour ne pas filtrer)
    :param comptes_ids: identifiants des comptes à inclure
    :param categories_valeurs: identifiants de catégorie à inclure (+ "aucune" pour "Sans catégorie")
    :param tri: "date" (plus récent d'abord) ou "montant" (plus grosses dépenses d'abord)
    """
    conditions = ["1 = 1"]
    parametres: list = []

    if annee != "toutes":
        conditions.append("strftime('%Y', operations.date_operation) = ?")
        parametres.append(str(annee))

    if mois != "tous":
        conditions.append("strftime('%m', operations.date_operation) = ?")
        parametres.append(f"{int(mois):02d}")

    condition_comptes, parametres_comptes = _construire_filtre_comptes(comptes_ids)
    conditions.append(condition_comptes)
    parametres.extend(parametres_comptes)

    condition_categories, parametres_categories = _construire_filtre_categories(categories_valeurs)
    conditions.append(condition_categories)
    parametres.extend(parametres_categories)

    lignes = connexion.execute(
        f"""
        SELECT
            operations.date_operation,
            operations.libelle,
            operations.montant,
            comptes.nom_affiche AS compte,
            comptes.couleur AS compte_couleur,
            comptes.lettre AS compte_lettre,
            categories.nom AS categorie,
            categories.couleur AS categorie_couleur
        FROM operations
        JOIN comptes ON operations.compte_id = comptes.id
        LEFT JOIN categories ON operations.categorie_id = categories.id
        WHERE {' AND '.join(conditions)}
        ORDER BY operations.date_operation DESC
        """,
        parametres,
    ).fetchall()

    # Regroupement par (année, mois). La base est déjà triée par date
    # décroissante : ça suffit pour le tri "date" à l'intérieur de chaque
    # groupe. Pour le tri "montant", chaque groupe est retrié séparément
    # juste après (le regroupement par mois, lui, ne change jamais).
    groupes: dict[tuple[int, int], list] = defaultdict(list)
    for ligne in lignes:
        annee_ligne, mois_ligne = ligne["date_operation"].split("-")[:2]
        groupes[(int(annee_ligne), int(mois_ligne))].append(ligne)

    if tri == "montant":
        for cle in groupes:
            groupes[cle].sort(key=lambda ligne: ligne["montant"])

    resultat = []
    for (annee_groupe, mois_groupe) in sorted(groupes.keys(), reverse=True):
        operations_du_mois = groupes[(annee_groupe, mois_groupe)]
        total_depenses = sum(op["montant"] for op in operations_du_mois if op["montant"] < 0)
        resultat.append(
            {
                "libelle_mois": obtenir_libelle_mois_annee(annee_groupe, mois_groupe),
                "total_depenses": total_depenses,
                "operations": operations_du_mois,
            }
        )

    return resultat
