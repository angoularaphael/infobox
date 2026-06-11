"""Recherche complémentaire e-mail / téléphone (hors BoxRec)."""
from __future__ import annotations

import os
import re
import time
from typing import Any

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{1,6})?")
SKIP_EMAIL_DOMAINS = ("boxrec.com", "example.com", "sentry.io", "w3.org")


def _pick_email(text: str) -> str:
    for m in EMAIL_RE.finditer(text):
        e = m.group(0).lower()
        if not any(d in e for d in SKIP_EMAIL_DOMAINS):
            return m.group(0)
    return ""


def _pick_phone(text: str) -> str:
    for m in PHONE_RE.finditer(text):
        p = m.group(0).strip()
        if len(re.sub(r"\D", "", p)) >= 9:
            return p
    return ""


def _search_text(query: str, max_results: int = 6) -> str:
    try:
        from duckduckgo_search import DDGS

        chunks: list[str] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                chunks.append(r.get("title", ""))
                chunks.append(r.get("body", ""))
                chunks.append(r.get("href", ""))
        return "\n".join(chunks)
    except Exception:
        return ""


def enrich_person(person: dict[str, Any], *, delay: float | None = None) -> dict[str, Any]:
    """Complète email/téléphone via recherche web si manquants."""
    wait = float(delay or os.getenv("ENRICH_DELAY_SECONDS", "2.5"))
    if person.get("email") and person.get("phone"):
        return person

    name = person.get("name", "").strip()
    if not name:
        return person

    role = person.get("role", "manager")
    location = person.get("location", "") or person.get("localisation", "")
    address = (person.get("address") or person.get("adresse") or "").strip()
    company = address.split("—")[0].strip() if "—" in address else address

    queries: list[str] = []
    if company and company != location:
        queries.append(f'"{name}" "{company}" email contact')
        queries.append(f'"{company}" {location} boxing contact')
    queries.extend(
        [
            f'"{name}" {role} {location} email contact',
            f'"{name}" boxing manager phone {location}',
            f'"{name}" {location} gym contact',
        ]
    )

    blob = ""
    for q in queries:
        blob += "\n" + _search_text(q, max_results=5)
        if person.get("email") and person.get("phone"):
            break
        time.sleep(wait)

    if not person.get("email"):
        email = _pick_email(blob)
        if email:
            person["email"] = email
            person["email_source"] = "web"
    if not person.get("phone"):
        phone = _pick_phone(blob)
        if phone:
            person["phone"] = phone
            person["phone_source"] = "web"

    return person


def enrich_people(people: list[dict[str, Any]], on_progress=None) -> list[dict[str, Any]]:
    for i, person in enumerate(people):
        if not person.get("email") or not person.get("phone"):
            enrich_person(person)
        if on_progress:
            on_progress(i + 1, len(people), person)
    return people
