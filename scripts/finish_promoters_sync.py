#!/usr/bin/env python3
"""Post-enrichissement : validation téléphones + sync Supabase promoteurs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *args: str) -> None:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *args]
    print(f"\n>>> {' '.join(cmd)}\n", flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    run("fix_bad_promoter_enrichment.py")
    run("sync_promoteurs_supabase.py")
    run("fix_bad_promoter_enrichment.py")
    print("\nPipeline promoteurs termine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
