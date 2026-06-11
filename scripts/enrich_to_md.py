#!/usr/bin/env python3
"""Generate managers_enrichis.md from managers_enrichis.csv."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "futurebd" / "managers_enrichis.csv"
DEFAULT_MD = ROOT / "futurebd" / "managers_enrichis.md"


def read_csv(path: Path) -> list[dict[str, str]]:
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
    lines = text.splitlines(keepends=True)
    start = 1 if lines and lines[0].strip().lower().lstrip("\ufeff").startswith("sep=") else 0
    return list(csv.DictReader(lines[start:], delimiter=";", quotechar='"'))


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").strip()


def build_md(rows: list[dict[str, str]]) -> str:
    total = len(rows)
    enrichi_oui = [r for r in rows if (r.get("enrichi") or "").strip().lower() == "oui"]
    enrichi_non = [r for r in rows if (r.get("enrichi") or "").strip().lower() != "oui"]
    with_email = sum(1 for r in rows if (r.get("email") or "").strip())
    with_phone = sum(1 for r in rows if (r.get("telephone") or "").strip())
    both = sum(
        1
        for r in rows
        if (r.get("email") or "").strip() and (r.get("telephone") or "").strip()
    )
    email_only = sum(
        1
        for r in rows
        if (r.get("email") or "").strip() and not (r.get("telephone") or "").strip()
    )
    phone_only = sum(
        1
        for r in rows
        if (r.get("telephone") or "").strip() and not (r.get("email") or "").strip()
    )

    lines: list[str] = [
        "# Managers enrichis — recherche web",
        "",
        f"**Date de génération :** {date.today().isoformat()}",
        "",
        "## Statistiques",
        "",
        f"- Total traité : {total}",
        f"- Avec contact trouvé (enrichi=oui) : {len(enrichi_oui)}",
        f"- Avec e-mail : {with_email}",
        f"- Avec téléphone : {with_phone}",
        f"- E-mail et téléphone : {both}",
        f"- E-mail seulement : {email_only}",
        f"- Téléphone seulement : {phone_only}",
        f"- Toujours sans contact (enrichi=non) : {len(enrichi_non)}",
        "",
        "> Les coordonnées issues du web doivent être vérifiées manuellement avant utilisation.",
        "",
        "## Contacts trouvés",
        "",
    ]

    if enrichi_oui:
        for r in sorted(enrichi_oui, key=lambda x: (x.get("nom") or "").lower()):
            sources = []
            if (r.get("email_source") or "").strip():
                sources.append(f"e-mail: {r['email_source'].strip()}")
            if (r.get("telephone_source") or "").strip():
                sources.append(f"tél: {r['telephone_source'].strip()}")
            src = "; ".join(sources) if sources else "—"
            lines.extend(
                [
                    f"### {esc(r.get('nom', ''))}",
                    "",
                    f"- **E-mail :** {esc(r.get('email', '')) or '—'}",
                    f"- **Téléphone :** {esc(r.get('telephone', '')) or '—'}",
                    f"- **Adresse / org :** {esc(r.get('adresse', '')) or '—'}",
                    f"- **Localisation :** {esc(r.get('localisation', '')) or '—'}",
                    f"- **Sources :** {src}",
                    "",
                ]
            )
    else:
        lines.append("_Aucun contact trouvé._")
        lines.append("")

    lines.extend(["## Toujours sans contact", ""])
    if enrichi_non:
        for r in sorted(enrichi_non, key=lambda x: (x.get("nom") or "").lower()):
            nom = esc(r.get("nom", ""))
            adresse = esc(r.get("adresse", ""))
            loc = esc(r.get("localisation", ""))
            extra = " — ".join(x for x in (adresse, loc) if x)
            lines.append(f"- **{nom}**" + (f" ({extra})" if extra else ""))
    else:
        lines.append("_Tous les managers ont un contact._")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère managers_enrichis.md depuis le CSV enrichi.")
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()
    if not args.input.is_file():
        print(f"Fichier introuvable : {args.input}", file=sys.stderr)
        sys.exit(1)
    rows = read_csv(args.input)
    args.output.write_text(build_md(rows), encoding="utf-8")
    print(f"Écrit : {args.output} ({len(rows)} lignes)")


if __name__ == "__main__":
    main()
