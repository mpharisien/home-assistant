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
    temp = fetch_ha_sensor(TEMP_SENSOR)
    hum  = fetch_ha_sensor(HUM_SENSOR)
    if temp is None and hum is None:
        return
    conn = get_db()
    now = datetime.now()
    conn.execute(
        "INSERT INTO temperature (timestamp, temp, humidite) VALUES (?, ?, ?)",
        (now.strftime("%Y-%m-%d %H:%M:%S"), temp, hum)
    )
    # Aggrégation quotidienne
    today = now.strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT temp, humidite FROM temperature WHERE timestamp LIKE ?",
        (f"{today}%",)
    ).fetchall()
    temps = [r["temp"] for r in rows if r["temp"] is not None]
    hums  = [r["humidite"] for r in rows if r["humidite"] is not None]
    if temps:
        conn.execute("""INSERT INTO temp_daily (date, temp_min, temp_max, temp_moy,
                        hum_min, hum_max, hum_moy)
                        VALUES (?,?,?,?,?,?,?)
                        ON CONFLICT(date) DO UPDATE SET
                        temp_min=excluded.temp_min, temp_max=excluded.temp_max,
                        temp_moy=excluded.temp_moy, hum_min=excluded.hum_min,
                        hum_max=excluded.hum_max, hum_moy=excluded.hum_moy""",
                     (today,
                      round(min(temps),1), round(max(temps),1), round(sum(temps)/len(temps),1),
                      round(min(hums),1),  round(max(hums),1),  round(sum(hums)/len(hums),1)))
    # Nettoyage données brutes > 14 jours
    limit = (now - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM temperature WHERE timestamp < ?", (limit,))
    conn.commit()
    conn.close()

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
        (
