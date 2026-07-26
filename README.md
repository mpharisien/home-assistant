# Devis Filler — Add-on Home Assistant

Add-on avec interface web (accessible depuis le menu latéral de Home Assistant)
pour remplir automatiquement des formulaires de demande de devis/rappel.

## Installation via votre dépôt GitHub

1. **Uploadez ce contenu sur GitHub**, dans `https://github.com/mpharisien/home-assistant` :
   - Le fichier `repository.yaml` doit être **à la racine** du repo (pas dans un sous-dossier)
   - Le dossier `devis_filler/` (avec tout son contenu) doit aussi être **à la racine**

   Structure finale attendue sur GitHub :
   ```
   home-assistant/
     repository.yaml
     devis_filler/
       config.yaml
       Dockerfile
       run.sh
       requirements.txt
       README.md
       app/
         app.py
         automation.py
         db.py
         schema.sql
         templates/...
         static/style.css
   ```

   Le plus simple si vous n'avez pas Git en local : sur la page GitHub du repo,
   bouton **"Add file" → "Upload files"**, puis glissez-déposez tout
   (en conservant l'arborescence des dossiers).

2. **Dans Home Assistant** :
   - Réglages → Add-ons → **Boutique des add-ons** (Add-on Store)
   - En haut à droite → ⋮ (menu) → **Dépôts** (Repositories)
   - Collez : `https://github.com/mpharisien/home-assistant` → Ajouter
   - Fermez, puis rafraîchissez la page si besoin

3. Un nouveau dépôt apparaît dans la liste avec **"Devis Filler"** dedans.
   Cliquez dessus → **Installer** (la première installation prend plusieurs
   minutes : elle télécharge Chromium pour Playwright).

4. Une fois installé → **Démarrer**. Activez "Afficher dans le menu latéral"
   pour un accès direct depuis la sidebar.

## Utilisation

L'interface propose 3 pages :

- **Accueil** : sélectionnez une identité (vous / votre femme) et cliquez
  "Soumettre" → suivi en direct de la progression, site par site.
- **Sites** : ajoutez vos sites de devis (URL + nom des champs si besoin),
  voyez le statut du dernier passage (✅ confirmé / ⚠️ à vérifier / ❌ erreur).
- **Identités** : ajoutez/modifiez vos informations personnelles.

### Ajouter un site

- **Mode automatique** : laissez les champs vides, l'add-on essaie de deviner
  tout seul (nom, prénom, email, téléphone, message) en analysant la page.
- **Mode manuel** : si l'automatique échoue (site marqué "à vérifier" après un
  essai), passez en mode manuel et indiquez le sélecteur CSS de chaque champ.
  Pour le trouver : ouvrez le formulaire dans Chrome, clic droit sur le champ →
  Inspecter → repérez l'attribut `id` ou `name` → utilisez `#id_du_champ` ou
  `input[name=nom_du_champ]`.

## Mettre à jour l'add-on plus tard

Après une modification du code sur GitHub :
Réglages → Add-ons → Boutique des add-ons → ⋮ → **Recharger**, puis
réinstallez/mettez à jour "Devis Filler" comme n'importe quel add-on.

## Les données sont conservées

Tout est stocké dans `/data/devis.db` à l'intérieur de l'add-on — ce dossier
est persistant (il survit aux mises à jour et redémarrages de l'add-on).

## Limites à connaître

- Les **captchas** ne peuvent pas être contournés automatiquement ; ces sites
  resteront en "à vérifier".
- Si un site change de structure, il apparaîtra en erreur au prochain
  passage — sans bloquer le traitement des autres sites.
- Pour un lancement automatique périodique (ex: chaque semaine), vous pouvez
  créer une automation Home Assistant qui appelle `http://localhost:8099/run`
  (POST, paramètre `identity_label`) via un `rest_command`.
