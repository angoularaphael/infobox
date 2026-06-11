#!/usr/bin/env python3
"""Apply Boxing Center SQL migration to Supabase."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "001_boxing_center.sql"


def apply_via_db_url(sql: str) -> bool:
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        return False
    try:
        import psycopg2
    except ImportError:
        print("[info] psycopg2 absent — pip install psycopg2-binary pour connexion directe")
        return False

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        print("[ok] Migration appliquée via DATABASE_URL")
        return True
    finally:
        conn.close()


def verify_tables(url: str, key: str) -> bool:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    resp = requests.get(
        f"{url.rstrip('/')}/rest/v1/managers",
        headers=headers,
        params={"select": "id", "limit": "1"},
        timeout=30,
    )
    return resp.status_code == 200


def main() -> int:
    load_dotenv(ROOT / "boxing-center-bot" / ".env")
    load_dotenv(ROOT / ".env")

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis")
        return 1

    if verify_tables(url, key):
        print("[ok] Tables déjà présentes (managers accessible)")
        return 0

    sql = MIGRATION.read_text(encoding="utf-8")
    if apply_via_db_url(sql):
        return 0

    print("=" * 60)
    print("Migration manuelle requise")
    print("=" * 60)
    print(f"1. Ouvrir https://supabase.com/dashboard/project/ulxtbvxdueolvnjhpzvw/sql")
    print(f"2. Coller le contenu de: {MIGRATION}")
    print("3. Exécuter le script SQL")
    print("4. Relancer: python scripts/sync_managers_supabase.py")
    print("=" * 60)
    return 2


if __name__ == "__main__":
    sys.exit(main())
