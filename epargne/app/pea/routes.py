"""
Pages web du module PEA.

Chaque fonction décorée par @blueprint_pea.get / .post / .route correspond à
une adresse (URL). Elle lit la demande, appelle les calculs ou la base de
données, puis affiche une page HTML (dossier templates/pea) ou redirige.
"""

from collections import defaultdict

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import bourse_yahoo
from app.base_de_donnees import obtenir_connexion
from app.outils import aujourdhui, format_champ, lire_date, lire_nombre
from app.pea import calculs, donnees, import_csv
from app.reglages import TYPES_AVEC_ACTION, TYPES_MOUVEMENT_PEA

blueprint_pea = Blueprint("pea", __name__, url_prefix="/pea")

# Nombre maximal de messages d'erreur affichés d'un coup après une actualisation
# des cours (les messages sont stockés dans un cookie, dont la taille est limitée).
_MAX_MESSAGES_ERREUR = 5


def _adresse_de_retour(adresse: str | None, par_defaut: str) -> str:
    """N'accepte qu'une adresse interne au site (commençant par un seul « / »)."""
    if adresse and adresse.startswith("/") and not adresse.startswith("//"):
        return adresse
    return par_defaut


# ----------------------------------------------------------------------------
# Portefeuille
# ----------------------------------------------------------------------------

@blueprint_pea.get("/")
def portefeuille():
    return render_template(
        "pea/portefeuille.html",
        portefeuille=calculs.calculer_portefeuille(obtenir_connexion()),
    )


@blueprint_pea.post("/actualiser-cours")
def actualiser_cours():
    """Récupère les cours sur Yahoo pour une action (action_id) ou pour toutes."""
    connexion = obtenir_connexion()
    retour = _adresse_de_retour(request.form.get("retour"), url_for("pea.portefeuille"))
    action_id = request.form.get("action_id", type=int)

    toutes = donnees.lister_actions(connexion)
    if action_id is not None:
        concernees = [a for a in toutes if a["id"] == action_id]
    else:
        # Actions détenues ou suivies
        etat = calculs.rejouer_mouvements(donnees.lister_mouvements(connexion))
        concernees = [
            a for a in toutes
            if a["suivie"] or (a["id"] in etat.positions and etat.positions[a["id"]].detenue)
        ]
    avec_symbole = [a for a in concernees if a["ticker"]]
    sans_symbole = len(concernees) - len(avec_symbole)

    if not avec_symbole:
        flash("Aucune action avec un symbole Yahoo à mettre à jour.", "info")
        return redirect(retour)

    nb_reussites, erreurs = bourse_yahoo.actualiser_cours(connexion, avec_symbole)
    flash(f"Cours mis à jour : {nb_reussites} action(s) sur {len(avec_symbole)}.",
          "succes" if not erreurs else "info")
    if sans_symbole:
        flash(f"{sans_symbole} action(s) sans symbole Yahoo ignorée(s).", "info")
    for erreur in erreurs[:_MAX_MESSAGES_ERREUR]:
        flash(erreur, "erreur")
    if len(erreurs) > _MAX_MESSAGES_ERREUR:
        flash(f"… et {len(erreurs) - _MAX_MESSAGES_ERREUR} autre(s) erreur(s).", "erreur")
    return redirect(retour)


# ----------------------------------------------------------------------------
# Historique des mouvements
# ----------------------------------------------------------------------------

@blueprint_pea.get("/historique")
def historique():
    connexion = obtenir_connexion()
    tous = donnees.lister_mouvements(connexion)

    filtres = {
        "annee": request.args.get("annee", ""),
        "action": request.args.get("action", type=int),
        "type": request.args.get("type", ""),
    }
    mouvements = [
        m for m in reversed(tous)  # du plus récent au plus ancien
        if (not filtres["annee"] or m["date"].startswith(f"{filtres['annee']}-"))
        and (filtres["action"] is None or m["action_id"] == filtres["action"])
        and (not filtres["type"] or m["type"] == filtres["type"])
    ]
    return render_template(
        "pea/historique.html",
        mouvements=mouvements,
        nb_total=len(tous),
        annees=sorted({m["date"][:4] for m in tous}, reverse=True),
        actions=donnees.lister_actions(connexion),
        filtres=filtres,
    )


def _lire_formulaire_mouvement(formulaire) -> tuple[dict, list[str]]:
    """
    Lit et vérifie le formulaire d'un mouvement.
    Renvoie (mouvement prêt à enregistrer, liste des erreurs).
    """
    erreurs = []

    def nombre(champ: str, libelle: str) -> float | None:
        try:
            return lire_nombre(formulaire.get(champ))
        except ValueError as erreur:
            erreurs.append(f"{libelle} : {erreur}")
            return None

    type_mouvement = formulaire.get("type", "")
    if type_mouvement not in TYPES_MOUVEMENT_PEA:
        erreurs.append("Type de mouvement invalide.")
    try:
        date = lire_date(formulaire.get("date"))
    except ValueError as erreur:
        erreurs.append(f"Date : {erreur}")
        date = None

    avec_action = type_mouvement in TYPES_AVEC_ACTION
    achat_ou_vente = type_mouvement in ("achat", "vente")
    nom_action = (formulaire.get("action") or "").strip()
    quantite = nombre("quantite", "Nombre")
    cours = nombre("cours", "Cours")
    dividende_par_action = nombre("dividende_par_action", "Dividende par action")
    frais = nombre("frais", "Frais") or 0.0
    montant = nombre("montant", "Montant")

    if avec_action and not nom_action:
        erreurs.append("Indique l'action concernée.")
    if achat_ou_vente and (quantite is None or quantite <= 0):
        erreurs.append("Le nombre de titres doit être supérieur à 0.")
    if quantite is not None and quantite < 0:
        erreurs.append("Le nombre de titres ne peut pas être négatif.")
    if achat_ou_vente and frais < 0:
        erreurs.append("Les frais ne peuvent pas être négatifs.")

    # Montant non saisi : calcul automatique quand c'est possible
    if montant is None and not erreurs:
        if achat_ou_vente and cours is not None:
            montant = quantite * cours + (frais if type_mouvement == "achat" else -frais)
        elif type_mouvement == "dividende" and quantite and dividende_par_action is not None:
            montant = quantite * dividende_par_action
        else:
            erreurs.append("Indique le montant (ou les éléments permettant de le calculer).")
    if montant is not None and montant <= 0:
        erreurs.append("Le montant doit être supérieur à 0.")

    mouvement = {
        "date": date,
        "type": type_mouvement,
        "nom_action": nom_action if avec_action else None,
        "quantite": quantite if avec_action else None,
        "cours": cours if achat_ou_vente else None,
        "frais": frais if achat_ou_vente else 0.0,
        "montant": round(montant, 2) if montant is not None else None,
        "commentaire": (formulaire.get("commentaire") or "").strip() or None,
    }
    return mouvement, erreurs


def _enregistrer_mouvement(connexion, mouvement: dict, mouvement_id: int | None = None) -> None:
    """Crée l'action si besoin, puis ajoute ou modifie le mouvement."""
    nom_action = mouvement.pop("nom_action")
    try:
        mouvement["action_id"] = None
        if nom_action:
            action = donnees.trouver_action_par_nom(connexion, nom_action)
            if action is None:
                mouvement["action_id"] = donnees.creer_action(connexion, nom_action, suivie=False)
                flash(f"Action « {nom_action} » créée : pense à renseigner son symbole Yahoo "
                      "(menu Actions à rendement) pour obtenir son cours.", "info")
            else:
                mouvement["action_id"] = action["id"]
        if mouvement_id is None:
            donnees.inserer_mouvement(connexion, mouvement)
        else:
            donnees.modifier_mouvement(connexion, mouvement_id, mouvement)
        connexion.commit()
    except Exception:
        connexion.rollback()
        raise


@blueprint_pea.route("/mouvements/nouveau", methods=["GET", "POST"])
def nouveau_mouvement():
    connexion = obtenir_connexion()
    if request.method == "POST":
        mouvement, erreurs = _lire_formulaire_mouvement(request.form)
        if not erreurs:
            _enregistrer_mouvement(connexion, mouvement)
            flash("Mouvement enregistré.", "succes")
            if request.form.get("continuer"):
                # « Enregistrer et saisir un autre » : on garde la date et le type
                return redirect(url_for("pea.nouveau_mouvement",
                                        date=mouvement["date"], type=mouvement["type"]))
            return redirect(url_for("pea.historique"))
        for erreur in erreurs:
            flash(erreur, "erreur")
        valeurs = request.form
    else:
        valeurs = {
            "date": request.args.get("date") or aujourdhui().isoformat(),
            "type": request.args.get("type", "achat"),
        }
    return render_template("pea/mouvement_form.html", valeurs=valeurs, mouvement_id=None,
                           actions=donnees.lister_actions(connexion))


@blueprint_pea.route("/mouvements/<int:mouvement_id>/modifier", methods=["GET", "POST"])
def modifier_mouvement(mouvement_id: int):
    connexion = obtenir_connexion()
    existant = donnees.obtenir_mouvement(connexion, mouvement_id)
    if existant is None:
        abort(404)

    if request.method == "POST":
        mouvement, erreurs = _lire_formulaire_mouvement(request.form)
        if not erreurs:
            _enregistrer_mouvement(connexion, mouvement, mouvement_id)
            flash("Mouvement modifié.", "succes")
            return redirect(url_for("pea.historique"))
        for erreur in erreurs:
            flash(erreur, "erreur")
        valeurs = request.form
    else:
        valeurs = {
            "date": existant["date"],
            "type": existant["type"],
            "action": existant["nom_action"] or "",
            "quantite": format_champ(existant["quantite"]),
            "cours": format_champ(existant["cours"]),
            "frais": format_champ(existant["frais"]) if existant["frais"] else "",
            "montant": format_champ(existant["montant"]),
            "commentaire": existant["commentaire"] or "",
        }
    return render_template("pea/mouvement_form.html", valeurs=valeurs, mouvement_id=mouvement_id,
                           actions=donnees.lister_actions(connexion))


@blueprint_pea.post("/mouvements/<int:mouvement_id>/supprimer")
def supprimer_mouvement(mouvement_id: int):
    connexion = obtenir_connexion()
    donnees.supprimer_mouvement(connexion, mouvement_id)
    connexion.commit()
    flash("Mouvement supprimé.", "succes")
    return redirect(url_for("pea.historique"))


# ----------------------------------------------------------------------------
# Dividendes reçus
# ----------------------------------------------------------------------------

@blueprint_pea.get("/dividendes")
def dividendes():
    annees = calculs.calculer_dividendes_par_annee(obtenir_connexion())
    chronologique = list(reversed(annees))
    graphique = {
        "libelles": [str(a.annee) for a in chronologique],
        "valeurs": [round(a.total_dividendes, 2) for a in chronologique],
        "serie": "Dividendes reçus",
    }
    return render_template("pea/dividendes.html", annees=annees, graphique=graphique)


# ----------------------------------------------------------------------------
# Actions à rendement
# ----------------------------------------------------------------------------

@blueprint_pea.get("/actions")
def actions():
    annee = aujourdhui().year
    lignes = calculs.calculer_tableau_actions(obtenir_connexion(), annee)
    dates_maj = [l.cours["date_maj"] for l in lignes if l.cours and l.cours["date_maj"]]
    return render_template(
        "pea/actions.html",
        lignes=lignes,
        annees=calculs.annees_affichees(annee),
        annees_moyenne=calculs.annees_moyenne(annee),
        date_maj_cours=min(dates_maj) if dates_maj else None,
    )


@blueprint_pea.route("/actions/nouvelle", methods=["GET", "POST"])
def nouvelle_action():
    return _formulaire_action(None)


@blueprint_pea.route("/actions/<int:action_id>", methods=["GET", "POST"])
def modifier_action(action_id: int):
    return _formulaire_action(action_id)


def _formulaire_action(action_id: int | None):
    """Affiche et traite le formulaire d'une action (création si action_id est None)."""
    connexion = obtenir_connexion()
    action = None
    if action_id is not None:
        action = donnees.obtenir_action(connexion, action_id)
        if action is None:
            abort(404)

    dividendes_enregistres = (
        donnees.lire_dividendes_exercice(connexion).get(action_id, {}) if action_id else {}
    )
    # Années proposées : celles du tableau + celles déjà renseignées
    annees = sorted(set(calculs.annees_affichees(aujourdhui().year)) | set(dividendes_enregistres))

    if request.method == "POST":
        erreurs = []
        nom = (request.form.get("nom") or "").strip()
        ticker = (request.form.get("ticker") or "").strip().upper() or None
        suivie = "suivie" in request.form
        en_evidence = "en_evidence" in request.form
        notes = (request.form.get("notes") or "").strip() or None

        if not nom:
            erreurs.append("Le nom de l'action est obligatoire.")
        else:
            homonyme = donnees.trouver_action_par_nom(connexion, nom)
            if homonyme is not None and homonyme["id"] != action_id:
                erreurs.append(f"Une action nommée « {homonyme['nom']} » existe déjà.")

        dividendes_saisis = {}
        for annee in annees:
            try:
                montant = lire_nombre(request.form.get(f"dividende_{annee}"))
            except ValueError as erreur:
                erreurs.append(f"Dividende {annee} : {erreur}")
                continue
            if montant is not None and montant < 0:
                erreurs.append(f"Dividende {annee} : le montant ne peut pas être négatif.")
                continue
            dividendes_saisis[annee] = montant

        if not erreurs:
            try:
                if action_id is None:
                    action_id = donnees.creer_action(connexion, nom, ticker, suivie, en_evidence, notes)
                else:
                    donnees.modifier_action(connexion, action_id, nom, ticker, suivie, en_evidence, notes)
                for annee, montant in dividendes_saisis.items():
                    donnees.enregistrer_dividende_exercice(connexion, action_id, annee, montant)
                connexion.commit()
            except Exception:
                connexion.rollback()
                raise
            flash(f"Action « {nom} » enregistrée.", "succes")
            return redirect(url_for("pea.actions"))

        for erreur in erreurs:
            flash(erreur, "erreur")
        valeurs = request.form
    elif action is not None:
        valeurs = {
            "nom": action["nom"],
            "ticker": action["ticker"] or "",
            "suivie": action["suivie"],
            "en_evidence": action["en_evidence"],
            "notes": action["notes"] or "",
        }
        for annee in annees:
            valeurs[f"dividende_{annee}"] = format_champ(dividendes_enregistres.get(annee))
    else:
        valeurs = {"suivie": True}

    # Informations Yahoo affichées pour aider à remplir les dividendes
    cours = None
    detaches_par_annee = {}
    nb_mouvements = 0
    if action is not None:
        cours = donnees.lire_cours(connexion).get(action["id"])
        regroupement = defaultdict(list)
        for ligne in donnees.lire_dividendes_detaches(connexion, action["id"]):
            regroupement[int(ligne["date"][:4])].append(ligne)
        detaches_par_annee = dict(sorted(regroupement.items(), reverse=True))
        nb_mouvements = donnees.compter_mouvements_action(connexion, action["id"])

    return render_template(
        "pea/action_form.html",
        action=action,
        valeurs=valeurs,
        annees=annees,
        cours=cours,
        detaches_par_annee=detaches_par_annee,
        nb_mouvements=nb_mouvements,
    )


@blueprint_pea.post("/actions/<int:action_id>/supprimer")
def supprimer_action(action_id: int):
    connexion = obtenir_connexion()
    action = donnees.obtenir_action(connexion, action_id)
    if action is None:
        abort(404)
    if donnees.compter_mouvements_action(connexion, action_id):
        flash("Impossible de supprimer une action qui a des mouvements dans l'historique.", "erreur")
        return redirect(url_for("pea.modifier_action", action_id=action_id))
    donnees.supprimer_action(connexion, action_id)
    connexion.commit()
    flash(f"Action « {action['nom']} » supprimée.", "succes")
    return redirect(url_for("pea.actions"))


# ----------------------------------------------------------------------------
# Import CSV
# ----------------------------------------------------------------------------

def _page_import(erreurs: list[str] | None = None, titre_erreurs: str | None = None):
    nb_mouvements = len(donnees.lister_mouvements(obtenir_connexion()))
    return render_template("pea/import.html", nb_mouvements=nb_mouvements,
                           erreurs=erreurs or [], titre_erreurs=titre_erreurs)


@blueprint_pea.get("/import")
def page_import():
    return _page_import()


def _contenu_fichier_envoye() -> bytes | None:
    fichier = request.files.get("fichier")
    if fichier is None or not fichier.filename:
        flash("Choisis un fichier CSV à importer.", "erreur")
        return None
    return fichier.read()


@blueprint_pea.post("/import/mouvements")
def importer_mouvements():
    contenu = _contenu_fichier_envoye()
    if contenu is None:
        return redirect(url_for("pea.page_import"))
    resultat = import_csv.importer_mouvements(
        obtenir_connexion(), contenu, remplacer="remplacer" in request.form
    )
    if resultat.erreurs:
        return _page_import(resultat.erreurs, "Import des mouvements annulé : rien n'a été enregistré.")
    flash(f"{resultat.nb_lignes} mouvement(s) importé(s).", "succes")
    if resultat.actions_creees:
        flash(f"{len(resultat.actions_creees)} action(s) créée(s) : "
              f"{', '.join(resultat.actions_creees)}. Pense à renseigner leur symbole Yahoo.", "info")
    return redirect(url_for("pea.historique"))


@blueprint_pea.post("/import/actions")
def importer_actions():
    contenu = _contenu_fichier_envoye()
    if contenu is None:
        return redirect(url_for("pea.page_import"))
    resultat = import_csv.importer_actions(obtenir_connexion(), contenu)
    if resultat.erreurs:
        return _page_import(resultat.erreurs, "Import des actions annulé : rien n'a été enregistré.")
    flash(f"{resultat.nb_lignes} action(s) importée(s), dont {len(resultat.actions_creees)} "
          "nouvelle(s).", "succes")
    return redirect(url_for("pea.actions"))
