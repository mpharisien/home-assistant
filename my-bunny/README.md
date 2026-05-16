# My Bunny - Tableau de bord Home Assistant

Ce projet gère le suivi de santé de Noisette, notre lapin.

## Structure
- `bunny_entities.yaml` : Entrées utilisateur (poids, dates, etc.)
- `bunny_sensors.yaml` : Capteurs (température, humidité)
- `bunny_templates.yaml` : Calculs automatiques (rappels)
- `bunny_dashboard.yaml` : Tableau de bord Lovelace

## Configuration requise
1. Intégration Tuya déjà configurée pour le capteur "Thermo bureau kos".
2. Les entités suivantes doivent exister :
   - `sensor.thermo_bureau_kos_temperature`
   - `sensor.thermo_bureau_kos_humidite`
   - `sensor.thermo_bureau_kos_etat_batterie`

## Notes
- Tout commence par `bunny_` pour une identification facile.
- Pour ajouter un événement (vaccin, visite vétérinaire), utilise les entrées dans **Outils > Aides**.
