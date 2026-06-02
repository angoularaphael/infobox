"""Stockage local des identifiants BoxRec (complète le fichier .env)."""
from __future__ import annotations

import json
import os
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "settings.json"


def _ensure_dir() -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict[str, str]:
    if not SETTINGS_PATH.is_file():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return {k: str(v) for k, v in data.items() if k in ("username", "password")}
    except (json.JSONDecodeError, OSError):
        return {}


def get_credentials() -> tuple[str, str]:
    """Priorité : variables d'environnement, puis fichier data/settings.json."""
    env_user = os.getenv("BOXREC_USERNAME", "").strip()
    env_pass = os.getenv("BOXREC_PASSWORD", "").strip()
    if env_user and env_pass:
        return env_user, env_pass
    stored = load_settings()
    return stored.get("username", "").strip(), stored.get("password", "").strip()


def save_credentials(username: str, password: str) -> None:
    _ensure_dir()
    SETTINGS_PATH.write_text(
        json.dumps({"username": username.strip(), "password": password}, indent=2),
        encoding="utf-8",
    )


def clear_credentials() -> None:
    if SETTINGS_PATH.is_file():
        SETTINGS_PATH.unlink()


def is_configured() -> bool:
    user, pwd = get_credentials()
    return bool(user and pwd)


def username_hint() -> str | None:
    user, _ = get_credentials()
    if not user:
        return None
    if len(user) <= 2:
        return user[0] + "***"
    return user[:2] + "***" + user[-1:]
