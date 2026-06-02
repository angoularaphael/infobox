"""Configuration publique et URL de déploiement."""
from __future__ import annotations

import os


def public_base_url() -> str:
    """URL de base pour le favori (local ou Vercel)."""
    explicit = (os.getenv("INFOBOX_PUBLIC_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    vercel = (os.getenv("VERCEL_URL") or "").strip()
    if vercel:
        if vercel.startswith("http"):
            return vercel.rstrip("/")
        return f"https://{vercel}"
    port = os.getenv("PORT", "5000")
    return f"http://127.0.0.1:{port}"


def is_production() -> bool:
    return bool(os.getenv("VERCEL") or os.getenv("INFOBOX_PUBLIC_URL"))
