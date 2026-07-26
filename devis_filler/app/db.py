import sqlite3
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("DEVIS_DB_PATH", Path(__file__).parent / "devis.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

SITE_FIELDS = ["prenom", "nom", "email", "telephone", "code_postal", "ville", "adresse", "message", "submit"]


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


# ---------- Identités ----------

def list_identities():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM identities ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_identity(identity_id=None, label=None):
    conn = get_connection()
    if identity_id is not None:
        row = conn.execute("SELECT * FROM identities WHERE id = ?", (identity_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM identities WHERE label = ?", (label,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_identity(data, identity_id=None):
    conn = get_connection()
    fields = ["label", "civilite", "nom", "prenom", "email", "telephone",
              "adresse", "code_postal", "ville", "message_defaut"]
    values = [data.get(f, "") for f in fields]
    if identity_id:
        set_clause = ", ".join(f"{f} = ?" for f in fields)
        conn.execute(f"UPDATE identities SET {set_clause} WHERE id = ?", values + [identity_id])
    else:
        placeholders = ", ".join("?" for _ in fields)
        conn.execute(f"INSERT INTO identities ({', '.join(fields)}) VALUES ({placeholders})", values)
    conn.commit()
    conn.close()


def delete_identity(identity_id):
    conn = get_connection()
    conn.execute("DELETE FROM identities WHERE id = ?", (identity_id,))
    conn.commit()
    conn.close()


# ---------- Sites ----------

def list_sites(only_active=False):
    conn = get_connection()
    query = "SELECT * FROM sites"
    if only_active:
        query += " WHERE actif = 1"
    query += " ORDER BY id"
    rows = [dict(r) for r in conn.execute(query).fetchall()]

    # attache le dernier statut connu pour chaque site
    for s in rows:
        last = conn.execute(
            """SELECT status, confirmation_text, detail, run_at FROM submissions_log
               WHERE site_id = ? ORDER BY run_at DESC LIMIT 1""",
            (s["id"],),
        ).fetchone()
        s["last_status"] = dict(last) if last else None
    conn.close()
    return rows


def get_site(site_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_site(data, site_id=None):
    conn = get_connection()
    fields = ["nom", "url", "mode", "notes"] + [f"sel_{f}" for f in SITE_FIELDS]
    values = []
    for f in fields:
        if f == "nom":
            values.append(data.get("nom", ""))
        elif f == "url":
            values.append(data.get("url", ""))
        elif f == "mode":
            values.append(data.get("mode", "auto"))
        elif f == "notes":
            values.append(data.get("notes", ""))
        else:
            key = f.replace("sel_", "")
            values.append(data.get(f"sel_{key}", ""))

    if site_id:
        set_clause = ", ".join(f"{f} = ?" for f in fields)
        conn.execute(f"UPDATE sites SET {set_clause} WHERE id = ?", values + [site_id])
    else:
        placeholders = ", ".join("?" for _ in fields)
        conn.execute(f"INSERT INTO sites ({', '.join(fields)}) VALUES ({placeholders})", values)
    conn.commit()
    conn.close()


def set_site_active(site_id, actif: bool):
    conn = get_connection()
    conn.execute("UPDATE sites SET actif = ? WHERE id = ?", (1 if actif else 0, site_id))
    conn.commit()
    conn.close()


def delete_site(site_id):
    conn = get_connection()
    conn.execute("DELETE FROM sites WHERE id = ?", (site_id,))
    conn.commit()
    conn.close()


# ---------- Logs ----------

def log_result(site_id, identity_id, status, confirmation_text="", detail=""):
    conn = get_connection()
    conn.execute(
        """INSERT INTO submissions_log (site_id, identity_id, status, confirmation_text, detail)
           VALUES (?, ?, ?, ?, ?)""",
        (site_id, identity_id, status, confirmation_text, detail),
    )
    conn.commit()
    conn.close()
