"""
Calculs du PEA, à partir de l'historique des mouvements.

Rien n'est stocké : tout (quantités détenues, prix de revient, liquidités...)
est recalculé à partir de l'historique à chaque affichage. Ainsi, corriger un
mouvement passé corrige automatiquement tous les résultats.

PRIX DE REVIENT (méthode du « prix moyen pondéré », utilisée en France) :
  - un achat ajoute son montant (frais inclus) au prix de revient total ;
  - une vente retire du prix de revient la part correspondant aux titres
    vendus ; le prix de revient unitaire (PRU) des titres restants ne change pas ;
  - un remboursement lié à une action diminue son prix de revient.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean

from app import outils
from app.pea import donnees
from app.reglages import (
    DIVIDENDES_ANNEES_APRES,
    DIVIDENDES_ANNEES_AVANT,
    MOYENNE_ANNEES_AVANT,
    SEUIL_TENDANCE,
)

# En dessous de ce seuil, une quantité est considérée comme nulle
# (les calculs avec des nombres à virgule ne sont jamais parfaitement exacts).
_EPSILON = 1e-9


# ----------------------------------------------------------------------------
# Rejeu de l'historique
# ----------------------------------------------------------------------------

@dataclass
class Position:
    """Situation d'une action dans le PEA."""
    action_id: int
    nom: str
    quantite: float = 0.0
    cout_total: float = 0.0           # prix de revient des titres détenus (frais inclus)
    dividendes: float = 0.0           # total des dividendes reçus depuis le début
    plus_value_realisee: float = 0.0  # gains / pertes des ventes passées
    cours_actuel: float | None = None

    @property
    def detenue(self) -> bool:
        return self.quantite > _EPSILON

    @property
    def pru(self) -> float | None:
        """Prix de revient unitaire."""
        return self.cout_total / self.quantite if self.detenue else None

    @property
    def valeur(self) -> float | None:
        """Valeur au cours actuel (None si le cours n'est pas connu)."""
        if not self.detenue or self.cours_actuel is None:
            return None
        return self.quantite * self.cours_actuel

    @property
    def valeur_retenue(self) -> float:
        """Valeur au cours actuel, ou à défaut le prix de revient."""
        valeur = self.valeur
        return valeur if valeur is not None else self.cout_total

    @property
    def plus_value_latente(self) -> float | None:
        valeur = self.valeur
        return None if valeur is None else valeur - self.cout_total

    @property
    def plus_value_latente_ratio(self) -> float | None:
        plus_value = self.plus_value_latente
        if plus_value is None or self.cout_total <= 0:
            return None
        return plus_value / self.cout_total


@dataclass
class EtatPea:
    """Résultat du rejeu de l'historique à une date donnée."""
    positions: dict[int, Position] = field(default_factory=dict)
    liquidites: float = 0.0
    apports_nets: float = 0.0  # ajouts - retraits de liquidités
    anomalies: list[str] = field(default_factory=list)


def rejouer_mouvements(mouvements, jusqu_au: str | None = None) -> EtatPea:
    """
    Rejoue les mouvements dans l'ordre pour calculer la situation du PEA.

    `mouvements` : lignes triées par date (puis par ordre de saisie), avec les
    clés date, type, action_id, nom_action, quantite, montant.
    `jusqu_au` : si renseigné (AAAA-MM-JJ), ignore les mouvements postérieurs.
    """
    etat = EtatPea()
    for mouvement in mouvements:
        if jusqu_au is not None and mouvement["date"] > jusqu_au:
            continue

        type_mouvement = mouvement["type"]
        montant = mouvement["montant"] or 0.0

        if type_mouvement == "apport":
            etat.liquidites += montant
            etat.apports_nets += montant
            continue
        if type_mouvement == "retrait":
            etat.liquidites -= montant
            etat.apports_nets -= montant
            continue
        if type_mouvement == "frais":
            etat.liquidites -= montant
            continue
        if type_mouvement == "remboursement":
            etat.liquidites += montant
            if mouvement["action_id"] is None:
                continue  # remboursement général (frais, taxe...) : rien d'autre à faire
            # Sinon, on continue ci-dessous pour mettre à jour l'action concernée

        # Mouvements liés à une action : achat, vente, dividende, remboursement
        action_id = mouvement["action_id"]
        position = etat.positions.get(action_id)
        if position is None:
            position = Position(action_id=action_id, nom=mouvement["nom_action"] or "?")
            etat.positions[action_id] = position
        quantite = mouvement["quantite"] or 0.0

        if type_mouvement == "achat":
            position.quantite += quantite
            position.cout_total += montant
            etat.liquidites -= montant

        elif type_mouvement == "vente":
            etat.liquidites += montant
            if quantite > position.quantite + _EPSILON:
                etat.anomalies.append(
                    f"{outils.format_date(mouvement['date'])} : vente de "
                    f"{outils.format_quantite(quantite)} {position.nom} alors que seulement "
                    f"{outils.format_quantite(position.quantite)} étaient détenues "
                    "(un achat manque peut-être dans l'historique)."
                )
            part_vendue = min(quantite / position.quantite, 1.0) if position.detenue else 1.0
            cout_vendu = position.cout_total * part_vendue
            position.cout_total -= cout_vendu
            position.quantite -= quantite
            position.plus_value_realisee += montant - cout_vendu
            if position.quantite <= _EPSILON:
                position.quantite = 0.0
                position.cout_total = 0.0

        elif type_mouvement == "dividende":
            position.dividendes += montant
            etat.liquidites += montant

        elif type_mouvement == "remboursement":
            # Argent rendu au titre de cette action (capital rendu, taxe
            # remboursée...) : il diminue le prix de revient des titres détenus.
            # Ce qui dépasserait le prix de revient (ou si l'action n'est plus
            # détenue) est compté comme un gain réalisé.
            baisse_cout = min(montant, position.cout_total) if position.detenue else 0.0
            position.cout_total -= baisse_cout
            position.plus_value_realisee += montant - baisse_cout

    return etat


# ----------------------------------------------------------------------------
# Portefeuille actuel
# ----------------------------------------------------------------------------

@dataclass
class Portefeuille:
    positions: list[Position]           # actions détenues
    positions_soldees: list[Position]   # actions entièrement vendues
    liquidites: float
    apports_nets: float
    valeur_titres: float
    cout_titres: float
    plus_value_latente: float           # sur les titres dont le cours est connu
    plus_value_latente_ratio: float | None
    valeur_totale: float                # titres + liquidités
    dividendes_annee: float
    dividendes_annee_precedente: float
    dividendes_total: float
    cours_manquants: list[str]
    anomalies: list[str]
    date_maj_cours: str | None


def calculer_portefeuille(connexion) -> Portefeuille:
    mouvements = donnees.lister_mouvements(connexion)
    etat = rejouer_mouvements(mouvements)
    cours = donnees.lire_cours(connexion)

    for position in etat.positions.values():
        ligne_cours = cours.get(position.action_id)
        position.cours_actuel = ligne_cours["cours_actuel"] if ligne_cours else None

    detenues = sorted(
        (p for p in etat.positions.values() if p.detenue),
        key=lambda p: p.valeur_retenue, reverse=True,
    )
    soldees = sorted(
        (p for p in etat.positions.values() if not p.detenue),
        key=lambda p: p.nom.lower(),
    )

    avec_cours = [p for p in detenues if p.valeur is not None]
    cout_avec_cours = sum(p.cout_total for p in avec_cours)
    plus_value_latente = sum(p.plus_value_latente for p in avec_cours)

    annee = outils.aujourdhui().year

    def dividendes_de(annee_recherchee: int) -> float:
        return sum(
            m["montant"] for m in mouvements
            if m["type"] == "dividende" and m["date"].startswith(f"{annee_recherchee}-")
        )

    dates_maj = [
        cours[p.action_id]["date_maj"] for p in detenues
        if p.action_id in cours and cours[p.action_id]["date_maj"]
    ]
    valeur_titres = sum(p.valeur_retenue for p in detenues)

    return Portefeuille(
        positions=detenues,
        positions_soldees=soldees,
        liquidites=etat.liquidites,
        apports_nets=etat.apports_nets,
        valeur_titres=valeur_titres,
        cout_titres=sum(p.cout_total for p in detenues),
        plus_value_latente=plus_value_latente,
        plus_value_latente_ratio=plus_value_latente / cout_avec_cours if cout_avec_cours > 0 else None,
        valeur_totale=valeur_titres + etat.liquidites,
        dividendes_annee=dividendes_de(annee),
        dividendes_annee_precedente=dividendes_de(annee - 1),
        dividendes_total=sum(p.dividendes for p in etat.positions.values()),
        cours_manquants=[p.nom for p in detenues if p.valeur is None],
        anomalies=etat.anomalies,
        # Date de la plus ancienne mise à jour parmi les actions détenues :
        # c'est elle qui indique si les cours affichés sont à jour.
        date_maj_cours=min(dates_maj) if dates_maj else None,
    )


# ----------------------------------------------------------------------------
# Dividendes reçus, par année et par action
# ----------------------------------------------------------------------------

@dataclass
class LigneDividendes:
    nom: str
    dividendes: float
    prix_de_revient: float | None
    rendement: float | None


@dataclass
class AnneeDividendes:
    annee: int
    lignes: list[LigneDividendes]
    total_dividendes: float
    total_prix_de_revient: float
    rendement: float | None


def calculer_dividendes_par_annee(connexion) -> list[AnneeDividendes]:
    """
    Pour chaque année où des dividendes ont été reçus, liste par action :
      - la somme des dividendes reçus dans l'année ;
      - le prix de revient des titres détenus au 31/12 (ou, si l'action a été
        vendue depuis, à la date de son dernier dividende de l'année) ;
      - le rendement = dividendes / prix de revient.
    Les actions détenues au 31/12 sans dividende dans l'année apparaissent
    aussi (avec 0), car elles comptent dans le capital investi.
    Résultat trié de l'année la plus récente à la plus ancienne.
    """
    mouvements = donnees.lister_mouvements(connexion)
    dividendes = [m for m in mouvements if m["type"] == "dividende"]
    annees = sorted({int(m["date"][:4]) for m in dividendes}, reverse=True)

    resultat = []
    for annee in annees:
        etat_fin_annee = rejouer_mouvements(mouvements, jusqu_au=f"{annee}-12-31")

        recus: dict[int, float] = defaultdict(float)
        date_dernier_dividende: dict[int, str] = {}
        noms: dict[int, str] = {}
        for m in dividendes:
            if m["date"].startswith(f"{annee}-"):
                recus[m["action_id"]] += m["montant"]
                date_dernier_dividende[m["action_id"]] = max(
                    m["date"], date_dernier_dividende.get(m["action_id"], "")
                )
                noms[m["action_id"]] = m["nom_action"] or "?"

        detenues = {aid: p for aid, p in etat_fin_annee.positions.items() if p.detenue}
        lignes = []
        for action_id in set(recus) | set(detenues):
            if action_id in detenues:
                prix_de_revient = detenues[action_id].cout_total
                nom = detenues[action_id].nom
            else:
                etat_au_dividende = rejouer_mouvements(
                    mouvements, jusqu_au=date_dernier_dividende[action_id]
                )
                position = etat_au_dividende.positions.get(action_id)
                prix_de_revient = position.cout_total if position and position.detenue else None
                nom = noms[action_id]
            montant_recu = recus.get(action_id, 0.0)
            lignes.append(LigneDividendes(
                nom=nom,
                dividendes=montant_recu,
                prix_de_revient=prix_de_revient,
                rendement=montant_recu / prix_de_revient if prix_de_revient else None,
            ))

        lignes.sort(key=lambda ligne: (-ligne.dividendes, ligne.nom.lower()))
        total_dividendes = sum(ligne.dividendes for ligne in lignes)
        total_prix_de_revient = sum(ligne.prix_de_revient or 0.0 for ligne in lignes)
        resultat.append(AnneeDividendes(
            annee=annee,
            lignes=lignes,
            total_dividendes=total_dividendes,
            total_prix_de_revient=total_prix_de_revient,
            rendement=total_dividendes / total_prix_de_revient if total_prix_de_revient else None,
        ))
    return resultat


# ----------------------------------------------------------------------------
# Tableau « Actions à rendement »
# ----------------------------------------------------------------------------

def annees_affichees(annee_courante: int) -> list[int]:
    """Années dont les dividendes sont affichés (en 2026 : 2022 à 2027)."""
    return list(range(annee_courante - DIVIDENDES_ANNEES_AVANT,
                      annee_courante + DIVIDENDES_ANNEES_APRES + 1))


def annees_moyenne(annee_courante: int) -> list[int]:
    """Années prises en compte pour la moyenne (en 2026 : 2024 à 2027)."""
    return list(range(annee_courante - MOYENNE_ANNEES_AVANT,
                      annee_courante + DIVIDENDES_ANNEES_APRES + 1))


def calculer_moyenne(valeurs: list[float]) -> float | None:
    return mean(valeurs) if valeurs else None


def calculer_tendance(valeurs_passees: list[float], valeurs_recentes: list[float]) -> str | None:
    """
    Compare la moyenne des dividendes récents (N et N+1) à celle des années
    passées (N-4 à N-1). Renvoie "hausse", "baisse", "stable", ou None si
    l'une des deux périodes n'a aucune valeur renseignée.
    """
    if not valeurs_passees or not valeurs_recentes:
        return None
    moyenne_passee = mean(valeurs_passees)
    moyenne_recente = mean(valeurs_recentes)
    if moyenne_passee == 0:
        return "hausse" if moyenne_recente > 0 else "stable"
    evolution = moyenne_recente / moyenne_passee - 1
    if evolution > SEUIL_TENDANCE:
        return "hausse"
    if evolution < -SEUIL_TENDANCE:
        return "baisse"
    return "stable"


def calculer_taux_decision(cours: float | None, minimum: float | None,
                           maximum: float | None) -> float | None:
    """
    Position du cours actuel dans la fourchette de l'année :
      1.0 (100 %) = au plus bas de l'année -> moment a priori favorable pour acheter
      0.0 (0 %)   = au plus haut de l'année
    Formule : (plus haut - cours) / (plus haut - plus bas)
    """
    if cours is None or minimum is None or maximum is None or maximum <= minimum:
        return None
    return (maximum - cours) / (maximum - minimum)


@dataclass
class LigneAction:
    action: object                      # ligne de la table "actions"
    cours: object | None                # ligne de la table "cours_bourse"
    dividendes: dict[int, float]        # {annee: dividende par action}
    moyenne_dividendes: float | None
    tendance: str | None
    rendement: float | None             # moyenne des dividendes / cours actuel
    rendement_12_mois: float | None     # dividendes détachés sur 12 mois / cours actuel
    taux_decision: float | None
    quantite_detenue: float

    @property
    def detenue(self) -> bool:
        return self.quantite_detenue > _EPSILON


def calculer_tableau_actions(connexion, annee_courante: int) -> list[LigneAction]:
    """
    Lignes du tableau « Actions à rendement » : les actions détenues, plus
    celles marquées comme suivies. Triées par rendement décroissant.
    """
    annees_pour_moyenne = annees_moyenne(annee_courante)
    # Périodes comparées pour la tendance (en 2026 : 2022-2025 contre 2026-2027)
    annees_passees = [a for a in annees_affichees(annee_courante) if a < annee_courante]
    annees_recentes = [a for a in annees_affichees(annee_courante) if a >= annee_courante]
    dividendes = donnees.lire_dividendes_exercice(connexion)
    cours = donnees.lire_cours(connexion)
    etat = rejouer_mouvements(donnees.lister_mouvements(connexion))

    lignes = []
    for action in donnees.lister_actions(connexion):
        position = etat.positions.get(action["id"])
        quantite = position.quantite if position else 0.0
        if not action["suivie"] and quantite <= _EPSILON:
            continue

        dividendes_action = dividendes.get(action["id"], {})
        valeurs_moyenne = [dividendes_action[a] for a in annees_pour_moyenne if a in dividendes_action]
        moyenne = calculer_moyenne(valeurs_moyenne)

        ligne_cours = cours.get(action["id"])
        cours_actuel = ligne_cours["cours_actuel"] if ligne_cours else None
        rendement = moyenne / cours_actuel if moyenne is not None and cours_actuel else None
        rendement_12_mois = (
            ligne_cours["dividendes_12_mois"] / cours_actuel
            if cours_actuel and ligne_cours["dividendes_12_mois"] is not None else None
        )

        lignes.append(LigneAction(
            action=action,
            cours=ligne_cours,
            dividendes=dividendes_action,
            moyenne_dividendes=moyenne,
            tendance=calculer_tendance(
                [dividendes_action[a] for a in annees_passees if a in dividendes_action],
                [dividendes_action[a] for a in annees_recentes if a in dividendes_action],
            ),
            rendement=rendement,
            rendement_12_mois=rendement_12_mois,
            taux_decision=calculer_taux_decision(
                cours_actuel,
                ligne_cours["min_1an"] if ligne_cours else None,
                ligne_cours["max_1an"] if ligne_cours else None,
            ),
            quantite_detenue=quantite,
        ))

    # Tri : meilleur rendement en premier, actions sans rendement à la fin
    lignes.sort(key=lambda l: (l.rendement is None, -(l.rendement or 0), l.action["nom"].lower()))
    return lignes
