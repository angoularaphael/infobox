#!/usr/bin/env python3
"""Import managers CSV into Supabase (boxing_center schema)."""

from __future__ import annotations

import csv
import os
import re
import sys
import unicodedata
from pathlib import Path

import time

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
FUTUREBD = ROOT / "futurebd"
CONTACTS_CSV = FUTUREBD / "managers_contacts_sans_doublons.csv"
ENRICHIS_CSV = FUTUREBD / "managers_enrichis.csv"

TEST_MANAGER = {
    "nom": "atangana",
    "email": "linuxcam05@gmail.com",
    "telephone": "237693646080",
    "adresse": "Test — Boxing Center",
    "localisation": "Cameroun",
    "url_profil": "",
    "is_test": True,
}


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits if len(digits) >= 7 else ""


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def contact_type(has_phone: bool, has_email: bool) -> str:
    if has_phone and has_email:
        return "both"
    if has_phone:
        return "phone_only"
    if has_email:
        return "email_only"
    return "none"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        print(f"[warn] Fichier absent: {path}")
        return []
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
    lines = text.splitlines(keepends=True)
    start = 0
    if lines and lines[0].strip().lower().lstrip("\ufeff").startswith("sep="):
        start = 1
    reader = csv.DictReader(lines[start:], delimiter=";")
    return [dict(row) for row in reader]


def pick(row: dict[str, str], *keys: str) -> str:
    lowered = {k.lower().strip(): v for k, v in row.items()}
    for key in keys:
        val = lowered.get(key.lower())
        if val and str(val).strip():
            return str(val).strip()
    return ""


def row_to_manager(row: dict[str, str], *, is_test: bool = False) -> dict | None:
    nom = pick(row, "nom", "Nom")
    if not nom:
        return None
    email = normalize_email(pick(row, "email", "Email"))
    telephone = normalize_phone(pick(row, "telephone", "Téléphone", "Telephone", "Tel"))
    adresse = pick(row, "adresse", "Organisation / Adresse", "organisation / adresse")
    localisation = pick(row, "localisation", "Localisation")
    url_profil = pick(row, "url_profil", "url profil", "profile_url")
    has_phone = bool(telephone)
    has_email = bool(email)
    return {
        "nom": nom,
        "email": email or None,
        "telephone": telephone or None,
        "adresse": adresse or None,
        "localisation": localisation or None,
        "url_profil": url_profil or None,
        "has_phone": has_phone,
        "has_email": has_email,
        "contact_type": contact_type(has_phone, has_email),
        "is_test": is_test,
    }


def load_all_managers() -> dict[str, dict]:
    by_name: dict[str, dict] = {}

    for row in read_csv_rows(CONTACTS_CSV):
        mgr = row_to_manager(row)
        if not mgr:
            continue
        key = normalize_name(mgr["nom"])
        by_name[key] = mgr

    for row in read_csv_rows(ENRICHIS_CSV):
        enrichi = pick(row, "enrichi").lower()
        if enrichi not in ("oui", "yes", "1", "true"):
            continue
        mgr = row_to_manager(row)
        if not mgr:
            continue
        key = normalize_name(mgr["nom"])
        if key in by_name:
            existing = by_name[key]
            for field in ("email", "telephone", "adresse", "localisation", "url_profil"):
                if not existing.get(field) and mgr.get(field):
                    existing[field] = mgr[field]
            existing["has_phone"] = bool(existing.get("telephone"))
            existing["has_email"] = bool(existing.get("email"))
            existing["contact_type"] = contact_type(existing["has_phone"], existing["has_email"])
        else:
            by_name[key] = mgr

    test_key = normalize_name(TEST_MANAGER["nom"])
    test_mgr = row_to_manager(TEST_MANAGER, is_test=True)
    if test_mgr:
        by_name[test_key] = test_mgr

    return by_name


def make_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PATCH"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def upsert_managers(url: str, key: str, managers: list[dict], session: requests.Session | None = None) -> None:
    endpoint = f"{url.rstrip('/')}/rest/v1/managers"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    http = session or requests
    batch_size = 50
    total_batches = (len(managers) + batch_size - 1) // batch_size
    for i in range(0, len(managers), batch_size):
        batch = managers[i : i + batch_size]
        batch_no = i // batch_size + 1
        print(f"  Lot {batch_no}/{total_batches} ({len(batch)} managers)...", flush=True)
        resp = http.post(
            endpoint,
            headers={**headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=batch,
            params={"on_conflict": "nom"},
            timeout=60,
        )
        if resp.status_code >= 400:
            # Fallback: delete all non-test and re-insert if unique index on nom fails
            raise RuntimeError(f"Upsert batch {i // batch_size + 1} failed ({resp.status_code}): {resp.text[:500]}")


def sync_via_upsert_loop(url: str, key: str, managers: list[dict], session: requests.Session) -> tuple[int, int]:
    """Insert or update each manager by normalized name."""
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    base = f"{url.rstrip('/')}/rest/v1/managers"
    inserted = updated = 0
    total = len(managers)

    for idx, mgr in enumerate(managers, 1):
        if idx == 1 or idx % 25 == 0 or idx == total:
            print(f"  Progression: {idx}/{total} — {mgr['nom'][:50]}", flush=True)

        norm = normalize_name(mgr["nom"])
        for attempt in range(4):
            try:
                search = session.get(
                    base,
                    headers=headers,
                    params={"select": "id,nom", "nom": f"ilike.{mgr['nom']}"},
                    timeout=45,
                )
                if search.status_code >= 400:
                    raise RuntimeError(f"Search failed: {search.text[:300]}")

                rows = search.json()
                existing = None
                for row in rows:
                    if normalize_name(row.get("nom", "")) == norm:
                        existing = row
                        break

                if existing:
                    patch = session.patch(
                        f"{base}?id=eq.{existing['id']}",
                        headers=headers,
                        json={k: v for k, v in mgr.items() if k != "nom"},
                        timeout=45,
                    )
                    if patch.status_code >= 400:
                        raise RuntimeError(f"Update {mgr['nom']}: {patch.text[:300]}")
                    updated += 1
                else:
                    post = session.post(base, headers=headers, json=mgr, timeout=45)
                    if post.status_code >= 400:
                        raise RuntimeError(f"Insert {mgr['nom']}: {post.text[:300]}")
                    inserted += 1
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                if attempt >= 3:
                    raise RuntimeError(f"{mgr['nom']}: {exc}") from exc
                wait = 2 ** attempt
                print(f"    Réessai dans {wait}s ({mgr['nom'][:30]})...", flush=True)
                time.sleep(wait)

        if idx % 10 == 0:
            time.sleep(0.15)

    return inserted, updated


def main() -> int:
    load_dotenv(ROOT / "boxing-center-bot" / ".env")
    load_dotenv(ROOT / ".env")

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis dans boxing-center-bot/.env")
        return 1

    managers_map = load_all_managers()
    managers = list(managers_map.values())
    print(f"Managers à synchroniser: {len(managers)}")
    print("Envoi vers Supabase (peut prendre 2 à 5 minutes, ne pas fermer la fenêtre)...", flush=True)

    session = make_session()
    try:
        try:
            print("Tentative envoi par lots rapides...", flush=True)
            upsert_managers(url, key, managers, session)
            print(f"Sync terminée — {len(managers)} managers synchronisés (mode lots)")
            return 0
        except RuntimeError as batch_err:
            print(f"Mode lots indisponible ({batch_err}). Passage en mode détaillé...", flush=True)
            inserted, updated = sync_via_upsert_loop(url, key, managers, session)
            print(f"Sync terminée — insérés: {inserted}, mis à jour: {updated}")
    except Exception as exc:
        print(f"Erreur sync: {exc}")
        print("Assurez-vous d'avoir appliqué supabase/migrations/001_boxing_center.sql")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
