#!/usr/bin/env python3
"""Apply promoteurs migration (005) to Supabase."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "005_promoteurs.sql"


def apply_via_db_url(sql: str) -> bool:
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        return False
    try:
        import psycopg2
    except ImportError:
        print("[info] psycopg2 absent")
        return False

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        print("[ok] Migration 005 appliquée via DATABASE_URL")
        return True
    finally:
        conn.close()


def verify_table(url: str, key: str) -> bool:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    resp = requests.get(
        f"{url.rstrip('/')}/rest/v1/promoteurs",
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

    if verify_table(url, key):
        print("[ok] Table promoteurs déjà présente")
        return 0

    sql = MIGRATION.read_text(encoding="utf-8")
    if apply_via_db_url(sql):
        return 0 if verify_table(url, key) else 1

    print("Migration manuelle requise : exécuter supabase/migrations/005_promoteurs.sql")
    return 2


if __name__ == "__main__":
    sys.exit(main())
