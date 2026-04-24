const express = require('express');
const fetch = require('node-fetch');
const path = require('path');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const HA_URL = (process.env.HA_URL || 'http://supervisor/core') + '/api';
const HA_TOKEN = process.env.HA_TOKEN || process.env.SUPERVISOR_TOKEN;

// DEBUG - à retirer après
console.log('HA_URL:', HA_URL);
console.log('HA_TOKEN défini:', HA_TOKEN ? 'OUI (longueur: ' + HA_TOKEN.length + ')' : 'NON - VIDE');

const TACHES = [
  { id: 'input_boolean.re_matin_manger',   label: '🍳 Manger' },
  { id: 'input_boolean.re_matin_habiller', label: '👕 S\'habiller' },
  { id: 'input_boolean.re_matin_dents',    label: '🦷 Se laver les dents' },
  { id: 'input_boolean.re_matin_sac',      label: '🎒 Vérifier le sac' },
  { id: 'input_boolean.re_matin_papa',     label: '⏳ Laisser papa se préparer' },
];

// Récupère l'état de toutes les tâches
app.get('/api/taches', async (req, res) => {
  try {
    const etats = await Promise.all(TACHES.map(async (tache) => {
      const response = await fetch(`${HA_URL}/api/states/${tache.id}`, {
        headers: { Authorization: `Bearer ${HA_TOKEN}` }
      });
      const data = await response.json();
      return { ...tache, etat: data.state === 'on' };
    }));
    res.json(etats);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Bascule une tâche (on/off)
app.post('/api/taches/:entityId/toggle', async (req, res) => {
  const { entityId } = req.params;
  try {
    await fetch(`${HA_URL}/api/services/input_boolean/toggle`, {
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
