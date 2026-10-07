import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_songs import needs_fetch, parse_theme  # noqa: E402

TODAY = date(2026, 9, 26)


def test_parse_theme_prefers_japanese_title():
    assert parse_theme('#1: "KAIKAIKITAN (廻廻奇譚)" by Eve (eps 1-13)') == ["廻廻奇譚", "Eve", "eps 1-13"]


def test_parse_theme_prefers_japanese_artist():
    assert parse_theme('"Lemon" by Kenshi Yonezu (米津玄師)') == ["Lemon", "米津玄師", ""]


def test_parse_theme_keeps_latin_parentheses():
    assert parse_theme('"again" by YUI (eps 1-14)') == ["again", "YUI", "eps 1-14"]


def test_parse_theme_without_number_prefix():
    assert parse_theme('"give it back" by Cö shu Nie (eps 14-)') == ["give it back", "Cö shu Nie", "eps 14-"]


def test_parse_theme_falls_back_to_raw_text():
    assert parse_theme("2: Unknown format") == ["Unknown format", "", ""]


def test_needs_fetch_when_not_fetched_yet():
    assert needs_fetch({"y": 1999}, None, TODAY, force=False)


def test_old_work_is_not_refetched():
    assert not needs_fetch({"y": 2010}, {"at": "2020-01-01"}, TODAY, force=False)


def test_recent_work_is_refetched_after_refresh_days():
    assert needs_fetch({"y": 2026}, {"at": "2026-09-01"}, TODAY, force=False)
    assert not needs_fetch({"y": 2026}, {"at": "2026-09-20"}, TODAY, force=False)


def test_force_refetches_everything():
    assert needs_fetch({"y": 2010}, {"at": "2026-09-26"}, TODAY, force=True)
