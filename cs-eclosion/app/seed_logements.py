"""
Script de peuplement initial du module Logements / Habitants.

À exécuter UNE SEULE FOIS, après le premier déploiement de cette mise à jour,
pour importer les 59 logements + leur historique propriétaire (2023 et 2026)
à partir du fichier Google Sheet que Marc-Antoine avait constitué manuellement.

Usage (depuis le shell de l'add-on, ou via Studio Code Server) :
    cd /app && python3 seed_logements.py

Ce script est protégé contre une double exécution : si des logements existent
déjà en base, il ne fait rien et l'affiche clairement.
"""
import database as db

LOGEMENTS = [
    ("135", "29", 2, 131.0, 0, 1, 0, 0, None, "100", "341", 12.0),
    ("107", "7", 2, 126.0, 1, 0, 1, 0, None, "101 (PMR)", "342 (PMR)", 12.0),
    ("118", "15", 2, 121.0, 0, 0, 0, 1, None, "102", "343", 12.0),
    ("129", "24", 2, 123.0, 0, 0, 0, 1, None, "103", "344", 12.0),
    ("117", "14", 3, 173.0, 0, 0, 0, 2, None, "104 (PMR)", "345 (PMR)", 12.0),
    ("128", "23", 3, 176.0, 0, 0, 0, 2, None, "105", "346", 12.0),
    ("137", "31", 2, 125.0, 0, 0, 0, 1, None, "106", "347", 12.0),
    ("103", "3", 2, 129.0, 1, 0, 1, 0, None, "107", "348", 12.0),
    ("122", "17", 3, 174.0, 0, 0, 0, 2, None, "108", "349", 12.0),
    ("136", "30", 3, 179.0, 0, 0, 0, 2, None, "109", "350", 12.0),
    ("243", "59", 3, 154.0, 0, 1, 0, 0, None, "110", "351", 12.0),
    ("131", "25", 2, 116.0, 0, 0, 0, 0, None, "111", "352", 12.0),
    ("235", "55", 3, 216.0, 0, 0, 0, 2, None, "112 D", "353 D", 19.0),
    ("241", "57", 4, 281.0, 1, 0, 0, 0, 82.8, "113 D", "354 D", 19.0),
    ("242", "58", 4, 252.0, 2, 0, 0, 0, 72.94, "114 D", "355 D", 19.0),
    ("225", "49", 3, 212.0, 0, 0, 0, 2, None, "115 D", "356 D", 17.0),
    ("214", "42", 3, 179.0, 0, 0, 0, 1, None, "116", "357", 12.0),
    ("224", "48", 3, 183.0, 0, 0, 0, 1, None, "117", "358", 12.0),
    ("211", "39", 2, 121.0, 0, 0, 0, 1, None, "60", "301", 12.0),
    ("221", "45", 2, 124.0, 0, 0, 0, 1, None, "61", "302", 12.0),
    ("231", "51", 2, 126.0, 0, 0, 0, 1, None, "62", "303", 12.0),
    ("203", "36", 2, 122.0, 0, 0, 0, 0, None, "63", "304", 12.0),
    ("204", "37", 2, 114.0, 0, 0, 0, 0, None, "64", "305", 15.0),
    ("205", "38", 2, 113.0, 0, 0, 0, 0, 42.08, "65", "306", 14.0),
    ("201", "34", 3, 183.0, 1, 0, 1, 0, None, "66", "307", 12.0),
    ("202", "35", 3, 179.0, 1, 0, 1, 0, None, "67", "308", 12.0),
    ("212", "40", 3, 173.0, 0, 0, 0, 2, None, "68", "309", 12.0),
    ("222", "46", 3, 176.0, 0, 0, 0, 2, None, "69", "310", 12.0),
    ("232", "52", 3, 181.0, 0, 0, 0, 2, None, "70", "311", 12.0),
    ("213", "41", 3, 177.0, 0, 1, 0, 0, None, "71", "312", 12.0),
    ("223", "47", 3, 182.0, 0, 1, 0, 0, None, "72", "313", 12.0),
    ("233", "53", 3, 185.0, 0, 1, 0, 0, None, "73", "314", 12.0),
    ("234", "54", 2, 187.0, 0, 0, 0, 1, None, "74", "315", 12.0),
    ("215", "43", 3, 207.0, 0, 0, 0, 2, 68.24, "75", "316", 12.0),
    ("216", "44", 3, 150.0, 0, 0, 0, 0, None, "76", "317", 12.0),
    ("226", "50", 3, 152.0, 0, 1, 0, 0, None, "77", "318", 12.0),
    ("111", "8", 2, 114.0, 0, 0, 0, 0, None, "78", "319", 12.0),
    ("121", "16", 2, 117.0, 0, 0, 0, 0, None, "79", "320", 12.0),
    ("236", "56", 3, 156.0, 0, 1, 0, 0, 55.59, "80", "321", 12.0),
    ("123", "18", 2, 124.0, 0, 1, 0, 0, None, "81", "322", 12.0),
    ("104", "4", 2, 130.0, 1, 0, 1, 0, None, "82", "323", 12.0),
    ("113", "10", 2, 123.0, 0, 1, 0, 0, None, "83", "324", 12.0),
    ("101", "1", 2, 121.0, 0, 0, 0, 0, None, "84", "325", 12.0),
    ("124", "19", 2, 125.0, 0, 1, 0, 0, None, "85", "326", 12.0),
    ("132", "26", 2, 156.0, 0, 0, 0, 0, 49.41, "86", "327", 12.0),
    ("105", "5", 2, 131.0, 1, 0, 1, 0, None, "87", "328", 12.0),
    ("114", "11", 2, 124.0, 0, 1, 0, 0, None, "88", "329", 12.0),
    ("125", "20", 2, 127.0, 0, 1, 0, 0, 40.53, "89", "330", 12.0),
    ("133", "27", 2, 129.0, 0, 1, 0, 0, None, "90", "331", 12.0),
    ("106", "6", 2, 130.0, 1, 0, 1, 0, None, "91", "332", 12.0),
    ("115", "12", 2, 124.0, 0, 1, 0, 0, None, "92", "333", 12.0),
    ("126", "21", 2, 127.0, 0, 1, 0, 0, None, "93", "334", 12.0),
    ("112", "9", 4, 234.0, 0, 1, 0, 0, None, "94 D", "335 D", 20.0),
    ("141", "32", 4, 273.0, 1, 0, 0, 0, 82.0, "95 D", "336 D", 19.0),
    ("142", "33", 4, 292.0, 1, 0, 0, 0, 87.82, "96 D (PMR)", "337 D (PMR)", 19.0),
    ("134", "28", 2, 129.0, 0, 1, 0, 0, None, "97", "338", 12.0),
    ("116", "13", 2, 126.0, 0, 1, 0, 0, None, "98", "339", 12.0),
    ("127", "22", 2, 128.0, 0, 1, 0, 0, None, "99", "340", 12.0),
    ("102", "2", 2, 109.0, 0, 0, 0, 0, None, None, None, None),
]

HISTORIQUE = [
    ("135", "2023-05-31", "proprietaire", "Mme CHRISTELLE HAMMOU"),
    ("135", "2026-03-28", "proprietaire", "Mme CHRISTELLE HAMMOU"),
    ("107", "2023-05-31", "proprietaire", "Mme VANESSA TOULISSE"),
    ("107", "2026-03-28", "proprietaire", "Mme VANESSA TOULISSE"),
    ("118", "2023-05-31", "proprietaire", "Mme HELENE DEH"),
    ("118", "2026-03-28", "proprietaire", "Mme HELENE DEH"),
    ("129", "2023-05-31", "proprietaire", "Mme SANDRINE GRAND"),
    ("129", "2026-03-28", "proprietaire", "Mme SANDRINE GRAND"),
    ("117", "2023-05-31", "proprietaire", "M. DOMINIQUE BATANI"),
    ("117", "2026-03-28", "proprietaire", "M. DOMINIQUE BATANI"),
    ("128", "2023-05-31", "proprietaire", "M. ou Mme EMMANUEL / SEGOLENE ALPHONSINE / TRAPLETTI /"),
    ("128", "2026-03-28", "proprietaire", "M. ou Mme EMMANUEL / SEGOLENE ALPHONSINE / TRAPLETTI"),
    ("137", "2023-05-31", "proprietaire", "M. TARIK HASSANINE"),
    ("137", "2026-03-28", "proprietaire", "M. TARIK HASSANINE"),
    ("103", "2023-05-31", "proprietaire", "M. ou Mme DOMINIQUE CALME OU VAUTRIN"),
    ("103", "2026-03-28", "proprietaire", "M. ou Mme DOMINIQUE CALME OU VAUTRIN"),
    ("122", "2023-05-31", "proprietaire", "M. PATRICE LECOEUCHE"),
    ("122", "2026-03-28", "proprietaire", "M. PATRICE LECOEUCHE"),
    ("136", "2023-05-31", "proprietaire", "M. MOHAMED SECK"),
    ("136", "2026-03-28", "proprietaire", "M. MOHAMED SECK"),
    ("243", "2023-05-31", "proprietaire", "M. OLIVIER RUDELLE"),
    ("243", "2026-03-28", "proprietaire", "M. OLIVIER RUDELLE"),
    ("131", "2023-05-31", "proprietaire", "Mme MURIEL TALLET"),
    ("131", "2026-03-28", "proprietaire", "Mme MURIEL TALLET"),
    ("235", "2023-05-31", "proprietaire", "M. FLORIAN SICOURMAT"),
    ("235", "2026-03-28", "proprietaire", "M. FLORIAN SICOURMAT"),
    ("241", "2023-05-31", "proprietaire", "M. ou Mme MARC-ANTOINE PHARISIEN OU MARCAILLE"),
    ("241", "2026-03-28", "proprietaire", "M. ou Mme MARC-ANTOINE PHARISIEN OU MARCAILLE"),
    ("242", "2023-05-31", "proprietaire", "M. MAXIME ENCHERY"),
    ("242", "2026-03-28", "proprietaire", "M. OLIVIER ROUZEVAL"),
    ("225", "2023-05-31", "proprietaire", "M. DAVID LEPEIGNEUL"),
    ("225", "2026-03-28", "proprietaire", "M. DAVID LEPEIGNEUL"),
    ("214", "2023-05-31", "proprietaire", "M. FRANCOIS RENE CRAMPET"),
    ("214", "2026-03-28", "proprietaire", "M. FRANCOIS RENE CRAMPET"),
    ("224", "2023-05-31", "proprietaire", "M. LUDOVIC MIRAMBET"),
    ("224", "2026-03-28", "proprietaire", "M. LUDOVIC MIRAMBET"),
    ("211", "2023-05-31", "proprietaire", "M. ALEX GOUILLON"),
    ("211", "2026-03-28", "proprietaire", "M. ALEX GOUILLON"),
    ("221", "2023-05-31", "proprietaire", "Mme SANDRINE COUGNOT"),
    ("221", "2026-03-28", "proprietaire", "Mme SANDRINE COUGNOT"),
    ("231", "2023-05-31", "proprietaire", "M et Mme MURIEL ET BRUNO CAILLON"),
    ("231", "2026-03-28", "proprietaire", "M et Mme MURIEL ET BRUNO CAILLON"),
    ("203", "2023-05-31", "proprietaire", "Mme ELODIE SORNAY"),
    ("203", "2026-03-28", "proprietaire", "Mme ELODIE SORNAY"),
    ("204", "2023-05-31", "proprietaire", "M. BORRIS MAKAYA DJHON"),
    ("204", "2026-03-28", "proprietaire", "M. BORRIS MAKAYA DJHON"),
    ("205", "2023-05-31", "proprietaire", "M. CHRISTOPHER INACIO"),
    ("205", "2026-03-28", "proprietaire", "M. CHRISTOPHER INACIO"),
    ("201", "2023-05-31", "proprietaire", "M. ERIC PERROT"),
    ("201", "2026-03-28", "proprietaire", "M et Mme ERIC et ISABEL PERROT"),
    ("202", "2023-05-31", "proprietaire", "Mme BEATRICE NGAFACK SONNE"),
    ("202", "2026-03-28", "proprietaire", "Mme BEATRICE NGAFACK SONNE"),
    ("212", "2023-05-31", "proprietaire", "Mme CHRYSTELLE FICADIERE"),
    ("212", "2026-03-28", "proprietaire", "Mme CHRYSTELLE FICADIERE"),
    ("222", "2023-05-31", "proprietaire", "M. PATRICK DA COSTA"),
    ("222", "2026-03-28", "proprietaire", "M. PATRICK DA COSTA"),
    ("232", "2023-05-31", "proprietaire", "M. ou Mme TONY ET CAROLE ROBITAILLE ET DELABRIERE"),
    ("232", "2026-03-28", "proprietaire", "M. ou Mme TONY ET CAROLE ROBITAILLE ET DELABRIERE"),
    ("213", "2023-05-31", "proprietaire", "M. CEDRIC PHUNG"),
    ("213", "2026-03-28", "proprietaire", "M. CEDRIC PHUNG"),
    ("223", "2023-05-31", "proprietaire", "M. JEAN MICHEL FEUNTEUN"),
    ("223", "2026-03-28", "proprietaire", "M. JEAN MICHEL FEUNTEUN"),
    ("233", "2023-05-31", "proprietaire", "M et Mme FRANK ET PASCALE FAUGERES"),
    ("233", "2026-03-28", "proprietaire", "M et Mme FRANK ET PASCALE FAUGERES"),
    ("234", "2023-05-31", "proprietaire", "M. LOIC PERSON"),
    ("234", "2026-03-28", "proprietaire", "M. LOIC PERSON"),
    ("215", "2023-05-31", "proprietaire", "M. ou Mme NICOLAS OU PHANIE FLECK OU DE MAISTRE"),
    ("215", "2026-03-28", "proprietaire", "M. ou Mme NICOLAS OU PHANIE FLECK OU DE MAISTRE"),
    ("216", "2023-05-31", "proprietaire", "M et Mme DAVID ET IMAN VARUSIO"),
    ("216", "2026-03-28", "proprietaire", "M et Mme DAVID ET IMAN VARUSIO"),
    ("226", "2023-05-31", "proprietaire", "Mme VALERIE LALIEUX"),
    ("226", "2026-03-28", "proprietaire", "Mme VALERIE LALIEUX"),
    ("111", "2023-05-31", "proprietaire", "Mme LAMIA LABASSI"),
    ("111", "2026-03-28", "proprietaire", "Mme LAMIA LABASSI"),
    ("121", "2023-05-31", "proprietaire", "M et Mme DAVID MALARD"),
    ("121", "2026-03-28", "proprietaire", "M. DAVID/SOPHIE MALARD"),
    ("236", "2023-05-31", "proprietaire", "M. VALENTIN LOUPE"),
    ("236", "2026-03-28", "proprietaire", "Mme OLFA KHARRAT"),
    ("123", "2023-05-31", "proprietaire", "M. YOANN PINOY"),
    ("123", "2026-03-28", "proprietaire", "M. YOANN PINOY"),
    ("104", "2023-05-31", "proprietaire", "M. CARLOS LOPES"),
    ("104", "2026-03-28", "proprietaire", "M. CARLOS LOPES"),
    ("113", "2023-05-31", "proprietaire", "M et Mme PHILIPPE FAUGERES"),
    ("113", "2026-03-28", "proprietaire", "M et Mme PHILIPPE FAUGERES"),
    ("101", "2023-05-31", "proprietaire", "M. JIMMY MORNET"),
    ("101", "2026-03-28", "proprietaire", "M. JIMMY MORNET"),
    ("124", "2023-05-31", "proprietaire", "M. ERWAN COTARD"),
    ("124", "2026-03-28", "proprietaire", "M. ERWAN COTARD"),
    ("132", "2023-05-31", "proprietaire", "M. VIVIEN FERODET"),
    ("132", "2026-03-28", "proprietaire", "Mme DAHLIA DRALI"),
    ("105", "2023-05-31", "proprietaire", "Mme JENNIFER EDLER VON GRAEVE"),
    ("105", "2026-03-28", "proprietaire", "Mme JENNIFER EDLER VON GRAEVE"),
    ("114", "2023-05-31", "proprietaire", "M. FARID CHAKIB RAHMOUNE"),
    ("114", "2026-03-28", "proprietaire", "M. FARID CHAKIB RAHMOUNE"),
    ("125", "2023-05-31", "proprietaire", "M. SEBASTIEN VAN STEENKISTE"),
    ("125", "2026-03-28", "proprietaire", "M. SEBASTIEN VAN STEENKISTE"),
    ("133", "2023-05-31", "proprietaire", "M. ARNAUD DESHAYES"),
    ("133", "2026-03-28", "proprietaire", "M. ARNAUD DESHAYES"),
    ("106", "2023-05-31", "proprietaire", "Mme ELISABETH LE LOSTEC"),
    ("106", "2026-03-28", "proprietaire", "Mme SOPHIA LING"),
    ("115", "2023-05-31", "proprietaire", "Mme AUDREY BILLOD MOREL"),
    ("115", "2026-03-28", "proprietaire", "Mme AUDREY BILLOD MOREL"),
    ("126", "2023-05-31", "proprietaire", "Mme FLORENCE DAMERON"),
    ("126", "2026-03-28", "proprietaire", "Mme FLORENCE DAMERON"),
    ("112", "2023-05-31", "proprietaire", "M. JEAN CHARLES LE BARON"),
    ("112", "2026-03-28", "proprietaire", "M. JEAN CHARLES LE BARON"),
    ("141", "2023-05-31", "proprietaire", "M. ou Mme CHRISTOPHE COLLANGE / DENIN"),
    ("141", "2026-03-28", "proprietaire", "M. EMMANUEL CAUET"),
    ("142", "2023-05-31", "proprietaire", "M. LAURENT TACHET"),
    ("142", "2026-03-28", "proprietaire", "Mme SYLVIE LEONARD"),
    ("134", "2023-05-31", "proprietaire", "M. STEPHANE DIGRACI"),
    ("134", "2026-03-28", "proprietaire", "M. STEPHANE DIGRACI"),
    ("116", "2023-05-31", "proprietaire", "M. RAVINDER SACHDEVA"),
    ("116", "2026-03-28", "proprietaire", "M. RAVINDER SACHDEVA"),
    ("127", "2023-05-31", "proprietaire", "M. EMMANUEL CAUET"),
    ("127", "2026-03-28", "proprietaire", "M. ou Mme CHRISTOPHE COLLANGE /  DENIN"),
    ("102", "2023-05-31", "proprietaire", "Mme MAUD MORNET"),
    ("102", "2026-03-28", "proprietaire", "Mme MAUD MORNET"),
]


def run():
    db.init_db()

    if db.count_logements() > 0:
        print(f"⚠️  {db.count_logements()} logements existent déjà en base. Seed annulé pour éviter les doublons.")
        print("Si tu veux vraiment ré-exécuter ce script, vide d'abord les tables 'logements' et 'logement_historique'.")
        return

    numero_to_id = {}
    for l in LOGEMENTS:
        logement_id = db.insert_logement(*l)
        numero_to_id[l[0]] = logement_id

    nb_historique = 0
    for numero_app, date, categorie, valeur in HISTORIQUE:
        logement_id = numero_to_id.get(numero_app)
        if logement_id:
            db.add_historique_entry(logement_id, date, categorie, valeur)
            nb_historique += 1

    print(f"✅ Seed terminé : {len(LOGEMENTS)} logements créés, {nb_historique} entrées d'historique ajoutées.")


if __name__ == '__main__':
    run()
