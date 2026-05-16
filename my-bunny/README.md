# 🐰 My Bunny

Add-on Home Assistant pour suivre la santé et le bien-être de votre lapin.

## 📋 Fonctionnalités

- ⚖️ **Poids** — Enregistrer et suivre l'évolution du poids
- 🏥 **Vétérinaire** — Gérer les rendez-vous et vaccins
- 📓 **Journal** — Noter les observations quotidiennes
- 🌡️ **Température** — Suivi de la température et humidité de la pièce

## 🚀 Installation

### 1. Ajouter le dépôt
Dans Home Assistant :
- Paramètres → Add-ons → Boutique des add-ons
- Menu ⋮ → Dépôts
- Ajouter : `https://github.com/TON_USERNAME/TON_REPO`

### 2. Installer l'add-on
- Chercher **My Bunny** dans la boutique
- Cliquer **Installer**
- Cliquer **Démarrer**

### 3. Ouvrir l'interface
- Cliquer **Ouvrir l'interface web**
- Ou aller sur `http://homeassistant.local:4000`

## 📁 Structure
my-bunny/
├── app/
│   ├── app.py              # Application Flask principale
│   ├── requirements.txt    # Dépendances Python
│   └── templates/          # Pages HTML
│       ├── base.html
│       ├── index.html
│       ├── poids.html
│       ├── veterinaire.html
│       ├── journal.html
│       └── temperature.html
├── config.json             # Configuration add-on HA
├── Dockerfile              # Image Docker
└── README.md


## 🔧 Données

Les données sont stockées dans `/share/my_bunny/` sur Home Assistant.
Elles sont conservées même après une mise à jour de l'add-on.

