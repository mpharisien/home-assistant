# 🩺 Carnet de santé

Add-on Home Assistant pour suivre la santé de plusieurs membres de la famille (enfant et adulte).

## 📋 Fonctionnalités

- 👤 **Profil** — Fiche par individu (identité, groupe sanguin, allergies, antécédents, diagnostics) + gestion multi-profils
- ⚖️ **Poids** — Suivi et graphique d'évolution
- 📏 **Taille** — Suivi et graphique d'évolution
- 🦷 **Dents** — Suivi de la chute des dents
- 📅 **Examens** — Liste des examens récurrents à surveiller (dentiste, généraliste, etc.), pré-remplie avec 8 examens courants, fréquence exprimée en mois et modifiable, avec la date de dernière réalisation par individu
- 📓 **Historique** — Journal des événements de santé (RDV médicaux, etc.)
- 🧩 **Problèmes de santé chroniques** — Module à venir

## 🚀 Installation

### 1. Ajouter le dépôt
Dans Home Assistant :
- Paramètres → Add-ons → Boutique des add-ons
- Menu ⋮ → Dépôts
- Ajouter : `https://github.com/mpharisien/home-assistant`

### 2. Installer l'add-on
- Chercher **Carnet de santé** dans la boutique
- Cliquer **Installer**
- Cliquer **Démarrer**

### 3. Ouvrir l'interface
- Cliquer **Ouvrir l'interface web**
- Ou aller sur `http://homeassistant.local:4200`

## 📁 Structure
```
carnet-de-sante/
├── app/
│   ├── app.py              # Application Flask principale
│   ├── requirements.txt    # Dépendances Python
│   └── templates/          # Pages HTML
│       ├── base.html
│       ├── index.html
│       ├── individu.html
│       ├── supprimer_individu.html
│       ├── poids.html
│       ├── taille.html
│       ├── dents.html
│       ├── examens.html
│       ├── historique.html
│       └── problemes.html
├── config.json              # Configuration add-on HA
├── Dockerfile                # Image Docker
└── README.md
```

## 🔧 Données

Les données sont stockées dans `/share/carnet_de_sante/` sur Home Assistant.
Elles sont conservées même après une mise à jour de l'add-on.

## 🗂️ Modèle de données

- `individu` : fiche d'identité de chaque personne suivie (inclut date et heure de naissance)
- `individu_actif` : mémorise quel profil est actuellement affiché
- `poids`, `taille`, `dents` : mesures liées à un individu
- `type_examen` : liste commune des types d'examens récurrents à surveiller, avec une fréquence exprimée en mois (pré-remplie avec 8 examens courants au premier démarrage)
- `suivi_examen` : date de dernière réalisation d'un type d'examen, par individu
- `evenement` : historique libre des événements de santé
