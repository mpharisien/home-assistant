"""
Analyse des relevés Océa (eau froide et thermique) sur une période choisie.

Utilisé par le dashboard Océa pour repérer les compteurs ou relevés suspects.

PRINCIPES (choix validés en octobre 2026, à relire avant toute modification)
------------------------------------------------------------------------------
1. On travaille sur la CONSOMMATION entre deux dates de relevé (index fin - index début),
   et non sur l'index cumulé. L'index cumulé mélange toutes les périodes depuis la pose :
   un logement anormal il y a six mois le resterait pour toujours.

2. La consommation est ramenée en m³ PAR JOUR. Les tournées n'ont pas toutes la même
   durée : sans cette division, une période plus longue paraîtrait plus "gourmande".

3. Une seule période (début + fin) pour l'eau froide ET le thermique : les deux compteurs
   sont toujours relevés le même jour lors des tournées.

4. On compare UNIQUEMENT les logements entre eux, sur la même période. La comparaison
   d'un logement avec sa propre période précédente a été abandonnée (v1.7.1) : avec une
   dizaine de logements vides ou occupés par intermittence et des dates de relevé
   irrégulières, elle produisait surtout des alertes inexplicables.

5. Pour comparer des logements de tailles différentes, on divise par le TANTIÈME (la
   surface n'est pas connue pour tous les logements). On calcule ensuite un INDICE :
       indice = (conso par jour / tantième) / médiane de l'immeuble de ce même ratio × 100
   100 = comme un logement médian de même taille ; 200 = 2 fois plus.
   On utilise la MÉDIANE et non la moyenne : les quelques valeurs aberrantes (justement
   celles qu'on cherche) fausseraient une moyenne, pas une médiane.

6. Seuil « logement vide » (optionnel, en m³/jour) : un logement dont TOUS les compteurs
   connus sont sous le seuil est considéré comme vide et ignoré. Si UN SEUL compteur est
   sous le seuil, le logement n'est PAS ignoré : c'est justement ce qu'on veut détecter
   (compteur bloqué, vanne oubliée...).

7. Saison de chauffe : en été, le chauffage est coupé et le thermique est quasiment nul
   partout. Les règles qui supposent que le chauffage tourne sont alors désactivées.
   Une période est "de chauffe" si le chauffage a été en marche au moins la MOITIÉ de ses
   jours (dates d'allumage / coupure saisies dans l'onglet Chauffage). En dessous, le
   thermique est trop faible pour que les comparaisons aient un sens.
   Si aucune date n'est saisie, on ne sait pas : toutes les règles s'appliquent.

8. Dates "complètes" : certaines tournées ne concernent que quelques logements (ex. les
   3 logements d'un même étage). Une date est complète si au moins 60 % des logements y
   ont été relevés. Ce seuil sert UNIQUEMENT à choisir la période proposée par défaut :
   l'utilisateur peut toujours choisir une date partielle, et les mêmes règles
   s'appliquent alors aux seuls logements relevés (médianes moins fiables, choix assumé).

NIVEAUX D'ALERTE (du plus grave au moins grave)
  rouge, orange, jaune : consommation trop élevée ou incohérence, par ordre de gravité ;
  vert : tout ce qui est "bas" (consommation faible), à simple titre d'information.
Pour une même règle et un même compteur, un logement n'apparaît qu'une fois, au niveau
le plus élevé atteint.

Ce module ne lit ni n'écrit la base : il reçoit des données et renvoie des résultats.
"""
from datetime import date as _date, timedelta
from statistics import median

FLUIDES = ('eau_froide', 'thermique')
LIBELLES = {'eau_froide': 'Eau froide', 'thermique': 'Thermique'}

# Ordre d'affichage des niveaux d'alerte (du plus grave au moins grave)
NIVEAUX = ('rouge', 'orange', 'jaune', 'vert')

# Part minimale des logements relevés pour qu'une date soit "complète" (principe 8).
PART_MINIMALE_DATE_COMPLETE = 0.60

# Part minimale des jours de la période avec chauffage en marche pour parler de
# "période de chauffe" (principe 7).
PART_MINIMALE_JOURS_CHAUFFE = 0.50

# Consommation élevée par rapport aux autres logements (indice, 100 = médiane).
# 2 fois la médiane = jaune, 3 fois = orange, 4 fois = rouge.
PALIERS_CONSO_ELEVEE = ((400, 'rouge'), (300, 'orange'), (200, 'jaune'))
# Au-delà de 8 fois la médiane, on suggère de vérifier le relevé (chiffre en trop,
# virgule mal placée...). Ce n'est plus une règle à part, seulement une mention.
INDICE_VERIFIER_RELEVE = 800
# Consommation faible : 2 fois moins que la médiane (indice ≤ 50) = vert.
INDICE_CONSO_FAIBLE = 50

# Un compteur nettement plus haut que l'autre, en indices (règles 7 et 8) :
# 2 fois = jaune, 3 fois = orange, 4 fois = rouge.
PALIERS_RATIO_COMPTEURS = ((4, 'rouge'), (3, 'orange'), (2, 'jaune'))

# Liste des règles, affichée telle quelle dans le dashboard (lien "Voir les règles").
# À tenir à jour si une règle change.
REGLES = [
    {'numero': 1, 'nom': 'Index en baisse', 'compteur': 'Eau froide',
     'declenchement': "Index de fin plus petit que l'index de début",
     'niveaux': 'rouge', 'desactivee': 'Jamais'},
    {'numero': 2, 'nom': 'Index en baisse', 'compteur': 'Thermique',
     'declenchement': "Index de fin plus petit que l'index de début",
     'niveaux': 'rouge', 'desactivee': 'Jamais'},
    {'numero': 3, 'nom': 'Thermique sans eau froide', 'compteur': 'Eau froide',
     'declenchement': 'Thermique au-dessus du seuil, eau froide en dessous (à zéro si aucun seuil)',
     'niveaux': 'rouge', 'desactivee': 'Jamais'},
    {'numero': 4, 'nom': 'Eau froide sans thermique', 'compteur': 'Thermique',
     'declenchement': 'Eau froide au-dessus du seuil, thermique en dessous (à zéro si aucun seuil)',
     'niveaux': 'orange', 'desactivee': 'Hors chauffage'},
    {'numero': 5, 'nom': 'Consommation élevée', 'compteur': 'Eau froide',
     'declenchement': '2 / 3 / 4 fois la médiane à taille égale (indice ≥ 200 / 300 / 400)',
     'niveaux': 'jaune / orange / rouge', 'desactivee': 'Jamais'},
    {'numero': 6, 'nom': 'Consommation élevée', 'compteur': 'Thermique',
     'declenchement': '2 / 3 / 4 fois la médiane à taille égale (indice ≥ 200 / 300 / 400)',
     'niveaux': 'jaune / orange / rouge', 'desactivee': 'Hors chauffage'},
    {'numero': 7, 'nom': "Thermique élevé par rapport à l'eau froide", 'compteur': 'Thermique',
     'declenchement': "Indice thermique ≥ 2 / 3 / 4 fois l'indice eau froide",
     'niveaux': 'jaune / orange / rouge', 'desactivee': 'Hors chauffage'},
    {'numero': 8, 'nom': 'Eau froide élevée par rapport au thermique', 'compteur': 'Eau froide',
     'declenchement': "Indice eau froide ≥ 2 / 3 / 4 fois l'indice thermique",
     'niveaux': 'jaune / orange / rouge', 'desactivee': 'Hors chauffage'},
    {'numero': 9, 'nom': 'Consommation faible', 'compteur': 'Eau froide',
     'declenchement': '2 fois moins que la médiane à taille égale, ou moins (indice ≤ 50)',
     'niveaux': 'vert', 'desactivee': 'Jamais'},
    {'numero': 10, 'nom': 'Consommation faible', 'compteur': 'Thermique',
     'declenchement': '2 fois moins que la médiane à taille égale, ou moins (indice ≤ 50)',
     'niveaux': 'vert', 'desactivee': 'Hors chauffage'},
]


def _fr(valeur, decimales=1):
    """Nombre à la française (virgule décimale), pour les textes d'explication."""
    return f"{valeur:.{decimales}f}".replace('.', ',')


def _jours_entre(debut, fin):
    return (_date.fromisoformat(fin) - _date.fromisoformat(debut)).days


def niveau_conso_elevee(indice):
    """Niveau d'alerte d'un indice de consommation (rouge/orange/jaune), ou None."""
    if indice is None:
        return None
    for seuil, niveau in PALIERS_CONSO_ELEVEE:
        if indice >= seuil:
            return niveau
    return None


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


def periode_par_defaut(dates, nb_logements):
    """
    Période proposée à l'ouverture du dashboard : les deux dernières dates complètes
    (au moins 60 % des logements relevés, principe 8). S'il n'y en a pas deux, on se
    rabat sur les deux dernières dates tout court.
    """
    minimum = nb_logements * PART_MINIMALE_DATE_COMPLETE
    completes = [d['date'] for d in dates if d['nb'] >= minimum]
    if len(completes) >= 2:
        return completes[1], completes[0]
    toutes = [d['date'] for d in dates]
    return (toutes[1], toutes[0]) if len(toutes) >= 2 else (None, None)


# ─── Saison de chauffe ────────────────────────────────────────────────────────

def jours_de_chauffe(evenements, debut, fin):
    """
    Nombre de jours de la période [debut, fin[ pendant lesquels le chauffage était en marche.

    evenements : liste de dicts {'date': 'AAAA-MM-JJ', 'action': 'allumage' ou 'coupure'}.
    - Le jour d'un événement, le nouvel état s'applique dès ce jour-là.
    - Avant le tout premier événement saisi, on considère l'état inverse de cet événement
      (si la première ligne est un allumage, le chauffage était coupé avant).
    Retourne None si aucun événement n'est saisi (état inconnu).
    """
    if not evenements:
        return None
    evts = sorted(evenements, key=lambda e: e['date'])
    jour = _date.fromisoformat(debut)
    dernier_jour = _date.fromisoformat(fin)
    etat = evts[0]['action'] != 'allumage'  # état avant le premier événement
    i, nb = 0, 0
    while jour < dernier_jour:
        while i < len(evts) and evts[i]['date'] <= jour.isoformat():
            etat = evts[i]['action'] == 'allumage'
            i += 1
        nb += etat
        jour += timedelta(days=1)
    return nb


# ─── Calculs sur la période ───────────────────────────────────────────────────

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
        # Vide = tous les compteurs connus sous le seuil (principe 6). Une valeur négative n'est
        # jamais "vide" : c'est un index en baisse, donc une erreur à signaler.
        ligne['vide'] = seuil is not None and bool(connues) and all(0 <= c < seuil for c in connues)
        lignes.append(ligne)

    def _comparable(li, fluide):
        """
        Valeur utilisable pour la médiane et l'indice : logement non vide, avec un tantième,
        consommation connue, et au-dessus du seuil (strictement positive s'il n'y a pas de seuil).
        Un compteur à l'arrêt alors que l'autre tourne est suspect : on ne le laisse pas tirer
        la médiane vers le bas ; il est signalé par les règles 3 et 4.
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

def _detecter_anomalies(lignes, seuil, chauffage_actif):
    """
    Applique les règles 1 à 10 (voir REGLES). chauffage_actif : False si la période est
    hors chauffage (règles 4, 6, 7, 8 et 10 désactivées), True ou None sinon.
    """
    anomalies = []
    hors_chauffage = chauffage_actif is False

    def ajouter(li, niveau, fluide, regle, type_, explication):
        anomalies.append({
            'numero_appartement': li['numero_appartement'],
            'niveau': niveau,
            'fluide': LIBELLES[fluide],
            'fluide_code': fluide,
            'regle': regle,
            'type': type_,
            'explication': explication,
        })

    # "À l'arrêt" : sous le seuil s'il est défini, sinon exactement zéro.
    arrete = (lambda v: v < seuil) if seuil is not None else (lambda v: v == 0)

    for li in lignes:
        # Règles 1 et 2 — Index en baisse : physiquement impossible, donc erreur de saisie
        # (ou compteur remplacé). Signalée même pour un logement vide.
        for regle, fluide in ((1, 'eau_froide'), (2, 'thermique')):
            if li[fluide] is not None and li[fluide] < 0:
                ajouter(li, 'rouge', fluide, regle, 'Index en baisse',
                        "L'index de fin est plus petit que l'index de début : erreur de saisie ou compteur remplacé ?")

        if li['vide']:
            continue

        ef, th = li['eau_froide'], li['thermique']
        if ef is not None and th is not None and ef >= 0 and th >= 0:
            # Règle 3 — Thermique sans eau froide (rouge, toute l'année) : typiquement un
            # logement inoccupé dont la vanne d'eau froide est fermée mais pas celle du
            # chauffage, qui chauffe donc pour rien. Ou compteur d'eau froide bloqué.
            if arrete(ef) and not arrete(th):
                ajouter(li, 'rouge', 'eau_froide', 3, 'Thermique sans eau froide',
                        f"{_fr(th, 3)} m³/jour de thermique mais quasiment pas d'eau froide ({_fr(ef, 3)} m³/jour) : "
                        "logement inoccupé chauffé, ou compteur d'eau froide bloqué ?")
            # Règle 4 — Eau froide sans thermique (orange) : hors chauffage, c'est normal,
            # d'où la désactivation. En période de chauffe : radiateurs fermés ou compteur bloqué.
            if not hors_chauffage and arrete(th) and not arrete(ef):
                ajouter(li, 'orange', 'thermique', 4, 'Eau froide sans thermique',
                        f"{_fr(ef, 3)} m³/jour d'eau froide mais quasiment pas de thermique ({_fr(th, 3)} m³/jour) : "
                        "radiateurs fermés, ou compteur thermique bloqué ou mal relevé ?")

        # Règles 5 et 6 — Consommation élevée par rapport aux autres logements (indice).
        # Règles 9 et 10 — Consommation faible (vert). Les règles thermiques (6 et 10) sont
        # désactivées hors chauffage : le thermique y est trop faible pour être comparé.
        for fluide, regle_haut, regle_bas in (('eau_froide', 5, 9), ('thermique', 6, 10)):
            if fluide == 'thermique' and hors_chauffage:
                continue
            indice = li[f'indice_{fluide}']
            if indice is None:
                continue
            niveau = niveau_conso_elevee(indice)
            if niveau:
                verif = " Vérifier une erreur de relevé." if indice >= INDICE_VERIFIER_RELEVE else ''
                ajouter(li, niveau, fluide, regle_haut, 'Consommation élevée',
                        f"{_fr(indice / 100)} fois la médiane de l'immeuble à taille égale.{verif}")
            elif indice <= INDICE_CONSO_FAIBLE:
                fois_moins = f"{_fr(100 / indice)} fois moins" if indice > 0 else "beaucoup moins"
                ajouter(li, 'vert', fluide, regle_bas, 'Consommation faible',
                        f"{fois_moins} que la médiane de l'immeuble à taille égale : logement peu occupé, "
                        "ou compteur qui sous-compte ?")

        # Règles 7 et 8 — Un compteur nettement plus haut que l'autre, en indices. Les deux
        # indices doivent exister (compteurs au-dessus du seuil). Désactivées hors chauffage.
        i_ef, i_th = li['indice_eau_froide'], li['indice_thermique']
        if not hors_chauffage and i_ef and i_th:
            for regle, fluide, haut, bas, libelle in (
                    (7, 'thermique', i_th, i_ef, "Thermique élevé par rapport à l'eau froide"),
                    (8, 'eau_froide', i_ef, i_th, 'Eau froide élevée par rapport au thermique')):
                ratio = haut / bas
                for palier, niveau in PALIERS_RATIO_COMPTEURS:
                    if ratio >= palier:
                        ajouter(li, niveau, fluide, regle, libelle,
                                f"Indice {LIBELLES[fluide].lower()} {_fr(ratio)} fois plus élevé que l'autre compteur "
                                f"({haut} contre {bas}).")
                        break

    rang = {n: i for i, n in enumerate(NIVEAUX)}
    anomalies.sort(key=lambda a: (rang[a['niveau']], a['numero_appartement'], a['regle']))
    return anomalies


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def analyser(logements, releves_eau_froide, releves_thermique, debut, fin, seuil, evenements_chauffage):
    """
    logements : liste de dicts (id, numero_appartement, tantieme)
    releves_eau_froide / releves_thermique : dict {(logement_id, 'AAAA-MM-JJ'): index en m³}
    debut, fin : dates 'AAAA-MM-JJ' (debut < fin)
    seuil : seuil "logement vide" en m³/jour, ou None
    evenements_chauffage : liste de dicts {'date', 'action'} (onglet Chauffage)
    """
    releves = {'eau_froide': releves_eau_froide, 'thermique': releves_thermique}
    lignes, medianes, medianes_brutes = _calculer_periode(logements, releves, debut, fin, seuil)

    jours = _jours_entre(debut, fin)
    nb_jours_chauffe = jours_de_chauffe(evenements_chauffage, debut, fin)
    # True = période de chauffe, False = hors chauffage, None = inconnu (aucune date saisie)
    chauffage_actif = None if nb_jours_chauffe is None else nb_jours_chauffe >= jours * PART_MINIMALE_JOURS_CHAUFFE

    anomalies = _detecter_anomalies(lignes, seuil, chauffage_actif)

    # Informations à afficher : compteurs exclus faute de relevé à l'une des deux dates
    sans_releve = {f: [li['numero_appartement'] for li in lignes if li[f] is None] for f in FLUIDES}
    fluides_absents = [LIBELLES[f] for f in FLUIDES if len(sans_releve[f]) == len(lignes)]

    return {
        'debut': debut,
        'fin': fin,
        'jours': jours,
        'seuil': seuil,
        'lignes': lignes,
        'medianes': medianes,
        'medianes_brutes': medianes_brutes,
        'anomalies': anomalies,
        'compte_niveaux': {n: sum(1 for a in anomalies if a['niveau'] == n) for n in NIVEAUX},
        'vides': [li['numero_appartement'] for li in lignes if li['vide']],
        'sans_releve': sans_releve,
        'fluides_absents': fluides_absents,
        'jours_chauffe': nb_jours_chauffe,
        'chauffage_actif': chauffage_actif,
        'regles': REGLES,
        'paliers': {
            'conso_elevee': [p for p, _ in PALIERS_CONSO_ELEVEE],  # [400, 300, 200]
            'conso_faible': INDICE_CONSO_FAIBLE,
            'ratio': [p for p, _ in PALIERS_RATIO_COMPTEURS],      # [4, 3, 2]
        },
    }
