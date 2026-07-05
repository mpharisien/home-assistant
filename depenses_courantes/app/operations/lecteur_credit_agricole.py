"""
Lecteur d'exports Crédit Agricole, au format OFX.

Le format OFX est un format bancaire standard. Techniquement, il
ressemble à du XML mais avec des balises qui ne sont pas toujours
fermées (ex: <DTPOSTED>20260630 sans </DTPOSTED>) - on ne peut donc
pas utiliser un lecteur XML classique, on extrait les informations
avec des motifs de texte (expressions régulières).

Un même fichier peut contenir un seul compte, ou plusieurs à la fois
(le Crédit Agricole permet d'exporter tous ses comptes en une fois).
Chaque compte forme un bloc <STMTRS>...</STMTRS> distinct, avec son
propre numéro de compte (ACCTID) et ses propres opérations. On traite
donc chaque bloc <STMTRS> indépendamment - sans jamais décider ici si
le compte doit être suivi ou non, ce n'est pas le rôle du lecteur.

Dans chaque bloc de compte, chaque opération est elle-même un bloc
<STMTTRN>...</STMTTRN> qui contient notamment :
  - DTPOSTED : la date (format AAAAMMJJ)
  - TRNAMT   : le montant, déjà signé (négatif = dépense)
  - FITID    : un identifiant unique fourni par la banque
  - NAME     : un résumé de l'opération
  - MEMO     : le détail complet de l'opération
"""

import re
from datetime import datetime

from app.operations.modele_operation import Operation
from app.operations.resultat_lecture import ResultatLecture

NOM_BANQUE = "Crédit Agricole"


def lire_fichier_ofx(chemin_fichier: str) -> ResultatLecture:
    """
    Lit un export OFX du Crédit Agricole (un ou plusieurs comptes) et
    renvoie toutes les opérations qu'il contient.

    :param chemin_fichier: chemin vers le fichier .ofx exporté
    """
    try:
        with open(chemin_fichier, encoding="utf-8") as fichier:
            contenu = fichier.read()
    except UnicodeDecodeError:
        with open(chemin_fichier, encoding="cp1252") as fichier:
            contenu = fichier.read()

    resultat = ResultatLecture()

    blocs_comptes = re.findall(r"<STMTRS>(.*?)</STMTRS>", contenu, re.S)

    for bloc_compte in blocs_comptes:
        identifiant_compte = re.search(r"<ACCTID>([^<\r\n]*)", bloc_compte).group(1)

        blocs_operations = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", bloc_compte, re.S)

        for bloc in blocs_operations:
            champs = dict(re.findall(r"<(\w+)>([^<\r\n]*)", bloc))

            date_operation = datetime.strptime(champs["DTPOSTED"], "%Y%m%d").date()
            montant = float(champs["TRNAMT"])
            libelle = champs.get("MEMO", champs.get("NAME", "")).strip()
            identifiant_unique = f"CA-{champs['FITID']}"

            resultat.operations.append(
                Operation(
                    date_operation=date_operation,
                    montant=montant,
                    identifiant_compte_brut=identifiant_compte,
                    banque=NOM_BANQUE,
                    libelle=libelle,
                    identifiant_unique=identifiant_unique,
                )
            )

    return resultat
