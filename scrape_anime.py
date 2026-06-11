#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AniList から TV / ショート / 劇場アニメ一覧を取得し、
ブラウザの file:// から読める anime-data.js を生成する。

使い方:
    python scrape_anime.py              # 全取得（TV/ショート=クール別 + 劇場=公開年別）2000〜現在
    python scrape_anime.py 2010         # 開始年を指定して全取得
    python scrape_anime.py --movies     # 劇場アニメだけ取得し、既存 anime-data.js にマージ
                                        #   （既存の TV/ショートはそのまま保持。高速）
    python scrape_anime.py --ova        # OVA だけ取得し既存にマージ（公開年別カテゴライズ）
    python scrape_anime.py --ona-jp 2000
                                        # 人気JP-ONA(配信)を pop>=floor で取得しマージ（ONA→TV扱い）
    python scrape_anime.py --range 1990 1999
                                        # 指定年範囲の TV/ショート + 劇場を取得し、既存にマージ
                                        #   （過去年代の追加に使う。既存データは保持）
    python scrape_anime.py --add "とんがり帽子のアトリエ" 200769
                                        # 個別作品をタイトル検索 or AniList ID で追加。
                                        #   ONA(配信)など通常スクレイプ対象外の作品の取りこぼし補完に使う。

仕様:
  - TV/ショート: format TV / TV_SHORT を season/seasonYear（放送開始クール）ごとに取得。
  - 劇場: format MOVIE を startDate（公開日）の年範囲で取得し、公開年でカテゴライズ。
      AniList は MOVIE に対し season 無しの seasonYear 単独フィルタを無視するため、
      seasonYear ではなく startDate_greater / startDate_lesser（FuzzyDateInt）で年を絞る。
  - isAdult は除外。
  - 出力は window.ANIME_CATALOG への代入（CORS回避のため .json ではなく .js）。
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import date

# ハングル（韓国語）を含むタイトルを除外するための判定。
# 日本のアニメリストにするため韓国作品（native/romaji がハングル）を弾く。
HANGUL_RE = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏ꥠ-꥿ힰ-퟿]")


def has_hangul(rec):
    return bool(HANGUL_RE.search(rec.get("t") or "")) or bool(HANGUL_RE.search(rec.get("tr") or ""))

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

# TV / ショート: クール（season + seasonYear）で取得
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

# 劇場 / OVA: 公開日(startDate)の年範囲で取得。型は FuzzyDateInt（Int ではない）。
YEARLY_QUERY = """
query ($dgt: FuzzyDateInt, $dlt: FuzzyDateInt, $page: Int, $fmt: MediaFormat) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    media(format: $fmt, startDate_greater: $dgt, startDate_lesser: $dlt, sort: POPULARITY_DESC, isAdult: false) {
      id
      title { romaji native }
      episodes
      season
      seasonYear
      format
      averageScore
      genres
      coverImage { medium }
      startDate { year }
    }
  }
}
"""


# 人気JP-ONA: 配信(ONA)で通常スクレイプ対象外だが主要作が多い。
# countryOfOrigin:JP で中国donghua等を除外し、人気度順に取得する。
ONA_JP_QUERY = """
query ($page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    media(format: ONA, countryOfOrigin: "JP", sort: POPULARITY_DESC, isAdult: false) {
      id
      title { romaji native }
      episodes
      season
      seasonYear
      format
      averageScore
      genres
      coverImage { medium }
      startDate { year month }
      popularity
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
    """TV/ショートをクール単位で取得。"""
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


def fetch_yearly(year, fmt, retry_on_empty=False):
    """劇場(MOVIE)/OVA を公開年(startDate)単位で取得。
    AniList が稀に空配列を返す既知の不具合があるため、retry_on_empty=True で
    0件だった場合に一度だけ再取得する。"""
    items = _fetch_yearly_once(year, fmt)
    if not items and retry_on_empty:
        print(f"    0件のため再取得 {year} {fmt} ...", flush=True)
        time.sleep(2)
        items = _fetch_yearly_once(year, fmt)
    return items


def _fetch_yearly_once(year, fmt):
    items = []
    page = 1
    # startDate は YYYYMMDD の FuzzyDateInt。年だけの作品は YYYY0000 になるため
    # 下限を year*10000-1（=YYYY 直前）にして年初の作品も取りこぼさない。
    dgt = year * 10000 - 1
    dlt = (year + 1) * 10000
    while True:
        data = post(YEARLY_QUERY, {"dgt": dgt, "dlt": dlt, "page": page, "fmt": fmt})
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


def fetch_movies(year, retry_on_empty=False):
    return fetch_yearly(year, "MOVIE", retry_on_empty)


# 個別追加用: タイトル検索 / ID 指定。ONA など通常対象外の format も取り込む。
ADD_FIELDS = "id title{romaji native} episodes season seasonYear format averageScore genres coverImage{medium} startDate{year}"
ADD_BY_ID_QUERY = "query ($id: Int) { Media(id: $id, type: ANIME) { %s } }" % ADD_FIELDS
ADD_SEARCH_QUERY = "query ($q: String) { Page(perPage: 1) { media(search: $q, type: ANIME, sort: SEARCH_MATCH) { %s } } }" % ADD_FIELDS


# AniList の format → 出力フィールド f
# MOVIE/OVA は公開年でカテゴライズ。ONA/SPECIAL は TV 扱いで該当クールに表示。
FMT = {"TV": "TV", "TV_SHORT": "SHORT", "MOVIE": "MOVIE", "OVA": "OVA"}

# 公開年(startDate)単位でカテゴライズする format（クールではなく年別ソート）
YEARLY_FORMATS = ("MOVIE", "OVA")


def make_record(m, year, season, force_fmt=None):
    """AniList の media 1件を出力レコードに変換。
    MOVIE/OVA は公開年(startDate)でカテゴライズし s=フォーマット名。"""
    title = m["title"]
    genres = [GENRE_JA.get(g, g) for g in (m.get("genres") or [])[:3]]
    fmt = m.get("format") or force_fmt or "TV"
    is_yearly = fmt in YEARLY_FORMATS
    if is_yearly:
        # 公開年を最優先（startDate.year → seasonYear → ループの year）
        yr = (m.get("startDate") or {}).get("year") or m.get("seasonYear") or year
        s = fmt
    else:
        yr = m.get("seasonYear") or year
        s = m.get("season") or season
    return {
        "id": m["id"],
        "t": title.get("native") or title.get("romaji") or "(不明)",
        "tr": title.get("romaji") or "",
        "y": yr,
        "s": s,
        "f": FMT.get(fmt, "TV"),
        "ep": m.get("episodes"),
        "img": (m.get("coverImage") or {}).get("medium") or "",
        "sc": m.get("averageScore"),
        "g": genres,
    }


# 同一年内の表示順: クール（冬春夏秋）→ OVA → 劇場
def _season_order(s):
    return {"WINTER": 0, "SPRING": 1, "SUMMER": 2, "FALL": 3, "OVA": 4, "MOVIE": 5}.get(s, 9)


def write_catalog(anime):
    # 韓国作品（ハングルタイトル）は日本のアニメリストから除外
    anime = [a for a in anime if not has_hangul(a)]
    anime = sorted(anime, key=lambda a: (-a["y"], _season_order(a["s"]), -(a.get("sc") or 0)))
    today = date.today().isoformat()
    # 生成日(created)は初回のものを引き継ぎ、更新日(generated)は毎回今日にする。
    created = today
    try:
        prev = load_existing()
        created = prev.get("created") or prev.get("generated") or today
    except Exception:
        pass
    payload = {
        "created": created,
        "generated": today,
        "source": "AniList (https://anilist.co)",
        "count": len(anime),
        "anime": anime,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("// 自動生成ファイル — scrape_anime.py により AniList から取得\n")
        f.write("window.ANIME_CATALOG = ")
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")


def load_existing():
    """既存 anime-data.js から payload(dict) を読み込む（マージ用）。"""
    with open(OUT_PATH, encoding="utf-8") as f:
        txt = f.read()
    start = txt.index("{")
    end = txt.rindex("}")
    return json.loads(txt[start:end + 1])


def movie_years(start_year):
    return list(range(start_year, date.today().year + 1))


def run_yearly_merge(fmt, start_year):
    """MOVIE/OVA を公開年単位で取得し、既存データにマージする。
    同フォーマットの既存レコードは入れ替え（他は保持）。高速。"""
    label = {"MOVIE": "劇場", "OVA": "OVA"}.get(fmt, fmt)
    out_f = FMT.get(fmt, fmt)
    existing = load_existing()
    kept = [a for a in existing.get("anime", []) if a.get("f") != out_f]
    seen_ids = {a["id"] for a in kept}
    years = movie_years(start_year)
    print(f"{label}をマージ取得: {start_year}〜{years[-1]} / 既存 {len(kept)} 件を保持", flush=True)

    fresh = []
    for n, year in enumerate(years, 1):
        print(f"[{fmt} {n}/{len(years)}] {year} ...", flush=True)
        media = fetch_yearly(year, fmt, retry_on_empty=True)
        added = 0
        for m in media:
            if m["id"] in seen_ids:
                continue
            seen_ids.add(m["id"])
            fresh.append(make_record(m, year, None, force_fmt=fmt))
            added += 1
        print(f"    取得 {len(media)} 件 / 新規 {added} 件 / {label}累計 {len(fresh)} 件", flush=True)
        time.sleep(1.2)

    write_catalog(kept + fresh)
    print(f"\n完了: {OUT_PATH} に既存 {len(kept)} + {label} {len(fresh)} = {len(kept) + len(fresh)} 作品を書き出しました。", flush=True)


def fetch_by_id(mid):
    d = post(ADD_BY_ID_QUERY, {"id": mid})
    if "errors" in d:
        print(f"    GraphQL error: {d['errors']}", flush=True)
        return None
    return d["data"]["Media"]


def search_one(title):
    d = post(ADD_SEARCH_QUERY, {"q": title})
    if "errors" in d:
        print(f"    GraphQL error: {d['errors']}", flush=True)
        return None
    arr = d["data"]["Page"]["media"]
    return arr[0] if arr else None


def run_add(queries):
    """個別作品をタイトル検索 or AniList ID で既存カタログに追加する。"""
    existing = load_existing()
    anime = list(existing.get("anime", []))
    seen = {a["id"] for a in anime}
    added = 0
    for q in queries:
        m = fetch_by_id(int(q)) if q.isdigit() else search_one(q)
        if not m:
            print(f"  見つかりませんでした: {q}", flush=True)
            continue
        rec = make_record(m, m.get("seasonYear") or date.today().year, m.get("season"))
        if rec["id"] in seen:
            print(f"  既に存在: {rec['t']}（{rec['y']} {rec['s']}）", flush=True)
            continue
        seen.add(rec["id"])
        anime.append(rec)
        added += 1
        print(f"  追加: {rec['y']} {rec['s']} {rec['f']} / {rec['t']}", flush=True)
        time.sleep(0.6)
    write_catalog(anime)
    print(f"\n完了: {added} 件を追加しました（ハングル除外後の総数は再読込で確認）。", flush=True)


def run_range_merge(lo, hi):
    """指定年範囲(lo〜hi)の TV/ショート + 劇場を取得し、既存データにマージする。
    過去年代を後から追加する用途。既存レコードは id で重複排除して保持。"""
    existing = load_existing()
    anime = list(existing.get("anime", []))
    seen_ids = {a["id"] for a in anime}
    years = list(range(lo, hi + 1))
    print(f"年範囲マージ: {lo}〜{hi} / 既存 {len(anime)} 件を保持", flush=True)

    added = 0
    # TV / ショート: 各年×4クール
    cours = [(y, s) for y in years for s in SEASONS]
    for n, (year, season) in enumerate(cours, 1):
        print(f"[TV/SHORT {n}/{len(cours)}] {year} {season} ...", flush=True)
        media = fetch_list(year, season, ["TV", "TV_SHORT"])
        for m in media:
            if m["id"] in seen_ids:
                continue
            seen_ids.add(m["id"])
            anime.append(make_record(m, year, season))
            added += 1
        print(f"    取得 {len(media)} 件 / 追加累計 {added} 件", flush=True)
        time.sleep(1.2)

    # 劇場 / OVA: 各年（公開年）
    for fmt in YEARLY_FORMATS:
        for n, year in enumerate(years, 1):
            print(f"[{fmt} {n}/{len(years)}] {year} ...", flush=True)
            media = fetch_yearly(year, fmt, retry_on_empty=True)
            cnt = 0
            for m in media:
                if m["id"] in seen_ids:
                    continue
                seen_ids.add(m["id"])
                anime.append(make_record(m, year, None, force_fmt=fmt))
                added += 1
                cnt += 1
            print(f"    取得 {len(media)} 件 / 新規 {cnt} 件 / 追加累計 {added} 件", flush=True)
            time.sleep(1.2)

    write_catalog(anime)
    print(f"\n完了: {OUT_PATH} に既存+{added}件をマージ（ハングル除外後の総数は再読込で確認）。", flush=True)


def _season_from_month(mo):
    """startDate.month から季節を推定（season が無いONA用）。"""
    return SEASONS[(mo - 1) // 3] if mo else None


def fetch_ona_jp_popular(floor):
    """人気JP-ONAを人気度降順に取得。popularity が floor を下回ったら打ち切り。"""
    items = []
    page = 1
    while True:
        data = post(ONA_JP_QUERY, {"page": page})
        if "errors" in data:
            print(f"    GraphQL error: {data['errors']}", flush=True)
            break
        pg = data["data"]["Page"]
        stop = False
        for m in pg["media"]:
            if (m.get("popularity") or 0) < floor:
                stop = True
                break
            items.append(m)
        print(f"    page {page}: 累計 {len(items)} 件", flush=True)
        if stop or not pg["pageInfo"]["hasNextPage"]:
            break
        page += 1
        time.sleep(1.0)
    return items


def run_ona_jp_merge(floor):
    """人気JP-ONAを既存カタログにマージ（ONA→TV扱いで該当クールに配置）。"""
    existing = load_existing()
    anime = list(existing.get("anime", []))
    seen = {a["id"] for a in anime}
    print(f"JP-ONA(人気pop>={floor})をマージ取得 / 既存 {len(anime)} 件を保持", flush=True)
    media = fetch_ona_jp_popular(floor)
    added = 0
    for m in media:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        sd = m.get("startDate") or {}
        season = m.get("season") or _season_from_month(sd.get("month")) or "WINTER"
        yr = m.get("seasonYear") or sd.get("year") or date.today().year
        anime.append(make_record(m, yr, season))
        added += 1
    write_catalog(anime)
    print(f"\n完了: JP-ONA を {added} 件追加（ハングル除外後の総数は再読込で確認）。", flush=True)


ONA_JP_FLOOR = 2000  # 自動更新で取り込む人気JP-ONAの popularity 下限


def run_update():
    """四半期ごとの自動更新用。現在の年の TV/ショート(クール)・劇場・OVA に加え、
    人気JP-ONA も取得して既存にマージする（新クール・新作・新規配信作の補完。軽量）。"""
    cur = date.today().year
    print(f"自動更新: {cur}年(クール/劇場/OVA) + 人気JP-ONA をマージ", flush=True)
    run_range_merge(cur, cur)
    run_ona_jp_merge(ONA_JP_FLOOR)


def run_full(start_year):
    """TV/ショート（クール別）と劇場（公開年別）をすべて取得。"""
    seasons = season_list(start_year)
    years = movie_years(start_year)
    print(f"対象: {start_year} 〜 現在 / TV・ショート {len(seasons)}クール + 劇場 {len(years)}年分", flush=True)

    seen = {}

    def ingest(media, year, season, force_fmt=None):
        for m in media:
            if m["id"] in seen:
                continue
            seen[m["id"]] = make_record(m, year, season, force_fmt=force_fmt)

    # TV / ショート: 季節（クール）ごと
    for n, (year, season) in enumerate(seasons, 1):
        print(f"[TV/SHORT {n}/{len(seasons)}] {year} {season} ...", flush=True)
        media = fetch_list(year, season, ["TV", "TV_SHORT"])
        ingest(media, year, season)
        print(f"    取得 {len(media)} 件 / 累計 {len(seen)} 件", flush=True)
        time.sleep(1.2)

    # 劇場 / OVA: 公開年ごと（startDate 年範囲）
    for fmt in YEARLY_FORMATS:
        for n, year in enumerate(years, 1):
            print(f"[{fmt} {n}/{len(years)}] {year} ...", flush=True)
            media = fetch_yearly(year, fmt, retry_on_empty=True)
            ingest(media, year, None, force_fmt=fmt)
            print(f"    取得 {len(media)} 件 / 累計 {len(seen)} 件", flush=True)
            time.sleep(1.2)

    write_catalog(list(seen.values()))
    print(f"\n完了: {OUT_PATH} に {len(seen)} 作品を書き出しました。", flush=True)


def main():
    args = sys.argv[1:]
    if args and args[0] == "--update":
        run_update()
    elif args and args[0] == "--ona-jp":
        floor = int(args[1]) if len(args) > 1 else 2000
        run_ona_jp_merge(floor)
    elif args and args[0] == "--add":
        run_add(args[1:])
    elif args and args[0] == "--range":
        lo = int(args[1])
        hi = int(args[2]) if len(args) > 2 else lo
        run_range_merge(lo, hi)
    elif args and args[0] in ("--movies", "--movie", "--merge"):
        start_year = int(args[1]) if len(args) > 1 else 1990
        run_yearly_merge("MOVIE", start_year)
    elif args and args[0] == "--ova":
        start_year = int(args[1]) if len(args) > 1 else 1990
        run_yearly_merge("OVA", start_year)
    else:
        start_year = int(args[0]) if args else 2000
        run_full(start_year)


if __name__ == "__main__":
    main()
