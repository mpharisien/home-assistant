# ============================================================================
# DOCKERFILE - Recette de construction de l'add-on
# ----------------------------------------------------------------------------
# Ce fichier décrit, étape par étape, comment fabriquer l'environnement dans
# lequel notre application va tourner : quels logiciels installer, quels
# fichiers copier, et quelle commande lancer au démarrage.
# ============================================================================

# Image de base définie dans build.yaml
ARG BUILD_FROM
FROM $BUILD_FROM

# Installation de Python (le langage utilisé pour notre application)
RUN apk add --no-cache python3 py3-pip

# On copie le code de notre application dans le dossier /app du conteneur
COPY app /app
WORKDIR /app

# Installation des librairies Python nécessaires (listées dans requirements.txt)
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copie et rend exécutable le script de démarrage
COPY run.sh /
RUN chmod a+x /run.sh

# Commande lancée automatiquement au démarrage de l'add-on
CMD [ "/run.sh" ]
