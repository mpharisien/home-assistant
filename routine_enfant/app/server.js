const express = require('express');
const fetch = require('node-fetch');
const path = require('path');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const HA_URL = (process.env.HA_URL || 'http://supervisor/core') + '/api';
const HA_TOKEN = process.env.HA_TOKEN || process.env.SUPERVISOR_TOKEN;

const ROUTINES = {
  matin: {
    id: 'matin',
    titre: 'Routine du matin',
    departLabel: 'Départ à 8h10',
    departH: 8, departM: 10,
    taches: [
      { id: 'input_boolean.re_matin_manger',   label: 'Manger',                   icone: '🍳' },
      { id: 'input_boolean.re_matin_habiller', label: "S'habiller",               icone: '👕' },
      { id: 'input_boolean.re_matin_dents',    label: 'Se laver les dents',       icone: '🦷' },
      { id: 'input_boolean.re_matin_sac',      label: 'Vérifier le sac',          icone: '🎒' },
      { id: 'input_boolean.re_matin_papa',     label: 'Laisser papa se préparer', icone: '⏳' },
    ]
  },
  ecole: {
    id: 'ecole',
    titre: 'Retour de l\'école',
    taches: [
      { id: 'input_boolean.re_ecole_chaussures', label: 'Ranger chaussures et manteau', icone: '👟' },
      { id: 'input_boolean.re_ecole_mains',      label: 'Se laver les mains',           icone: '🧼' },
      { id: 'input_boolean.re_ecole_gouter',     label: 'Goûter',                       icone: '🍎' },
      { id: 'input_boolean.re_ecole_devoirs',    label: 'Faire les devoirs',            icone: '📚' },
    ]
  },
  soir: {
    id: 'soir',
    titre: 'Bonsoir !',
    taches: [
      { id: 'media_player.shield_2',             label: 'Fin de la TV',                 icone: '📺', special: 'tv', finH: 19, finM: 40 },
      { id: 'input_boolean.re_soir_manger',      label: 'Finir de manger',              icone: '🍽️' },
      { id: 'input_boolean.re_soir_couleur',     label: 'Couleur du jour',              icone: '🎨' },
      { id: 'input_boolean.re_soir_maman',       label: 'Bonne nuit à maman',           icone: '💋' },
      { id: 'input_boolean.re_soir_toilettes',   label: 'Toilettes et dents',           icone: '🪥' },
    ]
  }
};

// Détermine la routine active selon l'heure
function routineActive() {
  const now = new Date();
  const h = now.getHours();
  const m = now.getMinutes();
  const total = h * 60 + m;
  if (total >= 6 * 60 && total < 16 * 60 + 30) return 'matin';
  if (total >= 16 * 60 + 30 && total < 19 * 60) return 'ecole';
  return 'soir';
}

// Récupère l'état d'une entité HA
async function getEtat(entityId) {
  const response = await fetch(`${HA_URL}/api/states/${entityId}`, {
    headers: { Authorization: `Bearer ${HA_TOKEN}` }
  });
  const data = await response.json();
  return data.state;
}

// API : infos de la routine active
app.get('/api/routine', async (req, res) => {
  try {
    const id = routineActive();
    const routine = ROUTINES[id];
    const taches = await Promise.all(routine.taches.map(async (t) => {
      const state = await getEtat(t.id);
      let etat = false;
      if (t.special === 'tv') {
        etat = (state === 'off' || state === 'unavailable' || state === 'idle' || state === 'standby');
      } else {
        etat = state === 'on';
      }
      return { ...t, etat, stateRaw: state };
    }));
    res.json({ id, titre: routine.titre, departLabel: routine.departLabel || null, departH: routine.departH || null, departM: routine.departM || null, taches });
  } catch (err) {
    console.log('ERREUR /api/routine:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// API : toggle une tâche
app.post('/api/taches/:entityId/toggle', async (req, res) => {
  const { entityId } = req.params;
  try {
    const response = await fetch(`${HA_URL}/api/services/input_boolean/toggle`, {
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

// API : état de la Shield (compteur TV)
app.get('/api/shield', async (req, res) => {
  try {
    const tvState = await getEtat('media_player.shield_2');
    const shieldToday = await getEtat('sensor.shield_on_today');
    res.json({ tvState, shieldToday });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(3000, () => console.log('Routine Enfant démarré sur le port 3000'));
