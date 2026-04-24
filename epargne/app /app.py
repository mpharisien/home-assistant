from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3, os, csv, io
from datetime import datetime
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.secret_key = "epargne-secret-2024"
DB_PATH = "/share/epargne/epargne.db"

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    # Enerfip
    conn.execute("""CREATE TABLE IF NOT EXISTS enerfip_projets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL,
        date_investissement TEXT NOT NULL, montant_investi REAL NOT NULL,
        taux_interet REAL NOT NULL, duree_mois INTEGER NOT NULL,
        date_fin TEXT, statut TEXT DEFAULT 'en cours', notes TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS enerfip_flux (
        id INTEGER PRIMARY KEY AUTOINCREMENT, projet_id INTEGER NOT NULL,
        date TEXT NOT NULL, type TEXT NOT NULL, montant REAL NOT NULL, notes TEXT,
        FOREIGN KEY (projet_id) REFERENCES enerfip_projets(id))""")
    # PEA
    conn.execute("""CREATE TABLE IF NOT EXISTS pea_mouvements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        nom_action TEXT,
        ticker TEXT,
        quantite REAL,
        prix_unitaire REAL,
        montant REAL NOT NULL,
        notes TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS pea_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        valeur REAL NOT NULL)""")
    conn.commit()
    conn.close()

# ── Helpers Enerfip ──
def calcul_stats_projet(projet, flux):
    interets_recus = sum(f["montant"] for f in flux if f["type"] == "interet")
    capital_rembourse = sum(f["montant"] for f in flux if f["type"] == "remboursement")
    interets_theoriques = projet["montant_investi"] * (projet["taux_interet"] / 100) * (projet["duree_mois"] / 12)
    capital_restant = projet["montant_investi"] - capital_rembourse
    taux = min((interets_recus / interets_theoriques * 100) if interets_theoriques > 0 else 0, 100)
    return {"interets_recus": round(interets_recus,2), "interets_theoriques": round(interets_theoriques,2),
            "capital_rembourse": round(capital_rembourse,2), "capital_restant": round(capital_restant,2),
            "taux_avancement": round(taux,1)}

def get_enerfip_stats():
    conn = get_db()
    projets = conn.execute("SELECT * FROM enerfip_projets").fetchall()
    total_investi = sum(p["montant_investi"] for p in projets)
    total_interets = 0
    for p in projets:
        flux = conn.execute("SELECT * FROM enerfip_flux WHERE projet_id=?", (p["id"],)).fetchall()
        total_interets += sum(f["montant"] for f in flux if f["type"] == "interet")
    conn.close()
    return {"investi": round(total_investi,2), "gains": round(total_interets,2), "valeur": round(total_investi+total_interets,2)}

# ── Helpers PEA ──
def get_cours(ticker):
    try:
        import urllib.request, json
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except:
        return None

def calcul_positions(mouvements):
    positions = {}
    for m in mouvements:
        if m["type"] not in ("achat", "vente") or not m["nom_action"]:
            continue
        nom = m["nom_action"]
        ticker = m["ticker"] or ""
        if nom not in positions:
            positions[nom] = {"nom": nom, "ticker": ticker, "quantite": 0, "investi": 0}
        if m["type"] == "achat":
            positions[nom]["quantite"] += m["quantite"] or 0
            positions[nom]["investi"] += m["montant"]
        elif m["type"] == "vente":
            positions[nom]["quantite"] -= m["quantite"] or 0
            positions[nom]["investi"] -= m["montant"]
    result = []
    for nom, p in positions.items():
        if p["quantite"] <= 0.001:
            continue
        p["pru"] = p["investi"] / p["quantite"] if p["quantite"] > 0 else 0
        cours = get_cours(p["ticker"]) if p["ticker"] else None
        p["cours"] = cours
        p["valeur"] = round(cours * p["quantite"], 2) if cours else None
        p["valeur_ou_investi"] = p["valeur"] if p["valeur"] else p["investi"]
        p["pv"] = round(p["valeur"] - p["investi"], 2) if p["valeur"] else None
        p["pv_pct"] = round((p["pv"] / p["investi"]) * 100, 2) if p["pv"] is not None and p["investi"] > 0 else None
        p["quantite"] = round(p["quantite"], 4)
        p["investi"] = round(p["investi"], 2)
        p["pru"] = round(p["pru"], 4)
        result.append(p)
    return sorted(result, key=lambda x: x["valeur_ou_investi"], reverse=True)

def calcul_stats_pea(mouvements, positions):
    total_apports = sum(m["montant"] for m in mouvements if m["type"] == "apport")
    total_retraits = sum(m["montant"] for m in mouvements if m["type"] == "retrait")
    total_dividendes = sum(m["montant"] for m in mouvements if m["type"] in ("dividende", "coupon"))
    valeur_totale = sum(p["valeur_ou_investi"] for p in positions)
    apports_nets = total_apports - total_retraits
    performance = valeur_totale + total_dividendes - apports_nets
    performance_pct = (performance / apports_nets * 100) if apports_nets > 0 else 0
    return {"total_apports": round(apports_nets, 2), "total_dividendes": round(total_dividendes, 2),
            "valeur_totale": round(valeur_totale, 2), "performance": round(performance, 2),
            "performance_pct": round(performance_pct, 2)}

def calcul_dividendes_annuels(mouvements):
    par_annee = {}
    for m in mouvements:
        if m["type"] not in ("dividende", "coupon"):
            continue
        annee = m["date"][:4]
        par_annee.setdefault(annee, 0)
        par_annee[annee] += m["montant"]
    # capital investi par année
    capital_par_annee = {}
    for m in mouvements:
        if m["type"] == "achat":
            annee = m["date"][:4]
            capital_par_annee.setdefault(annee, 0)
            capital_par_annee[annee] += m["montant"]
    result = []
    cumul_capital = 0
    for annee in sorted(par_annee.keys()):
        cumul_capital += capital_par_annee.get(annee, 0)
        div = par_annee[annee]
        result.append({"annee": annee, "dividendes": round(div, 2),
                       "capital": round(cumul_capital, 2),
                       "rendement": round(div / cumul_capital * 100, 2) if cumul_capital > 0 else 0})
    return result

# ══════════════════════════════════════
# ROUTES
# ══════════════════════════════════════

@app.route("/")
def dashboard():
    enerfip = get_enerfip_stats()
    total_investi = enerfip["investi"]
    total_gains = enerfip["gains"]
    total_patrimoine = enerfip["valeur"]
    return render_template("dashboard.html", active_page="dashboard", enerfip=enerfip,
        total_investi=total_investi, total_gains=total_gains, total_patrimoine=total_patrimoine)

# ── Enerfip routes ──
@app.route("/enerfip")
def enerfip():
    conn = get_db()
    projets = conn.execute("SELECT * FROM enerfip_projets ORDER BY date_investissement DESC").fetchall()
    projets_avec_stats = []
    total_investi = total_interets = 0
    for p in projets:
        flux = conn.execute("SELECT * FROM enerfip_flux WHERE projet_id=? ORDER BY date", (p["id"],)).fetchall()
        stats = calcul_stats_projet(p, flux)
        projets_avec_stats.append({"projet": p, "flux": flux, "stats": stats})
        total_investi += p["montant_investi"]
        total_interets += stats["interets_recus"]
    conn.close()
    return render_template("enerfip.html", active_page="enerfip", projets=projets_avec_stats,
        total_investi=round(total_investi,2), total_interets=round(total_interets,2))

@app.route("/enerfip/projet/ajouter", methods=["POST"])
def enerfip_ajouter_projet():
    d = request.form
    date_debut = datetime.strptime(d["date_investissement"], "%Y-%m-%d")
    duree = int(d["duree_mois"])
    date_fin = (date_debut + relativedelta(months=duree)).strftime("%Y-%m-%d")
    conn = get_db()
    conn.execute("INSERT INTO enerfip_projets (nom,date_investissement,montant_investi,taux_interet,duree_mois,date_fin,statut,notes) VALUES (?,?,?,?,?,?,?,?)",
        (d["nom"], d["date_investissement"], float(d["montant_investi"]), float(d["taux_interet"]),
         duree, date_fin, d.get("statut","en cours"), d.get("notes","")))
    conn.commit(); conn.close()
    flash("Projet ajouté.", "success")
    return redirect(url_for("enerfip"))

@app.route("/enerfip/flux/ajouter", methods=["POST"])
def enerfip_ajouter_flux():
    d = request.form
    conn = get_db()
    conn.execute("INSERT INTO enerfip_flux (projet_id,date,type,montant,notes) VALUES (?,?,?,?,?)",
        (int(d["projet_id"]), d["date"], d["type"], float(d["montant"]), d.get("notes","")))
    conn.commit(); conn.close()
    flash("Mouvement ajouté.", "success")
    return redirect(url_for("enerfip"))

@app.route("/enerfip/projet/supprimer/<int:projet_id>", methods=["POST"])
def enerfip_supprimer_projet(projet_id):
    conn = get_db()
    conn.execute("DELETE FROM enerfip_flux WHERE projet_id=?", (projet_id,))
    conn.execute("DELETE FROM enerfip_projets WHERE id=?", (projet_id,))
    conn.commit(); conn.close()
    flash("Projet supprimé.", "info")
    return redirect(url_for("enerfip"))

@app.route("/enerfip/flux/supprimer/<int:flux_id>", methods=["POST"])
def enerfip_supprimer_flux(flux_id):
    conn = get_db()
    conn.execute("DELETE FROM enerfip_flux WHERE id=?", (flux_id,))
    conn.commit(); conn.close()
    flash("Mouvement supprimé.", "info")
    return redirect(url_for("enerfip"))

# ── PEA routes ──
@app.route("/pea")
def pea():
    tab = request.args.get("tab", "portefeuille")
    filtre_action = request.args.get("filtre_action", "")
    filtre_type = request.args.get("filtre_type", "")
    conn = get_db()
    tous_mouvements = conn.execute("SELECT * FROM pea_mouvements ORDER BY date DESC").fetchall()
    actions_liste = sorted(set(m["nom_action"] for m in tous_mouvements if m["nom_action"]))
    types_liste = sorted(set(m["type"] for m in tous_mouvements))
    mouvements_filtres = tous_mouvements
    if filtre_action:
        mouvements_filtres = [m for m in mouvements_filtres if m["nom_action"] == filtre_action]
    if filtre_type:
        mouvements_filtres = [m for m in mouvements_filtres if m["type"] == filtre_type]
    positions = calcul_positions(tous_mouvements)
    stats = calcul_stats_pea(tous_mouvements, positions)
    dividendes_annuels = calcul_dividendes_annuels(tous_mouvements)
    snapshots_raw = conn.execute("SELECT * FROM pea_snapshots ORDER BY date").fetchall()
    snapshots = []
    for s in snapshots_raw:
        apports_a_date = sum(m["montant"] for m in tous_mouvements
                            if m["type"] == "apport" and m["date"] <= s["date"])
        snapshots.append({"date": s["date"], "valeur": s["valeur"], "apports": round(apports_a_date, 2)})
    conn.close()
    return render_template("pea.html", active_page="pea", tab=tab,
        positions=positions, stats=stats, mouvements=mouvements_filtres,
        actions_liste=actions_liste, types_liste=types_liste,
        filtre_action=filtre_action, filtre_type=filtre_type,
        dividendes_annuels=dividendes_annuels, snapshots=snapshots)

@app.route("/pea/mouvement/ajouter", methods=["POST"])
def pea_ajouter_mouvement():
    d = request.form
    conn = get_db()
    conn.execute("INSERT INTO pea_mouvements (date,type,nom_action,ticker,quantite,prix_unitaire,montant,notes) VALUES (?,?,?,?,?,?,?,?)",
        (d["date"], d["type"], d.get("nom_action") or None, d.get("ticker") or None,
         float(d["quantite"]) if d.get("quantite") else None,
         float(d["prix_unitaire"]) if d.get("prix_unitaire") else None,
         float(d["montant"]), d.get("notes","")))
    conn.commit(); conn.close()
    flash("Mouvement ajouté.", "success")
    return redirect(url_for("pea", tab="import"))

@app.route("/pea/mouvement/supprimer/<int:mouvement_id>", methods=["POST"])
def pea_supprimer_mouvement(mouvement_id):
    conn = get_db()
    conn.execute("DELETE FROM pea_mouvements WHERE id=?", (mouvement_id,))
    conn.commit(); conn.close()
    flash("Mouvement supprimé.", "info")
    return redirect(url_for("pea", tab="historique"))

@app.route("/pea/mouvement/modifier/<int:mouvement_id>", methods=["POST"])
def pea_modifier_mouvement(mouvement_id):
    d = request.form
    conn = get_db()
    conn.execute("""UPDATE pea_mouvements 
        SET date=?, type=?, nom_action=?, ticker=?, quantite=?, prix_unitaire=?, montant=?, notes=?
        WHERE id=?""",
        (d["date"], d["type"],
         d.get("nom_action") or None,
         d.get("ticker") or None,
         float(d["quantite"]) if d.get("quantite") else None,
         float(d["prix_unitaire"]) if d.get("prix_unitaire") else None,
         float(d["montant"]),
         d.get("notes",""),
         mouvement_id))
    conn.commit(); conn.close()
    flash("Mouvement modifié.", "success")
    return redirect(url_for("pea", tab="historique"))

@app.route("/pea/snapshot/ajouter", methods=["POST"])
def pea_ajouter_snapshot():
    d = request.form
    conn = get_db()
    conn.execute("INSERT INTO pea_snapshots (date,valeur) VALUES (?,?)", (d["date"], float(d["valeur"])))
    conn.commit(); conn.close()
    flash("Snapshot enregistré.", "success")
    return redirect(url_for("pea", tab="performance"))

@app.route("/pea/import", methods=["POST"])
def pea_import_csv():
    fichier = request.files.get("fichier")
    if not fichier:
        flash("Aucun fichier sélectionné.", "info")
        return redirect(url_for("pea", tab="import"))
    contenu = fichier.read().decode("utf-8-sig")
    premiere_ligne = contenu.split('\n')[0]
    separateur = ';' if ';' in premiere_ligne else ','
    reader = csv.DictReader(io.StringIO(contenu), delimiter=separateur)
    conn = get_db()
    nb = 0
    erreurs = []
    def parse_nombre(val):
        if not val or not val.strip():
            return None
        val = val.strip().replace('(', '-').replace(')', '')
        if ',' in val and '.' in val:
            val = val.replace('.', '').replace(',', '.')
        elif ',' in val:
            val = val.replace(',', '.')
        return float(val)
    types_valides = {"achat", "vente", "coupon", "apport", "retrait", "remboursement"}
    for i, row in enumerate(reader, 2):
        try:
            type_mouv = row.get("type", "").strip().lower()
            if type_mouv == "dividende":
                type_mouv = "coupon"
            if type_mouv == "apport de liquidités":
                type_mouv = "apport"
            if type_mouv not in types_valides:
                erreurs.append(f"Ligne {i} : type inconnu '{type_mouv}'")
                continue
            montant = parse_nombre(row.get("montant", ""))
            if montant is None:
                erreurs.append(f"Ligne {i} : montant manquant")
                continue
            conn.execute("INSERT INTO pea_mouvements (date,type,nom_action,ticker,quantite,prix_unitaire,montant,notes) VALUES (?,?,?,?,?,?,?,?)",
                (row["date"].strip(), type_mouv,
                 row.get("nom_action","").strip() or None,
                 row.get("ticker","").strip() or None,
                 parse_nombre(row.get("quantite","")),
                 parse_nombre(row.get("prix_unitaire","")),
                 montant, row.get("notes","").strip()))
            nb += 1
        except Exception as e:
            erreurs.append(f"Ligne {i} : {e}")
    conn.commit()
    conn.close()
    if nb:
        flash(f"{nb} mouvement(s) importé(s) avec succès.", "success")
    if erreurs:
        for e in erreurs[:5]:
            flash(e, "info")
    return redirect(url_for("pea", tab="historique"))

# ── Placeholders ──
@app.route("/epsor")
def epsor():
    return render_template("placeholder.html", active_page="epsor", titre="Epsor", sous_titre="Épargne salariale — Bientôt disponible")

@app.route("/binance")
def binance():
    return render_template("placeholder.html", active_page="binance", titre="Binance", sous_titre="Crypto — Bientôt disponible")

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
