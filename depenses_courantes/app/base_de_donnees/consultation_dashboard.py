"""
Calcule les jeux de données utilisés par les graphiques de la page
Dashboard. Chaque fonction renvoie une structure simple (labels +
valeurs + couleurs) directement prête à être donnée à Chart.js côté
navigateur.

Deux filtres globaux s'appliquent à (presque) tous les graphiques :
  - "annee_reference" : l'année étudiée par les graphiques "sur une
    année" (ex: évolution mois par mois). Les graphiques qui comparent
    plusieurs années par nature (comparatif d'un mois, comparatif de
    tous les mois) ignorent ce filtre, puisqu'ils montrent justement
    toutes les années disponibles.
  - "comptes_ids" : les comptes à inclure. S'applique à tous les
    graphiques, y compris ceux qui comparent plusieurs années.

De plus, toute opération dont la catégorie est marquée "exclue des
statistiques" (ex: "Virements internes", ou une catégorie de
remboursements entre proches) est systématiquement ignorée dans TOUS
les calculs ci-dessous - pas seulement les graphiques par catégorie.
C'est pour ça que chaque requête joint la table "categories" et filtre
sur "COALESCE(categories.exclu_des_statistiques, 0) = 0", même quand le
nom de la catégorie elle-même n'est pas utilisé dans le résultat.
"""

import sqlite3
from datetime import date

from app.utilitaires.dates_francaises import NOMS_MOIS

# Jointure et condition réutilisées par toutes les requêtes : une opération
# sans catégorie (categorie_id NULL) n'est jamais exclue, seule une
# catégorie explicitement marquée l'est (COALESCE gère cette valeur NULL).
JOINTURE_CATEGORIES = "LEFT JOIN categories ON operations.categorie_id = categories.id"
CONDITION_NON_EXCLUE = "COALESCE(categories.exclu_des_statistiques, 0) = 0"


def _condition_comptes(comptes_ids: list[int]) -> tuple[str, list]:
    """Construit la condition SQL du filtre "Compte" (liste vide => aucun résultat)."""
    if not comptes_ids:
        return "1 = 0", []
    marqueurs = ",".join("?" for _ in comptes_ids)
    return f"operations.compte_id IN ({marqueurs})", list(comptes_ids)


def _depenses_par_categorie(connexion: sqlite3.Connection, condition_periode: str, parametres_periode: list) -> dict:
    """Total des dépenses par catégorie, sur la période donnée (clause SQL déjà prête)."""
    lignes = connexion.execute(
        f"""
        SELECT
            COALESCE(categories.nom, 'Sans catégorie') AS nom,
            COALESCE(categories.couleur, '#a99fb0') AS couleur,
            SUM(-operations.montant) AS total
        FROM operations
        {JOINTURE_CATEGORIES}
        WHERE operations.montant < 0 AND {CONDITION_NON_EXCLUE} AND {condition_periode}
        GROUP BY COALESCE(categories.nom, 'Sans catégorie'), COALESCE(categories.couleur, '#a99fb0')
        ORDER BY total DESC
        """,
        parametres_periode,
    ).fetchall()

    return {
        "labels": [ligne["nom"] for ligne in lignes],
        "valeurs": [round(ligne["total"], 2) for ligne in lignes],
        "couleurs": [ligne["couleur"] for ligne in lignes],
    }


def obtenir_donnees_dashboard(connexion: sqlite3.Connection, annee_reference: int, comptes_ids: list[int]) -> dict:
    """
    Calcule l'ensemble des jeux de données nécessaires à la page
    Dashboard, pour l'année de référence et les comptes donnés.
    """
    condition_comptes, parametres_comptes = _condition_comptes(comptes_ids)
    aujourdhui = date.today()
    mois_courant_libelle = NOMS_MOIS[aujourdhui.month]

    resultat = {"annee_reference": annee_reference, "mois_courant_libelle": mois_courant_libelle}

    # ------------------------------------------------------------------
    # 1. Dépenses par catégorie - mois en cours (toujours le vrai mois
    #    actuel, indépendamment de l'année de référence choisie)
    # ------------------------------------------------------------------
    condition = f"strftime('%Y-%m', operations.date_operation) = ? AND {condition_comptes}"
    parametres = [aujourdhui.strftime("%Y-%m")] + parametres_comptes
    resultat["depenses_categorie_mois_courant"] = _depenses_par_categorie(connexion, condition, parametres)

    # ------------------------------------------------------------------
    # 2. Dépenses par catégorie - année de référence
    # ------------------------------------------------------------------
    condition = f"strftime('%Y', operations.date_operation) = ? AND {condition_comptes}"
    parametres = [str(annee_reference)] + parametres_comptes
    resultat["depenses_categorie_annee"] = _depenses_par_categorie(connexion, condition, parametres)

    # Le classement des catégories (graphique 7) reprend les mêmes
    # totaux que le graphique 2, déjà triés du plus grand au plus petit.
    resultat["classement_categories"] = resultat["depenses_categorie_annee"]

    # ------------------------------------------------------------------
    # 3. Évolution des dépenses par mois - année de référence
    # ------------------------------------------------------------------
    lignes = connexion.execute(
        f"""
        SELECT strftime('%m', operations.date_operation) AS mois, SUM(-operations.montant) AS total
        FROM operations
        {JOINTURE_CATEGORIES}
        WHERE operations.montant < 0 AND {CONDITION_NON_EXCLUE}
          AND strftime('%Y', operations.date_operation) = ? AND {condition_comptes}
        GROUP BY mois
        ORDER BY mois
        """,
        [str(annee_reference)] + parametres_comptes,
    ).fetchall()
    totaux_par_mois = {int(ligne["mois"]): ligne["total"] for ligne in lignes}
    resultat["evolution_depenses_mois"] = {
        "labels": [NOMS_MOIS[m] for m in range(1, 13)],
        "valeurs": [round(totaux_par_mois.get(m, 0), 2) for m in range(1, 13)],
    }

    # ------------------------------------------------------------------
    # 4. Comparatif du mois en cours (ex: tous les "juillet") entre les années
    # ------------------------------------------------------------------
    lignes = connexion.execute(
        f"""
        SELECT strftime('%Y', operations.date_operation) AS annee, SUM(-operations.montant) AS total
        FROM operations
        {JOINTURE_CATEGORIES}
        WHERE operations.montant < 0 AND {CONDITION_NON_EXCLUE}
          AND strftime('%m', operations.date_operation) = ? AND {condition_comptes}
        GROUP BY annee
        ORDER BY annee
        """,
        [f"{aujourdhui.month:02d}"] + parametres_comptes,
    ).fetchall()
    resultat["comparatif_mois_courant_entre_annees"] = {
        "labels": [ligne["annee"] for ligne in lignes],
        "valeurs": [round(ligne["total"], 2) for ligne in lignes],
    }

    # ------------------------------------------------------------------
    # 5. Dépenses par compte - année de référence
    # ------------------------------------------------------------------
    lignes = connexion.execute(
        f"""
        SELECT comptes.nom_affiche AS nom, comptes.couleur AS couleur, SUM(-operations.montant) AS total
        FROM operations
        JOIN comptes ON operations.compte_id = comptes.id
        {JOINTURE_CATEGORIES}
        WHERE operations.montant < 0 AND {CONDITION_NON_EXCLUE}
          AND strftime('%Y', operations.date_operation) = ? AND {condition_comptes}
        GROUP BY comptes.id
        ORDER BY total DESC
        """,
        [str(annee_reference)] + parametres_comptes,
    ).fetchall()
    resultat["depenses_par_compte"] = {
        "labels": [ligne["nom"] for ligne in lignes],
        "valeurs": [round(ligne["total"], 2) for ligne in lignes],
        "couleurs": [ligne["couleur"] for ligne in lignes],
    }

    # ------------------------------------------------------------------
    # 6. Dépenses vs recettes par mois - année de référence
    # ------------------------------------------------------------------
    lignes = connexion.execute(
        f"""
        SELECT
            strftime('%m', operations.date_operation) AS mois,
            SUM(CASE WHEN operations.montant < 0 THEN -operations.montant ELSE 0 END) AS depenses,
            SUM(CASE WHEN operations.montant > 0 THEN operations.montant ELSE 0 END) AS recettes
        FROM operations
        {JOINTURE_CATEGORIES}
        WHERE {CONDITION_NON_EXCLUE}
          AND strftime('%Y', operations.date_operation) = ? AND {condition_comptes}
        GROUP BY mois
        ORDER BY mois
        """,
        [str(annee_reference)] + parametres_comptes,
    ).fetchall()
    depenses_par_mois = {int(ligne["mois"]): ligne["depenses"] for ligne in lignes}
    recettes_par_mois = {int(ligne["mois"]): ligne["recettes"] for ligne in lignes}
    resultat["depenses_vs_recettes_par_mois"] = {
        "labels": [NOMS_MOIS[m] for m in range(1, 13)],
        "depenses": [round(depenses_par_mois.get(m, 0), 2) for m in range(1, 13)],
        "recettes": [round(recettes_par_mois.get(m, 0), 2) for m in range(1, 13)],
    }

    # ------------------------------------------------------------------
    # 8. Évolution du solde net (recettes - dépenses) par mois
    # ------------------------------------------------------------------
    resultat["solde_net_par_mois"] = {
        "labels": [NOMS_MOIS[m] for m in range(1, 13)],
        "valeurs": [
            round(recettes_par_mois.get(m, 0) - depenses_par_mois.get(m, 0), 2) for m in range(1, 13)
        ],
    }

    # ------------------------------------------------------------------
    # 9. Répartition des catégories dans le temps - année de référence
    # ------------------------------------------------------------------
    lignes = connexion.execute(
        f"""
        SELECT
            strftime('%m', operations.date_operation) AS mois,
            COALESCE(categories.nom, 'Sans catégorie') AS categorie,
            COALESCE(categories.couleur, '#a99fb0') AS couleur,
            SUM(-operations.montant) AS total
        FROM operations
        {JOINTURE_CATEGORIES}
        WHERE operations.montant < 0 AND {CONDITION_NON_EXCLUE}
          AND strftime('%Y', operations.date_operation) = ? AND {condition_comptes}
        GROUP BY mois, categorie, couleur
        """,
        [str(annee_reference)] + parametres_comptes,
    ).fetchall()
    categories_rencontrees = {}
    for ligne in lignes:
        categories_rencontrees[ligne["categorie"]] = ligne["couleur"]
    valeurs_par_categorie_et_mois: dict[str, dict[int, float]] = {nom: {} for nom in categories_rencontrees}
    for ligne in lignes:
        valeurs_par_categorie_et_mois[ligne["categorie"]][int(ligne["mois"])] = ligne["total"]

    resultat["repartition_categories_temps"] = {
        "labels": [NOMS_MOIS[m] for m in range(1, 13)],
        "series": [
            {
                "nom": nom_categorie,
                "couleur": categories_rencontrees[nom_categorie],
                "valeurs": [
                    round(valeurs_par_categorie_et_mois[nom_categorie].get(m, 0), 2) for m in range(1, 13)
                ],
            }
            for nom_categorie in categories_rencontrees
        ],
    }

    # ------------------------------------------------------------------
    # 10. Dépenses par compte au fil des mois - année de référence
    # ------------------------------------------------------------------
    lignes = connexion.execute(
        f"""
        SELECT
            strftime('%m', operations.date_operation) AS mois,
            comptes.nom_affiche AS compte,
            comptes.couleur AS couleur,
            SUM(-operations.montant) AS total
        FROM operations
        JOIN comptes ON operations.compte_id = comptes.id
        {JOINTURE_CATEGORIES}
        WHERE operations.montant < 0 AND {CONDITION_NON_EXCLUE}
          AND strftime('%Y', operations.date_operation) = ? AND {condition_comptes}
        GROUP BY mois, comptes.id
        """,
        [str(annee_reference)] + parametres_comptes,
    ).fetchall()
    comptes_rencontres = {}
    for ligne in lignes:
        comptes_rencontres[ligne["compte"]] = ligne["couleur"]
    valeurs_par_compte_et_mois: dict[str, dict[int, float]] = {nom: {} for nom in comptes_rencontres}
    for ligne in lignes:
        valeurs_par_compte_et_mois[ligne["compte"]][int(ligne["mois"])] = ligne["total"]

    resultat["depenses_compte_mois"] = {
        "labels": [NOMS_MOIS[m] for m in range(1, 13)],
        "series": [
            {
                "nom": nom_compte,
                "couleur": comptes_rencontres[nom_compte],
                "valeurs": [round(valeurs_par_compte_et_mois[nom_compte].get(m, 0), 2) for m in range(1, 13)],
            }
            for nom_compte in comptes_rencontres
        ],
    }

    # ------------------------------------------------------------------
    # 11. Comparatif mensuel des dépenses totales, toutes années confondues
    # ------------------------------------------------------------------
    lignes = connexion.execute(
        f"""
        SELECT
            strftime('%Y', operations.date_operation) AS annee,
            strftime('%m', operations.date_operation) AS mois,
            SUM(-operations.montant) AS total
        FROM operations
        {JOINTURE_CATEGORIES}
        WHERE operations.montant < 0 AND {CONDITION_NON_EXCLUE} AND {condition_comptes}
        GROUP BY annee, mois
        """,
        parametres_comptes,
    ).fetchall()
    annees_disponibles = sorted({ligne["annee"] for ligne in lignes})
    valeurs_par_annee_et_mois: dict[str, dict[int, float]] = {annee: {} for annee in annees_disponibles}
    for ligne in lignes:
        valeurs_par_annee_et_mois[ligne["annee"]][int(ligne["mois"])] = ligne["total"]

    resultat["comparatif_mensuel_toutes_annees"] = {
        "labels": [NOMS_MOIS[m] for m in range(1, 13)],
        "series": [
            {
                "nom": annee,
                "valeurs": [round(valeurs_par_annee_et_mois[annee].get(m, 0), 2) for m in range(1, 13)],
            }
            for annee in annees_disponibles
        ],
    }

    return resultat
