from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3, os, requests
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = "mybunny-secret-2024"
DB_PATH = "/share/my-bunny/bunny.db"

HA_URL = "http://supervisor/core"
HA_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

TEMP_SENSOR = "sensor.thermo_bureau_kos_temperature"
HUM_SENSOR  = "sensor.thermo_bureau_kos_humidite"

# ──────────────────────────────────────────────
# BASE DE DONNÉES
# ──────────────────────────────────────────────
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
    conn.execute("""CREATE TABLE IF NOT EXISTS veterinaire (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        description TEXT,
        prochain_rdv TEXT,
        notes TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        titre TEXT NOT NULL,
        description TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS temperature (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        temp REAL,
        humidite REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS temp_daily (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        temp_min REAL, temp_max REAL, temp_moy REAL,
        hum_min REAL,  hum_max REAL,  hum_moy REAL)""")
    conn.commit()
    conn.close()

# ──────────────────────────────────────────────
# COLLECTE TEMPÉRATURE DEPUIS HOME ASSISTANT
# ──────────────────────────────────────────────
def fetch_ha_sensor(entity_id):
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    try:
        r = requests.get(f"{HA_URL}/api/states/{entity_id}", headers=headers, timeout=5)
        if r.status_code == 200:
            return float(r.json()["state"])
    except Exception as e:
        print(f"Erreur capteur {entity_id}: {e}")
    return None

def collect_temperature():
    print(f"=== COLLECTE TEMP === Token présent: {bool(HA_TOKEN)}, longueur: {len(HA_TOKEN)}")
    temp = fetch_ha_sensor(TEMP_SENSOR)
    hum  = fetch_ha_sensor(HUM_SENSOR)
    print(f"=== RÉSULTAT === temp={temp}, hum={hum}")
    if temp is not None and hum is not None:
        conn = get_db()
        conn.execute(
            "INSERT INTO temperature (timestamp, temp, humidite) VALUES (?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), temp, hum)
        )
        conn.commit()
        conn.close()
        aggregate_daily()


# ──────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────
@app.route("/")
def index():
    conn = get_db()
    # Dernière température
    last_temp = conn.execute(
        "SELECT * FROM temperature ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    # Dernier poids
    last_poids = conn.execute(
        "SELECT * FROM poids ORDER BY date DESC LIMIT 1"
    ).fetchone()
    # Prochain vétérinaire
    today = datetime.now().strftime("%Y-%m-%d")
    next_rdv = conn.execute(
        "SELECT * FROM veterinaire WHERE prochain_rdv >= ? ORDER BY prochain_rdv ASC LIMIT 1",
        (today,)
    ).fetchone()
    # Journal récent
    journal = conn.execute(
        "SELECT * FROM journal ORDER BY date DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return render_template("index.html",
                       dernier_poids=last_poids["poids"] if last_poids else None,
                       temp_actuelle=last_temp["temp"] if last_temp else None,
                       hum_actuelle=last_temp["humidite"] if last_temp else None,
                       prochain_rdv=next_rdv,
                       derniers_journaux=journal)

@app.route("/poids", methods=["GET", "POST"])
def poids():
    conn = get_db()
    if request.method == "POST":
        date   = request.form["date"]
        poids_val = request.form["poids"]
        notes  = request.form.get("notes", "")
        conn.execute("INSERT INTO poids (date, poids, notes) VALUES (?, ?, ?)",
                     (date, poids_val, notes))
        conn.commit()
        flash("Poids enregistré ✓", "success")
        return redirect(url_for("poids"))
    historique = conn.execute("SELECT * FROM poids ORDER BY date DESC").fetchall()
    conn.close()
    return render_template("poids.html", historique=historique)

@app.route("/poids/supprimer/<int:id>")
def supprimer_poids(id):
    conn = get_db()
    conn.execute("DELETE FROM poids WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Entrée supprimée", "info")
    return redirect(url_for("poids"))

@app.route("/veterinaire", methods=["GET", "POST"])
def veterinaire():
    conn = get_db()
    if request.method == "POST":
        conn.execute("""INSERT INTO veterinaire (date, type, description, prochain_rdv, notes)
                        VALUES (?, ?, ?, ?, ?)""",
                     (request.form["date"],
                      request.form["type"],
                      request.form.get("description", ""),
                      request.form.get("prochain_rdv", "") or None,
                      request.form.get("notes", "")))
        conn.commit()
        flash("Consultation enregistrée ✓", "success")
        return redirect(url_for("veterinaire"))
    historique = conn.execute("SELECT * FROM veterinaire ORDER BY date DESC").fetchall()
    conn.close()
    return render_template("veterinaire.html", historique=historique)

@app.route("/veterinaire/supprimer/<int:id>")
def supprimer_veterinaire(id):
    conn = get_db()
    conn.execute("DELETE FROM veterinaire WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Entrée supprimée", "info")
    return redirect(url_for("veterinaire"))

@app.route("/journal", methods=["GET", "POST"])
def journal():
    conn = get_db()
    if request.method == "POST":
        conn.execute("INSERT INTO journal (date, titre, description) VALUES (?, ?, ?)",
                     (request.form["date"],
                      request.form["titre"],
                      request.form.get("description", "")))
        conn.commit()
        flash("Note enregistrée ✓", "success")
        return redirect(url_for("journal"))
    historique = conn.execute("SELECT * FROM journal ORDER BY date DESC").fetchall()
    conn.close()
    return render_template("journal.html", historique=historique)

@app.route("/journal/supprimer/<int:id>")
def supprimer_journal(id):
    conn = get_db()
    conn.execute("DELETE FROM journal WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Note supprimée", "info")
    return redirect(url_for("journal"))

@app.route("/temperature")
def temperature():
    conn = get_db()
    # 14 derniers jours agrégés
    daily = conn.execute(
        "SELECT * FROM temp_daily ORDER BY date DESC LIMIT 14"
    ).fetchall()
    # Dernières 24h brut
    limit = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    brut = conn.execute(
        "SELECT * FROM temperature WHERE timestamp >= ? ORDER BY timestamp ASC",
        (limit,)
    ).fetchall()
    conn.close()
    return render_template("temperature.html", daily=daily, brut=brut)

# ──────────────────────────────────────────────
# DÉMARRAGE
# ──────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(collect_temperature, "interval", minutes=15)
    scheduler.start()
    collect_temperature()  # collecte immédiate au démarrage
    app.run(host="0.0.0.0", port=4000, debug=False)
