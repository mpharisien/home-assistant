"""
Application "Dépenses Courantes" - Point d'entrée principal.

Cette application web (Flask) permet de :
  1. Déposer un fichier d'export bancaire pour l'importer (page d'accueil)
  2. Consulter la liste des opérations déjà importées (page /operations)
  3. Gérer les comptes détectés : les valider, les ignorer, les renommer
     (page /comptes)

CE FICHIER PEUT AUSSI ÊTRE LANCÉ EN LOCAL SUR TON PC, SANS HOME ASSISTANT :
  1. Ouvrir un terminal dans le dossier depenses_courantes
  2. Installer les dépendances :  pip install -r app/requirements.txt
  3. Lancer l'application :       python -m app.main
  4. Ouvrir dans un navigateur :  http://localhost:8000
Dans ce cas, la base de données est créée sous forme d'un simple fichier
"depenses.db" dans le dossier courant (voir app/base_de_donnees/connexion.py).
"""

import os
import tempfile

from flask import Flask, flash, redirect, render_template, request, url_for

from app.base_de_donnees.connexion import obtenir_connexion
from app.base_de_donnees.consultation_operations import lister_operations
from app.base_de_donnees.gestion_comptes import (
    definir_statut_compte,
    lister_comptes,
    renommer_compte,
)
from app.operations.import_fichier import importer_fichier_operations

application_web = Flask(__name__)

# Nécessaire pour que Flask puisse afficher des messages temporaires
# (ex: "Import réussi") d'une page à l'autre. Cette application n'étant
# accessible que sur le réseau local de la maison (pas exposée sur
# Internet), une valeur fixe suffit tout à fait ici.
application_web.secret_key = "depenses-courantes-cle-locale"


@application_web.route("/")
def page_accueil():
    """Page d'accueil : formulaires de dépôt d'un fichier à importer."""
    return render_template("accueil.html")


@application_web.route("/importer", methods=["POST"])
def importer():
    """
    Reçoit le fichier déposé sur la page d'accueil (quelle que soit la
    zone de dépôt utilisée, Crédit Agricole ou Boursobank - le
    traitement est identique, seule l'extension du fichier détermine
    comment il est lu), l'importe en base de données, puis revient à
    l'accueil avec un ou plusieurs messages de résultat.
    """
    fichier_depose = request.files.get("fichier_operations")

    if fichier_depose is None or fichier_depose.filename == "":
        flash("Aucun fichier n'a été sélectionné.", "erreur")
        return redirect(url_for("page_accueil"))

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

        if rapport.comptes_en_attente:
            flash(
                "Nouveau(x) compte(s) détecté(s), en attente de validation : "
                + ", ".join(sorted(rapport.comptes_en_attente))
                + ". Rends-toi sur la page \"Comptes\" pour les valider (ou les ignorer) "
                "avant que leurs opérations soient importées.",
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

    return redirect(url_for("page_accueil"))


@application_web.route("/operations")
def page_operations():
    """Page listant toutes les opérations déjà importées."""
    connexion = obtenir_connexion()
    operations = lister_operations(connexion)
    return render_template("operations.html", operations=operations)


@application_web.route("/comptes")
def page_comptes():
    """Page listant tous les comptes détectés, avec leur statut."""
    connexion = obtenir_connexion()
    comptes = lister_comptes(connexion)
    return render_template("comptes.html", comptes=comptes)


@application_web.route("/comptes/<int:compte_id>/renommer", methods=["POST"])
def renommer_compte_route(compte_id):
    """Change le nom affiché d'un compte."""
    nouveau_nom = request.form.get("nouveau_nom", "").strip()
    if nouveau_nom:
        connexion = obtenir_connexion()
        renommer_compte(connexion, compte_id, nouveau_nom)
        flash("Compte renommé.", "succes")
    else:
        flash("Le nom ne peut pas être vide.", "erreur")
    return redirect(url_for("page_comptes"))


@application_web.route("/comptes/<int:compte_id>/statut", methods=["POST"])
def changer_statut_compte_route(compte_id):
    """Change le statut d'un compte (valider, ignorer, ou reprendre le suivi)."""
    nouveau_statut = request.form.get("nouveau_statut", "")
    connexion = obtenir_connexion()
    try:
        definir_statut_compte(connexion, compte_id, nouveau_statut)
        flash("Statut du compte mis à jour.", "succes")
    except ValueError as erreur:
        flash(str(erreur), "erreur")
    return redirect(url_for("page_comptes"))


if __name__ == "__main__":
    application_web.run(host="0.0.0.0", port=8000)
