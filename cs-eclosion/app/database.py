import sqlite3
import os

DB_PATH = os.environ.get('DB_PATH', '/share/cs_eclosion/cs_eclosion.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    # Table des exercices (une ligne par année)
    c.execute('''
        CREATE TABLE IF NOT EXISTS exercices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annee INTEGER UNIQUE NOT NULL,
            budget_previsionnel REAL DEFAULT NULL,
            statut TEXT DEFAULT 'en_cours',  -- 'valide' ou 'en_cours'
            date_import TEXT DEFAULT NULL
        )
    ''')

    # Table des dépenses (toutes les écritures importées, données BRUTES Foncia)
    c.execute('''
        CREATE TABLE IF NOT EXISTS depenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exercice_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            cle_code TEXT NOT NULL,
            cle_libelle TEXT NOT NULL,
            type_code TEXT NOT NULL,
            type_libelle TEXT NOT NULL,
            libelle TEXT NOT NULL,
            montant REAL NOT NULL,
            tva REAL NOT NULL DEFAULT 0,
            recuperable REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (exercice_id) REFERENCES exercices(id)
        )
    ''')

    # Table des logements (partagée entre futurs modules : Océa, Habitants...)
    c.execute('''
        CREATE TABLE IF NOT EXISTS logements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_lot INTEGER UNIQUE NOT NULL,
            batiment TEXT,
            etage TEXT,
            tantieme REAL,
            actif INTEGER DEFAULT 1
        )
    ''')

    conn.commit()
    conn.close()


# ─── Exercices ────────────────────────────────────────────────────────────────

def get_all_exercices():
    conn = get_db()
    rows = conn.execute('SELECT * FROM exercices ORDER BY annee DESC').fetchall()
    conn.close()
    return rows


def get_exercice_by_annee(annee):
    conn = get_db()
    row = conn.execute('SELECT * FROM exercices WHERE annee = ?', (annee,)).fetchone()
    conn.close()
    return row


def upsert_exercice(annee, statut, budget_previsionnel=None):
    conn = get_db()
    existing = conn.execute('SELECT id FROM exercices WHERE annee = ?', (annee,)).fetchone()
    if existing:
        conn.execute(
            'UPDATE exercices SET statut = ?, date_import = datetime("now") WHERE annee = ?',
            (statut, annee)
        )
        if budget_previsionnel is not None:
            conn.execute(
                'UPDATE exercices SET budget_previsionnel = ? WHERE annee = ?',
                (budget_previsionnel, annee)
            )
        exercice_id = existing['id']
    else:
        cur = conn.execute(
            'INSERT INTO exercices (annee, statut, budget_previsionnel, date_import) VALUES (?, ?, ?, datetime("now"))',
            (annee, statut, budget_previsionnel)
        )
        exercice_id = cur.lastrowid
    conn.commit()
    conn.close()
    return exercice_id


def update_budget(annee, budget):
    conn = get_db()
    conn.execute('UPDATE exercices SET budget_previsionnel = ? WHERE annee = ?', (budget, annee))
    conn.commit()
    conn.close()


# ─── Import dépenses ──────────────────────────────────────────────────────────

def delete_depenses_by_exercice(exercice_id):
    conn = get_db()
    conn.execute('DELETE FROM depenses WHERE exercice_id = ?', (exercice_id,))
    conn.commit()
    conn.close()


def insert_depenses_bulk(exercice_id, rows):
    """rows = liste de tuples (date, cle_code, cle_libelle, type_code, type_libelle, libelle, montant, tva, recuperable)"""
    conn = get_db()
    conn.executemany(
        '''INSERT INTO depenses
           (exercice_id, date, cle_code, cle_libelle, type_code, type_libelle, libelle, montant, tva, recuperable)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        [(exercice_id,) + r for r in rows]
    )
    conn.commit()
    conn.close()


def get_all_depenses_raw(annee):
    """Toutes les écritures brutes d'un exercice (utilisé pour appliquer les regroupements analytiques en Python)."""
    conn = get_db()
    rows = conn.execute('''
        SELECT d.*
        FROM depenses d
        JOIN exercices e ON d.exercice_id = e.id
        WHERE e.annee = ?
    ''', (annee,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Requêtes vue Foncia (hiérarchie officielle, fidèle) ──────────────────────

def get_total_by_annee(annee):
    conn = get_db()
    row = conn.execute('''
        SELECT SUM(d.montant) as total
        FROM depenses d
        JOIN exercices e ON d.exercice_id = e.id
        WHERE e.annee = ?
    ''', (annee,)).fetchone()
    conn.close()
    return row['total'] or 0


def get_totaux_par_cle(annee):
    conn = get_db()
    rows = conn.execute('''
        SELECT d.cle_code, d.cle_libelle, SUM(d.montant) as total
        FROM depenses d
        JOIN exercices e ON d.exercice_id = e.id
        WHERE e.annee = ?
        GROUP BY d.cle_code
        ORDER BY d.cle_code
    ''', (annee,)).fetchall()
    conn.close()
    return rows


def get_totaux_par_type(annee, cle_code=None):
    conn = get_db()
    if cle_code:
        rows = conn.execute('''
            SELECT d.type_code, d.type_libelle, SUM(d.montant) as total
            FROM depenses d
            JOIN exercices e ON d.exercice_id = e.id
            WHERE e.annee = ? AND d.cle_code = ?
            GROUP BY d.type_code
            ORDER BY d.type_code
        ''', (annee, cle_code)).fetchall()
    else:
        rows = conn.execute('''
            SELECT d.type_code, d.type_libelle, SUM(d.montant) as total
            FROM depenses d
            JOIN exercices e ON d.exercice_id = e.id
            WHERE e.annee = ?
            GROUP BY d.type_code
            ORDER BY d.type_code
        ''', (annee,)).fetchall()
    conn.close()
    return rows


def get_evolution_mensuelle(annee, cle_code=None):
    conn = get_db()
    query = '''
        SELECT strftime('%Y-%m', d.date) as mois, SUM(d.montant) as total
        FROM depenses d
        JOIN exercices e ON d.exercice_id = e.id
        WHERE e.annee = ?
    '''
    params = [annee]
    if cle_code:
        query += ' AND d.cle_code = ?'
        params.append(cle_code)
    query += ' GROUP BY mois ORDER BY mois'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_totaux_par_fournisseur(annee=None):
    conn = get_db()
    if annee:
        rows = conn.execute('''
            SELECT e.annee,
                   TRIM(SUBSTR(d.libelle, 1,
                        CASE WHEN INSTR(d.libelle, ' - ') > 0
                             THEN INSTR(d.libelle, ' - ') - 1
                             ELSE LENGTH(d.libelle) END)) as fournisseur,
                   SUM(d.montant) as total
            FROM depenses d
            JOIN exercices e ON d.exercice_id = e.id
            WHERE e.annee = ?
            GROUP BY fournisseur
            ORDER BY total DESC
        ''', (annee,)).fetchall()
    else:
        rows = conn.execute('''
            SELECT e.annee,
                   TRIM(SUBSTR(d.libelle, 1,
                        CASE WHEN INSTR(d.libelle, ' - ') > 0
                             THEN INSTR(d.libelle, ' - ') - 1
                             ELSE LENGTH(d.libelle) END)) as fournisseur,
                   SUM(d.montant) as total
            FROM depenses d
            JOIN exercices e ON d.exercice_id = e.id
            GROUP BY e.annee, fournisseur
            ORDER BY fournisseur, e.annee
        ''').fetchall()
    conn.close()
    return rows
