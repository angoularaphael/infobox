"""Client HTTP BoxRec avec session, login et limitation de débit."""
from __future__ import annotations

import os
import time
from typing import Any, Callable
from urllib.parse import urlencode

from scraper.http_session import create_http_session
from scraper.parser import (
    extract_login_form_data,
    extract_search_country_from_url,
    is_login_page,
    merge_profile_into_person,
    parse_list_page,
    parse_profile_page,
)
from scraper.settings_store import get_credentials

BASE = "https://boxrec.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

VALID_ROLES = ("manager", "matchmaker", "promoter", "trainer", "media")


class BoxRecError(Exception):
    """Erreur métier liée à BoxRec."""


class BoxRecClient:
    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        delay: float | None = None,
        location: str | None = None,
        level_id: str | None = None,
        loc_txt: str | None = None,
        sex: str | None = None,
    ) -> None:
        stored_user, stored_pass = get_credentials()
        self.username = (username or stored_user).strip()
        self.password = password or stored_pass
        self.delay = float(delay or os.getenv("SCRAPE_DELAY_SECONDS", "1.5"))
        self.location = location or os.getenv("BOXREC_LOCATION", "gb_15599")
        self.level_id = level_id or os.getenv("BOXREC_LEVEL_ID", "gb")
        self.loc_txt = loc_txt or os.getenv("BOXREC_LOC_TXT", "United Kingdom")
        self.sex = sex or os.getenv("BOXREC_SEX", "m")
        self.session = create_http_session()
        self._logged_in = False
        self._last_request = 0.0

    def _wait(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _get(self, url: str) -> str:
        self._wait()
        resp = self.session.get(url, timeout=45)
        self._last_request = time.time()
        if resp.status_code == 403:
            raise BoxRecError(
                "Accès refusé (403). BoxRec bloque peut‑être cette IP — utilisez le mode manuel ou des identifiants."
            )
        if resp.status_code >= 400:
            raise BoxRecError(f"Erreur HTTP {resp.status_code} pour {url}")
        return resp.text

    def _post(
        self,
        url: str,
        data: dict[str, str],
        *,
        referer: str | None = None,
        allow_redirects: bool = True,
    ) -> str:
        self._wait()
        headers = {
            "Referer": referer or url,
            "Origin": BASE,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        resp = self.session.post(
            url, data=data, headers=headers, timeout=45, allow_redirects=allow_redirects
        )
        self._last_request = time.time()
        if resp.status_code == 403:
            raise BoxRecError(
                "BoxRec refuse la connexion automatique (403 — protection anti-bot). "
                "Utilisez le mode manuel : connectez-vous sur boxrec.com, copiez le HTML des pages liste."
            )
        if resp.status_code >= 400:
            raise BoxRecError(f"Erreur HTTP {resp.status_code} lors du POST {url}")
        return resp.text

    def login(self) -> None:
        if not self.username or not self.password:
            return
        # Cookies initiaux (Cloudflare / session)
        try:
            self._get(f"{BASE}/en")
        except BoxRecError:
            pass

        login_url = f"{BASE}/en/login"
        html = self._get(login_url)
        if not is_login_page(html):
            self._logged_in = True
            return

        form_meta = extract_login_form_data(html)
        csrf = form_meta.get("_csrf_token")
        if not csrf:
            raise BoxRecError(
                "Impossible d'obtenir le jeton CSRF de BoxRec. "
                "Le site bloque probablement les requêtes automatisées — utilisez le mode manuel."
            )

        post_url = form_meta.get("_form_action", login_url)
        payload = {
            "_csrf_token": csrf,
            "_username": self.username,
            "_password": self.password,
            "login[go]": "",
        }
        self._post(post_url, payload, referer=login_url)

        check = self._get(f"{BASE}/en")
        self._logged_in = not is_login_page(check)
        if not self._logged_in:
            raise BoxRecError(
                "Identifiants refusés ou session non établie. Vérifiez e-mail/mot de passe BoxRec."
            )

    def build_list_url(self, role: str, offset: int = 0) -> str:
        if role not in VALID_ROLES:
            raise BoxRecError(f"Rôle invalide : {role}. Valeurs : {', '.join(VALID_ROLES)}")
        params = {
            "ad_id": "",
            "l[location]": self.location,
            "l[role]": role,
            "l[company]": "",
            "l[sex]": self.sex,
            "l[division]": "",
            "l[loc_txt]": self.loc_txt,
            "l[level]": "c",
            "l[level_id]": self.level_id,
            "l_go": "",
            "level": "",
            "parent": "",
            "offset": str(offset),
        }
        return f"{BASE}/en/locations/people?{urlencode(params)}"

    def fetch_list_page(self, role: str, offset: int = 0) -> dict[str, Any]:
        url = self.build_list_url(role, offset)
        html = self._get(url)
        parsed = parse_list_page(html, list_url=url)
        parsed["url"] = url
        if parsed.get("is_login_page"):
            if self.username and self.password and not self._logged_in:
                self.login()
                html = self._get(url)
                parsed = parse_list_page(html, list_url=url)
                parsed["url"] = url
            if parsed.get("is_login_page"):
                raise BoxRecError(
                    "BoxRec exige une connexion. Définissez BOXREC_USERNAME et BOXREC_PASSWORD dans .env, "
                    "ou utilisez le mode manuel (coller le HTML depuis votre navigateur)."
                )
        return parsed

    def fetch_profile(self, profile_url: str) -> dict[str, str]:
        html = self._get(profile_url)
        if is_login_page(html):
            raise BoxRecError("Connexion requise pour lire les profils.")
        return parse_profile_page(html)

    def scrape_role(
        self,
        role: str,
        max_pages: int | None = None,
        fetch_contacts: bool = True,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, str]]:
        if self.username and self.password:
            self.login()

        all_people: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        offset = 0
        page = 0
        search_country = self.loc_txt or extract_search_country_from_url(
            self.build_list_url(role, 0)
        )

        while True:
            if max_pages is not None and page >= max_pages:
                break
            parsed = self.fetch_list_page(role, offset)
            batch = parsed.get("people", [])
            if not batch:
                break

            for person in batch:
                pid = person.get("id") or person.get("profile_url", "")
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                if fetch_contacts and person.get("profile_url"):
                    try:
                        profile = self.fetch_profile(person["profile_url"])
                        merge_profile_into_person(person, profile)
                        if (not person.get("email") or not person.get("phone")) and person.get(
                            "profile_url"
                        ):
                            time.sleep(self.delay * 1.5)
                            profile = self.fetch_profile(person["profile_url"])
                            merge_profile_into_person(person, profile)
                    except BoxRecError:
                        pass
                person["role"] = role
                if search_country and not person.get("search_country"):
                    person["search_country"] = search_country
                all_people.append(person)
                if on_progress:
                    on_progress(
                        {
                            "type": "person",
                            "count": len(all_people),
                            "person": person,
                            "page": page + 1,
                            "offset": offset,
                        }
                    )

            page += 1
            if on_progress:
                on_progress(
                    {
                        "type": "page_done",
                        "page": page,
                        "offset": offset,
                        "count": len(all_people),
                        "has_more": parsed.get("has_more"),
                    }
                )

            next_offset = parsed.get("next_offset")
            if next_offset is None or next_offset <= offset:
                break
            offset = int(next_offset)

        return all_people
