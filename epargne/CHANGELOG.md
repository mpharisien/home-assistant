# Historique des versions

## 2.1.0

- PEA : nouveau type de mouvement « Remboursement » (frais ou taxe remboursés, capital rendu
  par une société). Il augmente les liquidités sans compter comme un versement ; s'il concerne
  une action, il diminue son prix de revient. Reconnu aussi par l'import CSV.
- Actions à rendement : la colonne « Symbole » est retirée (visible au survol du nom) ; une ligne
  au-dessus des titres indique l'origine des colonnes (Yahoo Finance, tes données, calculs).
- Base de données : la table des mouvements du PEA est recréée automatiquement au démarrage
  (données conservées) pour accepter le nouveau type.

## 2.0.0

Nouvelle version écrite de zéro (l'ancienne version 1.x et ses données ne sont pas reprises).

- Tableau de bord : total, valeur par poche, répartition par poche et du PEA.
- PEA : portefeuille (PRU, plus-values, liquidités), historique, dividendes par année,
  tableau des actions à rendement avec données Yahoo Finance, import CSV depuis Google Sheets.
- Epsor et Enerfip : historique des mouvements et valorisations.
