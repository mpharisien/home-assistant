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
    'analytique': 'depenses',
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


def detect_format(header_line):
    """
    Détecte le format du CSV Foncia exporté.
    Format A (exercice clôturé)  : DATE;CLE DE REPARTITION;TYPE DE CHARGE;LIBELLE;A REPARTIR;TVA;RECUPERABLE
    Format B (exercice en cours) : DATE;CLE DE REPARTITION;TYPE DE CHARGE;LIBELLE;MONTANT
    """
    cols = [c.strip().upper() for c in header_line.split(';')]
    if 'TVA' in cols and 'RECUPERABLE' in cols:
        return 'cloture'
    return 'en_cours'


def parse_csv_foncia(content_bytes):
    """
    Parse un export Myfoncia (détail des écritures), quel que soit son format.
    Retourne (annee, lignes) où lignes = liste de tuples prêts pour insert_depenses_bulk :
    (date_iso, cle_code, cle_libelle, type_code, type_libelle, libelle, montant, tva, recuperable)
    Exclut la ligne TOTAUX.
    """
    content = content_bytes.decode('utf-8-sig').splitlines()
    if not content:
        return None, []

    fmt = detect_format(content[0])
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

    return annee, lignes


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    exercices = db.get_all_exercices()
    annees = [e['annee'] for e in exercices]

    data_annees = []
    for e in exercices:
        total = db.get_total_by_annee(e['annee'])
        data_annees.append({
            'annee': e['annee'],
            'statut': e['statut'],
            'total': total,
            'budget': e['budget_previsionnel'],
            'date_import': e['date_import'],
        })

    en_cours = next((d for d in data_annees if d['statut'] == 'en_cours'), None)
    evolution_en_cours = []
    evolution_precedente = []
    if en_cours:
        evolution_en_cours = db.get_evolution_mensuelle(en_cours['annee'])
        annee_precedente = en_cours['annee'] - 1
        if annee_precedente in annees:
            evolution_precedente = db.get_evolution_mensuelle(annee_precedente)

    return render_template('modules/depenses/dashboard.html',
                           data_annees=data_annees,
                           en_cours=en_cours,
                           evolution_en_cours=evolution_en_cours,
                           evolution_precedente=evolution_precedente,
                           annees=annees)


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


# ─── Vue Analytique (regroupements personnalisés) ─────────────────────────────

@app.route('/analytique')
def analytique():
    exercices = db.get_all_exercices()
    annee_sel = request.args.get('annee', type=int)
    annee_comp = request.args.get('compare', type=int)

    if not annee_sel and exercices:
        annee_sel = exercices[0]['annee']

    groupes_collectifs = []
    groupes_individuels = []
    groupes_comp = {}
    total_collectif = 0
    total_individuel = 0

    if annee_sel:
        depenses_brutes = db.get_all_depenses_raw(annee_sel)
        groupes = regr.regrouper_depenses(depenses_brutes)
        groupes_collectifs = [g for g in groupes if not g['is_individuel']]
        groupes_individuels = [g for g in groupes if g['is_individuel']]
        total_collectif = sum(g['total'] for g in groupes_collectifs)
        total_individuel = sum(g['total'] for g in groupes_individuels)

    if annee_comp:
        depenses_comp = db.get_all_depenses_raw(annee_comp)
        groupes_comp_raw = regr.regrouper_depenses(depenses_comp)
        groupes_comp = {g['groupe_label']: g['total'] for g in groupes_comp_raw}

    return render_template('modules/depenses/analytique.html',
                           exercices=exercices,
                           annee_sel=annee_sel,
                           annee_comp=annee_comp,
                           groupes_collectifs=groupes_collectifs,
                           groupes_individuels=groupes_individuels,
                           groupes_comp=groupes_comp,
                           total_collectif=total_collectif,
                           total_individuel=total_individuel)


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
            annee, lignes = parse_csv_foncia(content)

            if not annee or not lignes:
                flash('Impossible de lire le fichier CSV. Vérifiez le format.', 'error')
                return redirect(url_for('import_csv'))

            existing = db.get_exercice_by_annee(annee)
            existing_count = 0
            if existing:
                existing_count = len(db.get_all_depenses_raw(annee))

            tmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', dir='/tmp', encoding='utf-8')
            json.dump({'annee': annee, 'lignes': lignes}, tmp, ensure_ascii=False)
            tmp.close()

            return render_template('modules/depenses/import.html',
                                   exercices=exercices,
                                   preview=True,
                                   annee=annee,
                                   nb_lignes=len(lignes),
                                   existing_count=existing_count,
                                   tmp_path=tmp.name)

        elif action == 'confirmer':
            tmp_path = request.form.get('tmp_path')
            budget_str = request.form.get('budget_previsionnel', '').strip()
            statut = request.form.get('statut', 'valide')

            try:
                with open(tmp_path, 'r') as f:
                    data = json.load(f)
                annee = data['annee']
                lignes = [tuple(l) for l in data['lignes']]
            except Exception:
                flash('Erreur lors de la lecture des données temporaires.', 'error')
                return redirect(url_for('import_csv'))

            budget = None
            if budget_str:
                try:
                    budget = parse_montant(budget_str)
                except ValueError:
                    flash('Format du budget invalide.', 'error')
                    return redirect(url_for('import_csv'))

            exercice_id = db.upsert_exercice(annee, statut, budget)
            db.delete_depenses_by_exercice(exercice_id)
            db.insert_depenses_bulk(exercice_id, lignes)

            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

            flash(f"Import réussi : {len(lignes)} écritures pour l'exercice {annee}.", 'success')
            return redirect(url_for('dashboard'))

        elif action == 'annuler':
            tmp_path = request.form.get('tmp_path')
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return redirect(url_for('import_csv'))

    return render_template('modules/depenses/import.html', exercices=exercices, preview=False)


@app.route('/budget/<int:annee>', methods=['POST'])
def update_budget(annee):
    budget_str = request.form.get('budget', '').strip()
    try:
        budget = parse_montant(budget_str)
        db.update_budget(annee, budget)
        flash(f'Budget {annee} mis à jour.', 'success')
    except ValueError:
        flash('Format invalide.', 'error')
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=2000, debug=False, threaded=True)
