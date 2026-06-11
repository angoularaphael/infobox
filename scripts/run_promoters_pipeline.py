#!/usr/bin/env python3
"""Pipeline promoteurs : scrape BoxRec + enrichissement web + sorties promoteur.csv/.md."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUTUREBD = ROOT / "futurebd"
OUTPUT_CSV = FUTUREBD / "promoteur.csv"
OUTPUT_MD = FUTUREBD / "promoteur.md"


def run_step(cmd: list[str], *, env: dict | None = None) -> int:
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    import os

    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run(cmd, cwd=ROOT, env=merged)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline promoteurs (scrape + enrich, budget global).")
    parser.add_argument("--max-minutes", type=float, default=30.0, help="Budget total en minutes")
    parser.add_argument("--scrape-minutes", type=float, default=10.0, help="Part scrape BoxRec")
    parser.add_argument("--skip-scrape", action="store_true", help="Enrichir seulement (CSV déjà présents)")
    parser.add_argument("--skip-enrich", action="store_true", help="Scrape seulement")
    args = parser.parse_args()

    t0 = time.time()
    deadline = t0 + max(1.0, args.max_minutes) * 60.0
    scrape_budget = min(args.scrape_minutes, args.max_minutes * 0.4)

    FUTUREBD.mkdir(parents=True, exist_ok=True)

    if not args.skip_scrape:
        code = run_step(
            [
                sys.executable,
                str(ROOT / "scripts" / "scrape_promoters_boxrec.py"),
                "--max-minutes",
                str(min(3.0, scrape_budget)),
                "--max-pages",
                "2",
                "--delay",
                "1.0",
            ]
        )
        has_csv = bool(list(FUTUREBD.glob("boxrec_promoter_*.csv"))) or (FUTUREBD / "promoteurs_liste_brute.csv").is_file()
        if code != 0 or not has_csv:
            print("BoxRec indisponible — repli collecte web (DuckDuckGo).", flush=True)
            web_budget = scrape_budget if code != 0 else min(scrape_budget, 8.0)
            code = run_step(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "collect_promoters_web_search.py"),
                    "--max-minutes",
                    str(web_budget),
                    "--delay",
                    "1.5",
                ]
            )
            if code != 0:
                print("Collecte web échouée.", file=sys.stderr)
                return code

    if args.skip_enrich:
        print("Enrichissement ignoré (--skip-enrich).")
        return 0

    remaining_min = max(1.0, (deadline - time.time()) / 60.0)
    enrich_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "enrich_promoters_web.py"),
        "--from-futurebd",
        "--output",
        str(OUTPUT_CSV),
        "--md-output",
        str(OUTPUT_MD),
        "--max-minutes",
        str(remaining_min),
        "--delay",
        "2.0",
        "--max-pages",
        "3",
    ]
    code = run_step(enrich_cmd)
    elapsed = (time.time() - t0) / 60.0
    print(f"\nPipeline terminé en {elapsed:.1f} min (budget {args.max_minutes:.0f} min).")
    if OUTPUT_CSV.is_file():
        print(f"Sortie CSV : {OUTPUT_CSV}")
    if OUTPUT_MD.is_file():
        print(f"Sortie MD  : {OUTPUT_MD}")
    return code


if __name__ == "__main__":
    sys.exit(main())
