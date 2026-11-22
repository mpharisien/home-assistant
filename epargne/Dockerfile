# ============================================================================
# DOCKERFILE - Recette de construction de l'add-on
# ----------------------------------------------------------------------------
# Home Assistant suit cette recette pour fabriquer le « conteneur » (une sorte
# de mini-ordinateur isolé) dans lequel tourne l'application.
# ============================================================================

# Image de départ : un Linux minimal avec Python 3.12 déjà installé.
# (On n'utilise pas l'image de base Home Assistant : elle impose un système de
# démarrage spécifique, inutile pour une application aussi simple.)
FROM python:3.12-slim

# PYTHONUNBUFFERED : les messages de l'application apparaissent immédiatement
#                    dans l'onglet « Journal » de l'add-on.
# PYTHONDONTWRITEBYTECODE : évite de créer des fichiers .pyc inutiles.
# EPARGNE_BASE : emplacement de la base de données. /data est le dossier
#                persistant de l'add-on (conservé lors des mises à jour et
#                inclus dans les sauvegardes Home Assistant).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EPARGNE_BASE=/data/epargne.db

WORKDIR /opt/epargne

# On installe d'abord les librairies, puis on copie le code : ainsi, quand
# seul le code change, Docker réutilise l'étape d'installation déjà faite.
COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

COPY app app

# Lance l'application comme un module Python ("-m app.main") pour que les
# imports internes du type "from app.xxx import ..." fonctionnent.
CMD ["python", "-m", "app.main"]
