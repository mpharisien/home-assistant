"""
Application "Dépenses Courantes" - Point d'entrée principal.

Cette application web (Flask) permet de :
  1. Déposer un fichier d'export bancaire pour l'importer (page d'accueil)
  2. Consulter la liste des opérations déjà importées (page /operations)
  3. Gérer les comptes détectés : les ignorer, reprendre leur suivi,
     changer leur nom/couleur/lettre (page /comptes)

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
    PALETTE_COULEURS_COMPTES,
    ignorer_compte,
    lister_comptes,
    modifier_compte,
    reprendre_suivi_compte,
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
    return render_template("comptes.html", comptes=comptes, palette_couleurs=PALETTE_COULEURS_COMPTES)


@application_web.route("/comptes/<int:compte_id>/modifier", methods=["POST"])
def modifier_compte_route(compte_id):
    """Met à jour en une fois le nom, la couleur et la lettre d'un compte."""
    nouveau_nom = request.form.get("nouveau_nom", "").strip()
    nouvelle_couleur = request.form.get("nouvelle_couleur", "").strip()
    nouvelle_lettre = request.form.get("nouvelle_lettre", "").strip()

    if not nouveau_nom or not nouvelle_lettre:
        flash("Le nom et la lettre ne peuvent pas être vides.", "erreur")
        return redirect(url_for("page_comptes"))

    connexion = obtenir_connexion()
    modifier_compte(connexion, compte_id, nouveau_nom, nouvelle_couleur, nouvelle_lettre)
    flash("Compte mis à jour.", "succes")
    return redirect(url_for("page_comptes"))


@application_web.route("/comptes/<int:compte_id>/ignorer", methods=["POST"])
def ignorer_compte_route(compte_id):
    """
    Met un compte de côté : supprime ses opérations déjà importées et
    empêche toute nouvelle importation tant qu'il reste ignoré. La
    confirmation (avec le nombre d'opérations concernées) est faite
    côté navigateur avant l'envoi de cette requête.
    """
    connexion = obtenir_connexion()
    nb_supprimees = ignorer_compte(connexion, compte_id)
    flash(f"Compte ignoré : {nb_supprimees} opération(s) supprimée(s).", "succes")
    return redirect(url_for("page_comptes"))


@application_web.route("/comptes/<int:compte_id>/reprendre-le-suivi", methods=["POST"])
def reprendre_suivi_compte_route(compte_id):
    """Remet un compte ignoré en suivi (ne restaure pas ses anciennes opérations)."""
    connexion = obtenir_connexion()
    reprendre_suivi_compte(connexion, compte_id)
    flash("Compte de nouveau suivi. Réimporte un fichier pour récupérer ses opérations.", "succes")
    return redirect(url_for("page_comptes"))


if __name__ == "__main__":
    application_web.run(host="0.0.0.0", port=8000)
