#!/usr/bin/env python3
"""Détecte et corrige les téléphones promoteurs mal enrichis dans Supabase."""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
FUTUREBD = ROOT / "futurebd"

# Réutilise la logique managers
sys.path.insert(0, str(ROOT / "scripts"))
from fix_bad_manager_enrichment import (  # noqa: E402
    contact_type,
    normalize_phone_digits,
    patch_manager,
    validate_phone,
)

TABLE = "promoteurs"


def fetch_all_promoteurs(url: str, key: str) -> list[dict]:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    base = f"{url.rstrip('/')}/rest/v1/{TABLE}"
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


def patch_promoteur(url: str, key: str, promo_id: str, patch: dict) -> None:
    patch_manager(url, key, promo_id, patch)  # même API REST


def main() -> int:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "gestion-manager" / ".env.local")
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis", file=sys.stderr)
        return 1

    dry_run = "--dry-run" in sys.argv
    promoteurs = fetch_all_promoteurs(url, key)

    by_phone: dict[str, list[dict]] = defaultdict(list)
    for p in promoteurs:
        if p.get("is_test"):
            continue
        digits = normalize_phone_digits(p.get("telephone") or "")
        if digits:
            by_phone[digits].append(p)

    duplicate_phones = {ph: ps for ph, ps in by_phone.items() if len(ps) > 1}
    fixes: list[tuple[dict, dict, str]] = []

    for p in promoteurs:
        if p.get("is_test"):
            continue
        raw = p.get("telephone") or ""
        digits = normalize_phone_digits(raw)
        if not digits:
            continue

        new_digits = digits
        reason = ""

        if digits in duplicate_phones and len(duplicate_phones[digits]) > 1:
            new_digits = ""
            reason = f"telephone partage par {len(duplicate_phones[digits])} promoteurs"

        validated, val_err = validate_phone(new_digits or digits)
        if val_err:
            new_digits = ""
            reason = reason or val_err
        elif validated and validated != digits:
            new_digits = validated
            reason = reason or "format corrige"

        if new_digits == digits:
            continue

        has_phone = bool(new_digits)
        has_email = bool((p.get("email") or "").strip())
        patch = {
            "telephone": new_digits or None,
            "has_phone": has_phone,
            "has_email": has_email,
            "contact_type": contact_type(has_phone, has_email),
        }
        fixes.append((p, patch, reason or "correction"))

    print(f"Promoteurs analyses : {len(promoteurs)}")
    print(f"Telephones en double : {len(duplicate_phones)}")
    print(f"Corrections a appliquer : {len(fixes)}")
    print()

    for p, patch, reason in fixes[:30]:
        print(f"  - {p['nom'][:50]}")
        print(f"    {p.get('telephone')!r} -> {patch.get('telephone')!r} ({reason})")

    if dry_run:
        print("\n[dry-run] Aucune modification Supabase.")
        return 0

    ok = 0
    for p, patch, _ in fixes:
        patch_promoteur(url, key, p["id"], patch)
        ok += 1

    print(f"\nSupabase : {ok} promoteur(s) corrige(s).")
    report = FUTUREBD / "promoteurs_bad_phones_fixed.txt"
    FUTUREBD.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8") as f:
        f.write(f"Corrections: {len(fixes)}\n\n")
        for p, patch, reason in fixes:
            f.write(f"{p['nom']}\t{p.get('telephone')}\t{patch.get('telephone')}\t{reason}\n")
    print(f"Rapport : {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
