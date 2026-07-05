"""
Application "Dépenses Courantes" - Point d'entrée principal.

Cette application web (Flask) permet de :
  1. Déposer un fichier d'export bancaire pour l'importer (page d'accueil)
  2. Consulter la liste des opérations déjà importées (page /operations)

CE FICHIER PEUT AUSSI ÊTRE LANCÉ EN LOCAL SUR TON PC, SANS HOME ASSISTANT :
  1. Ouvrir un terminal dans le dossier depenses_courantes
  2. Installer les dépendances :  pip install -r app/requirements.txt
  3. Lancer l'application :       python app/main.py
  4. Ouvrir dans un navigateur :  http://localhost:8000
Dans ce cas, la base de données est créée sous forme d'un simple fichier
"depenses.db" dans le dossier courant (voir app/base_de_donnees/connexion.py).
"""

import os
import tempfile

from flask import Flask, flash, redirect, render_template, request, url_for

from app.base_de_donnees.connexion import obtenir_connexion
from app.base_de_donnees.consultation_operations import lister_operations
from app.operations.import_fichier import importer_fichier_operations

application_web = Flask(__name__)

# Nécessaire pour que Flask puisse afficher des messages temporaires
# (ex: "Import réussi") d'une page à l'autre. Cette application n'étant
# accessible que sur le réseau local de la maison (pas exposée sur
# Internet), une valeur fixe suffit tout à fait ici.
application_web.secret_key = "depenses-courantes-cle-locale"


@application_web.route("/")
def page_accueil():
    """Page d'accueil : formulaire de dépôt d'un fichier à importer."""
    return render_template("accueil.html")


@application_web.route("/importer", methods=["POST"])
def importer():
    """
    Reçoit le fichier déposé sur la page d'accueil, l'importe en base
    de données, puis revient à l'accueil avec un message de résultat.
    """
    fichier_depose = request.files.get("fichier_operations")

    if fichier_depose is None or fichier_depose.filename == "":
        flash("Aucun fichier n'a été sélectionné.", "erreur")
        return redirect(url_for("page_accueil"))

    # On enregistre temporairement le fichier sur le disque le temps de
    # le lire (nos lecteurs travaillent à partir d'un chemin de fichier).
    extension = os.path.splitext(fichier_depose.filename)[1]
    fichier_temporaire = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
    try:
        fichier_depose.save(fichier_temporaire.name)

        connexion = obtenir_connexion()
        resultat = importer_fichier_operations(
            connexion, fichier_temporaire.name, fichier_depose.filename
        )

        flash(
            f"Import terminé : {resultat.nb_operations_ajoutees} nouvelle(s) opération(s) "
            f"ajoutée(s), {resultat.nb_operations_deja_connues} déjà connue(s) (ignorée(s)).",
            "succes",
        )
    except ValueError as erreur:
        # Erreur "attendue" (format non reconnu, compte inconnu...) :
        # on l'affiche telle quelle, elle est déjà écrite pour l'utilisateur.
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


if __name__ == "__main__":
    application_web.run(host="0.0.0.0", port=8000)
