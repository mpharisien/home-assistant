const express = require('express');
const fetch = require('node-fetch');
const path = require('path');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const HA_URL = (process.env.HA_URL || 'http://supervisor/core');
const HA_TOKEN = process.env.HA_TOKEN || process.env.SUPERVISOR_TOKEN;

// DEBUG - à retirer après
console.log('HA_URL:', HA_URL);
console.log('HA_TOKEN défini:', HA_TOKEN ? 'OUI (longueur: ' + HA_TOKEN.length + ')' : 'NON - VIDE');

const TACHES = [
  { id: 'input_boolean.re_matin_manger',   label: 'Manger',                   icone: '🍳' },
  { id: 'input_boolean.re_matin_habiller', label: "S'habiller",               icone: '👕' },
  { id: 'input_boolean.re_matin_dents',    label: 'Laver les dents',       icone: '🦷' },
  { id: 'input_boolean.re_matin_sac',      label: 'Vérifier le sac',          icone: '🎒' },
  { id: 'input_boolean.re_matin_papa',     label: 'Laisser papa se préparer', icone: '⏳' },
];

// Récupère l'état de toutes les tâches
app.get('/api/taches', async (req, res) => {
  try {
    const etats = await Promise.all(TACHES.map(async (tache) => {
      const url = `${HA_URL}/api/states/${tache.id}`;
      console.log('Appel URL:', url);
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${HA_TOKEN}` }
      });
      console.log('Status HTTP:', response.status);
      const text = await response.text();
      console.log('Réponse brute:', text.substring(0, 200));
      const data = JSON.parse(text);
      return { ...tache, etat: data.state === 'on' };
    }));
    res.json(etats);
  } catch (err) {
    console.log('ERREUR:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// Bascule une tâche (on/off)
app.post('/api/taches/:entityId/toggle', async (req, res) => {
  const { entityId } = req.params;
  try {
    await fetch(`${HA_URL}/services/input_boolean/toggle`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${HA_TOKEN}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ entity_id: entityId })
    });
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(3000, () => console.log('Routine Enfant démarré sur le port 3000'));
