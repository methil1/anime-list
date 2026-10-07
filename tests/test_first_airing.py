"""first_airing_at（1話の放送時刻の算出）と run_airing_refresh の air 補完の単体テスト。実行: python -m pytest tests"""
import calendar
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scrape_anime as sa  # noqa: E402


def jst(y, mo, d, h=0):
    """JST の日時を unix 秒にする。"""
    return calendar.timegm((y, mo, d, h, 0, 0)) - sa.JST_OFFSET_SECONDS


def media(schedule=(), **extra):
    m = {"id": 1, "airingSchedule": {"nodes": [{"episode": e, "airingAt": at} for e, at in schedule]}}
    m.update(extra)
    return m


def test_returns_episode_one_when_schedule_starts_at_one():
    m = media([(1, jst(2026, 10, 3, 23)), (2, jst(2026, 10, 10, 23))])
    assert sa.first_airing_at(m) == jst(2026, 10, 3, 23)


def test_back_extrapolates_when_schedule_starts_later():
    m = media([(3, jst(2026, 10, 17, 23)), (4, jst(2026, 10, 24, 23)), (5, jst(2026, 10, 31, 23))])
    assert sa.first_airing_at(m) == jst(2026, 10, 17, 23) - 2 * sa.WEEK_SECONDS


def test_picks_smallest_episode_even_if_unsorted():
    m = media([(5, jst(2026, 10, 31, 23)), (2, jst(2026, 10, 10, 23)), (4, jst(2026, 10, 24, 23))])
    assert sa.first_airing_at(m) == jst(2026, 10, 10, 23) - sa.WEEK_SECONDS


def test_ignores_unusable_nodes():
    m = {"airingSchedule": {"nodes": [
        {"episode": 1, "airingAt": None},
        {"episode": 2, "airingAt": 0},
        {"episode": "3", "airingAt": 111},
        {"episode": None, "airingAt": 222},
        {"episode": 4, "airingAt": jst(2026, 10, 24, 23)},
    ]}}
    assert sa.first_airing_at(m) == jst(2026, 10, 24, 23) - 3 * sa.WEEK_SECONDS


def test_returns_none_without_schedule():
    assert sa.first_airing_at(media()) is None
    assert sa.first_airing_at({}) is None
    assert sa.first_airing_at({"airingSchedule": None}) is None
    assert sa.first_airing_at({"airingSchedule": {"nodes": None}}) is None


def _run_refresh(monkeypatch, records, medias):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 7)

    written = []
    monkeypatch.setattr(sa, "date", FakeDate)
    monkeypatch.setattr(sa, "load_existing", lambda: {"anime": records})
    monkeypatch.setattr(sa, "post", lambda q, v: {"data": {"Page": {"media": medias}}})
    monkeypatch.setattr(sa, "write_catalog", lambda anime: written.append(anime))
    monkeypatch.setattr(sa.time, "sleep", lambda s: None)
    sa.run_airing_refresh()
    return written


def test_refresh_sets_air_and_keeps_existing_when_no_schedule(monkeypatch):
    first = jst(2026, 10, 3, 23)
    records = [
        {"id": 1, "f": "TV", "y": 2026, "ed": 20261231},
        {"id": 2, "f": "TV", "y": 2026, "ed": 20261231, "air": 12345},
    ]
    medias = [
        media([(2, first + sa.WEEK_SECONDS)], id=1, episodes=12, status="RELEASING"),
        media([], id=2, episodes=12, status="RELEASING"),
    ]
    _run_refresh(monkeypatch, records, medias)
    assert records[0]["air"] == first
    assert records[1]["air"] == 12345
