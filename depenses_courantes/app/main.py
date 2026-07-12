"""
Application "Dépenses Courantes" - Point d'entrée principal.

Cette application web (Flask) permet de :
  1. Consulter un tableau de bord de graphiques (page d'accueil, /)
  2. Consulter les opérations avec filtres et regroupement mensuel (/operations)
  3. Consulter l'historique complet, sans filtre (/historique)
  4. Gérer les catégories : identité visuelle, correspondances bancaires,
     mots-clés d'attribution automatique, fusion, suppression (/categories)
  5. Gérer les comptes détectés (/comptes)
  6. Importer un fichier d'export bancaire (/importer)

CE FICHIER PEUT AUSSI ÊTRE LANCÉ EN LOCAL SUR TON PC, SANS HOME ASSISTANT :
  1. Ouvrir un terminal dans le dossier depenses_courantes
  2. Installer les dépendances :  pip install -r app/requirements.txt
  3. Lancer l'application :       python -m app.main
  4. Ouvrir dans un navigateur :  http://localhost:8000
Dans ce cas, la base de données est créée sous forme d'un simple fichier
"depenses.db" dans le dossier courant (voir app/base_de_donnees/connexion.py).
"""

import json
import os
import tempfile
from datetime import date

from flask import Flask, flash, make_response, redirect, render_template, request, url_for

from app.base_de_donnees.connexion import obtenir_connexion
from app.base_de_donnees.consultation_dashboard import obtenir_donnees_dashboard
from app.base_de_donnees.consultation_operations import (
    lister_operations,
    lister_operations_groupees_par_mois,
    obtenir_annees_disponibles,
    obtenir_derniere_date_operation,
)
from app.base_de_donnees.gestion_categories import (
    ajouter_mot_cle,
    fusionner_categories,
    lister_categories,
    modifier_categorie,
    obtenir_correspondances,
    obtenir_mots_cles,
    supprimer_categorie,
    supprimer_mot_cle,
)
from app.base_de_donnees.gestion_comptes import (
    PALETTE_COULEURS_COMPTES,
    ignorer_compte,
    lister_comptes,
    modifier_compte,
    reprendre_suivi_compte,
)
from app.operations.import_fichier import importer_fichier_operations
from app.utilitaires.dates_francaises import NOMS_MOIS

application_web = Flask(__name__)

# Nécessaire pour que Flask puisse afficher des messages temporaires
# (ex: "Import réussi") d'une page à l'autre. Cette application n'étant
# accessible que sur le réseau local de la maison (pas exposée sur
# Internet), une valeur fixe suffit tout à fait ici.
application_web.secret_key = "depenses-courantes-cle-locale"


@application_web.route("/")
def page_dashboard():
    """Page d'accueil : tableau de bord de graphiques."""
    connexion = obtenir_connexion()

    annees_disponibles = obtenir_annees_disponibles(connexion) or [date.today().year]
    annee_selectionnee = request.args.get("annee", type=int)
    if annee_selectionnee not in annees_disponibles:
        annee_selectionnee = annees_disponibles[0]

    comptes = lister_comptes(connexion)
    comptes_suivis = [compte for compte in comptes if compte["statut"] == "suivi"]

    if "compte" in request.args:
        comptes_ids_selectionnes = request.args.getlist("compte")
    else:
        comptes_ids_selectionnes = [str(compte["id"]) for compte in comptes_suivis]

    donnees = obtenir_donnees_dashboard(
        connexion, annee_selectionnee, [int(identifiant) for identifiant in comptes_ids_selectionnes]
    )

    return render_template(
        "dashboard.html",
        donnees=donnees,
        donnees_json=json.dumps(donnees, ensure_ascii=False),
        annees_disponibles=annees_disponibles,
        annee_selectionnee=annee_selectionnee,
        comptes=comptes_suivis,
        comptes_ids_selectionnes=comptes_ids_selectionnes,
    )


@application_web.route("/operations")
def page_operations():
    """
    Page des opérations, filtrable et triable, regroupée par mois. Les
    filtres choisis sont mémorisés dans un cookie du navigateur, pour
    être proposés à nouveau la prochaine fois qu'on ouvre cette page
    (ex: en cliquant sur "Opérations" dans le menu, un autre jour).
    """
    connexion = obtenir_connexion()
    NOM_COOKIE_FILTRES = "filtres_operations"

    # Bouton "Réinitialiser" : on efface les filtres mémorisés et on repart à zéro
    if request.args.get("reset") == "1":
        reponse = redirect(url_for("page_operations"))
        reponse.delete_cookie(NOM_COOKIE_FILTRES)
        return reponse

    # Aucun filtre dans l'URL (arrivée "fraîche" sur la page), mais des
    # filtres avaient été mémorisés lors d'une visite précédente : on
    # les réapplique en redirigeant vers la même URL, filtres inclus.
    filtres_memorises = request.cookies.get(NOM_COOKIE_FILTRES)
    if not request.args and filtres_memorises:
        return redirect(f"{url_for('page_operations')}?{filtres_memorises}")

    aujourdhui = date.today()
    aucun_filtre_fourni = not request.args

    annees_disponibles = obtenir_annees_disponibles(connexion)
    if aucun_filtre_fourni:
        derniere_date = obtenir_derniere_date_operation(connexion)
        if derniere_date:
            annee_selectionnee, mois_selectionne = derniere_date.split("-")[:2]
            mois_selectionne = str(int(mois_selectionne))  # retire le zéro initial ("07" -> "7")
        else:
            annee_selectionnee = str(aujourdhui.year) if aujourdhui.year in annees_disponibles else "toutes"
            mois_selectionne = str(aujourdhui.month) if annee_selectionnee == str(aujourdhui.year) else "tous"
    else:
        annee_selectionnee = request.args.get("annee", "toutes")
        mois_selectionne = request.args.get("mois", "tous")

    tri_selectionne = request.args.get("tri", "date")

    comptes = lister_comptes(connexion)
    comptes_suivis = [compte for compte in comptes if compte["statut"] == "suivi"]
    categories = lister_categories(connexion)

    if aucun_filtre_fourni:
        comptes_ids_selectionnes = [str(compte["id"]) for compte in comptes_suivis]
        categories_valeurs_selectionnees = [str(categorie["id"]) for categorie in categories] + ["aucune"]
    else:
        comptes_ids_selectionnes = request.args.getlist("compte")
        categories_valeurs_selectionnees = request.args.getlist("categorie")

    groupes_mensuels = lister_operations_groupees_par_mois(
        connexion,
        annee_selectionnee,
        mois_selectionne,
        [int(identifiant) for identifiant in comptes_ids_selectionnes],
        categories_valeurs_selectionnees,
        tri_selectionne,
    )

    reponse = make_response(
        render_template(
            "operations.html",
            groupes_mensuels=groupes_mensuels,
            annees_disponibles=annees_disponibles,
            annee_selectionnee=annee_selectionnee,
            mois_selectionne=mois_selectionne,
            tri_selectionne=tri_selectionne,
            comptes=comptes_suivis,
            comptes_ids_selectionnes=comptes_ids_selectionnes,
            categories=categories,
            categories_valeurs_selectionnees=categories_valeurs_selectionnees,
            noms_mois=NOMS_MOIS,
        )
    )

    # On ne mémorise que les filtres explicitement choisis par l'utilisateur
    # (pas les valeurs par défaut calculées automatiquement), pour que ces
    # valeurs par défaut restent à jour si aucun filtre n'a jamais été choisi.
    if not aucun_filtre_fourni:
        reponse.set_cookie(NOM_COOKIE_FILTRES, request.query_string.decode(), max_age=60 * 60 * 24 * 365)

    return reponse


@application_web.route("/historique")
def page_historique():
    """Page listant l'historique complet des opérations, sans filtre."""
    connexion = obtenir_connexion()
    operations = lister_operations(connexion)
    return render_template("historique.html", operations=operations)


@application_web.route("/importer")
def page_import():
    """Page d'import : formulaires de dépôt d'un fichier bancaire."""
    return render_template("accueil.html")


@application_web.route("/importer", methods=["POST"])
def importer():
    """
    Reçoit le fichier déposé sur la page d'import (quelle que soit la
    zone de dépôt utilisée, Crédit Agricole ou Boursobank - le
    traitement est identique, seule l'extension du fichier détermine
    comment il est lu), l'importe en base de données, puis revient à
    la page d'import avec un ou plusieurs messages de résultat.
    """
    fichier_depose = request.files.get("fichier_operations")

    if fichier_depose is None or fichier_depose.filename == "":
        flash("Aucun fichier n'a été sélectionné.", "erreur")
        return redirect(url_for("page_import"))

    extension = os.path.splitext(fichier_depose.filename)[1]
    fichier_temporaire = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
    try:
        fichier_depose.save(fichier_temporaire.name)

        connexion = obtenir_connexion()
        rapport = importer_fichier_operations(
            connexion, fichier_temporaire.name, fichier_depose.filename
        )

        flash(
            f"Import terminé : {rapport.nb_operations_ajoutees} nouvelle(s) opération(s) "
            f"ajoutée(s), {rapport.nb_operations_deja_connues} déjà connue(s) (ignorée(s)).",
            "succes",
        )

        if rapport.comptes_nouveaux:
            flash(
                "Nouveau(x) compte(s) détecté(s) et suivi(s) automatiquement : "
                + ", ".join(sorted(rapport.comptes_nouveaux))
                + ". Tu peux les renommer ou choisir leur couleur depuis la page \"Comptes\".",
                "avertissement",
            )

        if rapport.comptes_ignores:
            flash(
                "Comptes ignorés (comme demandé) : " + ", ".join(sorted(rapport.comptes_ignores)),
                "avertissement",
            )
    except ValueError as erreur:
        flash(str(erreur), "erreur")
    finally:
        os.remove(fichier_temporaire.name)

    return redirect(url_for("page_import"))


@application_web.route("/comptes")
def page_comptes():
    """Page listant tous les comptes détectés, avec leur statut."""
    connexion = obtenir_connexion()
    comptes = lister_comptes(connexion)
    return render_template("comptes.html", comptes=comptes, palette_couleurs=PALETTE_COULEURS_COMPTES)


@application_web.route("/comptes/<int:compte_id>/modifier", methods=["POST"])
def modifier_compte_route(compte_id):
    """
    Met à jour le nom, la couleur et la lettre d'un compte, et applique
    un éventuel changement de statut (suivi <-> ignoré). Passer à
    "ignoré" supprime les opérations déjà importées de ce compte - la
    confirmation (avec le nombre d'opérations concernées) est faite
    côté navigateur avant l'envoi de cette requête.
    """
    nouveau_nom = request.form.get("nouveau_nom", "").strip()
    nouvelle_couleur = request.form.get("nouvelle_couleur", "").strip()
    nouvelle_lettre = request.form.get("nouvelle_lettre", "").strip()
    nouveau_statut = request.form.get("nouveau_statut", "").strip()

    if not nouveau_nom or not nouvelle_lettre:
        flash("Le nom et la lettre ne peuvent pas être vides.", "erreur")
        return redirect(url_for("page_comptes"))

    connexion = obtenir_connexion()
    modifier_compte(connexion, compte_id, nouveau_nom, nouvelle_couleur, nouvelle_lettre)

    statut_actuel = connexion.execute(
        "SELECT statut FROM comptes WHERE id = ?", (compte_id,)
    ).fetchone()["statut"]

    if nouveau_statut == "ignore" and statut_actuel != "ignore":
        nb_supprimees = ignorer_compte(connexion, compte_id)
        flash(f"Compte mis à jour et ignoré : {nb_supprimees} opération(s) supprimée(s).", "succes")
    elif nouveau_statut == "suivi" and statut_actuel != "suivi":
        reprendre_suivi_compte(connexion, compte_id)
        flash(
            "Compte mis à jour et de nouveau suivi. Réimporte un fichier pour récupérer ses opérations.",
            "succes",
        )
    else:
        flash("Compte mis à jour.", "succes")

    return redirect(url_for("page_comptes"))


@application_web.route("/categories")
def page_categories():
    """Page listant toutes les catégories, avec leurs correspondances et mots-clés."""
    connexion = obtenir_connexion()
    categories = lister_categories(connexion)

    correspondances_par_categorie = {
        categorie["id"]: obtenir_correspondances(connexion, categorie["id"]) for categorie in categories
    }
    mots_cles_par_categorie = {
        categorie["id"]: obtenir_mots_cles(connexion, categorie["id"]) for categorie in categories
    }

    return render_template(
        "categories.html",
        categories=categories,
        correspondances_par_categorie=correspondances_par_categorie,
        mots_cles_par_categorie=mots_cles_par_categorie,
        palette_couleurs=PALETTE_COULEURS_COMPTES,
    )


@application_web.route("/categories/<int:categorie_id>/modifier", methods=["POST"])
def modifier_categorie_route(categorie_id):
    """Met à jour le nom et la couleur d'une catégorie."""
    nouveau_nom = request.form.get("nouveau_nom", "").strip()
    nouvelle_couleur = request.form.get("nouvelle_couleur", "").strip()

    if not nouveau_nom:
        flash("Le nom ne peut pas être vide.", "erreur")
        return redirect(url_for("page_categories"))

    connexion = obtenir_connexion()
    modifier_categorie(connexion, categorie_id, nouveau_nom, nouvelle_couleur)
    flash("Catégorie mise à jour.", "succes")
    return redirect(url_for("page_categories"))


@application_web.route("/categories/<int:categorie_id>/mots-cles/ajouter", methods=["POST"])
def ajouter_mot_cle_route(categorie_id):
    """Ajoute un mot-clé d'attribution automatique à une catégorie."""
    mot_cle = request.form.get("mot_cle", "").strip()

    if not mot_cle:
        flash("Le mot-clé ne peut pas être vide.", "erreur")
        return redirect(url_for("page_categories"))

    connexion = obtenir_connexion()
    try:
        ajouter_mot_cle(connexion, categorie_id, mot_cle)
        flash(f'Mot-clé "{mot_cle}" ajouté. Il s\'appliquera aux prochains imports.', "succes")
    except ValueError as erreur:
        flash(str(erreur), "erreur")

    return redirect(url_for("page_categories"))


@application_web.route("/categories/<int:categorie_id>/mots-cles/<int:mot_cle_id>/supprimer", methods=["POST"])
def supprimer_mot_cle_route(categorie_id, mot_cle_id):
    """Supprime un mot-clé d'attribution automatique."""
    connexion = obtenir_connexion()
    supprimer_mot_cle(connexion, mot_cle_id)
    flash("Mot-clé supprimé.", "succes")
    return redirect(url_for("page_categories"))


@application_web.route("/categories/<int:categorie_id>/fusionner", methods=["POST"])
def fusionner_categories_route(categorie_id):
    """Fusionne une catégorie (la source) dans une autre (la cible choisie)."""
    categorie_cible_id = request.form.get("categorie_cible_id", "").strip()

    if not categorie_cible_id:
        flash("Choisis une catégorie cible pour la fusion.", "erreur")
        return redirect(url_for("page_categories"))

    connexion = obtenir_connexion()
    nb_operations = fusionner_categories(connexion, categorie_id, int(categorie_cible_id))
    flash(f"Catégories fusionnées : {nb_operations} opération(s) déplacée(s).", "succes")
    return redirect(url_for("page_categories"))


@application_web.route("/categories/<int:categorie_id>/supprimer", methods=["POST"])
def supprimer_categorie_route(categorie_id):
    """Supprime une catégorie ; ses opérations repassent 'Sans catégorie'."""
    connexion = obtenir_connexion()
    nb_operations = supprimer_categorie(connexion, categorie_id)
    flash(f"Catégorie supprimée : {nb_operations} opération(s) repassée(s) \"Sans catégorie\".", "succes")
    return redirect(url_for("page_categories"))


if __name__ == "__main__":
    application_web.run(host="0.0.0.0", port=8000)
