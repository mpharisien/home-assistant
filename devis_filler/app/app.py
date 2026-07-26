import threading
import traceback
from flask import Flask, render_template, request, redirect, url_for

import db
import automation

app = Flask(__name__)
db.init_db()

# Etat du run en cours, partagé en mémoire (usage mono-utilisateur local)
RUN_STATE = {"running": False, "identity_label": None, "log": [], "error": None}
_lock = threading.Lock()


def _background_run(identity_label):
    def on_progress(result):
        with _lock:
            RUN_STATE["log"].append(result)

    try:
        automation.run_for_identity(identity_label, progress_cb=on_progress)
    except Exception as e:
        with _lock:
            RUN_STATE["error"] = f"{e}\n{traceback.format_exc()}"
    finally:
        with _lock:
            RUN_STATE["running"] = False


@app.route("/")
def index():
    identities = db.list_identities()
    return render_template("index.html", identities=identities, run_state=RUN_STATE)


@app.route("/run", methods=["POST"])
def start_run():
    identity_label = request.form.get("identity_label")
    with _lock:
        if not RUN_STATE["running"]:
            RUN_STATE["running"] = True
            RUN_STATE["identity_label"] = identity_label
            RUN_STATE["log"] = []
            RUN_STATE["error"] = None
            t = threading.Thread(target=_background_run, args=(identity_label,), daemon=True)
            t.start()
    return redirect(url_for("run_status"))


@app.route("/run/status")
def run_status():
    return render_template("run_status.html", run_state=RUN_STATE)


# ---------- Identités ----------

@app.route("/identities")
def identities_list():
    return render_template("identities.html", identities=db.list_identities())


@app.route("/identities/new", methods=["GET", "POST"])
def identity_new():
    if request.method == "POST":
        db.save_identity(request.form)
        return redirect(url_for("identities_list"))
    return render_template("identity_form.html", identity=None)


@app.route("/identities/<int:identity_id>/edit", methods=["GET", "POST"])
def identity_edit(identity_id):
    if request.method == "POST":
        db.save_identity(request.form, identity_id=identity_id)
        return redirect(url_for("identities_list"))
    return render_template("identity_form.html", identity=db.get_identity(identity_id=identity_id))


@app.route("/identities/<int:identity_id>/delete", methods=["POST"])
def identity_delete(identity_id):
    db.delete_identity(identity_id)
    return redirect(url_for("identities_list"))


# ---------- Sites ----------

@app.route("/sites")
def sites_list():
    return render_template("sites.html", sites=db.list_sites())


@app.route("/sites/new", methods=["GET", "POST"])
def site_new():
    if request.method == "POST":
        db.save_site(request.form)
        return redirect(url_for("sites_list"))
    return render_template("site_form.html", site=None, fields=db.SITE_FIELDS)


@app.route("/sites/<int:site_id>/edit", methods=["GET", "POST"])
def site_edit(site_id):
    if request.method == "POST":
        db.save_site(request.form, site_id=site_id)
        return redirect(url_for("sites_list"))
    return render_template("site_form.html", site=db.get_site(site_id), fields=db.SITE_FIELDS)


@app.route("/sites/<int:site_id>/toggle", methods=["POST"])
def site_toggle(site_id):
    site = db.get_site(site_id)
    db.set_site_active(site_id, not site["actif"])
    return redirect(url_for("sites_list"))


@app.route("/sites/<int:site_id>/delete", methods=["POST"])
def site_delete(site_id):
    db.delete_site(site_id)
    return redirect(url_for("sites_list"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
