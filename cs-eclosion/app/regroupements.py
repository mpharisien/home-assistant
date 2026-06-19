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


def assigner_groupe(depense):
    """Retourne (nom_groupe, ordre, is_individuel) pour une écriture donnée."""
    for nom, ordre, is_individuel, condition in REGLES:
        if condition(depense):
            return nom, ordre, is_individuel
    return RESTE_GROUPE


def regrouper_depenses(depenses):
    """
    Prend une liste de dépenses brutes (dicts) et retourne une liste de groupes
    analytiques agrégés : [{groupe_label, groupe_ordre, is_individuel, total}, ...]
    triée par ordre d'affichage.
    """
    groupes = {}  # nom_groupe -> {ordre, is_individuel, total}

    for d in depenses:
        nom, ordre, is_individuel = assigner_groupe(d)
        if nom not in groupes:
            groupes[nom] = {'groupe_label': nom, 'groupe_ordre': ordre, 'is_individuel': is_individuel, 'total': 0.0}
        groupes[nom]['total'] += d['montant']

    return sorted(groupes.values(), key=lambda g: g['groupe_ordre'])


def get_liste_regles():
    """Retourne la liste des règles sous forme lisible, pour affichage (ex: page d'aide/admin future)."""
    return [{'groupe': nom, 'ordre': ordre, 'individuel': individuel} for nom, ordre, individuel, _ in REGLES]
