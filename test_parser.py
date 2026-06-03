"""Tests unitaires légers du parseur (sans réseau)."""
from pathlib import Path

from scraper.parser import extract_search_country_from_url, parse_list_page, parse_profile_page

FIX = Path(__file__).parent / "fixtures"


def test_list_page():
    html = (FIX / "list_manager_p0.html").read_text(encoding="utf-8")
    data = parse_list_page(html)
    assert len(data["people"]) == 2
    assert data["people"][0]["name"] == "John Smith"
    assert data["people"][0]["id"] == "100001"


def test_profile_page():
    html = (FIX / "profile_manager.html").read_text(encoding="utf-8")
    prof = parse_profile_page(html)
    assert prof["email"] == "john.smith@example.com"
    assert "7946" in prof["phone"]


def test_search_country_from_url():
    url = (
        "https://boxrec.com/en/locations/people?"
        "l[role]=manager&l[loc_txt]=United%20Kingdom&l[location]=gb_15599&l[level_id]=gb"
    )
    assert extract_search_country_from_url(url) == "United Kingdom"


def test_profile_cfemail():
    html = (FIX / "profile_manager_cf.html").read_text(encoding="utf-8")
    prof = parse_profile_page(html)
    assert prof["email"] == "Kaozboxing@yahoo.com"
    assert "2678808330" in prof["phone"]
    assert "Kaoz boxing" in prof["address"]


def test_profile_flag_columns():
    html = (FIX / "profile_manager_flag.html").read_text(encoding="utf-8")
    prof = parse_profile_page(html)
    assert prof["email"] == "edgars.kukainis@inbox.lv"
    assert "29991704" in prof["phone"]
    assert "Riga" in prof["address"]


if __name__ == "__main__":
    test_list_page()
    test_profile_page()
    test_search_country_from_url()
    test_profile_cfemail()
    test_profile_flag_columns()
    print("OK — parseur")
