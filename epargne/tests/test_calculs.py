"""
Tests des calculs (outils de saisie, PEA, indicateurs).

Lancer tous les tests depuis le dossier "epargne" :
    python -m unittest discover -s tests -t .
"""

import unittest

from app import outils
from app.pea.calculs import (
    annees_affichees,
    annees_moyenne,
    calculer_moyenne,
    calculer_taux_decision,
    calculer_tendance,
    rejouer_mouvements,
)


def mouvement(date, type_mouvement, montant, action_id=None, nom=None, quantite=None):
    """Fabrique un mouvement au format attendu par rejouer_mouvements."""
    return {"date": date, "type": type_mouvement, "montant": montant,
            "action_id": action_id, "nom_action": nom, "quantite": quantite}


class TestOutils(unittest.TestCase):

    def test_lire_nombre_formats_francais(self):
        self.assertEqual(outils.lire_nombre("12,37"), 12.37)
        self.assertEqual(outils.lire_nombre("1 234,56"), 1234.56)
        self.assertEqual(outils.lire_nombre("1 234,56 €"), 1234.56)
        self.assertEqual(outils.lire_nombre("1.234,56"), 1234.56)
        self.assertEqual(outils.lire_nombre("12.5"), 12.5)
        self.assertIsNone(outils.lire_nombre(""))
        self.assertIsNone(outils.lire_nombre("   "))
        with self.assertRaises(ValueError):
            outils.lire_nombre("abc")
        with self.assertRaises(ValueError):
            outils.lire_nombre("nan")

    def test_lire_nombre_souple_ignore_valeurs_de_tableur(self):
        self.assertIsNone(outils.lire_nombre_souple("x"))
        self.assertIsNone(outils.lire_nombre_souple("#DIV/0!"))
        self.assertEqual(outils.lire_nombre_souple("2,05"), 2.05)

    def test_lire_date(self):
        self.assertEqual(outils.lire_date("05/01/2026"), "2026-01-05")
        self.assertEqual(outils.lire_date("05/01/26"), "2026-01-05")
        self.assertEqual(outils.lire_date("2026-01-05"), "2026-01-05")
        with self.assertRaises(ValueError):
            outils.lire_date("31/02/2026")

    def test_mise_en_forme(self):
        self.assertEqual(outils.format_euros(1234.5), "1 234,50 €")
        self.assertEqual(outils.format_nombre(-0.001), "0,00")
        self.assertEqual(outils.format_pourcent(0.1109), "11,09 %")
        self.assertEqual(outils.format_quantite(20.0), "20")
        self.assertEqual(outils.format_quantite(1.5), "1,5")
        self.assertEqual(outils.format_champ(12.37), "12,37")
        self.assertEqual(outils.format_champ(20.0), "20")
        self.assertEqual(outils.format_date("2026-01-05"), "05/01/2026")
        self.assertEqual(outils.format_euros(None), "—")


class TestRejeuPea(unittest.TestCase):

    def test_prix_de_revient_et_liquidites(self):
        # Exemple du Google Sheet : 25 Carrefour à 12,37 + 2,79 de frais = 312,04
        mouvements = [
            mouvement("2025-01-01", "apport", 1000),
            mouvement("2025-09-03", "achat", 312.04, 1, "CARREFOUR", 25),
            mouvement("2026-05-28", "dividende", 24.25, 1, "CARREFOUR", 25),
        ]
        etat = rejouer_mouvements(mouvements)
        position = etat.positions[1]
        self.assertEqual(position.quantite, 25)
        self.assertAlmostEqual(position.cout_total, 312.04)
        self.assertAlmostEqual(position.pru, 12.4816)
        self.assertAlmostEqual(position.dividendes, 24.25)
        self.assertAlmostEqual(etat.liquidites, 1000 - 312.04 + 24.25)
        self.assertAlmostEqual(etat.apports_nets, 1000)

    def test_vente_partielle_garde_le_pru(self):
        mouvements = [
            mouvement("2025-01-01", "achat", 1000, 1, "A", 100),   # PRU = 10
            mouvement("2025-06-01", "vente", 600, 1, "A", 40),     # vendu 15 / titre
        ]
        etat = rejouer_mouvements(mouvements)
        position = etat.positions[1]
        self.assertEqual(position.quantite, 60)
        self.assertAlmostEqual(position.pru, 10)
        self.assertAlmostEqual(position.cout_total, 600)
        self.assertAlmostEqual(position.plus_value_realisee, 600 - 400)
        self.assertEqual(etat.anomalies, [])

    def test_vente_totale_solde_la_position(self):
        mouvements = [
            mouvement("2025-01-01", "achat", 400, 1, "Nexity", 50),
            mouvement("2026-01-07", "vente", 438.01, 1, "Nexity", 50),
        ]
        position = rejouer_mouvements(mouvements).positions[1]
        self.assertFalse(position.detenue)
        self.assertEqual(position.cout_total, 0)
        self.assertAlmostEqual(position.plus_value_realisee, 38.01)

    def test_vente_superieure_au_detenu_signalee(self):
        mouvements = [mouvement("2025-01-01", "vente", 100, 1, "A", 10)]
        etat = rejouer_mouvements(mouvements)
        self.assertEqual(len(etat.anomalies), 1)
        self.assertFalse(etat.positions[1].detenue)

    def test_jusqu_au_ignore_les_mouvements_posterieurs(self):
        mouvements = [
            mouvement("2025-01-01", "achat", 100, 1, "A", 10),
            mouvement("2026-01-01", "achat", 100, 1, "A", 10),
        ]
        self.assertEqual(rejouer_mouvements(mouvements, jusqu_au="2025-12-31").positions[1].quantite, 10)

    def test_valeur_au_cours_actuel(self):
        position = rejouer_mouvements([mouvement("2025-01-01", "achat", 1000, 1, "A", 100)]).positions[1]
        self.assertIsNone(position.valeur)
        self.assertEqual(position.valeur_retenue, 1000)
        position.cours_actuel = 12
        self.assertAlmostEqual(position.valeur, 1200)
        self.assertAlmostEqual(position.plus_value_latente, 200)
        self.assertAlmostEqual(position.plus_value_latente_ratio, 0.2)


class TestIndicateursActions(unittest.TestCase):
    """Valeurs vérifiées par rapport au Google Sheet d'origine (année 2026)."""

    def test_annees(self):
        self.assertEqual(annees_affichees(2026), [2022, 2023, 2024, 2025, 2026, 2027])
        self.assertEqual(annees_moyenne(2026), [2024, 2025, 2026, 2027])

    def test_moyenne_comme_le_google_sheet(self):
        # M6 : 2024-2027 = 1,25 / 1,25 / 1,125 / 1,25 -> 1,22
        self.assertAlmostEqual(calculer_moyenne([1.25, 1.25, 1.125, 1.25]), 1.21875)
        # TF1 : 2027 non renseigné -> moyenne de 3 valeurs = 0,64
        self.assertAlmostEqual(calculer_moyenne([0.6, 0.63, 0.7]), 0.6433, places=4)
        self.assertIsNone(calculer_moyenne([]))

    def test_tendance_comme_le_google_sheet(self):
        # (dividendes 2022 à 2025, dividendes 2026-2027) -> flèche du Google Sheet
        cas = {
            "M6 →": ([1, 1.25, 1.25, 1.25], [1.125, 1.25], "stable"),
            "TF1 ↑": ([0.5, 0.55, 0.6, 0.63], [0.7], "hausse"),
            "Stellantis ↓": ([1.34, 1.55, 0.68, 0.17], [0.4, 0.6], "baisse"),
            "Carrefour ↑": ([0.56, 0.87, 1.15, 0.97], [1.01, 1.07], "hausse"),
            "Coface →": ([1.52, 1.3, 1.4, 1.3], [1.4, 1.4], "stable"),
            "Imerys →": ([1.45, 1.485], [1.45, 1.565], "stable"),       # +2,7 %
            "Rubis →": ([2.03, 2.05], [2.1, 2.15], "stable"),           # +4,2 %
            "Renault ↑": ([2.2, 2.2], [2.21, 2.426], "hausse"),         # +5,4 %
            "Sodexo ↓": ([2.65, 2.7], [2.359, 2.45], "baisse"),
            "BIC ↓": ([3.08, 2.412], [2.499, 2.588], "baisse"),
        }
        for nom, (passees, recentes, attendu) in cas.items():
            with self.subTest(nom):
                self.assertEqual(calculer_tendance(passees, recentes), attendu)
        # Verallia (2026 et 2027 vides) : #DIV/0! dans le Google Sheet -> pas de tendance
        self.assertIsNone(calculer_tendance([1.7, 1.7], []))

    def test_taux_de_decision_comme_le_google_sheet(self):
        # M6 : cours 10,92, min 1 an 9,76, max 1 an 13,04 -> 64,63 %
        self.assertAlmostEqual(calculer_taux_decision(10.92, 9.76, 13.04), 0.6463, places=4)
        # TF1 : 6,18 / 5,71 / 8,35 -> 82,20 %
        self.assertAlmostEqual(calculer_taux_decision(6.18, 5.71, 8.35), 0.8220, places=4)
        self.assertIsNone(calculer_taux_decision(None, 1, 2))
        self.assertIsNone(calculer_taux_decision(5, 5, 5))


if __name__ == "__main__":
    unittest.main()
