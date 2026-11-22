"""
Pages web des poches simples (Epsor, Enerfip...).

L'adresse contient le code de la poche : /poche/epsor, /poche/enerfip...
Le code doit exister dans reglages.POCHES, sinon la page « introuvable » s'affiche.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.base_de_donnees import obtenir_connexion
from app.outils import aujourdhui, format_champ, lire_date, lire_nombre
from app.poches.calculs import resumer_poche
from app.reglages import POCHES

blueprint_poches = Blueprint("poches", __name__, url_prefix="/poche")


def _verifier_poche(code: str) -> dict:
    if code not in POCHES:
        abort(404)
    return POCHES[code]


def _lire_formulaire_mouvement(code: str, formulaire) -> tuple[dict, list[str]]:
    """Lit et vérifie le formulaire. Renvoie (mouvement, liste des erreurs)."""
    erreurs = []
    type_mouvement = formulaire.get("type", "")
    if type_mouvement not in POCHES[code]["types"]:
        erreurs.append("Type de mouvement invalide.")
    try:
        date = lire_date(formulaire.get("date"))
    except ValueError as erreur:
        erreurs.append(f"Date : {erreur}")
        date = None
    try:
        montant = lire_nombre(formulaire.get("montant"))
    except ValueError as erreur:
        erreurs.append(f"Montant : {erreur}")
        montant = None
    else:
        # Le montant 0 est accepté (ex. arbitrage noté pour mémoire)
        if montant is None or montant < 0:
            erreurs.append("Le montant doit être un nombre positif.")

    mouvement = {
        "poche": code,
        "date": date,
        "type": type_mouvement,
        "libelle": (formulaire.get("libelle") or "").strip() or None,
        "montant": round(montant, 2) if montant is not None else None,
        "commentaire": (formulaire.get("commentaire") or "").strip() or None,
    }
    return mouvement, erreurs


def _libelles_existants(connexion, code: str) -> list[str]:
    """Libellés déjà utilisés (fonds, projets), proposés à la saisie."""
    lignes = connexion.execute(
        "SELECT DISTINCT libelle FROM poche_mouvements "
        "WHERE poche = ? AND libelle IS NOT NULL ORDER BY libelle",
        (code,),
    ).fetchall()
    return [ligne["libelle"] for ligne in lignes]


# ----------------------------------------------------------------------------
# Page principale d'une poche
# ----------------------------------------------------------------------------

@blueprint_poches.get("/<code>")
def page_poche(code: str):
    _verifier_poche(code)
    return render_template(
        "poches/poche.html",
        resume=resumer_poche(obtenir_connexion(), code),
        date_du_jour=aujourdhui().isoformat(),
    )


# ----------------------------------------------------------------------------
# Mouvements
# ----------------------------------------------------------------------------

@blueprint_poches.route("/<code>/mouvements/nouveau", methods=["GET", "POST"])
def nouveau_mouvement(code: str):
    definition = _verifier_poche(code)
    connexion = obtenir_connexion()
    if request.method == "POST":
        mouvement, erreurs = _lire_formulaire_mouvement(code, request.form)
        if not erreurs:
            connexion.execute(
                "INSERT INTO poche_mouvements (poche, date, type, libelle, montant, commentaire) "
                "VALUES (:poche, :date, :type, :libelle, :montant, :commentaire)",
                mouvement,
            )
            connexion.commit()
            flash("Mouvement enregistré.", "succes")
            return redirect(url_for("poches.page_poche", code=code))
        for erreur in erreurs:
            flash(erreur, "erreur")
        valeurs = request.form
    else:
        valeurs = {"date": aujourdhui().isoformat()}
    return render_template("poches/mouvement_form.html", code=code, definition=definition,
                           valeurs=valeurs, mouvement_id=None,
                           libelles=_libelles_existants(connexion, code))


@blueprint_poches.route("/<code>/mouvements/<int:mouvement_id>/modifier", methods=["GET", "POST"])
def modifier_mouvement(code: str, mouvement_id: int):
    definition = _verifier_poche(code)
    connexion = obtenir_connexion()
    existant = connexion.execute(
        "SELECT * FROM poche_mouvements WHERE id = ? AND poche = ?", (mouvement_id, code)
    ).fetchone()
    if existant is None:
        abort(404)

    if request.method == "POST":
        mouvement, erreurs = _lire_formulaire_mouvement(code, request.form)
        if not erreurs:
            connexion.execute(
                "UPDATE poche_mouvements SET date = :date, type = :type, libelle = :libelle, "
                "montant = :montant, commentaire = :commentaire WHERE id = :id",
                {**mouvement, "id": mouvement_id},
            )
            connexion.commit()
            flash("Mouvement modifié.", "succes")
            return redirect(url_for("poches.page_poche", code=code))
        for erreur in erreurs:
            flash(erreur, "erreur")
        valeurs = request.form
    else:
        valeurs = {
            "date": existant["date"],
            "type": existant["type"],
            "libelle": existant["libelle"] or "",
            "montant": format_champ(existant["montant"]),
            "commentaire": existant["commentaire"] or "",
        }
    return render_template("poches/mouvement_form.html", code=code, definition=definition,
                           valeurs=valeurs, mouvement_id=mouvement_id,
                           libelles=_libelles_existants(connexion, code))


@blueprint_poches.post("/<code>/mouvements/<int:mouvement_id>/supprimer")
def supprimer_mouvement(code: str, mouvement_id: int):
    _verifier_poche(code)
    connexion = obtenir_connexion()
    connexion.execute("DELETE FROM poche_mouvements WHERE id = ? AND poche = ?", (mouvement_id, code))
    connexion.commit()
    flash("Mouvement supprimé.", "succes")
    return redirect(url_for("poches.page_poche", code=code))


# ----------------------------------------------------------------------------
# Valorisations
# ----------------------------------------------------------------------------

@blueprint_poches.post("/<code>/valorisations")
def ajouter_valorisation(code: str):
    _verifier_poche(code)
    try:
        date = lire_date(request.form.get("date"))
        valeur = lire_nombre(request.form.get("valeur"))
        if valeur is None or valeur < 0:
            raise ValueError("la valeur doit être un nombre positif.")
    except ValueError as erreur:
        flash(f"Valorisation non enregistrée : {erreur}", "erreur")
        return redirect(url_for("poches.page_poche", code=code))

    connexion = obtenir_connexion()
    # Une seule valorisation par date : une nouvelle saisie remplace l'ancienne
    connexion.execute(
        "INSERT INTO poche_valorisations (poche, date, valeur) VALUES (?, ?, ?) "
        "ON CONFLICT (poche, date) DO UPDATE SET valeur = excluded.valeur",
        (code, date, round(valeur, 2)),
    )
    connexion.commit()
    flash("Valorisation enregistrée.", "succes")
    return redirect(url_for("poches.page_poche", code=code))


@blueprint_poches.post("/<code>/valorisations/<int:valorisation_id>/supprimer")
def supprimer_valorisation(code: str, valorisation_id: int):
    _verifier_poche(code)
    connexion = obtenir_connexion()
    connexion.execute(
        "DELETE FROM poche_valorisations WHERE id = ? AND poche = ?", (valorisation_id, code)
    )
    connexion.commit()
    flash("Valorisation supprimée.", "succes")
    return redirect(url_for("poches.page_poche", code=code))
