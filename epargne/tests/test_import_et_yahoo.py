"""
Tests de l'import CSV et de la lecture des réponses Yahoo (sans accès Internet).
"""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime

from app.base_de_donnees import MIGRATIONS, initialiser_base, ouvrir_connexion
from app.bourse_yahoo import ErreurYahoo, analyser_reponse
from app.pea import import_csv
from app.pea.donnees import lister_mouvements, lire_dividendes_exercice
from app.reglages import FUSEAU_HORAIRE

# Extrait de l'onglet « Bourse - Mouvements » tel qu'exporté par Google Sheets
# (virgule comme séparateur, nombres à la française entre guillemets).
CSV_MOUVEMENTS = """Date,Opération,Nombre,Action,Cours,Dividende,Montant,Frais,,Rendement
03/06/2025,Coupons,6,FDJ,,"2,05","12,3",,,
01/09/2025,Ajout de liquidités,,,,,1000,,,
03/09/2025,Achat,25,CARREFOUR,"12,370",,"312,04","2,79",,
05/01/2026,Coupons,20,TOTAL ENERGIES,"56,000",x,17,,,2026
07/01/2026,Vente,50,Nexity,"8,800",,"438,01","1,99",,
,,,,,,,,,
""".encode("utf-8")

# Extrait de l'onglet « Actions a rendement » (export Excel : point-virgule)
CSV_ACTIONS = """Action;EPA;Cours actuel;Dividende 2024;Dividende 2025;Dividende 2026;Dividende 2027;Tendance
M6 METROPOLE TELE;EPA:MMT;10,92;1,25;1,25;1,125;1,25;→
VERALLIA;EPA:VRLA;16,85;1,7;1,7;;;#DIV/0!
""".encode("cp1252", errors="replace")


class BaseTemporaire(unittest.TestCase):
    """Crée une base de données vide pour chaque test."""

    def setUp(self):
        dossier = tempfile.mkdtemp()
        self.chemin = os.path.join(dossier, "test.db")
        initialiser_base(self.chemin)
        self.connexion = ouvrir_connexion(self.chemin)

    def tearDown(self):
        self.connexion.close()


class TestImportMouvements(BaseTemporaire):

    def test_import_du_google_sheet(self):
        resultat = import_csv.importer_mouvements(self.connexion, CSV_MOUVEMENTS)
        self.assertEqual(resultat.erreurs, [])
        self.assertEqual(resultat.nb_lignes, 5)
        self.assertEqual(sorted(resultat.actions_creees), ["CARREFOUR", "FDJ", "Nexity", "TOTAL ENERGIES"])

        mouvements = lister_mouvements(self.connexion)
        achat = next(m for m in mouvements if m["type"] == "achat")
        self.assertEqual(achat["date"], "2025-09-03")
        self.assertEqual(achat["quantite"], 25)
        self.assertAlmostEqual(achat["cours"], 12.37)
        self.assertAlmostEqual(achat["frais"], 2.79)
        self.assertAlmostEqual(achat["montant"], 312.04)

        coupon_tte = next(m for m in mouvements if m["nom_action"] == "TOTAL ENERGIES")
        self.assertEqual(coupon_tte["type"], "dividende")
        self.assertIsNone(coupon_tte["cours"])  # le cours n'est pas gardé pour un dividende
        self.assertEqual(coupon_tte["montant"], 17)

    def test_ligne_invalide_annule_tout(self):
        contenu = CSV_MOUVEMENTS + "08/01/2026,Cadeau,10,M6,,,100,,,\n".encode("utf-8")
        resultat = import_csv.importer_mouvements(self.connexion, contenu)
        self.assertEqual(len(resultat.erreurs), 1)
        self.assertIn("Ligne 8", resultat.erreurs[0])
        self.assertEqual(lister_mouvements(self.connexion), [])

    def test_remplacer_l_historique(self):
        import_csv.importer_mouvements(self.connexion, CSV_MOUVEMENTS)
        import_csv.importer_mouvements(self.connexion, CSV_MOUVEMENTS, remplacer=True)
        self.assertEqual(len(lister_mouvements(self.connexion)), 5)

    def test_montant_calcule_si_absent(self):
        contenu = "Date;Opération;Nombre;Action;Cours;Frais;Montant\n01/02/2026;Achat;10;A;5;1;\n".encode()
        resultat = import_csv.importer_mouvements(self.connexion, contenu)
        self.assertEqual(resultat.erreurs, [])
        self.assertAlmostEqual(lister_mouvements(self.connexion)[0]["montant"], 51)

    def test_remboursement(self):
        contenu = ("Date;Opération;Nombre;Action;Montant\n"
                   "01/02/2026;Remboursement;;;15\n"
                   "02/02/2026;Remboursement;;COFACE;7,5\n").encode()
        resultat = import_csv.importer_mouvements(self.connexion, contenu)
        self.assertEqual(resultat.erreurs, [])
        sans_action, avec_action = lister_mouvements(self.connexion)
        self.assertEqual((sans_action["type"], sans_action["action_id"], sans_action["montant"]),
                         ("remboursement", None, 15))
        self.assertEqual((avec_action["nom_action"], avec_action["montant"]), ("COFACE", 7.5))

    def test_entete_introuvable(self):
        resultat = import_csv.importer_mouvements(self.connexion, b"a,b,c\n1,2,3\n")
        self.assertEqual(len(resultat.erreurs), 1)


class TestImportActions(BaseTemporaire):

    def test_import_liste_actions(self):
        resultat = import_csv.importer_actions(self.connexion, CSV_ACTIONS)
        self.assertEqual(resultat.erreurs, [])
        self.assertEqual(resultat.nb_lignes, 2)

        actions = {a["nom"]: a for a in self.connexion.execute("SELECT * FROM actions")}
        self.assertEqual(actions["M6 METROPOLE TELE"]["ticker"], "MMT.PA")
        self.assertEqual(actions["VERALLIA"]["ticker"], "VRLA.PA")

        dividendes = lire_dividendes_exercice(self.connexion)
        m6 = dividendes[actions["M6 METROPOLE TELE"]["id"]]
        self.assertEqual(m6, {2024: 1.25, 2025: 1.25, 2026: 1.125, 2027: 1.25})
        self.assertEqual(dividendes[actions["VERALLIA"]["id"]], {2024: 1.7, 2025: 1.7})

    def test_reimport_met_a_jour_sans_doublon(self):
        import_csv.importer_actions(self.connexion, CSV_ACTIONS)
        resultat = import_csv.importer_actions(self.connexion, CSV_ACTIONS)
        self.assertEqual(resultat.actions_creees, [])
        self.assertEqual(self.connexion.execute("SELECT COUNT(*) FROM actions").fetchone()[0], 2)

    def test_conversion_symboles(self):
        self.assertEqual(import_csv.convertir_en_symbole_yahoo("EPA:TTE"), "TTE.PA")
        self.assertEqual(import_csv.convertir_en_symbole_yahoo("tte.pa"), "TTE.PA")
        self.assertIsNone(import_csv.convertir_en_symbole_yahoo(""))


class TestYahoo(unittest.TestCase):

    def test_analyse_reponse(self):
        instant = datetime(2026, 11, 22, 12, 0, tzinfo=FUSEAU_HORAIRE)
        semaine = 7 * 24 * 3600
        maintenant = int(instant.timestamp())
        # 3 semaines récentes + une semaine il y a 3 ans + une il y a 8 ans
        horodatages = [maintenant - 8 * 365 * 86400, maintenant - 3 * 365 * 86400,
                       maintenant - 2 * semaine, maintenant - semaine, maintenant]
        reponse = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 78.19, "currency": "EUR",
                     "fiftyTwoWeekLow": 53.29, "fiftyTwoWeekHigh": 85.94},
            "timestamp": horodatages,
            "indicators": {"quote": [{
                "low": [20.0, 40.0, 70.0, None, 77.0],
                "high": [30.0, 90.0, 80.0, None, 79.0],
            }]},
            "events": {"dividends": {
                "1": {"amount": 0.85, "date": maintenant - 30 * 86400},
                "2": {"amount": 0.79, "date": maintenant - 400 * 86400},
            }},
        }]}}
        donnees = analyser_reponse(reponse, instant)
        self.assertEqual(donnees.cours_actuel, 78.19)
        self.assertEqual((donnees.min_1an, donnees.max_1an), (53.29, 85.94))
        self.assertEqual((donnees.min_5ans, donnees.max_5ans), (40.0, 90.0))
        self.assertEqual((donnees.min_10ans, donnees.max_10ans), (20.0, 90.0))
        self.assertAlmostEqual(donnees.dividendes_12_mois, 0.85)
        self.assertEqual(len(donnees.dividendes), 2)
        self.assertLess(donnees.dividendes[0][0], donnees.dividendes[1][0])  # triés par date

    def test_reponse_vide(self):
        with self.assertRaises(ErreurYahoo):
            analyser_reponse({"chart": {"result": None, "error": {}}}, datetime.now(FUSEAU_HORAIRE))


class TestBaseDeDonnees(unittest.TestCase):

    def test_refuse_une_ancienne_base(self):
        chemin = os.path.join(tempfile.mkdtemp(), "ancienne.db")
        connexion = ouvrir_connexion(chemin)
        connexion.execute("CREATE TABLE pea_mouvements (id INTEGER)")
        connexion.commit()
        connexion.close()
        with self.assertRaises(RuntimeError):
            initialiser_base(chemin)

    def test_initialisation_repetee_sans_erreur(self):
        chemin = os.path.join(tempfile.mkdtemp(), "test.db")
        initialiser_base(chemin)
        initialiser_base(chemin)  # au 2e démarrage, rien à faire
        connexion = ouvrir_connexion(chemin)
        self.assertEqual(connexion.execute("PRAGMA user_version").fetchone()[0], len(MIGRATIONS))
        connexion.close()

    def test_migration_2_conserve_les_donnees(self):
        # Simule une base créée par la version 2.0.0 (migration 1 seulement)
        chemin = os.path.join(tempfile.mkdtemp(), "v200.db")
        connexion = ouvrir_connexion(chemin)
        connexion.executescript(f"BEGIN;{MIGRATIONS[0][1]}PRAGMA user_version = 1;COMMIT;")
        connexion.execute("INSERT INTO actions (id, nom) VALUES (1, 'COFACE')")
        connexion.execute("INSERT INTO dividendes_exercice VALUES (1, 2025, 1.3)")
        connexion.execute("INSERT INTO pea_mouvements (date, type, action_id, quantite, montant) "
                          "VALUES ('2025-01-02', 'achat', 1, 10, 150)")
        connexion.commit()
        with self.assertRaises(sqlite3.IntegrityError):  # la v2.0.0 refusait ce type
            connexion.execute("INSERT INTO pea_mouvements (date, type, montant) "
                              "VALUES ('2025-01-03', 'remboursement', 5)")
        connexion.close()

        initialiser_base(chemin)  # applique la migration 2

        connexion = ouvrir_connexion(chemin)
        self.assertEqual(connexion.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(len(lister_mouvements(connexion)), 1)
        self.assertEqual(lire_dividendes_exercice(connexion), {1: {2025: 1.3}})
        connexion.execute("INSERT INTO pea_mouvements (date, type, montant) "
                          "VALUES ('2025-01-03', 'remboursement', 5)")
        # Le lien vers les actions est toujours contrôlé
        with self.assertRaises(sqlite3.IntegrityError):
            connexion.execute("DELETE FROM actions WHERE id = 1")
        connexion.close()


if __name__ == "__main__":
    unittest.main()
