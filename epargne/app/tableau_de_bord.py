"""
Page d'accueil : tableau de bord de toute l'épargne.
Affiche le total, la valeur de chaque poche et des graphiques de répartition.
"""

from flask import Blueprint, render_template, url_for

from app.base_de_donnees import obtenir_connexion
from app.outils import format_date, format_euros
from app.pea.calculs import calculer_portefeuille
from app.poches.calculs import resumer_poche
from app.reglages import POCHES

blueprint_tableau_de_bord = Blueprint("tableau_de_bord", __name__)


def _donnees_camembert(elements: list[tuple[str, float]]) -> dict:
    """Prépare les données d'un graphique « camembert » (valeurs positives uniquement)."""
    positifs = [(libelle, valeur) for libelle, valeur in elements if valeur > 0]
    return {
        "libelles": [libelle for libelle, _ in positifs],
        "valeurs": [round(valeur, 2) for _, valeur in positifs],
    }


@blueprint_tableau_de_bord.get("/")
def accueil():
    connexion = obtenir_connexion()
    portefeuille = calculer_portefeuille(connexion)

    poches = [{
        "nom": "PEA",
        "valeur": portefeuille.valeur_totale,
        "detail": f"dont {format_euros(portefeuille.liquidites)} de liquidités",
        "lien": url_for("pea.portefeuille"),
    }]
    for code, definition in POCHES.items():
        resume = resumer_poche(connexion, code)
        if resume.derniere_valorisation is not None:
            detail = f"Valorisation du {format_date(resume.derniere_valorisation['date'])}"
        else:
            detail = "Capital versé (aucune valorisation saisie)"
        poches.append({
            "nom": definition["nom"],
            "valeur": resume.valeur,
            "detail": detail,
            "lien": url_for("poches.page_poche", code=code),
        })

    repartition_pea = [(p.nom, p.valeur_retenue) for p in portefeuille.positions]
    repartition_pea.append(("Liquidités", portefeuille.liquidites))

    return render_template(
        "tableau_de_bord.html",
        portefeuille=portefeuille,
        poches=poches,
        total=sum(p["valeur"] for p in poches),
        camembert_poches=_donnees_camembert([(p["nom"], p["valeur"]) for p in poches]),
        camembert_pea=_donnees_camembert(repartition_pea),
    )
