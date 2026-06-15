#!/usr/bin/env python3
"""Insert manual boxeur list into Supabase (skip duplicates by phone or nom+categorie)."""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from contact_validation import normalize_phone_digits, validate_phone  # noqa: E402
from phone_country import country_from_phone  # noqa: E402
from sync_boxeurs_supabase import contact_type  # noqa: E402

BOXEURS_RAW = """
Mouss Boxe Beziers 2025,33650046298
Kevin DISSAUX BOXE 2026,33688894410
Antoine MANGIN BOXEUR PRO MANGIN 70kgs,33636462227
Clement Oppenot Boxe Pro 92kgs,33763200692
Alexander Manager Boxeur Ukrainien,420777433373
Antonio Club Boxeo,34679075013
Boxe Boulin Peio,33618553618
Boxeo Unitres,33628647297
Jesus Président Fede Catalane de Boxe,34678494571
Jimmy Lalin Boxe Pro,33651103923
Ludo Matchmaker Boxe,33770127011
Ruben Contact boxe Pro Espagne,34696021757
Santiago EUSEBIO BOXE 53KGS,33627425093
Shalva Boxeur pro 78/ 80kgs Belgique,995598775534
Artem ARTAK BOXE ALLEMAGNE,33760901468
Karim Boxe ARGENTAN,33762099374
Damian ROSATI BOXEO ARGENTINE,5491163782977
Michel Solis Boxe Annecy,33769265343
Tony Boxeo Argentina,5491166310870
Jaouad BELMEHDI BOXE B,33617204518
Jean Marc BOXE PETIT BAR,33680748546
Christian MERLE ASM BOXE,33660283266
Claude FAURE BOXE,33688704420
Entraîneur Gianni CARULLO BOXE,33685856910
Hicham Ap VAUVERT BOXE,33664065272
Maxime BEAUSSIRE BOXE,33687617044
Mickael MATHIEU BOXE,33767910782
Rene Club PCN NICE BOXE,33771211195
Jauma PONS Barcelone BOXEO,34644673007
Herve organisateur Boxe Pro Bayonne,33665168587
Guito Boxe entraîneur Tahar Belkhir,33642795164
Joan Boxeo Benicarlo,34635337113
Javi Boxeo Bilbao,34696695715
Laurent Ammani Boxe Bordeaux,33661580033
Philippe Cazeau Boxe Bordeaux,33660224492
Sofiane club boxe Bordeaux,33760988986
Bruno Fede Andorrana Boxe,376356440
Cyril Joly Boxe,33634415952
Damien Lacoudray Boxe,33646045384
Houari Rocque Brune Boxe,33663266427
Jonathan Rodrigues Organisateur Gala de Boxe,33672565596
Mamadou Thiam Boxe,33621237646
Sofiane OUZANI Comite Boxe,33621162241
Tony Porto Boxe,351916277165
BERDIA Barcelona Boxeo,34640661783
Lorenzo Parra Boxeo,34662434450
Boxe Yoan Boyer,33781939376
CLUB Boxe Hacine CHERIFI,33611425009
Tanguy FARUGIA Boxe Elancourt,33663476626
Fede Catalana Boxeo Fortes Presi Fcb,34609704320
Entraîneur Boxeur Pro Grèce,306972028463
Antonio Riga Boxeo Las Palmas Gym,34638460650
Robert Boxe club Limoge,33607299356
Jose LINARES Club Boxe Nord Linares,352621715408
Toni Tiberi Boxe Lux,352691580803
Eric boxeur pro 80kgs Luxembourg,33771105818
Joseph Cardillo entraineur 92kgs Patrick MBIDA,33687800888
Dimitri SEKA BOXE MOULIN,33672888205
Antony SILVESTRI Boxe Marseille,33787159613
Christophe Canal Boxe Marseille,33634171654
Entraîneur M. LIETO Boxe Marseille,33621327304
Organisateur gala boxe Menton,33668693377
Kassim Bourai entraineur Michel Moreira,33646081957
Jules Boxe Nantes,33684877303
Thierry Primo Boxe Orléans,33645169524
Boxe Haroche Orta,33659254383
Dorian MAIDANA BOXEO PRO,34657212021
Jefferson VARGAS BOXE PRO,34624466447
Kevin GREENWOOD BOXE PRO,447840367211
Boxeur pro Serhat Parlak,491773968548
92kgs Boxe Rodolfo Valencia,34696130194
Jean Pierre Boxe Corse Ile Rousse,33603004088
Club Boxeo Santander,34665477876
Boxe Pézenas Stephane,33645700798
Boxeo Barcelona TOR4,34627791033
Julien DIMNA boxe pro Tarbes,33780561811
Ihor Morhun boxeur Ukraine,48575439667
Contact Boxeur Ukrainien,4917664171198
johns boxe auch,33675709667
Hamid Zaim Club de boxe,33621724545
Joseph GERMAIN BOXE Noisy le grand,33608059260
""".strip()

NAME_FIXES = {
    "entraineur": "entraîneur",
    "Entraineur": "Entraîneur",
    "Herve ": "Hervé ",
    "Rene ": "René ",
}


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def fix_name(nom: str) -> str:
    for old, new in NAME_FIXES.items():
        nom = nom.replace(old, new)
    return nom


def guess_categorie(nom: str) -> str:
    low = nom.lower()
    if re.search(r"\bpro\b", low) or re.search(r"\d+\s*kgs?", low):
        return "pro"
    return "amateur"


def parse_boxeurs() -> list[dict]:
    rows: list[dict] = []
    for line in BOXEURS_RAW.splitlines():
        line = line.strip()
        if not line:
            continue
        nom, telephone = line.rsplit(",", 1)
        nom = fix_name(nom.strip())
        digits = normalize_phone_digits(telephone)
        validated, err = validate_phone(digits)
        if err or not validated:
            raise ValueError(f"Téléphone invalide pour {nom!r}: {telephone!r} ({err})")
        pays = country_from_phone(validated)
        if not pays:
            raise ValueError(f"Indicatif inconnu pour {nom!r}: {validated}")
        categorie = guess_categorie(nom)
        rows.append(
            {
                "nom": nom,
                "categorie": categorie,
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


def fetch_existing(url: str, key: str) -> tuple[set[tuple[str, str]], set[str]]:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    base = f"{url.rstrip('/')}/rest/v1/boxeurs"
    keys: set[tuple[str, str]] = set()
    phones: set[str] = set()
    offset = 0
    while True:
        resp = requests.get(
            base,
            headers=headers,
            params={"select": "nom,categorie,telephone", "offset": offset, "limit": 1000},
            timeout=60,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for row in batch:
            keys.add((normalize_name(row.get("nom") or ""), row.get("categorie") or ""))
            phone = normalize_phone_digits(row.get("telephone") or "")
            if phone:
                phones.add(phone)
        if len(batch) < 1000:
            break
        offset += 1000
    return keys, phones


def insert_boxeur(url: str, key: str, boxeur: dict) -> None:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = requests.post(f"{url.rstrip('/')}/rest/v1/boxeurs", headers=headers, json=boxeur, timeout=45)
    if resp.status_code >= 400:
        raise RuntimeError(f"Insert {boxeur['nom']}: {resp.text[:400]}")


def main() -> int:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "boxing-center-bot" / ".env")
    load_dotenv(ROOT / "gestion-manager" / ".env.local")

    url = os.environ.get("SUPABASE_URL", "").strip() or os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis", file=sys.stderr)
        return 1

    boxeurs = parse_boxeurs()
    existing_keys, existing_phones = fetch_existing(url, key)

    added: list[tuple[str, str, str, str]] = []
    skipped: list[tuple[str, str]] = []

    for boxeur in boxeurs:
        norm_name = normalize_name(boxeur["nom"])
        key_tuple = (norm_name, boxeur["categorie"])
        phone = boxeur["telephone"]
        if phone in existing_phones:
            skipped.append((boxeur["nom"], "téléphone en double"))
            continue
        if key_tuple in existing_keys:
            skipped.append((boxeur["nom"], "nom+catégorie en double"))
            continue
        insert_boxeur(url, key, boxeur)
        existing_keys.add(key_tuple)
        existing_phones.add(phone)
        added.append((boxeur["nom"], boxeur["categorie"], phone, boxeur["localisation"]))
        print(f"+ [{boxeur['categorie']}] {boxeur['nom']} -> {boxeur['localisation']} ({phone})")

    by_country: dict[str, int] = {}
    for _, _, _, pays in added:
        by_country[pays] = by_country.get(pays, 0) + 1

    print(f"\nAjoutés: {len(added)}, ignorés: {len(skipped)}")
    if by_country:
        print("Par pays:")
        for pays, count in sorted(by_country.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {pays}: {count}")
    for nom, reason in skipped:
        print(f"  skip {nom}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
