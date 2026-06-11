"""Pays BoxRec via le composant LocationPicker (liste officielle du site)."""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any

from bs4 import BeautifulSoup

BASE = "https://boxrec.com"
_SKIP_LABELS = re.compile(r"^(back|worldwide|all locations?)$", re.I)
_PICKER_SELECTOR = (
    '[data-action*="locationpicker#optionDrillDown"], '
    '[data-action*="locationpicker#optionSelect"]'
)


def _decode_live_props(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    text = html_lib.unescape(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def extract_location_picker_props(page_html: str) -> dict[str, Any] | None:
    """Extrait les props du LiveComponent LocationPicker depuis une page HTML."""
    soup = BeautifulSoup(page_html, "html.parser")
    el = soup.select_one('[data-live-name-value="LocationPicker"]')
    if not el:
        return None
    return _decode_live_props(el.get("data-live-props-value", ""))


def parse_countries_from_picker_html(picker_html: str) -> list[dict[str, str]]:
    """Parse la réponse HTML du LocationPicker (niveau pays)."""
    soup = BeautifulSoup(picker_html, "html.parser")
    countries: list[dict[str, str]] = []
    seen: set[str] = set()

    for el in soup.select(_PICKER_SELECTOR):
        display = (el.get("data-display") or el.get_text(" ", strip=True) or "").strip()
        if not display or _SKIP_LABELS.match(display):
            continue
        level = (el.get("data-level") or "").strip().lower()
        if level and level not in ("", "country", "c", "nation"):
            continue
        key = display.lower()
        if key in seen:
            continue
        seen.add(key)
        value = (el.get("data-value") or "").strip()
        address_id = f"{value}|||||{display}" if value else f"|||||{display}"
        countries.append({"label": display, "address_id": address_id})

    countries.sort(key=lambda c: c["label"].casefold())
    return countries


def fetch_countries_from_location_picker(
    session: Any,
    *,
    referer: str = "/en/locations/people",
    people_page_html: str | None = None,
) -> list[dict[str, str]]:
    """
    Charge tous les pays via POST /en/_components/LocationPicker.
    Nécessite une session BoxRec connectée (cookies sur `session`).
    """
    html = people_page_html
    if not html:
        resp = session.get(f"{BASE}{referer}", timeout=45)
        resp.raise_for_status()
        html = resp.text

    props = extract_location_picker_props(html)
    if not props or not props.get("@checksum"):
        return []

    updated = {
        "initialLoadData": True,
        "query": "",
        "level": "",
        "levelid": "",
        "parent": "",
    }
    form = {"data": (None, json.dumps({"props": props, "updated": updated}))}
    headers = {
        "Accept": "application/vnd.live-component+html",
        "X-Requested-With": "XMLHttpRequest",
        "X-Live-Url": referer,
    }
    resp = session.post(
        f"{BASE}/en/_components/LocationPicker",
        files=form,
        headers=headers,
        timeout=45,
    )
    resp.raise_for_status()
    return parse_countries_from_picker_html(resp.text)
