"""
Point d'entrée de l'application « Épargne ».

Cette application web (Flask) remplace un fichier Google Sheets de suivi de
l'épargne. Elle est organisée en modules (« blueprints » Flask) :
  - tableau_de_bord.py : page d'accueil, total et répartition
  - pea/               : historique, portefeuille, dividendes, actions à rendement
  - poches/            : poches simples (Epsor, Enerfip...)
Les pages HTML sont dans templates/, le style et les scripts dans static/.

LANCER L'APPLICATION SUR SON PC (sans Home Assistant), depuis le dossier "epargne" :
  1. pip install -r app/requirements.txt
  2. python -m app.main
  3. ouvrir http://localhost:5000 dans un navigateur
La base de données est alors un fichier "epargne.db" créé dans le dossier
courant (il est ignoré par git : il ne sera jamais envoyé sur GitHub).
"""

import logging
import sys

from flask import Flask
from waitress import serve

from app import outils
from app.base_de_donnees import fermer_connexion, initialiser_base, obtenir_cle_secrete
from app.pea.routes import blueprint_pea
from app.poches.routes import blueprint_poches
from app.reglages import ADRESSE_ECOUTE, CHEMIN_BASE_DE_DONNEES, POCHES, PORT, TYPES_MOUVEMENT_PEA
from app.tableau_de_bord import blueprint_tableau_de_bord

journal = logging.getLogger(__name__)

# Taille maximale d'un fichier envoyé (import CSV) : 5 Mo
TAILLE_MAX_ENVOI = 5 * 1024 * 1024


def creer_application(chemin_base: str | None = None) -> Flask:
    """
    Construit l'application. `chemin_base` permet d'utiliser une autre base de
    données (utile pour les tests) ; par défaut, celle définie dans reglages.py.
    """
    application = Flask(__name__)
    chemin = chemin_base or CHEMIN_BASE_DE_DONNEES
    application.config["CHEMIN_BASE"] = chemin
    application.config["MAX_CONTENT_LENGTH"] = TAILLE_MAX_ENVOI

    initialiser_base(chemin)
    application.secret_key = obtenir_cle_secrete(chemin)
    application.teardown_appcontext(fermer_connexion)

    # Filtres utilisables dans les pages HTML, ex. {{ montant|euros }}
    application.add_template_filter(outils.format_euros, "euros")
    application.add_template_filter(outils.format_nombre, "nombre")
    application.add_template_filter(outils.format_pourcent, "pourcent")
    application.add_template_filter(outils.format_quantite, "quantite")
    application.add_template_filter(outils.format_date, "date_fr")
    application.add_template_filter(outils.format_date_heure, "date_heure_fr")

    # Variables disponibles dans toutes les pages HTML
    @application.context_processor
    def variables_communes():
        return {"POCHES": POCHES, "TYPES_MOUVEMENT_PEA": TYPES_MOUVEMENT_PEA}

    application.register_blueprint(blueprint_tableau_de_bord)
    application.register_blueprint(blueprint_pea)
    application.register_blueprint(blueprint_poches)
    return application


def lancer() -> None:
    """Démarre le serveur web (appelé au démarrage de l'add-on)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        application = creer_application()
    except RuntimeError as erreur:
        # Erreur de démarrage expliquée (ex. ancienne base incompatible) :
        # on l'affiche clairement dans le journal de l'add-on.
        journal.error("%s", erreur)
        sys.exit(1)

    journal.info("Épargne démarrée sur le port %s (base : %s)", PORT, CHEMIN_BASE_DE_DONNEES)
    serve(application, host=ADRESSE_ECOUTE, port=PORT, threads=4)


if __name__ == "__main__":
    lancer()
