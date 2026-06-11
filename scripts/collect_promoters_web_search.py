#!/usr/bin/env python3
"""Collecte noms de promoteurs via recherche web (repli si BoxRec bloque)."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.enrich import _search_results  # noqa: E402

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

BOXREC_PROFILE_RE = re.compile(
    r"https?://(?:www\.)?boxrec\.com/en/([a-z0-9_-]+)/(\d+)",
    re.I,
)
SKIP_NAME_RE = re.compile(
    r"^(boxrec|boxing|promoter|promoters|people|locations|login|search|home|wiki)$",
    re.I,
)


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
            label = match.group(1).replace("_", " ").strip()
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


def clean_name(raw: str) -> str:
    text = unquote((raw or "").strip())
    text = re.sub(r"\s+", " ", text)
    for sep in (" | ", " - ", " – ", " — ", " :: ", ":"):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
    text = re.sub(r"\b(BoxRec|boxing promoter|promoter)\b.*$", "", text, flags=re.I).strip()
    if len(text) < 3 or len(text) > 80:
        return ""
    if SKIP_NAME_RE.match(text):
        return ""
    if text.isdigit():
        return ""
    return text


def name_from_boxrec_slug(slug: str) -> str:
    return clean_name(slug.replace("-", " ").title())


def extract_from_hit(hit: dict[str, str], country: str) -> dict[str, str] | None:
    href = hit.get("href", "")
    title = hit.get("title", "")
    body = hit.get("body", "")

    profile_url = ""
    nom = ""
    m = BOXREC_PROFILE_RE.search(href)
    if m:
        profile_url = m.group(0)
        nom = name_from_boxrec_slug(m.group(1))
    if not nom:
        nom = clean_name(title)
    if not nom:
        for token in re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", body):
            candidate = clean_name(token)
            if candidate:
                nom = candidate
                break
    if not nom:
        return None

    localisation = ""
    loc_match = re.search(r"\b(in|from|based in)\s+([A-Za-z][A-Za-z\s]{2,40})", body, re.I)
    if loc_match:
        localisation = loc_match.group(2).strip()

    return {
        "nom": nom,
        "email": "",
        "telephone": "",
        "adresse": "",
        "role": "promoter",
        "pays_recherche": country,
        "localisation": localisation,
        "url_profil": profile_url,
    }


def search_queries(country: str) -> list[str]:
    return [
        f'site:boxrec.com promoter {country}',
        f'boxing promoters {country} list',
        f'"{country}" boxing promoter contact',
        f'professional boxing promoter {country}',
    ]


def collect_country(
    country: str,
    *,
    seen: set[str],
    all_rows: list[dict[str, str]],
    delay: float,
    deadline: float,
) -> int:
    added = 0
    for query in search_queries(country):
        if time.time() >= deadline:
            break
        for hit in _search_results(query, max_results=10):
            if time.time() >= deadline:
                break
            row = extract_from_hit(hit, country)
            if not row:
                continue
            key = (row["url_profil"] or row["nom"]).casefold()
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(row)
            added += 1
        time.sleep(delay)
    if added:
        print(f"  [{country}] +{added} via web", flush=True)
    return added


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Collecte promoteurs via DuckDuckGo.")
    parser.add_argument("--max-minutes", type=float, default=15.0)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--countries", nargs="*", help="Pays explicites")
    args = parser.parse_args()

    FUTUREBD.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + max(1.0, args.max_minutes) * 60.0
    countries = ordered_countries(args.countries)
    if len(countries) > 25:
        countries = countries[:25]

    seen: set[str] = set()
    all_rows: list[dict[str, str]] = []

    print(
        f"Collecte web promoteurs — {len(countries)} pays, budget {args.max_minutes:.0f} min",
        flush=True,
    )

    for country in countries:
        if time.time() >= deadline:
            print("Budget temps épuisé.", flush=True)
            break
        print(f"Pays : {country}", flush=True)
        collect_country(
            country,
            seen=seen,
            all_rows=all_rows,
            delay=args.delay,
            deadline=deadline,
        )
        if all_rows:
            by_country = [r for r in all_rows if r["pays_recherche"] == country]
            if by_country:
                out = FUTUREBD / f"boxrec_promoter_{safe_filename(country)}.csv"
                write_csv(out, by_country)

    if not all_rows:
        print("Aucun promoteur collecté via web.", file=sys.stderr)
        return 1

    write_csv(RAW_LIST, all_rows)
    print(f"Total unique : {len(all_rows)} — {RAW_LIST}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
