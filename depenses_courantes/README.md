# Dépenses Courantes

Add-on Home Assistant qui regroupe et analyse les dépenses de la famille sur
plusieurs comptes bancaires (Crédit Agricole, Boursobank).

## Objectif du projet

- Importer les relevés de plusieurs comptes bancaires
- Les uniformiser dans un format commun
- Les stocker dans une base de données locale
- Les afficher et les analyser via une interface web (graphiques, catégories, prédictions)

## Comptes suivis (v0.1)

- Crédit Agricole : compte courant, compte courant joint
- Boursobank : compte courant, compte courant joint

(Les comptes d'épargne et d'investissement long terme ne sont pas suivis
dans cet add-on pour l'instant.)

## État actuel du projet

- [x] Squelette de l'add-on fonctionnel (page web de test)
- [ ] Import des relevés bancaires
- [ ] Catégorisation des dépenses
- [ ] Stockage en base de données
- [ ] Tableaux de bord / graphiques
- [ ] Prédictions

## Développement en local (sans Home Assistant)

```bash
cd depenses_courantes
pip install -r app/requirements.txt
python -m app.main
```

Puis ouvrir http://localhost:8000 dans un navigateur.

## Structure des fichiers

| Fichier          | Rôle                                                        |
|-------------------|-------------------------------------------------------------|
| `config.yaml`      | Carte d'identité de l'add-on pour Home Assistant             |
| `build.yaml`       | Image Docker de base utilisée                               |
| `Dockerfile`       | Recette de construction de l'add-on                          |
| `run.sh`           | Script lancé au démarrage de l'add-on                        |
| `app/main.py`      | Application web principale                                   |
| `app/requirements.txt` | Librairies Python nécessaires                            |
