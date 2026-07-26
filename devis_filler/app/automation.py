"""
Logique de remplissage automatique des formulaires.
Ne lève jamais d'exception vers l'appelant : chaque site est traité isolément,
loggé, et la boucle continue toujours.
"""
import time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import db

FIELD_KEYWORDS = {
    "prenom": ["prenom", "prénom", "firstname", "first_name", "fname"],
    "nom": ["nom", "lastname", "last_name", "lname", "name"],
    "email": ["email", "mail", "e-mail"],
    "telephone": ["telephone", "téléphone", "tel", "phone", "mobile", "gsm"],
    "code_postal": ["codepostal", "code_postal", "zip", "postal"],
    "ville": ["ville", "city"],
    "adresse": ["adresse", "address"],
    "message": ["message", "projet", "commentaire", "description", "details", "détails"],
}

SUBMIT_KEYWORDS = [
    "envoyer", "valider", "obtenir mon devis", "demander", "envoyer ma demande",
    "je valide", "recevoir", "submit", "send",
]

SUCCESS_KEYWORDS = [
    "merci", "a bien été envoyé", "a bien ete envoye", "demande enregistrée",
    "demande enregistree", "nous vous recontacterons", "confirmation",
    "a bien été reçu", "a bien ete recu", "bien reçue", "bien recue",
]


def guess_field_value(field_name, identity):
    mapping = {
        "prenom": identity["prenom"],
        "nom": identity["nom"],
        "email": identity["email"],
        "telephone": identity["telephone"],
        "code_postal": identity.get("code_postal") or "",
        "ville": identity.get("ville") or "",
        "adresse": identity.get("adresse") or "",
        "message": identity.get("message_defaut") or "",
    }
    return mapping.get(field_name, "")


def match_keyword(haystack, keywords):
    haystack = (haystack or "").lower()
    return any(k in haystack for k in keywords)


def autodetect_and_fill(page, identity):
    filled = 0
    inputs = page.query_selector_all("input, textarea")
    for el in inputs:
        try:
            attrs = " ".join(filter(None, [
                el.get_attribute("name"), el.get_attribute("id"),
                el.get_attribute("placeholder"), el.get_attribute("aria-label"),
            ]))
        except Exception:
            continue
        input_type = (el.get_attribute("type") or "text").lower()
        if input_type in ("hidden", "submit", "button", "checkbox", "radio", "file"):
            continue
        for field_name, keywords in FIELD_KEYWORDS.items():
            if match_keyword(attrs, keywords):
                value = guess_field_value(field_name, identity)
                if value:
                    try:
                        el.fill(value)
                        filled += 1
                    except Exception:
                        pass
                break
    return filled


def fill_with_selectors(page, site, identity):
    from db import SITE_FIELDS
    filled = 0
    for field_name in SITE_FIELDS:
        if field_name == "submit":
            continue
        selector = site.get(f"sel_{field_name}")
        if not selector:
            continue
        value = guess_field_value(field_name, identity)
        if value:
            try:
                page.fill(selector, value)
                filled += 1
            except Exception:
                pass
    return filled


def find_and_click_submit(page, custom_selector=None):
    if custom_selector:
        try:
            page.click(custom_selector)
            return True
        except Exception:
            pass
    buttons = page.query_selector_all("button, input[type=submit]")
    for b in buttons:
        try:
            tag = b.evaluate("el => el.tagName")
            text = (b.get_attribute("value") if tag == "INPUT" else b.inner_text()) or ""
        except Exception:
            text = ""
        if match_keyword(text, SUBMIT_KEYWORDS) or (b.get_attribute("type") or "").lower() == "submit":
            try:
                b.click()
                return True
            except Exception:
                continue
    return False


def check_success(page):
    try:
        body_text = page.inner_text("body")
    except Exception:
        body_text = ""
    for kw in SUCCESS_KEYWORDS:
        idx = body_text.lower().find(kw)
        if idx != -1:
            snippet = body_text[max(0, idx - 40): idx + 80].strip().replace("\n", " ")
            return True, snippet
    return False, ""


def process_site(page, site, identity):
    """Traite un site. Retourne un dict de résultat (et logue en base)."""
    result = {"site": site["nom"], "url": site["url"]}
    try:
        page.goto(site["url"], timeout=20000, wait_until="domcontentloaded")
    except PWTimeout:
        db.log_result(site["id"], identity["id"], "error", detail="Timeout au chargement de la page")
        result.update(status="error", detail="Timeout au chargement de la page")
        return result
    except Exception as e:
        db.log_result(site["id"], identity["id"], "error", detail=f"Erreur de chargement: {e}")
        result.update(status="error", detail=f"Erreur de chargement: {e}")
        return result

    try:
        if site["mode"] == "manuel":
            filled = fill_with_selectors(page, site, identity)
            if filled == 0:
                msg = "Mode manuel mais aucun sélecteur ne fonctionne — à corriger"
                db.log_result(site["id"], identity["id"], "needs_review", detail=msg)
                result.update(status="needs_review", detail=msg)
                return result
            find_and_click_submit(page, site.get("sel_submit"))
        else:
            filled = autodetect_and_fill(page, identity)
            if filled == 0:
                msg = "Aucun champ reconnu automatiquement — passez ce site en mode manuel"
                db.log_result(site["id"], identity["id"], "needs_review", detail=msg)
                result.update(status="needs_review", detail=msg)
                return result
            find_and_click_submit(page)

        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception as e:
        db.log_result(site["id"], identity["id"], "error", detail=f"Erreur pendant le remplissage: {e}")
        result.update(status="error", detail=f"Erreur pendant le remplissage: {e}")
        return result

    time.sleep(1)
    success, snippet = check_success(page)
    if success:
        db.log_result(site["id"], identity["id"], "success", confirmation_text=snippet)
        result.update(status="success", detail=snippet)
    else:
        msg = "Formulaire soumis mais aucune confirmation détectée — à vérifier"
        db.log_result(site["id"], identity["id"], "needs_review", detail=msg)
        result.update(status="needs_review", detail=msg)
    return result


def run_for_identity(identity_label, progress_cb=None):
    """
    Exécute le remplissage pour tous les sites actifs avec l'identité donnée.
    progress_cb(dict) est appelé après chaque site traité (pour l'UI en direct).
    """
    identity = db.get_identity(label=identity_label)
    if not identity:
        raise ValueError(f"Identité inconnue : {identity_label}")

    sites = db.list_sites(only_active=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        for site in sites:
            result = process_site(page, site, identity)
            if progress_cb:
                progress_cb(result)

        browser.close()
