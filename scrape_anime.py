#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AniList から TV アニメ一覧を年×クール（季節）ごとに取得し、
ブラウザの file:// から読める anime-data.js を生成する。

使い方:
    python scrape_anime.py            # 2000年WINTER 〜 現在クール
    python scrape_anime.py 2010       # 開始年を指定

仕様:
  - format: TV のみ（TV_SHORT / OVA / 映画 / ONA は除外）
  - 連続2クール以上の作品は AniList の season/seasonYear（=放送開始クール）に
    1回だけ出るため、そのまま開始クールへ配置される。
  - isAdult は除外。
  - 出力は window.ANIME_CATALOG への代入（CORS回避のため .json ではなく .js）。
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import date

API_URL = "https://graphql.anilist.co"
OUT_PATH = "anime-data.js"

# 季節の順序（暦順）。AniList enum は WINTER / SPRING / SUMMER / FALL
SEASONS = ["WINTER", "SPRING", "SUMMER", "FALL"]
SEASON_MONTH = {"WINTER": 1, "SPRING": 4, "SUMMER": 7, "FALL": 10}

# ジャンルの日本語化（無いものは原文のまま）
GENRE_JA = {
    "Action": "アクション", "Adventure": "冒険", "Comedy": "コメディ",
    "Drama": "ドラマ", "Fantasy": "ファンタジー", "Sci-Fi": "SF",
    "Romance": "恋愛", "Slice of Life": "日常", "Sports": "スポーツ",
    "Mystery": "ミステリー", "Horror": "ホラー", "Supernatural": "超常",
    "Thriller": "スリラー", "Psychological": "心理", "Mecha": "メカ",
    "Music": "音楽", "Ecchi": "エッチ", "Mahou Shoujo": "魔法少女",
    "Hentai": "成人向け",
}

QUERY = """
query ($season: MediaSeason, $year: Int, $page: Int, $formats: [MediaFormat]) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    media(season: $season, seasonYear: $year, format_in: $formats, sort: POPULARITY_DESC, isAdult: false) {
      id
      title { romaji native }
      episodes
      season
      seasonYear
      format
      averageScore
      genres
      coverImage { medium }
    }
  }
}
"""


def post(query, variables, retries=5):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AnimeCatalog/1.0",
        },
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", "60")) + 1
                print(f"    rate limited, waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            if e.code >= 500:
                print(f"    server error {e.code}, retry in 5s...", flush=True)
                time.sleep(5)
                continue
            raise
        except urllib.error.URLError as e:
            print(f"    network error ({e}), retry in 5s...", flush=True)
            time.sleep(5)
    raise RuntimeError("max retries exceeded")


def season_list(start_year):
    """start_year WINTER 〜 今日の属するクールまでを列挙。"""
    today = date.today()
    cur_year = today.year
    cur_season_idx = (today.month - 1) // 3  # 0=WINTER..3=FALL
    out = []
    for y in range(start_year, cur_year + 1):
        for i, s in enumerate(SEASONS):
            if y == cur_year and i > cur_season_idx:
                break
            out.append((y, s))
    return out


def fetch_list(year, season, formats):
    items = []
    page = 1
    while True:
        data = post(QUERY, {"season": season, "year": year, "page": page, "formats": formats})
        if "errors" in data:
            print(f"    GraphQL error: {data['errors']}", flush=True)
            break
        pg = data["data"]["Page"]
        items.extend(pg["media"])
        if not pg["pageInfo"]["hasNextPage"]:
            break
        page += 1
        time.sleep(1.2)
    return items


# AniList の format → 出力フィールド f
FMT = {"TV": "TV", "TV_SHORT": "SHORT", "MOVIE": "MOVIE"}


def main():
    start_year = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    seasons = season_list(start_year)
    years = sorted({y for (y, _s) in seasons})
    print(f"対象: {start_year} 〜 現在 / TV・ショート {len(seasons)}クール + 劇場版 {len(years)}年分", flush=True)

    seen = {}

    def ingest(media, year, season, force_movie=False):
        for m in media:
            if m["id"] in seen:
                continue
            title = m["title"]
            genres = [GENRE_JA.get(g, g) for g in (m.get("genres") or [])[:3]]
            fmt = m.get("format") or ("MOVIE" if force_movie else "TV")
            seen[m["id"]] = {
                "id": m["id"],
                "t": title.get("native") or title.get("romaji") or "(不明)",
                "tr": title.get("romaji") or "",
                "y": m.get("seasonYear") or year,
                "s": "MOVIE" if fmt == "MOVIE" else (m.get("season") or season),
                "f": FMT.get(fmt, "TV"),
                "ep": m.get("episodes"),
                "img": (m.get("coverImage") or {}).get("medium") or "",
                "sc": m.get("averageScore"),
                "g": genres,
            }

    # TV / ショート: 季節（クール）ごと
    for n, (year, season) in enumerate(seasons, 1):
        print(f"[TV/SHORT {n}/{len(seasons)}] {year} {season} ...", flush=True)
        media = fetch_list(year, season, ["TV", "TV_SHORT"])
        ingest(media, year, season)
        print(f"    取得 {len(media)} 件 / 累計 {len(seen)} 件", flush=True)
        time.sleep(1.2)

    # 劇場版: 年ごと（season 指定なし）
    for n, year in enumerate(years, 1):
        print(f"[MOVIE {n}/{len(years)}] {year} ...", flush=True)
        media = fetch_list(year, None, ["MOVIE"])
        ingest(media, year, None, force_movie=True)
        print(f"    取得 {len(media)} 件 / 累計 {len(seen)} 件", flush=True)
        time.sleep(1.2)

    order = {"WINTER": 0, "SPRING": 1, "SUMMER": 2, "FALL": 3, "MOVIE": 4}
    anime = sorted(seen.values(), key=lambda a: (-a["y"], order.get(a["s"], 9)))
    payload = {
        "generated": date.today().isoformat(),
        "source": "AniList (https://anilist.co)",
        "count": len(anime),
        "anime": anime,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("// 自動生成ファイル — scrape_anime.py により AniList から取得\n")
        f.write("window.ANIME_CATALOG = ")
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    print(f"\n完了: {OUT_PATH} に {len(anime)} 作品を書き出しました。", flush=True)


if __name__ == "__main__":
    main()
