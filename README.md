# 🎬 アニメ視聴カタログ

[AniList](https://anilist.co) を元データにした、TV / ショート / OVA / 劇場アニメの視聴記録サイト。
1990〜現在までの作品をクール（冬・春・夏・秋）別に一覧し、ポスターをクリックするだけで視聴状態を記録できます。

**🌐 公開ページ: https://methil1.github.io/anime-list/**

ビルド不要・依存ライブラリなしの**単一 HTML + ローカル JS** 構成。視聴状態はブラウザの `localStorage` に保存されます（サーバー不要・完全クライアントサイド）。

---

## ✨ 特徴

- **クール別カタログ** — 年タブ × クール（冬春夏秋）でポスター表示。OVA・劇場は公開年別。
- **ワンクリック視聴記録** — ポスターをクリックで「未マーク → 視聴中 → 視聴済」を循環。状態は `localStorage` に永続化。
- **複数選択フィルタ** — 状態（視聴済/視聴中/未視聴）と形式（TV/ショート/OVA/劇場）をトグルで絞り込み。
- **視聴コレクション** — 視聴済・視聴中の作品だけを「年代 → 年 → クール」の折りたたみ階層で表示。評価順表示にも切替可能。
- **🆕 新着ビュー** — 追加日（更新日）を最上位グループにし、各日の中を「年代 → 年 → クール」で階層表示。
- **横断検索** — 作品名・制作会社・声優・原作者で全年代を串刺し検索。
- **✨ おすすめ（レコメンド）** — 視聴履歴と自己評価からジャンル・原作・制作・原作者の嗜好プロファイルを作り、未視聴作品をスコアリングして提案。完全クライアントサイド。
- **📺 シリーズ対応** — 同一ベースタイトルをシリーズとして扱い、「見たいシリーズ」リストに一括登録して専用ビューで追跡したり、「シリーズごと興味なし」でおすすめ・好み学習から丸ごと除外できます。
- **ホバー情報カード** — 原作種別・制作会社・メインキャラ＋CV・放映日時／公開日／発売日を表示。
- **右クリックメニュー** — Wikipedia / AniList / 公式サイト / プライム・ビデオへのリンク、自己評価（★1〜5）・視聴状態の設定、おすすめ除外・シリーズの見たい／興味なし操作。
- **書き出し** — 視聴記録を JSON / CSV / コレクション画像（JPEG）でエクスポート。
- **四半期自動更新** — Windows タスクスケジューラで現行年のクール／劇場／OVA を自動再取得・コミット・プッシュ。

---

## 📁 構成

| ファイル | 役割 |
|---|---|
| `index.html` | カタログ閲覧 UI（HTML / CSS / JS を 1 ファイルに同梱）。 |
| `anime-data.js` | `window.ANIME_CATALOG` への代入。CORS 回避のため `.json` ではなく `.js`。 |
| `scrape_anime.py` | AniList GraphQL から取得し `anime-data.js` を生成するスクレイパー。 |
| `auto_update.bat` | 四半期自動更新タスクが叩くバッチ（`--update` → git commit → push）。 |

ローカルで見るには `index.html` をブラウザで直接開くだけです（`file://` で動作）。

---

## 🗂️ データ構造

`anime-data.js` は次の形のオブジェクトを `window.ANIME_CATALOG` に代入します。

```js
window.ANIME_CATALOG = {
  created:   "2026-06-11",          // 初回生成日
  generated: "2026-06-14",          // 最終生成日
  source:    "AniList (https://anilist.co)",
  count:     10266,
  anime: [ /* レコード配列 */ ]
};
```

各レコードのフィールド:

| キー | 内容 |
|---|---|
| `id` | AniList の作品 ID（`anilist.co/anime/{id}` に対応） |
| `t` / `tr` | 日本語タイトル / ローマ字タイトル |
| `y` | 放送年（劇場・OVA は公開／発売年） |
| `s` | `WINTER` / `SPRING` / `SUMMER` / `FALL` / `OVA` / `MOVIE` |
| `f` | 形式 `TV` / `SHORT` / `OVA` / `MOVIE`（ONA は `TV` 扱い） |
| `ep` | 話数 |
| `img` | ポスター画像 URL |
| `sc` | AniList 平均スコア |
| `g` | ジャンル配列 |
| `a` | 追加日（ISO `YYYY-MM-DD`、新着ビューの軸） |
| `src` | 原作種別（漫画 / ライトノベル / オリジナル 等） |
| `st` | 制作会社 |
| `ch` | メインキャラ＋CV `[[キャラ名, 声優名], …]` |
| `os` | 公式サイト URL |
| `d` | 公開／発売日（int `YYYYMMDD`） |
| `air` | 第1話放送日時（UNIX 秒, UTC） |
| `bc` | 放送曜日・時刻 `[曜日index(0=日), "HH:MM"]`（旧作の MAL 補完） |
| `au` | 原作者 |
| `nr` / `kk` | なろう発 / カクヨム発フラグ |

> 方針: 日本のアニメリストのため、タイトルにハングルを含む韓国作品は除外。中国 donghua・短編映画・PV/CM/MV・無料動画限定 ONA も品質維持のため除外しています。

---

## 🐍 スクレイパーの使い方

AniList GraphQL（`https://graphql.anilist.co`）から取得します。**User-Agent ヘッダ必須**（無いと 403）。

> Windows / PowerShell で実行する際は、日本語の print が cp932 で落ちないよう `$env:PYTHONIOENCODING="utf-8"` を設定してください。

```bash
python scrape_anime.py              # 全取得（TV/ショート=クール別 + 劇場=公開年別）2000〜現在
python scrape_anime.py 2010         # 開始年を指定して全取得
python scrape_anime.py --update     # 現行年のクール/劇場/OVA だけ再取得しマージ（軽量・自動更新用）
python scrape_anime.py --movies     # 劇場アニメだけ取得し既存にマージ
python scrape_anime.py --ova        # OVA だけ取得し既存にマージ（公開年別）
python scrape_anime.py --range 1990 1999   # 指定年範囲の TV/ショート+劇場を取得しマージ
python scrape_anime.py --ona-jp 2000       # 人気の日本製 ONA（配信作）を popularity>=floor で取込
python scrape_anime.py --add "とんがり帽子のアトリエ" 200769  # 個別作品をタイトル or ID で補完
```

エンリッチ系（既存データへの後付け・未設定分のみ。`--force` で全件再取得）:

```bash
python scrape_anime.py --enrich     # 原作/制作会社/キャラ/公式サイト等を後付け
python scrape_anime.py --dates      # OVA/劇場の公開・発売日を後付け
python scrape_anime.py --broadcast  # 旧作の放送曜日・時刻を MAL(Jikan API) から補完
python scrape_anime.py --authors    # 原作者(au) を後付け
python scrape_anime.py --narou      # 原作が小説系/その他の作品をなろう公式 API で照合し nr=1 付与
python scrape_anime.py --kakuyomu   # 同上をカクヨム検索で照合し kk=1 付与
```

---

## ⏱️ 自動更新

四半期ごと（1/1・4/1・7/1・10/1）に Windows タスクスケジューラ（タスク名 `AnimeCatalogQuarterly`）が `auto_update.bat` を実行し、
`python scrape_anime.py --update` → `git add anime-data.js` → commit → `git push origin main` を自動で行います。
当日 PC がオフでも、次回起動時に実行されます（`StartWhenAvailable`）。

再登録:

```bash
schtasks /create /tn AnimeCatalogQuarterly /tr <auto_update.bat のフルパス> ^
  /sc MONTHLY /d 1 /m JAN,APR,JUL,OCT /st 12:00 /f
```

> `.bat` のコメントは cp932 化け回避のため ASCII のみにしてください。git 認証は Windows 資格情報マネージャ依存です。

---

## 📜 データ出典・ライセンス

- アニメ情報・ポスター画像の出典: **[AniList](https://anilist.co)**。放送曜日・時刻の一部は **[MyAnimeList / Jikan API](https://jikan.moe)** から補完。
- 各作品の権利は原権利者に帰属します。本リポジトリは個人の視聴記録を目的とした非商用プロジェクトです。
