"""Map international phone digits (sans +) to French country labels (managerCountry.js)."""

from __future__ import annotations

# Longest prefixes first to avoid ambiguous matches (e.g. 351 before 35).
PHONE_PREFIX_COUNTRY: list[tuple[str, str]] = [
    ("995", "Géorgie"),
    ("507", "Panama"),
    ("420", "République tchèque"),
    ("380", "Ukraine"),
    ("376", "Andorre"),
    ("371", "Lettonie"),
    ("352", "Luxembourg"),
    ("351", "Portugal"),
    ("54", "Argentine"),
    ("49", "Allemagne"),
    ("48", "Pologne"),
    ("44", "Royaume-Uni"),
    ("43", "Autriche"),
    ("39", "Italie"),
    ("34", "Espagne"),
    ("33", "France"),
    ("32", "Belgique"),
    ("31", "Pays-Bas"),
    ("30", "Grèce"),
    ("1", "USA"),
]


def country_from_phone(digits: str) -> str | None:
    """Return French country label from international phone digits, or None."""
    if not digits:
        return None
    clean = "".join(c for c in str(digits) if c.isdigit())
    if clean.startswith("00"):
        clean = clean[2:]
    for prefix, country in PHONE_PREFIX_COUNTRY:
        if clean.startswith(prefix):
            return country
    return None
