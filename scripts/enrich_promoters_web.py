#!/usr/bin/env python3
"""Enrichit les promoteurs BoxRec (CSV) via recherche web + visite de sites.

Cherche e-mails et téléphones sur le web (DuckDuckGo + pages trouvées).
Ne repasse pas par BoxRec ni le favori navigateur.

Usage:
    python scripts/enrich_promoters_web.py --from-futurebd
    python scripts/enrich_promoters_web.py --input futurebd/promoters_sans_contact.csv
    python scripts/enrich_promoters_web.py --from-futurebd --limit 5
    python scripts/enrich_promoters_web.py --from-futurebd --resume

Sorties (dossier futurebd/) :
    promoteur.csv
    promoteur.md
    promoteur_checkpoint.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from contact_validation import normalize_email, normalize_phone_digits, validate_email, validate_phone  # noqa: E402
from scraper.enrich import enrich_person  # noqa: E402

FUTUREBD = ROOT / "futurebd"
DEFAULT_INPUT = FUTUREBD / "promoters_sans_contact.csv"
DEFAULT_OUTPUT = FUTUREBD / "promoteur.csv"
DEFAULT_MD = FUTUREBD / "promoteur.md"
CHECKPOINT = FUTUREBD / "promoteur_checkpoint.json"

BOXREC_FIELDS = (
    "nom",
    "email",
    "telephone",
    "adresse",
    "role",
    "pays_recherche",
    "localisation",
    "url_profil",
)

OUTPUT_FIELDS = (
    "nom",
    "email",
    "telephone",
    "adresse",
    "role",
    "pays_recherche",
    "localisation",
    "url_profil",
    "email_source",
    "telephone_source",
    "enrichi",
)


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def normalize_phone_digits(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def normalize_phone(value: str) -> str:
    digits = normalize_phone_digits(value)
    validated, _err = validate_phone(digits)
    return validated or ""


def normalize_email_field(value: str) -> str:
    validated, _err = validate_email(value)
    return validated or ""


def has_contact(row: dict[str, str]) -> bool:
    return bool(normalize_email_field(row.get("email", "")) or normalize_phone(row.get("telephone", "")))


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


def read_boxrec_csv(path: Path) -> list[dict[str, str]]:
    lines = read_text_lines(path)
    if not lines:
        return []
    start = 1 if lines and is_sep_line(lines[0]) else 0
    reader = csv.DictReader(lines[start:], delimiter=";", quotechar='"')
    rows: list[dict[str, str]] = []
    for raw in reader:
        row = {field: (raw.get(field) or "").strip() for field in BOXREC_FIELDS}
        if not row["url_profil"]:
            row["url_profil"] = (raw.get("profile_url") or "").strip()
        if not row["role"]:
            row["role"] = "promoter"
        if row["nom"]:
            rows.append(row)
    return rows


def read_sans_contact_csv(path: Path) -> list[dict[str, str]]:
    lines = read_text_lines(path)
    if not lines:
        return []
    start = 1 if lines and is_sep_line(lines[0]) else 0
    reader = csv.DictReader(lines[start:], delimiter=";", quotechar='"')
    rows: list[dict[str, str]] = []
    for raw in reader:
        nom = (raw.get("Nom") or raw.get("nom") or "").strip()
        if not nom:
            continue
        rows.append(
            {
                "nom": nom,
                "email": (raw.get("email") or raw.get("Email") or "").strip(),
                "telephone": (raw.get("telephone") or raw.get("Téléphone") or "").strip(),
                "adresse": (raw.get("Organisation / Adresse") or raw.get("adresse") or "").strip(),
                "localisation": (raw.get("Localisation") or raw.get("localisation") or "").strip(),
                "pays_recherche": (raw.get("pays_recherche") or raw.get("Pays") or "").strip(),
                "url_profil": (raw.get("url_profil") or raw.get("profile_url") or "").strip(),
                "role": "promoter",
            }
        )
    return rows


def load_rows_from_futurebd() -> list[dict[str, str]]:
    paths = sorted(FUTUREBD.glob("boxrec_promoter_*.csv"))
    if not paths:
        paths = sorted(FUTUREBD.glob("boxrec_*promoter*.csv"))
    if not paths and (FUTUREBD / "promoteurs_liste_brute.csv").is_file():
        paths = [FUTUREBD / "promoteurs_liste_brute.csv"]
    if not paths:
        return []

    by_profile: dict[str, dict[str, str]] = {}
    for path in paths:
        for row in read_boxrec_csv(path):
            key = row["url_profil"] or normalize_name(row["nom"])
            if key not in by_profile:
                by_profile[key] = row
            elif has_contact(row) and not has_contact(by_profile[key]):
                by_profile[key] = row

    return [r for r in by_profile.values() if not has_contact(r)]


def person_from_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "name": row["nom"],
        "email": row.get("email", ""),
        "phone": row.get("telephone", ""),
        "role": row.get("role") or "promoter",
        "location": row.get("localisation", ""),
        "search_country": row.get("pays_recherche", ""),
        "address": row.get("adresse", ""),
        "profile_url": row.get("url_profil", ""),
    }


def result_from_person(row: dict[str, str], person: dict[str, Any]) -> dict[str, str]:
    email = normalize_email_field(person.get("email") or row.get("email") or "")
    phone_raw = (person.get("phone") or row.get("telephone") or "").strip()
    phone = normalize_phone(phone_raw)
    if phone_raw and not phone:
        person.pop("phone", None)
        person.pop("phone_source", None)
    return {
        "nom": row["nom"],
        "email": email,
        "telephone": phone,
        "adresse": row.get("adresse", ""),
        "role": row.get("role") or "promoter",
        "pays_recherche": row.get("pays_recherche", ""),
        "localisation": row.get("localisation", ""),
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


def save_checkpoint(
    results: list[dict[str, str]],
    *,
    existing: dict[str, dict[str, str]] | None = None,
) -> None:
    merged = dict(existing or {})
    for row in results:
        merged[normalize_name(row["nom"])] = row
    FUTUREBD.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(
        json.dumps(list(merged.values()), ensure_ascii=False, indent=2),
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
    deep_web: bool,
    max_pages: int,
    on_progress=None,
    deadline: float | None = None,
) -> list[dict[str, str]]:
    checkpoint = load_checkpoint()
    results: list[dict[str, str]] = []
    total = len(rows)

    for i, row in enumerate(rows, start=1):
        if deadline is not None and time.time() >= deadline:
            print(f"\nBudget temps atteint — {len(results)}/{total} traités.", flush=True)
            for pending in rows[i - 1 :]:
                key = normalize_name(pending["nom"])
                if key in checkpoint:
                    results.append(checkpoint[key])
                else:
                    results.append(result_from_person(pending, person_from_row(pending)))
            break

        key = normalize_name(row["nom"])
        if key in checkpoint:
            result = checkpoint[key]
            results.append(result)
            if on_progress:
                on_progress(i, total, result)
            continue

        person = person_from_row(row)
        enrich_person(person, delay=delay, deep_web=deep_web, max_pages=max_pages)
        result = result_from_person(row, person)
        results.append(result)
        save_checkpoint(results, existing=checkpoint)
        checkpoint[normalize_name(row["nom"])] = result
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
    parser = argparse.ArgumentParser(
        description="Enrichit promoteurs via recherche web (DuckDuckGo + sites)."
    )
    parser.add_argument("--input", type=Path, default=None, help="CSV source")
    parser.add_argument(
        "--from-futurebd",
        action="store_true",
        help="Lit futurebd/boxrec_promoter_*.csv et garde ceux sans e-mail/tél.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD)
    parser.add_argument(
        "--max-minutes",
        type=float,
        default=0.0,
        help="Arrêt après N minutes (0 = illimité)",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=None)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=4,
        help="Pages web max à visiter par promoteur (défaut 4)",
    )
    parser.add_argument(
        "--snippets-only",
        action="store_true",
        help="DuckDuckGo uniquement, sans ouvrir les sites",
    )
    parser.add_argument("--resume", action="store_true", help="Reprendre le checkpoint")
    parser.add_argument("--reset", action="store_true", help="Efface le checkpoint")
    args = parser.parse_args()

    if args.reset and CHECKPOINT.is_file():
        CHECKPOINT.unlink()

    rows: list[dict[str, str]] = []
    if args.from_futurebd:
        rows = load_rows_from_futurebd()
        if not rows:
            print("Aucun boxrec_promoter_*.csv dans futurebd/ ou tous ont déjà un contact.", file=sys.stderr)
            sys.exit(1)
    elif args.input:
        if not args.input.is_file():
            print(f"Fichier introuvable : {args.input}", file=sys.stderr)
            sys.exit(1)
        if "sans_contact" in args.input.name.lower():
            rows = read_sans_contact_csv(args.input)
        else:
            rows = read_boxrec_csv(args.input)
            rows = [r for r in rows if not has_contact(r)]
    elif DEFAULT_INPUT.is_file():
        rows = read_sans_contact_csv(DEFAULT_INPUT)
    else:
        print("Indiquez --from-futurebd ou --input chemin.csv", file=sys.stderr)
        sys.exit(1)

    if args.limit > 0:
        rows = rows[: args.limit]

    if not rows:
        print("Aucune fiche promoteur à enrichir.", file=sys.stderr)
        sys.exit(1)

    delay = args.delay if args.delay is not None else float(os.getenv("ENRICH_DELAY_SECONDS", "2.5"))
    deep_web = not args.snippets_only

    print(f"Promoteurs à enrichir : {len(rows)}")
    print(f"Mode : {'DuckDuckGo + sites web' if deep_web else 'DuckDuckGo seulement'}")
    print(f"Délai : {delay}s — checkpoint : {CHECKPOINT.name}\n")

    t0 = time.time()
    deadline = t0 + args.max_minutes * 60.0 if args.max_minutes > 0 else None
    if deadline:
        print(f"Budget temps : {args.max_minutes:.1f} min\n")

    def on_progress(current: int, total: int, result: dict[str, str]) -> None:
        status = "OK" if result["enrichi"] == "oui" else "-"
        bits = []
        if result["email"]:
            bits.append(result["email"][:36])
        if result["telephone"]:
            bits.append(result["telephone"][:18])
        extra = " | ".join(bits)
        line = f"[{current}/{total}] {status} {result['nom'][:44]}"
        if extra:
            line += f" -> {extra}"
        try:
            print(line, flush=True)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)

    results = enrich_rows(
        rows,
        delay=delay,
        deep_web=deep_web,
        max_pages=max(1, args.max_pages),
        on_progress=on_progress,
        deadline=deadline,
    )
    write_results_csv(results, args.output)

    import importlib.util

    md_module_path = ROOT / "scripts" / "enrich_to_md.py"
    md_path = args.md_output
    try:
        spec = importlib.util.spec_from_file_location("enrich_to_md", md_module_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            md_text = mod.build_md(results).replace("managers", "promoteurs").replace(
                "Managers", "Promoteurs"
            )
            md_path.write_text(md_text, encoding="utf-8")
            print(f"Écrit : {md_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"Markdown non généré : {exc}", file=sys.stderr)

    elapsed = time.time() - t0
    print(f"\nTerminé en {elapsed / 60:.1f} min")
    print_summary(results)
    print(f"Écrit : {args.output}")


if __name__ == "__main__":
    main()
