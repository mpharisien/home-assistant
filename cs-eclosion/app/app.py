import os
import io
import csv
import json
import tempfile
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session

import database as db
import regroupements as regr

app = Flask(__name__)
app.secret_key = 'cs_eclosion_secret_2024'

db.init_db()


# ─── Contexte global des templates ────────────────────────────────────────────

# Associe chaque endpoint Flask à son module (pour activer le bon item de sidebar)
MODULES_PAR_ENDPOINT = {
    'dashboard': 'depenses',
    'foncia': 'depenses',
    'fournisseurs': 'depenses',
    'import_csv': 'depenses',
    'logements': 'logements',
    'sujets_ag': 'sujets_ag',
    'ocea_dashboard': 'ocea',
    'ocea_mon_logement': 'ocea',
    'ocea_suivi': 'ocea',
    'ocea_saisie': 'ocea',
    'ocea_saisie_thermique': 'ocea',
}


@app.context_processor
def inject_module_actif():
    return {'module_actif': MODULES_PAR_ENDPOINT.get(request.endpoint)}


# ─── Utilitaires ──────────────────────────────────────────────────────────────

def parse_montant(s):
    """Convertit '1 147,02' ou '1147,02' ou '-21682,80' en float."""
    return float(s.replace('\xa0', '').replace(' ', '').replace(',', '.'))


def split_code_libelle(raw):
    """'001 - CHARGES GENERALES' -> ('001', 'CHARGES GENERALES')"""
    raw = raw.strip()
    if ' - ' in raw:
        code, lib = raw.split(' - ', 1)
        return code.strip(), lib.strip()
    return raw, raw


def detect_type_fichier(header_line):
    """
    Détecte si le CSV importé est un fichier de DÉPENSES (détail écriture par écriture)
    ou un fichier de BUDGET (comparatif budget/réalisé par poste).
    Retourne 'depenses' ou 'budget' ou None si non reconnu.
    """
    cols = [c.strip().upper() for c in header_line.split(';')]
    if 'BUDGET EN COURS' in cols:
        return 'budget'
    if 'DATE' in cols and 'LIBELLE' in cols:
        return 'depenses'
    return None


def detect_format(header_line):
    """
    Détecte le format du CSV Foncia "dépenses" exporté.
    Format A (exercice clôturé)  : DATE;CLE DE REPARTITION;TYPE DE CHARGE;LIBELLE;A REPARTIR;TVA;RECUPERABLE
    Format B (exercice en cours) : DATE;CLE DE REPARTITION;TYPE DE CHARGE;LIBELLE;MONTANT
    Le format détermine aussi de façon fiable le statut de l'exercice : 'cloture' -> validé, 'en_cours' -> en cours.
    """
    cols = [c.strip().upper() for c in header_line.split(';')]
    if 'TVA' in cols and 'RECUPERABLE' in cols:
        return 'cloture'
    return 'en_cours'


def parse_csv_foncia(content_bytes):
    """
    Parse un export Myfoncia "dépenses" (détail des écritures), quel que soit son format.
    Retourne (annee, statut_detecte, lignes) où lignes = liste de tuples prêts pour insert_depenses_bulk :
    (date_iso, cle_code, cle_libelle, type_code, type_libelle, libelle, montant, tva, recuperable)
    Exclut la ligne TOTAUX.
    """
    content = content_bytes.decode('utf-8-sig').splitlines()
    if not content:
        return None, None, []

    fmt = detect_format(content[0])
    statut_detecte = 'valide' if fmt == 'cloture' else 'en_cours'
    reader = csv.reader(content[1:], delimiter=';')

    lignes = []
    annee = None

    for row in reader:
        if not row or not row[0].strip() or row[0].strip().upper().startswith('TOTAUX'):
            continue

        date_str = row[0].strip()
        cle_code, cle_lib = split_code_libelle(row[1])
        type_code, type_lib = split_code_libelle(row[2])
        libelle = row[3].strip()

        try:
            d = datetime.strptime(date_str, '%d/%m/%Y')
        except ValueError:
            continue

        if annee is None:
            annee = d.year
        date_iso = d.strftime('%Y-%m-%d')

        try:
            if fmt == 'cloture':
                montant = parse_montant(row[4].strip().strip('"'))
                tva = parse_montant(row[5].strip().strip('"'))
                recuperable = parse_montant(row[6].strip().strip('"'))
            else:  # en_cours : pas de TVA/Récupérable détaillés
                montant = parse_montant(row[4].strip().strip('"'))
                tva = 0.0
                recuperable = 0.0
        except (ValueError, IndexError):
            continue

        lignes.append((
            date_iso, cle_code, cle_lib, type_code, type_lib, libelle, montant, tva, recuperable
        ))

    return annee, statut_detecte, lignes


def parse_csv_budget(content_bytes):
    """
    Parse un export Myfoncia "comparatif budget/réalisé" (exercice en cours uniquement).
    On extrait uniquement la colonne BUDGET EN COURS, par clé+type de charge.
    Retourne une liste de tuples prêts pour insert_budget_bulk :
    (cle_code, cle_libelle, type_code, type_libelle, budget)
    Exclut la ligne TOTAUX.
    """
    content = content_bytes.decode('utf-8-sig').splitlines()
    if not content:
        return []

    reader = csv.reader(content[1:], delimiter=';')
    lignes = []

    for row in reader:
        if not row or not row[0].strip() or row[0].strip().upper().startswith('TOTAUX'):
            continue
        if len(row) < 4:
            continue

        cle_code, cle_lib = split_code_libelle(row[0])
        type_code, type_lib = split_code_libelle(row[1])

        try:
            budget = parse_montant(row[3].strip().strip('"'))
        except (ValueError, IndexError):
            continue

        lignes.append((cle_code, cle_lib, type_code, type_lib, budget))

    return lignes


# ─── Dashboard (fusion : vue d'ensemble + regroupements analytiques) ──────────

@app.route('/')
def dashboard():
    exercices = db.get_all_exercices()
    annees = [e['annee'] for e in exercices]  # déjà triées DESC par get_all_exercices
    annees_asc = sorted(annees)  # pour l'affichage chronologique gauche -> droite

    annee_sel = request.args.get('annee', type=int)
    annee_comp = request.args.get('compare', type=int)
    if not annee_sel and exercices:
        annee_sel = exercices[0]['annee']

    # Totaux réels par année (pour le graphique d'évolution globale)
    totaux_par_annee = {a: db.get_total_by_annee(a) for a in annees}

    groupes_collectifs = []
    groupes_individuels = []
    groupes_comp = {}
    total_collectif = 0
    total_individuel = 0
    budget_total = None
    budget_par_groupe = {}
    depenses_brutes = []

    if annee_sel:
        depenses_brutes = db.get_all_depenses_raw(annee_sel)
        groupes = regr.regrouper_depenses(depenses_brutes)
        groupes_collectifs = [g for g in groupes if not g['is_individuel']]
        groupes_individuels = [g for g in groupes if g['is_individuel']]
        total_collectif = sum(g['total'] for g in groupes_collectifs)
        total_individuel = sum(g['total'] for g in groupes_individuels)

        # Budget détaillé (s'il existe pour cet exercice)
        if db.has_budget_detail(annee_sel):
            budget_total = db.get_budget_total(annee_sel)
            budget_brut = db.get_all_budget_raw(annee_sel)
            groupes_budget = regr.regrouper_depenses(budget_brut, champ_montant='budget')
            budget_par_groupe = {g['groupe_label']: g['total'] for g in groupes_budget}

    if annee_comp:
        depenses_comp = db.get_all_depenses_raw(annee_comp)
        groupes_comp_raw = regr.regrouper_depenses(depenses_comp)
        groupes_comp = {g['groupe_label']: g['total'] for g in groupes_comp_raw}

    # Courbes mensualisées (réel vs prévisionnel/12) pour les 3 postes réguliers
    courbes_mensuelles = []
    if annee_sel and budget_par_groupe:
        for nom_groupe in regr.GROUPES_MENSUALISABLES:
            budget_groupe = budget_par_groupe.get(nom_groupe)
            if not budget_groupe:
                continue
            evolution = regr.evolution_mensuelle_groupe(depenses_brutes, nom_groupe)
            courbes_mensuelles.append({
                'nom': nom_groupe,
                'budget_annuel': budget_groupe,
                'budget_mensuel': budget_groupe / 12,
                'evolution': [{'mois': m, 'total': t} for m, t in evolution],
            })

    return render_template('modules/depenses/dashboard.html',
                           exercices=exercices,
                           annees=annees,
                           annees_asc=annees_asc,
                           annee_sel=annee_sel,
                           annee_comp=annee_comp,
                           totaux_par_annee=totaux_par_annee,
                           groupes_collectifs=groupes_collectifs,
                           groupes_individuels=groupes_individuels,
                           groupes_comp=groupes_comp,
                           total_collectif=total_collectif,
                           total_individuel=total_individuel,
                           budget_total=budget_total,
                           budget_par_groupe=budget_par_groupe,
                           courbes_mensuelles=courbes_mensuelles)


# ─── Vue Foncia (hiérarchie officielle) ───────────────────────────────────────

@app.route('/foncia')
def foncia():
    exercices = db.get_all_exercices()
    annee_sel = request.args.get('annee', type=int)
    if not annee_sel and exercices:
        annee_sel = exercices[0]['annee']

    cles = []
    if annee_sel:
        totaux_cles = db.get_totaux_par_cle(annee_sel)
        for cle in totaux_cles:
            types = db.get_totaux_par_type(annee_sel, cle['cle_code'])
            cles.append({
                'code': cle['cle_code'],
                'libelle': cle['cle_libelle'],
                'total': cle['total'],
                'types': [dict(t) for t in types]
            })

    evolution = db.get_evolution_mensuelle(annee_sel) if annee_sel else []
    evolution = [dict(e) for e in evolution]

    return render_template('modules/depenses/foncia.html',
                           exercices=exercices,
                           annee_sel=annee_sel,
                           cles=cles,
                           evolution=evolution)


# ─── Vue Fournisseurs ─────────────────────────────────────────────────────────

@app.route('/fournisseurs')
def fournisseurs():
    exercices = db.get_all_exercices()
    annees = [e['annee'] for e in exercices]

    toutes_lignes = db.get_totaux_par_fournisseur()

    pivot = {}  # fournisseur -> {annee_str: total}
    for row in toutes_lignes:
        f = row['fournisseur']
        if f not in pivot:
            pivot[f] = {}
        pivot[f][str(row['annee'])] = row['total']

    fournisseurs_list = [
        {'fournisseur': nom, 'montants': montants, 'total': sum(montants.values())}
        for nom, montants in pivot.items()
    ]
    fournisseurs_list.sort(key=lambda x: x['total'], reverse=True)

    return render_template('modules/depenses/fournisseurs.html',
                           exercices=exercices,
                           annees=annees,
                           fournisseurs_list=fournisseurs_list)


# ─── Import CSV ───────────────────────────────────────────────────────────────

@app.route('/import', methods=['GET', 'POST'])
def import_csv():
    exercices = db.get_all_exercices()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'preview':
            f = request.files.get('fichier')
            if not f or not f.filename.endswith('.csv'):
                flash('Veuillez sélectionner un fichier CSV.', 'error')
                return redirect(url_for('import_csv'))

            content = f.read()
            premiere_ligne = content.decode('utf-8-sig').splitlines()[0] if content else ''
            type_fichier = detect_type_fichier(premiere_ligne)

            if type_fichier is None:
                flash("Format de fichier non reconnu. Vérifiez qu'il s'agit bien d'un export Myfoncia.", 'error')
                return redirect(url_for('import_csv'))

            if type_fichier == 'depenses':
                annee, statut_detecte, lignes = parse_csv_foncia(content)
                if not annee or not lignes:
                    flash('Impossible de lire le fichier CSV. Vérifiez le format.', 'error')
                    return redirect(url_for('import_csv'))

                existing = db.get_exercice_by_annee(annee)
                existing_count = len(db.get_all_depenses_raw(annee)) if existing else 0

                tmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', dir='/tmp', encoding='utf-8')
                json.dump({'type': 'depenses', 'annee': annee, 'statut': statut_detecte, 'lignes': lignes}, tmp, ensure_ascii=False)
                tmp.close()

                return render_template('modules/depenses/import.html',
                                       exercices=exercices,
                                       preview=True,
                                       type_fichier='depenses',
                                       annee=annee,
                                       statut_detecte=statut_detecte,
                                       nb_lignes=len(lignes),
                                       existing_count=existing_count,
                                       tmp_path=tmp.name)

            else:  # type_fichier == 'budget'
                lignes = parse_csv_budget(content)
                if not lignes:
                    flash('Impossible de lire le fichier de budget. Vérifiez le format.', 'error')
                    return redirect(url_for('import_csv'))

                # Le fichier budget ne contient pas l'année explicitement : on l'associe
                # à l'exercice "en cours" actuel (c'est le seul exercice qui a un budget chez Foncia)
                exercice_en_cours = next((e for e in exercices if e['statut'] == 'en_cours'), None)
                if not exercice_en_cours:
                    flash("Aucun exercice 'en cours' trouvé. Importez d'abord le fichier de dépenses de l'exercice en cours avant le budget.", 'error')
                    return redirect(url_for('import_csv'))

                annee = exercice_en_cours['annee']
                existing_count = len(db.get_all_budget_raw(annee))

                tmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', dir='/tmp', encoding='utf-8')
                json.dump({'type': 'budget', 'annee': annee, 'lignes': lignes}, tmp, ensure_ascii=False)
                tmp.close()

                return render_template('modules/depenses/import.html',
                                       exercices=exercices,
                                       preview=True,
                                       type_fichier='budget',
                                       annee=annee,
                                       nb_lignes=len(lignes),
                                       existing_count=existing_count,
                                       tmp_path=tmp.name)

        elif action == 'confirmer':
            tmp_path = request.form.get('tmp_path')
            try:
                with open(tmp_path, 'r') as f:
                    data = json.load(f)
            except Exception:
                flash('Erreur lors de la lecture des données temporaires.', 'error')
                return redirect(url_for('import_csv'))

            if data['type'] == 'depenses':
                annee = data['annee']
                statut = data['statut']
                lignes = [tuple(l) for l in data['lignes']]

                exercice_id = db.upsert_exercice(annee, statut)
                db.delete_depenses_by_exercice(exercice_id)
                db.insert_depenses_bulk(exercice_id, lignes)

                flash(f"Import réussi : {len(lignes)} écritures pour l'exercice {annee} ({'validé' if statut == 'valide' else 'en cours'}).", 'success')

            else:  # budget
                annee = data['annee']
                lignes = [tuple(l) for l in data['lignes']]

                exercice = db.get_exercice_by_annee(annee)
                if not exercice:
                    flash(f"Exercice {annee} introuvable.", 'error')
                    return redirect(url_for('import_csv'))

                db.delete_budget_by_exercice(exercice['id'])
                db.insert_budget_bulk(exercice['id'], lignes)

                flash(f"Import réussi : budget détaillé importé pour l'exercice {annee} ({len(lignes)} postes).", 'success')

            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

            return redirect(url_for('dashboard'))

        elif action == 'annuler':
            tmp_path = request.form.get('tmp_path')
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return redirect(url_for('import_csv'))

        elif action == 'supprimer_exercice':
            annee = request.form.get('annee', type=int)
            if annee:
                db.delete_exercice_complet(annee)
                flash(f"Exercice {annee} supprimé (dépenses et budget effacés).", 'success')
            return redirect(url_for('import_csv'))

    return render_template('modules/depenses/import.html', exercices=exercices, preview=False)


# ─── Module Logements / Habitants ──────────────────────────────────────────────

CATEGORIES_HISTORIQUE = {
    'proprietaire': 'Propriétaire',
    'habitant': 'Habitant',
    'prix_vente': 'Prix de vente',
}


@app.route('/logements', methods=['GET', 'POST'])
def logements():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'ajouter_info':
            logement_id = request.form.get('logement_id', type=int)
            date = request.form.get('date', '').strip()
            categorie = request.form.get('categorie', '').strip()
            valeur = request.form.get('valeur', '').strip()

            if not date or not categorie or not valeur:
                flash('Date, catégorie et valeur sont obligatoires.', 'error')
            elif categorie not in CATEGORIES_HISTORIQUE:
                flash('Catégorie invalide.', 'error')
            else:
                db.add_historique_entry(logement_id, date, categorie, valeur)
                flash('Information ajoutée.', 'success')

            return redirect(url_for('logements'))

        elif action == 'supprimer_info':
            entry_id = request.form.get('entry_id', type=int)
            if entry_id:
                db.delete_historique_entry(entry_id)
                flash('Information supprimée.', 'success')
            return redirect(url_for('logements'))

    recherche = request.args.get('q', '').strip() or None
    surface_min = request.args.get('surface_min', type=float)
    surface_max = request.args.get('surface_max', type=float)

    liste = db.rechercher_logements(recherche_nom=recherche, surface_min=surface_min, surface_max=surface_max)

    # Historique complet pour chaque logement affiché (pour l'accordéon, évite un aller-retour JS)
    historiques = {l['id']: db.get_historique_logement(l['id']) for l in liste}

    return render_template('modules/logements/liste.html',
                           logements=liste,
                           historiques=historiques,
                           categories=CATEGORIES_HISTORIQUE,
                           recherche=recherche or '',
                           surface_min=surface_min,
                           surface_max=surface_max)


@app.route('/logements/seed-initial')
def seed_initial():
    """
    Route exceptionnelle, à visiter UNE SEULE FOIS pour peupler les 59 logements
    de démarrage. Protégée contre la double exécution : si des logements existent
    déjà, elle ne fait rien. Pas besoin de terminal/shell pour la déclencher,
    juste ouvrir cette URL dans le navigateur.
    """
    import seed_logements
    if db.count_logements() > 0:
        return f"⚠️ {db.count_logements()} logements existent déjà en base. Rien à faire. <a href='{url_for('logements')}'>Retour à la liste</a>"

    seed_logements.run()
    return f"✅ Seed terminé avec succès, {db.count_logements()} logements créés. <a href='{url_for('logements')}'>Voir la liste des logements</a>"


# ─── Module Sujets AG ───────────────────────────────────────────────────────────

@app.route('/sujets-ag', methods=['GET', 'POST'])
def sujets_ag():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'ajouter_idee':
            titre = request.form.get('titre', '').strip()
            if titre:
                db.add_idee_ag(titre)
                flash('Idée ajoutée.', 'success')

        elif action == 'modifier_titre':
            idee_id = request.form.get('idee_id', type=int)
            titre = request.form.get('titre', '').strip()
            if idee_id and titre:
                db.update_idee_ag_titre(idee_id, titre)

        elif action == 'modifier_description':
            idee_id = request.form.get('idee_id', type=int)
            description = request.form.get('description', '').strip()
            if idee_id:
                db.update_idee_ag_description(idee_id, description)

        elif action == 'modifier_statut':
            idee_id = request.form.get('idee_id', type=int)
            statut_id = request.form.get('statut_id', type=int)
            if idee_id:
                db.update_idee_ag_statut(idee_id, statut_id)

        elif action == 'supprimer_idee':
            idee_id = request.form.get('idee_id', type=int)
            if idee_id:
                db.delete_idee_ag(idee_id)
                flash('Idée supprimée.', 'success')

        elif action == 'deplacer_idee':
            idee_id = request.form.get('idee_id', type=int)
            direction = request.form.get('direction')
            if idee_id and direction in ('haut', 'bas'):
                db.deplacer_idee_ag(idee_id, direction)

        elif action == 'ajouter_tache':
            idee_id = request.form.get('idee_id', type=int)
            texte = request.form.get('texte', '').strip()
            if idee_id and texte:
                db.add_tache_ag(idee_id, texte)

        elif action == 'modifier_tache':
            tache_id = request.form.get('tache_id', type=int)
            texte = request.form.get('texte', '').strip()
            if tache_id and texte:
                db.update_tache_ag_texte(tache_id, texte)

        elif action == 'toggle_tache':
            tache_id = request.form.get('tache_id', type=int)
            if tache_id:
                db.toggle_tache_ag_fait(tache_id)

        elif action == 'supprimer_tache':
            tache_id = request.form.get('tache_id', type=int)
            if tache_id:
                db.delete_tache_ag(tache_id)

        elif action == 'ajouter_statut':
            nom = request.form.get('nom', '').strip()
            couleur = request.form.get('couleur', '#2d7dd2').strip()
            if nom:
                try:
                    db.add_statut_ag(nom, couleur)
                except Exception:
                    flash(f"Le statut « {nom} » existe déjà.", 'error')

        elif action == 'modifier_statut_ag':
            statut_id = request.form.get('statut_id', type=int)
            nom = request.form.get('nom', '').strip()
            couleur = request.form.get('couleur', '#2d7dd2').strip()
            if statut_id and nom:
                db.update_statut_ag(statut_id, nom, couleur)

        elif action == 'supprimer_statut':
            statut_id = request.form.get('statut_id', type=int)
            if statut_id:
                db.delete_statut_ag(statut_id)

        return redirect(url_for('sujets_ag'))

    idees = db.get_all_idees_ag()
    statuts = db.get_all_statuts_ag()
    return render_template('modules/sujets_ag/liste.html', idees=idees, statuts=statuts)


# ─── Module Relevés Océa ────────────────────────────────────────────────────────

# Numéro d'appartement de Marc-Antoine, valeur par défaut du sélecteur de logement
# sur la page "Mon logement" (mémorisée en session si l'utilisateur en choisit un autre).
MON_NUMERO_APPARTEMENT = '241'

# INDEX 4 contient parfois des lettres (ex: "Lr 6A19") -> champ texte libre, pas de unité fixe affichée.
# Les autres index ont toujours la même unité, fixée en dur (cf. db.UNITES_INDEX_THERMIQUE).
INDEX_4_EST_TEXTE_LIBRE = True


def get_mon_logement_id():
    return db.get_logement_id_by_numero(MON_NUMERO_APPARTEMENT)


@app.route('/ocea')
def ocea_dashboard():
    logements = db.get_all_logements_avec_etat_actuel()
    derniers_eau_froide = db.get_dernier_releve_eau_froide_tous_logements()
    derniers_thermique = db.get_dernier_releve_thermique_index5_tous_logements()

    data = []
    for l in logements:
        eau = derniers_eau_froide.get(l['id'])
        thermique = derniers_thermique.get(l['id'])
        data.append({
            'id': l['id'],
            'numero_appartement': l['numero_appartement'],
            'surface_m2': l['surface_m2'],
            'nb_pieces': l['nb_pieces'],
            'eau_froide_index': eau['index_m3'] if eau else None,
            'thermique_index5': thermique['valeur'] if thermique else None,
        })

    return render_template('modules/ocea/dashboard.html', data=data)


@app.route('/ocea/mon-logement', methods=['GET', 'POST'])
def ocea_mon_logement():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'changer_logement':
            numero = request.form.get('numero_appartement', '').strip()
            if numero:
                session['ocea_logement_consulte'] = numero
            return redirect(url_for('ocea_mon_logement'))

        # Pour toutes les actions de saisie, le logement concerné est celui actuellement
        # affiché (peut être différent de MON_NUMERO_APPARTEMENT si on consulte un autre logement).
        numero_actuel = session.get('ocea_logement_consulte', MON_NUMERO_APPARTEMENT)
        logement_id = db.get_logement_id_by_numero(numero_actuel)

        if action == 'ajouter_eau_froide':
            date = request.form.get('date', '').strip()
            index_m3 = request.form.get('index_m3', type=float)
            if date and index_m3 is not None:
                db.add_releve_eau_froide(logement_id, date, index_m3)
                flash('Relevé eau froide enregistré.', 'success')

        elif action == 'supprimer_eau_froide':
            releve_id = request.form.get('releve_id', type=int)
            if releve_id:
                db.delete_releve_eau_froide(releve_id)

        elif action == 'ajouter_eau_chaude':
            mois = request.form.get('mois', '').strip()
            conso = request.form.get('conso_m3', type=float)
            if mois and conso is not None:
                db.upsert_releve_eau_chaude(logement_id, mois, conso)
                flash('Relevé eau chaude enregistré.', 'success')

        elif action == 'supprimer_eau_chaude':
            releve_id = request.form.get('releve_id', type=int)
            if releve_id:
                db.delete_releve_eau_chaude(releve_id)

        elif action == 'ajouter_thermique':
            date = request.form.get('date', '').strip()
            if date:
                valeurs = {}
                for num in range(1, 17):
                    val = request.form.get(f'index_{num}_valeur', '').strip()
                    if val:
                        valeurs[num] = val
                if valeurs:
                    db.add_releve_thermique_bulk(logement_id, date, valeurs)
                    flash(f'Relevé thermique enregistré ({len(valeurs)} index renseignés).', 'success')
                else:
                    flash('Aucun index renseigné, rien à enregistrer.', 'error')

        elif action == 'supprimer_thermique':
            date = request.form.get('date', '').strip()
            if date:
                db.delete_releve_thermique_date(logement_id, date)

        return redirect(url_for('ocea_mon_logement'))

    numero_actuel = session.get('ocea_logement_consulte', MON_NUMERO_APPARTEMENT)
    logement_id = db.get_logement_id_by_numero(numero_actuel)
    if not logement_id:
        # Le logement mémorisé n'existe plus (changement de numérotation) -> retombe sur le défaut
        numero_actuel = MON_NUMERO_APPARTEMENT
        logement_id = db.get_logement_id_by_numero(numero_actuel)

    eau_froide = db.get_releves_eau_froide_logement(logement_id)
    eau_chaude = db.get_releves_eau_chaude(logement_id)
    thermique = db.get_releves_thermique(logement_id)
    logement = db.get_logement_by_id(logement_id)
    tous_logements = db.get_all_logements_avec_etat_actuel()

    from datetime import date as date_today
    return render_template('modules/ocea/mon_logement.html',
                           logement=logement,
                           numero_actuel=numero_actuel,
                           tous_logements=tous_logements,
                           eau_froide=list(reversed(eau_froide)),
                           eau_chaude=list(reversed(eau_chaude)),
                           thermique=thermique,
                           unites_index=db.UNITES_INDEX_THERMIQUE,
                           numeros_index=range(1, 17),
                           aujourd_hui=date_today.today().isoformat())


@app.route('/ocea/suivi')
def ocea_suivi():
    logements = db.get_all_logements_avec_etat_actuel()
    releves = db.get_all_releves_eau_froide()

    # Construire la liste des dates distinctes (colonnes du tableau croisé)
    dates = sorted({r['date'] for r in releves})

    # Pivot : logement_id -> {date: index_m3}
    pivot = {}
    for r in releves:
        pivot.setdefault(r['logement_id'], {})[r['date']] = r['index_m3']

    lignes = []
    for l in logements:
        lignes.append({
            'numero_appartement': l['numero_appartement'],
            'surface_m2': l['surface_m2'],
            'valeurs': pivot.get(l['id'], {}),
        })

    return render_template('modules/ocea/suivi.html', lignes=lignes, dates=dates)


@app.route('/ocea/saisie', methods=['GET', 'POST'])
def ocea_saisie():
    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        valeurs = {}
        for key, val in request.form.items():
            if key.startswith('logement_') and val.strip():
                logement_id = int(key.replace('logement_', ''))
                try:
                    valeurs[logement_id] = float(val.strip())
                except ValueError:
                    pass
        if date and valeurs:
            db.add_releves_eau_froide_bulk(date, valeurs)
            flash(f'{len(valeurs)} relevé(s) enregistré(s) pour le {date}.', 'success')
        else:
            flash('Aucune valeur saisie.', 'error')
        return redirect(url_for('ocea_saisie'))

    logements = db.get_all_logements_avec_etat_actuel()
    derniers_releves = db.get_dernier_releve_eau_froide_tous_logements()

    from datetime import date as date_today
    return render_template('modules/ocea/saisie.html',
                           logements=logements,
                           derniers_releves=derniers_releves,
                           aujourd_hui=date_today.today().isoformat())


@app.route('/ocea/saisie-thermique', methods=['GET', 'POST'])
def ocea_saisie_thermique():
    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        valeurs = {}
        for key, val in request.form.items():
            if key.startswith('logement_') and val.strip():
                logement_id = int(key.replace('logement_', ''))
                try:
                    valeurs[logement_id] = float(val.strip())
                except ValueError:
                    pass
        if date and valeurs:
            db.add_releves_thermique_index5_bulk(date, valeurs)
            flash(f'{len(valeurs)} relevé(s) thermique(s) enregistré(s) pour le {date}.', 'success')
        else:
            flash('Aucune valeur saisie.', 'error')
        return redirect(url_for('ocea_saisie_thermique'))

    logements = db.get_all_logements_avec_etat_actuel()
    derniers_releves = db.get_dernier_releve_thermique_index5_tous_logements()

    from datetime import date as date_today
    return render_template('modules/ocea/saisie_thermique.html',
                           logements=logements,
                           derniers_releves=derniers_releves,
                           aujourd_hui=date_today.today().isoformat())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=2000, debug=False, threaded=True)
