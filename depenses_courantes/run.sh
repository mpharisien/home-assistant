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

# On lance l'application comme un module Python ("-m app.main") et non
# comme un simple script : c'est nécessaire pour que les imports internes
# du type "from app.xxx import ..." fonctionnent correctement.
python3 -m app.main
