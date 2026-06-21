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

    # ── Migration : l'ancienne table 'logements' (schéma simplifié jamais utilisé,
    # colonnes numero_lot/batiment/etage) doit être supprimée avant de recréer le
    # nouveau schéma complet. CREATE TABLE IF NOT EXISTS ne modifie pas une table
    # déjà existante, donc cette vérification manuelle est nécessaire.
    existing_cols = c.execute("PRAGMA table_info(logements)").fetchall()
    if existing_cols and not any(col[1] == 'numero_appartement' for col in existing_cols):
        c.execute("DROP TABLE IF EXISTS logements")
        conn.commit()

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

    # Table du budget prévisionnel détaillé par poste (exercice en cours uniquement)
    c.execute('''
        CREATE TABLE IF NOT EXISTS budget_detail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exercice_id INTEGER NOT NULL,
            cle_code TEXT NOT NULL,
            cle_libelle TEXT NOT NULL,
            type_code TEXT NOT NULL,
            type_libelle TEXT NOT NULL,
            budget REAL NOT NULL,
            FOREIGN KEY (exercice_id) REFERENCES exercices(id)
        )
    ''')

    # Table des logements (données fixes) — module "Logements / Habitants"
    c.execute('''
        CREATE TABLE IF NOT EXISTS logements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_appartement TEXT UNIQUE NOT NULL,
            lot_appartement TEXT,
            nb_pieces INTEGER,
            tantieme REAL,
            terrasse INTEGER DEFAULT 0,
            balcon INTEGER DEFAULT 0,
            jardin INTEGER DEFAULT 0,
            loggia INTEGER DEFAULT 0,
            surface_m2 REAL,
            lot_parking TEXT,
            place_parking TEXT,
            tantieme_parking REAL
        )
    ''')

    # Table de l'historique daté par logement (propriétaire, habitant, prix de vente...)
    c.execute('''
        CREATE TABLE IF NOT EXISTS logement_historique (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logement_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            categorie TEXT NOT NULL,  -- 'proprietaire', 'habitant', 'prix_vente'
            valeur TEXT NOT NULL,
            FOREIGN KEY (logement_id) REFERENCES logements(id)
        )
    ''')

    # ── Module Sujets AG ──

    # Statuts personnalisés (nom + couleur)
    c.execute('''
        CREATE TABLE IF NOT EXISTS statuts_ag (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT UNIQUE NOT NULL,
            couleur TEXT NOT NULL DEFAULT '#2d7dd2'
        )
    ''')

    # Idées à remonter en AG
    c.execute('''
        CREATE TABLE IF NOT EXISTS idees_ag (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titre TEXT NOT NULL,
            description TEXT DEFAULT '',
            statut_id INTEGER,
            ordre INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (statut_id) REFERENCES statuts_ag(id) ON DELETE SET NULL
        )
    ''')

    # Tâches (sous-idées) d'une idée AG
    c.execute('''
        CREATE TABLE IF NOT EXISTS taches_ag (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idee_id INTEGER NOT NULL,
            texte TEXT NOT NULL,
            fait INTEGER NOT NULL DEFAULT 0,
            ordre INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (idee_id) REFERENCES idees_ag(id)
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


def delete_exercice_complet(annee):
    """Supprime un exercice et toutes ses données associées (dépenses + budget détaillé)."""
    conn = get_db()
    row = conn.execute('SELECT id FROM exercices WHERE annee = ?', (annee,)).fetchone()
    if row:
        exercice_id = row['id']
        conn.execute('DELETE FROM depenses WHERE exercice_id = ?', (exercice_id,))
        conn.execute('DELETE FROM budget_detail WHERE exercice_id = ?', (exercice_id,))
        conn.execute('DELETE FROM exercices WHERE id = ?', (exercice_id,))
        conn.commit()
    conn.close()


# ─── Budget détaillé (exercice en cours) ──────────────────────────────────────

def delete_budget_by_exercice(exercice_id):
    conn = get_db()
    conn.execute('DELETE FROM budget_detail WHERE exercice_id = ?', (exercice_id,))
    conn.commit()
    conn.close()


def insert_budget_bulk(exercice_id, rows):
    """rows = liste de tuples (cle_code, cle_libelle, type_code, type_libelle, budget)"""
    conn = get_db()
    conn.executemany(
        '''INSERT INTO budget_detail
           (exercice_id, cle_code, cle_libelle, type_code, type_libelle, budget)
           VALUES (?, ?, ?, ?, ?, ?)''',
        [(exercice_id,) + r for r in rows]
    )
    conn.commit()
    conn.close()


def get_budget_total(annee):
    conn = get_db()
    row = conn.execute('''
        SELECT SUM(b.budget) as total
        FROM budget_detail b
        JOIN exercices e ON b.exercice_id = e.id
        WHERE e.annee = ?
    ''', (annee,)).fetchone()
    conn.close()
    return row['total'] if row and row['total'] is not None else None


def get_all_budget_raw(annee):
    """Toutes les lignes de budget détaillé d'un exercice (pour appliquer les regroupements analytiques)."""
    conn = get_db()
    rows = conn.execute('''
        SELECT b.*
        FROM budget_detail b
        JOIN exercices e ON b.exercice_id = e.id
        WHERE e.annee = ?
    ''', (annee,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def has_budget_detail(annee):
    conn = get_db()
    row = conn.execute('''
        SELECT COUNT(*) as nb
        FROM budget_detail b
        JOIN exercices e ON b.exercice_id = e.id
        WHERE e.annee = ?
    ''', (annee,)).fetchone()
    conn.close()
    return row['nb'] > 0


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


# ─── Module Logements / Habitants ──────────────────────────────────────────────

def get_all_logements_avec_etat_actuel():
    """
    Retourne tous les logements avec leur propriétaire et habitant actuels
    (= l'entrée la plus récente de chaque catégorie dans l'historique).
    """
    conn = get_db()
    logements = conn.execute('SELECT * FROM logements ORDER BY numero_appartement').fetchall()
    result = []
    for l in logements:
        l = dict(l)
        proprio = conn.execute('''
            SELECT valeur, date FROM logement_historique
            WHERE logement_id = ? AND categorie = 'proprietaire'
            ORDER BY date DESC LIMIT 1
        ''', (l['id'],)).fetchone()
        habitant = conn.execute('''
            SELECT valeur, date FROM logement_historique
            WHERE logement_id = ? AND categorie = 'habitant'
            ORDER BY date DESC LIMIT 1
        ''', (l['id'],)).fetchone()
        l['proprietaire_actuel'] = proprio['valeur'] if proprio else None
        l['habitant_actuel'] = habitant['valeur'] if habitant else None
        result.append(l)
    conn.close()
    return result


def get_logement_by_id(logement_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM logements WHERE id = ?', (logement_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_historique_logement(logement_id):
    """Historique complet d'un logement, trié du plus récent au plus ancien."""
    conn = get_db()
    rows = conn.execute('''
        SELECT * FROM logement_historique
        WHERE logement_id = ?
        ORDER BY date DESC, id DESC
    ''', (logement_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def rechercher_logements(recherche_nom=None, surface_min=None, surface_max=None):
    """
    Retourne les logements correspondant aux filtres, avec état actuel.
    recherche_nom : cherche dans TOUT l'historique (propriétaire + habitant, toutes dates).
    """
    logements = get_all_logements_avec_etat_actuel()

    if recherche_nom:
        conn = get_db()
        terme = f'%{recherche_nom.strip()}%'
        ids_matches = conn.execute('''
            SELECT DISTINCT logement_id FROM logement_historique
            WHERE categorie IN ('proprietaire', 'habitant') AND valeur LIKE ?
        ''', (terme,)).fetchall()
        conn.close()
        ids_set = {r['logement_id'] for r in ids_matches}
        logements = [l for l in logements if l['id'] in ids_set]

    if surface_min is not None:
        logements = [l for l in logements if l['surface_m2'] is not None and l['surface_m2'] >= surface_min]
    if surface_max is not None:
        logements = [l for l in logements if l['surface_m2'] is not None and l['surface_m2'] <= surface_max]

    return logements


def add_historique_entry(logement_id, date, categorie, valeur):
    conn = get_db()
    conn.execute('''
        INSERT INTO logement_historique (logement_id, date, categorie, valeur)
        VALUES (?, ?, ?, ?)
    ''', (logement_id, date, categorie, valeur))
    conn.commit()
    conn.close()


def delete_historique_entry(entry_id):
    conn = get_db()
    conn.execute('DELETE FROM logement_historique WHERE id = ?', (entry_id,))
    conn.commit()
    conn.close()


def count_logements():
    conn = get_db()
    row = conn.execute('SELECT COUNT(*) as nb FROM logements').fetchone()
    conn.close()
    return row['nb']


def insert_logement(numero_appartement, lot_appartement, nb_pieces, tantieme,
                     terrasse, balcon, jardin, loggia, surface_m2,
                     lot_parking, place_parking, tantieme_parking):
    conn = get_db()
    cur = conn.execute('''
        INSERT INTO logements
        (numero_appartement, lot_appartement, nb_pieces, tantieme, terrasse, balcon, jardin, loggia,
         surface_m2, lot_parking, place_parking, tantieme_parking)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (numero_appartement, lot_appartement, nb_pieces, tantieme, terrasse, balcon, jardin, loggia,
          surface_m2, lot_parking, place_parking, tantieme_parking))
    conn.commit()
    logement_id = cur.lastrowid
    conn.close()
    return logement_id


def get_logement_id_by_numero(numero_appartement):
    conn = get_db()
    row = conn.execute('SELECT id FROM logements WHERE numero_appartement = ?', (numero_appartement,)).fetchone()
    conn.close()
    return row['id'] if row else None


# ─── Module Sujets AG ───────────────────────────────────────────────────────────

# Statuts

def get_all_statuts_ag():
    conn = get_db()
    rows = conn.execute('SELECT * FROM statuts_ag ORDER BY nom').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_statut_ag(nom, couleur):
    conn = get_db()
    conn.execute('INSERT INTO statuts_ag (nom, couleur) VALUES (?, ?)', (nom, couleur))
    conn.commit()
    conn.close()


def update_statut_ag(statut_id, nom, couleur):
    conn = get_db()
    conn.execute('UPDATE statuts_ag SET nom = ?, couleur = ? WHERE id = ?', (nom, couleur, statut_id))
    conn.commit()
    conn.close()


def delete_statut_ag(statut_id):
    conn = get_db()
    # Les idées qui utilisaient ce statut repassent à NULL (pas de statut) automatiquement
    # grâce à ON DELETE SET NULL défini dans le schéma.
    conn.execute('DELETE FROM statuts_ag WHERE id = ?', (statut_id,))
    conn.commit()
    conn.close()


# Idées

def get_all_idees_ag():
    """Retourne toutes les idées triées par ordre, avec leur statut (nom+couleur) et leurs tâches."""
    conn = get_db()
    idees = conn.execute('''
        SELECT i.*, s.nom as statut_nom, s.couleur as statut_couleur
        FROM idees_ag i
        LEFT JOIN statuts_ag s ON i.statut_id = s.id
        ORDER BY i.ordre, i.id
    ''').fetchall()
    result = []
    for idee in idees:
        idee = dict(idee)
        taches = conn.execute('''
            SELECT * FROM taches_ag WHERE idee_id = ? ORDER BY ordre, id
        ''', (idee['id'],)).fetchall()
        idee['taches'] = [dict(t) for t in taches]
        result.append(idee)
    conn.close()
    return result


def add_idee_ag(titre):
    conn = get_db()
    max_ordre = conn.execute('SELECT MAX(ordre) as m FROM idees_ag').fetchone()['m']
    ordre = (max_ordre or 0) + 1
    cur = conn.execute('INSERT INTO idees_ag (titre, ordre) VALUES (?, ?)', (titre, ordre))
    conn.commit()
    idee_id = cur.lastrowid
    conn.close()
    return idee_id


def update_idee_ag_titre(idee_id, titre):
    conn = get_db()
    conn.execute('UPDATE idees_ag SET titre = ? WHERE id = ?', (titre, idee_id))
    conn.commit()
    conn.close()


def update_idee_ag_description(idee_id, description):
    conn = get_db()
    conn.execute('UPDATE idees_ag SET description = ? WHERE id = ?', (description, idee_id))
    conn.commit()
    conn.close()


def update_idee_ag_statut(idee_id, statut_id):
    conn = get_db()
    conn.execute('UPDATE idees_ag SET statut_id = ? WHERE id = ?', (statut_id, idee_id))
    conn.commit()
    conn.close()


def delete_idee_ag(idee_id):
    conn = get_db()
    conn.execute('DELETE FROM taches_ag WHERE idee_id = ?', (idee_id,))
    conn.execute('DELETE FROM idees_ag WHERE id = ?', (idee_id,))
    conn.commit()
    conn.close()


def deplacer_idee_ag(idee_id, direction):
    """direction: 'haut' ou 'bas'. Échange l'ordre avec l'idée voisine."""
    conn = get_db()
    idees = conn.execute('SELECT id, ordre FROM idees_ag ORDER BY ordre, id').fetchall()
    idees = [dict(i) for i in idees]
    idx = next((i for i, x in enumerate(idees) if x['id'] == idee_id), None)
    if idx is None:
        conn.close()
        return

    if direction == 'haut' and idx > 0:
        voisin = idees[idx - 1]
    elif direction == 'bas' and idx < len(idees) - 1:
        voisin = idees[idx + 1]
    else:
        conn.close()
        return

    actuel = idees[idx]
    conn.execute('UPDATE idees_ag SET ordre = ? WHERE id = ?', (voisin['ordre'], actuel['id']))
    conn.execute('UPDATE idees_ag SET ordre = ? WHERE id = ?', (actuel['ordre'], voisin['id']))
    conn.commit()
    conn.close()


# Tâches

def add_tache_ag(idee_id, texte):
    conn = get_db()
    max_ordre = conn.execute('SELECT MAX(ordre) as m FROM taches_ag WHERE idee_id = ?', (idee_id,)).fetchone()['m']
    ordre = (max_ordre or 0) + 1
    conn.execute('INSERT INTO taches_ag (idee_id, texte, ordre) VALUES (?, ?, ?)', (idee_id, texte, ordre))
    conn.commit()
    conn.close()


def update_tache_ag_texte(tache_id, texte):
    conn = get_db()
    conn.execute('UPDATE taches_ag SET texte = ? WHERE id = ?', (texte, tache_id))
    conn.commit()
    conn.close()


def toggle_tache_ag_fait(tache_id):
    conn = get_db()
    row = conn.execute('SELECT fait FROM taches_ag WHERE id = ?', (tache_id,)).fetchone()
    if row:
        conn.execute('UPDATE taches_ag SET fait = ? WHERE id = ?', (0 if row['fait'] else 1, tache_id))
        conn.commit()
    conn.close()


def delete_tache_ag(tache_id):
    conn = get_db()
    conn.execute('DELETE FROM taches_ag WHERE id = ?', (tache_id,))
    conn.commit()
    conn.close()
