#!/usr/bin/env python3
"""Collecte promoteurs BoxRec (pages liste, sans login ni profils).

Écrit futurebd/boxrec_promoter_<pays>.csv et futurebd/promoteurs_liste_brute.csv.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.boxrec_client import BoxRecClient, BoxRecError  # noqa: E402

FUTUREBD = ROOT / "futurebd"
ZIP_PATH = ROOT / "futurebd.zip"
RAW_LIST = FUTUREBD / "promoteurs_liste_brute.csv"

PRIORITY_COUNTRIES = (
    "United Kingdom",
    "United States",
    "Mexico",
    "Germany",
    "France",
    "Spain",
    "Italy",
    "Canada",
    "Australia",
    "Ireland",
    "Philippines",
    "Japan",
    "South Africa",
    "Argentina",
    "Brazil",
)

FIELDS = (
    "nom",
    "email",
    "telephone",
    "adresse",
    "role",
    "pays_recherche",
    "localisation",
    "url_profil",
)


def country_label_from_zip_name(name: str) -> str:
    return name.replace("_", " ").strip()


def countries_from_zip() -> list[str]:
    if not ZIP_PATH.is_file():
        return []
    pattern = re.compile(r"futurebd/boxrec_manager_(.+)\.csv$", re.I)
    labels: list[str] = []
    seen: set[str] = set()
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for entry in zf.namelist():
            match = pattern.match(entry.replace("\\", "/"))
            if not match:
                continue
            label = country_label_from_zip_name(match.group(1))
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            labels.append(label)
    return sorted(labels, key=str.casefold)


def ordered_countries(extra: list[str] | None = None) -> list[str]:
    base = extra or countries_from_zip()
    if not base:
        base = list(PRIORITY_COUNTRIES)
    ordered: list[str] = []
    seen: set[str] = set()
    for label in (*PRIORITY_COUNTRIES, *base):
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(label)
    return ordered


def person_to_row(person: dict[str, Any]) -> dict[str, str]:
    return {
        "nom": (person.get("name") or "").strip(),
        "email": (person.get("email") or "").strip(),
        "telephone": (person.get("phone") or "").strip(),
        "adresse": (person.get("address") or "").strip(),
        "role": person.get("role") or "promoter",
        "pays_recherche": (person.get("search_country") or "").strip(),
        "localisation": (person.get("location") or "").strip(),
        "url_profil": (person.get("profile_url") or "").strip(),
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        handle.write("sep=;\n")
        writer = csv.writer(handle, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writerow(FIELDS)
        for row in rows:
            writer.writerow([row.get(field, "") for field in FIELDS])


def safe_filename(label: str) -> str:
    return re.sub(r"[^\w\-]+", "_", label.strip()).strip("_") or "Unknown"


def scrape_country(
    client: BoxRecClient,
    country: str,
    *,
    max_pages: int | None,
    deadline: float,
    seen_urls: set[str],
    all_rows: list[dict[str, str]],
) -> int:
    client.loc_txt = country
    added = 0
    try:
        people = client.scrape_role(
            "promoter",
            max_pages=max_pages,
            fetch_contacts=False,
        )
    except BoxRecError as exc:
        print(f"  [{country}] ignoré : {exc}", flush=True)
        return 0

    country_rows: list[dict[str, str]] = []
    for person in people:
        if time.time() >= deadline:
            break
        row = person_to_row(person)
        if not row["nom"]:
            continue
        key = row["url_profil"] or row["nom"].casefold()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        if not row["pays_recherche"]:
            row["pays_recherche"] = country
        country_rows.append(row)
        all_rows.append(row)
        added += 1

    if country_rows:
        out = FUTUREBD / f"boxrec_promoter_{safe_filename(country)}.csv"
        write_csv(out, country_rows)
        print(f"  [{country}] +{len(country_rows)} -> {out.name}", flush=True)
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape promoteurs BoxRec (listes sans login).")
    parser.add_argument("--max-minutes", type=float, default=12.0, help="Budget temps scrape")
    parser.add_argument("--max-pages", type=int, default=3, help="Pages liste max par pays")
    parser.add_argument("--delay", type=float, default=1.2, help="Délai entre requêtes")
    parser.add_argument("--countries", nargs="*", help="Pays explicites (sinon zip + priorité)")
    args = parser.parse_args()

    FUTUREBD.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + max(1.0, args.max_minutes) * 60.0
    countries = ordered_countries(args.countries)

    client = BoxRecClient(delay=args.delay)
    client.username = ""
    client.password = ""

    seen_urls: set[str] = set()
    all_rows: list[dict[str, str]] = []
    total_added = 0

    print(
        f"Scrape promoteurs — {len(countries)} pays, max {args.max_pages} pages/pays, "
        f"budget {args.max_minutes:.0f} min",
        flush=True,
    )

    for country in countries:
        if time.time() >= deadline:
            print("Budget temps scrape épuisé.", flush=True)
            break
        print(f"Pays : {country}", flush=True)
        total_added += scrape_country(
            client,
            country,
            max_pages=args.max_pages,
            deadline=deadline,
            seen_urls=seen_urls,
            all_rows=all_rows,
        )

    if all_rows:
        write_csv(RAW_LIST, all_rows)
        print(f"Total unique : {len(all_rows)} — {RAW_LIST}", flush=True)
    else:
        print("Aucun promoteur collecté.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
