CREATE TABLE IF NOT EXISTS identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL UNIQUE,
    civilite TEXT,
    nom TEXT NOT NULL,
    prenom TEXT NOT NULL,
    email TEXT NOT NULL,
    telephone TEXT NOT NULL,
    adresse TEXT,
    code_postal TEXT,
    ville TEXT,
    message_defaut TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    actif INTEGER DEFAULT 1,
    mode TEXT DEFAULT 'auto',          -- 'auto' ou 'manuel'
    sel_prenom TEXT,
    sel_nom TEXT,
    sel_email TEXT,
    sel_telephone TEXT,
    sel_code_postal TEXT,
    sel_ville TEXT,
    sel_adresse TEXT,
    sel_message TEXT,
    sel_submit TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS submissions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    identity_id INTEGER NOT NULL,
    run_at TEXT DEFAULT (datetime('now')),
    status TEXT NOT NULL,              -- 'success', 'needs_review', 'error'
    confirmation_text TEXT,
    detail TEXT,
    FOREIGN KEY (site_id) REFERENCES sites(id),
    FOREIGN KEY (identity_id) REFERENCES identities(id)
);
