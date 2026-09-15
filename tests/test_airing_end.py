"""airing_end_int（放送終了日の算出）の単体テスト。実行: python -m pytest tests"""
import calendar
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scrape_anime as sa  # noqa: E402

TODAY = date(2026, 9, 15)


def jst(y, mo, d, h=0):
    """JST の日時を unix 秒にする。"""
    return calendar.timegm((y, mo, d, h, 0, 0)) - sa.JST_OFFSET_SECONDS


def media(status="RELEASING", episodes=None, schedule=(), end=None):
    return {
        "status": status,
        "episodes": episodes,
        "endDate": {"year": end[0], "month": end[1], "day": end[2]} if end else {},
        "airingSchedule": {"nodes": [{"episode": e, "airingAt": at} for e, at in schedule]},
    }


def test_uses_last_scheduled_episode_date_in_jst():
    # 12/16 23:30 JST（UTC では 12/16 14:30）
    m = media(episodes=24, schedule=[(1, jst(2026, 7, 8, 23)), (24, jst(2026, 12, 16, 23))])
    assert sa.airing_end_int(m, TODAY) == 20261216


def test_late_night_airing_keeps_jst_date():
    # 9/27 01:00 JST は UTC だと 9/26。JST の日付で返すこと。
    m = media(episodes=12, schedule=[(12, jst(2026, 9, 27, 1))])
    assert sa.airing_end_int(m, TODAY) == 20260927


def test_extrapolates_weekly_when_schedule_is_shorter_than_episodes():
    m = media(episodes=26, schedule=[(25, jst(2026, 9, 19, 22))])
    assert sa.airing_end_int(m, TODAY) == 20260926


def test_prefers_later_end_date():
    m = media(episodes=12, schedule=[(12, jst(2026, 9, 20, 22))], end=(2026, 9, 27))
    assert sa.airing_end_int(m, TODAY) == 20260927


def test_end_date_only():
    m = media(status="FINISHED", episodes=12, end=(2026, 3, 28))
    assert sa.airing_end_int(m, TODAY) == 20260328


def test_releasing_with_stale_schedule_is_untrusted():
    # 放送中なのに予定表が7月で止まっている＝未登録分があるので判定しない
    m = media(schedule=[(1, jst(2026, 7, 5, 9))])
    assert sa.airing_end_int(m, TODAY) is None


def test_finished_in_the_past_is_trusted():
    m = media(status="FINISHED", episodes=10, schedule=[(10, jst(2026, 9, 1, 22))])
    assert sa.airing_end_int(m, TODAY) == 20260901


def test_no_information_returns_none():
    assert sa.airing_end_int(media(), TODAY) is None
