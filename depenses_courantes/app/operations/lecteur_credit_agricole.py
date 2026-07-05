"""
Lecteur d'exports Crédit Agricole, au format OFX.

Le format OFX est un format bancaire standard. Techniquement, il
ressemble à du XML mais avec des balises qui ne sont pas toujours
fermées (ex: <DTPOSTED>20260630 sans </DTPOSTED>) - on ne peut donc
pas utiliser un lecteur XML classique, on extrait les informations
avec des motifs de texte (expressions régulières).

Chaque opération dans le fichier est un bloc <STMTTRN>...</STMTTRN>
qui contient notamment :
  - DTPOSTED : la date (format AAAAMMJJ)
  - TRNAMT   : le montant, déjà signé (négatif = dépense)
  - FITID    : un identifiant unique fourni par la banque
  - NAME     : un résumé de l'opération
  - MEMO     : le détail complet de l'opération
"""

import re
from datetime import datetime

from app.operations.modele_operation import Operation

NOM_BANQUE = "Crédit Agricole"


def lire_fichier_ofx(chemin_fichier: str, nom_compte: str) -> list[Operation]:
    """
    Lit un export OFX du Crédit Agricole et renvoie la liste des
    opérations qu'il contient, sous forme d'objets Operation.

    :param chemin_fichier: chemin vers le fichier .ofx exporté
    :param nom_compte: nom donné au compte dans notre projet,
                        ex: "Crédit Agricole - Compte courant perso"
    """
    # Piège rencontré en pratique : l'en-tête du fichier annonce
    # "CHARSET:1252" (Windows-1252), mais le contenu réel est parfois
    # en UTF-8 malgré tout. On essaie donc UTF-8 en premier, et on se
    # rabat sur Windows-1252 uniquement si ça échoue.
    try:
        with open(chemin_fichier, encoding="utf-8") as fichier:
            contenu = fichier.read()
    except UnicodeDecodeError:
        with open(chemin_fichier, encoding="cp1252") as fichier:
            contenu = fichier.read()

    operations = []

    # On découpe le fichier en un bloc par opération
    blocs_operations = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", contenu, re.S)

    for bloc in blocs_operations:
        # On extrait chaque champ "<BALISE>valeur" du bloc
        champs = dict(re.findall(r"<(\w+)>([^<\r\n]*)", bloc))

        date_operation = datetime.strptime(champs["DTPOSTED"], "%Y%m%d").date()
        montant = float(champs["TRNAMT"])

        # NAME est un résumé, MEMO souvent plus complet : on garde le plus parlant
        libelle = champs.get("MEMO", champs.get("NAME", "")).strip()

        # On préfixe l'identifiant fourni par la banque pour qu'il ne
        # rentre jamais en collision avec celui d'une autre banque.
        identifiant_unique = f"CA-{champs['FITID']}"

        operations.append(
            Operation(
                date_operation=date_operation,
                montant=montant,
                compte=nom_compte,
                banque=NOM_BANQUE,
                libelle=libelle,
                identifiant_unique=identifiant_unique,
            )
        )

    return operations
