"""En-têtes de sécurité, anti-scraping léger et limitation de débit."""
from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from urllib.parse import urlparse

from flask import Flask, Request, Response, jsonify, request

_BLOCKED_UA = re.compile(
    r"scrapy|python-requests|httpx/|aiohttp|curl/|wget/|go-http|java/|libwww|"
    r"semrush|ahrefs|mj12bot|dotbot|petalbot|bytespider|headlesschrome",
    re.I,
)

_PROTECTED_PREFIXES = (
    "/api/scrape",
    "/api/import",
    "/api/enrich",
    "/api/export",
    "/api/session",
    "/api/config",
    "/api/parse",
)

_RATE_STORE: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW = 60.0
_RATE_MAX = int(os.getenv("INFOBOX_RATE_LIMIT_PER_MIN", "90"))


def _client_ip(req: Request) -> str:
    forwarded = req.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return req.remote_addr or "unknown"


def _rate_limited(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _RATE_STORE[ip] if now - t < _RATE_WINDOW]
    if len(hits) >= _RATE_MAX:
        _RATE_STORE[ip] = hits
        return True
    hits.append(now)
    _RATE_STORE[ip] = hits
    return False


def _allowed_cors_origin(origin: str, host_url: str) -> str | None:
    if not origin:
        return None
    if "boxrec.com" in origin.lower():
        return origin
    try:
        host = urlparse(host_url).netloc.lower()
        if urlparse(origin).netloc.lower() == host:
            return origin
    except Exception:
        pass
    return None


def _needs_api_key(path: str) -> bool:
    return any(path.startswith(p) for p in _PROTECTED_PREFIXES)


def _check_api_key() -> Response | tuple[Response, int] | None:
    secret = (os.getenv("INFOBOX_API_KEY") or "").strip()
    if not secret:
        return None
    provided = request.headers.get("X-InfoBox-Key") or request.args.get("api_key", "")
    if provided != secret:
        return jsonify({"error": "Accès refusé"}), 401
    return None


def register_security(app: Flask) -> None:
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY") or os.urandom(32).hex()
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("INFOBOX_MAX_BODY", str(2 * 1024 * 1024)))

    @app.before_request
    def _security_before() -> Response | tuple[Response, int] | None:
        path = request.path or "/"

        if request.method not in ("GET", "POST", "HEAD", "OPTIONS"):
            return jsonify({"error": "Méthode non autorisée"}), 405

        ua = request.headers.get("User-Agent", "")
        if _BLOCKED_UA.search(ua) and not path.startswith("/static/js/bookmarklet"):
            return jsonify({"error": "Accès refusé"}), 403

        if path.startswith("/api/") or path.startswith("/static/js/bookmarklet"):
            if _rate_limited(_client_ip(request)):
                return jsonify({"error": "Trop de requêtes — réessayez dans une minute"}), 429

        if path.startswith("/api/") and _needs_api_key(path):
            denied = _check_api_key()
            if denied is not None:
                return denied

        return None

    @app.after_request
    def _security_after(response: Response) -> Response:
        path = request.path or ""

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"

        if path.startswith("/api/") or path.startswith("/static/js/bookmarklet"):
            origin = _allowed_cors_origin(request.headers.get("Origin", ""), request.host_url)
            if origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-InfoBox-Key"

        if path.endswith(".html") or path in ("/", "/assistant", "/install-favori"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src https://fonts.gstatic.com; "
                "img-src 'self' data:; "
                "connect-src 'self' https://boxrec.com https://*.boxrec.com; "
                "frame-ancestors 'none'; base-uri 'self'"
            )

        return response
