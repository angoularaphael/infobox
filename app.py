"""Application Flask — collecte BoxRec managers / matchmakers / promoters."""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import uuid
import queue
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, request, send_file, send_from_directory
from io import BytesIO

from scraper.boxrec_client import BoxRecClient, BoxRecError, VALID_ROLES
from scraper.enrich import enrich_people
from scraper.http_session import session_backend_name
from scraper.export_utils import people_to_csv_rows, people_to_pdf_bytes
from scraper.parser import parse_list_page, parse_profile_page, merge_profile_into_person
from scraper.settings_store import (
    clear_credentials,
    get_credentials,
    is_configured,
    save_credentials,
    username_hint,
)
from infobox.config import is_production, public_base_url
from infobox.security import register_security

load_dotenv()

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
INFOBOX_VERSION = "3.6"

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
register_security(app)


def _html_page(name: str):
    return send_from_directory(STATIC_DIR, name)

_jobs: dict[str, dict[str, Any]] = {}
_sessions: dict[str, dict[str, Any]] = {}


def _job_error(job_id: str, message: str) -> None:
    _jobs[job_id]["status"] = "error"
    _jobs[job_id]["error"] = message


@app.get("/")
def page_accueil():
    return redirect("/assistant")


@app.get("/configuration")
@app.get("/collecte")
@app.get("/manuel")
@app.get("/resultats")
def page_legacy_redirect():
    return redirect("/assistant")


@app.get("/assistant")
def page_assistant():
    return _html_page("assistant.html")


@app.get("/@@BOOKMARKLET_HREF@@")
def bad_bookmark_placeholder():
    return redirect("/assistant?erreur=favori-invalide")


@app.get("/static/js/bookmarklet.js")
def serve_bookmarklet_js():
    """Évite qu’un favori mal copié (URL .js) remplace la page BoxRec par du code brut."""
    dest = (request.headers.get("Sec-Fetch-Dest") or "").lower()
    if dest == "document":
        return send_from_directory(STATIC_DIR, "favori-mauvais.html")
    return send_from_directory(
        os.path.join(STATIC_DIR, "js"),
        "bookmarklet.js",
        mimetype="application/javascript",
    )


def _build_bookmarklet_href() -> str:
    """Favori court : charge bookmarklet.js depuis InfoBox (local ou Vercel)."""
    base = public_base_url()
    launcher = (
        "(function(){"
        "try{"
        "if(window.__infoboxRun){return;}"
        "window.__infoboxRun=1;window.__infoboxCancel=0;"
        "if(!/boxrec\\.com/i.test(location.hostname)){"
        "alert('InfoBox\\n\\nOuvrez une page LISTE sur boxrec.com\\n"
        "(managers / matchmakers), puis recliquez le favori.');"
        "window.__infoboxRun=0;return;}"
        "var o=document.createElement('div');"
        "o.id='infobox-progress';"
        "o.innerHTML='<div style=\"position:fixed;inset:0;z-index:2147483647;"
        "background:rgba(10,22,40,0.88);display:flex;align-items:center;"
        "justify-content:center;font-family:Segoe UI,system-ui,sans-serif\">"
        "<div style=\"background:#fff;padding:1.5rem 2rem;border-radius:12px;"
        "border:2px solid #2563eb;text-align:center;max-width:22rem\">"
        "<div style=\"font-size:1.2rem;font-weight:700;color:#1d4ed8\">InfoBox</div>"
        "<div id=\"infobox-progress-msg\" style=\"margin-top:0.5rem;color:#0f172a;font-weight:600\">"
        "Démarrage…</div>"
        "<div id=\"infobox-progress-sub\" style=\"font-size:0.9rem;color:#475569;margin-top:0.5rem\">"
        "Chargement du script…</div></div></div>';"
        "document.body.appendChild(o);"
        f"var s=document.createElement('script');"
        f"s.src='{base}/static/js/bookmarklet.js?'+Date.now();"
        "s.onload=function(){"
        "if(typeof infoboxExtractFromPage==='function'){infoboxExtractFromPage();}"
        "else{alert('InfoBox: script non chargé. Ouvrez /assistant sur le site InfoBox.');window.__infoboxRun=0;}"
        "};"
        "s.onerror=function(){"
        "window.__infoboxRun=0;"
        "var p=document.getElementById('infobox-progress');if(p)p.remove();"
        "alert('InfoBox: impossible de joindre le serveur.\\n\\n"
        "1) Le site InfoBox doit être en ligne\\n"
        "2) Réinstallez le favori depuis /assistant\\n"
        "3) Réessayez sur boxrec.com');"
        "};"
        "document.head.appendChild(s);"
        "}catch(e){window.__infoboxRun=0;alert('InfoBox erreur: '+e);}"
        "})();"
    )
    return f"javascript:{quote(launcher, safe='(),.;=[]')}"


@app.get("/api/bookmarklet")
def api_bookmarklet():
    return jsonify({"href": _build_bookmarklet_href(), "version": INFOBOX_VERSION})


@app.get("/download/favori-infobox.html")
def download_favori_bookmarks_file():
    """Fichier importable dans Chrome/Edge — sans glisser-déposer."""
    href = html_lib.escape(_build_bookmarklet_href(), quote=True)
    content = f"""<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>InfoBox</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><A HREF="{href}" ADD_DATE="0">InfoBox v{INFOBOX_VERSION} — BoxRec export</A>
</DL><p>
"""
    return Response(
        content,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=favori-infobox.html"},
    )


@app.get("/test-favori")
def page_test_favori():
    """Vérifie que python app.py répond (ouvrir dans le navigateur)."""
    return jsonify({"ok": True, "message": "InfoBox serveur actif. Réinstallez le favori depuis /assistant."})


@app.get("/install-favori")
def page_install_favori():
    href = html_lib.escape(_build_bookmarklet_href(), quote=True)
    page = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
<title>Installer favori — InfoBox</title>
<link rel="stylesheet" href="/static/css/assistant.css" />
</head><body class="assistant-page"><div class="bg-glow"></div>
<div class="shell" style="text-align:center;padding-top:4rem">
<a class="brand" href="/assistant">Info<span>Box</span></a>
<h1 style="font-family:Fraunces,serif;margin:2rem 0 1rem">Glisser le favori</h1>
<p style="color:#a8a29e;max-width:24rem;margin:0 auto 2rem">Glissez le bouton vers la barre de favoris. Ne cliquez pas ici.</p>
<p><a class="btn" style="padding:1rem 1.75rem;font-size:1.1rem" href="{href}" draggable="true">InfoBox — glisser vers les favoris</a></p>
<p style="margin-top:2rem"><a href="/assistant" style="color:#60a5fa">← Retour à l’assistant</a></p>
</div></body></html>"""
    return Response(page, mimetype="text/html; charset=utf-8")


@app.route("/api/session/save", methods=["POST", "OPTIONS"])
def session_save():
    if request.method == "OPTIONS":
        return "", 204
    body = request.get_json(silent=True) or {}
    people = body.get("people", [])
    if not people:
        return jsonify({"error": "Liste vide"}), 400
    sid = str(uuid.uuid4())
    _sessions[sid] = {
        "people": people,
        "role": body.get("role", "manager"),
    }
    return jsonify({"session_id": sid, "count": len(people)})


@app.get("/api/session/<session_id>/csv")
def session_csv(session_id: str):
    data = _sessions.get(session_id)
    if not data:
        return jsonify({"error": "Session expirée — relancez le favori."}), 404
    role = data.get("role", "contacts")
    content = people_to_csv_rows(data["people"])
    return Response(
        content,
        mimetype="text/csv; charset=utf-16le",
        headers={"Content-Disposition": f"attachment; filename=boxrec_{role}.csv"},
    )


@app.get("/api/session/<session_id>/pdf")
def session_pdf(session_id: str):
    data = _sessions.get(session_id)
    if not data:
        return jsonify({"error": "Session expirée — relancez le favori."}), 404
    role = data.get("role", "contacts")
    pdf = people_to_pdf_bytes(data["people"], title=f"BoxRec — {role}")
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"boxrec_{role}.pdf",
    )


@app.route("/api/enrich", methods=["POST", "OPTIONS"])
def api_enrich():
    if request.method == "OPTIONS":
        return "", 204
    body = request.get_json(silent=True) or {}
    people = body.get("people", [])
    if not isinstance(people, list):
        return jsonify({"error": "Format invalide"}), 400
    enrich_people(people)
    return jsonify({"ok": True, "people": people, "count": len(people)})


@app.post("/api/import")
def api_import():
    body = request.get_json(silent=True) or {}
    people = body.get("people")
    if not isinstance(people, list) or not people:
        return jsonify({"error": "Aucun contact dans les données importées."}), 400
    role = (body.get("role") or "").strip().lower()
    for p in people:
        if role and not p.get("role"):
            p["role"] = role
    return jsonify({"ok": True, "people": people, "count": len(people)})


@app.get("/robots.txt")
def robots_txt():
    return send_from_directory(STATIC_DIR, "robots.txt", mimetype="text/plain")


@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "roles": list(VALID_ROLES),
            "configured": is_configured(),
            "http_backend": session_backend_name(),
            "recommended_mode": "assistant",
            "public_url": public_base_url(),
            "production": is_production(),
        }
    )


@app.get("/api/config")
def get_config():
    user, _ = get_credentials()
    env_user = os.getenv("BOXREC_USERNAME", "").strip()
    source = "env" if env_user else ("file" if user else None)
    return jsonify(
        {
            "configured": is_configured(),
            "username_hint": username_hint(),
            "source": source,
        }
    )


@app.post("/api/config")
def post_config():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password")

    if not username:
        return jsonify({"error": "Nom d'utilisateur requis."}), 400

    _, existing_pass = get_credentials()
    if password is None or password == "":
        if not existing_pass:
            return jsonify({"error": "Mot de passe requis pour la première configuration."}), 400
        password = existing_pass
    else:
        password = str(password)

    save_credentials(username, password)
    return jsonify({"ok": True, "message": "Identifiants enregistrés localement (data/settings.json)."})


@app.delete("/api/config")
def delete_config():
    if os.getenv("BOXREC_USERNAME", "").strip():
        return jsonify(
            {
                "error": "Les identifiants viennent du fichier .env. Retirez-les de .env pour utiliser l'interface.",
            }
        ), 400
    clear_credentials()
    return jsonify({"ok": True})


@app.post("/api/config/test")
def test_config():
    if not is_configured():
        return jsonify({"ok": False, "message": "Aucun identifiant configuré."}), 400
    try:
        client = BoxRecClient()
        client.login()
        parsed = client.fetch_list_page("manager", offset=0)
        if parsed.get("is_login_page"):
            return jsonify(
                {
                    "ok": False,
                    "message": "Connexion refusée — vérifiez identifiant et mot de passe.",
                }
            )
        return jsonify({"ok": True, "message": "Connexion BoxRec réussie."})
    except BoxRecError as exc:
        return jsonify({"ok": False, "message": str(exc), "manual_mode": True})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "message": f"Erreur : {exc}"})


@app.post("/api/scrape")
def start_scrape():
    body = request.get_json(silent=True) or {}
    role = (body.get("role") or "manager").strip().lower()
    max_pages = body.get("max_pages")
    fetch_contacts = body.get("fetch_contacts", True)
    all_countries = bool(body.get("all_countries"))
    if max_pages is not None:
        max_pages = int(max_pages)

    if role not in VALID_ROLES:
        return jsonify({"error": f"Rôle invalide. Choisir : {', '.join(VALID_ROLES)}"}), 400

    import uuid

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "running",
        "role": role,
        "people": [],
        "error": None,
        "events": queue.Queue(),
    }

    def run() -> None:
        q: queue.Queue = _jobs[job_id]["events"]

        def on_progress(evt: dict[str, Any]) -> None:
            if evt.get("type") == "person":
                _jobs[job_id]["people"].append(evt["person"])
            q.put(evt)

        try:
            client = BoxRecClient()
            if all_countries:
                people = client.scrape_all_countries(
                    role,
                    max_pages=max_pages,
                    fetch_contacts=bool(fetch_contacts),
                    on_progress=on_progress,
                )
            else:
                people = client.scrape_role(
                    role,
                    max_pages=max_pages,
                    fetch_contacts=bool(fetch_contacts),
                    on_progress=on_progress,
                )
            _jobs[job_id]["people"] = people
            _jobs[job_id]["status"] = "done"
            q.put({"type": "done", "count": len(people)})
        except BoxRecError as exc:
            _job_error(job_id, str(exc))
            q.put({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            _job_error(job_id, f"Erreur inattendue : {exc}")
            q.put({"type": "error", "message": str(exc)})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.get("/api/scrape/<job_id>/stream")
def scrape_stream(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job introuvable"}), 404

    def generate():
        q: queue.Queue = job["events"]
        while True:
            try:
                evt = q.get(timeout=120)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
                break
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
            if evt.get("type") in ("done", "error"):
                break

    return Response(generate(), mimetype="text/event-stream")


@app.get("/api/scrape/<job_id>")
def scrape_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job introuvable"}), 404
    return jsonify(
        {
            "status": job["status"],
            "role": job.get("role"),
            "count": len(job.get("people", [])),
            "people": job.get("people", []),
            "error": job.get("error"),
        }
    )


@app.post("/api/parse/manual")
def parse_manual():
    """Mode secours : coller le HTML d'une page liste (et optionnellement profils)."""
    body = request.get_json(silent=True) or {}
    html = body.get("html", "")
    role = (body.get("role") or "manager").strip().lower()
    fetch_profiles = body.get("fetch_profiles", False)

    if not html.strip():
        return jsonify({"error": "HTML vide"}), 400

    list_url = (body.get("list_url") or "").strip()
    parsed = parse_list_page(html, list_url=list_url or None)
    people = parsed.get("people", [])
    search_country = parsed.get("search_country") or ""
    for p in people:
        p["role"] = role
        if search_country and not p.get("search_country"):
            p["search_country"] = search_country

    if fetch_profiles and is_configured():
        try:
            client = BoxRecClient()
            client.login()
            for p in people:
                if p.get("profile_url"):
                    try:
                        prof = client.fetch_profile(p["profile_url"])
                        merge_profile_into_person(p, prof)
                    except BoxRecError:
                        pass
        except BoxRecError as exc:
            return jsonify({"people": people, "warning": str(exc)})

    return jsonify(
        {
            "people": people,
            "is_login_page": parsed.get("is_login_page"),
            "total_hint": parsed.get("total_hint"),
        }
    )


@app.post("/api/parse/profile")
def parse_profile_manual():
    body = request.get_json(silent=True) or {}
    html = body.get("html", "")
    if not html.strip():
        return jsonify({"error": "HTML vide"}), 400
    return jsonify(parse_profile_page(html))


@app.post("/api/export/csv")
def export_csv():
    people = (request.get_json(silent=True) or {}).get("people", [])
    content = people_to_csv_rows(people)
    return Response(
        content,
        mimetype="text/csv; charset=utf-16le",
        headers={"Content-Disposition": "attachment; filename=boxrec_contacts.csv"},
    )


@app.post("/api/export/pdf")
def export_pdf():
    body = request.get_json(silent=True) or {}
    people = body.get("people", [])
    title = body.get("title", "BoxRec — Contacts")
    pdf = people_to_pdf_bytes(people, title=title)
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="boxrec_contacts.pdf",
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print(f"InfoBox — {public_base_url()}/assistant")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True, use_reloader=False)
