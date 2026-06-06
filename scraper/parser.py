"""Parse les pages HTML BoxRec (liste et profil)."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{1,6})?"
)

PERSON_ROLES = (
    "manager",
    "matchmaker",
    "promoter",
    "trainer",
    "media",
    "referee",
    "judge",
    "inspector",
    "supervisor",
    "doctor",
    "timekeeper",
)

_PERSON_HREF_RE = re.compile(
    r"/en/(" + "|".join(PERSON_ROLES) + r")/(\d+)(?:/|$|\?|#)",
    re.I,
)

_NON_PERSON_PATH_SEGMENTS = frozenset(
    {
        "locations",
        "login",
        "event",
        "events",
        "bout",
        "bouts",
        "ratings",
        "schedule",
        "results",
        "date",
        "champions",
        "clubs",
        "titles",
        "quick_search",
        "proboxer",
        "amateurboxer",
        "boxer",
        "wiki",
        "forum",
        "shop",
    }
)

_LIST_LOCATION_HEADERS = ("location", "residence", "town", "city", "résidence")

_COUNTRY_CODE_LABELS = {
    "GBR": "Royaume-Uni",
    "GB": "Royaume-Uni",
    "UK": "Royaume-Uni",
    "USA": "États-Unis",
    "US": "États-Unis",
    "FRA": "France",
    "FR": "France",
    "DEU": "Allemagne",
    "DE": "Allemagne",
    "IRL": "Irlande",
    "IE": "Irlande",
    "GD": "Grenada",
    "GRD": "Grenada",
    "VEN": "Venezuela",
    "VE": "Venezuela",
    "PRI": "Puerto Rico",
    "PR": "Puerto Rico",
    "ESP": "Spain",
    "ES": "Spain",
}


def _person_href_match(href: str) -> re.Match[str] | None:
    if not href:
        return None
    m = _PERSON_HREF_RE.search(href)
    if m:
        return m
    generic = re.search(r"/en/([a-z][a-z0-9_]*)/(\d+)(?:/|$|\?|#)", href, re.I)
    if generic and generic.group(1).lower() not in _NON_PERSON_PATH_SEGMENTS:
        return generic
    return None


def _list_column_index(headers: list[str], names: tuple[str, ...]) -> int:
    for name in names:
        if name in headers:
            return headers.index(name)
    return -1


def _find_list_table(soup: BeautifulSoup):
    best = None
    best_count = 0
    for table in soup.select("table.dataTable, table"):
        count = sum(1 for a in table.select("a[href]") if _person_href_match(a.get("href", "")))
        if count > best_count:
            best = table
            best_count = count
    return best


def extract_search_country_from_html(html: str) -> str:
    """Pays de recherche depuis le formulaire ou le titre de page BoxRec."""
    soup = BeautifulSoup(html, "html.parser")
    for selector in (
        'input[name="l[loc_txt]"]',
        'input[name*="loc_txt"]',
        'input[name="l[location]"]',
    ):
        inp = soup.select_one(selector)
        if inp and inp.get("value", "").strip():
            value = inp["value"].strip()
            if not re.fullmatch(r"[a-z]{2,3}_?", value, re.I):
                return value
    for form in soup.select("form"):
        action = form.get("action") or ""
        if "locations/people" in action or 'name="l[role]"' in str(form):
            from_form = extract_search_country_from_url(urljoin("https://boxrec.com", action))
            if from_form:
                return from_form
    for a in soup.select('a[href*="locations/people"]'):
        from_link = extract_search_country_from_url(urljoin("https://boxrec.com", a.get("href", "")))
        if from_link:
            return from_link
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if title:
        m = re.search(r"\b(?:in|near|around)\s+(.+?)(?:\s*[-|]|$)", title, re.I)
        if m:
            return m.group(1).strip()
    return ""


def extract_search_country_from_url(url: str) -> str:
    """Pays ciblé par la recherche BoxRec (paramètres l[loc_txt], l[country], etc.)."""
    if not url:
        return ""
    if "?" in url:
        qs = parse_qs(urlparse(url).query)
        loc_txt = (qs.get("l[loc_txt]") or [""])[0].strip()
        if loc_txt:
            return loc_txt
        country = (qs.get("l[country]") or [""])[0].strip().upper()
        if country:
            return _COUNTRY_CODE_LABELS.get(country, country)
        level = (qs.get("l[level_id]") or [""])[0].strip().upper()
        if level in _COUNTRY_CODE_LABELS:
            return _COUNTRY_CODE_LABELS[level]
        location = (qs.get("l[location]") or [""])[0].strip().lower()
        if location.startswith("gb"):
            return _COUNTRY_CODE_LABELS["GB"]
        code = re.match(r"([a-z]{2,3})_?", location)
        if code:
            mapped = _COUNTRY_CODE_LABELS.get(code.group(1).upper())
            if mapped:
                return mapped
    return ""


def is_login_page(html: str) -> bool:
    lowered = html.lower()
    return "/login" in lowered and (
        "please login" in lowered or 'name="_username"' in lowered
    )


def extract_login_form_data(html: str) -> dict[str, str]:
    """Extrait le jeton CSRF et l'URL d'action du formulaire de connexion BoxRec."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.select_one('form[action*="/login"]')
    if not form:
        return {}
    data: dict[str, str] = {}
    csrf = form.select_one('input[name="_csrf_token"]')
    if csrf and csrf.get("value"):
        data["_csrf_token"] = str(csrf["value"]).strip()
    action = (form.get("action") or "/en/login").strip()
    data["_form_action"] = urljoin("https://boxrec.com", action)
    return data


def _normalize_phone(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    digits = re.sub(r"\D", "", text)
    if len(digits) < 7:
        return ""
    return text


def _decode_cfemail(hex_str: str) -> str:
    """Décode data-cfemail (protection Cloudflare sur BoxRec)."""
    if not hex_str or len(hex_str) < 4:
        return ""
    key = int(hex_str[:2], 16)
    chars: list[str] = []
    for i in range(2, len(hex_str), 2):
        chars.append(chr(int(hex_str[i : i + 2], 16) ^ key))
    return "".join(chars)


_CFEMAIL_RE = re.compile(r'data-cfemail=["\']([a-f0-9]+)["\']', re.I)

_EMAIL_LABELS = frozenset({"email", "e-mail", "courriel", "mail"})
_PHONE_LABELS = frozenset(
    {
        "phone",
        "phones",
        "telephone",
        "telephones",
        "téléphones",
        "téléphone",
        "tel",
        "mobile",
        "cell",
        "fax",
    }
)
_ADDRESS_LABELS = frozenset(
    {"residence", "company", "address", "adresse", "résidence", "société"}
)


def _find_profile_sections(soup: BeautifulSoup) -> list[Any]:
    sections: list[Any] = []
    for table in soup.select("table"):
        if table.select_one("td.rowLabel, th.rowLabel"):
            sections.append(table)
    if sections:
        return sections
    h1 = soup.select_one("h1")
    if h1:
        node = h1.parent
        for _ in range(16):
            if node is None:
                break
            if node.select_one(
                "tr td.rowLabel, tr.drawRowBorder, tr th, a[href^='mailto:'], [data-cfemail]"
            ):
                return [node]
            node = node.parent
    return [soup.body] if soup.body else [soup]


def _profile_content_scope(soup: BeautifulSoup):
    h1 = soup.select_one("h1")
    if not h1:
        return soup.body or soup
    node = h1.parent
    for _ in range(20):
        if node is None:
            break
        if node.select_one(
            "[data-cfemail], a[href^='mailto:'], td.rowLabel, tr.drawRowBorder"
        ):
            return node
        node = node.parent
    return soup.body or soup


def _scan_profile_contacts_globally(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    emails: list[str] = []
    phones: list[str] = []
    scope = _profile_content_scope(soup)
    for cf in scope.select("[data-cfemail]"):
        decoded = _decode_cfemail(str(cf.get("data-cfemail", "")))
        if decoded and "@" in decoded and "boxrec.com" not in decoded.lower():
            emails.append(decoded)
    for mail in scope.select('a[href^="mailto:"]'):
        e = mail.get("href", "").replace("mailto:", "").split("?")[0].strip()
        if e and "@" in e and "boxrec.com" not in e.lower():
            emails.append(e)
    for tel in scope.select('a[href^="tel:"]'):
        _add_phones_from_text(tel.get("href", "").replace("tel:", ""), phones)
    return emails, phones


def _row_label_name(row) -> str:
    cell = row.select_one("td.rowLabel, th.rowLabel, th")
    if not cell:
        return ""
    bold = cell.select_one("b")
    text = bold.get_text(" ", strip=True) if bold else cell.get_text(" ", strip=True)
    return text.lower().rstrip(":")


def _row_value_cells(row) -> list:
    """Cellules valeur (hors rowLabel) — gère drapeau + texte sur plusieurs colonnes."""
    label_cell = row.select_one("td.rowLabel, th.rowLabel")
    value_cells = [
        td
        for td in row.find_all("td", recursive=False)
        if "rowLabel" not in (td.get("class") or [])
    ]
    if not value_cells:
        tds = row.find_all("td")
        if label_cell:
            value_cells = [
                td for td in tds if td != label_cell and "rowLabel" not in (td.get("class") or [])
            ]
        elif len(tds) >= 2:
            value_cells = [tds[-1]]
    if not value_cells:
        th = row.select_one("th")
        td = row.select_one("td")
        if th and td and th != label_cell:
            value_cells = [td]
    return value_cells


def _cells_combined_text(cells: list) -> str:
    parts = [c.get_text(" ", strip=True) for c in cells if c.get_text(strip=True)]
    return " ".join(parts)


def _label_matches(label: str, keys: frozenset[str]) -> bool:
    return any(label == k or label.startswith(k) for k in keys)


def _extract_profile_fields_fallback(html: str) -> tuple[str, str, str]:
    emails: list[str] = []
    phones: list[str] = []
    address_parts: list[str] = []
    chunk = re.split(r"<h2[\s>]", html, maxsplit=1, flags=re.I)[0]
    row_re = re.compile(
        r"<tr[^>]*>[\s\S]*?<(?:td|th)[^>]*\browLabel\b[^>]*>[\s\S]*?"
        r"<b>\s*([^<]+?)\s*</b>[\s\S]*?</(?:td|th)>((?:\s*<td[^>]*>[\s\S]*?</td>)+)",
        re.I,
    )
    for label_raw, cells_html in row_re.findall(chunk):
        label = label_raw.strip().lower().rstrip(":")
        cell_text = re.sub(r"<[^>]+>", " ", cells_html)
        cell_text = re.sub(r"\s+", " ", cell_text).strip()
        cell_html = cells_html
        if _label_matches(label, _EMAIL_LABELS):
            cf = re.search(r'data-cfemail=["\']([a-f0-9]+)["\']', cell_html, re.I)
            if cf:
                decoded = _decode_cfemail(cf.group(1))
                if decoded and "@" in decoded and "boxrec.com" not in decoded.lower():
                    emails.append(decoded)
            m = EMAIL_RE.search(cell_text)
            if m and "boxrec.com" not in m.group(0).lower():
                emails.append(m.group(0))
        if _label_matches(label, _PHONE_LABELS):
            _add_phones_from_text(cell_text, phones)
        if _label_matches(label, _ADDRESS_LABELS) and cell_text:
            address_parts.append(cell_text)
    email = emails[0] if emails else ""
    phone = " ; ".join(dict.fromkeys(phones)) if phones else ""
    address = " — ".join(dict.fromkeys(address_parts)) if address_parts else ""
    return email, phone, address


def _add_phones_from_text(text: str, phones: list[str]) -> None:
    for part in re.split(r"[\n,;|/]+", text):
        p = part.strip()
        if not p:
            continue
        for m in re.finditer(r"\+\d[\d\s().-]{6,}", p):
            phones.append(m.group(0).strip())
        normalized = _normalize_phone(p)
        if normalized:
            phones.append(normalized)


def _extract_profile_fields(soup: BeautifulSoup, html: str = "") -> tuple[str, str, str]:
    emails: list[str] = []
    phones: list[str] = []
    address_parts: list[str] = []

    for root in _find_profile_sections(soup):
        for row in root.select("tr"):
            value_cells = _row_value_cells(row)
            if not value_cells:
                continue
            label = _row_label_name(row)
            value = _cells_combined_text(value_cells)
            for value_cell in value_cells:
                for cf in value_cell.select("[data-cfemail]"):
                    decoded = _decode_cfemail(str(cf.get("data-cfemail", "")))
                    if decoded and "@" in decoded and "boxrec.com" not in decoded.lower():
                        emails.append(decoded)
                if _label_matches(label, _EMAIL_LABELS):
                    for mail in value_cell.select('a[href^="mailto:"]'):
                        e = mail.get("href", "").replace("mailto:", "").split("?")[0].strip()
                        if e and "@" in e and "boxrec.com" not in e.lower():
                            emails.append(e)
            if _label_matches(label, _EMAIL_LABELS):
                m = EMAIL_RE.search(value)
                if m and "boxrec.com" not in m.group(0).lower():
                    emails.append(m.group(0))
            if _label_matches(label, _PHONE_LABELS):
                _add_phones_from_text(value, phones)
                for value_cell in value_cells:
                    for tel in value_cell.select('a[href^="tel:"]'):
                        _add_phones_from_text(tel.get("href", "").replace("tel:", ""), phones)
            if _label_matches(label, _ADDRESS_LABELS) and value:
                address_parts.append(value)

    global_emails, global_phones = _scan_profile_contacts_globally(soup)
    emails.extend(global_emails)
    phones.extend(global_phones)

    email = emails[0] if emails else ""
    phone = " ; ".join(dict.fromkeys(phones)) if phones else ""
    address = " — ".join(dict.fromkeys(address_parts)) if address_parts else ""

    if html and (not email or not phone):
        fe, fp, fa = _extract_profile_fields_fallback(html)
        if not email and fe:
            email = fe
        if not phone and fp:
            phone = fp
        if not address and fa:
            address = fa
    return email, phone, address


def _extract_email_phone_from_soup(soup: BeautifulSoup) -> tuple[str, str]:
    email, phone, _address = _extract_profile_fields(soup)
    return email, phone


def _find_row_profile_link(tr) -> Any | None:
    for a in tr.select("a.personLink, a[href]"):
        if _person_href_match(a.get("href", "")):
            return a
    return None


def _extract_row_location(tds, headers: list[str], link_td) -> str:
    loc_idx = _list_column_index(headers, _LIST_LOCATION_HEADERS)
    if loc_idx >= 0 and loc_idx < len(tds):
        return tds[loc_idx].get_text(" ", strip=True)
    for td in tds:
        if td == link_td:
            continue
        if td.select_one("img[src*='flag'], img[alt]"):
            text = td.get_text(" ", strip=True)
            if text:
                return text
    if len(tds) > 1:
        for td in tds[1:]:
            if td == link_td:
                continue
            text = td.get_text(" ", strip=True)
            if text and not re.fullmatch(r"\d+", text) and text not in {"♂", "♀", "male", "female"}:
                return text
    return ""


def _extract_row_company(tds, headers: list[str]) -> str:
    company_idx = _list_column_index(headers, ("company", "société", "societe"))
    if company_idx >= 0 and company_idx < len(tds):
        return tds[company_idx].get_text(" ", strip=True)
    return ""


def parse_list_page(
    html: str,
    base_url: str = "https://boxrec.com",
    list_url: str | None = None,
) -> dict[str, Any]:
    """Extrait les personnes et métadonnées de pagination d'une page liste."""
    soup = BeautifulSoup(html, "html.parser")
    search_country = extract_search_country_from_url(list_url or "") or extract_search_country_from_html(html)
    people: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    table = _find_list_table(soup)
    if table:
        header_row = table.select_one("tr:has(th)") or table.select_one("tr")
        header_cells = header_row.select("th") if header_row else []
        if not header_cells and header_row:
            header_cells = header_row.find_all("td")
        headers = [th.get_text(" ", strip=True).lower() for th in header_cells]
        for tr in table.select("tr"):
            if tr.find("th") and tr != header_row:
                continue
            link = _find_row_profile_link(tr)
            if not link:
                continue
            href = link.get("href", "")
            full_url = urljoin(base_url, href)
            name = link.get_text(" ", strip=True)
            match = _person_href_match(href)
            person_id = match.group(2) if match else ""
            if person_id and person_id in seen_ids:
                continue
            if person_id:
                seen_ids.add(person_id)

            tds = tr.find_all("td")
            link_td = link.find_parent("td")
            location = _extract_row_location(tds, headers, link_td)
            company = _extract_row_company(tds, headers)
            address = company

            people.append(
                {
                    "id": person_id,
                    "name": name,
                    "profile_url": full_url,
                    "location": location,
                    "search_country": search_country,
                    "address": address,
                    "email": "",
                    "phone": "",
                }
            )

    if not people:
        for link in soup.select("a.personLink, a[href]"):
            href = link.get("href", "")
            match = _person_href_match(href)
            if not match:
                continue
            pid = match.group(2)
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            people.append(
                {
                    "id": pid,
                    "name": link.get_text(" ", strip=True),
                    "profile_url": urljoin(base_url, href),
                    "location": "",
                    "search_country": search_country,
                    "address": "",
                    "email": "",
                    "phone": "",
                }
            )

    next_offset = None
    page_size = len(people) if people else 20
    offsets: list[int] = []
    for a in soup.select('a[href*="offset="]'):
        href = a.get("href", "")
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        if "offset" in qs:
            try:
                offsets.append(int(qs["offset"][0]))
            except (ValueError, IndexError):
                pass
    current_offset = 0
    for inp in soup.select('input[name="offset"]'):
        try:
            current_offset = int(inp.get("value", 0))
        except ValueError:
            pass

    if offsets:
        higher = [o for o in offsets if o > current_offset]
        if higher:
            next_offset = min(higher)
    elif people:
        next_offset = current_offset + page_size

    total_text = ""
    for node in soup.find_all(
        string=re.compile(r"\d+\s+(?:results?|people|personnes?)", re.I)
    ):
        total_text = str(node)
        break

    return {
        "people": people,
        "search_country": search_country,
        "next_offset": next_offset,
        "page_size": page_size,
        "has_more": bool(people) and next_offset is not None,
        "total_hint": total_text.strip(),
        "is_login_page": is_login_page(html),
    }


def parse_profile_page(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    email, phone, address = _extract_profile_fields(soup, html)
    name = ""
    h1 = soup.select_one("h1") or soup.select_one(".personName")
    if h1:
        name = h1.get_text(" ", strip=True)
    return {"name": name, "email": email, "phone": phone, "address": address}


def merge_profile_into_person(person: dict[str, str], profile: dict[str, str]) -> dict[str, str]:
    if profile.get("name") and not person.get("name"):
        person["name"] = profile["name"]
    if profile.get("email"):
        person["email"] = profile["email"]
    if profile.get("phone"):
        person["phone"] = profile["phone"]
    if profile.get("address"):
        person["address"] = profile["address"]
        if not person.get("location"):
            person["location"] = profile["address"]
    return person
