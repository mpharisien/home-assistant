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

    # ── Migration : les tables de relevés Océa créées avant l'ajout des contraintes
    # anti-doublon (UNIQUE) et du changement de type de 'valeur' (REAL -> TEXT pour
    # gérer l'INDEX 4 alphanumérique) doivent être recréées en conservant les données
    # déjà saisies. On garde, pour chaque doublon (même logement+date[+index]), la
    # ligne avec le plus grand id (= la plus récemment insérée).
    def colonne_existe(table, colonne):
        cols = c.execute(f"PRAGMA table_info({table})").fetchall()
        return any(col[1] == colonne for col in cols)

    def table_existe(table):
        return c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None

    def a_contrainte_unique(table):
        sql = c.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return sql and 'UNIQUE' in sql['sql']

    if table_existe('releves_eau_froide') and not a_contrainte_unique('releves_eau_froide'):
        anciennes = c.execute('SELECT * FROM releves_eau_froide ORDER BY id').fetchall()
        c.execute('ALTER TABLE releves_eau_froide RENAME TO releves_eau_froide_old')
        conn.commit()
        c.execute('''
            CREATE TABLE releves_eau_froide (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                logement_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                index_m3 REAL NOT NULL,
                FOREIGN KEY (logement_id) REFERENCES logements(id),
                UNIQUE(logement_id, date)
            )
        ''')
        for r in anciennes:
            c.execute('''
                INSERT INTO releves_eau_froide (logement_id, date, index_m3) VALUES (?, ?, ?)
                ON CONFLICT(logement_id, date) DO UPDATE SET index_m3 = excluded.index_m3
            ''', (r['logement_id'], r['date'], r['index_m3']))
        c.execute('DROP TABLE releves_eau_froide_old')
        conn.commit()

    if table_existe('releves_thermique') and (
        not a_contrainte_unique('releves_thermique') or colonne_existe('releves_thermique', 'unite')
    ):
        anciennes = c.execute('SELECT * FROM releves_thermique ORDER BY id').fetchall()
        c.execute('ALTER TABLE releves_thermique RENAME TO releves_thermique_old')
        conn.commit()
        c.execute('''
            CREATE TABLE releves_thermique (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                logement_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                numero_index INTEGER NOT NULL,
                valeur TEXT NOT NULL,
                FOREIGN KEY (logement_id) REFERENCES logements(id),
                UNIQUE(logement_id, date, numero_index)
            )
        ''')
        for r in anciennes:
            c.execute('''
                INSERT INTO releves_thermique (logement_id, date, numero_index, valeur) VALUES (?, ?, ?, ?)
                ON CONFLICT(logement_id, date, numero_index) DO UPDATE SET valeur = excluded.valeur
            ''', (r['logement_id'], r['date'], r['numero_index'], str(r['valeur'])))
        c.execute('DROP TABLE releves_thermique_old')
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
            tantieme_parking REAL,
            numero_compteur_eau_froide TEXT,
            numero_compteur_thermique TEXT
        )
    ''')

    # Migration : ajout des numéros de compteur sur une table 'logements' déjà existante
    # (ALTER TABLE ADD COLUMN, car CREATE TABLE IF NOT EXISTS ne modifie pas une table existante).
    cols_logements = [col[1] for col in c.execute("PRAGMA table_info(logements)").fetchall()]
    if 'numero_compteur_eau_froide' not in cols_logements:
        c.execute("ALTER TABLE logements ADD COLUMN numero_compteur_eau_froide TEXT")
    if 'numero_compteur_thermique' not in cols_logements:
        c.execute("ALTER TABLE logements ADD COLUMN numero_compteur_thermique TEXT")
    conn.commit()

    # Table de l'historique daté par logement (propriétaire, habitant...)
    c.execute('''
        CREATE TABLE IF NOT EXISTS logement_historique (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logement_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            categorie TEXT NOT NULL,  -- 'proprietaire', 'habitant'
            valeur TEXT NOT NULL,
            FOREIGN KEY (logement_id) REFERENCES logements(id)
        )
    ''')

    # Table des ventes d'appartements — module "Ventes"
    # logement_id est NULLABLE : NULL signifie "logement non identifié" (case
    # "Je ne sais pas" du formulaire), pour ne pas bloquer la saisie d'une vente
    # dont on n'a pas encore retrouvé l'appartement exact.
    # valeur_fonciere = terme officiel data.gouv/DVF (≠ prix affiché sur l'annonce,
    # et ≠ "prix réel" au sens strict : c'est la valeur déclarée dans l'acte).
    c.execute('''
        CREATE TABLE IF NOT EXISTS ventes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logement_id INTEGER,
            date_annonce TEXT,
            prix_annonce REAL,
            valeur_fonciere REAL,
            charges_previsionnelles REAL,
            surface_reelle_bati REAL,
            surface_carrez REAL,
            numero_lot TEXT,
            reference_mutation TEXT,
            agence TEXT,
            lien_annonce TEXT,
            FOREIGN KEY (logement_id) REFERENCES logements(id)
        )
    ''')

    # Migrations sur une table 'ventes' déjà existante (versions précédentes du module) :
    # - renommage prix_officiel -> valeur_fonciere (terme officiel data.gouv/DVF)
    # - ajout des champs issus de la fiche officielle DVF (surfaces, lot, référence)
    cols_ventes = [col[1] for col in c.execute("PRAGMA table_info(ventes)").fetchall()]
    if 'prix_officiel' in cols_ventes and 'valeur_fonciere' not in cols_ventes:
        c.execute("ALTER TABLE ventes RENAME COLUMN prix_officiel TO valeur_fonciere")
    cols_ventes = [col[1] for col in c.execute("PRAGMA table_info(ventes)").fetchall()]
    if 'surface_reelle_bati' not in cols_ventes:
        c.execute("ALTER TABLE ventes ADD COLUMN surface_reelle_bati REAL")
    if 'surface_carrez' not in cols_ventes:
        c.execute("ALTER TABLE ventes ADD COLUMN surface_carrez REAL")
    if 'numero_lot' not in cols_ventes:
        c.execute("ALTER TABLE ventes ADD COLUMN numero_lot TEXT")
    if 'reference_mutation' not in cols_ventes:
        c.execute("ALTER TABLE ventes ADD COLUMN reference_mutation TEXT")
    conn.commit()

    # Table de paramètres simples clé/valeur (ex: date de dernière vérification
    # manuelle des valeurs foncières sur data.gouv, module Ventes).
    c.execute('''
        CREATE TABLE IF NOT EXISTS parametres (
            cle TEXT PRIMARY KEY,
            valeur TEXT
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

    # ── Module Relevés Océa ──

    # Eau froide : un INDEX cumulatif (m³) par logement et par date, relevé manuellement
    # dans le couloir. Tous les 59 logements peuvent avoir des relevés ici.
    # UNIQUE(logement_id, date) : une 2e saisie le même jour remplace la précédente (upsert).
    c.execute('''
        CREATE TABLE IF NOT EXISTS releves_eau_froide (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logement_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            index_m3 REAL NOT NULL,
            FOREIGN KEY (logement_id) REFERENCES logements(id),
            UNIQUE(logement_id, date)
        )
    ''')

    # Eau chaude : consommation mensuelle (déjà calculée par Océa), pour le logement
    # de Marc-Antoine uniquement. mois au format 'YYYY-MM'.
    c.execute('''
        CREATE TABLE IF NOT EXISTS releves_eau_chaude_mensuel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logement_id INTEGER NOT NULL,
            mois TEXT NOT NULL,
            consommation_m3 REAL NOT NULL,
            FOREIGN KEY (logement_id) REFERENCES logements(id),
            UNIQUE(logement_id, mois)
        )
    ''')

    # Thermique : plusieurs index (INDEX 1 à 16 sur le boîtier). Pour le logement de
    # Marc-Antoine, tous les index peuvent être renseignés (relevé détaillé). Pour les
    # 59 logements, seul l'INDEX 5 (consommation cumulée m³) est saisi.
    # valeur en TEXT car l'INDEX 4 contient des lettres (ex: "Lr 6A19") — conversion en
    # nombre faite à la lecture uniquement quand c'est pertinent (ex: INDEX 5 pour les calculs).
    # UNIQUE(logement_id, date, numero_index) : une 2e saisie du même index le même jour
    # remplace la précédente (upsert).
    c.execute('''
        CREATE TABLE IF NOT EXISTS releves_thermique (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logement_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            numero_index INTEGER NOT NULL,
            valeur TEXT NOT NULL,
            FOREIGN KEY (logement_id) REFERENCES logements(id),
            UNIQUE(logement_id, date, numero_index)
        )
    ''')

    # ── Module Tickets du CS ──

    # Catégories de tickets, avec une couleur parmi une palette fixe de 16 couleurs
    # (cf. COULEURS_CATEGORIES_TICKETS), gérées librement sur la page "Données".
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT UNIQUE NOT NULL,
            couleur TEXT NOT NULL
        )
    ''')

    # Prestataires pouvant être associés à un ticket, gérés librement sur la page "Données".
    c.execute('''
        CREATE TABLE IF NOT EXISTS prestataires_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT UNIQUE NOT NULL
        )
    ''')

    # Personnes pouvant être assignées à un ticket (membres du CS, syndic...),
    # gérées librement sur la page "Données".
    c.execute('''
        CREATE TABLE IF NOT EXISTS assignes_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT UNIQUE NOT NULL
        )
    ''')

    # Ticket de suivi (remplace les échanges par mail éparpillés). categorie_id,
    # prestataire_id et assigne_id sont NULLABLES : si l'entrée correspondante est
    # supprimée de la page "Données", le champ redevient simplement vide sur le
    # ticket (pas de suppression en cascade), exactement comme pour les statuts
    # de l'ancien module Sujets AG.
    # ordre sert au tri manuel (boutons monter/descendre) de la page d'accueil,
    # uniquement pertinent tant que le ticket est "en_cours".
    c.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titre TEXT NOT NULL,
            description TEXT DEFAULT '',
            statut TEXT NOT NULL DEFAULT 'en_cours',
            categorie_id INTEGER,
            prestataire_id INTEGER,
            assigne_id INTEGER,
            date_creation TEXT NOT NULL,
            date_cloture TEXT,
            ordre INTEGER NOT NULL DEFAULT 0
        )
    ''')

    # Mises à jour chronologiques d'un ticket (équivalent d'un fil de suivi),
    # chacune avec sa propre date librement modifiable (pour ressaisir un
    # historique ancien tel qu'il s'est réellement déroulé).
    c.execute('''
        CREATE TABLE IF NOT EXISTS mises_a_jour_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            texte TEXT NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
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


def get_historique_logement_avec_ventes(logement_id):
    """
    Historique d'un logement (propriétaire/habitant) fusionné avec ses ventes,
    affichées comme des lignes "Vente" en lecture seule (gérées depuis le module
    Ventes, pas depuis ce formulaire). Pour la colonne "Valeur" d'une vente, on
    affiche le prix officiel s'il est connu, sinon le prix d'annonce, sinon rien.
    Trié du plus récent au plus ancien.
    """
    hist = get_historique_logement(logement_id)
    for h in hist:
        h['is_vente'] = False

    ventes = get_ventes_par_logement(logement_id)
    for v in ventes:
        montant = v['valeur_fonciere'] if v['valeur_fonciere'] is not None else v['prix_annonce']
        hist.append({
            'id': v['id'],
            'date': v['date_annonce'] or '',
            'categorie': 'vente',
            'valeur': montant,
            'is_vente': True,
        })

    hist.sort(key=lambda h: (h['date'] or ''), reverse=True)
    return hist


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


def update_numeros_compteurs(logement_id, numero_compteur_eau_froide, numero_compteur_thermique):
    conn = get_db()
    conn.execute('''
        UPDATE logements SET numero_compteur_eau_froide = ?, numero_compteur_thermique = ? WHERE id = ?
    ''', (numero_compteur_eau_froide or None, numero_compteur_thermique or None, logement_id))
    conn.commit()
    conn.close()


# ─── Module Ventes ──────────────────────────────────────────────────────────────

def get_all_ventes():
    """
    Toutes les ventes enregistrées, les plus récemment ajoutées en premier.
    Inclut le numéro d'appartement (None si logement_id est NULL, càd "non identifié").
    """
    conn = get_db()
    rows = conn.execute('''
        SELECT v.*, l.numero_appartement
        FROM ventes v
        LEFT JOIN logements l ON l.id = v.logement_id
        ORDER BY v.id DESC
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_vente_by_id(vente_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM ventes WHERE id = ?', (vente_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_ventes_par_logement(logement_id):
    """Ventes enregistrées pour un logement donné, les plus récentes en premier."""
    conn = get_db()
    rows = conn.execute('''
        SELECT * FROM ventes WHERE logement_id = ? ORDER BY date_annonce DESC, id DESC
    ''', (logement_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_vente(logement_id, date_annonce, prix_annonce, valeur_fonciere,
                  charges_previsionnelles, surface_reelle_bati, surface_carrez,
                  numero_lot, reference_mutation, agence, lien_annonce):
    conn = get_db()
    cur = conn.execute('''
        INSERT INTO ventes
        (logement_id, date_annonce, prix_annonce, valeur_fonciere, charges_previsionnelles,
         surface_reelle_bati, surface_carrez, numero_lot, reference_mutation, agence, lien_annonce)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (logement_id, date_annonce, prix_annonce, valeur_fonciere, charges_previsionnelles,
          surface_reelle_bati, surface_carrez, numero_lot, reference_mutation, agence, lien_annonce))
    conn.commit()
    vente_id = cur.lastrowid
    conn.close()
    return vente_id


def update_vente(vente_id, logement_id, date_annonce, prix_annonce, valeur_fonciere,
                  charges_previsionnelles, surface_reelle_bati, surface_carrez,
                  numero_lot, reference_mutation, agence, lien_annonce):
    conn = get_db()
    conn.execute('''
        UPDATE ventes
        SET logement_id = ?, date_annonce = ?, prix_annonce = ?, valeur_fonciere = ?,
            charges_previsionnelles = ?, surface_reelle_bati = ?, surface_carrez = ?,
            numero_lot = ?, reference_mutation = ?, agence = ?, lien_annonce = ?
        WHERE id = ?
    ''', (logement_id, date_annonce, prix_annonce, valeur_fonciere,
          charges_previsionnelles, surface_reelle_bati, surface_carrez,
          numero_lot, reference_mutation, agence, lien_annonce, vente_id))
    conn.commit()
    conn.close()


def delete_vente(vente_id):
    conn = get_db()
    conn.execute('DELETE FROM ventes WHERE id = ?', (vente_id,))
    conn.commit()
    conn.close()


# ─── Paramètres (clé/valeur) ────────────────────────────────────────────────────

def get_parametre(cle):
    conn = get_db()
    row = conn.execute('SELECT valeur FROM parametres WHERE cle = ?', (cle,)).fetchone()
    conn.close()
    return row['valeur'] if row else None


def set_parametre(cle, valeur):
    conn = get_db()
    conn.execute('''
        INSERT INTO parametres (cle, valeur) VALUES (?, ?)
        ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur
    ''', (cle, valeur))
    conn.commit()
    conn.close()


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


# ─── Module Relevés Océa ────────────────────────────────────────────────────────

# Unité fixe par numéro d'INDEX du compteur thermique (affichage uniquement, le
# boîtier donne toujours la même grandeur pour un même index).
UNITES_INDEX_THERMIQUE = {
    1: 'kWh', 2: 'kWh', 3: '', 4: '', 5: 'm3', 6: 'h',
    7: 'C°', 8: 'C°', 9: 'K', 10: '', 11: '', 12: '',
    13: '', 14: '', 15: '', 16: '',
}

# Eau froide (tous logements, index cumulatif m³)

def get_releves_eau_froide_logement(logement_id):
    """Historique complet des relevés d'un logement, du plus ancien au plus récent."""
    conn = get_db()
    rows = conn.execute('''
        SELECT * FROM releves_eau_froide WHERE logement_id = ? ORDER BY date
    ''', (logement_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_dernier_releve_eau_froide_tous_logements():
    """Pour chaque logement, son dernier relevé en date (ou aucun si jamais relevé)."""
    conn = get_db()
    rows = conn.execute('''
        SELECT r.logement_id, r.date, r.index_m3
        FROM releves_eau_froide r
        WHERE r.id IN (
            SELECT id FROM releves_eau_froide r2
            WHERE r2.logement_id = r.logement_id
            ORDER BY date DESC LIMIT 1
        )
    ''').fetchall()
    conn.close()
    return {r['logement_id']: dict(r) for r in rows}


def add_releve_eau_froide(logement_id, date, index_m3):
    """Upsert : si un relevé existe déjà pour ce logement à cette date, sa valeur est remplacée."""
    conn = get_db()
    conn.execute('''
        INSERT INTO releves_eau_froide (logement_id, date, index_m3) VALUES (?, ?, ?)
        ON CONFLICT(logement_id, date) DO UPDATE SET index_m3 = excluded.index_m3
    ''', (logement_id, date, index_m3))
    conn.commit()
    conn.close()


def add_releves_eau_froide_bulk(date, valeurs_par_logement):
    """
    valeurs_par_logement : dict {logement_id: index_m3}. Utilisé par la grille de saisie.
    Upsert normal, SAUF si la valeur est 0 : dans ce cas, le relevé existant à cette date
    pour ce logement est supprimé (un index réel ne peut jamais valoir 0, donc 0 est
    utilisé comme commande de suppression dans cette grille). S'il n'existait rien à
    cette date, rien à supprimer : aucune ligne n'est créée.
    """
    conn = get_db()
    for lid, val in valeurs_par_logement.items():
        if val == 0:
            conn.execute('DELETE FROM releves_eau_froide WHERE logement_id = ? AND date = ?', (lid, date))
        else:
            conn.execute('''
                INSERT INTO releves_eau_froide (logement_id, date, index_m3) VALUES (?, ?, ?)
                ON CONFLICT(logement_id, date) DO UPDATE SET index_m3 = excluded.index_m3
            ''', (lid, date, val))
    conn.commit()
    conn.close()


def delete_releve_eau_froide(releve_id):
    conn = get_db()
    conn.execute('DELETE FROM releves_eau_froide WHERE id = ?', (releve_id,))
    conn.commit()
    conn.close()


def get_all_releves_eau_froide():
    """Tous les relevés eau froide, toutes dates et logements confondus (pour le tableau croisé et les calculs de conso)."""
    conn = get_db()
    rows = conn.execute('SELECT * FROM releves_eau_froide ORDER BY logement_id, date').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def calculer_consommations_eau_froide():
    """
    Calcule la consommation (différence entre relevés successifs) pour chaque logement.
    Retourne un dict {logement_id: [{date_debut, date_fin, jours, index_debut, index_fin, conso_m3, conso_par_jour}, ...]}
    triée chronologiquement. Le premier relevé d'un logement n'a pas de consommation associée
    (rien à comparer avant lui).
    """
    from datetime import datetime as dt
    releves = get_all_releves_eau_froide()
    par_logement = {}
    for r in releves:
        par_logement.setdefault(r['logement_id'], []).append(r)

    result = {}
    for logement_id, liste in par_logement.items():
        liste.sort(key=lambda r: r['date'])
        consos = []
        for i in range(1, len(liste)):
            prec, cur = liste[i - 1], liste[i]
            d1 = dt.strptime(prec['date'], '%Y-%m-%d')
            d2 = dt.strptime(cur['date'], '%Y-%m-%d')
            jours = (d2 - d1).days or 1
            conso = cur['index_m3'] - prec['index_m3']
            consos.append({
                'date_debut': prec['date'], 'date_fin': cur['date'], 'jours': jours,
                'index_debut': prec['index_m3'], 'index_fin': cur['index_m3'],
                'conso_m3': conso, 'conso_par_jour': conso / jours,
            })
        result[logement_id] = consos
    return result


# Eau chaude mensuelle (logement de Marc-Antoine uniquement)

def get_releves_eau_chaude(logement_id):
    conn = get_db()
    rows = conn.execute('''
        SELECT * FROM releves_eau_chaude_mensuel WHERE logement_id = ? ORDER BY mois
    ''', (logement_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_releve_eau_chaude(logement_id, mois, consommation_m3):
    conn = get_db()
    conn.execute('''
        INSERT INTO releves_eau_chaude_mensuel (logement_id, mois, consommation_m3) VALUES (?, ?, ?)
        ON CONFLICT(logement_id, mois) DO UPDATE SET consommation_m3 = excluded.consommation_m3
    ''', (logement_id, mois, consommation_m3))
    conn.commit()
    conn.close()


def delete_releve_eau_chaude(releve_id):
    conn = get_db()
    conn.execute('DELETE FROM releves_eau_chaude_mensuel WHERE id = ?', (releve_id,))
    conn.commit()
    conn.close()


# Thermique — relevé détaillé (logement de Marc-Antoine, tous les index 1-16)

def get_releves_thermique(logement_id):
    """Retourne les relevés groupés par date : [{date, index: {numero: {valeur, unite, id}}}, ...] triés du plus récent au plus ancien."""
    conn = get_db()
    rows = conn.execute('''
        SELECT * FROM releves_thermique WHERE logement_id = ? ORDER BY date DESC, numero_index
    ''', (logement_id,)).fetchall()
    conn.close()

    par_date = {}
    for r in rows:
        r = dict(r)
        par_date.setdefault(r['date'], {})[r['numero_index']] = {
            'valeur': r['valeur'], 'unite': UNITES_INDEX_THERMIQUE.get(r['numero_index'], ''), 'id': r['id']
        }
    return [{'date': d, 'index': idx} for d, idx in par_date.items()]


def add_releve_thermique_bulk(logement_id, date, valeurs_par_index):
    """valeurs_par_index : dict {numero_index: valeur_texte}. Seuls les index renseignés sont insérés. Upsert par (logement, date, index)."""
    conn = get_db()
    conn.executemany('''
        INSERT INTO releves_thermique (logement_id, date, numero_index, valeur) VALUES (?, ?, ?, ?)
        ON CONFLICT(logement_id, date, numero_index) DO UPDATE SET valeur = excluded.valeur
    ''', [(logement_id, date, num, str(val)) for num, val in valeurs_par_index.items()])
    conn.commit()
    conn.close()


def delete_releve_thermique_date(logement_id, date):
    """Supprime tous les index d'un relevé thermique complet (identifié par sa date)."""
    conn = get_db()
    conn.execute('DELETE FROM releves_thermique WHERE logement_id = ? AND date = ?', (logement_id, date))
    conn.commit()
    conn.close()


# Thermique — relevé simplifié pour les 59 logements (INDEX 5 uniquement, conso cumulée m³)

def get_dernier_releve_thermique_index5_tous_logements():
    """Pour chaque logement, le dernier relevé de l'INDEX 5 (consommation cumulée thermique)."""
    conn = get_db()
    rows = conn.execute('''
        SELECT r.logement_id, r.date, r.valeur
        FROM releves_thermique r
        WHERE r.numero_index = 5
          AND r.id IN (
              SELECT id FROM releves_thermique r2
              WHERE r2.logement_id = r.logement_id AND r2.numero_index = 5
              ORDER BY date DESC LIMIT 1
          )
    ''').fetchall()
    conn.close()
    result = {}
    for r in rows:
        try:
            result[r['logement_id']] = {'date': r['date'], 'valeur': float(r['valeur'])}
        except (ValueError, TypeError):
            pass
    return result


def get_all_releves_thermique_index5():
    """Tous les relevés thermique INDEX 5 (consommation cumulée), toutes dates et logements confondus (pour la page Historique thermique)."""
    conn = get_db()
    rows = conn.execute('''
        SELECT logement_id, date, valeur FROM releves_thermique
        WHERE numero_index = 5 ORDER BY logement_id, date
    ''').fetchall()
    conn.close()
    result = []
    for r in rows:
        try:
            result.append({'logement_id': r['logement_id'], 'date': r['date'], 'valeur': float(r['valeur'])})
        except (ValueError, TypeError):
            pass
    return result


def add_releve_thermique_index5_simple(logement_id, date, valeur_m3):
    """Saisie simplifiée pour les 59 logements : un seul chiffre, toujours INDEX 5. Upsert."""
    conn = get_db()
    conn.execute('''
        INSERT INTO releves_thermique (logement_id, date, numero_index, valeur) VALUES (?, ?, 5, ?)
        ON CONFLICT(logement_id, date, numero_index) DO UPDATE SET valeur = excluded.valeur
    ''', (logement_id, date, str(valeur_m3)))
    conn.commit()
    conn.close()


def add_releves_thermique_index5_bulk(date, valeurs_par_logement):
    """
    valeurs_par_logement : dict {logement_id: valeur_m3}. Utilisé par la grille de saisie thermique.
    Upsert normal, SAUF si la valeur est 0 : dans ce cas, le relevé existant à cette date pour
    ce logement est supprimé (même règle que pour l'eau froide, cf. add_releves_eau_froide_bulk).
    """
    conn = get_db()
    for lid, val in valeurs_par_logement.items():
        if val == 0:
            conn.execute('DELETE FROM releves_thermique WHERE logement_id = ? AND date = ? AND numero_index = 5', (lid, date))
        else:
            conn.execute('''
                INSERT INTO releves_thermique (logement_id, date, numero_index, valeur) VALUES (?, ?, 5, ?)
                ON CONFLICT(logement_id, date, numero_index) DO UPDATE SET valeur = excluded.valeur
            ''', (lid, date, str(val)))
    conn.commit()
    conn.close()


# ─── Module Tickets du CS ───────────────────────────────────────────────────────

# Palette fixe de 16 couleurs bien distinctes proposées sur la page "Données"
# pour les catégories de tickets (pas de sélecteur de couleur libre).
COULEURS_CATEGORIES_TICKETS = [
    '#e6194b', '#3cb44b', '#4363d8', '#f58231',
    '#911eb4', '#42d4f4', '#f032e6', '#bfef45',
    '#fabed4', '#469990', '#dcbeff', '#9a6324',
    '#800000', '#aaffc3', '#808000', '#000075',
]


# Catégories

def get_all_categories_tickets():
    conn = get_db()
    rows = conn.execute('SELECT * FROM categories_tickets ORDER BY nom').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_categorie_ticket(nom, couleur):
    conn = get_db()
    conn.execute('INSERT INTO categories_tickets (nom, couleur) VALUES (?, ?)', (nom, couleur))
    conn.commit()
    conn.close()


def update_categorie_ticket(categorie_id, nom, couleur):
    conn = get_db()
    conn.execute('UPDATE categories_tickets SET nom = ?, couleur = ? WHERE id = ?', (nom, couleur, categorie_id))
    conn.commit()
    conn.close()


def delete_categorie_ticket(categorie_id):
    # Pas de suppression en cascade : les tickets qui utilisaient cette catégorie
    # gardent leur categorie_id en base, mais celui-ci ne correspond plus à aucune
    # ligne de categories_tickets, donc les jointures LEFT JOIN affichent un champ
    # vide pour ces tickets (même principe que les statuts de l'ancien Sujets AG).
    conn = get_db()
    conn.execute('DELETE FROM categories_tickets WHERE id = ?', (categorie_id,))
    conn.commit()
    conn.close()


# Prestataires

def get_all_prestataires_tickets():
    conn = get_db()
    rows = conn.execute('SELECT * FROM prestataires_tickets ORDER BY nom').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_prestataire_ticket(nom):
    conn = get_db()
    conn.execute('INSERT INTO prestataires_tickets (nom) VALUES (?)', (nom,))
    conn.commit()
    conn.close()


def update_prestataire_ticket(prestataire_id, nom):
    conn = get_db()
    conn.execute('UPDATE prestataires_tickets SET nom = ? WHERE id = ?', (nom, prestataire_id))
    conn.commit()
    conn.close()


def delete_prestataire_ticket(prestataire_id):
    conn = get_db()
    conn.execute('DELETE FROM prestataires_tickets WHERE id = ?', (prestataire_id,))
    conn.commit()
    conn.close()


# Assignés

def get_all_assignes_tickets():
    conn = get_db()
    rows = conn.execute('SELECT * FROM assignes_tickets ORDER BY nom').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_assigne_ticket(nom):
    conn = get_db()
    conn.execute('INSERT INTO assignes_tickets (nom) VALUES (?)', (nom,))
    conn.commit()
    conn.close()


def update_assigne_ticket(assigne_id, nom):
    conn = get_db()
    conn.execute('UPDATE assignes_tickets SET nom = ? WHERE id = ?', (nom, assigne_id))
    conn.commit()
    conn.close()


def delete_assigne_ticket(assigne_id):
    conn = get_db()
    conn.execute('DELETE FROM assignes_tickets WHERE id = ?', (assigne_id,))
    conn.commit()
    conn.close()


# Tickets

_JOINTURES_TICKETS = '''
    SELECT t.*,
           c.nom as categorie_nom, c.couleur as categorie_couleur,
           p.nom as prestataire_nom,
           a.nom as assigne_nom
    FROM tickets t
    LEFT JOIN categories_tickets c ON t.categorie_id = c.id
    LEFT JOIN prestataires_tickets p ON t.prestataire_id = p.id
    LEFT JOIN assignes_tickets a ON t.assigne_id = a.id
'''


def get_tickets_en_cours():
    """Tickets en cours, triés selon l'ordre manuel (boutons monter/descendre)."""
    conn = get_db()
    rows = conn.execute(_JOINTURES_TICKETS + '''
        WHERE t.statut = 'en_cours'
        ORDER BY t.ordre, t.id
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tickets_clotures():
    """
    Tickets clôturés. Le tri (par date de clôture, catégorie ou prestataire) et le
    regroupement par année de clôture sont faits côté application (app.py), pas ici,
    car ils dépendent de l'affichage demandé sur la page.
    """
    conn = get_db()
    rows = conn.execute(_JOINTURES_TICKETS + '''
        WHERE t.statut = 'termine'
        ORDER BY t.date_cloture DESC, t.id DESC
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ticket_by_id(ticket_id):
    conn = get_db()
    row = conn.execute(_JOINTURES_TICKETS + ' WHERE t.id = ?', (ticket_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_ticket(titre, description, categorie_id, prestataire_id, assigne_id, date_creation):
    """Un nouveau ticket est toujours créé 'en_cours' et placé tout en haut de la liste manuelle."""
    conn = get_db()
    min_ordre = conn.execute("SELECT MIN(ordre) as m FROM tickets WHERE statut = 'en_cours'").fetchone()['m']
    ordre = (min_ordre or 0) - 1
    cur = conn.execute('''
        INSERT INTO tickets (titre, description, statut, categorie_id, prestataire_id,
                              assigne_id, date_creation, date_cloture, ordre)
        VALUES (?, ?, 'en_cours', ?, ?, ?, ?, NULL, ?)
    ''', (titre, description, categorie_id, prestataire_id, assigne_id, date_creation, ordre))
    conn.commit()
    ticket_id = cur.lastrowid
    conn.close()
    return ticket_id


def update_ticket(ticket_id, titre, description, categorie_id, prestataire_id, assigne_id,
                   statut, date_creation, date_cloture):
    """
    Mise à jour complète d'un ticket. Si statut == 'en_cours', date_cloture est forcée à
    NULL (la clôture est effacée à la réouverture), quel que soit ce qui est transmis.
    """
    if statut == 'en_cours':
        date_cloture = None
    conn = get_db()
    conn.execute('''
        UPDATE tickets
        SET titre = ?, description = ?, categorie_id = ?, prestataire_id = ?, assigne_id = ?,
            statut = ?, date_creation = ?, date_cloture = ?
        WHERE id = ?
    ''', (titre, description, categorie_id, prestataire_id, assigne_id,
          statut, date_creation, date_cloture, ticket_id))
    conn.commit()
    conn.close()


def delete_ticket(ticket_id):
    conn = get_db()
    conn.execute('DELETE FROM mises_a_jour_tickets WHERE ticket_id = ?', (ticket_id,))
    conn.execute('DELETE FROM tickets WHERE id = ?', (ticket_id,))
    conn.commit()
    conn.close()


def deplacer_ticket(ticket_id, direction):
    """direction: 'haut' ou 'bas'. Échange l'ordre avec le ticket 'en_cours' voisin."""
    conn = get_db()
    tickets = conn.execute('''
        SELECT id, ordre FROM tickets WHERE statut = 'en_cours' ORDER BY ordre, id
    ''').fetchall()
    tickets = [dict(t) for t in tickets]
    idx = next((i for i, x in enumerate(tickets) if x['id'] == ticket_id), None)
    if idx is None:
        conn.close()
        return

    if direction == 'haut' and idx > 0:
        voisin = tickets[idx - 1]
    elif direction == 'bas' and idx < len(tickets) - 1:
        voisin = tickets[idx + 1]
    else:
        conn.close()
        return

    actuel = tickets[idx]
    conn.execute('UPDATE tickets SET ordre = ? WHERE id = ?', (voisin['ordre'], actuel['id']))
    conn.execute('UPDATE tickets SET ordre = ? WHERE id = ?', (actuel['ordre'], voisin['id']))
    conn.commit()
    conn.close()


# Mises à jour d'un ticket

def get_mises_a_jour_ticket(ticket_id):
    """Mises à jour d'un ticket, de la plus ancienne à la plus récente."""
    conn = get_db()
    rows = conn.execute('''
        SELECT * FROM mises_a_jour_tickets WHERE ticket_id = ? ORDER BY date, id
    ''', (ticket_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_mise_a_jour_ticket(ticket_id, date, texte):
    conn = get_db()
    conn.execute('INSERT INTO mises_a_jour_tickets (ticket_id, date, texte) VALUES (?, ?, ?)',
                 (ticket_id, date, texte))
    conn.commit()
    conn.close()


def update_mise_a_jour_ticket(mise_a_jour_id, date, texte):
    conn = get_db()
    conn.execute('UPDATE mises_a_jour_tickets SET date = ?, texte = ? WHERE id = ?',
                 (date, texte, mise_a_jour_id))
    conn.commit()
    conn.close()


def delete_mise_a_jour_ticket(mise_a_jour_id):
    conn = get_db()
    conn.execute('DELETE FROM mises_a_jour_tickets WHERE id = ?', (mise_a_jour_id,))
    conn.commit()
    conn.close()
