#!/usr/bin/env python3
"""Import boxeurs CSV into Supabase (table boxeurs). Template from sync_promoteurs_supabase.py."""

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
AMATEUR_CSV = FUTUREBD / "boxeurs_amateur.csv"
PRO_CSV = FUTUREBD / "boxeurs_pro.csv"


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


def row_to_boxeur(row: dict[str, str], categorie: str) -> dict | None:
    nom = pick(row, "nom", "Nom")
    if not nom:
        return None
    email = normalize_email(pick(row, "email", "Email"))
    telephone = normalize_phone(pick(row, "telephone", "Téléphone", "Telephone", "Tel"))
    adresse = pick(row, "adresse", "Organisation / Adresse", "organisation / adresse")
    localisation = pick(row, "localisation", "Localisation")
    url_profil = pick(row, "url_profil", "url profil", "profile_url")
    row_cat = pick(row, "categorie", "Catégorie", "Categorie").lower()
    if row_cat in ("amateur", "pro"):
        categorie = row_cat
    has_phone = bool(telephone)
    has_email = bool(email)
    return {
        "nom": nom,
        "categorie": categorie,
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


def load_all_boxeurs() -> dict[tuple[str, str], dict]:
    by_key: dict[tuple[str, str], dict] = {}

    sources = [(AMATEUR_CSV, "amateur"), (PRO_CSV, "pro")]
    for path, default_cat in sources:
        for row in read_csv_rows(path):
            boxeur = row_to_boxeur(row, default_cat)
            if not boxeur:
                continue
            key = (normalize_name(boxeur["nom"]), boxeur["categorie"])
            if key in by_key:
                existing = by_key[key]
                for field in ("email", "telephone", "adresse", "localisation", "url_profil"):
                    if not existing.get(field) and boxeur.get(field):
                        existing[field] = boxeur[field]
                existing["has_phone"] = bool(existing.get("telephone"))
                existing["has_email"] = bool(existing.get("email"))
                existing["contact_type"] = contact_type(existing["has_phone"], existing["has_email"])
            else:
                by_key[key] = boxeur

    return by_key


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


def sync_via_loop(url: str, key: str, boxeurs: list[dict], session: requests.Session) -> tuple[int, int]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    base = f"{url.rstrip('/')}/rest/v1/boxeurs"
    inserted = updated = 0
    total = len(boxeurs)

    for idx, boxeur in enumerate(boxeurs, 1):
        if idx == 1 or idx % 25 == 0 or idx == total:
            print(f"  Progression: {idx}/{total} — {boxeur['nom'][:50]} ({boxeur['categorie']})", flush=True)

        norm = normalize_name(boxeur["nom"])
        for attempt in range(4):
            try:
                search = session.get(
                    base,
                    headers=headers,
                    params={
                        "select": "id,nom,categorie",
                        "nom": f"ilike.{boxeur['nom']}",
                        "categorie": f"eq.{boxeur['categorie']}",
                    },
                    timeout=45,
                )
                if search.status_code >= 400:
                    raise RuntimeError(f"Search failed: {search.text[:300]}")

                rows = search.json()
                existing = None
                for row in rows:
                    if normalize_name(row.get("nom", "")) == norm and row.get("categorie") == boxeur["categorie"]:
                        existing = row
                        break

                if existing:
                    resp = session.patch(
                        f"{base}?id=eq.{existing['id']}",
                        headers=headers,
                        json=boxeur,
                        timeout=45,
                    )
                    if resp.status_code >= 400:
                        raise RuntimeError(f"Update failed: {resp.text[:300]}")
                    updated += 1
                else:
                    resp = session.post(base, headers=headers, json=boxeur, timeout=45)
                    if resp.status_code >= 400:
                        raise RuntimeError(f"Insert failed: {resp.text[:300]}")
                    inserted += 1
                break
            except Exception as exc:
                if attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
                print(f"    retry {attempt + 1}: {exc}", flush=True)

    return inserted, updated


def main() -> int:
    load_dotenv(ROOT / "boxing-center-bot" / ".env")
    load_dotenv(ROOT / ".env")

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis")
        return 1

    boxeurs_map = load_all_boxeurs()
    boxeurs = list(boxeurs_map.values())
    if not boxeurs:
        print("Aucun boxeur à importer — placez les CSV dans futurebd/")
        return 0

    print(f"Import de {len(boxeurs)} boxeur(s)...")
    session = make_session()
    inserted, updated = sync_via_loop(url, key, boxeurs, session)
    print(f"[ok] {inserted} inséré(s), {updated} mis à jour")
    return 0


if __name__ == "__main__":
    sys.exit(main())
