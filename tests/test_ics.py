"""放送カレンダーの .ics 書き出し(index.html の buildIcs)の単体テスト。実行: python -m pytest tests

index.html の `// ==ICS-BEGIN==` 〜 `// ==ICS-END==` を切り出して node で評価する。"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEEK = 7 * 86400
AIR = 1791036000   # 2026-10-03 23:00 JST (14:00 UTC)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node が無い")


def ics_block():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    m = re.search(r"// ==ICS-BEGIN==[^\n]*\n(.*?)// ==ICS-END==", html, re.S)
    assert m, "index.html に ICS ブロックが無い"
    return m.group(1)


def build(shows, now):
    js = ics_block() + "\nprocess.stdout.write(JSON.stringify(buildIcs(%s, %d)));" % (json.dumps(shows), now)
    out = subprocess.run(["node"], input=js, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def unfold(text):
    return text.replace("\r\n ", "")


def events(text):
    return re.findall(r"BEGIN:VEVENT\r\n(.*?)END:VEVENT", unfold(text), re.S)


def show(**kw):
    s = {"id": 1, "t": "テスト", "f": "TV", "air": AIR, "ep": 12}
    s.update(kw)
    return s


def test_wraps_in_vcalendar_with_crlf():
    r = build([show()], AIR - 1)
    assert r["text"].startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
    assert r["text"].endswith("END:VCALENDAR\r\n")
    assert "\n" not in r["text"].replace("\r\n", "")


def test_one_event_per_episode_weekly_in_utc():
    r = build([show(ep=3)], AIR - 1)
    ev = events(r["text"])
    assert len(ev) == 3 and r["events"] == 3
    assert "DTSTART:20261003T140000Z" in ev[0]
    assert "DTEND:20261003T143000Z" in ev[0]
    assert "DTSTART:20261010T140000Z" in ev[1]
    assert "SUMMARY:テスト 第1話" in ev[0]
    assert "SUMMARY:テスト 第3話" in ev[2]
    assert "UID:anime-1-ep3@methil1.github.io" in ev[2]


def test_short_is_five_minutes():
    ev = events(build([show(f="SHORT", ep=1)], AIR - 1)["text"])
    assert "DTEND:20261003T140500Z" in ev[0]


def test_skips_episodes_already_finished():
    # 2話の放送中(開始10分後)に書き出すと、1話は除外・2話は残る
    r = build([show(ep=3)], AIR + WEEK + 600)
    ev = events(r["text"])
    assert [re.search(r"第(\d+)話", e).group(1) for e in ev] == ["2", "3"]


def test_skips_shows_without_air_or_ep():
    r = build([show(id=1), show(id=2, air=None), show(id=3, ep=None), show(id=4, ep=0)], AIR - 1)
    assert r["shows"] == 1
    assert r["skipped"] == 3
    assert r["events"] == 12


def test_unknown_episode_count_runs_weekly_until_end_date():
    # 話数未発表でも放送終了日(ed, JST)が分かっていれば、その日まで毎週入れる
    r = build([show(ep=None, ed=20261017)], AIR - 1)
    ev = events(r["text"])
    assert len(ev) == 3 and r["shows"] == 1 and r["skipped"] == 0
    assert "DTSTART:20261017T140000Z" in ev[2]


def test_end_date_compares_in_jst():
    # 23:30 JST 放送は UTC だと前日。ed の日付比較は JST で行う
    air = AIR + 30 * 60 + 9 * 3600   # 2026-10-04 08:30 JST
    late = AIR + 30 * 60            # 2026-10-03 23:30 JST = 14:30 UTC
    assert len(events(build([show(air=late, ep=None, ed=20261003)], late - 1)["text"])) == 1
    assert len(events(build([show(air=air, ep=None, ed=20261003)], air - 1)["text"])) == 0


def test_escapes_text_values():
    ev = events(build([show(t="A, B; C\\D", ep=1)], AIR - 1)["text"])
    assert "SUMMARY:A\\, B\\; C\\\\D 第1話" in ev[0]


def test_folds_long_lines_at_75_octets():
    r = build([show(t="あ" * 60, ep=1)], AIR - 1)
    for line in r["text"].split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    assert "あ" * 60 in unfold(r["text"])


def test_fold_never_splits_emoji():
    title = "x" * 54 + "🎵" * 10
    r = build([show(t=title, ep=1)], AIR - 1)
    for line in r["text"].split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    assert title in unfold(r["text"])


def test_known_episodes_stop_at_end_date():
    ev = events(build([show(ep=12, ed=20261010)], AIR - 1)["text"])
    assert len(ev) == 2


def test_episode_count_over_200_falls_back_to_end_date():
    r = build([show(ep=500, ed=20261010), show(id=2, ep=500)], AIR - 1)
    assert r["events"] == 2 and r["skipped"] == 1
