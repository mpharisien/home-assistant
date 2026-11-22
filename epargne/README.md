# Épargne

Add-on Home Assistant qui remplace un fichier Google Sheets de suivi de l'épargne.
Interface web accessible sur le réseau local : `http://<adresse-de-home-assistant>:5000/`

## Fonctionnalités

- **Tableau de bord** : épargne totale, valeur de chaque poche, graphiques de répartition.
- **PEA** (actions à rendement)
  - *Portefeuille* : actions détenues, prix de revient unitaire (PRU), valeur au cours actuel,
    plus-value latente, liquidités.
  - *Historique* : achats, ventes, dividendes, ajouts / retraits de liquidités, frais, remboursements.
  - *Dividendes* : dividendes reçus par année et par action, avec le rendement sur le prix de revient.
  - *Actions à rendement* : cours, plus bas et plus hauts sur 1, 5 et 10 ans (Yahoo Finance),
    dividendes par exercice, moyenne, tendance, rendement et « taux de décision ».
  - *Import* : reprise des onglets du Google Sheet exportés en CSV.
- **Epsor** (épargne salariale) et **Enerfip** (financement participatif) : historique des
  mouvements et valorisations saisies à la main.

## Données et confidentialité

- Les données sont stockées dans une base SQLite : `/data/epargne.db` sur Home Assistant.
  Ce dossier est conservé lors des mises à jour et inclus dans les sauvegardes Home Assistant.
- Ce dépôt est **public** : aucune donnée personnelle ne doit y figurer. Les informations
  confidentielles se saisissent dans l'application (elles restent dans la base, sur Home Assistant).
- L'interface n'a pas de mot de passe : elle est accessible à tout appareil du réseau local.

## Technologies (et pourquoi)

| Élément | Choix | Raison |
|---|---|---|
| Langage | Python 3.12 | Simple à lire, très répandu |
| Application web | Flask + Waitress | Léger, idéal pour des pages HTML et des formulaires ; déjà utilisé dans les autres add-ons du dépôt |
| Base de données | SQLite | Un simple fichier, sans serveur, sauvegardé avec l'add-on |
| Pages | HTML (modèles Jinja), CSS, un peu de JavaScript | Pas d'outil de compilation à installer |
| Graphiques | Chart.js (fichier inclus dans `app/static`) | Fonctionne sans accès à Internet |
| Cours de bourse | Yahoo Finance (service public des graphiques) | Gratuit, sans compte |

## Structure des fichiers

```
epargne/
├── config.yaml          Carte d'identité de l'add-on (nom, version, port)
├── Dockerfile           Recette de construction de l'add-on
├── CHANGELOG.md         Historique des versions
├── app/
│   ├── main.py          Point d'entrée : crée l'application et démarre le serveur
│   ├── reglages.py      Réglages : chemin de la base, types de mouvements, poches...
│   ├── base_de_donnees.py  Connexion SQLite et structure des tables (migrations)
│   ├── outils.py        Lecture des nombres/dates saisis, mise en forme à la française
│   ├── bourse_yahoo.py  Récupération des cours sur Yahoo Finance
│   ├── tableau_de_bord.py  Page d'accueil
│   ├── pea/             Module PEA : donnees.py (SQL), calculs.py, routes.py (pages), import_csv.py
│   ├── poches/          Poches simples (Epsor, Enerfip) : calculs.py, routes.py
│   ├── templates/       Pages HTML
│   └── static/          Style (CSS), script (JS), Chart.js
└── tests/               Tests automatiques
```

## Faire évoluer le projet

- **Modifier une page** : `app/templates/...` (HTML) et `app/static/style.css`.
- **Ajouter une poche simple** : ajouter une entrée dans `POCHES` (`app/reglages.py`).
- **Modifier la structure de la base** : ajouter une migration à la fin de `MIGRATIONS`
  (`app/base_de_donnees.py`), sans modifier les précédentes. Les données existantes sont conservées.
- **Publier une nouvelle version** : augmenter `version` dans `config.yaml`, noter les changements
  dans `CHANGELOG.md`, envoyer sur GitHub, puis mettre à jour l'add-on dans Home Assistant.

## Lancer l'application sur son PC (facultatif)

Nécessite Python 3.12 ou plus. Depuis le dossier `epargne` :

```bash
pip install -r app/requirements.txt
python -m app.main                          # puis ouvrir http://localhost:5000
python -m unittest discover -s tests -t .   # lancer les tests
```

En local, la base est un fichier `epargne.db` créé dans le dossier courant ; il est exclu de git
(voir `.gitignore`) et ne sera donc jamais publié.
