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

# On copie le code de notre application dans /app/app (on garde le nom du
# dossier "app" à l'intérieur, car notre code l'utilise comme un package
# Python : les imports sont écrits "from app.xxx import ...")
COPY app /app/app
WORKDIR /app

# Installation des librairies Python nécessaires (listées dans requirements.txt)
RUN pip3 install --no-cache-dir --break-system-packages -r app/requirements.txt

# Copie et rend exécutable le script de démarrage
COPY run.sh /
RUN chmod a+x /run.sh

# L'image de base utilise normalement un système de démarrage (s6-overlay)
# comme point d'entrée. On l'annule ici ("ENTRYPOINT []") pour que notre
# script run.sh soit exécuté directement, sans passer par ce système -
# c'est nécessaire pour un add-on aussi simple que le nôtre (une seule
# application), sinon on obtient l'erreur "can only run as pid 1".
ENTRYPOINT []

# Commande lancée automatiquement au démarrage de l'add-on
CMD [ "/run.sh" ]
