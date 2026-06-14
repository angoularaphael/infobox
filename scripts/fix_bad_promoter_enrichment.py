#!/usr/bin/env python3
"""Détecte et corrige téléphones / e-mails promoteurs mal enrichis dans Supabase."""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
FUTUREBD = ROOT / "futurebd"

sys.path.insert(0, str(ROOT / "scripts"))
from contact_validation import (  # noqa: E402
    normalize_email,
    normalize_phone_digits,
    validate_email,
    validate_phone,
)
from fix_bad_manager_enrichment import contact_type  # noqa: E402

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
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = requests.patch(
        f"{url.rstrip('/')}/rest/v1/{TABLE}?id=eq.{promo_id}",
        headers=headers,
        json=patch,
        timeout=45,
    )
    if resp.status_code >= 400:
        raise RuntimeError(resp.text[:400])


def build_contact_patch(promo: dict, *, telephone: str | None, email: str | None) -> dict:
    has_phone = bool(telephone)
    has_email = bool(email)
    return {
        "telephone": telephone or None,
        "email": email or None,
        "has_phone": has_phone,
        "has_email": has_email,
        "contact_type": contact_type(has_phone, has_email),
    }


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
    live = [p for p in promoteurs if not p.get("is_test")]

    by_phone: dict[str, list[dict]] = defaultdict(list)
    by_email: dict[str, list[dict]] = defaultdict(list)
    for p in live:
        digits = normalize_phone_digits(p.get("telephone") or "")
        if digits:
            by_phone[digits].append(p)
        email = normalize_email(p.get("email") or "")
        if email:
            by_email[email].append(p)

    duplicate_phones = {ph: ps for ph, ps in by_phone.items() if len(ps) > 1}
    duplicate_emails = {em: ps for em, ps in by_email.items() if len(ps) > 1}

    fixes: list[tuple[dict, dict, str]] = []
    pending: dict[str, dict] = {}

    def queue_fix(promo: dict, patch: dict, reason: str) -> None:
        promo_id = promo["id"]
        merged = pending.setdefault(promo_id, {"promo": promo, "patch": {}, "reasons": []})
        merged["patch"].update(patch)
        merged["reasons"].append(reason)

    for p in live:
        raw_phone = p.get("telephone") or ""
        digits = normalize_phone_digits(raw_phone)
        new_phone = digits
        phone_reason = ""

        if digits:
            if digits in duplicate_phones and len(duplicate_phones[digits]) > 1:
                new_phone = ""
                phone_reason = f"telephone partage par {len(duplicate_phones[digits])} promoteurs"
            else:
                validated, val_err = validate_phone(digits)
                if val_err:
                    new_phone = ""
                    phone_reason = val_err
                else:
                    new_phone = validated or ""

            if new_phone != digits:
                queue_fix(
                    p,
                    build_contact_patch(
                        p,
                        telephone=new_phone or None,
                        email=normalize_email(p.get("email") or "") or None,
                    ),
                    phone_reason or "correction telephone",
                )

        raw_email = normalize_email(p.get("email") or "")
        new_email = raw_email
        email_reason = ""

        if raw_email:
            if raw_email in duplicate_emails and len(duplicate_emails[raw_email]) > 1:
                new_email = ""
                email_reason = f"email partage par {len(duplicate_emails[raw_email])} promoteurs"

            validated_email, email_err = validate_email(new_email or raw_email)
            if email_err:
                new_email = ""
                email_reason = email_reason or email_err
            elif validated_email:
                new_email = validated_email

            if new_email != raw_email:
                pending_patch = pending.get(p["id"], {}).get("patch", {})
                if "telephone" in pending_patch:
                    current_phone = pending_patch["telephone"]
                else:
                    current_phone = digits or None
                queue_fix(
                    p,
                    build_contact_patch(p, telephone=current_phone, email=new_email or None),
                    email_reason or "correction email",
                )

    for item in pending.values():
        reasons = "; ".join(dict.fromkeys(item["reasons"]))
        fixes.append((item["promo"], item["patch"], reasons))

    print(f"Promoteurs analyses : {len(promoteurs)}")
    print(f"Telephones en double : {len(duplicate_phones)}")
    print(f"Emails en double : {len(duplicate_emails)}")
    print(f"Corrections a appliquer : {len(fixes)}")
    print()

    for p, patch, reason in fixes[:40]:
        print(f"  - {p['nom'][:50]}")
        if "telephone" in patch:
            print(f"    tel {p.get('telephone')!r} -> {patch.get('telephone')!r}")
        if "email" in patch:
            print(f"    email {p.get('email')!r} -> {patch.get('email')!r}")
        print(f"    ({reason})")
    if len(fixes) > 40:
        print(f"  … et {len(fixes) - 40} autres")

    if dry_run:
        print("\n[dry-run] Aucune modification Supabase.")
        return 0

    ok = 0
    for p, patch, _ in fixes:
        patch_promoteur(url, key, p["id"], patch)
        ok += 1
        if ok % 25 == 0:
            print(f"  {ok}/{len(fixes)} mis a jour…", flush=True)

    print(f"\nSupabase : {ok} promoteur(s) corrige(s).")
    report = FUTUREBD / "promoteurs_bad_contacts_fixed.txt"
    FUTUREBD.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8") as f:
        f.write(f"Corrections: {len(fixes)}\n\n")
        for p, patch, reason in fixes:
            f.write(
                f"{p['nom']}\t{p.get('telephone')}\t{patch.get('telephone')}\t"
                f"{p.get('email')}\t{patch.get('email')}\t{reason}\n"
            )
    print(f"Rapport : {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
