"""
Petits outils utilisés dans toute l'application :
  - lecture des nombres et des dates saisis par l'utilisateur (format français)
  - mise en forme des nombres, montants, pourcentages et dates pour l'affichage
"""

import math
import unicodedata
from datetime import date, datetime

from app.reglages import FUSEAU_HORAIRE

# Espaces qu'on peut trouver dans un nombre écrit à la française : espace
# normale, espace insécable, espace fine insécable (utilisée par Google Sheets).
_ESPACES = (" ", " ", " ")

# Valeurs « vides » qu'on rencontre dans un tableur (cellule d'erreur, croix...)
_VALEURS_VIDES_TABLEUR = {"x", "-", "—", "n/a", "na"}


# ----------------------------------------------------------------------------
# Date et heure
# ----------------------------------------------------------------------------

def maintenant() -> datetime:
    """Date et heure actuelles, à l'heure de Paris."""
    return datetime.now(FUSEAU_HORAIRE)


def aujourdhui() -> date:
    """Date du jour, à l'heure de Paris."""
    return maintenant().date()


# ----------------------------------------------------------------------------
# Lecture des saisies
# ----------------------------------------------------------------------------

def normaliser_texte(texte: str | None) -> str:
    """
    Met un texte en minuscules, sans accents et sans espaces superflus.
    Sert à comparer des libellés saisis de façons différentes :
    "Ajout de liquidités" et "ajout de  LIQUIDITES" donnent le même résultat.
    """
    decompose = unicodedata.normalize("NFKD", texte or "")
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return " ".join(sans_accents.lower().split())


def lire_nombre(texte) -> float | None:
    """
    Convertit un nombre saisi (« 1 234,56 », « 12.5 », « 3,2 € ») en nombre.
    Renvoie None si le texte est vide. Lève ValueError si le texte n'est pas
    un nombre valide (le message d'erreur est destiné à l'utilisateur).
    """
    if texte is None:
        return None
    if isinstance(texte, (int, float)):
        return float(texte)

    propre = str(texte).strip().replace("€", "")
    for espace in _ESPACES:
        propre = propre.replace(espace, "")
    if propre == "":
        return None

    # « 1.234,56 » : le point sépare les milliers, la virgule les décimales
    if "," in propre and "." in propre:
        propre = propre.replace(".", "")
    propre = propre.replace(",", ".")

    try:
        valeur = float(propre)
    except ValueError:
        raise ValueError(f"« {texte} » n'est pas un nombre valide.") from None
    if not math.isfinite(valeur):
        raise ValueError(f"« {texte} » n'est pas un nombre valide.")
    return valeur


def lire_nombre_souple(texte) -> float | None:
    """
    Comme lire_nombre, mais considère comme vides les valeurs typiques d'un
    tableur qui ne sont pas des nombres : « x », « - », « #DIV/0! »...
    """
    propre = str(texte or "").strip()
    if propre.startswith("#") or propre.lower() in _VALEURS_VIDES_TABLEUR:
        return None
    return lire_nombre(propre)


def lire_date(texte: str | None) -> str:
    """
    Convertit une date saisie (« 05/01/2026 », « 05/01/26 » ou « 2026-01-05 »)
    au format utilisé en base de données : « 2026-01-05 » (AAAA-MM-JJ).
    Ce format a l'avantage de se trier correctement par ordre alphabétique.
    Lève ValueError si la date n'est pas valide.
    """
    propre = (texte or "").strip()
    for format_date_saisie in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(propre, format_date_saisie).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"« {texte} » n'est pas une date valide (format attendu : JJ/MM/AAAA).")


# ----------------------------------------------------------------------------
# Mise en forme pour l'affichage (utilisées comme « filtres » dans les pages
# HTML, par exemple {{ montant|euros }} - voir main.py)
# ----------------------------------------------------------------------------

def format_nombre(valeur, decimales: int = 2) -> str:
    """1234.5 -> « 1 234,50 ». Renvoie « — » si la valeur est absente."""
    if valeur is None:
        return "—"
    arrondi = round(float(valeur), decimales)
    if arrondi == 0:
        arrondi = 0.0  # évite d'afficher « -0,00 »
    texte = f"{arrondi:,.{decimales}f}"  # format anglais : « 1,234.50 »
    return texte.replace(",", " ").replace(".", ",")


def format_euros(valeur, decimales: int = 2) -> str:
    """1234.5 -> « 1 234,50 € »."""
    if valeur is None:
        return "—"
    return f"{format_nombre(valeur, decimales)} €"


def format_pourcent(ratio, decimales: int = 2) -> str:
    """0.1109 -> « 11,09 % » (la valeur reçue est un ratio, pas un pourcentage)."""
    if ratio is None:
        return "—"
    return f"{format_nombre(ratio * 100, decimales)} %"


def format_quantite(valeur) -> str:
    """Affiche une quantité sans décimales inutiles : 20.0 -> « 20 », 1.5 -> « 1,5 »."""
    if valeur is None:
        return "—"
    if float(valeur).is_integer():
        return format_nombre(valeur, 0)
    return format_nombre(valeur, 4).rstrip("0").rstrip(",")


def format_champ(valeur) -> str:
    """
    Nombre à pré-remplir dans un champ de formulaire : 12.37 -> « 12,37 »,
    sans séparateur de milliers (pour pouvoir être modifié facilement).
    """
    if valeur is None:
        return ""
    texte = f"{float(valeur):.6f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",")


def format_date(valeur) -> str:
    """« 2026-01-05 » -> « 05/01/2026 »."""
    if not valeur:
        return "—"
    try:
        return date.fromisoformat(str(valeur)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(valeur)


def format_date_heure(valeur) -> str:
    """« 2026-01-05T14:30:00+01:00 » -> « 05/01/2026 à 14:30 »."""
    if not valeur:
        return "—"
    try:
        return datetime.fromisoformat(str(valeur)).strftime("%d/%m/%Y à %H:%M")
    except ValueError:
        return str(valeur)
