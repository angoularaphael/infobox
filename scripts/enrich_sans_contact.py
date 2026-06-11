#!/usr/bin/env python3
"""Enrichit managers_sans_contact.csv via recherche web (DuckDuckGo).

Usage:
    python scripts/enrich_sans_contact.py              # tout le fichier
    python scripts/enrich_sans_contact.py --limit 10   # test sur 10 lignes
    python scripts/enrich_sans_contact.py --resume     # reprend le checkpoint

Sorties (dossier futurebd/) :
    managers_enrichis.csv          — tous les managers + contacts trouvés
    managers_enrichis_checkpoint.json — sauvegarde après chaque fiche
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.enrich import enrich_person  # noqa: E402

FUTUREBD = ROOT / "futurebd"
DEFAULT_INPUT = FUTUREBD / "managers_sans_contact.csv"
DEFAULT_OUTPUT = FUTUREBD / "managers_enrichis.csv"
DEFAULT_MD = FUTUREBD / "managers_enrichis.md"
CHECKPOINT = FUTUREBD / "managers_enrichis_checkpoint.json"

OUTPUT_FIELDS = (
    "nom",
    "email",
    "telephone",
    "adresse",
    "localisation",
    "url_profil",
    "email_source",
    "telephone_source",
    "enrichi",
)

SANS_CONTACT_FIELDS = (
    "nom",
    "adresse",
    "localisation",
    "url_profil",
)


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def read_text_lines(path: Path) -> list[str]:
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
    return text.splitlines(keepends=True)


def is_sep_line(line: str) -> bool:
    return line.strip().lower().lstrip("\ufeff").startswith("sep=")


def read_sans_contact_csv(path: Path) -> list[dict[str, str]]:
    lines = read_text_lines(path)
    if not lines:
        return []
    start = 0
    if lines and is_sep_line(lines[0]):
        start = 1
    reader = csv.DictReader(lines[start:], delimiter=";", quotechar='"')
    rows: list[dict[str, str]] = []
    for raw in reader:
        nom = (raw.get("Nom") or raw.get("nom") or "").strip()
        if not nom:
            continue
        rows.append(
            {
                "nom": nom,
                "adresse": (raw.get("Organisation / Adresse") or raw.get("adresse") or "").strip(),
                "localisation": (raw.get("Localisation") or raw.get("localisation") or "").strip(),
                "url_profil": (raw.get("url_profil") or raw.get("profile_url") or "").strip(),
            }
        )
    return rows


def person_from_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "name": row["nom"],
        "email": "",
        "phone": "",
        "role": "manager",
        "location": row["localisation"],
        "address": row["adresse"],
        "profile_url": row.get("url_profil", ""),
    }


def result_from_person(row: dict[str, str], person: dict[str, Any]) -> dict[str, str]:
    email = (person.get("email") or "").strip()
    phone = (person.get("phone") or "").strip()
    return {
        "nom": row["nom"],
        "email": email,
        "telephone": phone,
        "adresse": row["adresse"],
        "localisation": row["localisation"],
        "url_profil": row.get("url_profil") or person.get("profile_url", ""),
        "email_source": person.get("email_source", ""),
        "telephone_source": person.get("phone_source", ""),
        "enrichi": "oui" if email or phone else "non",
    }


def load_checkpoint() -> dict[str, dict[str, str]]:
    if not CHECKPOINT.is_file():
        return {}
    try:
        data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        return {normalize_name(r["nom"]): r for r in data if r.get("nom")}
    except (json.JSONDecodeError, KeyError):
        return {}


def save_checkpoint(results: list[dict[str, str]]) -> None:
    FUTUREBD.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_results_csv(results: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        handle.write("sep=;\n")
        writer = csv.writer(handle, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writerow(OUTPUT_FIELDS)
        for row in results:
            writer.writerow([row.get(field, "") for field in OUTPUT_FIELDS])


def enrich_rows(
    rows: list[dict[str, str]],
    *,
    delay: float,
    on_progress=None,
) -> list[dict[str, str]]:
    checkpoint = load_checkpoint()
    results: list[dict[str, str]] = []
    total = len(rows)

    for i, row in enumerate(rows, start=1):
        key = normalize_name(row["nom"])
        if key in checkpoint:
            result = checkpoint[key]
            results.append(result)
            if on_progress:
                on_progress(i, total, result)
            continue

        person = person_from_row(row)
        enrich_person(person, delay=delay)
        result = result_from_person(row, person)
        results.append(result)
        save_checkpoint(results)
        if on_progress:
            on_progress(i, total, result)

    return results


def print_summary(results: list[dict[str, str]]) -> None:
    found = sum(1 for r in results if r["enrichi"] == "oui")
    with_email = sum(1 for r in results if r["email"])
    with_phone = sum(1 for r in results if r["telephone"])
    print(f"Total traité : {len(results)}")
    print(f"Avec contact trouvé : {found}")
    print(f"  — e-mail : {with_email}")
    print(f"  — téléphone : {with_phone}")
    print(f"Toujours sans contact : {len(results) - found}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrichit managers_sans_contact.csv via le web.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"CSV source (défaut : {DEFAULT_INPUT.name})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"CSV de sortie (défaut : {DEFAULT_OUTPUT.name})",
    )
    parser.add_argument("--limit", type=int, default=0, help="Nombre max de fiches (0 = tout)")
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Délai entre requêtes DuckDuckGo (défaut : ENRICH_DELAY_SECONDS ou 2.5)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Ignore le checkpoint et recommence à zéro",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Fichier introuvable : {args.input}", file=sys.stderr)
        print("Placez managers_sans_contact.csv dans futurebd/ ou utilisez --input.", file=sys.stderr)
        sys.exit(1)

    if args.reset and CHECKPOINT.is_file():
        CHECKPOINT.unlink()

    rows = read_sans_contact_csv(args.input)
    if args.limit > 0:
        rows = rows[: args.limit]

    if not rows:
        print("Aucune ligne à traiter.", file=sys.stderr)
        sys.exit(1)

    delay = args.delay if args.delay is not None else 2.5
    print(f"Lecture : {args.input} ({len(rows)} fiche(s))")
    print(f"Délai entre requêtes : {delay}s — checkpoint : {CHECKPOINT.name}")
    print("Recherche web en cours (peut prendre longtemps)…\n")

    t0 = time.time()

    def on_progress(current: int, total: int, result: dict[str, str]) -> None:
        status = "OK" if result["enrichi"] == "oui" else "—"
        email = result["email"][:40] if result["email"] else ""
        print(f"[{current}/{total}] {status} {result['nom'][:50]}", end="")
        if email:
            print(f" -> {email}", end="")
        print(flush=True)

    results = enrich_rows(rows, delay=delay, on_progress=on_progress)
    write_results_csv(results, args.output)

    import importlib.util

    md_module_path = ROOT / "scripts" / "enrich_to_md.py"
    try:
        spec = importlib.util.spec_from_file_location("enrich_to_md", md_module_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            DEFAULT_MD.write_text(mod.build_md(results), encoding="utf-8")
            print(f"Écrit : {DEFAULT_MD}")
    except Exception as exc:  # noqa: BLE001
        print(f"Markdown non généré : {exc}", file=sys.stderr)

    elapsed = time.time() - t0
    print(f"\nTerminé en {elapsed / 60:.1f} min")
    print_summary(results)
    print(f"Écrit : {args.output}")
    if CHECKPOINT.is_file():
        print(f"Checkpoint : {CHECKPOINT}")


if __name__ == "__main__":
    main()
