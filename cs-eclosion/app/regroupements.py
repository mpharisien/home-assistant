"""
Règles de regroupement analytique pour le module "Analyse des dépenses".

Principe : les données en base (table `depenses`) restent TOUJOURS la copie brute
de ce que Foncia fournit. Ce fichier définit uniquement la façon dont on les
RELIT et REGROUPE à l'affichage, pour la vue analytique.

Pour changer un regroupement (ex: isoler un nouveau poste), il suffit de modifier
les règles ci-dessous. Les années précédentes seront automatiquement recalculées,
puisqu'aucune donnée n'est jamais transformée en base.

Chaque règle est évaluée DANS L'ORDRE. La première règle qui correspond à une
écriture l'assigne à son groupe. Si aucune règle ne correspond, l'écriture tombe
dans le groupe "Charges générales (reste)" par défaut (cf. RESTE_GROUPE).
"""

# Chaque règle : (nom_groupe, ordre_affichage, is_individuel, condition_fn)
# condition_fn reçoit une ligne de dépense (dict) et retourne True/False

REGLES = [
    (
        "Ménage",
        1,
        False,
        lambda d: d['type_code'] in ('120', '170'),
    ),
    (
        "Espaces verts",
        2,
        False,
        lambda d: d['type_code'] == '110',
    ),
    (
        "Assurance",
        3,
        False,
        lambda d: d['type_code'] == '195' and d['cle_code'] == '001',
    ),
    (
        "Ascenseurs",
        4,
        False,
        lambda d: d['type_code'] in ('136', '137'),
    ),
    (
        "Honoraires syndic",
        5,
        False,
        lambda d: d['type_code'] in ('700', '701') and d['cle_code'] == '001',
    ),
    (
        "Électricité",
        6,
        False,
        lambda d: d['type_code'] == '302' and d['cle_code'] != '700',
    ),
    (
        "Chaufferie (gaz, entretien, réparations)",
        7,
        False,
        lambda d: d['cle_code'] == '700',
    ),
    (
        "Eau froide individuelle",
        8,
        True,
        lambda d: d['cle_code'] == '816',
    ),
    (
        "Eau chaude individuelle",
        9,
        True,
        lambda d: d['cle_code'] == '836',
    ),
    (
        "Répartiteurs chauffage individuel",
        10,
        True,
        lambda d: d['cle_code'] in ('737', '738'),
    ),
    (
        "Parking / Circulations",
        11,
        False,
        lambda d: d['cle_code'] == '047',
    ),
    (
        "Escaliers",
        12,
        False,
        lambda d: d['cle_code'] in ('300', '301'),
    ),
    (
        "Logements (charges communes)",
        13,
        False,
        lambda d: d['cle_code'] == '039',
    ),
]

# Groupe par défaut pour tout ce qui ne correspond à aucune règle ci-dessus
# (en pratique : le reste de la clé 001 - Charges générales)
RESTE_GROUPE = ("Charges générales (reste)", 99, False)


# Groupes pour lesquels une courbe "prévisionnel mensualisé" (budget annuel / 12) a du sens,
# car ces dépenses arrivent par écritures régulières tout au long de l'année (constaté sur 2025).
# Pour les autres groupes, les écritures sont trop ponctuelles/irrégulières pour que ça soit pertinent.
GROUPES_MENSUALISABLES = ["Ménage", "Chaufferie (gaz, entretien, réparations)", "Électricité"]


def assigner_groupe(depense):
    """Retourne (nom_groupe, ordre, is_individuel) pour une écriture donnée."""
    for nom, ordre, is_individuel, condition in REGLES:
        if condition(depense):
            return nom, ordre, is_individuel
    return RESTE_GROUPE


def regrouper_depenses(depenses, champ_montant='montant'):
    """
    Prend une liste de lignes (dépenses ou budget, dicts) et retourne une liste de groupes
    analytiques agrégés : [{groupe_label, groupe_ordre, is_individuel, total}, ...]
    triée par ordre d'affichage.

    champ_montant : nom de la clé contenant le montant à sommer ('montant' pour les dépenses,
    'budget' pour les lignes de budget détaillé).
    """
    groupes = {}  # nom_groupe -> {ordre, is_individuel, total}

    for d in depenses:
        nom, ordre, is_individuel = assigner_groupe(d)
        if nom not in groupes:
            groupes[nom] = {'groupe_label': nom, 'groupe_ordre': ordre, 'is_individuel': is_individuel, 'total': 0.0}
        groupes[nom]['total'] += d[champ_montant]

    return sorted(groupes.values(), key=lambda g: g['groupe_ordre'])


def get_liste_regles():
    """Retourne la liste des règles sous forme lisible, pour affichage (ex: page d'aide/admin future)."""
    return [{'groupe': nom, 'ordre': ordre, 'individuel': individuel} for nom, ordre, individuel, _ in REGLES]


def evolution_mensuelle_groupe(depenses, nom_groupe):
    """
    Calcule le cumul mensuel des dépenses appartenant à un groupe analytique donné.
    Retourne une liste de tuples (mois 'YYYY-MM', total_du_mois) triée par mois.
    """
    par_mois = {}
    for d in depenses:
        nom, _, _ = assigner_groupe(d)
        if nom != nom_groupe:
            continue
        mois = d['date'][:7]  # 'YYYY-MM-DD' -> 'YYYY-MM'
        par_mois[mois] = par_mois.get(mois, 0.0) + d['montant']
    return sorted(par_mois.items())
