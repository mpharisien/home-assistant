/* ==========================================================================
   PETITES INTERACTIONS DE L'INTERFACE
   --------------------------------------------------------------------------
   Ce script est chargé sur toutes les pages. Chaque fonctionnalité s'active
   uniquement si la page contient les éléments concernés (repérés par des
   attributs "data-...") : il n'y a donc rien à écrire dans les pages HTML.
   Seule dépendance : Chart.js (fichier chart.umd.min.js) pour les graphiques.
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  activerConfirmations();
  activerBoutonsPatience();
  activerTrisDeTableaux();
  activerChampsSelonType();
  dessinerGraphiques();
});

/* Formulaire avec data-confirmation="Question ?" : demande confirmation
   avant l'envoi (utilisé pour les suppressions). */
function activerConfirmations() {
  document.querySelectorAll("form[data-confirmation]").forEach((formulaire) => {
    formulaire.addEventListener("submit", (evenement) => {
      if (!window.confirm(formulaire.dataset.confirmation)) {
        evenement.preventDefault();
      }
    });
  });
}

/* Formulaire avec data-patience="Texte" : pendant l'envoi, le bouton est
   désactivé et affiche ce texte (utile pour l'actualisation des cours,
   qui peut prendre une trentaine de secondes). */
function activerBoutonsPatience() {
  document.querySelectorAll("form[data-patience]").forEach((formulaire) => {
    formulaire.addEventListener("submit", () => {
      const bouton = formulaire.querySelector("button[type=submit], button:not([type])");
      if (bouton) {
        // Petit délai : le formulaire doit être envoyé avant que le bouton soit désactivé
        setTimeout(() => {
          bouton.disabled = true;
          bouton.textContent = formulaire.dataset.patience;
        }, 0);
      }
    });
  });
}

/* Tableau avec la classe "triable" : un clic sur un titre de colonne trie
   les lignes. Pour trier des nombres, chaque cellule porte sa valeur brute
   dans data-valeur="1234.5" (vide = aucune valeur, toujours placée en bas).
   Un titre avec data-tri="non" n'est pas triable. */
function activerTrisDeTableaux() {
  document.querySelectorAll("table.triable").forEach((tableau) => {
    const entetes = tableau.querySelectorAll("thead tr:last-child th");
    entetes.forEach((entete, index) => {
      if (entete.dataset.tri === "non") return;
      entete.classList.add("triable-entete");
      entete.title = "Cliquer pour trier";
      entete.addEventListener("click", () => trierTableau(tableau, index, entete));
    });
  });
}

function trierTableau(tableau, index, entete) {
  const corps = tableau.tBodies[0];
  const lignes = Array.from(corps.rows);
  // Premier clic : décroissant pour les nombres (le plus grand en haut)
  const croissant = entete.dataset.ordre === "decroissant";
  tableau.querySelectorAll("thead th").forEach((th) => th.removeAttribute("data-ordre"));
  entete.dataset.ordre = croissant ? "croissant" : "decroissant";

  const cleDeTri = (ligne) => {
    const cellule = ligne.cells[index];
    if (!cellule) return null;
    if (cellule.dataset.valeur !== undefined) {
      return cellule.dataset.valeur === "" ? null : parseFloat(cellule.dataset.valeur);
    }
    const texte = cellule.textContent.trim().toLowerCase();
    return texte === "" ? null : texte;
  };

  lignes.sort((a, b) => {
    const va = cleDeTri(a);
    const vb = cleDeTri(b);
    if (va === null && vb === null) return 0;
    if (va === null) return 1;
    if (vb === null) return -1;
    const comparaison = typeof va === "number" && typeof vb === "number"
      ? va - vb
      : String(va).localeCompare(String(vb), "fr");
    return croissant ? comparaison : -comparaison;
  });
  lignes.forEach((ligne) => corps.appendChild(ligne));
}

/* Formulaire de mouvement : affiche seulement les champs utiles au type
   choisi. Le menu porte data-selecteur-type ; chaque bloc de champ porte
   data-types="achat vente" (liste des types pour lesquels il est affiché). */
function activerChampsSelonType() {
  const selecteur = document.querySelector("[data-selecteur-type]");
  if (!selecteur) return;
  const mettreAJour = () => {
    document.querySelectorAll("[data-types]").forEach((bloc) => {
      bloc.hidden = !bloc.dataset.types.split(" ").includes(selecteur.value);
    });
  };
  selecteur.addEventListener("change", mettreAJour);
  mettreAJour();
}

/* Graphiques : <canvas data-graphique="camembert|barres" data-donnees='{...}'>
   data-donnees contient {"libelles": [...], "valeurs": [...], "serie": "..."} */
const PALETTE = [
  "#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#db2777",
  "#65a30d", "#ea580c", "#4f46e5", "#0d9488", "#a16207", "#9333ea", "#64748b",
];
const FORMAT_EUROS = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

function dessinerGraphiques() {
  if (typeof Chart === "undefined") return;
  document.querySelectorAll("canvas[data-graphique]").forEach((canevas) => {
    const donnees = JSON.parse(canevas.dataset.donnees);
    if (canevas.dataset.graphique === "camembert") {
      creerCamembert(canevas, donnees);
    } else {
      creerBarres(canevas, donnees);
    }
  });
}

function creerCamembert(canevas, donnees) {
  const total = donnees.valeurs.reduce((somme, valeur) => somme + valeur, 0);
  new Chart(canevas, {
    type: "doughnut",
    data: {
      labels: donnees.libelles,
      datasets: [{
        data: donnees.valeurs,
        backgroundColor: donnees.libelles.map((_, i) => PALETTE[i % PALETTE.length]),
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            label: (contexte) => {
              const part = total ? (contexte.parsed / total) * 100 : 0;
              return ` ${contexte.label} : ${FORMAT_EUROS.format(contexte.parsed)} `
                + `(${part.toFixed(1).replace(".", ",")} %)`;
            },
          },
        },
      },
    },
  });
}

function creerBarres(canevas, donnees) {
  new Chart(canevas, {
    type: "bar",
    data: {
      labels: donnees.libelles,
      datasets: [{ label: donnees.serie, data: donnees.valeurs, backgroundColor: PALETTE[1] }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (contexte) => ` ${FORMAT_EUROS.format(contexte.parsed.y)}` } },
      },
      scales: { y: { beginAtZero: true, ticks: { callback: (valeur) => FORMAT_EUROS.format(valeur) } } },
    },
  });
}
