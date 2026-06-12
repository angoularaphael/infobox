#!/usr/bin/env python3
"""Détecte et corrige les téléphones managers mal enrichis, puis sync Supabase."""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
FUTUREBD = ROOT / "futurebd"
ENRICHIS_CSV = FUTUREBD / "managers_enrichis.csv"
CONTACTS_CSV = FUTUREBD / "managers_contacts_sans_doublons.csv"


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def normalize_phone_digits(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def extract_phone_from_field(value: str) -> str:
    """Prend le premier numéro quand plusieurs sont collés (ex. +86 … ; +86 …)."""
    raw = (value or "").strip()
    if not raw:
        return ""
    for part in re.split(r"[;/|]", raw):
        part = part.strip()
        if not part:
            continue
        digits = normalize_phone_digits(part)
        if digits:
            return digits
    return ""


def fix_doubled_phone(digits: str) -> str | None:
    """Ex. 86150046847118615004684711 → 8615004684711"""
    if len(digits) < 16 or len(digits) % 2 != 0:
        return None
    half = len(digits) // 2
    if digits[:half] == digits[half:]:
        return digits[:half]
    return None


def validate_phone(digits: str) -> tuple[str | None, str | None]:
    """Retourne (téléphone valide, erreur). Erreur None = OK."""
    if not digits:
        return None, "vide"

    doubled = fix_doubled_phone(digits)
    if doubled:
        digits = doubled

    if len(digits) > 15:
        return None, f"trop_long ({len(digits)})"

    if len(digits) < 8:
        return None, f"trop_court ({len(digits)})"

    return digits, None


def contact_type(has_phone: bool, has_email: bool) -> str:
    if has_phone and has_email:
        return "both"
    if has_phone:
        return "phone_only"
    if has_email:
        return "email_only"
    return "none"


def fetch_all_managers(url: str, key: str) -> list[dict]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    base = f"{url.rstrip('/')}/rest/v1/managers"
    rows: list[dict] = []
    offset = 0
    page = 1000
    while True:
        resp = requests.get(
            base,
            headers=headers,
            params={
                "select": "id,nom,email,telephone,localisation,adresse,url_profil,is_test",
                "order": "nom.asc",
                "offset": offset,
                "limit": page,
            },
            timeout=60,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return rows


def patch_manager(url: str, key: str, manager_id: str, patch: dict) -> None:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = requests.patch(
        f"{url.rstrip('/')}/rest/v1/managers?id=eq.{manager_id}",
        headers=headers,
        json=patch,
        timeout=45,
    )
    if resp.status_code >= 400:
        raise RuntimeError(resp.text[:400])


def load_trusted_phones_from_contacts() -> dict[str, str]:
    """Nom normalisé → téléphone de la base contacts (avant enrichissement web)."""
    trusted: dict[str, str] = {}
    if not CONTACTS_CSV.exists():
        return trusted
    import csv

    raw = CONTACTS_CSV.read_bytes()
    text = raw.decode("utf-8-sig") if not raw.startswith(b"\xff") else raw.decode("utf-16")
    lines = text.splitlines()
    start = 1 if lines and lines[0].lower().startswith("sep=") else 0
    for row in csv.DictReader(lines[start:], delimiter=";"):
        nom = (row.get("nom") or row.get("Nom") or "").strip()
        tel = extract_phone_from_field(row.get("telephone") or row.get("Téléphone") or "")
        valid, _err = validate_phone(tel)
        if nom and valid:
            trusted[normalize_name(nom)] = valid
    return trusted


def main() -> int:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "gestion-manager" / ".env.local")
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis dans .env", file=sys.stderr)
        return 1

    dry_run = "--dry-run" in sys.argv
    managers = fetch_all_managers(url, key)
    trusted = load_trusted_phones_from_contacts()

    by_phone: dict[str, list[dict]] = defaultdict(list)
    for m in managers:
        if m.get("is_test"):
            continue
        digits = normalize_phone_digits(m.get("telephone") or "")
        if digits:
            by_phone[digits].append(m)

    duplicate_phones = {p: ms for p, ms in by_phone.items() if len(ms) > 1}

    fixes: list[tuple[dict, dict, str]] = []

    for m in managers:
        if m.get("is_test"):
            continue
        nom = m.get("nom") or ""
        key_name = normalize_name(nom)
        raw = m.get("telephone") or ""
        digits = normalize_phone_digits(raw)
        if not digits:
            continue

        new_digits = digits
        reason = ""

        # Source de vérité : contacts d'origine (uniquement si numéro fiable)
        trusted_digits = trusted.get(key_name)
        if trusted_digits:
            if digits != trusted_digits:
                new_digits = trusted_digits
                reason = "restauré depuis contacts"
            else:
                continue

        if digits in duplicate_phones and len(duplicate_phones[digits]) > 1:
            new_digits = ""
            reason = f"téléphone partagé par {len(duplicate_phones[digits])} managers"

        validated, val_err = validate_phone(new_digits or digits)
        if val_err:
            new_digits = ""
            reason = reason or val_err
        elif validated and validated != digits:
            new_digits = validated
            reason = reason or "format corrigé"

        if new_digits == digits:
            continue

        has_phone = bool(new_digits)
        has_email = bool((m.get("email") or "").strip())
        patch = {
            "telephone": new_digits or None,
            "has_phone": has_phone,
            "has_email": has_email,
            "contact_type": contact_type(has_phone, has_email),
        }
        fixes.append((m, patch, reason or "correction"))

    print(f"Managers analysés : {len(managers)}")
    print(f"Téléphones en double : {len(duplicate_phones)}")
    print(f"Corrections à appliquer : {len(fixes)}")
    print()

    for m, patch, reason in fixes[:30]:
        print(f"  - {m['nom'][:50]}")
        print(f"    {m.get('telephone')!r} -> {patch.get('telephone')!r} ({reason})")
    if len(fixes) > 30:
        print(f"  … et {len(fixes) - 30} autres")

    if dry_run:
        print("\n[dry-run] Aucune modification Supabase.")
        return 0

    ok = 0
    for m, patch, _reason in fixes:
        patch_manager(url, key, m["id"], patch)
        ok += 1
        if ok % 25 == 0:
            print(f"  {ok}/{len(fixes)} mis à jour…", flush=True)

    print(f"\nSupabase : {ok} manager(s) corrigé(s).")

    report = FUTUREBD / "managers_bad_phones_fixed.txt"
    FUTUREBD.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8") as f:
        f.write(f"Corrections: {len(fixes)}\n\n")
        for m, patch, reason in fixes:
            f.write(f"{m['nom']}\t{m.get('telephone')}\t{patch.get('telephone')}\t{reason}\n")
    print(f"Rapport : {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
