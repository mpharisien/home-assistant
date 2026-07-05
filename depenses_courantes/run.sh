#!/usr/bin/env bash
# ============================================================================
# SCRIPT DE DÉMARRAGE
# ----------------------------------------------------------------------------
# C'est la toute première chose exécutée quand l'add-on démarre.
# ============================================================================

# /data est le dossier persistant propre à cet add-on : il survit aux
# redémarrages et aux mises à jour de l'add-on (contrairement au reste
# du conteneur, qui repart de zéro à chaque mise à jour).
export CHEMIN_BASE_DE_DONNEES="/data/depenses.db"

python3 /app/main.py
