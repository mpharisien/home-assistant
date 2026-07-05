"""
Structure (schéma) de la base de données du projet.

La base de données est un simple fichier SQLite. Elle contient 4 tables :

- categories : la liste des catégories du projet, que l'utilisateur peut
  gérer (ajouter/renommer/supprimer) depuis l'interface web.

- correspondances_categories_bancaires : fait le lien entre la catégorie
  brute fournie par une banque (ex: "Alimentation" chez Boursobank) et la
  catégorie du projet correspondante. Grâce à cette table intermédiaire,
  si l'utilisateur renomme une catégorie du projet, les prochains imports
  continueront à retrouver la bonne catégorie automatiquement.

- comptes : la liste des comptes bancaires détectés. Aucun numéro de
  compte n'est jamais écrit dans le code : un compte apparaît ici tout
  seul dès qu'il est rencontré dans un import, avec le statut
  "en_attente". Tant qu'il n'est pas validé par l'utilisateur (statut
  "suivi") sur la page "Comptes", ses opérations ne sont pas importées -
  ça évite d'importer par erreur un compte non désiré (ex: une épargne).
  Un compte peut aussi être mis de côté volontairement (statut "ignore").

- operations : chaque dépense ou recette importée, rattachée à son
  compte. "categorie_modifiee_manuellement" permet de savoir qu'une
  correction humaine a eu lieu sur cette opération, pour ne jamais
  l'écraser automatiquement plus tard (ex: si une règle d'attribution
  est modifiée après coup).
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

CREATE TABLE IF NOT EXISTS comptes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant_brut TEXT NOT NULL,
    banque TEXT NOT NULL,
    nom_affiche TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'en_attente',
    UNIQUE(banque, identifiant_brut)
);

CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant_unique TEXT NOT NULL UNIQUE,
    date_operation TEXT NOT NULL,
    montant REAL NOT NULL,
    compte_id INTEGER NOT NULL REFERENCES comptes(id),
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
    _migrer_si_ancien_schema(connexion)
    connexion.executescript(DEFINITION_TABLES)
    connexion.commit()


def _migrer_si_ancien_schema(connexion):
    """
    Filet de sécurité pour la toute première mise à jour du projet : une
    version antérieure du schéma (avant l'introduction de la table
    "comptes") a pu créer une table "operations" incompatible avec la
    structure actuelle. Comme le projet n'a encore jamais servi à
    importer de vraies données à ce stade, on peut sans risque repartir
    de zéro si on détecte cette ancienne structure. Ce filet de sécurité
    pourra être retiré une fois cette transition passée.
    """
    colonnes = {ligne["name"] for ligne in connexion.execute("PRAGMA table_info(operations)")}
    if colonnes and "compte_id" not in colonnes:
        connexion.executescript("DROP TABLE IF EXISTS operations; DROP TABLE IF EXISTS comptes;")
        connexion.commit()
