"""
Structure (schéma) de la base de données du projet.

La base de données est un simple fichier SQLite. Elle contient 3 tables :

- categories : la liste des catégories du projet, que l'utilisateur peut
  gérer (ajouter/renommer/supprimer) depuis l'interface web.

- correspondances_categories_bancaires : fait le lien entre la catégorie
  brute fournie par une banque (ex: "Alimentation" chez Boursobank) et la
  catégorie du projet correspondante. Grâce à cette table intermédiaire,
  si l'utilisateur renomme une catégorie du projet, les prochains imports
  continueront à retrouver la bonne catégorie automatiquement.

- operations : chaque dépense ou recette importée. "categorie_modifiee_
  manuellement" permet de savoir qu'une correction humaine a eu lieu sur
  cette opération, pour ne jamais l'écraser automatiquement plus tard
  (par exemple si une règle d'attribution est modifiée après coup).
"""

DEFINITION_TABLES = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS correspondances_categories_bancaires (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    banque TEXT NOT NULL,
    categorie_source TEXT NOT NULL,
    categorie_id INTEGER NOT NULL REFERENCES categories(id),
    UNIQUE(banque, categorie_source)
);

CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant_unique TEXT NOT NULL UNIQUE,
    date_operation TEXT NOT NULL,
    montant REAL NOT NULL,
    compte TEXT NOT NULL,
    banque TEXT NOT NULL,
    libelle TEXT NOT NULL,
    categorie_id INTEGER REFERENCES categories(id),
    categorie_modifiee_manuellement INTEGER NOT NULL DEFAULT 0
);
"""


def initialiser_base_de_donnees(connexion):
    """
    Crée les tables si elles n'existent pas encore.
    Ne fait rien si la base de données est déjà à jour (sans danger
    d'être appelée à chaque démarrage de l'application).
    """
    connexion.executescript(DEFINITION_TABLES)
    connexion.commit()
