#!/usr/bin/env python3
"""Consolide les CSV boxrec_*_*.csv (tous rôles / pays) en managers_final.csv et managers_final.md."""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUTUREBD = ROOT / "futurebd"
OUTPUT_CSV = FUTUREBD / "managers_final.csv"
OUTPUT_MD = FUTUREBD / "managers_final.md"

FIELDS = (
    "nom",
    "email",
    "telephone",
    "adresse",
    "role",
    "pays_recherche",
    "localisation",
)


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits if len(digits) >= 7 else ""


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def has_contact(row: dict[str, str]) -> bool:
    return bool(normalize_email(row.get("email", "")) or normalize_phone(row.get("telephone", "")))


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
    rows: list[dict[str, str]] = []
    lines = read_text_lines(path)
    if not lines:
        return rows
    start = 0
    if lines and is_sep_line(lines[0]):
        start = 1
    reader = csv.DictReader(lines[start:], delimiter=";", quotechar='"')
    for raw in reader:
        row = {field: (raw.get(field) or "").strip() for field in FIELDS}
        if row["nom"]:
            rows.append(row)
    return rows


def dedupe_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()
    unique: list[dict[str, str]] = []
    duplicates = 0

    for row in rows:
        email_key = normalize_email(row["email"])
        phone_key = normalize_phone(row["telephone"])

        is_dup = False
        if email_key and email_key in seen_emails:
            is_dup = True
        if phone_key and phone_key in seen_phones:
            is_dup = True

        if is_dup:
            duplicates += 1
            continue

        unique.append(row)
        if email_key:
            seen_emails.add(email_key)
        if phone_key:
            seen_phones.add(phone_key)

    return unique, duplicates


def write_csv(rows: list[dict[str, str]]) -> None:
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        handle.write("sep=;\n")
        writer = csv.writer(handle, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writerow(FIELDS)
        for row in rows:
            writer.writerow([row[field] for field in FIELDS])


def md_field(value: str) -> str:
    return value.strip() if value.strip() else "—"


def write_md(rows: list[dict[str, str]], stats: dict[str, int]) -> None:
    lines = [
        "# Contacts BoxRec — managers, matchmakers, etc.",
        "",
        f"**Total : {len(rows)}** contacts (e-mail et/ou téléphone, sans doublons).",
        "",
        "## Statistiques",
        "",
        f"- Fichiers CSV sources lus : {stats['source_files']}",
        f"- Lignes brutes (tous pays) : {stats['raw_rows']}",
        f"- Sans e-mail ni téléphone (exclus) : {stats['no_contact']}",
        f"- Doublons retirés : {stats['duplicates']}",
        f"- Avec e-mail et téléphone : {stats['both']}",
        f"- Avec e-mail seulement : {stats['email_only']}",
        f"- Avec téléphone seulement : {stats['phone_only']}",
        "",
        "---",
        "",
    ]

    sorted_rows = sorted(rows, key=lambda r: normalize_name(r["nom"]))
    current_letter = ""
    for row in sorted_rows:
        letter = normalize_name(row["nom"])[:1].upper() if row["nom"] else "#"
        if not letter.isalpha():
            letter = "#"
        if letter != current_letter:
            current_letter = letter
            lines.extend(["", f"## {current_letter}", ""])

        email = md_field(row["email"])
        phone = md_field(row["telephone"])
        pays = row["pays_recherche"] or "—"
        loc = row["localisation"] or "—"
        addr = row["adresse"] or loc
        lines.append(
            f"- **{row['nom']}** — {email} — {phone} — *{pays}* — {loc} · {addr}"
        )

    OUTPUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    source_files = sorted(
        p
        for p in FUTUREBD.glob("boxrec_*.csv")
        if p.name not in {OUTPUT_CSV.name, "managers_final.csv"}
    )
    all_rows: list[dict[str, str]] = []
    raw_rows = 0
    no_contact = 0

    for path in source_files:
        for row in read_boxrec_csv(path):
            raw_rows += 1
            if not has_contact(row):
                no_contact += 1
                continue
            all_rows.append(row)

    unique_rows, duplicates = dedupe_rows(all_rows)
    unique_rows.sort(key=lambda r: normalize_name(r["nom"]))

    both = email_only = phone_only = 0
    for row in unique_rows:
        has_email = bool(normalize_email(row["email"]))
        has_phone = bool(normalize_phone(row["telephone"]))
        if has_email and has_phone:
            both += 1
        elif has_email:
            email_only += 1
        else:
            phone_only += 1

    write_csv(unique_rows)
    write_md(
        unique_rows,
        {
            "source_files": len(source_files),
            "raw_rows": raw_rows,
            "no_contact": no_contact,
            "duplicates": duplicates,
            "both": both,
            "email_only": email_only,
            "phone_only": phone_only,
        },
    )

    print(f"Sources: {len(source_files)} fichiers")
    print(f"Lignes brutes: {raw_rows}")
    print(f"Sans contact: {no_contact}")
    print(f"Doublons: {duplicates}")
    print(f"Total final: {len(unique_rows)}")
    print(f"Écrit: {OUTPUT_CSV}")
    print(f"Écrit: {OUTPUT_MD}")


if __name__ == "__main__":
    main()
