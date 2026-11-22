"""
Tests des pages web : chaque page doit s'afficher sans erreur, et les
formulaires principaux doivent enregistrer les données.
Utilise le « client de test » de Flask : aucun serveur à lancer, pas d'Internet.
"""

import io
import os
import tempfile
import unittest

from app.bourse_yahoo import DonneesBourse, enregistrer_donnees
from app.main import creer_application
from tests.test_import_et_yahoo import CSV_ACTIONS, CSV_MOUVEMENTS


class TestPages(unittest.TestCase):

    def setUp(self):
        self.chemin = os.path.join(tempfile.mkdtemp(), "test.db")
        self.application = creer_application(self.chemin)
        self.client = self.application.test_client()

    def verifier_page(self, adresse):
        reponse = self.client.get(adresse)
        self.assertEqual(reponse.status_code, 200, f"{adresse} -> {reponse.status_code}")
        return reponse.get_data(as_text=True)

    def toutes_les_pages(self):
        pages = ["/", "/pea/", "/pea/historique", "/pea/dividendes", "/pea/actions",
                 "/pea/actions/nouvelle", "/pea/mouvements/nouveau", "/pea/import",
                 "/poche/epsor", "/poche/enerfip", "/poche/epsor/mouvements/nouveau"]
        for adresse in pages:
            self.verifier_page(adresse)

    def test_pages_vides(self):
        self.toutes_les_pages()

    def test_pages_avec_donnees(self):
        # Import des actions puis des mouvements
        reponse = self.client.post("/pea/import/actions",
                                   data={"fichier": (io.BytesIO(CSV_ACTIONS), "actions.csv")})
        self.assertEqual(reponse.status_code, 302)
        reponse = self.client.post("/pea/import/mouvements",
                                   data={"fichier": (io.BytesIO(CSV_MOUVEMENTS), "mvt.csv")})
        self.assertEqual(reponse.status_code, 302)

        # Cours fictif pour une action détenue (sans appeler Yahoo)
        from app.base_de_donnees import ouvrir_connexion
        connexion = ouvrir_connexion(self.chemin)
        carrefour = connexion.execute("SELECT id FROM actions WHERE nom = 'CARREFOUR'").fetchone()["id"]
        enregistrer_donnees(connexion, carrefour, DonneesBourse(
            cours_actuel=16.1, devise="EUR", min_1an=12.63, max_1an=17.54,
            dividendes_12_mois=1.15, dividendes=[("2026-05-28", 1.15)],
        ))
        connexion.close()

        # Poche Epsor : un mouvement et une valorisation
        self.client.post("/poche/epsor/mouvements/nouveau",
                         data={"date": "2026-03-01", "type": "interessement", "libelle": "Fonds A", "montant": "1500"})
        self.client.post("/poche/epsor/valorisations", data={"date": "2026-06-30", "valeur": "1 620,50"})

        self.toutes_les_pages()
        self.verifier_page(f"/pea/actions/{carrefour}")
        self.verifier_page(f"/pea/historique?annee=2026&action={carrefour}&type=achat")

        accueil = self.verifier_page("/")
        self.assertIn("1 620,50", accueil)        # valeur Epsor
        actions = self.verifier_page("/pea/actions")
        self.assertNotIn("<th>Symbole</th>", actions)    # colonne retirée en 2.1.0
        self.assertIn('title="MMT.PA"', actions)          # symbole visible au survol du nom
        self.assertIn("Tes données", actions)            # origine des colonnes indiquée
        self.assertIn("nom-detenue", actions)           # Carrefour est détenue
        dividendes = self.verifier_page("/pea/dividendes")
        self.assertIn("2025", dividendes)

    def test_saisie_modification_suppression_mouvement(self):
        # Achat sans montant : calculé automatiquement (10 x 12,5 + 1,5 = 126,50)
        reponse = self.client.post("/pea/mouvements/nouveau", data={
            "date": "2026-02-01", "type": "achat", "action": "Nouvelle Action",
            "quantite": "10", "cours": "12,5", "frais": "1,5", "montant": "",
        })
        self.assertEqual(reponse.status_code, 302)
        historique = self.verifier_page("/pea/historique")
        self.assertIn("126,50", historique)
        self.assertIn("Nouvelle Action", historique)

        # Erreur de saisie : la page est réaffichée avec le message
        reponse = self.client.post("/pea/mouvements/nouveau", data={
            "date": "2026-02-01", "type": "vente", "action": "Nouvelle Action", "quantite": "abc",
        })
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("pas un nombre valide", reponse.get_data(as_text=True))

        # Modification puis suppression
        self.verifier_page("/pea/mouvements/1/modifier")
        reponse = self.client.post("/pea/mouvements/1/modifier", data={
            "date": "2026-02-02", "type": "achat", "action": "Nouvelle Action",
            "quantite": "10", "cours": "12,5", "frais": "0", "montant": "",
        })
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("125,00", self.verifier_page("/pea/historique"))
        self.client.post("/pea/mouvements/1/supprimer")
        self.assertIn("Aucun mouvement", self.verifier_page("/pea/historique"))

    def test_saisie_remboursement_sans_action(self):
        reponse = self.client.post("/pea/mouvements/nouveau", data={
            "date": "2026-02-01", "type": "remboursement", "action": "", "montant": "12,40",
        })
        self.assertEqual(reponse.status_code, 302)
        historique = self.verifier_page("/pea/historique")
        self.assertIn("etiquette-remboursement", historique)
        self.assertIn("12,40", historique)
        self.verifier_page("/pea/mouvements/1/modifier")
        self.verifier_page("/pea/")

    def test_fiche_action_et_dividendes(self):
        reponse = self.client.post("/pea/actions/nouvelle", data={
            "nom": "TF1", "ticker": "tfi.pa", "suivie": "on",
            "dividende_2025": "0,63", "dividende_2026": "0,7",
        })
        self.assertEqual(reponse.status_code, 302)
        page = self.verifier_page("/pea/actions")
        self.assertIn("TFI.PA", page)
        self.assertIn("0,630", page)
        # Doublon refusé
        reponse = self.client.post("/pea/actions/nouvelle", data={"nom": "tf1"})
        self.assertIn("existe déjà", reponse.get_data(as_text=True))

    def test_poche_inconnue(self):
        self.assertEqual(self.client.get("/poche/inconnue").status_code, 404)


if __name__ == "__main__":
    unittest.main()
