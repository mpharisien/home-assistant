import os
import io
import csv
import json
import tempfile
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=2000, debug=False, threaded=True)
