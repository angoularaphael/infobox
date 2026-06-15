"""Validation partagée e-mail / téléphone pour managers et promoteurs."""

from __future__ import annotations

import re

SPAM_EMAIL_SUBSTRINGS = (
    "casino",
    "alexandercasino",
    "bet365",
    "poker",
    "slots",
    "gambling",
    "1xbet",
    "bookmaker",
)

GENERIC_SHARED_EMAILS = frozenset(
    {
        "bonjour@alfieformation.com",
        "contact@alexandercasino.casino",
    }
)

ISBN_PREFIXES = ("978", "979")


def normalize_phone_digits(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def fix_doubled_phone(digits: str) -> str | None:
    if len(digits) < 16 or len(digits) % 2 != 0:
        return None
    half = len(digits) // 2
    if digits[:half] == digits[half:]:
        return digits[:half]
    return None


def looks_like_date_phone(digits: str) -> bool:
    if len(digits) != 8:
        return False
    if not re.match(r"^(19|20)\d{6}$", digits):
        return False
    month = int(digits[4:6])
    day = int(digits[6:8])
    if 1 <= month <= 12 and 1 <= day <= 31:
        return True
    year_a = int(digits[:4])
    year_b = int(digits[4:])
    return 1900 <= year_a <= 2100 and 1900 <= year_b <= 2100


def looks_like_isbn(digits: str) -> bool:
    if len(digits) == 13 and digits.startswith(ISBN_PREFIXES):
        return True
    if len(digits) == 10 and digits.isdigit() and digits.startswith(ISBN_PREFIXES[:3]):
        return True
    return False


def looks_like_scraped_garbage(digits: str) -> bool:
    """Faux positifs fréquents du scraping (IDs, dates collées, etc.)."""
    if len(digits) >= 12 and re.match(r"^20[12]\d", digits):
        return True
    if len(digits) >= 12 and len(set(digits)) <= 4:
        return True
    if len(digits) >= 11 and digits.startswith(("0" * 4, "1" * 4)):
        return True
    return False


def validate_phone(digits: str) -> tuple[str | None, str | None]:
    """Retourne (téléphone valide, erreur). Erreur None = OK.

    Format attendu : international sans + (ex. 33612345678), 10 à 15 chiffres.
    """
    if not digits:
        return None, "vide"

    doubled = fix_doubled_phone(digits)
    if doubled:
        digits = doubled

    if looks_like_date_phone(digits):
        return None, "date_yyyymmdd"

    if looks_like_isbn(digits):
        return None, "isbn"

    if looks_like_scraped_garbage(digits):
        return None, "format_suspect"

    if len(digits) > 15:
        return None, f"trop_long ({len(digits)})"

    min_len = 10
    if digits.startswith("376"):
        min_len = 9
    if len(digits) < min_len:
        return None, f"trop_court_sans_indicatif ({len(digits)})"

    if len(set(digits)) <= 2:
        return None, "chiffres_repetitifs"

    return digits, None


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def validate_email(email: str) -> tuple[str | None, str | None]:
    """Retourne (email valide, erreur). Erreur None = OK."""
    normalized = normalize_email(email)
    if not normalized:
        return None, "vide"

    if "@" not in normalized or normalized.count("@") != 1:
        return None, "format_invalide"

    local, _host = normalized.split("@", 1)
    if not local or len(local) < 2:
        return None, "format_invalide"

    if normalized in GENERIC_SHARED_EMAILS:
        return None, "email_generique_spam"

    if any(token in normalized for token in SPAM_EMAIL_SUBSTRINGS):
        return None, "domaine_spam"

    return normalized, None
