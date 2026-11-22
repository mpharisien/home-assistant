"""
Accès à la base de données SQLite.

SQLite est une base de données contenue dans un simple fichier (epargne.db) :
pas de serveur à installer, et Home Assistant la sauvegarde avec l'add-on.

ÉVOLUTION DE LA STRUCTURE (« migrations ») :
La structure des tables est décrite dans la liste MIGRATIONS ci-dessous. La base
retient le numéro de la dernière migration appliquée (PRAGMA user_version). Au
démarrage, l'application applique automatiquement les migrations manquantes.

Pour faire évoluer la structure plus tard (ajouter une table, une colonne...) :
  1. NE PAS modifier une migration existante (elle a déjà été appliquée sur
     ta base de Home Assistant, elle ne serait pas rejouée).
  2. Ajouter une nouvelle migration à la fin de la liste, avec le numéro suivant,
     par exemple : (3, "ALTER TABLE actions ADD COLUMN secteur TEXT;")
Tes données existantes sont ainsi conservées.
"""

import secrets
import sqlite3

from flask import current_app, g

# ----------------------------------------------------------------------------
# Structure de la base
# ----------------------------------------------------------------------------

_MIGRATION_1 = """
-- Réglages internes de l'application (clé / valeur).
-- C'est ici qu'on pourra stocker plus tard des informations confidentielles
-- saisies dans l'application (elles ne sont jamais publiées sur GitHub).
CREATE TABLE parametres (
    cle    TEXT PRIMARY KEY,
    valeur TEXT
);

-- Actions (titres) suivies ou détenues dans le PEA.
CREATE TABLE actions (
    id          INTEGER PRIMARY KEY,
    nom         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    ticker      TEXT,                          -- symbole Yahoo Finance, ex. "TTE.PA"
    suivie      INTEGER NOT NULL DEFAULT 1,    -- 1 = affichée dans « Actions à rendement » même si non détenue
    en_evidence INTEGER NOT NULL DEFAULT 0,    -- 1 = surlignée en jaune dans ce tableau
    notes       TEXT
);

-- Dividende par action, par exercice (saisi à la main ou importé).
CREATE TABLE dividendes_exercice (
    action_id INTEGER NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
    annee     INTEGER NOT NULL,
    montant   REAL NOT NULL,
    PRIMARY KEY (action_id, annee)
);

-- Dernières données de bourse récupérées sur Yahoo Finance (une ligne par action).
CREATE TABLE cours_bourse (
    action_id          INTEGER PRIMARY KEY REFERENCES actions(id) ON DELETE CASCADE,
    cours_actuel       REAL,
    devise             TEXT,
    min_1an            REAL,
    max_1an            REAL,
    min_5ans           REAL,
    max_5ans           REAL,
    min_10ans          REAL,
    max_10ans          REAL,
    dividendes_12_mois REAL,   -- somme des dividendes détachés sur les 12 derniers mois
    date_maj           TEXT,   -- date/heure de la dernière récupération réussie
    erreur             TEXT    -- message d'erreur de la dernière tentative (NULL si OK)
);

-- Historique des dividendes détachés, tel que fourni par Yahoo Finance.
CREATE TABLE dividendes_detaches (
    action_id INTEGER NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
    date      TEXT NOT NULL,
    montant   REAL NOT NULL,
    PRIMARY KEY (action_id, date)
);

-- Historique des mouvements du PEA.
-- "montant" est toujours positif : c'est le type qui indique le sens.
--   achat    : montant débité (cours x nombre + frais)
--   vente    : montant crédité (cours x nombre - frais)
--   dividende, apport : montant crédité
--   retrait, frais    : montant débité
CREATE TABLE pea_mouvements (
    id          INTEGER PRIMARY KEY,
    date        TEXT NOT NULL,      -- format AAAA-MM-JJ
    type        TEXT NOT NULL CHECK (type IN ('achat', 'vente', 'dividende', 'apport', 'retrait', 'frais')),
    action_id   INTEGER REFERENCES actions(id) ON DELETE RESTRICT,
    quantite    REAL,
    cours       REAL,               -- cours unitaire (achat / vente uniquement)
    frais       REAL NOT NULL DEFAULT 0,
    montant     REAL NOT NULL CHECK (montant >= 0),
    commentaire TEXT
);
CREATE INDEX idx_pea_mouvements_date ON pea_mouvements (date);

-- Historique des mouvements des autres poches (Epsor, Enerfip...).
-- "poche" et "type" correspondent aux clés définies dans reglages.POCHES.
CREATE TABLE poche_mouvements (
    id          INTEGER PRIMARY KEY,
    poche       TEXT NOT NULL,
    date        TEXT NOT NULL,
    type        TEXT NOT NULL,
    libelle     TEXT,               -- fonds, projet...
    montant     REAL NOT NULL CHECK (montant >= 0),
    commentaire TEXT
);
CREATE INDEX idx_poche_mouvements ON poche_mouvements (poche, date);

-- Valeur d'une poche à une date donnée (relevée sur le site de la plateforme).
CREATE TABLE poche_valorisations (
    id     INTEGER PRIMARY KEY,
    poche  TEXT NOT NULL,
    date   TEXT NOT NULL,
    valeur REAL NOT NULL,
    UNIQUE (poche, date)
);
"""

# Version 2.1.0 : ajout du type de mouvement « remboursement ».
# La migration 1 limitait les types possibles avec un CHECK, que SQLite ne sait
# pas modifier : on recrée donc la table (en recopiant les données) sans cette
# limite. La liste des types autorisés est désormais uniquement dans
# reglages.TYPES_MOUVEMENT_PEA, et l'application la vérifie avant d'enregistrer.
# Ajouter un type plus tard ne demandera donc plus de migration.
_MIGRATION_2 = """
CREATE TABLE pea_mouvements_v2 (
    id          INTEGER PRIMARY KEY,
    date        TEXT NOT NULL,      -- format AAAA-MM-JJ
    type        TEXT NOT NULL,      -- une clé de reglages.TYPES_MOUVEMENT_PEA
    action_id   INTEGER REFERENCES actions(id) ON DELETE RESTRICT,
    quantite    REAL,
    cours       REAL,               -- cours unitaire (achat / vente uniquement)
    frais       REAL NOT NULL DEFAULT 0,
    montant     REAL NOT NULL CHECK (montant >= 0),
    commentaire TEXT
);
INSERT INTO pea_mouvements_v2 (id, date, type, action_id, quantite, cours, frais, montant, commentaire)
    SELECT id, date, type, action_id, quantite, cours, frais, montant, commentaire FROM pea_mouvements;
DROP TABLE pea_mouvements;
ALTER TABLE pea_mouvements_v2 RENAME TO pea_mouvements;
CREATE INDEX idx_pea_mouvements_date ON pea_mouvements (date);
"""

# Liste ordonnée des migrations : (numéro, script SQL). Voir l'explication en haut.
MIGRATIONS = [
    (1, _MIGRATION_1),
    (2, _MIGRATION_2),
]


# ----------------------------------------------------------------------------
# Connexions
# ----------------------------------------------------------------------------

def ouvrir_connexion(chemin: str) -> sqlite3.Connection:
    """Ouvre une connexion à la base située à `chemin`."""
    connexion = sqlite3.connect(chemin)
    # Permet d'accéder aux colonnes par leur nom : ligne["date"]
    connexion.row_factory = sqlite3.Row
    # Active le contrôle des liens entre tables (désactivé par défaut dans SQLite)
    connexion.execute("PRAGMA foreign_keys = ON")
    return connexion


def obtenir_connexion() -> sqlite3.Connection:
    """
    Renvoie la connexion à la base pour la requête web en cours.
    Elle est ouverte à la première utilisation, puis réutilisée jusqu'à la fin
    de la requête (elle est alors fermée par fermer_connexion).
    """
    if "connexion" not in g:
        g.connexion = ouvrir_connexion(current_app.config["CHEMIN_BASE"])
    return g.connexion


def fermer_connexion(_erreur=None) -> None:
    """Ferme la connexion de la requête en cours (appelé automatiquement par Flask)."""
    connexion = g.pop("connexion", None)
    if connexion is not None:
        connexion.close()


# ----------------------------------------------------------------------------
# Initialisation et migrations
# ----------------------------------------------------------------------------

def initialiser_base(chemin: str) -> None:
    """Crée la base si besoin et applique les migrations manquantes."""
    connexion = ouvrir_connexion(chemin)
    try:
        version = connexion.execute("PRAGMA user_version").fetchone()[0]

        # Sécurité : une base sans numéro de version mais contenant déjà des
        # tables vient d'une autre application (par exemple l'ancienne version
        # de cet add-on). On refuse de la modifier plutôt que de la corrompre.
        if version == 0:
            tables = connexion.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if tables:
                raise RuntimeError(
                    f"La base de données {chemin} contient déjà des tables qui ne viennent "
                    "pas de cette version de l'application (ancienne version de l'add-on ?). "
                    "Désinstalle complètement l'add-on dans Home Assistant (ce qui supprime "
                    "ses données), puis réinstalle-le."
                )

        for numero, script in MIGRATIONS:
            if numero <= version:
                continue
            try:
                # Toute la migration est appliquée d'un bloc (ou pas du tout)
                connexion.executescript(
                    f"BEGIN;\n{script}\nPRAGMA user_version = {numero};\nCOMMIT;"
                )
            except sqlite3.Error:
                connexion.rollback()
                raise
    finally:
        connexion.close()


# ----------------------------------------------------------------------------
# Paramètres internes
# ----------------------------------------------------------------------------

def lire_parametre(connexion: sqlite3.Connection, cle: str) -> str | None:
    ligne = connexion.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
    return ligne["valeur"] if ligne else None


def ecrire_parametre(connexion: sqlite3.Connection, cle: str, valeur: str) -> None:
    connexion.execute(
        "INSERT INTO parametres (cle, valeur) VALUES (?, ?) "
        "ON CONFLICT (cle) DO UPDATE SET valeur = excluded.valeur",
        (cle, valeur),
    )
    connexion.commit()


def obtenir_cle_secrete(chemin: str) -> str:
    """
    Renvoie la clé secrète utilisée par Flask pour signer les messages affichés
    après une action (« Mouvement enregistré »...).
    Elle est générée au hasard au premier démarrage et stockée dans la base :
    elle ne doit pas être écrite dans le code, puisque celui-ci est public.
    """
    connexion = ouvrir_connexion(chemin)
    try:
        cle = lire_parametre(connexion, "cle_secrete")
        if cle is None:
            cle = secrets.token_hex(32)
            ecrire_parametre(connexion, "cle_secrete", cle)
        return cle
    finally:
        connexion.close()
