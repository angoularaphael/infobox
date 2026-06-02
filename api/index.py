"""Point d'entrée Vercel serverless pour Flask (WSGI)."""
from app import app  # noqa: F401 — instance Flask exportée pour @vercel/python

# Alias explicite pour les runtimes qui cherchent « handler »
handler = app
