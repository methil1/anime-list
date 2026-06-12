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


# PV・ティザー・CM・MV・YouTube限定ミニアニメ等の宣伝/おまけ映像を除外する判定。
# ONA一括取込(--ona-jp)で混入しやすい。PV/CM/MV は前後に英数字が無い単独トークンのみ一致。
PROMO_RE = re.compile(
    r"ティザー|予告|特報|番宣|ミニアニメ|ぷちアニメ|ミュージックビデオ|ノンクレジット"
    r"|Music\s*Video|Teaser|Trailer|Promotion(?:al)?(?:\s*Video)?"
    r"|(?<![A-Za-z0-9])(?:PV|CM|MV)s?(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def is_promo(m):
    """AniList media がPV/ティザー/ミニアニメ等の宣伝・おまけ映像かをタイトルで判定。"""
    t = m.get("title") or {}
    return bool(PROMO_RE.search(f"{t.get('native') or ''} / {t.get('romaji') or ''}"))


# 無料動画サイトのみで配信されるONA（Web限定ミニアニメ等）を除外するための判定。
# ストリーミングリンクが以下のサイトだけの作品は正規配信が無いとみなす。
FREE_VIDEO_SITES = {"youtube", "twitter", "vimeo"}


def is_free_video_only(m):
    """配信が YouTube/Twitter/Vimeo のみの作品か。

    STREAMINGリンクがあればそれだけで判定。無い場合（Twitter限定ミニ等は
    SOCIALリンクのみのことがある）は全リンクで判定し、公式サイト等が
    1つでもあれば保持。リンク情報が皆無なら判定不能として保持。
    """
    links = m.get("externalLinks") or []
    streaming = [(l.get("site") or "").lower() for l in links if l.get("type") == "STREAMING"]
    if streaming:
        return all(s in FREE_VIDEO_SITES for s in streaming)
    sites = [(l.get("site") or "").lower() for l in links]
    return bool(sites) and all(s in FREE_VIDEO_SITES for s in sites)


# ONA除外フィルタ(is_promo/is_free_video_only/is_minor_ona)を適用しない保持リスト。
# AniListのデータ不備(スタッフ1人登録等)で機械判定に引っかかる有名作をここに足す。
# 人気度では分離不可(刃牙道2806 < からめるハニー5259 等)のため手動リストで管理。
ONA_KEEP_IDS = {
    20962,   # ヘタリア The World Twinkle
    19469,   # 斉木楠雄のΨ難 (ONA)
    210032,  # 刃牙道 第2クール
    21678,   # 暗殺教室 2 課外授業編
    20859,   # 逃亡者・毛利小五郎
}


# 手動除外リスト。is_excluded_movie 等の機械判定では拾えないが、
# カタログに載せたくない作品の AniList ID をここに足す（全モード共通で write_catalog が除外）。
EXCLUDE_IDS = {
    176879,  # 箱の時代
    103549,  # ナヌムの家
    10149,   # 魔法阿媽 (台湾制作・countryOfOrigin=TWでCNフィルタ外)
    103456,  # 穴 -the ten hole stories-
    145442,  # BIBLIOMANIA
}


def is_minor_ona(m):
    """1話1分の作品・スタッフ登録が1人の作品（ロゴ映像/個人制作の小品）を判定。

    注: staff の pageInfo.total はAniListが不正確な値(500等)を返すため、
    perPage:2 で取得した edges の件数で「1人」を判定する。
    """
    if (m.get("duration") or 0) == 1:
        return True
    edges = ((m.get("staff") or {}).get("edges"))
    return edges is not None and len(edges) == 1

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

# 原作種別（AniList source enum）の日本語化。ホバー情報カードの「原作」に表示。
SOURCE_JA = {
    "ORIGINAL": "オリジナル", "MANGA": "漫画", "LIGHT_NOVEL": "ライトノベル",
    "VISUAL_NOVEL": "ビジュアルノベル", "VIDEO_GAME": "ゲーム", "GAME": "ゲーム",
    "NOVEL": "小説", "WEB_NOVEL": "Web小説", "DOUJINSHI": "同人誌",
    "ANIME": "アニメ", "MANHWA": "漫画", "MANHUA": "漫画", "COMIC": "コミック",
    "LIVE_ACTION": "実写", "MULTIMEDIA_PROJECT": "メディアミックス",
    "PICTURE_BOOK": "絵本", "CARD_GAME": "カードゲーム", "MUSIC": "音楽",
    "OTHER": "その他",
}


def source_ja(m):
    """AniList の source enum を日本語ラベルに変換（無い/不明なら None）。"""
    s = m.get("source")
    return SOURCE_JA.get(s) if s else None


def studio_name(m):
    """制作会社名を取得。isMain の制作会社を優先し、最大2社を「・」連結。"""
    edges = ((m.get("studios") or {}).get("edges")) or []
    mains = [e["node"]["name"] for e in edges if e.get("isMain") and e.get("node")]
    if not mains:
        mains = [e["node"]["name"] for e in edges if e.get("node")][:1]
    return "・".join(mains[:2]) if mains else None


def char_pairs(m):
    """メインキャラ（最大5）を [キャラ名, 日本語CV名] の配列で返す。
    UIは先頭4件を表示し、5件目があれば「…」で続きを示す。CV未登録は名前のみ。"""
    edges = ((m.get("characters") or {}).get("edges")) or []
    out = []
    for e in edges:
        nm = ((e.get("node") or {}).get("name")) or {}
        cname = nm.get("native") or nm.get("full")
        if not cname:
            continue
        vas = e.get("voiceActors") or []
        cv = None
        if vas:
            van = vas[0].get("name") or {}
            cv = van.get("native") or van.get("full")
        out.append([cname, cv] if cv else [cname])
    return out or None

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
      source
      studios { edges { isMain node { name } } }
      characters(role: MAIN, sort: [ROLE, RELEVANCE], perPage: 5) {
        edges { node { name { native full } } voiceActors(language: JAPANESE) { name { native full } } }
      }
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
      countryOfOrigin
      duration
      averageScore
      genres
      coverImage { medium }
      startDate { year }
      source
      studios { edges { isMain node { name } } }
      characters(role: MAIN, sort: [ROLE, RELEVANCE], perPage: 5) {
        edges { node { name { native full } } voiceActors(language: JAPANESE) { name { native full } } }
      }
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
      duration
      externalLinks { site type }
      staff(perPage: 2) { edges { node { id } } }
      source
      studios { edges { isMain node { name } } }
      characters(role: MAIN, sort: [ROLE, RELEVANCE], perPage: 5) {
        edges { node { name { native full } } voiceActors(language: JAPANESE) { name { native full } } }
      }
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
        # 中国制作・短編の劇場版は取得段階で除外（OVA等は is_excluded_movie が素通し）
        items.extend(m for m in pg["media"] if not is_excluded_movie(m))
        if not pg["pageInfo"]["hasNextPage"]:
            break
        page += 1
        time.sleep(1.2)
    return items


# 上映時間がこの分数以下の劇場版は短編・PV的小品として除外する。
MOVIE_MIN_DURATION = 20


def is_excluded_movie(m):
    """劇場(MOVIE)の除外対象を判定する。
    1) 中国制作(countryOfOrigin=CN)の劇場版（donghua）。字面では日本と区別
       できないが countryOfOrigin で機械的に分離できる。
    2) 上映時間が MOVIE_MIN_DURATION 分以下の劇場版（短編・特典映像・PV的小品）。
       duration 不明(None)は過剰除外を避けるため保持する。
    MOVIE 以外（OVA など）は対象外。"""
    if (m.get("format") or "") != "MOVIE":
        return False
    if (m.get("countryOfOrigin") or "") == "CN":
        return True
    dur = m.get("duration")
    return dur is not None and dur <= MOVIE_MIN_DURATION


def fetch_movies(year, retry_on_empty=False):
    return fetch_yearly(year, "MOVIE", retry_on_empty)


# 個別追加用: タイトル検索 / ID 指定。ONA など通常対象外の format も取り込む。
ADD_FIELDS = ("id title{romaji native} episodes season seasonYear format averageScore genres coverImage{medium} startDate{year} "
              "source studios{edges{isMain node{name}}} "
              "characters(role: MAIN, sort: [ROLE, RELEVANCE], perPage: 5){edges{node{name{native full}} voiceActors(language: JAPANESE){name{native full}}}}")
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
    rec = {
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
        "a": date.today().isoformat(),  # カタログへの追加日（新着表示用）
    }
    enrich_record(rec, m)
    return rec


def enrich_record(rec, m):
    """ホバー情報カード用の原作(src)/制作(st)/メインキャラ(ch)をレコードに付与。
    取得できた項目だけ追加し、ch は「処理済み」を表すため空でも [] を入れる。"""
    src = source_ja(m)
    if src:
        rec["src"] = src
    else:
        rec.pop("src", None)
    st = studio_name(m)
    if st:
        rec["st"] = st
    else:
        rec.pop("st", None)
    rec["ch"] = char_pairs(m) or []


# 同一年内の表示順: クール（冬春夏秋）→ OVA → 劇場
def _season_order(s):
    return {"WINTER": 0, "SPRING": 1, "SUMMER": 2, "FALL": 3, "OVA": 4, "MOVIE": 5}.get(s, 9)


def write_catalog(anime):
    # 韓国作品（ハングルタイトル）は日本のアニメリストから除外
    anime = [a for a in anime if not has_hangul(a)]
    # 手動除外リスト（EXCLUDE_IDS）の作品を除外
    anime = [a for a in anime if a["id"] not in EXCLUDE_IDS]
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
        if m["id"] not in ONA_KEEP_IDS:   # 保持リストの作品は除外フィルタをバイパス
            if is_promo(m):   # PV/ティザー/CM/ミニアニメ等は本編ではないので除外
                continue
            if is_free_video_only(m):   # YouTube/Twitter/Vimeoのみ配信のWeb限定作品は除外
                continue
            if is_minor_ona(m):   # 1話1分・スタッフ1人の小品は除外
                continue
        sd = m.get("startDate") or {}
        season = m.get("season") or _season_from_month(sd.get("month")) or "WINTER"
        yr = m.get("seasonYear") or sd.get("year") or date.today().year
        anime.append(make_record(m, yr, season))
        added += 1
    write_catalog(anime)
    print(f"\n完了: JP-ONA を {added} 件追加（ハングル除外後の総数は再読込で確認）。", flush=True)


# 既存カタログに原作/制作/メインキャラを後付けするエンリッチ用クエリ（id_in でバッチ取得）。
ENRICH_QUERY = """
query ($ids: [Int]) {
  Page(perPage: 25) {
    media(id_in: $ids) {
      id
      source
      studios { edges { isMain node { name } } }
      characters(role: MAIN, sort: [ROLE, RELEVANCE], perPage: 5) {
        edges { node { name { native full } } voiceActors(language: JAPANESE) { name { native full } } }
      }
    }
  }
}
"""


def run_enrich(force=False, batch=20):
    """既存 anime-data.js の各作品に原作(src)/制作(st)/メインキャラ(ch)を後付けする。
    ch フィールドが無いものだけを対象に id_in でバッチ取得（中断後の再実行で続きから）。
    force=True で全件再取得。途中で定期チェックポイント保存する。"""
    existing = load_existing()
    anime = list(existing.get("anime", []))
    by_id = {a["id"]: a for a in anime}
    todo = [a["id"] for a in anime if force or "ch" not in a]
    print(f"エンリッチ対象: {len(todo)} / 全 {len(anime)} 件 (batch={batch})", flush=True)
    done = 0
    for i in range(0, len(todo), batch):
        ids = todo[i:i + batch]
        data = post(ENRICH_QUERY, {"ids": ids})
        if "errors" in data:
            print(f"    GraphQL error: {data['errors']}", flush=True)
            time.sleep(3)
            continue
        for m in data["data"]["Page"]["media"]:
            a = by_id.get(m["id"])
            if a is not None:
                enrich_record(a, m)
        done += len(ids)
        step = i // batch
        if step % 20 == 0:
            print(f"    {done}/{len(todo)} 件処理 ...", flush=True)
        if step and step % 50 == 0:
            write_catalog(anime)  # 定期チェックポイント（中断対策）
        time.sleep(1.0)
    write_catalog(anime)
    print(f"\n完了: {done} 件をエンリッチしました（{OUT_PATH} 更新済み）。", flush=True)


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
    elif args and args[0] == "--enrich":
        force = "--force" in args
        run_enrich(force=force)
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
