# ============================================================================
# APPLICATION "Dépenses Courantes" - Point d'entrée principal
# ----------------------------------------------------------------------------
# Ce fichier lance un petit serveur web (avec la librairie Flask) qui affiche
# une page dans le navigateur. C'est volontairement très simple pour l'instant :
# le but est juste de valider que le circuit complet fonctionne
# (VS Code -> GitHub -> Home Assistant -> page web visible).
#
# On viendra progressivement enrichir ce fichier (ou le découper en plusieurs
# modules bien nommés : import_releves.py, categorisation.py, etc.) au fur
# et à mesure qu'on ajoutera des fonctionnalités.
#
# CE FICHIER PEUT AUSSI ÊTRE LANCÉ EN LOCAL SUR TON PC, SANS HOME ASSISTANT :
#   1. Ouvrir un terminal dans VS Code (menu Terminal > Nouveau terminal)
#   2. Installer Flask une seule fois :  pip install flask
#   3. Lancer l'application :            python app/main.py
#   4. Ouvrir dans un navigateur :       http://localhost:8000
# ============================================================================

from flask import Flask

# Création de l'application web
application_web = Flask(__name__)


@application_web.route("/")
def page_accueil():
    """
    Page affichée quand on ouvre l'interface web de l'add-on.
    Pour l'instant, elle sert juste à confirmer que tout fonctionne.
    """
    return (
        "<h1>Dépenses Courantes</h1>"
        "<p>L'add-on fonctionne correctement. 🎉</p>"
        "<p>Prochaine étape : import des relevés bancaires.</p>"
    )


# Ce bloc ne s'exécute que si on lance directement "python main.py"
# (que ce soit en local sur ton PC, ou dans le conteneur de l'add-on).
if __name__ == "__main__":
    # host="0.0.0.0" = accessible depuis l'extérieur du conteneur/PC (pas juste en local)
    # port=8000 = doit correspondre au port déclaré dans config.yaml
    application_web.run(host="0.0.0.0", port=8000)
