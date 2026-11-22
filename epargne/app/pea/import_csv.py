"""
Import de fichiers CSV exportés depuis Google Sheets (ou Excel).

Deux imports sont proposés, pour reprendre les données du Google Sheet :
  1. l'onglet « Bourse - Mouvements » -> historique des mouvements du PEA
  2. l'onglet « Actions a rendement » -> liste des actions et leurs dividendes

Les colonnes sont repérées grâce à leur titre (ligne d'en-tête), peu importe
leur position ou la présence d'autres colonnes. Un import est « tout ou rien » :
s'il y a la moindre erreur, rien n'est enregistré et les erreurs sont listées
avec leur numéro de ligne (le même que dans le tableur).
"""

import csv
import io
import re
from dataclasses import dataclass, field

from app.outils import lire_date, lire_nombre, lire_nombre_souple, normaliser_texte
from app.pea import donnees
from app.reglages import TYPES_ACTION_FACULTATIVE, TYPES_AVEC_ACTION

# Nombre maximal de lignes parcourues pour trouver la ligne d'en-tête
_LIGNES_MAX_AVANT_ENTETE = 10


@dataclass
class ResultatImport:
    nb_lignes: int = 0                    # mouvements importés ou actions traitées
    actions_creees: list[str] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Lecture du fichier
# ----------------------------------------------------------------------------

def lire_csv(contenu: bytes) -> list[list[str]]:
    """Décode le fichier et le découpe en lignes et cellules."""
    try:
        texte = contenu.decode("utf-8-sig")  # "-sig" retire l'éventuel marqueur BOM
    except UnicodeDecodeError:
        texte = contenu.decode("cp1252")     # encodage des anciens fichiers Excel

    # Séparateur : virgule (Google Sheets), point-virgule (Excel français) ou tabulation
    premiere_ligne = texte.splitlines()[0] if texte else ""
    separateur = max((",", ";", "\t"), key=premiere_ligne.count)
    return list(csv.reader(io.StringIO(texte), delimiter=separateur))


def trouver_entete(lignes: list[list[str]], alias: dict[str, tuple[str, ...]],
                   obligatoires: tuple[str, ...]) -> tuple[int | None, dict[str, int]]:
    """
    Cherche la ligne d'en-tête parmi les premières lignes du fichier.
    `alias` : {nom interne: titres de colonne acceptés (sans accents, en minuscules)}
    Renvoie (index de la ligne d'en-tête, {nom interne: index de la colonne}).
    """
    for index_ligne, cellules in enumerate(lignes[:_LIGNES_MAX_AVANT_ENTETE]):
        colonnes: dict[str, int] = {}
        for index_colonne, cellule in enumerate(cellules):
            titre = normaliser_texte(cellule)
            for nom, titres_acceptes in alias.items():
                if nom not in colonnes and titre in titres_acceptes:
                    colonnes[nom] = index_colonne
        if all(nom in colonnes for nom in obligatoires):
            return index_ligne, colonnes
    return None, {}


def _lecteur_de_cellules(cellules: list[str], colonnes: dict[str, int]):
    """Renvoie une fonction qui lit une cellule de la ligne par son nom interne."""
    def lire(nom: str) -> str:
        index = colonnes.get(nom)
        if index is None or index >= len(cellules):
            return ""
        return cellules[index].strip()
    return lire


# ----------------------------------------------------------------------------
# Import 1 : mouvements du PEA
# ----------------------------------------------------------------------------

_ALIAS_MOUVEMENTS = {
    "date": ("date",),
    "operation": ("operation", "type"),
    "nombre": ("nombre", "quantite", "qte"),
    "action": ("action", "titre"),
    "cours": ("cours", "prix", "prix unitaire"),
    "dividende": ("dividende", "dividende par action"),
    "montant": ("montant",),
    "frais": ("frais",),
}

# Libellés d'opération reconnus (sans accents, en minuscules) -> type en base
_OPERATIONS = {
    "achat": "achat", "achats": "achat",
    "vente": "vente", "ventes": "vente",
    "coupon": "dividende", "coupons": "dividende",
    "dividende": "dividende", "dividendes": "dividende",
    "ajout de liquidites": "apport", "apport": "apport", "apport de liquidites": "apport",
    "versement": "apport", "depot": "apport",
    "retrait": "retrait", "retrait de liquidites": "retrait",
    "frais": "frais", "taxe": "frais", "taxes": "frais", "droits de garde": "frais",
    "remboursement": "remboursement", "remboursements": "remboursement",
    "remboursement de frais": "remboursement",
}


def analyser_ligne_mouvement(lire) -> dict:
    """
    Transforme une ligne du fichier en mouvement. `lire(nom)` renvoie le texte
    de la cellule. Lève ValueError (message pour l'utilisateur) si la ligne est invalide.
    """
    operation = lire("operation")
    type_mouvement = _OPERATIONS.get(normaliser_texte(operation))
    if type_mouvement is None:
        raise ValueError(
            f"opération « {operation} » non reconnue (attendu : Achat, Vente, Coupons, "
            "Ajout de liquidités, Retrait de liquidités, Frais ou Remboursement)."
        )

    date = lire_date(lire("date"))
    quantite = lire_nombre(lire("nombre"))
    cours = lire_nombre_souple(lire("cours"))
    dividende_par_action = lire_nombre_souple(lire("dividende"))
    frais = lire_nombre(lire("frais")) or 0.0
    montant = lire_nombre(lire("montant"))
    nom_action = lire("action")

    if type_mouvement in TYPES_AVEC_ACTION and not nom_action:
        raise ValueError("le nom de l'action est obligatoire pour ce type d'opération.")
    if type_mouvement in ("achat", "vente") and not quantite:
        raise ValueError("le nombre de titres est obligatoire pour un achat ou une vente.")

    # Montant absent : on le calcule si possible
    if montant is None:
        if type_mouvement == "achat" and quantite and cours is not None:
            montant = quantite * cours + frais
        elif type_mouvement == "vente" and quantite and cours is not None:
            montant = quantite * cours - frais
        elif type_mouvement == "dividende" and quantite and dividende_par_action is not None:
            montant = quantite * dividende_par_action
        else:
            raise ValueError("le montant est vide et ne peut pas être calculé.")

    avec_action = type_mouvement in TYPES_AVEC_ACTION
    garder_action = avec_action or type_mouvement in TYPES_ACTION_FACULTATIVE
    return {
        "date": date,
        "type": type_mouvement,
        "nom_action": (nom_action or None) if garder_action else None,
        "quantite": abs(quantite) if avec_action and quantite is not None else None,
        # Le cours n'a de sens que pour un achat ou une vente
        "cours": cours if type_mouvement in ("achat", "vente") else None,
        "frais": abs(frais) if type_mouvement in ("achat", "vente") else 0.0,
        "montant": round(abs(montant), 2),
        "commentaire": None,
    }


def importer_mouvements(connexion, contenu: bytes, remplacer: bool = False) -> ResultatImport:
    """
    Importe un fichier de mouvements. Si `remplacer` est vrai, l'historique
    existant est d'abord supprimé (pratique pour refaire un import corrigé).
    """
    resultat = ResultatImport()
    lignes = lire_csv(contenu)
    index_entete, colonnes = trouver_entete(lignes, _ALIAS_MOUVEMENTS, ("date", "operation", "montant"))
    if index_entete is None:
        resultat.erreurs.append(
            "Ligne d'en-tête introuvable : le fichier doit contenir au moins les colonnes "
            "« Date », « Opération » et « Montant »."
        )
        return resultat

    a_importer = []
    for numero, cellules in enumerate(lignes[index_entete + 1:], start=index_entete + 2):
        lire = _lecteur_de_cellules(cellules, colonnes)
        if not lire("date") and not lire("operation"):
            continue  # ligne vide
        try:
            a_importer.append(analyser_ligne_mouvement(lire))
        except ValueError as erreur:
            resultat.erreurs.append(f"Ligne {numero} : {erreur}")

    if resultat.erreurs:
        return resultat
    if not a_importer:
        resultat.erreurs.append("Aucun mouvement trouvé dans le fichier.")
        return resultat

    try:
        if remplacer:
            donnees.supprimer_tous_les_mouvements(connexion)
        identifiants: dict[str, int] = {}
        for mouvement in a_importer:
            nom = mouvement.pop("nom_action")
            mouvement["action_id"] = None
            if nom:
                cle = normaliser_texte(nom)
                if cle not in identifiants:
                    action = donnees.trouver_action_par_nom(connexion, nom)
                    if action is None:
                        # Créée « non suivie » : elle apparaîtra dans le tableau
                        # des actions à rendement tant qu'elle est détenue.
                        identifiants[cle] = donnees.creer_action(connexion, nom, suivie=False)
                        resultat.actions_creees.append(nom)
                    else:
                        identifiants[cle] = action["id"]
                mouvement["action_id"] = identifiants[cle]
            donnees.inserer_mouvement(connexion, mouvement)
        connexion.commit()
    except Exception:
        connexion.rollback()
        raise

    resultat.nb_lignes = len(a_importer)
    return resultat


# ----------------------------------------------------------------------------
# Import 2 : liste des actions à rendement
# ----------------------------------------------------------------------------

_ALIAS_ACTIONS = {
    "nom": ("action", "nom"),
    "code": ("epa", "code", "ticker", "symbole", "symbole yahoo"),
}
_COLONNE_DIVIDENDE = re.compile(r"^dividende (\d{4})$")

# Préfixes de place boursière (format Google Finance) -> suffixe Yahoo
_PLACES_BOURSIERES = {
    "EPA": ".PA",   # Euronext Paris
    "AMS": ".AS",   # Euronext Amsterdam
    "EBR": ".BR",   # Euronext Bruxelles
    "ELI": ".LS",   # Euronext Lisbonne
    "ETR": ".DE",   # Xetra (Allemagne)
    "BIT": ".MI",   # Milan
    "BME": ".MC",   # Madrid
}


def convertir_en_symbole_yahoo(code: str) -> str | None:
    """« EPA:TTE » (format Google Finance) -> « TTE.PA » (format Yahoo)."""
    propre = (code or "").strip().upper()
    if not propre:
        return None
    if ":" in propre:
        place, symbole = propre.split(":", 1)
        suffixe = _PLACES_BOURSIERES.get(place.strip())
        if suffixe:
            return symbole.strip() + suffixe
    return propre


def importer_actions(connexion, contenu: bytes) -> ResultatImport:
    """
    Importe la liste des actions : nom, symbole et dividendes par année
    (colonnes « Dividende 2022 », « Dividende 2023 »...).
    Les actions existantes (même nom) sont mises à jour, les autres créées.
    """
    resultat = ResultatImport()
    lignes = lire_csv(contenu)
    index_entete, colonnes = trouver_entete(lignes, _ALIAS_ACTIONS, ("nom",))
    if index_entete is None:
        resultat.erreurs.append(
            "Ligne d'en-tête introuvable : le fichier doit contenir une colonne « Action »."
        )
        return resultat

    # Repère les colonnes « Dividende AAAA »
    colonnes_dividendes = {}
    for index_colonne, cellule in enumerate(lignes[index_entete]):
        correspondance = _COLONNE_DIVIDENDE.match(normaliser_texte(cellule))
        if correspondance:
            colonnes_dividendes[int(correspondance.group(1))] = index_colonne

    a_importer = []
    for numero, cellules in enumerate(lignes[index_entete + 1:], start=index_entete + 2):
        lire = _lecteur_de_cellules(cellules, colonnes)
        nom = lire("nom")
        if not nom:
            continue
        try:
            dividendes = {}
            for annee, index_colonne in colonnes_dividendes.items():
                texte = cellules[index_colonne] if index_colonne < len(cellules) else ""
                valeur = lire_nombre_souple(texte)
                if valeur is not None:
                    dividendes[annee] = valeur
        except ValueError as erreur:
            resultat.erreurs.append(f"Ligne {numero} : {erreur}")
            continue
        a_importer.append((nom, convertir_en_symbole_yahoo(lire("code")), dividendes))

    if resultat.erreurs:
        return resultat
    if not a_importer:
        resultat.erreurs.append("Aucune action trouvée dans le fichier.")
        return resultat

    try:
        for nom, ticker, dividendes in a_importer:
            action = donnees.trouver_action_par_nom(connexion, nom)
            if action is None:
                action_id = donnees.creer_action(connexion, nom, ticker=ticker, suivie=True)
                resultat.actions_creees.append(nom)
            else:
                action_id = action["id"]
                donnees.modifier_action(
                    connexion, action_id, action["nom"], ticker or action["ticker"],
                    suivie=True, en_evidence=bool(action["en_evidence"]), notes=action["notes"],
                )
            for annee, montant in dividendes.items():
                donnees.enregistrer_dividende_exercice(connexion, action_id, annee, montant)
        connexion.commit()
    except Exception:
        connexion.rollback()
        raise

    resultat.nb_lignes = len(a_importer)
    return resultat
