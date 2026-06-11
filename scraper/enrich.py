"""Recherche complémentaire e-mail / téléphone (hors BoxRec) via web."""
from __future__ import annotations

import os
import re
import time
from typing import Any
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{1,6})?"
)
SKIP_EMAIL_DOMAINS = (
    "boxrec.com",
    "example.com",
    "sentry.io",
    "w3.org",
    "schema.org",
    "duckduckgo.com",
    "google.com",
    "gstatic.com",
    "facebook.com",
    "instagram.com",
)
SKIP_FETCH_HOSTS = (
    "boxrec.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "duckduckgo.com",
    "google.com",
    "linkedin.com",
)

ROLE_QUERIES: dict[str, list[str]] = {
    "promoter": [
        '"{name}" boxing promoter {location} email',
        '"{name}" promoter {location} contact phone',
        '"{name}" "{company}" boxing events contact',
        '"{company}" {location} boxing promoter email',
        '"{name}" matchmaker promoter {country} email',
    ],
    "manager": [
        '"{name}" "{company}" email contact',
        '"{company}" {location} boxing contact',
        '"{name}" boxing manager {location} email',
        '"{name}" boxing manager phone {location}',
        '"{name}" {location} gym contact',
    ],
    "matchmaker": [
        '"{name}" boxing matchmaker {location} email',
        '"{name}" matchmaker {location} contact',
    ],
}


def _pick_email(text: str) -> str:
    for m in EMAIL_RE.finditer(text):
        e = m.group(0).lower()
        if not any(d in e for d in SKIP_EMAIL_DOMAINS):
            return m.group(0)
    return ""


def _pick_phone(text: str) -> str:
    for m in PHONE_RE.finditer(text):
        p = m.group(0).strip()
        digits = re.sub(r"\D", "", p)
        if 9 <= len(digits) <= 15:
            return p
    return ""


def _search_results(query: str, max_results: int = 8) -> list[dict[str, str]]:
    try:
        from duckduckgo_search import DDGS

        out: list[dict[str, str]] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                out.append(
                    {
                        "title": r.get("title", "") or "",
                        "body": r.get("body", "") or "",
                        "href": r.get("href", "") or "",
                    }
                )
        return out
    except Exception:
        return []


def _should_fetch_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    try:
        host = urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return False
    return not any(skip in host for skip in SKIP_FETCH_HOSTS)


def _fetch_page_text(url: str, *, timeout: int = 20) -> str:
    if not _should_fetch_url(url):
        return ""
    try:
        from scraper.http_session import create_http_session

        session = create_http_session()
        resp = session.get(url, timeout=timeout)
        if resp.status_code >= 400:
            return ""
        html = resp.text or ""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            return soup.get_text("\n", strip=True)[:120_000]
        except Exception:
            return html[:120_000]
    except Exception:
        return ""


def _build_queries(person: dict[str, Any]) -> list[str]:
    name = (person.get("name") or "").strip()
    if not name:
        return []

    role = (person.get("role") or "manager").strip().lower()
    location = (person.get("location") or person.get("localisation") or "").strip()
    country = (person.get("search_country") or person.get("pays_recherche") or location).strip()
    address = (person.get("address") or person.get("adresse") or "").strip()
    company = address.split("—")[0].strip() if "—" in address else address
    if company == location:
        company = ""

    templates = ROLE_QUERIES.get(role, ROLE_QUERIES["manager"])
    queries: list[str] = []
    seen: set[str] = set()
    for tpl in templates:
        q = tpl.format(
            name=name,
            company=company or name,
            location=location or country or "boxing",
            country=country or location or "",
        ).strip()
        if q and q not in seen:
            seen.add(q)
            queries.append(q)
    return queries


def enrich_person(
    person: dict[str, Any],
    *,
    delay: float | None = None,
    deep_web: bool = True,
    max_pages: int = 4,
) -> dict[str, Any]:
    """Complète email/téléphone via DuckDuckGo (+ visite de pages si deep_web)."""
    wait = float(delay or os.getenv("ENRICH_DELAY_SECONDS", "2.5"))
    if person.get("email") and person.get("phone"):
        return person

    queries = _build_queries(person)
    if not queries:
        return person

    blob_parts: list[str] = []
    urls_to_fetch: list[str] = []

    for q in queries:
        for hit in _search_results(q, max_results=6):
            blob_parts.extend([hit["title"], hit["body"], hit["href"]])
            href = hit["href"]
            if deep_web and href and href not in urls_to_fetch:
                urls_to_fetch.append(href)

        if not person.get("email"):
            email = _pick_email("\n".join(blob_parts))
            if email:
                person["email"] = email
                person["email_source"] = "web_search"
        if not person.get("phone"):
            phone = _pick_phone("\n".join(blob_parts))
            if phone:
                person["phone"] = phone
                person["phone_source"] = "web_search"

        if person.get("email") and person.get("phone"):
            return person
        time.sleep(wait)

    if deep_web and urls_to_fetch and (not person.get("email") or not person.get("phone")):
        fetched = 0
        for url in urls_to_fetch:
            if fetched >= max_pages:
                break
            if not _should_fetch_url(url):
                continue
            page_text = _fetch_page_text(url)
            fetched += 1
            if not page_text:
                time.sleep(wait)
                continue

            blob_parts.append(page_text)
            if not person.get("email"):
                email = _pick_email(page_text)
                if email:
                    person["email"] = email
                    person["email_source"] = url[:200]
            if not person.get("phone"):
                phone = _pick_phone(page_text)
                if phone:
                    person["phone"] = phone
                    person["phone_source"] = url[:200]

            if person.get("email") and person.get("phone"):
                break
            time.sleep(wait)

    return person


def enrich_people(
    people: list[dict[str, Any]],
    *,
    deep_web: bool = True,
    on_progress=None,
) -> list[dict[str, Any]]:
    for i, person in enumerate(people):
        if not person.get("email") or not person.get("phone"):
            enrich_person(person, deep_web=deep_web)
        if on_progress:
            on_progress(i + 1, len(people), person)
    return people
