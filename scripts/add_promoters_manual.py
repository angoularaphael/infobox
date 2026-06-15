#!/usr/bin/env python3
"""Insert manual promoter list into Supabase (skip duplicates by normalized name or phone)."""

from __future__ import annotations

import os
import sys
import unicodedata
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from contact_validation import normalize_phone_digits, validate_phone  # noqa: E402
from phone_country import country_from_phone  # noqa: E402
from sync_promoteurs_supabase import contact_type  # noqa: E402

PROMOTERS_RAW = """
Ali promoteur Boxe Valencia Espagne,34687075304
Baris Tunal Erdogan Promoteur,33749113057
Celaya Promoteur Boxe Espagne Galicia,34639346038
Julio Cesar Archibold Promoteur Boxe Panama,50765924064
PROMOTOR SENTO ESPAGNA,34676066350
Promoteur Omir Rodrigues Espagne,34675506341
Daniel NADER PROMOTEUR AUTRICHE,4366488315818
Adrien Promoteur Boxe Allemagne,33618290526
Promoteur Boxe Rufino Angulo,33680848761
Davide NICOTRA PROMOTEUR BOXE,33659293960
Promoteur Portugais BOXE,351966031154
Promoteur boxe Allemagne Ben Bakic,491632575694
Promoteur Boxe Pays Bas,31650742010
Inigo Herbosa promoteur boxe Bilbao,34667855303
Promoteur Boxe Manager Viktar Biélorusse,37126889022
Bachir Promoteur Boxe,33676951378
Pavel Šour Promoteur Boxe,420725080433
Promoteur Alain Vinot Boxe,33620475683
Promoteur Boxe Allemagne CLAUSSEN,4943121070182
Promoteur Emil Pavel Pop Boxe Pro Espagne,34617897000
Promoteur Angleterre Chris Glover,17187814456
Lela PROMOTEUR BOXE PRO Présidente Fede Géorgie,995591552861
Promoteur Angleterre Steve Illis,447730712095
Promoteur boxe Italien,393395607745
Davide Giordano Promoteur BOXE MALTA,393240911042
Nicolas Promoteur Normandie,33610626814
PIETRO PROMOTEUR,33628694359
Promoteur Boxe Pro Biernacki Pologne,48693505162
12 ONZAS ACADEMY Promoteur Espagne Boxe,34663147737
Antonio Sanchez Promoteur,34667620200
Mykhailo Vasylenko Promoteur,380660913991
Nathalie promoteur boxe,33610242092
Frank Nicotra Boxe promoteur,33624800090
Pierre Demarteau promoteur,32493156093
""".strip()


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def parse_promoters() -> list[dict]:
    rows: list[dict] = []
    for line in PROMOTERS_RAW.splitlines():
        line = line.strip()
        if not line:
            continue
        nom, telephone = line.rsplit(",", 1)
        nom = nom.strip()
        digits = normalize_phone_digits(telephone)
        validated, err = validate_phone(digits)
        if err or not validated:
            raise ValueError(f"Téléphone invalide pour {nom!r}: {telephone!r} ({err})")
        pays = country_from_phone(validated)
        if not pays:
            raise ValueError(f"Indicatif inconnu pour {nom!r}: {validated}")
        rows.append(
            {
                "nom": nom,
                "telephone": validated,
                "localisation": pays,
                "email": None,
                "adresse": None,
                "url_profil": None,
                "has_phone": True,
                "has_email": False,
                "contact_type": contact_type(True, False),
                "is_test": False,
            }
        )
    return rows


def fetch_existing(url: str, key: str) -> tuple[set[str], set[str]]:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    base = f"{url.rstrip('/')}/rest/v1/promoteurs"
    names: set[str] = set()
    phones: set[str] = set()
    offset = 0
    while True:
        resp = requests.get(
            base,
            headers=headers,
            params={"select": "nom,telephone", "offset": offset, "limit": 1000},
            timeout=60,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for row in batch:
            names.add(normalize_name(row.get("nom") or ""))
            phone = normalize_phone_digits(row.get("telephone") or "")
            if phone:
                phones.add(phone)
        if len(batch) < 1000:
            break
        offset += 1000
    return names, phones


def insert_promoter(url: str, key: str, promo: dict) -> None:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = requests.post(f"{url.rstrip('/')}/rest/v1/promoteurs", headers=headers, json=promo, timeout=45)
    if resp.status_code >= 400:
        raise RuntimeError(f"Insert {promo['nom']}: {resp.text[:400]}")


def main() -> int:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "boxing-center-bot" / ".env")
    load_dotenv(ROOT / "gestion-manager" / ".env.local")

    url = os.environ.get("SUPABASE_URL", "").strip() or os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis", file=sys.stderr)
        return 1

    promoteurs = parse_promoters()
    existing_names, existing_phones = fetch_existing(url, key)

    added: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str]] = []

    for promo in promoteurs:
        norm_name = normalize_name(promo["nom"])
        phone = promo["telephone"]
        if norm_name in existing_names:
            skipped.append((promo["nom"], "nom en double"))
            continue
        if phone in existing_phones:
            skipped.append((promo["nom"], "téléphone en double"))
            continue
        insert_promoter(url, key, promo)
        existing_names.add(norm_name)
        existing_phones.add(phone)
        added.append((promo["nom"], phone, promo["localisation"]))
        print(f"+ {promo['nom']} -> {promo['localisation']} ({phone})")

    print(f"\nAjoutés: {len(added)}, ignorés: {len(skipped)}")
    for nom, reason in skipped:
        print(f"  skip {nom}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
