"""
Structure (schéma) de la base de données du projet.

La base de données est un simple fichier SQLite. Elle contient 5 tables :

- categories : la liste des catégories du projet. "couleur" forme son
  identité visuelle (étiquette colorée), modifiable depuis la page
  "Catégories".

- correspondances_categories_bancaires : fait le lien entre la catégorie
  brute fournie par une banque (ex: "Alimentation" chez Boursobank) et la
  catégorie du projet correspondante. Grâce à cette table intermédiaire,
  si l'utilisateur renomme une catégorie du projet, les prochains imports
  continueront à retrouver la bonne catégorie automatiquement.

- regles_attribution_automatique : des règles "si le libellé contient ce
  mot-clé, alors telle catégorie". Un mot-clé ne peut appartenir qu'à une
  seule catégorie à la fois (contrainte d'unicité). Ces règles sont
  volontairement prioritaires sur la catégorie fournie par la banque
  (voir app/base_de_donnees/gestion_categories.py pour le détail).

- comptes : la liste des comptes bancaires détectés. Aucun numéro de
  compte n'est jamais écrit dans le code : un compte apparaît ici tout
  seul, immédiatement suivi ("statut" = "suivi"), dès qu'il est
  rencontré dans un import. L'utilisateur peut ensuite le mettre de
  côté ("statut" = "ignore", ce qui supprime aussi ses opérations déjà
  importées) s'il ne souhaite pas le suivre (ex: un compte d'épargne).
  "couleur" et "lettre" forment l'identité visuelle du compte, affichée
  en plus court partout où le nom complet prendrait trop de place.

- operations : chaque dépense ou recette importée, rattachée à son
  compte. "categorie_modifiee_manuellement" permet de savoir qu'une
  correction humaine a eu lieu sur cette opération, pour ne jamais
  l'écraser automatiquement plus tard (ex: si une règle d'attribution
  est modifiée après coup).
"""

DEFINITION_TABLES = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL UNIQUE,
    couleur TEXT NOT NULL DEFAULT '#6a2c91',
    exclu_des_statistiques INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS correspondances_categories_bancaires (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    banque TEXT NOT NULL,
    categorie_source TEXT NOT NULL,
    categorie_id INTEGER NOT NULL REFERENCES categories(id),
    UNIQUE(banque, categorie_source)
);

CREATE TABLE IF NOT EXISTS regles_attribution_automatique (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mot_cle TEXT NOT NULL UNIQUE,
    categorie_id INTEGER NOT NULL REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS comptes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant_brut TEXT NOT NULL,
    banque TEXT NOT NULL,
    nom_affiche TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'suivi',
    couleur TEXT NOT NULL DEFAULT '#6a2c91',
    lettre TEXT NOT NULL DEFAULT '?',
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
    Crée les tables si elles n'existent pas encore, et applique les
    petites migrations nécessaires sur une base de données existante
    (ajout de colonnes, sans jamais toucher aux données déjà présentes).
    """
    connexion.executescript(DEFINITION_TABLES)
    _migrer_identite_visuelle_comptes(connexion)
    _migrer_suppression_statut_en_attente(connexion)
    _migrer_couleur_categories(connexion)
    _creer_categorie_virements_internes_si_absente(connexion)
    _migrer_exclusion_statistiques_categories(connexion)
    connexion.commit()


def _creer_categorie_virements_internes_si_absente(connexion):
    """
    Pré-crée une catégorie "Virements internes", destinée à classer les
    mouvements d'argent entre tes propres comptes (ex: Crédit Agricole
    vers Boursobank) - à utiliser dès maintenant manuellement, en
    attendant une future détection automatique de ces virements.
    """
    existe_deja = connexion.execute(
        "SELECT id FROM categories WHERE nom = 'Virements internes'"
    ).fetchone()
    if existe_deja is None:
        connexion.execute(
            "INSERT INTO categories (nom, couleur) VALUES ('Virements internes', '#4a3f9e')"
        )


def _migrer_exclusion_statistiques_categories(connexion):
    """
    Ajoute la colonne "exclu_des_statistiques" à la table "categories"
    si elle n'existe pas encore. Une catégorie marquée ainsi continue
    d'apparaître normalement dans les listes d'opérations, mais ses
    montants sont ignorés dans tous les calculs du Dashboard (dépenses,
    recettes, soldes...) - utile pour les mouvements qui ne représentent
    pas une vraie dépense/recette personnelle (virements entre tes
    propres comptes, remboursements de proches...).

    "Virements internes" est systématiquement marquée ainsi : c'est sa
    raison d'être, que la colonne vienne d'être ajoutée ou non.
    """
    colonnes = {ligne["name"] for ligne in connexion.execute("PRAGMA table_info(categories)")}

    if "exclu_des_statistiques" not in colonnes:
        connexion.execute(
            "ALTER TABLE categories ADD COLUMN exclu_des_statistiques INTEGER NOT NULL DEFAULT 0"
        )

    connexion.execute(
        "UPDATE categories SET exclu_des_statistiques = 1 WHERE nom = 'Virements internes'"
    )


def _migrer_identite_visuelle_comptes(connexion):
    """
    Ajoute les colonnes "couleur" et "lettre" à la table "comptes" si
    elles n'existent pas encore (base de données créée avant leur
    introduction). Les comptes déjà existants reçoivent une valeur par
    défaut cohérente (couleur selon la banque, lettre = initiale du nom)
    plutôt que la valeur générique utilisée le temps de la migration.
    """
    colonnes = {ligne["name"] for ligne in connexion.execute("PRAGMA table_info(comptes)")}

    if "couleur" not in colonnes:
        connexion.execute("ALTER TABLE comptes ADD COLUMN couleur TEXT NOT NULL DEFAULT '#6a2c91'")
    if "lettre" not in colonnes:
        connexion.execute("ALTER TABLE comptes ADD COLUMN lettre TEXT NOT NULL DEFAULT '?'")

    if colonnes and ("couleur" not in colonnes or "lettre" not in colonnes):
        connexion.execute(
            "UPDATE comptes SET couleur = '#1a8a4c' WHERE banque = 'Crédit Agricole' AND couleur = '#6a2c91'"
        )
        connexion.execute(
            "UPDATE comptes SET couleur = '#0d3b73' WHERE banque = 'Boursobank' AND couleur = '#6a2c91'"
        )
        connexion.execute("UPDATE comptes SET lettre = UPPER(SUBSTR(nom_affiche, 1, 1)) WHERE lettre = '?'")


def _migrer_suppression_statut_en_attente(connexion):
    """
    Le statut "en_attente" a été retiré du projet : un compte est
    maintenant immédiatement suivi dès sa détection. Les comptes qui
    étaient restés sur cet ancien statut (créé par une version
    antérieure) basculent simplement en "suivi".
    """
    connexion.execute("UPDATE comptes SET statut = 'suivi' WHERE statut = 'en_attente'")


def _migrer_couleur_categories(connexion):
    """
    Ajoute la colonne "couleur" à la table "categories" si elle
    n'existe pas encore. Les catégories déjà existantes reçoivent
    chacune une couleur différente (en tournant dans la palette, dans
    l'ordre de création) plutôt que la valeur générique utilisée le
    temps de la migration.
    """
    # Import local pour éviter une dépendance circulaire au chargement du module
    from app.base_de_donnees.palette_couleurs import obtenir_couleur_par_rang

    colonnes = {ligne["name"] for ligne in connexion.execute("PRAGMA table_info(categories)")}

    if "couleur" not in colonnes:
        connexion.execute("ALTER TABLE categories ADD COLUMN couleur TEXT NOT NULL DEFAULT '#6a2c91'")

        lignes = connexion.execute("SELECT id FROM categories ORDER BY id").fetchall()
        for rang, ligne in enumerate(lignes):
            connexion.execute(
                "UPDATE categories SET couleur = ? WHERE id = ?",
                (obtenir_couleur_par_rang(rang), ligne["id"]),
            )
