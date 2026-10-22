"""
Analyse des relevés Océa (eau froide et thermique) sur une période choisie.

Utilisé par le dashboard Océa pour repérer les compteurs ou relevés suspects.

PRINCIPES (choix validés en octobre 2026, à relire avant toute modification)
------------------------------------------------------------------------------
1. On travaille sur la CONSOMMATION entre deux dates de relevé (index fin - index début),
   et non sur l'index cumulé. L'index cumulé mélange toutes les périodes depuis la pose :
   un logement anormal il y a six mois le resterait pour toujours.

2. La consommation est ramenée en m³ PAR JOUR. Les tournées n'ont pas toutes la même
   durée (ex. 102 jours puis 115 jours) : sans cette division, une période plus longue
   paraîtrait toujours plus "gourmande".

3. Une seule période (début + fin) pour l'eau froide ET le thermique : les deux compteurs
   sont toujours relevés le même jour lors des tournées.

4. Pour comparer des logements de tailles différentes, on divise par le TANTIÈME (la
   surface n'est pas connue pour tous les logements). On calcule ensuite un INDICE :
       indice = (conso par jour / tantième) / médiane de l'immeuble de ce même ratio × 100
   100 = comme un logement médian de même taille ; 250 = 2,5 fois plus.
   On utilise la MÉDIANE et non la moyenne : quelques valeurs aberrantes (justement celles
   qu'on cherche) fausseraient une moyenne, pas une médiane.

5. Seuil « logement vide » (optionnel, en m³/jour) : un logement dont TOUS les compteurs
   connus sont sous le seuil est considéré comme vide et retiré des comparaisons.
   Si UN SEUL compteur est sous le seuil, le logement n'est PAS retiré : c'est justement
   l'anomalie "eau froide sans thermique" (ou l'inverse) qu'on veut détecter
   (compteur bloqué ou mal relevé).

6. Dates "complètes" : certaines tournées ne concernent que quelques logements (ex. les 3
   logements d'un même étage). Une date est dite complète si au moins 60 % des logements
   y ont été relevés. Ce seuil de 60 % sert UNIQUEMENT à choisir des valeurs par défaut
   raisonnables (période affichée par défaut, période précédente) : comparer l'immeuble
   à 3 logements n'aurait pas de sens. 60 % plutôt que 100 % pour tolérer quelques
   logements oubliés ou inaccessibles lors d'une tournée complète.
   L'utilisateur peut toujours choisir lui-même une date partielle : les mêmes règles
   s'appliquent alors, sur les seuls logements relevés (les médianes sont moins fiables,
   c'est un choix assumé).

Ce module ne lit ni n'écrit la base : il reçoit des données et renvoie des résultats.
"""
from datetime import date as _date
from statistics import median

FLUIDES = ('eau_froide', 'thermique')
LIBELLES = {'eau_froide': 'Eau froide', 'thermique': 'Thermique'}

# Part minimale des logements relevés pour qu'une date soit "complète" (voir principe 6).
PART_MINIMALE_DATE_COMPLETE = 0.60

# Seuils de détection, exprimés en indice (100 = médiane de l'immeuble, à taille égale).
# Fixés volontairement larges pour ne signaler que les cas nets ; à ajuster si trop sensibles.
INDICE_TRES_ELEVE = 250       # plus de 2,5 fois la médiane
INDICE_TRES_FAIBLE = 40       # moins de 0,4 fois la médiane
INDICE_ERREUR_CHIFFRE = 800   # plus de 8 fois la médiane : chiffre en trop ou virgule mal placée, probablement
# Un indice multiplié ou divisé par 3 d'une période à l'autre est jugé "brutal". On compare
# des indices (relatifs à l'immeuble) et non des volumes : ainsi, la hausse normale du
# chauffage en hiver touche tout l'immeuble et ne déclenche pas d'alerte.
RATIO_CHANGEMENT_BRUTAL = 3


def _fr(valeur, decimales=1):
    """Nombre à la française (virgule décimale), pour les textes d'explication."""
    return f"{valeur:.{decimales}f}".replace('.', ',')


def _jours_entre(debut, fin):
    return (_date.fromisoformat(fin) - _date.fromisoformat(debut)).days


# ─── Dates de relevé ──────────────────────────────────────────────────────────

def dates_avec_nombre_releves(releves_par_fluide):
    """
    Liste des dates de relevé, de la plus récente à la plus ancienne, avec pour chacune
    le nombre de logements relevés (au moins un des deux compteurs).
    Retour : [{'date': 'AAAA-MM-JJ', 'nb': 59}, ...]
    """
    logements_par_date = {}
    for fluide in FLUIDES:
        for (logement_id, d) in releves_par_fluide[fluide]:
            logements_par_date.setdefault(d, set()).add(logement_id)
    return [{'date': d, 'nb': len(ids)} for d, ids in sorted(logements_par_date.items(), reverse=True)]


def dates_completes(dates, nb_logements):
    """Dates où au moins 60 % des logements ont été relevés (voir principe 6), plus récente en premier."""
    minimum = nb_logements * PART_MINIMALE_DATE_COMPLETE
    return [d['date'] for d in dates if d['nb'] >= minimum]


def periode_par_defaut(dates, nb_logements):
    """
    Période proposée à l'ouverture du dashboard : les deux dernières dates complètes.
    S'il n'y en a pas deux, on se rabat sur les deux dernières dates tout court.
    """
    completes = dates_completes(dates, nb_logements)
    if len(completes) >= 2:
        return completes[1], completes[0]
    toutes = [d['date'] for d in dates]
    return (toutes[1], toutes[0]) if len(toutes) >= 2 else (None, None)


def periode_precedente(dates, nb_logements, debut):
    """
    Période qui précède celle analysée : de la dernière date COMPLÈTE avant le début,
    jusqu'au début. On ignore les dates partielles : comparer un logement à une période
    où seuls 3 logements avaient été relevés n'aurait pas de sens (médiane sur 3 valeurs).
    """
    avant = [d for d in dates_completes(dates, nb_logements) if d < debut]
    return (avant[0], debut) if avant else None


# ─── Calculs sur une période ──────────────────────────────────────────────────

def _calculer_periode(logements, releves_par_fluide, debut, fin, seuil):
    """
    Pour chaque logement : consommation par jour de chaque compteur, statut "vide" et indices.
    seuil : m³/jour, ou None si aucun seuil n'est défini (aucun logement n'est alors ignoré).
    """
    jours = _jours_entre(debut, fin)
    lignes = []
    for l in logements:
        ligne = {
            'id': l['id'],
            'numero_appartement': l['numero_appartement'],
            'tantieme': l.get('tantieme'),
        }
        for fluide in FLUIDES:
            releves = releves_par_fluide[fluide]
            i_debut, i_fin = releves.get((l['id'], debut)), releves.get((l['id'], fin))
            # Pas de relevé à l'une des deux dates : consommation inconnue (None), le compteur
            # est simplement exclu de l'analyse pour ce logement.
            ligne[fluide] = (i_fin - i_debut) / jours if i_debut is not None and i_fin is not None else None

        connues = [ligne[f] for f in FLUIDES if ligne[f] is not None]
        # Vide = tous les compteurs connus sous le seuil (principe 5). Une valeur négative n'est
        # jamais "vide" : c'est un index en baisse, donc une erreur à signaler.
        ligne['vide'] = seuil is not None and bool(connues) and all(0 <= c < seuil for c in connues)
        lignes.append(ligne)

    def _comparable(li, fluide):
        """
        Valeur utilisable pour la médiane et l'indice : logement non vide, avec un tantième,
        consommation connue, et au-dessus du seuil (strictement positive s'il n'y a pas de seuil).
        Un compteur à l'arrêt alors que l'autre tourne est suspect : on ne le laisse pas tirer
        la médiane vers le bas, et il est signalé par la règle 2 ("eau froide sans thermique").
        """
        v = li[fluide]
        return (not li['vide'] and li['tantieme'] and v is not None
                and (v >= seuil if seuil else v > 0))

    medianes = {}         # médiane de (conso par jour / tantième), base de l'indice
    medianes_brutes = {}  # médiane de la conso par jour, pour le graphique en barres "% de la médiane"
    for fluide in FLUIDES:
        valeurs = [li for li in lignes if _comparable(li, fluide)]
        medianes[fluide] = median([li[fluide] / li['tantieme'] for li in valeurs]) if valeurs else None
        medianes_brutes[fluide] = median([li[fluide] for li in valeurs]) if valeurs else None

    for li in lignes:
        for fluide in FLUIDES:
            m = medianes[fluide]
            li[f'indice_{fluide}'] = round(li[fluide] / li['tantieme'] / m * 100) \
                if m and _comparable(li, fluide) else None

    return lignes, medianes, medianes_brutes


# ─── Détection des anomalies ──────────────────────────────────────────────────

def _indices_si_echange(a, b, fluide, releves, debut, fin, mediane):
    """
    Indices qu'auraient les logements a et b si on échangeait leurs index de FIN de période.
    Sert à détecter une confusion entre deux compteurs pendant la tournée.
    """
    jours = _jours_entre(debut, fin)
    a_debut, a_fin = releves.get((a['id'], debut)), releves.get((a['id'], fin))
    b_debut, b_fin = releves.get((b['id'], debut)), releves.get((b['id'], fin))
    if None in (a_debut, a_fin, b_debut, b_fin) or not mediane:
        return None
    conso_a = (b_fin - a_debut) / jours
    conso_b = (a_fin - b_debut) / jours
    return conso_a / a['tantieme'] / mediane * 100, conso_b / b['tantieme'] / mediane * 100


def _detecter_anomalies(lignes, lignes_prec, medianes, releves_par_fluide, debut, fin, seuil):
    anomalies = []
    normal = lambda indice: INDICE_TRES_FAIBLE < indice < INDICE_TRES_ELEVE

    def ajouter(li, gravite, fluide, type_, explication):
        anomalies.append({
            'numero_appartement': li['numero_appartement'],
            'gravite': gravite,  # 1 = à vérifier en priorité (barre rouge), 2 = à surveiller (barre orange)
            'fluide': LIBELLES[fluide],
            'fluide_code': fluide,
            'type': type_,
            'explication': explication,
        })

    for li in lignes:
        # Règle 1 — Index en baisse : physiquement impossible, donc erreur de saisie
        # (ou compteur remplacé). Signalée même pour un logement vide.
        for fluide in FLUIDES:
            if li[fluide] is not None and li[fluide] < 0:
                ajouter(li, 1, fluide, 'Index en baisse',
                        "L'index de fin est plus petit que l'index de début : erreur de saisie ou compteur remplacé ?")

        if li['vide']:
            continue

        # Règle 2 — Un compteur tourne, l'autre non. "Non" = sous le seuil s'il est défini,
        # sinon exactement zéro. Probablement un compteur bloqué ou mal relevé.
        ef, th = li['eau_froide'], li['thermique']
        if ef is not None and th is not None and ef >= 0 and th >= 0:
            arrete = (lambda v: v < seuil) if seuil is not None else (lambda v: v == 0)
            if arrete(th) and not arrete(ef):
                ajouter(li, 1, 'thermique', 'Eau froide sans thermique',
                        f"{_fr(ef, 3)} m³/jour d'eau froide mais quasiment pas de thermique ({_fr(th, 3)} m³/jour) : "
                        "compteur thermique bloqué ou mal relevé ?")
            if arrete(ef) and not arrete(th):
                ajouter(li, 1, 'eau_froide', 'Thermique sans eau froide',
                        f"{_fr(th, 3)} m³/jour de thermique mais quasiment pas d'eau froide ({_fr(ef, 3)} m³/jour) : "
                        "compteur d'eau froide bloqué ou mal relevé ?")

        # Règle 3 — Consommation hors norme par rapport à l'immeuble, à taille égale (indice).
        for fluide in FLUIDES:
            indice = li[f'indice_{fluide}']
            if indice is None:
                continue
            fois = _fr(indice / 100)
            if indice >= INDICE_ERREUR_CHIFFRE:
                ajouter(li, 1, fluide, 'Erreur de chiffre ?',
                        f"{fois} fois la médiane de l'immeuble à taille égale : chiffre en trop ou virgule mal placée ?")
            elif indice >= INDICE_TRES_ELEVE:
                ajouter(li, 2, fluide, 'Consommation très élevée',
                        f"{fois} fois la médiane de l'immeuble à taille égale.")
            elif indice <= INDICE_TRES_FAIBLE:
                ajouter(li, 2, fluide, 'Consommation très faible',
                        f"Seulement {fois} fois la médiane de l'immeuble à taille égale : "
                        "compteur qui sous-compte, ou logement peu occupé ?")

    # Règle 4 — Relevés inversés : deux logements anormaux (hors norme ou index en baisse) qui
    # redeviennent normaux TOUS LES DEUX si on échange leurs index de fin. Typique d'une
    # confusion entre deux compteurs voisins pendant la tournée.
    for fluide in FLUIDES:
        candidats = [li for li in lignes
                     if not li['vide'] and li['tantieme'] and li[fluide] is not None
                     and (li[fluide] < 0 or (li[f'indice_{fluide}'] is not None and not normal(li[f'indice_{fluide}'])))]
        for i, a in enumerate(candidats):
            for b in candidats[i + 1:]:
                indices = _indices_si_echange(a, b, fluide, releves_par_fluide[fluide], debut, fin, medianes[fluide])
                if indices and all(normal(x) for x in indices):
                    for li, autre in ((a, b), (b, a)):
                        ajouter(li, 1, fluide, 'Relevés inversés ?',
                                f"Hors norme, mais redevient normal si on échange son relevé avec celui du logement "
                                f"{autre['numero_appartement']} : confusion pendant la tournée ?")

    # Règle 5 — Changement brutal par rapport à la période précédente. On compare des indices,
    # donc l'évolution de tout l'immeuble (saison de chauffe, vacances...) est neutralisée.
    if lignes_prec:
        prec = {li['id']: li for li in lignes_prec}
        for li in lignes:
            p = prec.get(li['id'])
            if not p or li['vide'] or p['vide']:
                continue
            for fluide in FLUIDES:
                avant, apres = p[f'indice_{fluide}'], li[f'indice_{fluide}']
                if not avant or not apres or apres >= INDICE_ERREUR_CHIFFRE:
                    continue  # pas de comparaison possible, ou déjà signalé comme erreur de chiffre
                ratio = apres / avant
                if ratio >= RATIO_CHANGEMENT_BRUTAL:
                    ajouter(li, 1, fluide, 'Hausse brutale',
                            f"Consommation {_fr(ratio)} fois plus forte que sur la période précédente, "
                            "à évolution de l'immeuble égale : fuite ?")
                elif ratio <= 1 / RATIO_CHANGEMENT_BRUTAL:
                    ajouter(li, 2, fluide, 'Baisse brutale',
                            f"Consommation {_fr(1 / ratio)} fois plus faible que sur la période précédente, "
                            "à évolution de l'immeuble égale : compteur bloqué ou logement inoccupé ?")

    anomalies.sort(key=lambda a: (a['gravite'], a['numero_appartement'], a['fluide']))
    return anomalies


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def analyser(logements, releves_eau_froide, releves_thermique, debut, fin, seuil):
    """
    logements : liste de dicts (id, numero_appartement, tantieme)
    releves_eau_froide / releves_thermique : dict {(logement_id, 'AAAA-MM-JJ'): index en m³}
    debut, fin : dates 'AAAA-MM-JJ' (debut < fin)
    seuil : seuil "logement vide" en m³/jour, ou None
    """
    releves = {'eau_froide': releves_eau_froide, 'thermique': releves_thermique}
    dates = dates_avec_nombre_releves(releves)

    lignes, medianes, medianes_brutes = _calculer_periode(logements, releves, debut, fin, seuil)

    prec = periode_precedente(dates, len(logements), debut)
    lignes_prec = _calculer_periode(logements, releves, *prec, seuil)[0] if prec else None

    anomalies = _detecter_anomalies(lignes, lignes_prec, medianes, releves, debut, fin, seuil)

    # Informations à afficher : compteurs exclus faute de relevé à l'une des deux dates
    sans_releve = {f: [li['numero_appartement'] for li in lignes if li[f] is None] for f in FLUIDES}
    fluides_absents = [LIBELLES[f] for f in FLUIDES if len(sans_releve[f]) == len(lignes)]

    # Données du graphique "période précédente / période choisie"
    comparaison = []
    if lignes_prec:
        p_par_id = {li['id']: li for li in lignes_prec}
        for li in lignes:
            p = p_par_id.get(li['id'])
            if p:
                comparaison.append({
                    'numero_appartement': li['numero_appartement'],
                    'eau_froide': [p['indice_eau_froide'], li['indice_eau_froide']],
                    'thermique': [p['indice_thermique'], li['indice_thermique']],
                })

    return {
        'debut': debut,
        'fin': fin,
        'jours': _jours_entre(debut, fin),
        'seuil': seuil,
        'lignes': lignes,
        'medianes': medianes,
        'medianes_brutes': medianes_brutes,
        'anomalies': anomalies,
        'periode_precedente': prec,
        'comparaison': comparaison,
        'vides': [li['numero_appartement'] for li in lignes if li['vide']],
        'sans_releve': sans_releve,
        'fluides_absents': fluides_absents,
        'seuils_indice': {'tres_eleve': INDICE_TRES_ELEVE, 'tres_faible': INDICE_TRES_FAIBLE},
    }
