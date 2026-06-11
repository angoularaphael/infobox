#!/usr/bin/env python3
"""Import promoteurs CSV into Supabase (table promoteurs)."""

from __future__ import annotations

import csv
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
FUTUREBD = ROOT / "futurebd"
PROMOTEUR_CSV = FUTUREBD / "promoteur.csv"
RAW_LIST_CSV = FUTUREBD / "promoteurs_liste_brute.csv"


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


def row_to_promoteur(row: dict[str, str]) -> dict | None:
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
        "is_test": False,
    }


def load_all_promoteurs() -> dict[str, dict]:
    by_name: dict[str, dict] = {}

    sources = [PROMOTEUR_CSV]
    if RAW_LIST_CSV.exists() and RAW_LIST_CSV != PROMOTEUR_CSV:
        sources.append(RAW_LIST_CSV)

    for path in sources:
        for row in read_csv_rows(path):
            promo = row_to_promoteur(row)
            if not promo:
                continue
            key = normalize_name(promo["nom"])
            if key in by_name:
                existing = by_name[key]
                for field in ("email", "telephone", "adresse", "localisation", "url_profil"):
                    if not existing.get(field) and promo.get(field):
                        existing[field] = promo[field]
                existing["has_phone"] = bool(existing.get("telephone"))
                existing["has_email"] = bool(existing.get("email"))
                existing["contact_type"] = contact_type(existing["has_phone"], existing["has_email"])
            else:
                by_name[key] = promo

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


def upsert_promoteurs(url: str, key: str, promoteurs: list[dict], session: requests.Session) -> None:
    endpoint = f"{url.rstrip('/')}/rest/v1/promoteurs"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    batch_size = 50
    total_batches = (len(promoteurs) + batch_size - 1) // batch_size
    for i in range(0, len(promoteurs), batch_size):
        batch = promoteurs[i : i + batch_size]
        batch_no = i // batch_size + 1
        print(f"  Lot {batch_no}/{total_batches} ({len(batch)} promoteurs)...", flush=True)
        resp = session.post(
            endpoint,
            headers=headers,
            json=batch,
            params={"on_conflict": "nom"},
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Upsert batch {batch_no} failed ({resp.status_code}): {resp.text[:500]}")


def sync_via_loop(url: str, key: str, promoteurs: list[dict], session: requests.Session) -> tuple[int, int]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    base = f"{url.rstrip('/')}/rest/v1/promoteurs"
    inserted = updated = 0
    total = len(promoteurs)

    for idx, promo in enumerate(promoteurs, 1):
        if idx == 1 or idx % 25 == 0 or idx == total:
            print(f"  Progression: {idx}/{total} — {promo['nom'][:50]}", flush=True)

        norm = normalize_name(promo["nom"])
        for attempt in range(4):
            try:
                search = session.get(
                    base,
                    headers=headers,
                    params={"select": "id,nom", "nom": f"ilike.{promo['nom']}"},
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
                        json={k: v for k, v in promo.items() if k != "nom"},
                        timeout=45,
                    )
                    if patch.status_code >= 400:
                        raise RuntimeError(f"Update {promo['nom']}: {patch.text[:300]}")
                    updated += 1
                else:
                    post = session.post(base, headers=headers, json=promo, timeout=45)
                    if post.status_code >= 400:
                        raise RuntimeError(f"Insert {promo['nom']}: {post.text[:300]}")
                    inserted += 1
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                if attempt >= 3:
                    raise RuntimeError(f"{promo['nom']}: {exc}") from exc
                wait = 2**attempt
                print(f"    Réessai dans {wait}s ({promo['nom'][:30]})...", flush=True)
                time.sleep(wait)

        if idx % 10 == 0:
            time.sleep(0.15)

    return inserted, updated


def verify_table(url: str, key: str) -> bool:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    resp = requests.get(
        f"{url.rstrip('/')}/rest/v1/promoteurs",
        headers=headers,
        params={"select": "id", "limit": "1"},
        timeout=30,
    )
    return resp.status_code == 200


def main() -> int:
    load_dotenv(ROOT / "boxing-center-bot" / ".env")
    load_dotenv(ROOT / ".env")

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis dans .env")
        return 1

    if not PROMOTEUR_CSV.exists() and not RAW_LIST_CSV.exists():
        print(f"Aucun CSV promoteur ({PROMOTEUR_CSV})")
        return 1

    if not verify_table(url, key):
        print("Table promoteurs inaccessible. Appliquez supabase/migrations/005_promoteurs.sql")
        return 1

    promoteurs_map = load_all_promoteurs()
    promoteurs = list(promoteurs_map.values())
    with_contact = sum(1 for p in promoteurs if p["has_email"] or p["has_phone"])
    print(f"Promoteurs à synchroniser: {len(promoteurs)} (avec contact: {with_contact})")

    session = make_session()
    try:
        try:
            print("Tentative envoi par lots...", flush=True)
            upsert_promoteurs(url, key, promoteurs, session)
            print(f"Sync terminée — {len(promoteurs)} promoteurs synchronisés (mode lots)")
            return 0
        except RuntimeError as batch_err:
            print(f"Mode lots indisponible ({batch_err}). Passage en mode détaillé...", flush=True)
            inserted, updated = sync_via_loop(url, key, promoteurs, session)
            print(f"Sync terminée — insérés: {inserted}, mis à jour: {updated}")
    except Exception as exc:
        print(f"Erreur sync: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
