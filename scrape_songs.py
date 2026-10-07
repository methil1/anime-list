#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
各作品の OP/ED 曲名を MyAnimeList 公式 API から取得し、songs-data.js に保存する。
右クリックメニュー「🎵 OP/ED曲を動画サイトで探す」の曲リストに使う。

使い方:
    python scrape_songs.py            # 未取得の作品＋直近作(今年・去年)の古い取得分を取得
    python scrape_songs.py --force    # 全作品を取り直す
    python scrape_songs.py --limit 200
                                      # 今回は最大200件まで（様子見・分割実行用）

Client ID（MAL の API 設定 https://myanimelist.net/apiconfig で発行）は
環境変数 MAL_CLIENT_ID か、このフォルダの .mal_client_id ファイル（gitignore 済み）から読む。

出力: window.ANIME_SONGS = {"<AniList ID>": {"op": [[曲名, 歌手, 話数]], "ed": [...], "at": "YYYY-MM-DD"}}
  - 曲が無い作品も {"at": ...} だけ入れて「取得済み」とする（中断後の再実行で続きから）。
  - 曲名・歌手は、括弧書きの日本語表記があればそちらを採用する。
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

from scrape_anime import MAL_ID_QUERY, load_existing, post

OUT_PATH = "songs-data.js"
CLIENT_ID_FILE = ".mal_client_id"
MAL_API = "https://api.myanimelist.net/v2/anime/{}?fields=opening_themes,ending_themes"
REQUEST_INTERVAL = 0.6          # MAL API への間隔（秒）。公式の上限は非公開なので控えめに
REFRESH_DAYS = 14               # 直近作はこの日数より古い取得分を取り直す（曲は放送後に判明することが多い）
CHECKPOINT_EVERY = 50           # この件数ごとに songs-data.js へ途中保存
AL_BATCH = 50                   # AniList の id_in は最大 50

JA_CHAR_RE = re.compile(r"[぀-ヿ㐀-鿿]")
TRAILING_PAREN_RE = re.compile(r"^(.*?)\s*\(([^()]+)\)\s*$")
THEME_RE = re.compile(r'^"(.+?)"\s*by\s+(.+?)\s*(?:\((eps?\s[^)]*)\))?\s*$', re.I)
NUMBER_PREFIX_RE = re.compile(r"^\s*#?\d+:\s*")


def prefer_ja(s):
    """「KAIKAIKITAN (廻廻奇譚)」→「廻廻奇譚」。括弧内が日本語ならそちらを採る。"""
    m = TRAILING_PAREN_RE.match(s)
    if m and JA_CHAR_RE.search(m.group(2)):
        return m.group(2).strip()
    return s.strip()


def parse_theme(text):
    """MAL の theme 文字列 `#1: "Title (邦題)" by Artist (eps 1-13)` を [曲名, 歌手, 話数] にする。"""
    s = NUMBER_PREFIX_RE.sub("", str(text)).strip()
    m = THEME_RE.match(s)
    if not m:
        return [s.strip('"'), "", ""]
    return [prefer_ja(m.group(1)), prefer_ja(m.group(2)), m.group(3) or ""]


def read_client_id():
    cid = os.environ.get("MAL_CLIENT_ID", "").strip()
    if not cid and os.path.exists(CLIENT_ID_FILE):
        with open(CLIENT_ID_FILE, encoding="utf-8") as f:
            cid = f.read().strip()
    return cid


def mal_themes(mal_id, client_id, retries=4):
    """MAL API から {"op": [...], "ed": [...]} を返す。作品が無い(404)は空。失敗時は None。"""
    req = urllib.request.Request(
        MAL_API.format(mal_id),
        headers={"X-MAL-CLIENT-ID": client_id, "User-Agent": "AnimeCatalog/1.0"},
    )
    for _ in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {
                "op": [parse_theme(t.get("text", "")) for t in data.get("opening_themes") or []],
                "ed": [parse_theme(t.get("text", "")) for t in data.get("ending_themes") or []],
            }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"op": [], "ed": []}
            if e.code in (401, 403):
                raise RuntimeError(f"MAL API が {e.code} を返しました。Client ID を確認してください。") from e
            if e.code == 429 or e.code >= 500:
                time.sleep(10 if e.code == 429 else 3)
                continue
            print(f"    MAL {mal_id}: HTTP {e.code}", flush=True)
            return None
        except urllib.error.URLError:
            time.sleep(3)
    return None


def load_songs():
    if not os.path.exists(OUT_PATH):
        return {}
    with open(OUT_PATH, encoding="utf-8") as f:
        txt = f.read()
    return json.loads(txt[txt.index("{"):txt.rindex("}") + 1])


def write_songs(songs):
    ordered = {k: songs[k] for k in sorted(songs, key=int)}
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write("// 自動生成ファイル — scrape_songs.py により MyAnimeList から取得\n")
        f.write("window.ANIME_SONGS = ")
        json.dump(ordered, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")


def needs_fetch(rec, entry, today, force):
    """取得対象か。未取得は常に対象。直近作(今年・去年)は古い取得分を取り直す。"""
    if force or entry is None:
        return True
    if (rec.get("y") or 0) < today.year - 1:
        return False
    try:
        fetched = date.fromisoformat(entry.get("at", "1970-01-01"))
    except ValueError:
        return True
    return today - fetched > timedelta(days=REFRESH_DAYS)


def mal_id_map(ids):
    data = post(MAL_ID_QUERY, {"ids": ids})
    if "errors" in data:
        raise RuntimeError(f"AniList error: {data['errors']}")
    return {m["id"]: m.get("idMal") for m in data["data"]["Page"]["media"]}


def run_songs(force=False, limit=None):
    client_id = read_client_id()
    if not client_id:
        print(f"MAL の Client ID が無いので曲名の取得をスキップします（環境変数 MAL_CLIENT_ID か {CLIENT_ID_FILE}）。", flush=True)
        return
    today = date.today()
    anime = load_existing().get("anime", [])
    songs = load_songs()
    todo = [a["id"] for a in anime if needs_fetch(a, songs.get(str(a["id"])), today, force)]
    if limit:
        todo = todo[:limit]
    print(f"OP/ED曲の取得対象: {len(todo)} 件（MAL API・約{REQUEST_INTERVAL}秒/件）", flush=True)

    done = found = failed = 0
    for i in range(0, len(todo), AL_BATCH):
        ids = todo[i:i + AL_BATCH]
        malmap = mal_id_map(ids)
        for aid in ids:
            mal = malmap.get(aid)
            themes = mal_themes(mal, client_id) if mal else {"op": [], "ed": []}
            if mal:
                time.sleep(REQUEST_INTERVAL)
            if themes is None:
                failed += 1        # 取得失敗は記録しない＝次回また取りに行く
                continue
            entry = {k: v for k, v in themes.items() if v}
            entry["at"] = today.isoformat()
            songs[str(aid)] = entry
            done += 1
            found += 1 if len(entry) > 1 else 0
            if done % CHECKPOINT_EVERY == 0:
                write_songs(songs)
                print(f"    {done}/{len(todo)} 件処理（曲あり {found} 件）...", flush=True)
    write_songs(songs)
    print(f"\n完了: {done} 件処理・曲あり {found} 件・失敗 {failed} 件（{OUT_PATH} 更新済み）。", flush=True)


def main():
    args = sys.argv[1:]
    limit = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    run_songs(force="--force" in args, limit=limit)


if __name__ == "__main__":
    main()
