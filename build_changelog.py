"""git log からパッチノート（changelog.js）を生成する。

- 対象は画面に関係する種類（feat / fix / style / perf）のコミットだけ。
- バージョンは古い順に積み上げて自動採番する: 最初の対象コミットを v1.0.0 とし、
  feat で真ん中（minor）+1・右端を 0 に戻す、それ以外は右端（patch）+1。
- 開発者モード関連など、利用者に見せないコミットは EXCLUDE で除外する（番号も進めない）。

post-commit フック（.git/hooks/post-commit）から呼ばれ、差分があればそのコミットに amend で含める。
手動で実行してもよい: python build_changelog.py
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "changelog.js"

TYPES = {"feat": "新機能", "fix": "修正", "style": "見た目", "perf": "高速化"}
SUBJECT_RE = re.compile(r"^(?:@\s*)?(feat|fix|style|perf)(?:\([^)]*\))?!?:\s*(.+)$")
# 利用者に見せないコミット（開発者モード関連・開発者モード限定の機能）
EXCLUDE = re.compile(r"開発者モード|デベロッパー|developer|dev-?mode|裏コマンド|合言葉|Nyaa", re.IGNORECASE)
# 開発中の機能（おすすめ）に関する項目。番号は進め、画面では開発者モードのときだけ表示する（"dev": true）
DEV_ONLY = re.compile(r"おすすめ|レコメンド|興味なし|シリーズ")


def git_log():
    out = subprocess.run(
        ["git", "-c", "i18n.logOutputEncoding=utf-8", "log", "--reverse", "--no-merges",
         "--date=short", "--format=%ad%x1f%s"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    for line in out.splitlines():
        date, _, subject = line.partition("\x1f")
        yield date, subject


def build():
    entries = []
    minor = patch = None
    for date, subject in git_log():
        m = SUBJECT_RE.match(subject.strip())
        if not m or EXCLUDE.search(subject):
            continue
        kind, text = m.groups()
        if minor is None:
            minor, patch = 0, 0          # 最初の対象コミット = v1.0.0
        elif kind == "feat":
            minor, patch = minor + 1, 0
        else:
            patch += 1
        entry = {"v": f"1.{minor}.{patch}", "d": date, "t": TYPES[kind], "s": text}
        if DEV_ONLY.search(text):
            entry["dev"] = True
        entries.append(entry)
    entries.reverse()   # 新しい順
    body = ",\n".join(json.dumps(e, ensure_ascii=False) for e in entries)   # 1行1件
    OUT.write_text(f"// 自動生成（build_changelog.py）。手で編集しない。\nwindow.CHANGELOG = [\n{body}\n];\n",
                   encoding="utf-8", newline="\n")
    return entries


if __name__ == "__main__":
    e = build()
    print(f"{len(e)} entries, latest v{e[0]['v'] if e else '-'}")
