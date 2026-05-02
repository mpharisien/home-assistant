from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3, os
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = "stats-vie-secret-2024"
DB_PATH = "/share/stats_vie/stats_vie.db"

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS poids (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        poids REAL NOT NULL,
        notes TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cheveux (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        notes TEXT)""")
    conn.commit()
    conn.close()

# ── Helpers ──

def calcul_stats_poids(mesures):
    if not mesures:
        return None
    poids_list = [m["poids"] for m in mesures]
    premiere = mesures[-1]  # trié DESC, donc le plus ancien est en dernier
    derniere = mesures[0]
    evolution = round(derniere["poids"] - premiere["poids"], 1)
    return {
        "min": round(min(poids_list), 1),
        "max": round(max(poids_list), 1),
        "moyenne": round(sum(poids_list) / len(poids_list), 1),
        "evolution": evolution,
        "nb_mesures": len(mesures),
        "premiere_date": premiere["date"],
        "derniere_date": derniere["date"],
    }

def calcul_stats_cheveux(coupes):
    if len(coupes) < 2:
        return {
            "nb_coupes": len(coupes),
            "intervalle_moyen": None,
            "derniere_coupe": coupes[0]["date"] if coupes else None,
            "jours_depuis": None,
        }
    # Calculer les intervalles entre chaque coupe
    dates = [datetime.strptime(c["date"], "%Y-%m-%d") for c in coupes]
    intervalles = [(dates[i] - dates[i+1]).days for i in range(len(dates)-1)]
    intervalle_moyen = round(sum(intervalles) / len(intervalles))
    jours_depuis = (datetime.today() - dates[0]).days
    return {
        "nb_coupes": len(coupes),
        "intervalle_moyen": intervalle_moyen,
        "derniere_coupe": coupes[0]["date"],
        "jours_depuis": jours_depuis,
    }

# ── Routes ──

@app.route("/")
def index():
    return redirect(url_for("poids"))

@app.route("/poids")
def poids():
    conn = get_db()
    mesures = conn.execute("SELECT * FROM poids ORDER BY date DESC").fetchall()
    conn.close()
    stats = calcul_stats_poids(mesures)
    today = date.today().isoformat()
    return render_template("poids.html", active_page="poids", mesures=mesures, stats=stats, today=today)

@app.route("/poids/ajouter", methods=["POST"])
def poids_ajouter():
    d = request.form
    conn = get_db()
    conn.execute("INSERT INTO poids (date, poids, notes) VALUES (?, ?, ?)",
        (d["date"], float(d["poids"]), d.get("notes", "")))
    conn.commit()
    conn.close()
    flash("Mesure ajoutée.", "success")
    return redirect(url_for("poids"))

@app.route("/poids/supprimer/<int:id>", methods=["POST"])
def poids_supprimer(id):
    conn = get_db()
    conn.execute("DELETE FROM poids WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Mesure supprimée.", "info")
    return redirect(url_for("poids"))

@app.route("/cheveux")
def cheveux():
    conn = get_db()
    coupes = conn.execute("SELECT * FROM cheveux ORDER BY date DESC").fetchall()
    conn.close()
    stats = calcul_stats_cheveux(coupes)
    today = date.today().isoformat()
    return render_template("cheveux.html", active_page="cheveux", coupes=coupes, stats=stats, today=today)

@app.route("/cheveux/ajouter", methods=["POST"])
def cheveux_ajouter():
    d = request.form
    conn = get_db()
    conn.execute("INSERT INTO cheveux (date, notes) VALUES (?, ?)",
        (d["date"], d.get("notes", "")))
    conn.commit()
    conn.close()
    flash("Coupe enregistrée.", "success")
    return redirect(url_for("cheveux"))

@app.route("/cheveux/supprimer/<int:id>", methods=["POST"])
def cheveux_supprimer(id):
    conn = get_db()
    conn.execute("DELETE FROM cheveux WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Entrée supprimée.", "info")
    return redirect(url_for("cheveux"))

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=False)
