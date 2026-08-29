from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "carnet-de-sante-secret-2026"
DB_PATH = "/share/carnet_de_sante/carnet_de_sante.db"

# Liste des examens pré-remplis au premier démarrage (nom, fréquence en mois, description).
# Basée sur les recommandations générales de suivi médical (hors examens spécifiques au sexe).
EXAMENS_PAR_DEFAUT = [
    ("Médecin généraliste", 12, "Tension, auscultation, poids, bilan général"),
    ("Dentiste", 12, "Détartrage, vérification des caries, santé des gencives"),
    ("Bilan sanguin complet", 36, "Numération, créatinine, glycémie, cholestérol (LDL/HDL/triglycérides)"),
    ("Ophtalmologue", 36, "Contrôle de la vue ; dépistage glaucome recommandé dès 40 ans, DMLA annuelle dès 55 ans"),
    ("Dermatologue", 12, "Contrôle des grains de beauté / dépistage des cancers de la peau"),
    ("Podologue", 12, "Prévention des douleurs articulaires liées aux pieds"),
    ("Tension artérielle", 12, "Dépistage de l'hypertension, recommandé dès 30 ans"),
    ("Dépistage cancer colorectal (test FIT)", 24, "Kit à faire chez soi, recommandé de 50 à 74 ans"),
]


# ──────────────────────────────────────────────
# BASE DE DONNÉES
# ──────────────────────────────────────────────
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    connexion = sqlite3.connect(DB_PATH)
    connexion.row_factory = sqlite3.Row
    connexion.execute("PRAGMA foreign_keys = ON")
    return connexion


def init_db():
    connexion = get_db()

    connexion.execute("""CREATE TABLE IF NOT EXISTS individu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prenom TEXT NOT NULL,
        nom TEXT,
        date_naissance TEXT,
        heure_naissance TEXT,
        groupe_sanguin TEXT,
        lieu_naissance TEXT,
        allergies TEXT,
        antecedents TEXT,
        diagnostics TEXT,
        photo TEXT)""")

    connexion.execute("""CREATE TABLE IF NOT EXISTS individu_actif (
        id INTEGER PRIMARY KEY,
        individu_id INTEGER)""")
    connexion.execute("INSERT OR IGNORE INTO individu_actif (id, individu_id) VALUES (1, NULL)")

    connexion.execute("""CREATE TABLE IF NOT EXISTS poids (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        individu_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        poids REAL NOT NULL,
        notes TEXT)""")

    connexion.execute("""CREATE TABLE IF NOT EXISTS taille (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        individu_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        taille REAL NOT NULL,
        notes TEXT)""")

    connexion.execute("""CREATE TABLE IF NOT EXISTS dents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        individu_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        dent TEXT NOT NULL,
        notes TEXT)""")

    connexion.execute("""CREATE TABLE IF NOT EXISTS type_examen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL UNIQUE,
        frequence_mois INTEGER,
        description TEXT)""")

    connexion.execute("""CREATE TABLE IF NOT EXISTS suivi_examen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        individu_id INTEGER NOT NULL,
        type_examen_id INTEGER NOT NULL,
        derniere_date TEXT,
        UNIQUE(individu_id, type_examen_id))""")

    connexion.execute("""CREATE TABLE IF NOT EXISTS evenement (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        individu_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        titre TEXT NOT NULL,
        description TEXT)""")

    for nom, frequence_mois, description in EXAMENS_PAR_DEFAUT:
        connexion.execute(
            "INSERT OR IGNORE INTO type_examen (nom, frequence_mois, description) VALUES (?, ?, ?)",
            (nom, frequence_mois, description)
        )

    connexion.commit()
    connexion.close()


# ──────────────────────────────────────────────
# FORMATAGE
# ──────────────────────────────────────────────
def formater_date_affichage(date_iso):
    """Convertit une date stockée en YYYY-MM-DD vers un affichage JJ-MM-AAAA."""
    if not date_iso:
        return None
    try:
        return datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return date_iso


def formater_frequence_mois(mois):
    """Transforme une fréquence stockée en mois en texte lisible
    (ex: 12 -> 'Tous les ans', 36 -> 'Tous les 3 ans', 5 -> 'Tous les 5 mois')."""
    if mois is None:
        return "—"
    if mois % 12 == 0:
        annees = mois // 12
        return "Tous les ans" if annees == 1 else f"Tous les {annees} ans"
    return f"Tous les {mois} mois"


@app.template_filter("frequence")
def filtre_frequence(mois):
    return formater_frequence_mois(mois)


# ──────────────────────────────────────────────
# GESTION DE L'INDIVIDU ACTIF
# ──────────────────────────────────────────────
def obtenir_individu_actif_id(connexion):
    """Retourne l'id de l'individu actuellement affiché, en réparant
    automatiquement la référence si elle est absente ou invalide
    (par exemple après la suppression du profil actif)."""
    ligne = connexion.execute(
        "SELECT individu_id FROM individu_actif WHERE id = 1"
    ).fetchone()
    individu_id = ligne["individu_id"] if ligne else None

    if individu_id is not None:
        existe = connexion.execute(
            "SELECT id FROM individu WHERE id = ?", (individu_id,)
        ).fetchone()
        if existe:
            return individu_id

    premier_individu = connexion.execute(
        "SELECT id FROM individu ORDER BY id ASC LIMIT 1"
    ).fetchone()
    nouvel_id = premier_individu["id"] if premier_individu else None
    connexion.execute(
        "UPDATE individu_actif SET individu_id = ? WHERE id = 1", (nouvel_id,)
    )
    connexion.commit()
    return nouvel_id


def assurer_suivi_examen_complet(connexion, individu_id):
    """Crée les lignes de suivi manquantes pour un individu, une par type
    d'examen existant, afin que le tableau des examens soit toujours
    complet même après l'ajout d'un nouveau type ou d'un nouvel individu."""
    types_examen = connexion.execute("SELECT id FROM type_examen").fetchall()
    for type_examen in types_examen:
        connexion.execute(
            """INSERT OR IGNORE INTO suivi_examen (individu_id, type_examen_id, derniere_date)
               VALUES (?, ?, NULL)""",
            (individu_id, type_examen["id"])
        )
    connexion.commit()


@app.context_processor
def injecter_contexte_individu():
    connexion = get_db()
    individu_actif_id = obtenir_individu_actif_id(connexion)
    individu_actif = None
    if individu_actif_id:
        individu_actif = connexion.execute(
            "SELECT * FROM individu WHERE id = ?", (individu_actif_id,)
        ).fetchone()
    liste_individus = connexion.execute(
        "SELECT id, prenom, nom FROM individu ORDER BY prenom ASC"
    ).fetchall()
    connexion.close()
    return dict(individu_actif=individu_actif, liste_individus=liste_individus)


# ──────────────────────────────────────────────
# ACCUEIL
# ──────────────────────────────────────────────
@app.route("/")
def index():
    connexion = get_db()
    individu_actif_id = obtenir_individu_actif_id(connexion)

    imc = None
    dernier_poids = None
    derniere_taille = None
    date_dernier_poids = None
    date_derniere_taille = None
    derniers_evenements = []

    if individu_actif_id:
        ligne_poids = connexion.execute(
            "SELECT date, poids FROM poids WHERE individu_id = ? ORDER BY date DESC, id DESC LIMIT 1",
            (individu_actif_id,)
        ).fetchone()
        ligne_taille = connexion.execute(
            "SELECT date, taille FROM taille WHERE individu_id = ? ORDER BY date DESC, id DESC LIMIT 1",
            (individu_actif_id,)
        ).fetchone()

        if ligne_poids:
            dernier_poids = ligne_poids["poids"]
            date_dernier_poids = formater_date_affichage(ligne_poids["date"])
        if ligne_taille:
            derniere_taille = ligne_taille["taille"]
            date_derniere_taille = formater_date_affichage(ligne_taille["date"])

        if dernier_poids and derniere_taille and derniere_taille > 0:
            taille_en_metres = derniere_taille / 100
            imc = round(dernier_poids / (taille_en_metres ** 2), 1)

        derniers_evenements = connexion.execute(
            "SELECT * FROM evenement WHERE individu_id = ? ORDER BY date DESC, id DESC LIMIT 5",
            (individu_actif_id,)
        ).fetchall()

    connexion.close()
    return render_template(
        "index.html",
        imc=imc,
        dernier_poids=dernier_poids,
        derniere_taille=derniere_taille,
        date_dernier_poids=date_dernier_poids,
        date_derniere_taille=date_derniere_taille,
        derniers_evenements=derniers_evenements
    )


# ──────────────────────────────────────────────
# FICHE INDIVIDU
# ──────────────────────────────────────────────
@app.route("/individu", methods=["GET", "POST"])
def individu():
    connexion = get_db()
    individu_actif_id = obtenir_individu_actif_id(connexion)

    if request.method == "POST" and individu_actif_id:
        connexion.execute(
            """UPDATE individu SET prenom=?, nom=?, date_naissance=?, heure_naissance=?,
               groupe_sanguin=?, lieu_naissance=?, allergies=?, antecedents=?, diagnostics=? WHERE id=?""",
            (request.form.get("prenom", "").strip(),
             request.form.get("nom", "").strip(),
             request.form.get("date_naissance") or None,
             request.form.get("heure_naissance") or None,
             request.form.get("groupe_sanguin") or None,
             request.form.get("lieu_naissance", "").strip(),
             request.form.get("allergies", "").strip(),
             request.form.get("antecedents", "").strip(),
             request.form.get("diagnostics", "").strip(),
             individu_actif_id)
        )
        connexion.commit()
        flash("Fiche mise à jour ✓", "success")
        connexion.close()
        return redirect(url_for("individu"))

    tous_les_individus = connexion.execute(
        "SELECT * FROM individu ORDER BY prenom ASC"
    ).fetchall()
    connexion.close()
    return render_template("individu.html", tous_les_individus=tous_les_individus)


@app.route("/individu/creer", methods=["POST"])
def creer_individu():
    connexion = get_db()
    prenom = request.form.get("prenom", "").strip()
    nom = request.form.get("nom", "").strip()
    date_naissance = request.form.get("date_naissance") or None
    heure_naissance = request.form.get("heure_naissance") or None

    if not prenom:
        flash("Le prénom est obligatoire pour créer un profil", "info")
        connexion.close()
        return redirect(url_for("individu"))

    curseur = connexion.execute(
        "INSERT INTO individu (prenom, nom, date_naissance, heure_naissance) VALUES (?, ?, ?, ?)",
        (prenom, nom, date_naissance, heure_naissance)
    )
    nouvel_individu_id = curseur.lastrowid
    connexion.commit()

    assurer_suivi_examen_complet(connexion, nouvel_individu_id)

    connexion.execute(
        "UPDATE individu_actif SET individu_id = ? WHERE id = 1", (nouvel_individu_id,)
    )
    connexion.commit()
    connexion.close()

    flash(f"Profil de {prenom} créé ✓", "success")
    return redirect(url_for("individu"))


@app.route("/individu/activer/<int:individu_id>")
def activer_individu(individu_id):
    connexion = get_db()
    existe = connexion.execute(
        "SELECT id FROM individu WHERE id = ?", (individu_id,)
    ).fetchone()
    if existe:
        connexion.execute(
            "UPDATE individu_actif SET individu_id = ? WHERE id = 1", (individu_id,)
        )
        connexion.commit()
    connexion.close()
    destination = request.referrer or url_for("index")
    return redirect(destination)


@app.route("/individu/supprimer/<int:individu_id>")
def confirmer_suppression_individu(individu_id):
    connexion = get_db()
    individu_a_supprimer = connexion.execute(
        "SELECT * FROM individu WHERE id = ?", (individu_id,)
    ).fetchone()
    connexion.close()
    if not individu_a_supprimer:
        flash("Profil introuvable", "info")
        return redirect(url_for("individu"))
    return render_template(
        "supprimer_individu.html", individu_a_supprimer=individu_a_supprimer
    )


@app.route("/individu/supprimer/<int:individu_id>/definitif", methods=["POST"])
def supprimer_individu_definitif(individu_id):
    connexion = get_db()
    individu_a_supprimer = connexion.execute(
        "SELECT * FROM individu WHERE id = ?", (individu_id,)
    ).fetchone()

    if not individu_a_supprimer:
        flash("Profil introuvable", "info")
        connexion.close()
        return redirect(url_for("individu"))

    confirmation_saisie = request.form.get("confirmation_prenom", "").strip()
    if confirmation_saisie != individu_a_supprimer["prenom"]:
        flash("Le prénom saisi ne correspond pas. Suppression annulée.", "info")
        connexion.close()
        return redirect(url_for("confirmer_suppression_individu", individu_id=individu_id))

    connexion.execute("DELETE FROM poids WHERE individu_id = ?", (individu_id,))
    connexion.execute("DELETE FROM taille WHERE individu_id = ?", (individu_id,))
    connexion.execute("DELETE FROM dents WHERE individu_id = ?", (individu_id,))
    connexion.execute("DELETE FROM suivi_examen WHERE individu_id = ?", (individu_id,))
    connexion.execute("DELETE FROM evenement WHERE individu_id = ?", (individu_id,))
    connexion.execute("DELETE FROM individu WHERE id = ?", (individu_id,))
    connexion.execute(
        "UPDATE individu_actif SET individu_id = NULL WHERE individu_id = ?", (individu_id,)
    )
    connexion.commit()
    connexion.close()

    flash(f"Le profil de {individu_a_supprimer['prenom']} a été supprimé", "info")
    return redirect(url_for("index"))


# ──────────────────────────────────────────────
# POIDS
# ──────────────────────────────────────────────
@app.route("/poids", methods=["GET", "POST"])
def poids():
    connexion = get_db()
    individu_actif_id = obtenir_individu_actif_id(connexion)

    if request.method == "POST" and individu_actif_id:
        connexion.execute(
            "INSERT INTO poids (individu_id, date, poids, notes) VALUES (?, ?, ?, ?)",
            (individu_actif_id, request.form["date"], request.form["poids"],
             request.form.get("notes", ""))
        )
        connexion.commit()
        flash("Poids enregistré ✓", "success")
        connexion.close()
        return redirect(url_for("poids"))

    historique = []
    graphique = []
    if individu_actif_id:
        historique = connexion.execute(
            "SELECT * FROM poids WHERE individu_id = ? ORDER BY date DESC, id DESC",
            (individu_actif_id,)
        ).fetchall()
        graphique = connexion.execute(
            "SELECT date, poids FROM poids WHERE individu_id = ? ORDER BY date ASC, id ASC",
            (individu_actif_id,)
        ).fetchall()

    connexion.close()
    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    return render_template("poids.html", historique=historique, graphique=graphique, today=aujourd_hui)


@app.route("/poids/supprimer/<int:poids_id>")
def supprimer_poids(poids_id):
    connexion = get_db()
    connexion.execute("DELETE FROM poids WHERE id = ?", (poids_id,))
    connexion.commit()
    connexion.close()
    flash("Entrée supprimée", "info")
    return redirect(url_for("poids"))


# ──────────────────────────────────────────────
# TAILLE
# ──────────────────────────────────────────────
@app.route("/taille", methods=["GET", "POST"])
def taille():
    connexion = get_db()
    individu_actif_id = obtenir_individu_actif_id(connexion)

    if request.method == "POST" and individu_actif_id:
        connexion.execute(
            "INSERT INTO taille (individu_id, date, taille, notes) VALUES (?, ?, ?, ?)",
            (individu_actif_id, request.form["date"], request.form["taille"],
             request.form.get("notes", ""))
        )
        connexion.commit()
        flash("Taille enregistrée ✓", "success")
        connexion.close()
        return redirect(url_for("taille"))

    historique = []
    graphique = []
    if individu_actif_id:
        historique = connexion.execute(
            "SELECT * FROM taille WHERE individu_id = ? ORDER BY date DESC, id DESC",
            (individu_actif_id,)
        ).fetchall()
        graphique = connexion.execute(
            "SELECT date, taille FROM taille WHERE individu_id = ? ORDER BY date ASC, id ASC",
            (individu_actif_id,)
        ).fetchall()

    connexion.close()
    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    return render_template("taille.html", historique=historique, graphique=graphique, today=aujourd_hui)


@app.route("/taille/supprimer/<int:taille_id>")
def supprimer_taille(taille_id):
    connexion = get_db()
    connexion.execute("DELETE FROM taille WHERE id = ?", (taille_id,))
    connexion.commit()
    connexion.close()
    flash("Entrée supprimée", "info")
    return redirect(url_for("taille"))


# ──────────────────────────────────────────────
# DENTS
# ──────────────────────────────────────────────
@app.route("/dents", methods=["GET", "POST"])
def dents():
    connexion = get_db()
    individu_actif_id = obtenir_individu_actif_id(connexion)

    if request.method == "POST" and individu_actif_id:
        connexion.execute(
            "INSERT INTO dents (individu_id, date, dent, notes) VALUES (?, ?, ?, ?)",
            (individu_actif_id, request.form["date"], request.form["dent"],
             request.form.get("notes", ""))
        )
        connexion.commit()
        flash("Entrée enregistrée ✓", "success")
        connexion.close()
        return redirect(url_for("dents"))

    historique = []
    if individu_actif_id:
        historique = connexion.execute(
            "SELECT * FROM dents WHERE individu_id = ? ORDER BY date DESC, id DESC",
            (individu_actif_id,)
        ).fetchall()

    connexion.close()
    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    return render_template("dents.html", historique=historique, today=aujourd_hui)


@app.route("/dents/supprimer/<int:dent_id>")
def supprimer_dent(dent_id):
    connexion = get_db()
    connexion.execute("DELETE FROM dents WHERE id = ?", (dent_id,))
    connexion.commit()
    connexion.close()
    flash("Entrée supprimée", "info")
    return redirect(url_for("dents"))


# ──────────────────────────────────────────────
# EXAMENS
# ──────────────────────────────────────────────
@app.route("/examens")
def examens():
    connexion = get_db()
    individu_actif_id = obtenir_individu_actif_id(connexion)

    lignes_examens = []
    if individu_actif_id:
        assurer_suivi_examen_complet(connexion, individu_actif_id)
        lignes_examens = connexion.execute(
            """SELECT type_examen.id AS type_id, type_examen.nom AS nom,
                      type_examen.frequence_mois AS frequence_mois,
                      type_examen.description AS description,
                      suivi_examen.id AS suivi_id, suivi_examen.derniere_date AS derniere_date
               FROM type_examen
               LEFT JOIN suivi_examen
                   ON suivi_examen.type_examen_id = type_examen.id
                   AND suivi_examen.individu_id = ?
               ORDER BY type_examen.nom ASC""",
            (individu_actif_id,)
        ).fetchall()

    connexion.close()
    return render_template("examens.html", lignes_examens=lignes_examens)


@app.route("/examens/type/nouveau", methods=["POST"])
def creer_type_examen():
    connexion = get_db()
    nom = request.form.get("nom", "").strip()
    frequence_mois = request.form.get("frequence_mois") or None
    description = request.form.get("description", "").strip()

    if not nom:
        flash("Le nom de l'examen est obligatoire", "info")
        connexion.close()
        return redirect(url_for("examens"))

    curseur = connexion.execute(
        "INSERT INTO type_examen (nom, frequence_mois, description) VALUES (?, ?, ?)",
        (nom, frequence_mois, description)
    )
    nouveau_type_id = curseur.lastrowid
    connexion.commit()

    individus_existants = connexion.execute("SELECT id FROM individu").fetchall()
    for ligne_individu in individus_existants:
        connexion.execute(
            """INSERT OR IGNORE INTO suivi_examen (individu_id, type_examen_id, derniere_date)
               VALUES (?, ?, NULL)""",
            (ligne_individu["id"], nouveau_type_id)
        )
    connexion.commit()
    connexion.close()

    flash("Type d'examen ajouté ✓", "success")
    return redirect(url_for("examens"))


@app.route("/examens/type/supprimer/<int:type_id>")
def supprimer_type_examen(type_id):
    connexion = get_db()
    connexion.execute("DELETE FROM suivi_examen WHERE type_examen_id = ?", (type_id,))
    connexion.execute("DELETE FROM type_examen WHERE id = ?", (type_id,))
    connexion.commit()
    connexion.close()
    flash("Type d'examen supprimé", "info")
    return redirect(url_for("examens"))


@app.route("/examens/frequence/<int:type_id>", methods=["POST"])
def modifier_frequence_examen(type_id):
    connexion = get_db()
    frequence_mois = request.form.get("frequence_mois") or None
    connexion.execute(
        "UPDATE type_examen SET frequence_mois = ? WHERE id = ?", (frequence_mois, type_id)
    )
    connexion.commit()
    connexion.close()
    flash("Fréquence mise à jour ✓", "success")
    return redirect(url_for("examens"))


@app.route("/examens/date/<int:suivi_id>", methods=["POST"])
def mettre_a_jour_date_examen(suivi_id):
    connexion = get_db()
    nouvelle_date = request.form.get("derniere_date") or None
    connexion.execute(
        "UPDATE suivi_examen SET derniere_date = ? WHERE id = ?", (nouvelle_date, suivi_id)
    )
    connexion.commit()
    connexion.close()
    flash("Date mise à jour ✓", "success")
    return redirect(url_for("examens"))


# ──────────────────────────────────────────────
# HISTORIQUE DES ÉVÉNEMENTS DE SANTÉ
# ──────────────────────────────────────────────
@app.route("/historique", methods=["GET", "POST"])
def historique():
    connexion = get_db()
    individu_actif_id = obtenir_individu_actif_id(connexion)

    if request.method == "POST" and individu_actif_id:
        connexion.execute(
            "INSERT INTO evenement (individu_id, date, titre, description) VALUES (?, ?, ?, ?)",
            (individu_actif_id, request.form["date"], request.form["titre"],
             request.form.get("description", ""))
        )
        connexion.commit()
        flash("Événement enregistré ✓", "success")
        connexion.close()
        return redirect(url_for("historique"))

    liste_evenements = []
    if individu_actif_id:
        liste_evenements = connexion.execute(
            "SELECT * FROM evenement WHERE individu_id = ? ORDER BY date DESC, id DESC",
            (individu_actif_id,)
        ).fetchall()

    connexion.close()
    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    return render_template("historique.html", liste_evenements=liste_evenements, today=aujourd_hui)


@app.route("/historique/supprimer/<int:evenement_id>")
def supprimer_evenement(evenement_id):
    connexion = get_db()
    connexion.execute("DELETE FROM evenement WHERE id = ?", (evenement_id,))
    connexion.commit()
    connexion.close()
    flash("Événement supprimé", "info")
    return redirect(url_for("historique"))


@app.route("/historique/modifier/<int:evenement_id>", methods=["POST"])
def modifier_evenement(evenement_id):
    connexion = get_db()
    connexion.execute(
        "UPDATE evenement SET date=?, titre=?, description=? WHERE id=?",
        (request.form["date"], request.form["titre"],
         request.form.get("description", ""), evenement_id)
    )
    connexion.commit()
    connexion.close()
    flash("Événement mis à jour ✓", "success")
    return redirect(url_for("historique"))


# ──────────────────────────────────────────────
# PROBLÈMES DE SANTÉ CHRONIQUES (à venir)
# ──────────────────────────────────────────────
@app.route("/problemes")
def problemes():
    return render_template("problemes.html")


# ──────────────────────────────────────────────
# DÉMARRAGE
# ──────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=4200, debug=False)
