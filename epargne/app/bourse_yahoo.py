"""
Récupération des données de bourse sur Yahoo Finance.

On interroge l'adresse publique utilisée par les graphiques du site Yahoo
Finance (aucun compte ni clé n'est nécessaire). Pour chaque action, une seule
requête renvoie :
  - le cours actuel et les plus haut / plus bas sur 52 semaines
  - l'historique hebdomadaire des cours sur 10 ans (pour les min / max 5 et 10 ans)
  - l'historique des dividendes détachés

Les symboles Yahoo des actions de la bourse de Paris se terminent par « .PA »
(ex. TotalEnergies = TTE.PA). Ils se trouvent sur https://fr.finance.yahoo.com

Remarque : ce service n'est pas officiellement documenté par Yahoo. S'il change
un jour, seul ce fichier sera à adapter.
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.outils import maintenant
from app.reglages import FUSEAU_HORAIRE

journal = logging.getLogger(__name__)

URL_YAHOO = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbole}"
    "?range=10y&interval=1wk&events=div"
)
# Identification envoyée à Yahoo. Testé en novembre 2026 :
#   - sans identification (« Python-urllib ») : refusé (erreur 429) ;
#   - en se faisant passer pour un navigateur Chrome complet : refusé aussi
#     (Yahoo détecte que ce n'est pas un vrai Chrome) ;
#   - avec cette identification courte : accepté.
ENTETES_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
DELAI_MAX_SECONDES = 15
# Pause entre deux actions, pour ne pas être bloqué par Yahoo
PAUSE_ENTRE_ACTIONS_SECONDES = 0.5
# En cas de refus « trop de requêtes » (429) : nouvel essai après cette pause
PAUSE_AVANT_NOUVEL_ESSAI_SECONDES = 2


class ErreurYahoo(Exception):
    """
    Erreur lors de la récupération des données (message destiné à l'utilisateur).
    `passagere` : True si un nouvel essai un peu plus tard a des chances de réussir.
    """

    def __init__(self, message: str, passagere: bool = False):
        super().__init__(message)
        self.passagere = passagere


@dataclass
class DonneesBourse:
    """Données utiles extraites de la réponse de Yahoo pour une action."""
    cours_actuel: float | None = None
    devise: str | None = None
    min_1an: float | None = None
    max_1an: float | None = None
    min_5ans: float | None = None
    max_5ans: float | None = None
    min_10ans: float | None = None
    max_10ans: float | None = None
    dividendes_12_mois: float = 0.0
    # Liste de (date AAAA-MM-JJ, montant par action)
    dividendes: list[tuple[str, float]] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Lecture de la réponse (sans accès réseau : facile à tester)
# ----------------------------------------------------------------------------

def analyser_reponse(reponse: dict, instant: datetime) -> DonneesBourse:
    """Extrait les données utiles de la réponse JSON de Yahoo."""
    try:
        resultat = reponse["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        raise ErreurYahoo("Réponse de Yahoo inattendue (aucune donnée).") from None

    meta = resultat.get("meta") or {}
    horodatages = resultat.get("timestamp") or []
    cotations = ((resultat.get("indicators") or {}).get("quote") or [{}])[0]
    plus_bas = cotations.get("low") or []
    plus_hauts = cotations.get("high") or []

    def extremes_depuis(nb_annees: float) -> tuple[float | None, float | None]:
        """Plus bas et plus haut des semaines comprises dans les `nb_annees` dernières années."""
        limite = (instant - timedelta(days=365.25 * nb_annees)).timestamp()
        bas, hauts = [], []
        for index, horodatage in enumerate(horodatages):
            if horodatage < limite:
                continue
            if index < len(plus_bas) and plus_bas[index] is not None:
                bas.append(plus_bas[index])
            if index < len(plus_hauts) and plus_hauts[index] is not None:
                hauts.append(plus_hauts[index])
        return (min(bas) if bas else None, max(hauts) if hauts else None)

    donnees = DonneesBourse(
        cours_actuel=meta.get("regularMarketPrice"),
        devise=meta.get("currency"),
    )
    donnees.min_5ans, donnees.max_5ans = extremes_depuis(5)
    donnees.min_10ans, donnees.max_10ans = extremes_depuis(10)

    # Plus bas / plus haut sur 1 an : Yahoo fournit directement les valeurs
    # « 52 semaines » ; à défaut, on les calcule à partir de l'historique.
    min_calcule, max_calcule = extremes_depuis(1)
    donnees.min_1an = meta.get("fiftyTwoWeekLow") or min_calcule
    donnees.max_1an = meta.get("fiftyTwoWeekHigh") or max_calcule

    # Dividendes détachés
    evenements = (resultat.get("events") or {}).get("dividends") or {}
    limite_12_mois = (instant - timedelta(days=365)).timestamp()
    for evenement in evenements.values():
        horodatage = evenement.get("date")
        montant = evenement.get("amount")
        if horodatage is None or montant is None:
            continue
        jour = datetime.fromtimestamp(horodatage, FUSEAU_HORAIRE).date().isoformat()
        donnees.dividendes.append((jour, float(montant)))
        if horodatage >= limite_12_mois:
            donnees.dividendes_12_mois += float(montant)
    donnees.dividendes.sort()

    if donnees.cours_actuel is None:
        raise ErreurYahoo("Yahoo n'a pas renvoyé de cours pour ce symbole.")
    return donnees


# ----------------------------------------------------------------------------
# Accès réseau
# ----------------------------------------------------------------------------

def telecharger_donnees(symbole: str) -> DonneesBourse:
    """Interroge Yahoo Finance pour un symbole (ex. "TTE.PA")."""
    try:
        contenu = _interroger_yahoo(symbole)
    except ErreurYahoo as erreur:
        if not erreur.passagere:
            raise
        # Refus passager : on réessaie une fois après une courte pause
        time.sleep(PAUSE_AVANT_NOUVEL_ESSAI_SECONDES)
        contenu = _interroger_yahoo(symbole)
    return analyser_reponse(contenu, maintenant())


def _interroger_yahoo(symbole: str) -> dict:
    """Envoie la requête et renvoie la réponse JSON (ou lève ErreurYahoo)."""
    url = URL_YAHOO.format(symbole=urllib.parse.quote(symbole.strip()))
    requete = urllib.request.Request(url, headers=ENTETES_HTTP)
    try:
        with urllib.request.urlopen(requete, timeout=DELAI_MAX_SECONDES) as reponse:
            return json.load(reponse)
    except urllib.error.HTTPError as erreur:
        if erreur.code == 404:
            raise ErreurYahoo(
                f"Symbole « {symbole} » inconnu de Yahoo (pour Paris, il se termine par .PA)."
            ) from None
        if erreur.code == 429:
            raise ErreurYahoo(
                "Yahoo limite le nombre de requêtes : réessaie dans quelques minutes.",
                passagere=True,
            ) from None
        raise ErreurYahoo(f"Yahoo a répondu par une erreur (code {erreur.code}).") from None
    except urllib.error.URLError as erreur:
        raise ErreurYahoo(f"Impossible de joindre Yahoo Finance ({erreur.reason}).") from None
    except (TimeoutError, json.JSONDecodeError) as erreur:
        raise ErreurYahoo(f"Réponse de Yahoo illisible ou trop lente ({erreur}).") from None
    except OSError as erreur:  # connexion coupée en cours de route, etc.
        raise ErreurYahoo(f"Erreur réseau en interrogeant Yahoo ({erreur}).") from None


def actualiser_cours(connexion, actions) -> tuple[int, list[str]]:
    """
    Met à jour en base les données de bourse des actions données (lignes de la
    table "actions" possédant un ticker).
    Renvoie (nombre d'actions mises à jour, liste des messages d'erreur).
    En cas d'échec pour une action, ses données précédentes sont conservées.
    """
    nb_reussites = 0
    erreurs = []
    for position, action in enumerate(actions):
        if position > 0:
            time.sleep(PAUSE_ENTRE_ACTIONS_SECONDES)
        try:
            donnees = telecharger_donnees(action["ticker"])
        except ErreurYahoo as erreur:
            message = str(erreur)
            erreurs.append(f"{action['nom']} : {message}")
            journal.warning("Cours de %s (%s) : %s", action["nom"], action["ticker"], message)
            connexion.execute(
                "INSERT INTO cours_bourse (action_id, erreur) VALUES (?, ?) "
                "ON CONFLICT (action_id) DO UPDATE SET erreur = excluded.erreur",
                (action["id"], message),
            )
            connexion.commit()
            continue

        enregistrer_donnees(connexion, action["id"], donnees)
        nb_reussites += 1
    return nb_reussites, erreurs


def enregistrer_donnees(connexion, action_id: int, donnees: DonneesBourse) -> None:
    """Enregistre en base les données récupérées pour une action."""
    connexion.execute(
        """
        INSERT INTO cours_bourse (
            action_id, cours_actuel, devise, min_1an, max_1an, min_5ans, max_5ans,
            min_10ans, max_10ans, dividendes_12_mois, date_maj, erreur
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT (action_id) DO UPDATE SET
            cours_actuel = excluded.cours_actuel,
            devise = excluded.devise,
            min_1an = excluded.min_1an,
            max_1an = excluded.max_1an,
            min_5ans = excluded.min_5ans,
            max_5ans = excluded.max_5ans,
            min_10ans = excluded.min_10ans,
            max_10ans = excluded.max_10ans,
            dividendes_12_mois = excluded.dividendes_12_mois,
            date_maj = excluded.date_maj,
            erreur = NULL
        """,
        (
            action_id, donnees.cours_actuel, donnees.devise,
            donnees.min_1an, donnees.max_1an, donnees.min_5ans, donnees.max_5ans,
            donnees.min_10ans, donnees.max_10ans, round(donnees.dividendes_12_mois, 4),
            maintenant().isoformat(timespec="seconds"),
        ),
    )
    connexion.executemany(
        "INSERT INTO dividendes_detaches (action_id, date, montant) VALUES (?, ?, ?) "
        "ON CONFLICT (action_id, date) DO UPDATE SET montant = excluded.montant",
        [(action_id, jour, montant) for jour, montant in donnees.dividendes],
    )
    connexion.commit()
