"""
Réglages généraux de l'application.

On regroupe ici les valeurs « fixes » utilisées un peu partout, pour pouvoir
les modifier à un seul endroit.

ATTENTION : ce fichier est publié sur GitHub (dépôt public). Ne jamais y écrire
d'information personnelle ou confidentielle (numéro de compte, etc.). Ce type
d'information doit être saisi dans l'application : il est alors stocké dans la
base de données, qui reste sur Home Assistant.
"""

import os
from zoneinfo import ZoneInfo

# --- Base de données ---------------------------------------------------------
# Sur Home Assistant, le Dockerfile définit EPARGNE_BASE=/data/epargne.db.
# En local (sur ton PC), cette variable n'existe pas : on utilise alors un
# simple fichier "epargne.db" dans le dossier courant (ignoré par git).
CHEMIN_BASE_DE_DONNEES = os.environ.get("EPARGNE_BASE", "epargne.db")

# --- Serveur web -------------------------------------------------------------
# 0.0.0.0 = accepter les connexions venant des autres machines du réseau local
ADRESSE_ECOUTE = "0.0.0.0"
PORT = int(os.environ.get("EPARGNE_PORT", "5000"))

FUSEAU_HORAIRE = ZoneInfo("Europe/Paris")

# --- PEA : types de mouvements -----------------------------------------------
# Clé = valeur stockée en base (ne pas modifier), valeur = libellé affiché.
TYPES_MOUVEMENT_PEA = {
    "achat": "Achat",
    "vente": "Vente",
    "dividende": "Dividende",
    "apport": "Ajout de liquidités",
    "retrait": "Retrait de liquidités",
    "frais": "Frais / taxes",
    # Argent rendu sur le PEA qui n'est ni un versement de ta part, ni un
    # dividende : frais ou taxe remboursés, capital rendu par une société...
    # S'il concerne une action, il diminue son prix de revient.
    "remboursement": "Remboursement",
}
# Types de mouvements qui concernent obligatoirement une action précise
TYPES_AVEC_ACTION = ("achat", "vente", "dividende")
# Types pour lesquels l'action est facultative
TYPES_ACTION_FACULTATIVE = ("remboursement",)

# --- PEA : tableau « Actions à rendement » -----------------------------------
# Avec N = année en cours, on affiche les dividendes de N-4 à N+1
# (en 2026 : de 2022 à 2027, comme dans le Google Sheet d'origine).
DIVIDENDES_ANNEES_AVANT = 4
DIVIDENDES_ANNEES_APRES = 1
# La moyenne des dividendes est calculée sur N-2 à N+1 (en 2026 : 2024 à 2027),
# en ne prenant que les années renseignées.
MOYENNE_ANNEES_AVANT = 2
# Tendance (même règle que le Google Sheet, vérifiée sur toutes ses lignes) :
# on compare la moyenne des dividendes de N et N+1 (en 2026 : 2026-2027) à la
# moyenne des années précédentes affichées (2022-2025). Au-delà de +5 % : hausse,
# en dessous de -5 % : baisse, sinon stable (5 % = 0.05).
SEUIL_TENDANCE = 0.05

# --- Autres poches d'épargne -------------------------------------------------
# Les poches « simples » (Epsor, Enerfip) partagent le même fonctionnement :
# un historique de mouvements + des valorisations saisies à la main.
#
# Chaque type de mouvement a un « effet » qui sert aux calculs :
#   - "apport"  : argent versé dans la poche (augmente le capital investi)
#   - "retrait" : argent qui sort de la poche (diminue le capital investi)
#   - "revenu"  : gain perçu (intérêts...), compté à part
#   - "charge"  : frais, impôts, compté à part
#   - "neutre"  : simple information (ex. arbitrage entre deux fonds)
#
# Pour ajouter une poche, il suffit d'ajouter une entrée ici : le menu, les
# pages et le tableau de bord la prendront en compte automatiquement.
POCHES = {
    "epsor": {
        "nom": "Epsor",
        "description": "Épargne salariale (PEE, PERECO…)",
        "libelle_support": "Fonds / support",
        "types": {
            "versement": {"libelle": "Versement volontaire", "effet": "apport"},
            "interessement": {"libelle": "Intéressement", "effet": "apport"},
            "participation": {"libelle": "Participation", "effet": "apport"},
            "abondement": {"libelle": "Abondement employeur", "effet": "apport"},
            "retrait": {"libelle": "Retrait / déblocage", "effet": "retrait"},
            "arbitrage": {"libelle": "Arbitrage entre fonds", "effet": "neutre"},
            "frais": {"libelle": "Frais", "effet": "charge"},
        },
    },
    "enerfip": {
        "nom": "Enerfip",
        "description": "Financement participatif (énergies renouvelables)",
        "libelle_support": "Projet",
        "types": {
            "investissement": {"libelle": "Investissement dans un projet", "effet": "apport"},
            "remboursement": {"libelle": "Remboursement de capital", "effet": "retrait"},
            "interets": {"libelle": "Intérêts reçus", "effet": "revenu"},
            "impots": {"libelle": "Impôts / prélèvements sociaux", "effet": "charge"},
        },
    },
}
