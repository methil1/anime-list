"""マイページ「次に見る」の並び順(index.html の nextUpCompare)の単体テスト。実行: python -m pytest tests

index.html の `// ==NEXTUP-ORDER-BEGIN==` 〜 `// ==NEXTUP-ORDER-END==` を切り出して node で評価する。"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node が無い")


def order_block():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    m = re.search(r"// ==NEXTUP-ORDER-BEGIN==[^\n]*\n(.*?)// ==NEXTUP-ORDER-END==", html, re.S)
    assert m, "index.html に NEXTUP-ORDER ブロックが無い"
    return m.group(1)


def sort_titles(items):
    js = order_block() + "\nprocess.stdout.write(JSON.stringify(%s.sort(nextUpCompare).map(o => o.a.t)));" % json.dumps(items)
    out = subprocess.run(["node"], input=js, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def item(t, as_="airing", day=None, mins=0, y=2026):
    slot = None if day is None else {"day": day, "mins": mins, "time": ""}
    return {"a": {"t": t, "y": y}, "as": as_, "slot": slot}


def test_airing_sorted_sunday_to_saturday():
    items = [item("土", day=6, mins=1380), item("月", day=1, mins=1380), item("日", day=0, mins=1380)]
    assert sort_titles(items) == ["日", "月", "土"]


def test_same_day_sorted_by_time():
    items = [item("深夜", day=3, mins=1430), item("夕方", day=3, mins=1080), item("夜", day=3, mins=1380)]
    assert sort_titles(items) == ["夕方", "夜", "深夜"]


def test_upcoming_joins_calendar_order():
    items = [item("火", day=2), item("放送前の月", as_="upcoming", day=1)]
    assert sort_titles(items) == ["放送前の月", "火"]


def test_unknown_slot_after_scheduled_then_finished_last():
    items = [
        item("完結2020", as_="finished", day=0, y=2020),
        item("枠不明", day=None),
        item("完結2024", as_="finished", y=2024),
        item("土", day=6),
    ]
    assert sort_titles(items) == ["土", "枠不明", "完結2024", "完結2020"]
